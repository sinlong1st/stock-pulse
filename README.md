# StockPulse

A lightweight, single-user market intelligence service. It monitors financial
news and macroeconomic events on a schedule, classifies what matters, and sends
alerts (Telegram for the MVP) — so you don't have to watch the news all day.

Design goals: simple, low-maintenance, and under **$10/month**.

See [`specs/STOCKPULSE_PROJECT_SPEC.md`](specs/STOCKPULSE_PROJECT_SPEC.md) and
[`specs/STOCKPULSE_TECHNICAL_PLAN.md`](specs/STOCKPULSE_TECHNICAL_PLAN.md) for the
full product and technical plans.

## Status

**Phase 0 — Project Foundation** (current): runnable FastAPI skeleton with
configuration, logging, and a health check. No news collection or AI yet.

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

Key settings (all in `.env`, see `.env.example`): `BRIEFING_TIMEZONE`
(defaults to `America/Los_Angeles`, independent of `TIMEZONE`),
`BRIEFING_MORNING_AT` / `BRIEFING_INTRADAY_UNTIL` / `BRIEFING_WRAP_AT`, the
look-back windows, and `BRIEFING_MODEL`.

> ⚠️ Each briefing is one OpenAI call. Retrieval is the two RSS feeds only for
> now (web search — `BRIEFING_WEB_SEARCH_ENABLED` — is not wired yet).

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
10. Docker deploy ✅ · CI
