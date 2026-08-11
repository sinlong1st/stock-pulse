# StockPulse — Position Exit Advisor, adapted plan

This is the build plan for `STOCKPULSE_POSITION_EXIT_ADVISOR_SPEC.md`, rewritten to
fit the StockPulse that **actually exists**.

The spec is excellent on product thinking — §3.2 (judge the hold from the *current
price* forward, not from cost basis), §3.3 (no forced binary), §3.5 (no false
precision) are the right principles and they survive intact. It is over-specified on
infrastructure in the same way the committee spec was: six database tables, an
evidence-ID citation system, and a fresh set of service classes for market data,
technicals and support/resistance that this project already ships.

**The duplication risk is the whole story.** Building `ExitAdvisorService`,
`TechnicalAnalysisService` and `SupportResistanceService` as written would give two
systems computing ATR, support levels and risk/reward. They *will* drift, and then
Predict and Exit will disagree about where support is on the same stock on the same
day — which destroys trust in both. Everything below reuses instead.

---

## 1. Decisions taken (2026-08-10)

| Question | Decision |
|---|---|
| Where it lives in the app | **Mode toggle inside Predict** — a `Segmented` "BUY? / I OWN IT" at the top of the Predict screen |
| Evidence scope for MVP | **Core + broad market** — position math, levels, indicators, earnings, news, SPY/VIX. No peers, sector, macro, or fundamentals |
| Positions | **Saved** — a JSON store like `app/prediction/store.py`, so you don't retype shares and average cost every session |

## 2. What we keep from the spec

| Principle | Why it stays |
|---|---|
| **Incremental risk/reward from the current price** (§3.2, §6) | The single most valuable idea in the document. Judging a hold from cost basis is the mistake every retail tool makes |
| **Profit giveback in dollars** (§7) | "-$440 back to support" lands where "-4.6% to support" doesn't. Same reason the entry-evidence card works |
| No forced binary (§3.3), partial selling first-class (§3.4, §8) | The honest answer is usually "trim some". A hold/sell toggle would be a worse product |
| No false precision — zones, not price targets (§3.5) | Already how Predict talks |
| All arithmetic in code, never the LLM (§5) | This project's existing hard rule: **numbers are real, narrative is AI** |
| Deterministic rule engine with veto authority (§28) | Ported straight from `app/prediction/rules.py`, which already proved the pattern |
| Evidence text is untrusted data, not instructions (§40) | Already enforced by `_GUARDRAILS` in `app/prediction/analyst.py` |
| Store the evidence snapshot for honest later scoring (§38) | Prevents look-ahead bias when the outcomes are graded |

## 3. What we drop, and why

| Spec asks for | Decision | Reason |
|---|---|---|
| Evidence IDs on every claim (§9) | **Drop** | Real work, and the app renders no citations anywhere. The existing "authoritative numbers in the prompt, AI writes only narrative" already prevents the fabrication it guards against |
| Six new tables (§42) | **Collapse to one** + reuse | `position_exit_analyses` (with the evidence snapshot as JSON on the row). Outcomes reuse the `predictions` table, which already carries `source`, baseline price and a scoring loop |
| `TechnicalAnalysisService`, `SupportResistanceService`, `MarketDataService`, `HistoricalPriceService`, `EarningsService`, `NewsService` (§34) | **Drop — reuse** | All six already exist. See the reuse map in §5 |
| Sector + peer analysis (§16), `SectorService`, `PeerComparisonService` | **Defer** | No peer-mapping source exists. An AI-guessed peer list can be plainly wrong, and a wrong peer comparison is worse than none |
| Macro event calendar (§18), `MacroService` | **Defer** | No source at all. Highest cost, lowest MVP value |
| Fundamentals / valuation (§19) | **Blocked** | Yahoo's chart endpoint is price/volume only — the same wall that blocks the deferred revenue chart |
| `POST /api/v1/positions/exit-advisor` | **Unversion** → `/api/positions/exit-advisor` | Matches every other route in `app/main.py` |
| Committee integration (§36, Phase 8) | **Defer** | Consistent with the committee plan's "decide with data" stance. `requiresDebate` has come back false on every live run so far |
| Queue/poll, brokerage execution | **Never** | SSE already exists; execution is explicitly out of scope in MVP per the spec itself |

