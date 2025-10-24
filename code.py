import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from binance import Client
from telegram import Bot

# === CONFIG ===
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
BINANCE_API_KEY = ""      # optional if only public price
BINANCE_SECRET_KEY = ""   # optional if only public price
PRICE_CHECK_INTERVAL = 30  # seconds
PRICE_CHANGE_THRESHOLD = 500  # USD

# === INIT ===
bot = Bot(token=TELEGRAM_TOKEN)
client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)

last_price = None

def create_price_image(current_price, change):
    """Generate image showing price and change"""
    img = Image.new("RGB", (600, 300), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("arial.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except:
        font_big = font_small = ImageFont.load_default()

    color = (0, 255, 0) if change > 0 else (255, 50, 50)
    sign = "+" if change > 0 else ""

    draw.text((50, 50), f"BTC/USDT Price Alert", font=font_small, fill=(200, 200, 200))
    draw.text((50, 120), f"${current_price:,.2f}", font=font_big, fill=color)
    draw.text((50, 200), f"Change: {sign}${change:,.2f}", font=font_small, fill=color)
    draw.text((50, 240), f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
              font=font_small, fill=(150, 150, 150))

    img_path = "btc_alert.png"
    img.save(img_path)
    return img_path


def get_btc_price():
    """Fetch latest BTC price from Binance"""
    ticker = client.get_symbol_ticker(symbol="BTCUSDT")
    return float(ticker["price"])


def send_alert(current_price, change):
    """Send image + text alert to Telegram"""
    image_path = create_price_image(current_price, change)
    message = f"💰 *BTC Price Alert!*\n\nCurrent Price: `${current_price:,.2f}`\nChange: `{change:+,.2f}` USD"
    bot.send_photo(chat_id=CHAT_ID, photo=open(image_path, "rb"), caption=message, parse_mode="Markdown")


def main():
    global last_price
    while True:
        try:
            price = get_btc_price()

            if last_price is not None:
                diff = price - last_price
                if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                    print(f"Change detected: ${diff:.2f}")
                    send_alert(price, diff)

            last_price = price
            print(f"[{datetime.now().strftime('%H:%M:%S')}] BTC Price: ${price:,.2f}")
            time.sleep(PRICE_CHECK_INTERVAL)

        except Exception as e:
            print("Error:", e)
            time.sleep(PRICE_CHECK_INTERVAL)


if __name__ == "__main__":
    main()
