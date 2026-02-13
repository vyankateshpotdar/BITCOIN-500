import asyncio
import sys
from binance import Client
from telegram import Bot

# ===== FORCE LOGS TO APPEAR ON KOYEB =====
sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIG =====
TELEGRAM_TOKEN = "8349405657:AAH8UDEIe5mRs1um9ejFXTOMKTqwdo1I6oA"  # YOUR BOT TOKEN
CHANNELS = ["@bitcoin500alerts"]

BINANCE_API_KEY = ""        # optional
BINANCE_SECRET_KEY = "HX00kLtTFNZH5oaWuOg0cgP"  # optional

PRICE_CHECK_INTERVAL = 1        # seconds
PRICE_CHANGE_THRESHOLD = 500    # USD
ALERT_IMAGE_PATH = "alert_image.png"

# ===== INIT =====
bot = Bot(token=TELEGRAM_TOKEN)
client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)

start_price = None

# ===== FUNCTIONS =====
def get_btc_price():
    ticker = client.get_symbol_ticker(symbol="BTCUSDT")
    price = float(ticker["price"])
    print(f"[BINANCE] BTCUSDT = {price}", flush=True)
    return price

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
            print(f"[TELEGRAM] Sent alert to {chat_id}", flush=True)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}", flush=True)

# ===== MAIN LOOP =====
async def main():
    global start_price

    start_price = get_btc_price()
    print(f"[STARTED] Tracking BTC from {start_price}", flush=True)

    await send_alert(start_price, 0)

    while True:
        try:
            price = get_btc_price()
            diff = price - start_price

            print(f"[PRICE] BTC={price} | Δ={diff}", flush=True)

            if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                print(f"[ALERT] Threshold hit at {price}", flush=True)
                await send_alert(price, diff)
                start_price = price

            await asyncio.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR]", e, flush=True)
            await asyncio.sleep(5)

# ===== ENTRY =====
if __name__ == "__main__":
    asyncio.run(main())
