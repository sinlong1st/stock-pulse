# StockPulse — AI Investment Committee, adapted plan

This is the build plan for `StockPulse_AI_Investment_Committee_SPEC.md`, rewritten
to fit the StockPulse that **actually exists** rather than a blank slate.

The original spec is sound on principles and over-specified on infrastructure. It
assumes a greenfield service with Postgres, Redis and a task queue, and it
re-invents several subsystems this project already ships. This plan keeps the
principles, drops the duplicate machinery, and orders the work so **every phase
is useful on its own** — you can stop after any phase and still be better off.

---

## 1. What we keep from the original spec

These are the ideas worth building, and they survive intact:

| Principle | Why it stays |
|---|---|
| Evidence before opinion, with evidence IDs | A stronger version of this project's existing "numbers are real, narrative is AI" rule |
| Evidence text is **untrusted data**, not instructions | Already the rule in `app/prediction/analyst.py`; the spec formalises it |
| **Rule engine has veto authority** | The single highest-value idea here. Deterministic, cheap, testable |
| Disagreement is a valid outcome | Honest. Forced consensus would be worse than no answer |
| Scenario ranges, never exact prices | Matches how Predict already talks |
| Independent first opinions (no anchoring) | The only way a second model adds information |
| Anonymised critique, fresh judge | Prevents self-preference and context contamination |
| **Store the evidence package** to avoid look-ahead bias (§25.7) | The most important line in the spec for honest evaluation |

## 2. What we drop, and why

| Spec asks for | Decision | Reason |
|---|---|---|
| PostgreSQL | **Drop** — keep SQLite | One container on a small droplet. SQLite handles this volume. Alembic is already wired |
| Redis + Celery/Dramatiq/RQ | **Drop** — keep APScheduler | Background work already runs on APScheduler. A queue is infrastructure to operate, not value |
| Queue-and-poll API (§19) | **Replace** with existing SSE | `/api/predict/stream` already streams stage events. §18.2's six progress states map onto it directly |
| `/api/v1/committee/...` | **Replace** with `/api/committee/...` | Match the existing unversioned convention |
| New `TechnicalEvidence` module | **Extend** `app/prediction/signals.py` | Support/resistance and trend already live there |
| New `analysis_outcomes` table | **Extend** the `predictions` table | It already has `source`, `strategy_id`, baseline price, horizon and a scoring loop |
| New evaluation framework | **Extend** `build_strategy_accuracy` | Per-strategy accuracy already exists; add a per-provider dimension |
| Separate `EvidencePackage` schema | **Grow** the existing `evidence` block | Predict already returns most of it |

**The duplication risk is the real blocker.** Building `app/committee/` exactly as
written would give two systems computing support levels, risk/reward and accuracy.
They *will* drift. Everything below reuses instead.

## 3. What's genuinely missing and must be built

- **ATR** — required by four rules (chase, stop validity, post-event move, entry-zone
  comparison). Pure arithmetic over bars we already fetch.
- **RSI / MACD / SMA / EMA** — for the evidence package. Also pure arithmetic.
- **A macro event calendar** (Fed / CPI / jobs). We only have earnings. Either find a
  source or scope those rules out of the MVP.
- **Position context** — average cost, side, stop. New storage, single-user for now.
- **Bid/ask and relative volume** — bid/ask isn't in Yahoo's chart API. Relative
  volume is derivable. Treat both as optional evidence.

---

## 4. Phases

Each phase ships something usable. Stop whenever the value stops justifying the cost.

### Phase 0 — Indicators (no LLM, no cost)

Extend `app/prediction/signals.py` with `atr14`, `rsi14`, `macd`, `sma20/50/200`,
`ema9/21`, and a `volatilityRegime` derived from ATR relative to its own history.

*Ships:* better evidence chips in Predict immediately.
*Risk:* none. Deterministic, fully unit-testable.

### Phase 1 — Rule engine over existing Predict ⭐ **start here**

