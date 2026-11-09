import os
import sys
import json
import html
import time
import signal
import threading
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from io import BytesIO
from datetime import datetime, timezone, timedelta
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
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
DROPBOX_CREDENTIALS_READY = all((DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN))
DROPBOX_CLEANUP_THRESHOLD_BYTES = 1_800_000_000
PERIODIC_REPORTS_ENABLED = os.getenv("PERIODIC_REPORTS_ENABLED", "true").lower() in ("1", "true", "yes")

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
    if not DROPBOX_CREDENTIALS_READY:
        logger.warning("[BLOGGER] Dropbox image credentials are incomplete; posts will be text-only")

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


def _publish_blogger_content(title: str, content: str, chart: bytes = None, labels=None) -> bool:
    """Publish supplied HTML to Blogger, optionally hosting its chart on Dropbox."""
    if not BLOGGER_ENABLED:
        return False
    if not BLOGGER_CREDENTIALS_READY:
        logger.warning("[BLOGGER] Skipping post because Blogger credentials are incomplete")
        return False

    dropbox_path = None
    dropbox_access_token = None
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

        chart_url = None
        if chart and DROPBOX_CREDENTIALS_READY:
            try:
                dropbox_access_token = _get_dropbox_access_token()
                uploaded = _upload_blogger_chart(dropbox_access_token, chart)
                if uploaded:
                    chart_url, dropbox_path = uploaded
            except (requests.RequestException, ValueError) as error:
                logger.warning("[BLOGGER] Image hosting failed; publishing text only: %s", error)
        html_content = content
        if chart_url:
            image_html = (
                f'<figure><img src="{html.escape(chart_url, quote=True)}" '
                'alt="BTCUSDT Binance Spot candlestick and volume chart for this report period" '
                'style="display:block;max-width:100%;height:auto;margin:16px auto;" />'
                '<figcaption>BTCUSDT Binance Spot candlestick chart with BTC volume bars; UTC.</figcaption></figure>'
            )
            html_content = html_content.replace("{{CHART}}", image_html)
        else:
            html_content = html_content.replace("{{CHART}}", "")

        response = _http_session.post(
            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
            params={"isDraft": "false"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "kind": "blogger#post",
                "title": title,
                "content": html_content,
                "labels": labels or ["Bitcoin", "BTCUSDT", "Bitcoin Price", "Binance Spot", "Crypto Market Update"],
            },
            timeout=20,
        )
        if response.status_code != 200:
            logger.warning("[BLOGGER] Post failed: HTTP %s body=%s", response.status_code, response.text[:500])
            if dropbox_path and dropbox_access_token:
                _delete_blogger_chart(dropbox_access_token, dropbox_path)
            return False
        post = response.json()
        logger.info("[BLOGGER] Post published (post_id=%s url=%s)", post.get("id"), post.get("url"))
        return True
    except (requests.RequestException, ValueError) as error:
        if dropbox_path and dropbox_access_token:
            _delete_blogger_chart(dropbox_access_token, dropbox_path)
        logger.warning("[BLOGGER] Post failed: %s", error)
        return False


def _send_blogger_post(price: float, change: float = None, chart: bytes = None) -> bool:
    """Publish a price update to the configured Blogger blog."""
    title, content = _blogger_content(price, change)
    return _publish_blogger_content(title, content, chart)


def send_blogger_post_async(price: float, change: float = None, chart: bytes = None) -> None:
    """Publish off-thread so Google API latency cannot interrupt price monitoring."""
    if not BLOGGER_ENABLED:
        return
    worker = threading.Thread(
        target=_send_blogger_post,
        args=(price, change, chart),
        name="blogger-crosspost",
        daemon=True,
    )
    worker.start()


def send_blogger_report_async(title: str, content: str, chart: bytes) -> None:
    if not BLOGGER_ENABLED:
        return
    worker = threading.Thread(
        target=_publish_blogger_content,
        args=(title, content, chart, ["Bitcoin", "BTCUSDT", "Bitcoin Report", "Binance Spot", "Crypto Market Summary"]),
        name="blogger-periodic-report",
        daemon=True,
    )
    worker.start()


def _get_dropbox_access_token() -> str:
    """Exchange the stored Dropbox refresh token for a short-lived access token."""
    response = _http_session.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": DROPBOX_REFRESH_TOKEN,
            "client_id": DROPBOX_APP_KEY,
            "client_secret": DROPBOX_APP_SECRET,
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise requests.HTTPError(f"Dropbox token refresh failed: HTTP {response.status_code}")
    access_token = response.json().get("access_token")
    if not access_token:
        raise ValueError("Dropbox token refresh returned no access token")
    return access_token


