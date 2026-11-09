import os
import sys
import json
import html
import time
import signal
import threading
import logging
from io import BytesIO
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import websocket
import tweepy
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter

# ===== CONFIG (from environment) =====
# Required:
#   TELEGRAM_TOKEN
# Optional:
#   CHAT_ID (default: @bitcoin500alerts)
#   PORT (default: 8000)
#   PRICE_THRESHOLD (default: 500)
#   PRICE_LOG_INTERVAL (default: 10)
#   SYMBOL (default: BTCUSDT)
#   BINANCE_BASE_URL (default: https://data-api.binance.vision)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "-1003175403499")
PORT = int(os.getenv("PORT", "8000"))
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "500"))
PRICE_LOG_INTERVAL = float(os.getenv("PRICE_LOG_INTERVAL", "10"))
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://data-api.binance.vision")
X_POSTS_ENABLED = os.getenv("X_POSTS_ENABLED", "false").lower() in ("1", "true", "yes")
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
X_CREDENTIALS_READY = all((X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET))
BLOGGER_ENABLED = os.getenv("BLOGGER_ENABLED", "false").lower() in ("1", "true", "yes")
BLOGGER_CLIENT_ID = os.getenv("BLOGGER_CLIENT_ID")
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET")
BLOGGER_REFRESH_TOKEN = os.getenv("BLOGGER_REFRESH_TOKEN")
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
BLOGGER_CREDENTIALS_READY = all((
    BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID
))

# ===== LOGGING =====
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bitcoin500")

# ===== VALIDATION (fail fast on bad config) =====
if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN is required but not set. Exiting.")
    sys.exit(1)

if PRICE_THRESHOLD <= 0:
    logger.critical("PRICE_THRESHOLD must be > 0, got %s. Exiting.", PRICE_THRESHOLD)
    sys.exit(1)

if PRICE_LOG_INTERVAL <= 0:
    logger.critical("PRICE_LOG_INTERVAL must be > 0, got %s. Exiting.", PRICE_LOG_INTERVAL)
    sys.exit(1)

if X_POSTS_ENABLED:
    if X_CREDENTIALS_READY:
        logger.info("[X] Cross-posting is enabled")
    else:
        logger.warning("[X] Posting is enabled but one or more X API credentials are missing")

if BLOGGER_ENABLED:
    if BLOGGER_CREDENTIALS_READY:
        logger.info("[BLOGGER] Cross-posting is enabled")
    else:
        logger.warning("[BLOGGER] Posting is enabled but Blogger credentials are incomplete")

# ===== HTTP SESSION (connection reuse for both Binance + Telegram) =====
_http_session = requests.Session()

# ===== STOP CONTROL =====
_stop_event = threading.Event()
_httpd_ref = None


def _escape_markdown(text: str) -> str:
    """Escape characters that break Telegram legacy Markdown parsing."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram(text: str) -> bool:
    """Send a Telegram message to the configured chat."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN is not set; skipping Telegram send")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        r = _http_session.post(url, json=payload, timeout=10)
        try:
            result = r.json()
        except ValueError:
            result = {}

        if r.status_code != 200 or not result.get("ok"):
            logger.warning(
                "Telegram send failed: http_status=%s description=%s body=%s",
                r.status_code,
                result.get("description", "Telegram returned no success confirmation"),
                r.text[:1000],
            )
            return False
        else:
            logger.info(
                "Telegram accepted message for %s (message_id=%s)",
                CHAT_ID,
                result.get("result", {}).get("message_id"),
            )
            return True
    except requests.RequestException as e:
        logger.exception("Telegram request error: %s", e)
        return False


