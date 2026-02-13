import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from binance import Client
from telegram import Bot

# ===== FORCE LOGS =====
sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIG =====
TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"   # YOUR TOKEN
CHANNELS = ["@bitcoin500alerts"]

BINANCE_API_KEY = "G3dDgpY3WUrxJBzOsaWX0BsTg58E8iKeYzkdV0hC6"
BINANCE_SECRET_KEY = "HX00iwkZvewblwC4qGpFuJMYcLiKywENC7bkPElSDlLvtkLtTFNZH5oaWuOg0cgP"

PRICE_CHECK_INTERVAL = 1
PRICE_CHANGE_THRESHOLD = 500
ALERT_IMAGE_PATH = "alert_image.png"

PORT = 8000

# ===== INIT =====
bot = Bot(token=TELEGRAM_TOKEN)
client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)

start_price = None

# ===== HEALTH SERVER =====
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

# ===== FUNCTIONS =====
def get_btc_price():
    ticker = client.get_symbol_ticker(symbol="BTCUSDT")
    price = float(ticker["price"])
    print(f"[BINANCE] BTCUSDT = {price}")
    return price

def send_alert(current_price, diff):
    arrow = "⬆" if diff > 0 else "⬇"
    message = (
        f"{arrow} *BTC Price Update!*\n\n"
        f"Current Price: `${current_price:,.2f}`\n"
        f"Change: `{diff:+,.2f}` USD"
    )

    for chat_id in CHANNELS:
        try:
            with open(ALERT_IMAGE_PATH, "rb") as img:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=img,
                    caption=message,
                    parse_mode="Markdown"
                )
            print(f"[TELEGRAM] Sent alert to {chat_id}")
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

# ===== MAIN LOOP =====
async def main():
    global start_price

    start_price = get_btc_price()
    print(f"[STARTED] Tracking BTC from {start_price}")

    send_alert(start_price, 0)

    while True:
        try:
            price = get_btc_price()
            diff = price - start_price

            print(f"[PRICE] BTC={price} | Δ={diff}")

            if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                print("[ALERT] Threshold reached")
                send_alert(price, diff)
                start_price = price

            await asyncio.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR]", e)
            await asyncio.sleep(5)

# ===== ENTRY =====
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    asyncio.run(main())