def _upload_blogger_chart(access_token: str, chart: bytes):
    """Upload a chart to the Dropbox app folder and return a public render link."""
    if not _make_dropbox_room(access_token, len(chart)):
        logger.warning("[BLOGGER] Skipping chart upload; Dropbox usage is above the limit and no old charts can be removed")
        return None

    path = f"/bitcoin500-btcusdt-{int(time.time() * 1000)}.png"
    try:
        upload = _http_session.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({
                    "path": path,
                    "mode": "add",
                    "autorename": True,
                    "mute": True,
                    "strict_conflict": False,
                }),
                "Content-Type": "application/octet-stream",
            },
            data=chart,
            timeout=30,
        )
    except requests.RequestException:
        _delete_blogger_chart(access_token, path)
        raise
    if upload.status_code not in (200, 201):
        logger.warning("[BLOGGER] Chart upload to Dropbox failed: HTTP %s", upload.status_code)
        _delete_blogger_chart(access_token, path)
        return None

    try:
        result = upload.json()
    except ValueError:
        _delete_blogger_chart(access_token, path)
        raise
    path = result.get("path_lower", path)
    try:
        shared = _http_session.post(
            "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "path": path,
                "settings": {
                    "audience": {".tag": "public"},
                    "access": {".tag": "viewer"},
                    "requested_visibility": {".tag": "public"},
                },
            },
            timeout=20,
        )
    except requests.RequestException:
        _delete_blogger_chart(access_token, path)
        raise
    if shared.status_code not in (200, 201):
        logger.warning("[BLOGGER] Could not create a Dropbox view link: HTTP %s", shared.status_code)
        _delete_blogger_chart(access_token, path)
        return None

    try:
        link = shared.json().get("url")
    except ValueError:
        _delete_blogger_chart(access_token, path)
        raise
    if not link:
        logger.warning("[BLOGGER] Dropbox returned no shared link")
        _delete_blogger_chart(access_token, path)
        return None
    parts = urlsplit(link)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["raw"] = "1"
    query.pop("dl", None)
    render_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return render_url, path