Implement the deterministic vetoes from §15 against the **existing** `evidence`
block, no new schemas:

`RULE-FRESH-001` stale quote · `RULE-EARN-001` earnings proximity · `RULE-RR-001`
minimum risk/reward · `RULE-CHASE-001` excessive chase · `RULE-STOP-001` invalid
stop · `RULE-DATA-001` missing data · `RULE-VOL-001` extreme volatility ·
`RULE-MOVE-001` post-event move

The engine takes the entry assessment and may **downgrade** it (`good` → `wait`),
attaching the reason. Risk/reward is recalculated in code — never trusted from a
model.

*Ships:* the discipline half of the whole feature, for **zero extra LLM cost**.
*Why first:* it's the part most likely to change a bad decision, and it needs no
second model to work.

### Phase 2 — DeepSeek provider behind a common interface

A `LLMProvider` protocol (§20.3) with two implementations. See §6 below — this is
a small change because DeepSeek is OpenAI-compatible.

*Ships:* nothing user-visible. Keep it to one phase and move on.

### Phase 3 — Second opinion, measured ⭐ **the decision point**

Run DeepSeek **alongside** OpenAI on the same Predict evidence. Record both with
`provider` on the `predictions` row (which already carries `source` and
`strategy_id`), and extend `build_strategy_accuracy` to group by provider.

Show both verdicts in the app. No debate, no judge yet.

*Ships:* two independent reads, and — crucially — **the data to answer whether
two models beat one**, using the accuracy loop that's already accumulating.
*Why this matters:* everything after this is expensive. This phase tells you
whether it's worth it, with your own numbers rather than a hunch.

### Phase 4 — Agreement + fresh judge (Committee mode)

Only if Phase 3 shows the second opinion adds something. Implement §11 agreement
scoring and §14 fresh anonymous judge. Early-stop per §22.1 when the models agree —
that's what keeps typical cost near two calls, not seven.

**§11 agreement scoring: done** (`app/prediction/agreement.py`). Deterministic,
free, and it replaces a boolean that compared entry grades only. Two adaptations
were forced by our smaller vocabulary:

- The spec assumes continuous 0–1 confidence and triggers on a 0.25 gap. Our
  analysts emit three levels, so the gap is counted in **ordinal steps** (2 = the
  low/high extremes). Mapping three levels onto decimals to fit the threshold
  would be the false precision §3.5 rules out.
- §11.2's entry-zone and invalidation ATR comparisons are **not implemented**.
  Both models receive the same deterministically-computed levels, so there is
  nothing to compare — this only becomes real if analysts propose their own zones.

`requiresDebate` is computed and exposed but nothing consumes it yet; it is the
Phase 5 gate.

**§14 fresh judge: not started.** It is a third LLM call, so it needs a decision
first — run automatically whenever `requiresDebate` is true, or on demand only.
Per §7 it should ship behind a default-off flag either way. Worth noting that on
live runs so far, `requiresDebate` comes back **false** — the models differ in
emphasis, not direction — so a judge would rarely fire.

### Phase 5 — Cross-critique and rebuttal (Full Debate)

Only on material conflict or explicit request. §12–13.

### Phase 6 — UI

Committee tab, analyst cards, evidence drawer, debate view. Reuse the terminal
loader for progress — a full debate takes long enough that the ABORT button
finally earns its place.

---

## 5. Recommended path

**Phase 0 → 1 → 3, then decide.**

Phase 1 gives most of the risk discipline with no LLM cost. Phase 3 gives a real
answer on whether the committee premise holds. Phases 4–6 are the "investment
committee experience" — worth building if the *experience* is the product, but
worth deciding with data in hand.

**Honest expectation:** the committee will improve the *transparency and discipline*
of the output. It is unlikely to move directional accuracy much. Two models trained
on overlapping data produce correlated errors — they can agree confidently and both
be wrong. Agreement is not evidence of correctness. Build it for the reasoning
quality, and let the accuracy loop keep you honest.

---