def _send_x_chart(text: str, chart: bytes) -> bool:
    """Upload the alert chart and publish it using X account user-context auth."""
    if not X_POSTS_ENABLED:
        return False
    if not X_CREDENTIALS_READY:
        logger.warning("[X] Skipping post because X API credentials are incomplete")
        return False

    try:
        auth = tweepy.OAuth1UserHandler(
            X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
        )
        api = tweepy.API(auth)
        media = api.media_upload(
            filename="bitcoin500-chart.png",
            file=BytesIO(chart),
            media_category="tweet_image",
        )
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
        result = client.create_tweet(text=text, media_ids=[str(media.media_id)])
        post_id = result.data.get("id") if result.data else None
        logger.info("[X] Chart post accepted (post_id=%s)", post_id)
        return True
    except Exception as error:
        logger.exception("[X] Chart post failed: %s", error)
        return False


def send_x_chart_async(text: str, chart: bytes) -> None:
    """Post in the background so X API latency won't pause price monitoring."""
    if not X_POSTS_ENABLED:
        return
    worker = threading.Thread(
        target=_send_x_chart,
        args=(text, chart),
        name="x-crosspost",
        daemon=True,
    )
    worker.start()


def _send_blogger_post(title: str, html_content: str) -> bool:
    """Publish a price update to the configured Blogger blog."""
    if not BLOGGER_ENABLED:
        return False
    if not BLOGGER_CREDENTIALS_READY:
        logger.warning("[BLOGGER] Skipping post because Blogger credentials are incomplete")
        return False

    try:
        token_response = _http_session.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": BLOGGER_CLIENT_ID,
                "client_secret": BLOGGER_CLIENT_SECRET,
                "refresh_token": BLOGGER_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        if token_response.status_code != 200:
            logger.warning("[BLOGGER] OAuth token refresh failed: HTTP %s", token_response.status_code)
            return False
        access_token = token_response.json().get("access_token")
        if not access_token:
            logger.warning("[BLOGGER] OAuth token refresh returned no access token")
            return False

        response = _http_session.post(
            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
            params={"isDraft": "false"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={"kind": "blogger#post", "title": title, "content": html_content},
            timeout=20,
        )
        if response.status_code != 200:
            logger.warning("[BLOGGER] Post failed: HTTP %s body=%s", response.status_code, response.text[:500])
            return False
        post = response.json()
        logger.info("[BLOGGER] Post published (post_id=%s url=%s)", post.get("id"), post.get("url"))
        return True
    except (requests.RequestException, ValueError) as error:
        logger.warning("[BLOGGER] Post failed: %s", error)
        return False


def send_blogger_post_async(title: str, html_content: str) -> None:
    """Publish off-thread so Google API latency cannot interrupt price monitoring."""
    if not BLOGGER_ENABLED:
        return
    worker = threading.Thread(
        target=_send_blogger_post,
        args=(title, html_content),
        name="blogger-crosspost",
        daemon=True,
    )
    worker.start()


def _blogger_content(price: float, change: float = None):
    """Build a compact public Blogger post from a live price update."""
    timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")
    safe_symbol = html.escape(SYMBOL)
    title = f"BITCOIN 500 | {safe_symbol} ${price:,.2f}"
    direction = "" if change is None else ("Up" if change > 0 else "Down")
    change_html = (
        "" if change is None else
        f"<p><strong>Move:</strong> {direction} ${abs(change):,.2f} from the last alert reference.</p>"
    )
    content = (
        f"<h2>₿ {safe_symbol} live price: ${price:,.2f}</h2>"
        f"{change_html}"
        f"<p><strong>Updated:</strong> {timestamp}</p>"
        "<p>Follow <a href=\"https://t.me/bitcoin500alerts\">BITCOIN 500 on Telegram</a> "
        "for threshold-based BTC price alerts.</p>"
        "<p><em>Market information only. Not financial advice or a trading recommendation.</em></p>"
    )
    return title, content


def _get_chart_candles(symbol: str, limit: int = 48):
    """Fetch recent 15-minute Binance candles for the alert chart."""
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    response = _http_session.get(
        url,
        params={"symbol": symbol, "interval": "15m", "limit": limit},
        timeout=10,
    )
    if response.status_code != 200:
        raise BinancePublicAPIError(f"Klines HTTP {response.status_code}: {response.text[:500]}")
    candles = response.json()
    if not isinstance(candles, list) or not candles:
        raise BinancePublicAPIError(f"Unexpected kline response: {candles}")
    return candles


def _create_chart(symbol: str, current_price: float) -> bytes:
    """Render a clean dark candlestick snapshot and return PNG bytes."""
    candles = _get_chart_candles(symbol)
    times = [datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc) for candle in candles]
    opens = [float(candle[1]) for candle in candles]
    highs = [float(candle[2]) for candle in candles]
    lows = [float(candle[3]) for candle in candles]
    closes = [float(candle[4]) for candle in candles]
    volumes = [float(candle[5]) for candle in candles]

    fig, (price_ax, volume_ax) = plt.subplots(
        2, 1, figsize=(10, 5.6), dpi=160, sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.06},
    )
    background = "#101820"
    fig.patch.set_facecolor(background)
    for axis in (price_ax, volume_ax):
        axis.set_facecolor(background)
        axis.grid(True, color="#263440", linewidth=0.65, alpha=0.8)
        axis.tick_params(colors="#91a0ad", labelsize=8, length=0, pad=7)
        for spine in axis.spines.values():
            spine.set_visible(False)

    x_values = mdates.date2num(times)
    candle_width = (x_values[1] - x_values[0]) * 0.62 if len(x_values) > 1 else 0.008
    for x, opening, high, low, close, volume in zip(
        x_values, opens, highs, lows, closes, volumes
    ):
        color = "#36c98f" if close >= opening else "#ff6474"
        price_ax.vlines(x, low, high, color=color, linewidth=1.0, alpha=0.95)
        body_bottom = min(opening, close)
        body_height = max(abs(close - opening), current_price * 0.000025)
        price_ax.add_patch(Rectangle(
            (x - candle_width / 2, body_bottom), candle_width, body_height,
            facecolor=color, edgecolor=color, linewidth=0.5,
        ))
        volume_ax.bar(x, volume, width=candle_width, color=color, alpha=0.65, linewidth=0)

    price_ax.text(
        0.5, 0.5, "@bitcoin500alerts",
        transform=price_ax.transAxes,
        ha="center", va="center",
        color="#29343d", alpha=0.82,
        fontsize=24, fontweight="bold", zorder=0.5,
    )

    price_ax.axhline(current_price, color="#65b9ff", linewidth=0.9, alpha=0.8)
    price_ax.set_xlim(x_values[0] - candle_width, x_values[-1] + candle_width * 4)
    price_ax.set_ylim(min(lows) * 0.999, max(highs) * 1.001)
    price_ax.yaxis.tick_right()
    price_ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:,.0f}"))
    volume_ax.yaxis.tick_right()
    volume_ax.yaxis.set_major_formatter(FuncFormatter(
        lambda value, _: (
            f"{value / 1000:.1f}k" if abs(value) >= 1000
            else f"{value:.2f}" if abs(value) < 1
            else f"{value:,.1f}"
        )
    ))
    volume_ax.set_ylabel("BTC", rotation=0, color="#91a0ad", fontsize=8, labelpad=15)
    volume_ax.yaxis.set_label_position("right")
    volume_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=timezone.utc))
    volume_ax.set_xlabel("UTC  ·  15 minute candles  ·  last 12 hours", color="#91a0ad", fontsize=8, labelpad=8)
    fig.suptitle(f"{symbol}  ·  Binance Spot", x=0.08, ha="left", color="#f2f5f7", fontsize=14, fontweight="semibold")
    price_ax.set_title(f"LIVE PRICE   ${current_price:,.2f}", loc="left", color="#65b9ff", fontsize=10, pad=10)
    fig.subplots_adjust(left=0.08, right=0.94, top=0.88, bottom=0.12)

    image = BytesIO()
    fig.savefig(image, format="png", facecolor=background, bbox_inches="tight")
    plt.close(fig)
    return image.getvalue()


