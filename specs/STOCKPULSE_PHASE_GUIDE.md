# StockPulse — Phase Guide & Progress Tracker

A plain-English companion to the technical plan. It answers three questions
for every phase: **what gets built, what you can do/see after it, and how to
check it works.** Update the status column as we go.

> Mental model: we build StockPulse like a house — foundation first, then one
> room at a time. Each phase ends with something that actually runs.

---

## Where we are now

**Live in production** — deployed 24/7 on a DigitalOcean droplet via Docker.

```
✅ Phase 0   Foundation (web server + /health)
✅ Phase 1   News collection (pull real headlines)
✅ Phase 2   Remember what it's seen (database + dedup)
✅ Phase 3   Filter out the noise (keywords/watchlist)
✅ Phase 4   AI decides what matters (+ sentiment)
✅ Phase 5   Alert rules (should we notify?)
✅ Phase 6   Send Telegram alerts
✅ Phase 7   Run automatically (per-source schedules)
✅ Phase 8   Quiet hours + price context + self-evaluation   (see EVALUATION_PLAN)
✅ Phase 9   Market Briefing "secretary" + on-demand /report   (see BRIEFING_PLAN)
✅ Phase 10  Manage watchlist from Telegram (/watch /unwatch …) (see WATCHLIST_COMMANDS_PLAN)
✅ Phase 11  Docker deploy (Dockerfile + compose + DEPLOY.md)   ← LIVE
⬜ Later     CI; briefing web-search (step H); optional extras
```

Each of the later phases has its own spec in `specs/` with full design + a
build-order table marked shipped. This guide tracks the original MVP pipeline
(phases 0–7); the newer capabilities are summarized in §"Beyond the MVP" below.

---

## The pipeline (what a news article travels through)

Each phase lights up one more box. Boxes with ✅ exist today.

```
   News sources
   (RSS feeds)          ✅ Phase 1
        │
        ▼
   Collect + Normalize  ✅ Phase 1   → turn messy feeds into clean articles
        │
        ▼
   Store + Deduplicate  ✅ Phase 2   → save articles, skip ones already handled
        │
        ▼
   Rule filter          ✅ Phase 3   → drop obvious noise before spending money
        │
        ▼
   AI classifier        ✅ Phase 4   → importance, category, tickers, summary
        │
        ▼
   Alert decision       ✅ Phase 5   → OUR rules decide: notify or not?
        │
        ▼
   Notify (Telegram)    ✅ Phase 6   → message hits your phone
        │
        ▼
   (runs on a timer)    ✅ Phase 7   → all of the above, automatic
```

---

## Phase-by-phase detail

### ✅ Phase 0 — Foundation
| | |
|---|---|
| **Goal** | A runnable, empty app skeleton. |
| **What you can do** | Start a web server; ask it "are you alive?" |
| **What you'll see** | `GET /health` → `{"status":"ok","version":"0.1.0"}` |
| **How to test** | `uvicorn app.main:app --reload`, then open http://127.0.0.1:8000/health |
| **Not yet** | No news, no AI, no alerts. |

### ✅ Phase 1 — News collection
| | |
|---|---|
| **Goal** | Pull real articles from **one** source (Yahoo Finance RSS). |
| **What you can do** | Trigger a fetch and see live headlines flow through your own code. |
| **What you'll see** | A visual news page at http://127.0.0.1:8000/ · or raw JSON at `/collect` |
| **How to test** | Start the server, open http://127.0.0.1:8000/ in a browser · or run `pytest` |
| **Not yet** | Nothing is saved — calling `/collect` twice returns the same items. |

### ✅ Phase 2 — Persistence & deduplication
| | |
|---|---|
| **Goal** | Save articles to a database and never process the same story twice. |
| **What you can do** | Click "Fetch latest news" repeatedly; articles accumulate, no duplicates. |
| **What you'll see** | A `stockpulse.db` file; `/collect` returns `new` vs `duplicates` counts. |
| **How to test** | `/collect` twice → 2nd run shows all duplicates, `stored_total` unchanged · or `pytest` |
| **Setup** | Run `alembic upgrade head` once to create the database table. |

### ✅ Phase 3 — Rule-based filtering
| | |
|---|---|
| **Goal** | Cheaply drop irrelevant articles before involving AI (saves money). |
| **What you can do** | Separate "likely matters" from "obvious noise" using tickers, company names, macro + sector keywords. |
| **What you'll see** | `/collect` reports a `relevant` count; the home page highlights matches with chips (NVDA, Fed, AI/Semiconductor…). |
| **How to test** | `/collect` and read the `relevant` count · open `/` and look for highlighted cards · or `pytest` |
| **Configure** | Edit `watchlist.json` (tickers + names) and `keywords.json` (macro + sector keywords), then restart. Copy each from its `*.example.json`. |
| **Note** | Matching is deliberately generous (better to over-include than miss news); the AI in Phase 4 is the second, smarter gate. |

### ✅ Phase 4 — AI classification
| | |
|---|---|
| **Goal** | Ask an AI model (OpenAI) to judge each filtered article. |
| **What you can do** | Get structured output: importance, category, tickers, summary, why it matters, alert recommendation. |
| **What you'll see** | `POST /classify` returns a validated verdict per article and stores it; classified cards on the home page show an importance badge + "why it matters". |
| **How to test** | `pytest` uses a *mocked* AI (no API calls) · live: click "Analyze with AI" on `/`, or `POST /classify?limit=1`. |
| **Configure** | Set `OPENAI_API_KEY` in `.env` (and optionally `OPENAI_MODEL`, default `gpt-4o-mini`). |
| **Cost** | Manual/opt-in only — nothing calls the API automatically. Already-classified articles are skipped. |

