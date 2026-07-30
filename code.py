import os
import sys
import time
import signal
import threading
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from binance import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

# ===== CONFIG (from environment) =====
# Required:
#   TELEGRAM_TOKEN
# Optional:
#   CHAT_ID (default: @bitcoin500alerts)
#   PORT (default: 8000)
#   CHECK_INTERVAL (default: 2.0)   <- NOTE: default raised from 0.1s, see "Changes Made"
#   PRICE_THRESHOLD (default: 500)
#   BINANCE_API_KEY / BINANCE_API_SECRET (optional for public endpoints)
#   SYMBOL (default: BTCUSDT)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "@bitcoin500alerts")
PORT = int(os.getenv("PORT", "8000"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "2.0"))
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "500"))

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")

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

if CHECK_INTERVAL <= 0:
    logger.critical("CHECK_INTERVAL must be > 0, got %s. Exiting.", CHECK_INTERVAL)
    sys.exit(1)

if CHECK_INTERVAL < 1.0:
    logger.warning(
        "CHECK_INTERVAL=%s is very aggressive and may trigger Binance rate limits. "
        "Consider >= 1.0s.",
        CHECK_INTERVAL,
    )

if PRICE_THRESHOLD <= 0:
    logger.critical("PRICE_THRESHOLD must be > 0, got %s. Exiting.", PRICE_THRESHOLD)
    sys.exit(1)

# ===== BINANCE =====
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ===== HTTP SESSION (connection reuse) =====
_http_session = requests.Session()

# ===== STOP CONTROL =====
_stop_event = threading.Event()
_httpd_ref: HTTPServer | None = None  # populated once the health server starts


def _escape_markdown(text: str) -> str:
    """Escape characters that break Telegram legacy Markdown parsing."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram(text: str) -> None:
    """Send a Telegram message to the configured chat."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN is not set; skipping Telegram send")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        r = _http_session.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Telegram send failed: status=%s body=%s", r.status_code, r.text)
        else:
            logger.info("Telegram send ok")
    except requests.RequestException as e:
        logger.exception("Telegram request error: %s", e)


def _get_price(symbol: str) -> float:
    """Fetch the latest price from Binance."""
    data = client.get_symbol_ticker(symbol=symbol)
    return float(data["price"])


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

    # keep logs quiet
    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    global _httpd_ref
    logger.info("[HEALTH] Starting health server on port %s", PORT)
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.timeout = 1.0  # unblocks handle_request() periodically so _stop_event is checked
    _httpd_ref = httpd

    while not _stop_event.is_set():
        httpd.handle_request()  # returns after `timeout` even with no request

    httpd.server_close()
    logger.info("[HEALTH] Health server stopped")


# ===== BTC LOOP =====
def _get_price_with_retry(symbol: str, max_attempts: int | None = None) -> float:
    """Fetch price, retrying with exponential backoff instead of crashing on
    a transient failure at startup."""
    attempt = 0
    backoff = 1.0
    while not _stop_event.is_set():
        try:
            return _get_price(symbol)
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error("[BINANCE API ERROR] %s", e)
        except Exception as e:
            logger.exception("[BINANCE ERROR] %s", e)

        attempt += 1
        if max_attempts is not None and attempt >= max_attempts:
            raise RuntimeError(f"Failed to fetch price after {attempt} attempts")

        _stop_event.wait(min(30.0, backoff))
        backoff = min(30.0, backoff * 2.0)

    raise RuntimeError("Stopped during startup price fetch")


def btc_loop() -> None:
    logger.info(
        "[BOT] Price loop starting (symbol=%s threshold=%s interval=%s)",
        SYMBOL, PRICE_THRESHOLD, CHECK_INTERVAL,
    )

    # Initialize start price with retry instead of a hard exit on first failure
    try:
        start_price = _get_price_with_retry(SYMBOL)
    except RuntimeError as e:
        logger.critical("[STARTUP FAILURE] %s", e)
        return

    logger.info("[START PRICE] %s", start_price)
    send_telegram(f"{SYMBOL} = `{start_price}`")

    backoff = 1.0
    while not _stop_event.is_set():
        try:
            price = _get_price(SYMBOL)
            diff = price - start_price
            logger.info("[PRICE] %s Δ %s", price, diff)

            if abs(diff) >= PRICE_THRESHOLD:
                arrow = "↑" if diff > 0 else "↓"
                sign = "+" if diff > 0 else ""
                symbol_safe = _escape_markdown(SYMBOL)

                msg = (
                    f"*{arrow} {symbol_safe} = ${price:,.2f}*\n"
                    f"*Change = {sign}{diff:,.2f} USD*\n"
                    f"_Time: {datetime.now(timezone.utc).isoformat()}Z_"
                )

                send_telegram(msg)
                start_price = price

            backoff = 1.0
            _stop_event.wait(CHECK_INTERVAL)

        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error("[BINANCE API ERROR] %s", e)
            _stop_event.wait(min(30.0, backoff))
            backoff = min(30.0, backoff * 2.0)
        except Exception as e:
            logger.exception("[LOOP ERROR] %s", e)
            _stop_event.wait(min(30.0, backoff))
            backoff = min(30.0, backoff * 2.0)


def _shutdown(signum, frame):
    logger.info("[BOT] Shutting down (signal=%s)", signum)
    _stop_event.set()
    if _httpd_ref is not None:
        # Unblock a pending accept() promptly rather than waiting for the
        # 1s socket timeout on the health server loop.
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

    # allow health server to bind
    time.sleep(1)

    btc_loop()

    logger.info("=== APP EXITING ===")
