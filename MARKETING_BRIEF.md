# BITCOIN 500 — Marketing Brief

**Research basis:** The current pushed repository files only. Repo facts are cited by path. Positioning and tagline options are proposals, not existing claims. Unknowns are marked **UNKNOWN - ask founder**.

## 1. APP IDENTITY

- **Name:** BITCOIN 500 (README heading: “₿ITCOIN-500”). Source: `README.md:1`.
- **Existing tagline:** “Stay informed. Never miss a significant Bitcoin move again. ₿” Source: `README.md:215`.
- **One-sentence description:** A Telegram-first bot that monitors Binance BTCUSDT and sends threshold price alerts with charts, plus scheduled daily, weekly, and monthly summaries. Sources: `code.py:867–993,678–816`; `README.md:34–46`.
- **One-paragraph description:** BITCOIN 500 listens to Binance’s BTCUSDT mini-ticker stream and compares the price with its current alert reference (default threshold $500). When the threshold is reached, it sends a chart and price movement to Telegram. It also sends a startup snapshot and completed-period reports. Optional integrations cross-post to X and publish Blogger posts with Dropbox-hosted chart images. Its posts include a market-information disclaimer. Sources: `code.py:35–61,705–816,897–980`; `README.md:41–47`.
- **Platforms:** Telegram bot/channel delivery is core; X and Blogger are optional publishing destinations. There is an operational HTTP health service, but no customer dashboard. Docker and Koyeb deployment are documented. No Android/iOS/desktop app or customer-facing API is present. Sources: `code.py:824–863`; `README.md:138–159`; `Dockerfile`; `Procfile`.
- **Tech stack:** Python 3.10 container; Binance WebSocket/public REST; Telegram Bot API; Matplotlib; optional Tweepy/X, Blogger API with Google OAuth, Dropbox API; Docker. Sources: `Dockerfile`; `requirements.txt`; `code.py`.

## 2. PROBLEM & SOLUTION

- **Problem:** People who follow Bitcoin may not want to watch charts continuously. Source: `README.md:34`.
- **Who has it:** Likely BTCUSDT watchers who want larger moves and periodic summaries in Telegram. This is an inference from the product behavior; demographics and audience research are **UNKNOWN - ask founder**.
- **User flow:**
  1. Reader joins the Telegram channel at `https://t.me/bitcoin500alerts` (in `code.py`).
  2. Operator configures a Telegram token and chat destination and runs/deploys the service. The bot needs posting rights in the channel. Sources: `README.md:86–112,140–146`.
  3. Bot listens to Binance’s BTCUSDT mini-ticker stream and records the first price as the reference. Sources: `code.py:875–903`; `README.md:58–62`.
  4. When movement from the reference reaches the configured threshold (default $500), it sends price, movement, UTC time, and chart, then resets the reference. Sources: `code.py:35–41,938–980`.
  5. The bot optionally posts startup/threshold updates to X and Blogger. Sources: `code.py:42–59,907–979`.
  6. Scheduler posts the prior UTC day, week, and month summaries to Telegram and optionally Blogger. Sources: `code.py:678–816`; `README.md:207`.

## 3. TARGET AUDIENCE

| Likely user type | Likely pain point | Alternatives indicated by repo |
|---|---|---|
| BTCUSDT watchers | Want alerts for larger moves without continuously checking charts | Manual chart watching is implied by `README.md:34`; named alternatives are **UNKNOWN - ask founder** |
| Telegram Bitcoin followers | Want price and chart information in a Telegram channel | Other channels/apps are **UNKNOWN - ask founder** |
| Readers seeking market recaps | Want a summarized completed-day/week/month range and volume | Named alternatives are **UNKNOWN - ask founder** |

- **Region/language/currency hints:** English copy; timestamps and report schedule use UTC; BTCUSDT market pair; prices and alert threshold in USD/USDT. No countries or localized versions specified. Sources: `code.py:35–41,734–749`; `README.md:170–189,207`.
- **Demographics, trading experience, and geographic focus:** **UNKNOWN - ask founder**.

## 4. FEATURES