## 6. DeepSeek integration

**Difficulty: low.** The API is OpenAI-compatible — same request shape, same
`/chat/completions` path, `Authorization: Bearer` header. The existing analysts
already post to `f"{base_url}/chat/completions"` with a configurable `base_url`,
so a provider is a config change plus a thin class.

```python
# app/config.py
deepseek_api_key: str = ""
deepseek_base_url: str = "https://api.deepseek.com"
deepseek_model: str = "deepseek-v4-flash"
```

**Two caveats:**

- **Structured Outputs (`json_schema`) is not documented for DeepSeek.** JSON mode
  (`json_object`) is. Use `json_object` plus Pydantic validation — exactly the
  pattern `BriefingResult` and `PredictionRead` already use, so no new approach.
- **Data residency.** The hosted API runs in China. Fine for public market data;
  worth a thought before any position or account details are ever sent.

### Prompt caching is a big deal here

DeepSeek's cache-hit input price is roughly **50× cheaper** than a cache miss
($0.0028 vs $0.14 per 1M). Every committee call shares the same evidence-package
prefix, so putting the evidence **first and byte-identical** across calls turns
most of the input into cache hits. Design the prompts that way from day one.

---

## 7. Cheap by default — a hard design rule

**Every model choice must be configurable, and every default must be the cheapest
option that works.** Expensive models are opt-in, never assumed. This is a
constraint on the build, not a tuning exercise afterwards.

It applies at two levels.

### Runtime: the user picks the mode

The mode selector (§5) *is* the cheap option, available on every analysis:

| Mode | Calls | Use when |
|---|---|---|
| **Quick Scan** | 1 | The default for routine checks |
| **Committee** | 3 | You actually care about this entry |
| **Full Debate** | 7 | High stakes, or the models disagree |

Quick Scan must remain a first-class mode, not a degraded fallback — most lookups
don't need a committee.

### Config: one setting per role, cheapest defaults

```bash
# Per-role models. Defaults are the cheapest that do the job.
COMMITTEE_QUICK_MODEL=deepseek-v4-flash
COMMITTEE_ANALYST_A_MODEL=deepseek-v4-flash
COMMITTEE_ANALYST_B_MODEL=gpt-4o-mini
COMMITTEE_CRITIQUE_MODEL=deepseek-v4-flash
COMMITTEE_JUDGE_MODEL=gpt-4.1-mini        # the one worth paying more for, maybe

COMMITTEE_DEFAULT_MODE=quick               # cheap unless asked otherwise
COMMITTEE_MAX_PER_DAY=20                   # hard stop, refuses beyond this
```

Rules that follow from this:

- **No model name is ever hard-coded.** Every call reads its model from config,
  the same way `BRIEFING_MODEL` and `PREDICTION_MODEL` already do.
- **Nothing silently upgrades.** A more expensive model is only ever used because
  a setting says so.
- **`COMMITTEE_MAX_PER_DAY` is enforced server-side** and returns a clear error,
  so a retry loop or an over-enthusiastic afternoon can't produce a surprise bill.
- **The cost of the run is recorded** on the analysis row (tokens per call, per
  provider), so "what did this actually cost" is answerable from data rather than
  estimated.

### The floor

Running everything on the cheapest models is a supported configuration, not a
degraded one:

| All-DeepSeek `v4-flash` | Cost |
|---|---|
| Quick Scan | ~$0.0015 |
| Committee | ~$0.006 |
| Full Debate | ~$0.015 |

At 5 analyses a day that's **under $1/month**. The expensive configurations below
are a choice, and one you can make per role after testing whether they're better.

---

## 8. Cost

Per **full debate** (7 calls: 2 analysts, 2 critiques, 2 rebuttals, 1 judge),
estimating ~80k input and ~10k output tokens in total:

