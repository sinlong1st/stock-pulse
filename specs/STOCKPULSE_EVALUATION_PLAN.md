# StockPulse — Quiet Hours, Price Confirmation & Self-Evaluation Plan

**Status:** proposal / design only. No code yet. This document plans three
related enhancements and the order to build them. Nothing here changes the
existing pipeline until we agree on it.

---

## 1. Why

StockPulse can already detect and alert. The next leap is **trust**:

1. **Quiet hours** — don't wake the user at 3am for non-critical news.
2. **Price confirmation** — cross-check news against real price movement
   (using Alpaca, whose keys are already in `.env`).
3. **Self-evaluation** — measure whether the AI's bullish/bearish calls
   actually line up with what prices did afterward, and summarize *"are we
   doing this correctly?"*

These build on each other: price data (2) is the input the evaluation
loop (3) needs. Quiet hours (1) is independent and small, so it goes first.

---

## 2. Feature 1 — Quiet Hours

### Goal
Suppress non-urgent alerts during the user's sleeping hours; deliver them
later instead of dropping them.

### Behavior
- Config a daily quiet window in the **user's local timezone** (they're in
  Vietnam; the US market timezone is a separate concern handled in
  Feature 3).
- During the window, alerts below a threshold are **held** (kept `PENDING`),
  not discarded. They are delivered on the first send after the window ends.
- `CRITICAL` alerts always bypass quiet hours.

This fits the existing model cleanly: alerts are already `PENDING` until the
delivery step sends them. Quiet hours just makes the sender **skip
non-critical sends while the window is open** — they naturally flush later.

### Config (proposed)
```
QUIET_HOURS_ENABLED=true
QUIET_HOURS_START=22:00        # local time
QUIET_HOURS_END=07:00          # may cross midnight
TIMEZONE=Asia/Ho_Chi_Minh      # app-wide local timezone (also used by the digest)
QUIET_HOURS_MIN_IMPORTANCE=CRITICAL   # this level and above always sends
```

### Where it lives
A small helper (`app/alerts/quiet_hours.py`) with `is_quiet_now(settings)`
and a check in the delivery router (`send_pending_alerts`): skip an alert if
`is_quiet_now()` and its importance is below `QUIET_HOURS_MIN_IMPORTANCE`.

### Edge cases
- Window crossing midnight (22:00–07:00) — handle with a simple range check.
- Timezone via `zoneinfo` (`TIMEZONE` — one app-wide setting).
- Held alerts must not be marked `FAILED`; they simply stay `PENDING`.

### Effort: small (½ day). Independent of the other two.

---

## 3. Feature 2 — Alpaca Price Integration

### Goal
Fetch real price data for watchlist tickers so we can (a) add price context
to alerts and (b) feed the evaluation loop.

### Provider
Alpaca Market Data API v2 (`https://data.alpaca.markets/v2`), authenticated
with `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (already present). Free tier uses
the IEX feed (may be ~15 min delayed) — fine for movement checks, not for
trading.

### Interface (isolated, like the classifier/notifier)
```python
class PriceClient(ABC):
    async def latest_price(self, ticker: str) -> float | None: ...
    async def change_since(self, ticker: str, since: datetime) -> PriceMove | None: ...
    async def bars(self, ticker: str, start, end) -> list[Bar]: ...

@dataclass
class PriceMove:
    ticker: str
    start_price: float
    end_price: float
    return_pct: float
    start_at: datetime
    end_at: datetime
```
An `AlpacaPriceClient` implements it with httpx (injectable transport for
tests, same pattern as the RSS collector and Telegram notifier).

### Immediate use: price context in alerts (optional)
When a classified article has watchlist tickers, optionally attach today's
move, e.g. append to the alert:
```
Price: NVDA +2.1% today
```
Config: `PRICE_CONTEXT_IN_ALERTS=true|false`.

### Config (proposed)
```
ALPACA_API_KEY=...          # already present
ALPACA_SECRET_KEY=...        # already present
ALPACA_DATA_URL=https://data.alpaca.markets/v2
PRICE_FEATURES_ENABLED=true
PRICE_CONTEXT_IN_ALERTS=false
```

### Gotchas to handle
- **Not every symbol has data**: `SPCX` (SpaceX) is private, ETFs are fine.
  Missing data → skip gracefully, never crash a run.
- **Market hours**: prices only move 9:30–16:00 ET on trading days. Movement
  windows must be measured in *market time*, not wall-clock. Use a simple US
  market-hours check (or Alpaca's calendar endpoint) so an overnight gap
  isn't mistaken for "no movement".
- **Rate limits / cost**: free tier is rate-limited; cache latest prices per
  run and only query tickers we actually need.

### Effort: medium (1–2 days).

---

## 4. Feature 3 — Self-Evaluation Loop

### The core question
> When the AI says a piece of news is **bullish** (or **bearish**) for a
> stock, does the price actually move that way afterward — and how often?

We turn each classification into a **prediction**, wait a defined horizon,
then compare the prediction to the real price move and score it.

### Concept
```
Article → AI classification (sentiment: BULLISH/BEARISH/NEUTRAL, tickers)
        → record a prediction per ticker, with baseline price at t0
        → wait a horizon (e.g. next market hour, next market close)
        → fetch price at t1, compute return
        → score: did the move match the predicted direction?
        → aggregate into an accuracy report
