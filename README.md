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
cp watchlist.example.json watchlist.json   # then edit your tickers + company names

# Create the database (runs migrations)
alembic upgrade head
```

## Configuring the watchlist

Your tracked tickers and their company-name aliases live in **`watchlist.json`**
(git-ignored). It maps each ticker to the names that should also match in
headlines:

```json
{
  "NVDA": ["Nvidia"],
  "MSFT": ["Microsoft"],
  "TSLA": ["Tesla"]
}
```

Edit the file and **restart the app** to pick up changes. If the file is
missing, StockPulse falls back to built-in defaults, so it always runs.

## Run

```bash
uvicorn app.main:app --reload
```

Then check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0"}
```

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
5. Alert decision engine
6. Telegram notifications
7. Scheduled end-to-end pipeline
8. Docker & CI