| Configuration | Approx. cost per analysis |
|---|---|
| All DeepSeek `v4-flash` | **~$0.015** |
| DeepSeek + `gpt-4.1-mini`, judge on `gpt-4.1-mini` | **~$0.035** |
| DeepSeek + `gpt-4.1-mini`, judge on `gpt-4.1` | **~$0.08** |
| *Today's single-call Predict, for reference* | *~$0.002* |

**Committee mode** (early-stopped, no debate — 3 calls) costs roughly 40% of the
above. With §22.1's early stopping, most analyses should land there.

### Per mode

| Mode | Calls | Cheapest (all flash) | Mixed, mini judge | Mixed, `gpt-4.1` judge |
|---|---|---|---|---|
| Quick Scan | 1 | $0.0015 | $0.002 | — |
| Committee | 3 | $0.006 | $0.017 | $0.052 |
| Full Debate | 7 | $0.015 | $0.035 | $0.08 |

### Per month — **this is an on-demand feature**

Unlike briefings, which fire ~6×/day whether or not you read them, committee cost
is bounded by you asking for it. Assuming debate triggers on ~30% of analyses:

| Usage | Cheapest | Mixed, mini judge | Mixed, `gpt-4.1` judge |
|---|---|---|---|
| 2/day | $0.50 | $1.35 | $3.60 |
| 5/day | $1.30 | $3.40 | $9.00 |
| 10/day | $2.60 | $6.70 | $18.00 |
| 20/day | $5.20 | $13.40 | $36.00 |

For reference, current StockPulse spend is roughly **$0.30–1/month** (6 briefings
a day on `gpt-4o-mini`, plus classifier calls).

### The one place cost can run away

The original spec's §5.1 suggests Quick Scan for *"normal news alerts, watchlist
monitoring"* — which would make it **automatic**, not on-demand. The news monitor
polls every 1–2 minutes, so hooking Quick Scan to alerts could mean dozens of
calls a day with no user action.

**Decision: do not wire Quick Scan into the alert pipeline in the MVP.** Keep every
committee mode user-triggered. Revisit only with a per-day cap and a clear reason.

**Two warnings:**

1. DeepSeek's own docs state: *"We plan to raise the overall pricing for DeepSeek
   API services in the near future, with a significant increase expected."* Don't
   architect around today's price being permanent.
2. **Latency is the real cost.** Seven mostly-sequential calls means **60–120
   seconds** versus ~8s today. Analysts run concurrently; critique and rebuttal
   can too. The judge cannot.

*Prices checked 2026-08-07 against the providers' own pricing pages; both move.*

---

## 9. Reuse map

What each part of the spec maps onto, so nothing gets built twice:

| Spec component | Existing code to extend |
|---|---|
| `TechnicalEvidence` | `app/prediction/signals.py` |
| `QuoteEvidence`, `PriceHistoryEvidence` | `app/prices.py`, `signals.fetch_bars` |
| `EventEvidence` (earnings) | `app/earnings.py` |
| `NewsEvidence` | `app/briefing/retrieval.py` |
| `CurrentPriceAssessment`, `TradeSetup` | the `entry` + `evidence` blocks in `app/prediction/service.py` |
| `StrategyProfile` | `app/prediction/store.py` custom strategies |
| Rule engine risk/reward | `_evidence()` in `app/prediction/service.py` |
| `analysis_outcomes`, evaluation | `predictions` table + `app/evaluation.py` |
| Progress states (§18.2) | `app/api/stream.py` SSE stages |
| Prompt/schema versioning (§26) | new — add alongside `strategy_id` on predictions |

---

## 9. Open questions

1. **Macro event calendar** — build, buy, or scope the Fed/CPI/jobs rules out of MVP?
2. **Position context** — worth building single-user, or wait for accounts?
3. **Committee vs Predict** — one feature with a "deep analysis" mode, or two
   separate tabs? One feature avoids explaining to yourself why there are two
   places to analyse a stock.
4. **Judge model** — a stronger judge is where most of the cost sits. Test whether
   `gpt-4.1-mini` judges as well as `gpt-4.1` before committing to the expensive one.