```

### New data: `predictions` table
One row per (classification, ticker), because a classification can name
several tickers.
```python
class Prediction:
    id: int
    classification_id: int      # FK
    article_id: int             # denormalized for convenience
    ticker: str
    sentiment: str              # BULLISH / BEARISH / NEUTRAL
    importance: str
    created_at: datetime        # t0 (prediction time)
    baseline_price: float | None
    baseline_at: datetime | None
    horizon: str                # e.g. "1h", "1d"
    evaluate_after: datetime     # when it becomes due
    status: str                 # PENDING_BASELINE / PENDING_EVAL / EVALUATED / SKIPPED
    price_at_horizon: float | None
    return_pct: float | None
    outcome: str | None         # HIT / MISS / FLAT
    evaluated_at: datetime | None
```

We can support **multiple horizons per prediction** (e.g. 1h and 1d) either
as separate rows or separate columns; separate rows is simpler to aggregate.

### Scoring rule (proposed, configurable thresholds)
Let `move_threshold = 0.3%` (a stock is "up" if return ≥ +0.3%, "down" if
≤ −0.3%, else "flat").

| Prediction | Price move | Outcome |
|---|---|---|
| BULLISH | up | HIT |
| BULLISH | down | MISS |
| BEARISH | down | HIT |
| BEARISH | up | MISS |
| NEUTRAL | flat | HIT |
| NEUTRAL | up/down | MISS |
| any | flat (for bull/bear) | FLAT (neither hit nor miss) |

`FLAT` is tracked separately so a directional call that "didn't move much"
doesn't unfairly count as wrong.

### Two scheduled jobs (or one job, two stages)
1. **Baseline capture** — shortly after a prediction is created, record the
   ticker's price at t0 (`PENDING_BASELINE → PENDING_EVAL`). If the market is
   closed, baseline = last close and horizons measured in market time.
2. **Evaluation** — for predictions whose `evaluate_after` has passed, fetch
   `price_at_horizon`, compute `return_pct`, set `outcome`, mark `EVALUATED`.

### The summary — "are we doing this correctly?"
A periodic report (daily and/or on demand) aggregating `EVALUATED`
predictions:
- **Directional accuracy** = HITs / (HITs + MISSes), overall and split by
  BULLISH vs BEARISH.
- **Accuracy by importance** — do HIGH/CRITICAL calls move more/right?
- **Average return following bullish vs bearish** news (does bullish news
  actually precede positive returns on average?).
- **Sample size** and date range (so small-sample results are flagged).
- Optional: best/worst tickers, calibration by confidence.

Delivered as:
- A new **`/evaluation` page** (like `/alerts`) with the numbers, and/or
- A **daily Telegram digest**: e.g. *"Last 7 days: 24 evaluated · bullish
  61% hit · bearish 55% hit · avg +0.8% after bullish."*

### Config (proposed)
```
EVALUATION_ENABLED=true
EVALUATION_HORIZONS=1h,1d          # market-time horizons
EVALUATION_MOVE_THRESHOLD_PCT=0.3
EVALUATION_DIGEST_ENABLED=false    # daily Telegram summary (hour is in TIMEZONE)
EVALUATION_DIGEST_ENABLED=false    # daily Telegram summary
```

### Effort: large (the headline feature; several days). Depends on Feature 2.

---

## 5. Honest caveats (must be stated in the UI/report)

- **Correlation, not causation.** A stock moving after bullish news doesn't
  prove the news caused it. Short horizons are dominated by market noise.
- **Small samples lie.** Early accuracy numbers will swing wildly; the report
  must always show sample size and a "not enough data yet" state.
- **This is not trading advice** and not a backtest of a strategy — it's a
  quality check on the *classifier*, to help tune prompts/thresholds.
- **Free data limits.** IEX feed may be delayed and misses some venues;
  treat prices as approximate.
- **Survivorship / selection.** We only evaluate what we alerted/classified,
  which is already a filtered set.

## 6. Non-goals (for now)
- Automated trading or order placement.
- Intraday tick precision / options / crypto price eval.
- Re-training a model. We *tune* prompts and thresholds from the findings; we
  don't train anything.

---

## 7. Suggested build order — ✅ all shipped

| Step | Feature | Status |
|---|---|---|
| A | Quiet hours | ✅ done |
| B | Alpaca price client + (optional) price-in-alerts | ✅ done |
| C | Prediction recording + baseline capture | ✅ done |
| D | Evaluation job + scoring (tolerance band + bad-data guard) | ✅ done |
| E | `/evaluation` dashboard + daily Telegram digest | ✅ done |

Decisions made along the way: tolerance band default **±0.5%**; horizons via
`EVALUATION_HORIZONS` (default `1d`); implausible moves (> `EVALUATION_MAX_MOVE_PCT`,
default 40%) are skipped as bad free-feed data; the dashboard and digest are
localized by `OUTPUT_LANGUAGE`.

Note: start **C** as early as possible even before the report exists —
accuracy stats are only meaningful after days/weeks of collected data, so the
sooner predictions start recording, the sooner the summary is useful.

---

## 8. Open questions (for you)

1. **Quiet window**: what local hours? (e.g. 22:00–07:00 Vietnam time?)
2. **Horizons**: evaluate at 1 market hour and 1 market day? Add "next
   earnings"/longer? (Longer = more meaningful but slower feedback.)
3. **Move threshold**: is ±0.3% a reasonable "flat" band, or per-ticker
   volatility-adjusted later?
4. **Summary delivery**: `/evaluation` web page, daily Telegram digest, or
   both?
5. **Scope of predictions**: evaluate every classified watchlist ticker, or
   only ones that triggered an alert?
```