Note that §46's own **Definition of Done** never mentions peers, sector, macro or
fundamentals. The MVP below satisfies §46 in full.

## 4. What is genuinely new

Everything here is the *position layer* — mostly pure arithmetic, which is the cheap
and testable kind of work:

- Position math (§5): cost basis, value, unrealized P&L, giveback, remaining P&L.
- Hold reward/risk **in dollars and per share** (§6) — related to the existing
  percentage `rewardRisk` but not the same number, and it must not be conflated.
- Partial-sell calculator (§8): 25/33/50/75/custom.
- Bull/base/bear scenarios (§20) with code-computed dollar ranges.
- Exit rule engine (§28) — new rules, existing mechanism.
- Saved positions store + CRUD.
- Broad market context (SPY / VIX) — ~40 lines on top of `fetch_bars` and `_trend`.
- The UI.

## 5. Reuse map

Nothing in this column gets rebuilt.

| Need | Already in the repo |
|---|---|
| Daily OHLCV bars | `app/prediction/signals.py::fetch_bars` |
| Current price + freshness | `app/prices.py::maybe_briefing_price_client`, `price_freshness` |
| Symbol resolution (typo-tolerant, AI fallback) | `app/commands/symbols.py::resolve_symbol_smart` via `service._resolve` |
| RSI / MACD / ATR / SMA / EMA / volatility regime | `app/prediction/indicators.py::compute_indicators` |
| Support levels, nearest resistance (swing pivots) | `app/prediction/signals.py::support_levels`, `nearest_resistance` |
| Range position, trend, discount | `app/prediction/signals.py::compute_signals` |
| Earnings date + EPS beat/miss | `app/earnings.py::fetch_many` |
| Fresh company news | `app/briefing/retrieval.py::retrieve_fresh_news` + `build_focus_collectors` |
| LLM call, strict schema, repair retry, token/latency capture | `app/llm.py::ChatProvider.complete_model` |
| Provider choice + second opinion + agreement | `app/prediction/mode.py`, `agreement.py` |
| Prompt guardrails + injection defense pattern | `app/prediction/analyst.py::_GUARDRAILS` |
| Rule engine (cap-only downgrades, structured findings) | `app/prediction/rules.py` |
| SSE with stage progress | `app/api/stream.py::sse_events`, `mobile/src/data/sse.ts` |
| Recording reads for later scoring | `app/evaluation.py::record_prediction_read`, `predictions.source` |
| Charts, segmented control, loader, i18n | `PriceChart`, `MiniBars`, `Segmented`, `HackerLoader`, `mobile/src/i18n/` |

---

## 6. Architecture

```
app/position/
  math.py       # §5-§8, §20 dollars. Decimal. No I/O, no AI.
  store.py      # saved positions (JSON), modeled on prediction/store.py
  advisor.py    # the exit analyst: prompt + ExitRead schema
  rules.py      # §28 exit rule engine
  service.py    # build_exit_advice() — orchestration

app/prediction/
  evidence.py   # NEW: extracted shared gather step (see Phase 2)
  market.py     # NEW: SPY/VIX broad-market context
```

### The shared evidence step

`build_prediction` currently does: resolve → bars → price → signals → support →
indicators → earnings → news → analyst. **The first seven steps are exactly what the
exit advisor needs.** Phase 2 extracts them into `app/prediction/evidence.py`:

```python
@dataclass
class Evidence:
    ticker: str; name: str
    bars: list[Bar]; price: float | None; freshness: str | None
    signals: Signals; support: dict; resistance: float | None
    indicators: Indicators; earnings: object | None
    news: list[str]; series: dict

async def gather(query, settings, *, progress=None) -> Evidence | None
```

