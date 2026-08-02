# StockPulse — AI Prediction Plan

**Status:** proposal / design only. No code yet. A **forward-looking** feature:
for a given stock, the AI gives a multi-horizon read — **bounce vs dip** over
1 week / 1 month / 3 months — plus a **"good discount?"** signal, synthesized
from recent news + price trend + where the price sits in its range.

> ⚠️ **Framing is everything here.** This is the AI's *reasoned opinion*, not a
> forecast model and **not investment advice**. It's speculative by nature.
> Every surface must say so, plainly. The honest hook is the self-evaluation tie
> (§7): we don't just predict — we **grade our own predictions over time**.

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

---

## 5. Where it lives (app + API)

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

## 6. Cost & gating

- Each prediction = **1 OpenAI call + a bars fetch**. On-demand only; no
  automatic runs. Consider a short per-ticker cache and a per-day cap.
- Fits the future tiering (Pro-only, or N/day free) from the mobile plan.

---

## 7. The elegant part — predictions feed self-evaluation

A prediction already *is* a directional call with horizons. So we **record it
into the existing prediction/evaluation loop** (`record_predictions`-style) with
horizons `1w / 1mo / 3mo` and a baseline price. Then the **shipped evaluation
scorer** grades it later (now market-closed-aware, §eval plan), and the
**Accuracy screen shows how good the AI's *predictions* have been** — not just
its alert sentiment. The app predicts *and* keeps itself honest. (Caveat: 1–3
month horizons mean accuracy builds slowly — that's fine, it's real.)

---

## 8. Config (proposed)

```
PREDICTION_ENABLED=false
PREDICTION_HORIZONS=1w,1mo,3mo
PREDICTION_MODEL=gpt-4o-mini
PREDICTION_RANGE_MONTHS=3          # window for the discount/trend signals
PREDICTION_CACHE_MINUTES=180       # reuse a recent read for the same ticker
```

---

## 9. Suggested build order

| Step | Piece | Status |
|---|---|---|
| A | Bars/price-history fetch (Yahoo v8) + `signals.py` (discount + trend), tested | ⬜ |
| B | `analyst.py` (OpenAI → validated JSON) + `build_prediction` assembler | ⬜ |
| C | `GET /api/predict` endpoint (name→ticker, news + signals + analyst) + tests | ⬜ |
| D | Mobile **Predict** screen in the AI area | ⬜ |
| E | Record predictions into the eval loop (1w/1mo/3mo) → accuracy over time | ⬜ |
| F | Cache + per-day cap; tier gating (later) | ⬜ |

Build A–B pure/deterministic-first (testable offline), then wire the endpoint.

---

## 10. Risks & open questions

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
