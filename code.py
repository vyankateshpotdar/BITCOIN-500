import asyncio
from binance import Client
from telegram import Bot

# === CONFIG ===
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHANNELS = ["@channel1", "@channel2"]  # Telegram channels
BINANCE_API_KEY = ""      # optional
BINANCE_SECRET_KEY = ""   # optional
PRICE_CHECK_INTERVAL = 30  # seconds
PRICE_CHANGE_THRESHOLD = 500  # USD
ALERT_IMAGE_PATH = "alert_image.png"  # Your static 16:9 image

# === INIT ===
bot = Bot(token=TELEGRAM_TOKEN)
client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)

start_price = None  # Reference price when bot starts

# === FUNCTIONS ===

def get_btc_price():
    """Fetch latest BTC price from Binance"""
    ticker = client.get_symbol_ticker(symbol="BTCUSDT")
    return float(ticker["price"])

async def send_alert(current_price, diff):
    """Send alert with static image and up/down arrow"""
    arrow = "🔺" if diff > 0 else "🔻"  # up or down arrow
    message = f"{arrow} *BTC Price Update!*\n\nCurrent Price: `${current_price:,.2f}`\nChange: `{diff:+,.2f}` USD"

    for chat_id in CHANNELS:
        try:
            with open(ALERT_IMAGE_PATH, "rb") as img:
                await bot.send_photo(chat_id=chat_id, photo=img, caption=message, parse_mode="Markdown")
            print(f"Alert sent to {chat_id}")
        except Exception as e:
            print(f"Failed to send alert to {chat_id}: {e}")

# === MAIN LOOP ===

async def main():
    global start_price
    start_price = get_btc_price()
    print(f"Bot started. Tracking from ${start_price:,.2f}")
    await send_alert(start_price, 0)  # initial alert, diff = 0

    while True:
        try:
            price = get_btc_price()
            diff = price - start_price
            if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                print(f"Price change detected: ${diff:,.2f}")
                await send_alert(price, diff)
                start_price = price  # reset reference price

            print(f"BTC Price: ${price:,.2f}")
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
