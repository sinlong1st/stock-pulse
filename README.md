# StockPulse

A lightweight, single-user market intelligence service. It monitors financial
news and macroeconomic events on a schedule, classifies what matters, and sends
alerts (Telegram for the MVP) — so you don't have to watch the news all day.

Design goals: simple, low-maintenance, and under **$10/month**.

See [`specs/STOCKPULSE_PROJECT_SPEC.md`](specs/STOCKPULSE_PROJECT_SPEC.md) and
[`specs/STOCKPULSE_TECHNICAL_PLAN.md`](specs/STOCKPULSE_TECHNICAL_PLAN.md) for the
full product and technical plans.

## Status

**Live in production** — deployed 24/7 on a DigitalOcean droplet via Docker.
What it does today:

- **News → alerts:** collects RSS (watchlist + macro), dedupes, rule-filters,
  AI-classifies (importance/category/sentiment/tickers), and sends Telegram
  alerts on a schedule. Quiet hours hold non-urgent alerts overnight.
- **Self-evaluation:** scores the AI's bullish/bearish calls against real price
  moves (`/evaluation`, optional daily digest).
- **Market Briefing "the secretary":** pulls the *latest* news and an AI analyst
  reports what matters for your watchlist — scheduled (08:30 → every 2h → 18:00
  PT weekdays) and on demand via `/report` (whole watchlist or a single stock),
  with open/current prices + honest freshness labels and price-mover flags.
- **Manage from Telegram:** `/watchlist`, `/watch <name>`, `/unwatch`, `/help`.

Feature designs live in `specs/` (evaluation, briefing, watchlist-commands
plans, all marked shipped); progress overview in
[`specs/STOCKPULSE_PHASE_GUIDE.md`](specs/STOCKPULSE_PHASE_GUIDE.md). Deploy:
[`DEPLOY.md`](DEPLOY.md) (+ [`BUYING_A_SERVER.md`](BUYING_A_SERVER.md) for a
first server).

## Requirements

- Python 3.12+

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash);  use .venv/bin/activate on macOS/Linux

# Install the project with dev dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env            # then edit .env with real values
cp watchlist.example.json watchlist.json   # your tickers + company names
cp keywords.example.json keywords.json     # your macro + sector keywords

# Create the database (runs migrations)
alembic upgrade head
```

## Configuring what StockPulse watches

Two git-ignored JSON files control the rule filter. Edit them and **restart
the app** to pick up changes. If either file is missing, StockPulse falls
back to built-in defaults, so it always runs.

**`watchlist.json`** — tracked tickers and their company-name aliases (the
names that should also match in headlines):

```json
{
  "NVDA": ["Nvidia"],
  "MSFT": ["Microsoft"],
  "TSLA": ["Tesla"]
}
```

**`keywords.json`** — macro keywords and sector groups:

```json
{
  "macro": ["Federal Reserve", "CPI", "inflation", "tariff"],
  "sectors": {
    "AI/Semiconductor": ["AI", "semiconductor", "GPU"],
    "Crypto": ["bitcoin", "ethereum"]
  }
}
```

Omit a top-level key to keep its built-in default; use an empty list/object
to disable that part. Broad words like `oil` or `bank` can over-match — trim
them here if alerts get noisy.

### Language

Set `OUTPUT_LANGUAGE` in `.env` (e.g. `English`, `Vietnamese`, `Spanish`) to
choose the language the AI writes the summary and "why it matters" in.
Telegram alerts inherit it. Existing classifications keep their original
language; only new ones use the new setting.

### Alert message options

Each AI verdict also includes a **sentiment** — whether the news is good
(🟢 bullish, green ▲), bad (🟠 bearish, orange ▼), or neutral (⚪ →) for the
related stock. It shows on the news page next to the importance badge and in
the alert header. It's the AI's read of the news, not a price prediction.

The Telegram alert leads with the AI summary and "why it matters", then the
source and article title (the title is also in the link). Two `.env` toggles:

- `ALERT_INCLUDE_LINK` (default `true`) — include the article URL.
- `ALERT_LINK_PREVIEW` (default `false`) — show Telegram's link preview/
  thumbnail. Off keeps messages short.

## Run

```bash
uvicorn app.main:app --reload
```

Then check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0"}
```

Open http://127.0.0.1:8000/ for the news page and http://127.0.0.1:8000/alerts
for alert history.

> On Windows PowerShell, activate the venv first with
> `.\.venv\Scripts\Activate.ps1`, then the same `uvicorn` command. `Ctrl+C`
> stops the server. Use `--reload` only in development.

## Market Briefing ("the secretary")

A proactive analyst that pulls the **latest** news, decides what matters for
your watchlist (AI, semis, macro/Fed, geopolitics/war, energy), and reports it
— separate from the per-article alert flow. See
[specs/STOCKPULSE_BRIEFING_PLAN.md](specs/STOCKPULSE_BRIEFING_PLAN.md).

Three ways to get a briefing:

- **On demand — dashboard:** the **🗞️ Report now** button on the news page
  (or `POST /report`). Always answers, even on a quiet market.
- **On demand — Telegram:** send **`/report`** to your bot. Set
  `BRIEFING_COMMAND_ENABLED=true` (needs the server running to listen).
- **On demand — one stock:** send **`/report WDC`** (or a company name — even a
  typo, like `/report micosoft` or `/report spacex`). It narrows the news to
  that name and the AI resolves the ticker with common sense. Also
  `POST /report?q=WDC`.