def _make_dropbox_room(access_token: str, incoming_bytes: int) -> bool:
    """Keep total Dropbox use below 1.8 GB by deleting oldest bot charts first."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    usage_response = _http_session.post(
        "https://api.dropboxapi.com/2/users/get_space_usage",
        headers=headers,
        json={},
        timeout=15,
    )
    if usage_response.status_code != 200:
        logger.warning("[BLOGGER] Could not read Dropbox storage use: HTTP %s", usage_response.status_code)
        return False
    used_bytes = int(usage_response.json().get("used", 0))
    if used_bytes + incoming_bytes <= DROPBOX_CLEANUP_THRESHOLD_BYTES:
        return True

    first_page = _http_session.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers=headers,
        json={"path": "", "recursive": False, "limit": 2000},
        timeout=20,
    )
    if first_page.status_code != 200:
        logger.warning("[BLOGGER] Could not list Dropbox charts for cleanup: HTTP %s", first_page.status_code)
        return False

    listing = first_page.json()
    entries = list(listing.get("entries", []))
    while listing.get("has_more"):
        page = _http_session.post(
            "https://api.dropboxapi.com/2/files/list_folder/continue",
            headers=headers,
            json={"cursor": listing["cursor"]},
            timeout=20,
        )
        if page.status_code != 200:
            logger.warning("[BLOGGER] Could not continue Dropbox chart listing: HTTP %s", page.status_code)
            return False
        listing = page.json()
        entries.extend(listing.get("entries", []))

    chart_files = [
        entry for entry in entries
        if entry.get(".tag") == "file" and entry.get("name", "").startswith("bitcoin500-btcusdt-")
    ]
    chart_files.sort(key=lambda entry: entry.get("server_modified", ""))
    for file in chart_files:
        if used_bytes + incoming_bytes <= DROPBOX_CLEANUP_THRESHOLD_BYTES:
            break
        deletion = _http_session.post(
            "https://api.dropboxapi.com/2/files/delete_v2",
            headers=headers,
            json={"path": file.get("id") or file.get("path_lower")},
            timeout=15,
        )
        if deletion.status_code not in (200, 201):
            logger.warning("[BLOGGER] Could not delete oldest chart %s: HTTP %s", file.get("name"), deletion.status_code)
            continue
        used_bytes = max(0, used_bytes - int(file.get("size", 0)))
        logger.info(
            "[BLOGGER] Deleted oldest chart %s to keep Dropbox below 1.8 GB",
            file.get("name"),
        )

    return used_bytes + incoming_bytes <= DROPBOX_CLEANUP_THRESHOLD_BYTES


def _delete_blogger_chart(access_token: str, path: str) -> None:
    """Delete a Dropbox chart only when it failed to become part of a Blogger post."""
    try:
        response = _http_session.post(
            "https://api.dropboxapi.com/2/files/delete_v2",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"path": path},
            timeout=15,
        )
        if response.status_code not in (200, 201):
            logger.warning("[BLOGGER] Could not clean up unused Dropbox chart: HTTP %s", response.status_code)
    except requests.RequestException as error:
        logger.warning("[BLOGGER] Could not clean up unused Dropbox chart: %s", error)


def _blogger_content(price: float, change: float = None, chart_url: str = None):
    """Build a useful, factual, search-friendly BTCUSDT price post."""
    updated = datetime.now(timezone.utc)
    timestamp = updated.strftime("%d %b %Y, %H:%M:%S UTC")
    safe_symbol = html.escape(SYMBOL)
    safe_time = html.escape(updated.isoformat(timespec="seconds"))
    title = f"{safe_symbol} Bitcoin Price: ${price:,.2f} | BITCOIN 500"
    direction = "" if change is None else ("Up" if change > 0 else "Down")
    change_html = (
        "" if change is None else
        f"<p><strong>Price move:</strong> BTCUSDT moved {direction.lower()} ${abs(change):,.2f} "
        "from BITCOIN 500's previous alert reference. This is a price change, not a trading signal.</p>"
    )
    image_html = "{{CHART}}"
    if chart_url:
        safe_chart_url = html.escape(chart_url, quote=True)
        alt = html.escape(
            f"BTCUSDT Bitcoin price chart with 15-minute Binance Spot candles and volume, "
            f"covering the last 12 hours. Latest price ${price:,.2f}. BITCOIN 500.",
            quote=True,
        )
        image_html = (
            f'<figure><img src="{safe_chart_url}" alt="{alt}" '
            'style="display:block;max-width:100%;height:auto;margin:16px auto;" />'
            '<figcaption>BTCUSDT 15-minute candlestick chart with volume; last 12 hours, UTC.</figcaption></figure>'
        )
    content = (
        f"<h2>Bitcoin (BTCUSDT) price update: ${price:,.2f}</h2>"
        f"<p>The latest Binance Spot BTCUSDT price snapshot is <strong>${price:,.2f} USDT per BTC</strong>. "
        "BTCUSDT is the Bitcoin-to-Tether (USDT) trading pair. The chart below shows 15-minute "
        "candles and trading volume for the past 12 hours. Each candle summarizes that period's open, "
        "high, low, and close; volume bars show BTC traded during each candle.</p>"
        f"{image_html}"
        f"{change_html}"
        f"<p><strong>Updated:</strong> <time datetime=\"{safe_time}\">{timestamp}</time></p>"
        f"<h3>About BITCOIN 500 BTC price alerts</h3>"
        f"<p>BITCOIN 500 tracks the {safe_symbol} market price and shares threshold-based Bitcoin price "
        f"updates when price movement reaches the configured ${PRICE_THRESHOLD:,.0f} USD alert threshold. "
        "These updates provide market context for readers who want to follow BTC price changes without "
        "watching charts continuously.</p>"
        "<p><a href=\"https://t.me/bitcoin500alerts\">Follow BITCOIN 500 on Telegram</a> for BTCUSDT price alerts.</p>"
        "<p><em>Market information only. Not financial advice or a trading recommendation.</em></p>"
    )
    return title, content


def _get_chart_candles(symbol: str, limit: int = 48, interval: str = "15m", start_ms: int = None, end_ms: int = None):
    """Fetch Binance candles, optionally bounded to a completed report period."""
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
    if start_ms is not None:
        params["startTime"] = start_ms
    if end_ms is not None:
        params["endTime"] = end_ms
    response = _http_session.get(
        url,
        params=params,
        timeout=10,
    )
    if response.status_code != 200:
        raise BinancePublicAPIError(f"Klines HTTP {response.status_code}: {response.text[:500]}")
    candles = response.json()
    if not isinstance(candles, list) or not candles:
        raise BinancePublicAPIError(f"Unexpected kline response: {candles}")
    return candles


def _create_chart(symbol: str, current_price: float, interval: str = "15m", limit: int = 48,
                  start_ms: int = None, end_ms: int = None, period_label: str = "LAST 12 HOURS",
                  price_label: str = "LIVE PRICE", candles_override=None) -> bytes:
    """Render a clean dark candlestick snapshot and return PNG bytes."""
    candles = candles_override or _get_chart_candles(symbol, limit, interval, start_ms, end_ms)
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
    date_format = "%d %b" if len(candles) > 48 else "%H:%M"
    volume_ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format, tz=timezone.utc))
    interval_label = {"15m": "15 MIN", "1h": "1 HOUR", "4h": "4 HOUR"}.get(interval, interval.upper())
    volume_ax.set_xlabel(f"UTC  ·  {interval_label} CANDLES  ·  {period_label}", color="#91a0ad", fontsize=8, labelpad=8)
    fig.suptitle(f"{symbol}  ·  Binance Spot", x=0.08, ha="left", color="#f2f5f7", fontsize=14, fontweight="semibold")
    price_ax.set_title(f"{price_label}   ${current_price:,.2f}", loc="left", color="#65b9ff", fontsize=10, pad=10)
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


REPORT_TYPES = {
    "daily": {"interval": "15m", "limit": 96, "minute": 5, "window": 15},
    "weekly": {"interval": "1h", "limit": 168, "minute": 10, "window": 20},
    "monthly": {"interval": "4h", "limit": 200, "minute": 15, "window": 30},
}
_published_report_keys = set()


def _report_period(report_type: str, now: datetime):
    """Return the completed UTC period's key, bounds, and display label."""
    if report_type == "daily":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        label = start.strftime("%d %b %Y")
    elif report_type == "weekly":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
        label = f"{start:%d %b} – {(end - timedelta(seconds=1)):%d %b %Y}"
    else:
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month_last = end - timedelta(days=1)
        start = previous_month_last.replace(day=1)
        label = start.strftime("%B %Y")
    key = f"{report_type}:{start.strftime('%Y-%m-%d')}"
    return key, start, end, label