| Feature | What it does (plain language) | User benefit | Status | File reference |
|---|---|---|---|---|
| BTCUSDT stream monitoring | Listens to Binance’s one-second mini-ticker WebSocket and reconnects after errors. | Keeps the bot listening without processing every individual trade. | Core | `code.py:867–993`; `README.md:41,58–62` |
| Threshold alerts | Sends a message and chart when movement from the current reference reaches configured threshold (default $500). | Brings larger price moves to Telegram. | Core | `code.py:35–41,938–980`; `README.md:42,61` |
| Startup update | Sends an initial price and chart at startup. | Shows the bot has started and shares a snapshot. | Core | `code.py:899–935` |
| Chart snapshots | Dark Binance Spot candlestick chart with volume, price, and `@bitcoin500alerts` watermark. Regular alert chart covers 48 15-minute candles. | Gives price alerts visual context. | Core | `code.py:541–636`; `README.md:47` |
| Scheduled reports | Completed day/week/month OHLC, net/percent move, BTC/USDT volume, and period-specific chart. | Offers a periodic recap in the channel. | Core; enabled by default | `code.py:61,678–816`; `README.md:46,182,207` |
| X cross-posting | Can upload chart and post startup/alert details to X. | Optional additional distribution. | Secondary; off by default via `X_POSTS_ENABLED` | `code.py:42–47,153–196,907–979`; `README.md:148,176–180` |
| Blogger publishing | Can publish price updates and reports with chart, market context, timestamp, and Telegram link. | Provides a web article version of updates. | Secondary; off by default via `BLOGGER_ENABLED` | `code.py:48–55,199–304,934–979`; `README.md:150–159,181–189` |
| Dropbox chart hosting/cleanup | Stores Blogger chart images and deletes oldest bot-generated images when projected account usage exceeds 1.8 GB. | Supplies embeddable Blogger images. | Secondary; Blogger image dependency | `code.py:56–60,307–492`; `README.md:155–159` |
| Health/status routes | Returns simple responses at `/`, `/health`, and `/status`. | Lets hosting check if the process responds. | Secondary; operational | `code.py:824–863`; `README.md:48,209–214` |
| Retry/backoff and graceful shutdown | Retries transient connection issues and handles termination signals. | Helps recover and stop cleanly. | Core/operational | `code.py:996–1004`; `README.md:51–52` |

## 5. UNIQUE SELLING POINTS

- Threshold BTCUSDT alerts are paired with chart snapshots. Sources: `code.py:938–980`; `README.md:42,47`.
- The same bot combines event alerts with completed daily, weekly, and monthly recaps. Sources: `code.py:678–816`; `README.md:46`.
- Optional publishing to X and Blogger; Blogger charts can be hosted through Dropbox. Sources: `code.py:153–304,327–492`; `README.md:44–46,150–159`.
- No competitor research or superiority benchmarks are included. Comparisons: **UNKNOWN - ask founder**.

## 6. PRICING & MONETIZATION

- **Product price/plans/member limits:** **UNKNOWN - ask founder**. No payment, subscription, or checkout code found.
- **Source license:** MIT; this is software licensing, not a user plan. Source: `LICENSE`.
- **Configured limits:** Default threshold $500; regular chart uses 48 candles at 15-minute intervals; report charts use up to 96 15-minute, 168 hourly, or 200 four-hour candles. Sources: `code.py:35–41,541–564,678–682`.
- **Dropbox storage behavior:** The bot tries to keep total usage below 1.8 GB by removing oldest generated charts; older Blogger images can break after deletion. Sources: `code.py:60,407–474`; `README.md:159`.
- **Hosting costs:** README recommends an always-on paid Koyeb Worker for continuous service; this is operator hosting, not product pricing. Source: `README.md:138–146`.
- **Ads, affiliate links, and revenue model:** **UNKNOWN - ask founder**; none found in repo.
- **X costs:** README advises checking X Developer Console pricing; exact cost is **UNKNOWN**. Source: `README.md:148`.

## 7. INTEGRATIONS & SUPPORTED SERVICES

