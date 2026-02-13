import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from binance import Client
from telegram import Bot

# ================= CONFIG =================
TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"
CHANNELS = ["@bitcoin500alerts"]

BINANCE_API_KEY = "G3dDgpY3WUrxJBzOsaWX0BsTg58E8iKeYzkdV0hC6"
BINANCE_SECRET_KEY = "HX00iwkZvewblwC4qGpFuJMYcLiKywENC7bkPElSDlLvtkLtTFNZH5oaWuOg0cgP"

PORT = 8000
PRICE_CHECK_INTERVAL = 5
PRICE_CHANGE_THRESHOLD = 500

# ================= INIT =================
bot = Bot(token=TELEGRAM_TOKEN)
client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
start_price = None

# ================= HEALTH SERVER =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[HEALTH] Server running on port {PORT}")
    server.serve_forever()

# ================= BOT LOGIC =================
def get_btc_price():
    price = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
    print(f"[BINANCE] BTCUSDT = {price}")
    return price

def send_alert_sync(price, diff):
    arrow = "⬆️" if diff >= 0 else "⬇️"
    msg = (
        f"{arrow} *BTC Price Alert*\n\n"
        f"Price: `${price:,.2f}`\n"
        f"Change: `{diff:+,.2f}` USD"
    )

    for ch in CHANNELS:
        try:
            bot.send_message(chat_id=ch, text=msg, parse_mode="Markdown")
            print(f"[TELEGRAM] Alert sent to {ch}")
        except Exception as e:
            print("[TELEGRAM ERROR]", e)

async def main():
    global start_price
    start_price = get_btc_price()
    print(f"[STARTED] Tracking BTC from {start_price}")

    while True:
        try:
            price = get_btc_price()
            diff = price - start_price
            print(f"[PRICE] BTC={price} | Δ={diff}")

            if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                send_alert_sync(price, diff)
                start_price = price

            await asyncio.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR]", e)
            await asyncio.sleep(5)

# ================= START =================
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    asyncio.run(main())