def send_telegram_chart(caption: str, price: float, chart: bytes = None) -> bool:
    """Send a chart photo with a caption; return False so callers can fall back to text."""
    try:
        if chart is None:
            chart = _create_chart(SYMBOL, price)
    except Exception as error:
        logger.warning("Chart generation failed; sending text only: %s", error)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        response = _http_session.post(
            url,
            data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("bitcoin-price.png", chart, "image/png")},
            timeout=30,
        )
        try:
            result = response.json()
        except ValueError:
            result = {}
        if response.status_code != 200 or not result.get("ok"):
            logger.warning(
                "Telegram chart send failed: http_status=%s description=%s",
                response.status_code,
                result.get("description", response.text[:500]),
            )
            return False
        logger.info(
            "Telegram accepted chart for %s (message_id=%s)",
            CHAT_ID,
            result.get("result", {}).get("message_id"),
        )
        return True
    except requests.RequestException as error:
        logger.exception("Telegram chart request error: %s", error)
        return False


class BinancePublicAPIError(Exception):
    """Raised when Binance's public REST API returns an error payload."""
    pass


# ===== HEALTH CHECK SERVER =====
class Handler(BaseHTTPRequestHandler):
    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._respond(200, b"OK")
            return

        if self.path == "/status":
            self._respond(200, b"RUNNING")
            return

        self.send_error(404, "Not Found")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    global _httpd_ref
    logger.info("[HEALTH] Starting health server on port %s", PORT)
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.timeout = 1.0
    _httpd_ref = httpd

    while not _stop_event.is_set():
        httpd.handle_request()

    httpd.server_close()
    logger.info("[HEALTH] Health server stopped")