def _build_periodic_report(report_type: str, now: datetime) -> None:
    """Build and deliver a completed daily, weekly, or monthly market report."""
    settings = REPORT_TYPES[report_type]
    key, start, end, label = _report_period(report_type, now)
    try:
        candles = _get_chart_candles(
            SYMBOL,
            limit=settings["limit"],
            interval=settings["interval"],
            start_ms=int(start.timestamp() * 1000),
            end_ms=int(end.timestamp() * 1000) - 1,
        )
        if not candles:
            raise BinancePublicAPIError("No candles returned for report period")
        opened = float(candles[0][1])
        high = max(float(candle[2]) for candle in candles)
        low = min(float(candle[3]) for candle in candles)
        closed = float(candles[-1][4])
        btc_volume = sum(float(candle[5]) for candle in candles)
        quote_volume = sum(float(candle[7]) for candle in candles)
        move = closed - opened
        move_pct = (move / opened * 100) if opened else 0
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000) - 1
        chart = _create_chart(
            SYMBOL, closed, interval=settings["interval"], limit=settings["limit"],
            start_ms=start_ms, end_ms=end_ms, period_label=label.upper(),
            price_label="PERIOD CLOSE", candles_override=candles,
        )
        direction = "▲" if move >= 0 else "▼"
        signed_move = f"+${move:,.2f}" if move >= 0 else f"−${abs(move):,.2f}"
        period_title = f"{report_type.title()} BTCUSDT Market Report — {label}"
        telegram_caption = (
            f"₿  *BITCOIN 500 · {report_type.upper()} REPORT*\n"
            f"*BTCUSDT · Binance Spot*\n"
            f"🗓  {label} (UTC)\n\n"
            f"{direction}  Open: *${opened:,.2f}*  →  Close: *${closed:,.2f}*\n"
            f"📈  High: *${high:,.2f}*\n"
            f"📉  Low: *${low:,.2f}*\n"
            f"↕️  Net move: *{signed_move} ({move_pct:+.2f}%)*\n"
            f"📊  Volume: *{btc_volume:,.4f} BTC* · *${quote_volume:,.0f} USDT*\n"
            f"🕯  {len(candles)} × {settings['interval']} candles\n\n"
            "Market summary only · Not financial advice.\n"
            "Follow @bitcoin500alerts for threshold-based BTC updates."
        )
        telegram_delivered = send_telegram_chart(telegram_caption, closed, chart)
        if not telegram_delivered:
            telegram_delivered = send_telegram(telegram_caption)

        safe_label = html.escape(label)
        safe_symbol = html.escape(SYMBOL)
        safe_period = html.escape(report_type)
        safe_start = html.escape(start.strftime("%Y-%m-%d %H:%M UTC"))
        safe_end = html.escape(end.strftime("%Y-%m-%d %H:%M UTC"))
        safe_chart_interval = html.escape(settings["interval"])
        blogger_content = (
            f"<h2>{safe_symbol} {safe_period.title()} Bitcoin Market Summary: {safe_label}</h2>"
            f"<p>This {safe_period} BTCUSDT report summarizes Binance Spot market activity from "
            f"<time>{safe_start}</time> through <time>{safe_end}</time>. It includes the period's "
            f"opening and closing price, high, low, percentage change, and aggregated trading volume.</p>"
            "{{CHART}}"
            "<h3>BTCUSDT price and volume details</h3><ul>"
            f"<li><strong>Open:</strong> ${opened:,.2f} USDT</li>"
            f"<li><strong>High:</strong> ${high:,.2f} USDT</li>"
            f"<li><strong>Low:</strong> ${low:,.2f} USDT</li>"
            f"<li><strong>Close:</strong> ${closed:,.2f} USDT</li>"
            f"<li><strong>Net change:</strong> {signed_move} ({move_pct:+.2f}%)</li>"
            f"<li><strong>BTC volume:</strong> {btc_volume:,.4f} BTC</li>"
            f"<li><strong>Quote volume:</strong> ${quote_volume:,.2f} USDT</li>"
            f"<li><strong>Chart resolution:</strong> {len(candles)} {safe_chart_interval} candles</li></ul>"
            f"<p>BTCUSDT is the Bitcoin-to-Tether market pair. The chart shows Binance Spot "
            f"{safe_chart_interval} candlesticks and traded BTC volume for {safe_label}; all times are UTC.</p>"
            "<p><a href=\"https://t.me/bitcoin500alerts\">Follow BITCOIN 500 on Telegram</a> "
            "for threshold-based Bitcoin price updates and chart snapshots.</p>"
            "<p><em>Market information only. Not financial advice or a trading recommendation.</em></p>"
        )
        blogger_title = f"{period_title} | Bitcoin Price, Range & Volume"
        send_blogger_report_async(blogger_title, blogger_content, chart)
        logger.info(
            "[REPORT] %s report processed for %s (telegram_delivered=%s blogger_enabled=%s)",
            report_type.upper(), label, telegram_delivered, BLOGGER_ENABLED,
        )
    except (BinancePublicAPIError, requests.RequestException, ValueError, IndexError) as error:
        logger.exception("[REPORT] Could not build %s report for %s: %s", report_type, label, error)


