import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from binance import Client
import requests

# ===== CONFIG =====
TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"
CHAT_IDS = ["@bitcoin500alerts"]   # channel must be admin-added
PORT = 8000
CHECK_INTERVAL = 5
PRICE_THRESHOLD = 500

# ===== BINANCE =====
client = Client("", "")
start_price = None

# ===== TELEGRAM SEND =====
def send_telegram(msg):
    for chat in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat,
            "text": msg,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, json=payload, timeout=10)
        print("[TELEGRAM]", r.text)

# ===== HEALTH CHECK =====
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def health_server():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

# ===== PRICE LOOP =====
def price_loop():
    global start_price
    start_price = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
    print("[START]", start_price)

    while True:
        try:
            price = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
            diff = price - start_price
            print("[PRICE]", price, diff)

            if abs(diff) >= PRICE_THRESHOLD:
                msg = f"🚨 *BTC ALERT*\nPrice: `{price}`\nChange: `{diff:+}`"
                send_telegram(msg)
                start_price = price

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR]", e)
            time.sleep(5)

# ===== START =====
if __name__ == "__main__":
    threading.Thread(target=health_server, daemon=True).start()
    price_loop()
