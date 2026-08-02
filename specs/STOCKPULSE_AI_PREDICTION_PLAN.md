# StockPulse — AI Prediction Plan

**Status:** proposal / design only. No code yet. A **forward-looking** feature:
for a given stock, the AI gives a multi-horizon read — **bounce vs dip** over
1 week / 1 month / 3 months — plus a **"good discount?"** signal, synthesized
from recent news + price trend + where the price sits in its range.

> ⚠️ **Framing is everything here.** This is the AI's *reasoned opinion*, not a
> forecast model and **not investment advice**. It's speculative by nature.
> Every surface must say so, plainly. The honest hook is the self-evaluation tie
> (§8): we don't just predict — we **grade our own predictions over time**.

> 💡 **Scale-up baked in:** the AI's reasoning runs on a **strategy** (§5) — our
> default is visible for transparency, and users can later bring their **own
> strategy in plain language**, with **per-strategy accuracy** to see if theirs
> beats ours. Designed in from day one; custom input ships in the Pro era.

---

## 1. Why (and how it differs from Evaluation)

Two sides of the same coin, and easy to confuse:

| | **Evaluation** (shipped) | **AI Prediction** (this) |
|---|---|---|
| Direction | **Backward** — scores past alert calls | **Forward** — a lean on the future |
| Question | "How accurate *have* we been?" | "What might happen next, and is it cheap?" |
| Trigger | automatic (scheduled scoring) | on-demand (you ask about a stock) |

They live in the same **AI area** of the app (the Report tab — which already
hosts the 🎯 accuracy screen). Prediction is the natural companion.

---

## 2. What the user gets (output shape)

Per stock, on demand:

```jsonc
{
  "ticker": "WDC", "name": "Western Digital",
  "price": "65.20", "priceFresh": "as of Fri 13:00 PDT",
  "discount": {                 // grounded in real price data, NOT valuation
    "level": "cheap|fair|rich", // where price sits in its recent range
    "vsRangeNote": "12% above the 3-month low, 22% below the high",
    "note": "Near the lower third of its 3-month range."
  },
  "trend": "up|down|sideways",  // from a moving-average slope
  "horizons": [
    { "horizon": "1w",  "lean": "bounce|dip|hold", "confidence": "low|med|high",
      "rationale": "one plain sentence" },
    { "horizon": "1mo", "lean": "...", "confidence": "...", "rationale": "..." },
    { "horizon": "3mo", "lean": "...", "confidence": "...", "rationale": "..." }
  ],
  "drivers": ["short bullets: the news + trend factors behind the read"],
  "strategy": { "id": "default", "name": "StockPulse Balanced" },  // which lens made this read (§5)
  "generatedAt": "…", "disclaimer": "AI opinion — not investment advice."
}
```

**Design rule:** the **numbers are real, the narrative is the AI.** The `discount`
and `trend` come from *actual price history* (deterministic); the LLM writes the
per-horizon lean + rationale on top. This keeps the hard facts out of the model's
imagination.

---

## 3. Inputs

1. **Recent news** for the stock — reuse the briefing's focus retrieval
   (`app/briefing/focus.py` + `retrieve_fresh_news`) so it pulls the same fresh,
   timestamped headlines the `/report WDC` flow uses.
2. **Price history / trend** — *new*: a bars fetch (Yahoo v8 chart, already used
   for snapshots) over ~3–6 months to compute: current vs range (the "discount"),
   and a short-vs-long moving-average slope (the "trend").
3. **Current price + freshness** — the existing `snapshot()`.

---

## 4. How it's produced

- **Deterministic layer** (`app/prediction/signals.py`, new): from the bars,
  compute `discount.level` (price position in the N-month range), `trend`
  (MA slope), and the range notes. No AI — just math on real prices.
- **AI layer** (`app/prediction/analyst.py`, new): an OpenAI call given the news
  digest + the computed signals, asked for a **strict JSON**: per-horizon
  `lean` + `confidence` + one-sentence `rationale`, and the `drivers`. Validated
  into a Pydantic model, exactly like `ClassificationResult` / `BriefingResult`
  (raw output never trusted).
