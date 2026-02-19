import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from binance import Client
import requests
import sys

# ===== CONFIG =====
TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"   # rotate your token
CHAT_ID = "@bitcoin500alerts"             # bot must be admin
PORT = 8000
CHECK_INTERVAL = 1
PRICE_THRESHOLD = 500   # ≈ ±500 USD

# ===== BINANCE =====
client = Client("", "")

# ===== FORCE LOG FLUSH =====
def log(*args):
    print(*args)
    sys.stdout.flush()

# ===== TELEGRAM SEND =====
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload, timeout=10)
    log("[TELEGRAM RESPONSE]", r.text)

# ===== HEALTH CHECK SERVER =====
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_health_server():
    log("[HEALTH] Starting health server on port", PORT)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

# ===== BTC LOOP =====
def btc_loop():
    log("[BOT] BTC loop starting")

    try:
        start_price = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
        log("[START PRICE]", start_price)
        send_telegram(f"BTC = `{start_price}`")
    except Exception as e:
        log("[BINANCE ERROR AT START]", e)
        return

    while True:
        try:
            price = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
            diff = price - start_price

            log("[PRICE]", price, "Δ", diff)

            if abs(diff) >= PRICE_THRESHOLD:
                arrow = "⬆️" if diff > 0 else "⬇️"
                sign = "+" if diff > 0 else ""

                msg = (
                    f"{arrow} BTC : ${price:,.2f}\n "
                    f"📊 Change: `{sign}{diff:,.2f} USD`"
                )

                send_telegram(msg)
                start_price = price

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log("[LOOP ERROR]", e)
            time.sleep(5)

# ===== MAIN =====
if __name__ == "__main__":
    log("=== APP BOOTING ===")

    threading.Thread(
        target=start_health_server,
        daemon=True
    ).start()

    time.sleep(2)  # allow health server to bind
    btc_loop()