### ✅ Phase 5 — Alert decision engine
| | |
|---|---|
| **Goal** | **Our** app (not the AI) makes the final call on whether to alert. |
| **What you can do** | Consistent importance → action; alert records are created (status PENDING). |
| **What you'll see** | `LOW → log only · MEDIUM/HIGH/CRITICAL → Telegram`; `/classify` reports `alerts_created`. |
| **How to test** | `pytest` on the decision rules and alert storage. |
| **Configure** | `ALERT_MIN_IMPORTANCE` in `.env` (default `MEDIUM`). |
| **Note** | The AI's `should_alert` is only a recommendation; the app decides by importance threshold + relevance. |

### ✅ Phase 6 — Telegram notifications
| | |
|---|---|
| **Goal** | Actually deliver a message to your phone. |
| **What you can do** | Send PENDING alerts to Telegram; view all alerts + status on the `/alerts` page. |
| **What you'll see** | A real Telegram message (headline, why it matters, tickers, link); alerts move PENDING → SENT/FAILED. |
| **How to test** | Mocked tests for formatting/sending/routing · live: click "Send pending" on `/alerts`. |
| **Needs** | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env` (create a bot via @BotFather). |

### ✅ Phase 7 — Scheduled end-to-end pipeline
| | |
|---|---|
| **Goal** | Tie it all together and run it **automatically**. |
| **What you can do** | `POST /run` to run the whole pipeline once, or enable the scheduler to repeat it. |
| **What you'll see** | One log line per run: `collected=… new=… relevant=… classified=… alerts_created=… sent=…`. |
| **How to test** | `pytest` (fully mocked) · live: `POST /run` once, or set `SCHEDULER_ENABLED=true`. |
| **Configure** | `SCHEDULER_ENABLED` (default false); `WATCHLIST_FETCH_INTERVAL_MINUTES` (5) + `MACRO_FETCH_INTERVAL_MINUTES` (30) run as two independent jobs; `MAX_CLASSIFICATIONS_PER_RUN`, `MAX_ALERTS_PER_RUN`. |
| **Cost** | Enabling the scheduler spends OpenAI credit and sends Telegram on its own; caps limit each run. |

### ✅ Phase 8 — Quiet hours + price context + self-evaluation
See **STOCKPULSE_EVALUATION_PLAN.md** (build order A–E all shipped). Adds a daily
quiet window that holds non-urgent alerts, Alpaca price context, and a
self-evaluation loop that scores the AI's bullish/bearish calls against real
price moves (`/evaluation` page, `POST /evaluate`, optional daily digest).

### ✅ Phase 9 — Market Briefing "the secretary" + on-demand /report
See **STOCKPULSE_BRIEFING_PLAN.md** (A–G shipped; web search = deferred step H).
A separate pipeline from alerts: pull the **latest** news → an AI analyst
synthesizes what matters for the watchlist → deliver. Scheduled (08:30 → every
2h → 18:00 PT weekdays) and on demand (`/report`, `/report wdc`, `POST /report`).
Includes a timestamp/recap guard, rolling theme memory, notable price-mover
flags, and open/current price lines with honest freshness labels (Yahoo source).

### ✅ Phase 10 — Manage the watchlist from Telegram
See **STOCKPULSE_WATCHLIST_COMMANDS_PLAN.md** (A–E shipped). A command router on
the Telegram listener: `/watchlist`, `/watch <name>` (Yahoo name→ticker),
`/unwatch <ticker>`, `/help`. Edits `watchlist.json` live (no restart).

### ✅ Phase 11 — Docker deploy
`Dockerfile` + `docker-compose.yml` (restart policy, data volume, writable
watchlist mount) + `DEPLOY.md` + `BUYING_A_SERVER.md`. Running 24/7 on a
DigitalOcean droplet. CI is still a "later".

---

## When is the MVP "done"?

The MVP ended at **Phase 7**: on its own, pull real news → skip duplicates →
filter noise → AI-classify → decide if it matters → send a Telegram alert →
store history, on a schedule, for **under $10/month**. Everything since (8–11)
is the "trust + control" layer on top, and it's all shipped and deployed.

---

## Beyond the MVP — where things live

- **Alerts pipeline:** `app/jobs/news_monitor.py`, `app/pipeline/`, `app/alerts/`.
- **Self-evaluation:** `app/evaluation.py`, `app/jobs/evaluator.py`.
- **Prices:** `app/prices.py` (Alpaca + Yahoo clients, freshness labels).
- **Briefing ("secretary"):** `app/briefing/` (retrieval, analyst, render, memory,
  focus) + `app/jobs/briefing.py` (the `run_briefing`/`run_report` job).
- **Telegram commands:** `app/alerts/telegram_listener.py` (router) + `app/commands/`.
- **Config:** everything is in `app/config.py` (typed) + `.env.example`.

## How to try whatever is built so far

```powershell
# 1. activate the environment
.\.venv\Scripts\Activate.ps1

# 2. start the app (add --reload for development)
uvicorn app.main:app

# 3. dashboard + docs
#    http://127.0.0.1:8000/       (news + Fetch/Analyze/Report buttons)
#    http://127.0.0.1:8000/evaluation
#    http://127.0.0.1:8000/docs   (interactive API)

# run the tests any time (all external services mocked)
pytest
```

_Legend: ✅ done · ⬜ not started. Keep the "Where we are now" block in sync as phases land._