| Service | Use | Required/optional |
|---|---|---|
| Binance Spot | BTCUSDT mini-ticker WebSocket and public klines for charts/reports | Core (`code.py:41,541–559,875–897`) |
| Telegram Bot API | Sends messages and chart photos to configured chat | Required (`code.py:112–150,639–675`) |
| X | Optional chart upload and post via Tweepy | Optional (`code.py:42–47,153–196`) |
| Blogger / Google OAuth | Optional Blogger articles and summaries | Optional (`code.py:48–55,199–304`; `setup_blogger.py`) |
| Dropbox | Optional Blogger chart storage and public viewing links | Optional (`code.py:56–60,307–492`; `setup_dropbox.py`) |
| Docker | Container build and launch | Optional deployment (`Dockerfile`) |
| Koyeb | Documented deployment target | Optional hosting (`README.md:138–146`) |
| GitHub Actions | Manual workflow; installs dependencies and runs bot with secrets, five-minute timeout | Manual run, not 24/7 (`.github/workflows/btc-bot.yml`) |

## 8. USER FLOW & ONBOARDING

- **Signup/login:** None implemented. Readers join Telegram; operators configure and run the bot. Sources: `README.md:86–112`; `code.py`.
- **Operator setup:** Create bot via BotFather, set `TELEGRAM_TOKEN`/`CHAT_ID`, install requirements, run `python code.py` or deploy Docker/Koyeb. Sources: `README.md:75–146`.
- **Interactive commands/screens:** No Telegram commands, keyboard, or product screens found. Health routes are operational only (`code.py:824–842`).
- **Reusable exact copy:**
  - Startup: `₿  *BTCUSDT · Bitcoin price*` / `💵 *$[price]*` / `🕒 Updated [date/time] UTC` (`code.py:902–906`).
  - Alert: `↑ BTCUSDT · Price alert` / `💵 *$[price]*` / `📊 Change: *+[change]*` / UTC time (`code.py:947–956`).
  - Report header: `₿ BITCOIN 500 · DAILY/WEEKLY/MONTHLY REPORT` (`code.py:734–749`).
  - CTA: `Join our Telegram: https://t.me/bitcoin500alerts` (`code.py:907–912,958–964`).
  - Disclaimer: `Market summary only · Not financial advice.` (`code.py:747`).
  - Config error: `TELEGRAM_TOKEN is required but not set. Exiting.` (`code.py:70–73`).
- **Voice inferred from copy:** Concise, price-first, factual, with arrows/emojis; Blogger content is explanatory and includes a disclaimer. Sources: `code.py:495–538,734–779,902–979`.

## 9. BRAND ASSETS & VOICE

- **Local asset:** `alert_image.png`; README calls it a sample alert screenshot. Runtime code does not reference it (`README.md:220–228`; `code.py`).
- **README image:** Remote GitHub user-attachment image, not a checked-in asset (`README.md:2`).
- **Chart palette:** Background `#101820`, green up `#36c98f`, red down `#ff6474`, blue price line `#65b9ff`, watermark `@bitcoin500alerts` (`code.py:578–630`).
- **Logo/type:** Text glyph `₿`; no standalone logo or chosen brand font is defined. Matplotlib is used for charts (`code.py`; `requirements.txt`).
- **Voice:** Factual, concise, market-oriented. This is an inference from alert and report copy.

## 10. TRUST & PROOF

- **Credentials:** Tokens and OAuth values are read from environment variables; setup docs recommend storing them as secrets. `.gitignore` excludes `.env*`, OAuth client JSON, and token files. Sources: `code.py:35–59`; `README.md:143,148,157,167–189`; `.gitignore`.
- **Network:** API requests use HTTPS and Binance stream uses WSS (`code.py:118,210,309,335,366,541,875`).
- **Data storage:** No application database/user-profile store found. Alert reference and scheduled report de-duplication are in process memory (`code.py`). Hosting logs are outside this claim.
- **Public content:** Dropbox chart links use public viewer access for Blogger embedding (`code.py:366–404`).
- **Metrics/testimonials:** None found. Subscriber counts, performance, uptime, and testimonials: **UNKNOWN - ask founder**.
- **Disclaimer:** “Market summary only · Not financial advice” and “not a trading recommendation” appear in report/Blogger content (`code.py:747,779`).
- **Privacy/terms/support pages:** Not found in repo; **UNKNOWN - ask founder** whether available elsewhere.
- **Security claim limits:** No end-user authentication, encryption-at-rest system, security audit, or certification documented.

