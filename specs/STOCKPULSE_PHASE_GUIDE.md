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
✅ Phase 2  Remember what it's seen (database + dedup)   ← YOU ARE HERE
⬜ Phase 3  Filter out the noise (keywords/watchlist)
⬜ Phase 4  AI decides what matters
⬜ Phase 5  Alert rules (should we notify?)
⬜ Phase 6  Send Telegram alerts
⬜ Phase 7  Run automatically every few minutes
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
   Rule filter          ⬜ Phase 3   → drop obvious noise before spending money
        │
        ▼
   AI classifier        ⬜ Phase 4   → importance, category, tickers, summary
        │
        ▼
   Alert decision       ⬜ Phase 5   → OUR rules decide: notify or not?
        │
        ▼
   Notify (Telegram)    ⬜ Phase 6   → message hits your phone
        │
        ▼
   (runs on a timer)    ⬜ Phase 7   → all of the above, automatic
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

### ⬜ Phase 3 — Rule-based filtering
| | |
|---|---|
| **Goal** | Cheaply drop irrelevant articles before involving AI (saves money). |
| **What you can do** | Separate "likely matters" from "obvious noise" using keywords + your watchlist. |
| **What you'll see** | Counts like "collected 50 → 7 passed the filter". |
| **How to test** | `pytest` on relevant vs. irrelevant sample articles. |

### ⬜ Phase 4 — AI classification
| | |
|---|---|
| **Goal** | Ask an AI model to judge each filtered article. |
| **What you can do** | Get structured output: importance, category, tickers, summary, why it matters. |
| **What you'll see** | A JSON verdict per article (validated before we trust it). |
| **How to test** | `pytest` with a *mocked* AI — no real API calls in normal tests. |
| **Note** | This is the first phase that can cost money to run for real. |

### ⬜ Phase 5 — Alert decision engine
| | |
|---|---|
| **Goal** | **Our** app (not the AI) makes the final call on whether to alert. |
| **What you can do** | Map importance → action consistently. |
| **What you'll see** | `LOW → log only · MEDIUM/HIGH/CRITICAL → Telegram` (for the MVP). |
| **How to test** | `pytest` on the decision rules. |

### ⬜ Phase 6 — Telegram notifications
| | |
|---|---|
| **Goal** | Actually deliver a message to your phone. |
| **What you can do** | Receive a formatted alert with the headline, why it matters, and a link. |
| **What you'll see** | A real Telegram message during manual testing. |
| **How to test** | Mocked tests for formatting; one real manual send to confirm. |
| **Needs** | A Telegram bot token + chat ID in `.env`. |

### ⬜ Phase 7 — Scheduled end-to-end pipeline
| | |
|---|---|
| **Goal** | Tie it all together and run it **automatically**. |
| **What you can do** | Leave it running; it checks news every N minutes on its own. |
| **What you'll see** | Log summaries: `Collected 50 · Duplicates 31 · Filtered 7 · Alerts 2`. |
| **How to test** | Start the app and watch scheduled runs fire in the logs. |
| **This is the finish line** | The "it checks news by itself" behavior you originally expected. |

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