def report_scheduler() -> None:
    """Publish the previous completed UTC day, week, and month on schedule."""
    if not PERIODIC_REPORTS_ENABLED:
        logger.info("[REPORT] Scheduled reports are disabled")
        return
    logger.info("[REPORT] UTC schedule enabled: daily 00:05, weekly Mon 00:10, monthly day 1 at 00:15")
    while not _stop_event.is_set():
        now = datetime.now(timezone.utc)
        for report_type, settings in REPORT_TYPES.items():
            minute = settings["minute"]
            if now.hour == 0 and minute <= now.minute < minute + settings["window"]:
                if report_type == "weekly" and now.weekday() != 0:
                    continue
                if report_type == "monthly" and now.day != 1:
                    continue
                key, _, _, label = _report_period(report_type, now)
                if key not in _published_report_keys:
                    _published_report_keys.add(key)
                    threading.Thread(
                        target=_build_periodic_report,
                        args=(report_type, now),
                        name=f"{report_type}-report",
                        daemon=True,
                    ).start()
                    logger.info("[REPORT] Queued %s report for %s", report_type, label)
        _stop_event.wait(20)


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
                        send_blogger_post_async(price, chart=chart)
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
                        send_blogger_post_async(price, diff, chart)
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

    reports_thread = threading.Thread(target=report_scheduler, name="report-scheduler", daemon=True)
    reports_thread.start()

    time.sleep(1)

    btc_loop()

    logger.info("=== APP EXITING ===")