- **Assembler** (`build_prediction`): merges the deterministic signals + the AI
  read into the §2 shape.

The AI layer's prompt is **layered** (§5) so the reasoning framework is swappable
without touching the guardrails or the real numbers.

---

## 5. Strategies — the customizable framework (the scale-up)

A **strategy** is the natural-language framework that shapes *how the AI
interprets* the real signals + news into a lean. Our built-in one is just the
**default strategy**; users can view it, and (later, Pro) write their own.

### The prompt is layered — only the middle is user-editable
```
[ GUARDRAILS ]   ← output JSON schema · "not advice" · safety · "facts are fixed"  (ours, always wins)
[ STRATEGY ]     ← default (ours) OR the user's text: how to weigh news/trend/discount/horizons
[ SIGNALS+NEWS ] ← the real numbers (discount, trend, range) + fresh headlines     (deterministic, fixed)
→ validated JSON: lean + rationale
```
The strategy **only influences interpretation/weighting** — never the output
format, the disclaimers, or the real numbers. That boundary is the safety model
(§11.8).

### Two kinds of strategy
- **Default (ships in v1, free):** our balanced framework, stored as a constant.
  **Visible** to the user in a *"How this reads the stock"* detail modal — the
  transparency that builds trust.
- **Custom (Pro, multi-user era):** the user writes their own strategy in plain
  language, e.g.
  - *value:* "Quality names 20%+ off their high where the bad news looks
    temporary; ignore short-term momentum."
  - *momentum:* "Ride strong uptrends; avoid falling knives even if 'cheap.'"

  Same real data, a different lens → a different read.

### Per-strategy accuracy — the killer metric
Every prediction is **tagged with the strategy that made it** and fed into the
self-evaluation loop (§8). So the Accuracy screen can show
**"Your strategy 68% · StockPulse default 61%"** — users see whether *their*
framework actually beats ours, over real trading outcomes. It's novel, sticky,
and it makes the whole feature self-justifying.

### Data model
A `Strategy` = `{ id, name, body (natural language), builtin: bool }`. The default
is a constant; custom strategies are **per-user** data, so they lean on the
multi-user / sign-in foundation — which is why *custom input* ships in that era.
But we **design `strategy_id` into the analyst call + the recorded predictions
from day one**, so the upgrade is drop-in.

### Phasing
- **v1 (with the base feature):** default strategy only, shown in the modal; the
  analyst prompt is already layered and `strategy_id` is recorded on predictions.
- **v2 (Pro / multi-user):** create/edit custom strategies · per-strategy accuracy
  · maybe a small preset library (value / momentum / dividend).

---

## 6. Where it lives (app + API)

- **API:** `GET /api/predict?q=<ticker-or-name>` (token-guarded, like the other
  mobile endpoints). Resolves the name→ticker (reuse `resolve_focus` /
  `resolve_symbol`), fetches news + bars, runs the analyst, returns JSON.
  One OpenAI call per request → **on-demand only** (a button), optionally cached
  per ticker for a few hours.
- **App:** a **Predict** entry in the AI area — e.g. a screen reached from the
  Report tab (or a second segment there). Input a ticker → loading → the card:
  discount badge, trend, the three horizon rows (bounce ▲ / dip ▼ / hold →), the
  drivers, and the disclaimer. Same visual language as the rest (sentiment
  colors, freshness labels).

---

## 7. Cost & gating

- Each prediction = **1 OpenAI call + a bars fetch**. On-demand only; no
  automatic runs. Consider a short per-ticker cache and a per-day cap.
- Fits the future tiering (Pro-only, or N/day free) from the mobile plan.
  Custom strategies (§5) are a natural **Pro** unlock; the default is free.

---

## 8. The elegant part — predictions feed self-evaluation