## 11. DISTRIBUTION & LINKS

- **GitHub:** https://github.com/vyankateshpotdar/BITCOIN-500 (`README.md`).
- **Telegram:** `@bitcoin500alerts`; `https://t.me/bitcoin500alerts` appears in `code.py`.
- **Blogger URL:** **UNKNOWN - ask founder**; repo can select a blog but does not name its public URL (`setup_blogger.py`).
- **X profile:** **UNKNOWN - ask founder**; credentials exist but no public profile URL is configured.
- **Website, app stores, support email:** **UNKNOWN - ask founder**; none found.
- **Analytics:** No analytics integration found.
- **Referral/share:** No referral mechanism; Telegram join links are CTAs, not tracked referrals.
- **Routes:** `/`, `/health`, `/status` are operational endpoints, not marketing pages (`code.py:824–842`).

## 12. MARKETING GAPS & OPPORTUNITIES

- No landing page, user-facing dashboard, signup flow, analytics, or referral tracking.
- No audience/competitor research, product pricing, marketing budget, launch plan, testimonials, or public performance metrics.
- No privacy policy, terms, support contact, or public X/Blogger profile links in repo.
- No localization beyond English and UTC.
- Dropbox cleanup can remove old chart images while Blogger posts remain (`README.md:159`).
- Scheduled posts require the process to be running at report times; README warns free Koyeb web services can sleep (`README.md:142–146,207`).

**Five quick wins (proposals):**

1. Create a landing page with a clear Telegram join CTA, threshold explanation, and disclaimer.
2. Publish privacy, terms, and support contact pages.
3. Add privacy-conscious analytics for landing visits and Telegram clicks.
4. Pin a channel onboarding post explaining thresholds, UTC report schedule, and charts.
5. Measure channel growth and post engagement before making public traction claims.

## 13. KEYWORDS & POSITIONING

**15 suggested keywords:** Bitcoin price alerts Telegram; BTCUSDT alerts; Binance Bitcoin price alerts; Bitcoin threshold alerts; BTC price chart Telegram; Bitcoin candlestick chart; BTC volume chart; Bitcoin daily market summary; Bitcoin weekly market report; Bitcoin monthly market report; BTCUSDT price update; Binance Spot BTCUSDT; Bitcoin market movement notifications; Telegram crypto price updates; Bitcoin chart snapshot.

**Three draft positioning statements:**

1. “Follow significant BTCUSDT moves with chart-backed Telegram alerts.”
2. “A Telegram-first BTCUSDT watcher with threshold alerts and periodic recaps.”
3. “Binance Spot Bitcoin updates and historical chart summaries, delivered to Telegram.”

**Five draft taglines (under 8 words):**

- “Bitcoin moves. Get the chart.”
- “BTC updates, without constant chart watching.”
- “A clearer view of Bitcoin moves.”
- “Follow BTCUSDT, one alert at a time.”
- “Your Bitcoin market recap on Telegram.”

## 14. OPEN QUESTIONS FOR THE FOUNDER

- Who is the primary audience, and which countries/languages should marketing target?
- Is the audience beginner, active trader, long-term holder, or general market follower?
- Is access free? Is a paid product or revenue model planned?
- Which competitors matter, and what comparison claims can be substantiated?
- Is $500 the intended public default? Can subscribers configure their own threshold?
- How should users understand the reference price (startup/previous alert)?
- What are the official Blogger and X profile URLs?
- Is there a website, support email, privacy policy, or terms page outside the repo?
- What are the channel growth target, launch plan/date, and marketing budget?
- Which subscriber/reach/uptime/delivery metrics may be shared publicly?
- Who monitors incidents and handles user support?
- What uptime can the hosting plan support?
- What is the retention policy for old Dropbox charts and linked Blogger images?
- Are additional pairs, exchanges, languages, or reports planned?
- Should X posting remain enabled given possible API costs?