Both `build_prediction` and `build_exit_advice` call it. This is the single most
important structural decision in the plan — it is what stops the two features from
drifting apart on the same stock.

### Money type

`app/position/math.py` uses **`Decimal`** internally and converts to `float` at the
payload boundary. The spec asks for it (§8), the module is self-contained arithmetic
over user-entered dollar amounts, and it costs nothing. The rest of the codebase
stays on `float` — do not spread `Decimal` into `signals.py` or `indicators.py`,
where the inputs are already floats from Yahoo.

### Scenarios stay grounded

§20 lets the AI produce price ranges. Left unconstrained, that reintroduces exactly
the invented levels §3.5 forbids. So:

1. **Code** proposes candidate levels from real swing structure (near supports, the
   nearest resistance, the level above it, the window floor).
2. **AI** picks which levels bound each of bull/base/bear and assigns probabilities.
3. **Code** normalizes probabilities to 100 and computes every dollar figure.

The AI never emits a price. It selects from levels that came from real price action.

### The asymmetry, restated for exits

`app/prediction/rules.py` only ever moves advice toward *not buying*. The exit
mirror is: **rules only ever move the recommendation toward lower exposure** — hold →
hold-with-stop → partial-sell → reduce → exit. A rule may never talk you into holding
more. RULE-EXIT-010 (a valid breakout shouldn't trigger a sell just because RSI is
high) is therefore implemented as a **suppressor** of RULE-EXIT-009, not as an
upgrade — same shape as the `high-volatility` guard reading the *original*
assessment, so firing order can't change the outcome.

---

## 7. Phases

Each phase is useful on its own. **Phase 4 is the natural stopping point for a first
useful ship** — see the note there.

### Phase 1 — Position math ⭐ start here

`app/position/math.py`, pure `Decimal` arithmetic, no I/O and no AI. Implements §5.1–5.9,
§6, §8, §20 dollar ranges, §31 cost-basis recovery. Full unit tests including the
below-cost case (§ RULE-EXIT-011) and the divide-by-zero guards (giveback % is only
defined when unrealized P&L > 0; hold R/R is undefined when support ≥ current price).

*Ships:* nothing user-visible. It is the spec's own recommended first step (§47) and
everything else depends on it.

### Phase 2 — Shared evidence + market context

Extract `app/prediction/evidence.py` from `build_prediction` with **no behavior
change** — the 558 existing tests must pass untouched. Then add
`app/prediction/market.py`: SPY and ^VIX via `fetch_bars`, trend via the existing
`_trend`, plus the stock's relative strength versus SPY over 5/20 days.

*Ships:* market context could be surfaced in Predict too, but don't — keep the diff
honest and land it with the exit feature.
*Risk:* this is the one refactor of well-tested working code in the plan. Extract
first, verify tests green, commit separately from anything new.

### Phase 3 — Saved positions

`app/position/store.py` (JSON, `POSITIONS_FILE`, redirected to `/app/data` in Docker,
same pattern as strategies) + `GET/POST/PUT/DELETE /api/positions`. Delete is an
**archive**, never a hard delete, so past analyses stay attributable — the same
decision the strategies store made and for the same reason.

### Phase 4 — Numbers-only exit view ⭐ useful without any AI

Wire Phase 1 + Phase 2 + Phase 3 into `build_exit_advice` with **no LLM call yet**,
and render it: position summary, hold-vs-sell card (lock now / additional upside to
resistance / giveback to support / hold R/R), partial-sell calculator, technical card.

*Ships:* a genuinely useful screen for **zero LLM cost**. §30's regret-minimization
display is entirely arithmetic. If the AI narrative later turns out to add little,
this is the feature.

### Phase 5 — Exit analyst

`app/position/advisor.py`: the §25 system prompt over the shared `_GUARDRAILS`
pattern, an `ExitRead` Pydantic schema (§22: action, confidence, thesis,
recommendedPlan, three alternatives, reasonsToHold/Sell, decisionTriggers, warnings,
scenario level-picks + probabilities), validated through `ChatProvider.complete_model`.
Reuses the existing mode picker, so `both` gives a second opinion and `agreement.py`
scores it for free.

