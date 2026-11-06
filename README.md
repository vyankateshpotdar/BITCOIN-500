# ₿ITCOIN-500
<img width="1920" height="1080" alt="575270147-d27f95ba-1254-45f9-8b1e-0725fc618ac0" src="https://github.com/user-attachments/assets/3ed82335-e714-4f21-8152-ec0abc7aa7ab" />

![Bitcoin](https://img.shields.io/badge/Bitcoin-Project-orange?logo=bitcoin)
![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker)
![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)

A real-time Bitcoin price alert bot that watches the market 24/7 and sends instant **Telegram notifications** whenever BTC moves by **±$500 or more**. Built with Python, Binance API, and Docker.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
  - [Local Setup](#local-setup)
  - [Docker Setup](#docker-setup)
  - [Koyeb Hosting](#koyeb-hosting)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**BITCOIN-500** monitors the Bitcoin (BTC/USDT) price on Binance and fires a Telegram alert the moment the price shifts by $500 or more from the last recorded checkpoint. This keeps you informed about significant market movements without drowning you in noise from minor fluctuations.

---

## Features

- **Real-Time Price Monitoring** — Receives Binance trade updates over a persistent WebSocket connection.
- **Smart Threshold Alerts** — Only triggers when the price moves ±$500, reducing alert fatigue.
- **Telegram Notifications** — Sends formatted alerts directly to your Telegram chat or channel.
- **Chart Snapshots** — Includes a recent 15-minute candlestick chart with startup and threshold alerts.
- **Health Check Server** — Built-in HTTP server with `/health` and `/status` endpoints for uptime monitoring.
- **Docker Ready** — Fully containerized for easy deployment anywhere.
- **Configurable via Environment Variables** — No code changes needed to customize behavior.
- **Graceful Shutdown** — Handles `SIGINT` / `SIGTERM` signals cleanly.
- **Exponential Backoff** — Automatically retries with increasing delays on API errors.

---

## How It Works

1. On startup, the bot receives the latest BTC trade from Binance and stores it as the **reference price**.
2. A Telegram message is sent with the latest price and UTC timestamp as soon as the bot starts.
3. The bot then listens to Binance's live trade stream and reconnects automatically after connection errors.
4. When the price differs from the reference by **$500 or more**, a Telegram alert is sent showing the new price, the change amount, and direction (↑ or ↓).
5. The reference price is updated to the new price, and monitoring continues.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.8+ |
| Price Data | Binance API (`python-binance`) |
| Notifications | Telegram Bot API (`python-telegram-bot`) |
| HTTP Requests | `requests` |
| Containerization | Docker |
| CI/CD | GitHub Actions |

---

## Prerequisites

- Python 3.8+
- A [Binance account](https://www.binance.com/) (API key optional for public price endpoints)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)
- Docker (optional, for containerized deployment)

---

## Setup & Installation

### Local Setup

1. **Clone the repository**

```bash
git clone https://github.com/vyankateshpotdar/BITCOIN-500.git
cd BITCOIN-500
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Set environment variables**

```bash
export TELEGRAM_TOKEN="your_telegram_bot_token"
export CHAT_ID="@your_channel_or_chat_id"
```

4. **Run the bot**

```bash
python code.py
```

---

### Docker Setup

1. **Build the image**

```bash
docker build -t bitcoin-500 .
```

2. **Run the container**

```bash
docker run -d \
  -e TELEGRAM_TOKEN="your_telegram_bot_token" \
  -e CHAT_ID="@your_channel_or_chat_id" \
  -p 8000:8000 \
  bitcoin-500
```

### Koyeb Hosting

1. Push the latest project files to GitHub, then create a service from that repository in Koyeb.
2. Choose **Dockerfile** as the build method and keep the Dockerfile path as `Dockerfile`.
3. For continuous 24/7 alerts, select a **Worker** service and a paid instance. Koyeb's Free instance does not support workers and free web services can scale to zero when they receive no traffic.
4. Add `TELEGRAM_TOKEN` as a Koyeb Secret and reference it as the service environment variable. Add `CHAT_ID` with the channel ID as a regular environment variable (or secret).
5. Leave the Docker command at its default; the image runs `python code.py` and reconnects to Binance automatically.

The bot must already be an administrator in the Telegram channel with permission to post. If you choose a **Web Service** instead of a Worker, expose port `8000` as HTTP and use `/health` as the health-check path. This is suitable for a test deployment, but a Free instance can sleep after an hour without inbound traffic, so it is not reliable for uninterrupted alerts.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_TOKEN` | ✅ Yes | — | Your Telegram bot token from BotFather |
| `CHAT_ID` | No | `-1003175403499` | Telegram chat ID or channel username |
| `PORT` | No | `8000` | Port for the health check HTTP server |
| `PRICE_THRESHOLD` | No | `500` | USD threshold to trigger an alert |
| `PRICE_LOG_INTERVAL` | No | `10` | Seconds between live price log entries |
| `SYMBOL` | No | `BTCUSDT` | Binance trading pair symbol |
| `BINANCE_API_KEY` | No | — | Binance API key (optional for public data) |
| `BINANCE_API_SECRET` | No | — | Binance API secret |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, etc.) |

---

## Usage

Once running, the bot will:

- Send a startup message to Telegram with the initial BTC price.
- Log the latest BTC price every 10 seconds while the stream is connected.
- Send alerts like this when the threshold is crossed:

```
↑ BTCUSDT = $105,234.50
Change = +502.30 USD
Time: 2026-05-09T10:32:15Z
```

You can check the bot's health at:

```
GET http://localhost:8000/health  → 200 OK
GET http://localhost:8000/status  → 200 RUNNING
```

---

## Project Structure

```
BITCOIN-500/
├── code.py              # Main bot logic
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker container config
├── alert_image.png      # Sample alert screenshot
├── LICENSE              # MIT License
└── .github/
    └── workflows/       # GitHub Actions CI/CD
```

---

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a new branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request.

Please open an issue first for major changes so we can discuss the approach.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

> Stay informed. Never miss a significant Bitcoin move again. ₿
