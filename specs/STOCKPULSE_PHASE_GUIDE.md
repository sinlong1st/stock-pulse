# StockPulse — Phase Guide & Progress Tracker

A plain-English companion to the technical plan. It answers three questions
for every phase: **what gets built, what you can do/see after it, and how to
check it works.** Update the status column as we go.

> Mental model: we build StockPulse like a house — foundation first, then one
> room at a time. Each phase ends with something that actually runs.

---

## Where we are now

```
✅ Phase 0  Foundation (web server + /health)
✅ Phase 1  News collection (pull real headlines)
✅ Phase 2  Remember what it's seen (database + dedup)
✅ Phase 3  Filter out the noise (keywords/watchlist)
✅ Phase 4  AI decides what matters
✅ Phase 5  Alert rules (should we notify?)
✅ Phase 6  Send Telegram alerts
✅ Phase 7  Run automatically every few minutes   ← YOU ARE HERE
⬜ Phase 8  Package it up (Docker + CI)
```

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
| **Configure** | `SCHEDULER_ENABLED` (default false), `NEWS_CHECK_INTERVAL_MINUTES`, `MAX_CLASSIFICATIONS_PER_RUN`, `MAX_ALERTS_PER_RUN`. |
| **Cost** | Enabling the scheduler spends OpenAI credit and sends Telegram on its own; caps limit each run. |

### ⬜ Phase 8 — Docker & CI
| | |
|---|---|
| **Goal** | Make it easy to run anywhere and validate every change. |
| **What you can do** | Clone → run with documented steps; tests run automatically on push. |
| **What you'll see** | A `Dockerfile` and green GitHub Actions checks. |
| **How to test** | `docker compose up`; CI passes on a pull request. |

---

## When is the MVP "done"?

When StockPulse can, on its own: pull real news → skip duplicates → filter noise →
AI-classify what's left → decide if it matters → send a Telegram alert → and store
the history — all on a schedule, for **under $10/month**.

That's the end of **Phase 7** (with Phase 8 making it easy to deploy).

---

## How to try whatever is built so far

```powershell
# 1. activate the environment
.\.venv\Scripts\Activate.ps1

# 2. start the app
uvicorn app.main:app --reload

# 3. in a browser, see the latest headlines as a clean page
#    http://127.0.0.1:8000/
#    (or the interactive API page: http://127.0.0.1:8000/docs)

# run the tests any time
pytest
```

_Legend: ✅ done · ⬜ not started. Keep the "Where we are now" block in sync as phases land._