- **Scheduled:** set `BRIEFING_ENABLED=true` (and `SCHEDULER_ENABLED=true`). On
  US-market/Pacific time, Mon–Fri: a full **08:30** morning brief, short
  **every-2h** updates (10:30–16:30), and an **18:00** end-of-day wrap.

Every report carries a **timestamp** (in `BRIEFING_TIMEZONE`) and an **open +
current price** line per relevant ticker (a full `/report` prices your whole
watchlist; a focused one prices that stock) with an honest **freshness label** —
`live` if the last trade is recent, otherwise the actual last-trade time (e.g.
`as of Fri 13:00 PDT`), since outside market hours a stock isn't trading and
there is no live price. Prices default to **Yahoo** (`BRIEFING_PRICE_SOURCE`) —
free, keyless, consolidated across venues and including pre/post-market, so it's
close to a phone stocks app; set it to `alpaca` to use the IEX feed instead.
Toggle the whole block with `BRIEFING_PRICES_IN_REPORT`.

Key settings (all in `.env`, see `.env.example`): `BRIEFING_TIMEZONE`
(defaults to `America/Los_Angeles`, independent of `TIMEZONE`),
`BRIEFING_MORNING_AT` / `BRIEFING_INTRADAY_UNTIL` / `BRIEFING_WRAP_AT`, the
look-back windows, `BRIEFING_MODEL`, and `BRIEFING_PRICES_IN_REPORT`.

> ⚠️ Each briefing is one OpenAI call. Retrieval is the two RSS feeds only for
> now (web search — `BRIEFING_WEB_SEARCH_ENABLED` — is not wired yet).

## Telegram commands

With the listener on (`BRIEFING_COMMAND_ENABLED=true`), text these to your bot:

| Command | Does |
|---|---|
| `/report [ticker]` | Market briefing (add a ticker/name for one stock) |
| `/watchlist` | Show your watched tickers |
| `/watch tesla` | Add a stock (resolves the name → ticker via Yahoo) |
| `/unwatch tsla` | Remove a stock |
| `/language vi` | Switch AI output language — `en` or `vi` (others rejected) |
| `/help` | List the commands |

`/watch` and `/unwatch` edit `watchlist.json` and take effect immediately (news
+ reports pick up the change, no restart). `/language` switches the AI output
language between English (`en`) and Vietnamese (`vi`) live — the choice is saved
to `runtime_prefs.json` (in the `./data` volume under Docker) and overrides
`OUTPUT_LANGUAGE`; anything other than `en`/`vi` is politely rejected. All
commands are locked to your chat.

> **Docker note:** `docker-compose.yml` mounts `watchlist.json` **writable** so
> `/watch`/`/unwatch` can persist. (If you deployed before this, `git pull &&
> docker compose up -d --build` recreates the container with the new mount.)

## Running the pipeline

The full pipeline is **collect → dedupe → filter → classify → decide → alert**.

News comes from two sources, each on its own fetch cadence:

- **Watchlist** — Yahoo Finance per-ticker feeds (from `watchlist.json`),
  every `WATCHLIST_FETCH_INTERVAL_MINUTES` (default 5).
- **Macro** — a Google News search over your macro keywords, every
  `MACRO_FETCH_INTERVAL_MINUTES` (default 30).

How to run it:

- **Once, on demand:** `POST /run` (or the buttons on the news page) — runs
  both sources through one full cycle. The safe way to test.
- **Automatically:** set `SCHEDULER_ENABLED=true` in `.env`; the two sources
  run as independent scheduled jobs on their own intervals.

> ⚠️ Automatic mode spends OpenAI credit and sends Telegram messages on its
> own. `MAX_CLASSIFICATIONS_PER_RUN` and `MAX_ALERTS_PER_RUN` cap each run.

## Test

```bash
pytest
```

## Deploy (24/7)

StockPulse is a single always-on process (scheduler + Telegram listener + web),
so it wants a small always-on host, not serverless. A `Dockerfile` +
`docker-compose.yml` are included:

```bash
cp .env.example .env            # fill in keys + toggles
cp watchlist.example.json watchlist.json
cp keywords.example.json  keywords.json
docker compose up -d --build
docker compose logs -f
```

Full step-by-step for a cheap VPS (Docker install, SSH-tunnel to the dashboard,
updates, backups) is in **[DEPLOY.md](DEPLOY.md)**. Never bought a server
before? **[BUYING_A_SERVER.md](BUYING_A_SERVER.md)** walks you through choosing a
provider, SSH keys, and first login.

## Roadmap

Development proceeds one phase at a time (see the technical plan):

0. Project foundation ✅
1. News collection (RSS) ✅
2. Persistence & deduplication (SQLite) ✅
3. Rule-based filtering ✅
4. AI classification ✅
5. Alert decision engine ✅
6. Telegram notifications ✅
7. Scheduled end-to-end pipeline ✅
8. Quiet hours, price confirmation & self-evaluation ✅
9. Market briefing + on-demand /report ✅ (web search deferred)
10. Manage watchlist from Telegram (/watch /unwatch) ✅
11. Docker deploy ✅ · CI (todo)

Deferred / ideas: briefing **web search** (let the model pull news itself,
`BRIEFING_WEB_SEARCH_ENABLED`); AI-fallback name resolution for `/watch` typos;
GitHub Actions CI.
