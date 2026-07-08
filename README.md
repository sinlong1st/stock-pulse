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

## Running the pipeline

The full pipeline is **collect → dedupe → filter → classify → decide → alert**.

- **Once, on demand:** `POST /run` (or the buttons on the news page). This is
  the safe way to test — it runs a single cycle.
- **Automatically:** set `SCHEDULER_ENABLED=true` in `.env` and StockPulse
  runs the pipeline every `NEWS_CHECK_INTERVAL_MINUTES`.

> ⚠️ Automatic mode spends OpenAI credit and sends Telegram messages on its
> own. `MAX_CLASSIFICATIONS_PER_RUN` and `MAX_ALERTS_PER_RUN` cap each run.

## Test

```bash
pytest
```

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
8. Docker & CI