# ===== BTC LOOP =====
def btc_loop() -> None:
    logger.info(
        "[BOT] Mini-ticker stream starting (symbol=%s threshold=%s)",
        SYMBOL, PRICE_THRESHOLD,
    )
    logger.info("[BOT] Telegram destination: %s", CHAT_ID)
    # The raw @trade stream can emit many messages per second. The mini ticker
    # updates once per second and is sufficient for threshold price alerts.
    stream_url = f"wss://data-stream.binance.vision:443/ws/{SYMBOL.lower()}@miniTicker"
    reference_price = None
    backoff = 1.0

    while not _stop_event.is_set():
        connection = None
        try:
            logger.info("[BINANCE] Connecting to 1-second mini-ticker stream")
            connection = websocket.create_connection(stream_url, timeout=10)
            connection.settimeout(1)
            logger.info("[BINANCE] Mini-ticker stream connected")
            backoff = 1.0
            last_price_log = 0.0

            while not _stop_event.is_set():
                try:
                    raw_event = connection.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw_event:
                    raise websocket.WebSocketConnectionClosedException("Empty stream response")

                event = json.loads(raw_event)
                price = float(event["c"])
                if reference_price is None:
                    reference_price = price
                    logger.info("[START PRICE] %s", price)
                    startup_message = (
                        f"₿  *{_escape_markdown(SYMBOL)}  ·  Bitcoin price*\n\n"
                        f"💵  *${price:,.2f}*\n\n"
                        f"🕒  Updated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M:%S')} UTC"
                    )
                    x_startup_message = (
                        f"₿ {SYMBOL} · Bitcoin price\n\n"
                        f"💵 ${price:,.2f}\n"
                        f"🕒 Updated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M:%S')} UTC\n\n"
                        "Join our Telegram: https://t.me/bitcoin500alerts"
                    )
                    try:
                        chart = _create_chart(SYMBOL, price)
                    except Exception as error:
                        logger.warning("Chart generation failed; sending text only: %s", error)
                        chart = None
                    for attempt in range(1, 4):
                        delivered = send_telegram_chart(startup_message, price, chart) if chart else False
                        if not delivered:
                            delivered = send_telegram(startup_message)
                        if delivered:
                            break
                        if attempt < 3:
                            delay = attempt * 2
                            logger.warning("[STARTUP MESSAGE] Retry %s/3 in %s seconds", attempt + 1, delay)
                            _stop_event.wait(delay)
                    else:
                        logger.error("[STARTUP MESSAGE] Could not deliver startup price after 3 attempts")
                    if chart:
                        send_x_chart_async(x_startup_message, chart)
                    elif X_POSTS_ENABLED:
                        logger.warning("[X] Startup cross-post skipped because the chart couldn't be created")
                    if BLOGGER_ENABLED:
                        blogger_title, blogger_content = _blogger_content(price)
                        send_blogger_post_async(blogger_title, blogger_content)
                    continue

                diff = price - reference_price
                now = time.monotonic()
                if now - last_price_log >= PRICE_LOG_INTERVAL:
                    logger.info(
                        "[PRICE] %s = $%s (change from alert reference: %+.2f USD)",
                        SYMBOL, f"{price:,.2f}", diff,
                    )
                    last_price_log = now

                if abs(diff) >= PRICE_THRESHOLD:
                    arrow = "↑" if diff > 0 else "↓"
                    sign = "+" if diff > 0 else ""
                    symbol_safe = _escape_markdown(SYMBOL)
                    msg = (
                        f"{arrow}  *{symbol_safe}  ·  Price alert*\n\n"
                        f"💵  *${price:,.2f}*\n"
                        f"📊  Change: *{sign}${diff:,.2f}*\n\n"
                        f"🕒  {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M:%S')} UTC"
                    )
                    x_move_sign = "+" if diff > 0 else "−"
                    x_msg = (
                        f"{arrow} {SYMBOL} · BTC price alert\n\n"
                        f"💵 ${price:,.2f}\n"
                        f"📊 Change: {x_move_sign}${abs(diff):,.2f}\n"
                        f"🕒 {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M:%S')} UTC\n\n"
                        "Join our Telegram: https://t.me/bitcoin500alerts"
                    )
                    logger.info("[ALERT] Threshold crossed: %s %+.2f USD", SYMBOL, diff)
                    try:
                        chart = _create_chart(SYMBOL, price)
                    except Exception as error:
                        logger.warning("Chart generation failed; sending text only: %s", error)
                        chart = None
                    delivered = send_telegram_chart(msg, price, chart) if chart else False
                    if not delivered:
                        send_telegram(msg)
                    if chart:
                        send_x_chart_async(x_msg, chart)
                    elif X_POSTS_ENABLED:
                        logger.warning("[X] Alert cross-post skipped because the chart couldn't be created")
                    if BLOGGER_ENABLED:
                        blogger_title, blogger_content = _blogger_content(price, diff)
                        send_blogger_post_async(blogger_title, blogger_content)
                    reference_price = price

        except (websocket.WebSocketException, requests.RequestException, OSError, ValueError, KeyError) as e:
            logger.warning("[BINANCE STREAM ERROR] %s", e)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        if not _stop_event.is_set():
            logger.info("[BINANCE] Reconnecting in %.1f seconds", backoff)
            _stop_event.wait(backoff)
            backoff = min(30.0, backoff * 2.0)


def _shutdown(signum, frame):
    logger.info("[BOT] Shutting down (signal=%s)", signum)
    _stop_event.set()
    if _httpd_ref is not None:
        try:
            _httpd_ref.server_close()
        except Exception:
            pass


# ===== MAIN =====
if __name__ == "__main__":
    logger.info("=== APP BOOTING ===")

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    time.sleep(1)

    btc_loop()

    logger.info("=== APP EXITING ===")
