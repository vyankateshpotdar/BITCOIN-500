import asyncio
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Bot

# ================= CONFIG =================

TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"

CHANNELS = ["@bitcoin500alerts"]

PRICE_CHECK_INTERVAL = 1  # seconds
PRICE_CHANGE_THRESHOLD = 500  # USD
ALERT_IMAGE_PATH = "alert_image.png"

# ================= INIT =================

bot = Bot(token=TELEGRAM_TOKEN)
start_price = None

# ================= KOYEB HEALTH SERVER =================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ================= FUNCTIONS =================

def get_btc_price():
    r = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"},
        timeout=10
    )
    return float(r.json()["price"])

async def send_alert(current_price, diff):
    arrow = "⬆" if diff > 0 else "⬇"
    message = (
        f"{arrow} *BTC Price Update!*\n\n"
        f"Current Price: `${current_price:,.2f}`\n"
        f"Change: `{diff:+,.2f}` USD"
    )

    for chat_id in CHANNELS:
        try:
            with open(ALERT_IMAGE_PATH, "rb") as img:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=img,
                    caption=message,
                    parse_mode="Markdown"
                )
            print(f"Alert sent to {chat_id}")
        except Exception as e:
            print(f"Telegram error:", e)

# ================= MAIN LOOP =================

async def main():
    global start_price

    start_price = get_btc_price()
    print(f"Bot started. Tracking from ${start_price:,.2f}")
    await send_alert(start_price, 0)

    while True:
        try:
            price = get_btc_price()
            diff = price - start_price

            if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                print(f"Price change detected: ${diff:,.2f}")
                await send_alert(price, diff)
                start_price = price

            await asyncio.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("Runtime error:", e)
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(main())