A prediction already *is* a directional call with horizons. So we **record it
into the existing prediction/evaluation loop** (`record_predictions`-style) with
horizons `1w / 1mo / 3mo`, a baseline price, **and the `strategy_id`** that made
it. Then the **shipped evaluation scorer** grades it later (now market-closed-
aware, see the eval plan), and the **Accuracy screen shows how good the AI's
*predictions* have been** — overall and **per strategy** (§5). The app predicts
*and* keeps itself honest. (Caveat: 1–3 month horizons mean accuracy builds
slowly — that's fine, it's real.)

---

## 9. Config (proposed)

```
PREDICTION_ENABLED=false
PREDICTION_HORIZONS=1w,1mo,3mo
PREDICTION_MODEL=gpt-4o-mini
PREDICTION_RANGE_MONTHS=3          # window for the discount/trend signals
PREDICTION_CACHE_MINUTES=180       # reuse a recent read for the same ticker
```

---

## 10. Suggested build order

**v1 — the feature + the default strategy (visible, swappable):**

| Step | Piece | Status |
|---|---|---|
| A | Bars/price-history fetch (Yahoo v8) + `signals.py` (discount + trend), tested | ⬜ |
| B | `analyst.py` — **layered prompt** (guardrails + strategy block + signals) → validated JSON; default strategy as a constant | ⬜ |
| C | `build_prediction` assembler + `GET /api/predict` endpoint (name→ticker, news + signals + analyst) + tests | ⬜ |
| D | Mobile **Predict** screen in the AI area + a **"How this reads the stock"** modal showing the default strategy | ⬜ |
| E | Record predictions into the eval loop with `strategy_id` (1w/1mo/3mo) → accuracy over time | ⬜ |
| F | Cache + per-day cap | ⬜ |

**v2 — custom strategies (Pro / multi-user era):**

| Step | Piece | Status |
|---|---|---|
| G | Per-user strategy store (create/edit natural-language strategies) + safety sandbox (§11.8) | ⬜ |
| H | Strategy picker on the Predict screen; use the chosen strategy in the analyst call | ⬜ |
| I | **Per-strategy accuracy** on the Evaluation screen ("yours vs default") | ⬜ |
| J | Preset library (value / momentum / dividend) | ⬜ |

Build A–B pure/deterministic-first (testable offline), then wire the endpoint.
The layering (B) and `strategy_id` (E) are the day-one hooks that make v2 drop-in.

---

## 11. Risks & open questions

1. **"Prediction" invites over-trust.** Lead with "the AI's read, not a
   forecast." Keep confidence honest (mostly "low/med"); never imply certainty.
   App Store reviews scrutinize market-prediction apps — the disclaimer + framing
   must be solid.
2. **"Discount" ≠ cheap fundamentally.** We have no fundamentals (P/E, earnings),
   so "discount" is **price-position in a recent range** (technical), not value.
   Say that — or later add a valuation source.
3. **Hallucination.** Mitigated by grounding all numbers in real price data and
   validating the AI's JSON; the LLM only writes the qualitative lean + rationale.
4. **Slow feedback.** 1–3 month horizons take that long to score, so prediction
   accuracy accrues slowly. Set expectations in the UI.
5. **Cost.** Per-request OpenAI + bars. Cache + cap; Pro-gate in the product.
6. **Scope of v1.** Single-stock (type a ticker) first; a "predict my whole
   watchlist" batch is a fast follow (cost permitting).
7. **Horizon realism.** Are 1w/1mo/3mo the right set, or add "next earnings"?
   Lean: start with the three; revisit.
8. **Custom-strategy safety (prompt injection).** A user's free-text strategy is
   untrusted input in the prompt. Contain it: the strategy block sits **between**
   fixed guardrails that always win (output schema, "not advice", "the real
   numbers are authoritative — never contradict them"), the output stays strict
   validated JSON, and we ignore/neutralize attempts to change format or role.
   Treat the strategy as *preferences on weighting*, never as instructions to the
   system. (Open: length cap, a light content check, and whether to show a
   "using your custom strategy" badge on each prediction for clarity.)
9. **Strategy quality is the user's.** A vague or contradictory custom strategy
   yields worse reads — surface examples/presets, and let per-strategy accuracy
   (§5) be the honest feedback.