Prompt must explicitly carry §26's thirteen questions and the §3.1 framing that the
user **already owns this** — the failure mode here is the model quietly answering
"is this a good stock?" instead.

### Phase 6 — Exit rule engine

`app/position/rules.py`, mechanism copied from `prediction/rules.py`, ordered on an
exposure ladder instead of a caution ladder:

`RULE-EXIT-001` stale quote during market hours · `002/003` shares & average cost > 0
(request validation) · `004` stop below current price · `005` earnings inside the
window · `006` poor incremental hold R/R → bias partial, never force full exit ·
`007` primary support broken · `008` trend deterioration (price < SMA20/EMA21,
MACD histogram negative) · `009` extreme extension (ATRs above SMA20, elevated RSI,
near resistance) · `010` valid-breakout suppressor for 009 · `011` below cost — never
call it "profit-taking" · `012` partial-sell bounds.

Findings stay structured (`code` + `params`), never English — the app phrases them.

### Phase 7 — UI

`Segmented` toggle on `PredictScreen`. That screen is already 649 lines, so the
position mode goes into components, not inline: `PositionInput`, `HoldVsSell`,
`PartialSellCalculator`, `ScenarioCards`, `ExitPlans`. All new strings into
`mobile/src/i18n/strings.ts` (en + vi).

**One required change to `mobile/src/data/sse.ts`:** it is GET-only
(`xhr.open('GET', ...)` at line 113). The exit request has eight fields, so teach it
an optional `{ method, body }` — about six lines, JS-only, OTA-safe — rather than
cramming a position into query params. Add `EXIT_STAGES` mirroring `PREDICT_STAGES`,
and keep it in sync with the copy in `api.ts`, which the loader indexes off.

### Phase 8 — History and outcomes

Analysis history (§37) is cheap and worth having: the thesis evolving across
`Aug 5 HOLD @ $455 → Aug 10 PARTIAL SELL @ $492` is the feature's own credibility.

Outcome scoring (§38) is **not** cheap, see the open question below.

### Phase 9 — Committee (deferred)

Only if per-provider accuracy shows the second opinion earns its latency.

---

## 8. Cost

One LLM call per analysis — same order as Predict (~$0.0003 OpenAI, ~$0.0004
DeepSeek, ~$0.0007 for `both`). It is on-demand and user-initiated. **Do not wire it
into the alert pipeline**, the same standing rule as Quick Scan: that is the one path
where cost runs away.

New config for `app/config.py` + `.env.example`:

```
POSITION_EXIT_ENABLED=true
POSITIONS_FILE=positions.json
POSITION_EXIT_MIN_HOLD_RR=1.0      # §6: below this, bias toward trimming
POSITION_EXIT_EARNINGS_DAYS=3      # §28 RULE-EXIT-005 window
```

## 9. Open questions

1. **How are exit recommendations scored?** The `predictions` table maps a read onto
   `sentiment` (BULLISH/BEARISH/NEUTRAL), and hold→bullish / exit→bearish /
   partial→neutral is lossy. §38's real metrics — target hit before support break,
   max favorable/adverse excursion, immediate-sell vs hold return — need their own
   scorer over the stored evidence snapshot. **Recommendation:** don't force it into
   the existing loop in Phase 8; design it separately once there are real analyses to
   score, and keep `build_evaluation_report` scoped away from `source='exit'` so the
   existing accuracy numbers can't shift (the same guard that protects them from
   Predict reads today).
2. **Does a stale saved position mislead?** If you sell WDC and never update the
   store, the app keeps advising on a position you don't hold. A "last confirmed"
   date on the row, or a prompt to confirm before analyzing, probably earns its keep.
3. **Is `both` mode the right default here?** It is for Predict, because paired
   samples are the only way to compare models. For an exit decision the added ~20s
   latency may not be worth it. Start with the saved Predict mode, revisit after use.
