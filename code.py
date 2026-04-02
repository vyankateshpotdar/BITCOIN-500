import os
import sys
import time
import signal
import threading
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from binance import Client

# ===== CONFIG (from environment) =====
# Required:
#   TELEGRAM_TOKEN
# Optional:
#   CHAT_ID (default: @bitcoin500alerts)
#   PORT (default: 8000)
#   CHECK_INTERVAL (default: 0.1)
#   PRICE_THRESHOLD (default: 500)
#   BINANCE_API_KEY / BINANCE_API_SECRET (optional for public endpoints)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "@bitcoin500alerts")
PORT = int(os.getenv("PORT", "8000"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "0.1"))
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

# ===== BINANCE =====
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ===== STOP CONTROL =====
_stop_event = threading.Event()

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
        r = requests.post(url, json=payload, timeout=10)
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
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if self.path == "/status":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"RUNNING")
            return

        self.send_error(404, "Not Found")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    # keep logs quiet
    def log_message(self, format, *args):
        return

def start_health_server() -> None:
    logger.info("[HEALTH] Starting health server on port %s", PORT)
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)

    # allow graceful shutdown via _stop_event
    def _serve():
        while not _stop_event.is_set():
            httpd.handle_request()

    _serve()

# ===== BTC LOOP =====
def btc_loop() -> None:
    logger.info("[BOT] Price loop starting (symbol=%s threshold=%s interval=%s)", SYMBOL, PRICE_THRESHOLD, CHECK_INTERVAL)

    # Initialize start price
    try:
        start_price = _get_price(SYMBOL)
        logger.info("[START PRICE] %s", start_price)
        send_telegram(f"{SYMBOL} = ` {start_price}`")
    except Exception as e:
        logger.exception("[BINANCE ERROR AT START] %s", e)
        return

    backoff = 1.0
    while not _stop_event.is_set():
        try:
            price = _get_price(SYMBOL)
            diff = price - start_price
            logger.info("[PRICE] %s Δ %s", price, diff)

            if abs(diff) >= PRICE_THRESHOLD:
                arrow = "↑" if diff > 0 else "↓"
                sign = "+" if diff > 0 else ""

                msg = (
                    f"*{arrow} {SYMBOL} = ${price:,.2f}*\n"
                    f"*Change = {sign}{diff:,.2f} USD*"
                    f"_Time: {datetime.utcnow().isoformat()}Z_"
                )

                send_telegram(msg)
                start_price = price

            backoff = 1.0
            _stop_event.wait(CHECK_INTERVAL)

        except Exception as e:
            logger.exception("[LOOP ERROR] %s", e)
            # simple exponential backoff, capped
            _stop_event.wait(min(30.0, backoff))
            backoff = min(30.0, backoff * 2.0)


def _shutdown(signum, frame):
    logger.info("[BOT] Shutting down (signal=%s)", signum)
    _stop_event.set()

# ===== MAIN =====
if __name__ == "__main__":
    logger.info("=== APP BOOTING ===")

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    threading.Thread(target=start_health_server, daemon=True).start()

    # allow health server to bind
    time.sleep(1)

    btc_loop()