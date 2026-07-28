# StockPulse — Hourly Market Briefing ("The Secretary") Plan

**Status:** proposal / design only. No code yet. This plans a new, self-contained
job that runs *alongside* the existing alert pipeline — it does not change how
alerts, classification, or self-evaluation work today.

---

## 1. Why

StockPulse today is **reactive**: it fetches news, classifies each article, and
fires one Telegram alert per important item. Great for "this just happened."

What's missing is a **proactive analyst** — a secretary that, on its own cadence,
pulls the *latest* news across the themes that move your watchlist (AI &
semiconductors, big tech, macro/Fed, geopolitics & war, energy), reads the
trend, and tells you what actually matters right now — and stays quiet when
nothing does.

This is a different pipeline from alerts:

| | Alerts (existing) | Briefing (new) |
|---|---|---|
| Trigger | per important article | on a clock (hourly) |
| Output | one message per event | one synthesized brief |
| Source | our fetched + stored feed | **live pull** (our feed + web search) |
| Question | "is this article important?" | "what should I know right now, and is it trending?" |

They complement each other — keep both.

---

## 2. Core principles

1. **Live, not stored.** The briefing does NOT summarize yesterday's database.
   Each run pulls fresh news at that moment.
2. **The model can pull news itself.** Beyond our two RSS feeds, enable OpenAI's
   web-search tool so the model retrieves live news and cross-checks coverage —
   a hybrid of our grounded feed + its own retrieval.
3. **Timestamp-aware.** A recent *publish date* is not proof of recent *news*.
   We separate genuinely-new events from recaps/roundups, mechanically and in
   the prompt (see §4).
4. **Quiet by default.** Hourly cadence means most runs have nothing material.
   The model is allowed — expected — to say "nothing new," and we only ping on
   a material update. Respects the existing quiet-hours settings.
5. **Trend-aware with a thin memory.** The news source is always live, but we
   keep the last few hours' briefing themes as a small rolling state so the
   model can say "strengthening / fading / new" instead of starting blind.

---

## 3. Retrieval — hybrid, with a freshness window

Two sources feed each run:

**A. Our fetch (grounded spine).**
Reuse the existing collectors (Yahoo per-ticker + Google macro search). Filter
to items whose **`published_at`** — not `collected_at` — falls within a
freshness window (default **2h**). Items with a missing/older publish time are
**flagged as unverified**, never silently trusted as fresh.

- `published_at` = when the world got the news.
- `collected_at` = when we happened to poll. Never use this for freshness.

**B. Model web-search (widen + confirm).**
Enable the web-search tool (OpenAI Responses API) so the model pulls live news
our two feeds miss and gauges how widely a story is reported. Honest tradeoffs:
costs more per call, adds latency, is less repeatable, and needs a model that
supports the tool (a per-job model override, separate from the classifier's
`gpt-4o-mini`). At ~24 calls/day the cost is still small.

**Config toggle:** `BRIEFING_WEB_SEARCH_ENABLED`. Off = leaner, our feeds only.
On (recommended) = truly "pulls the news itself."

---

## 4. The timestamp guard (the "week-in-review" trap)

A weekly recap published this morning is *fresh by timestamp but stale by
content*. A mechanical filter can't see that — the model must judge it. Two
layers:

**Mechanical:** filter our feed by `published_at` within the window; dedupe
against the last few hours so the same headline isn't re-reported; pass the
model an explicit **NOW** timestamp plus each item's publish time.

**Semantic (in the prompt):** classify every item before using it —

- `temporal_type`: `breaking` | `developing` | `recap_or_roundup` | `evergreen_analysis`
- `event_time`: when the underlying **event** happened (from the text), not when
  the article was published.

Rule: an item is "new" only if the **event** is within the window of NOW — not
merely because the publish date is recent. Recaps/evergreen items may be cited
for *trend context* but are labeled **background**, never as this-hour news. If
event time is unclear, downgrade its weight rather than assume fresh.

Each output theme carries `event_time` + `freshness: new | background` so the
delivery layer leads with genuinely new items.

---

## 5. The prompt (the heart of it)

**System prompt (draft):**
```
You are StockPulse, a sharp market-intelligence analyst acting as a personal
secretary for one investor. Your ONLY job: from the latest news provided (and
any you retrieve), surface what could move THIS investor's watchlist — and be
honest when nothing material has changed.

WATCHLIST: {tickers}
FOCUS THEMES: AI & semiconductors, big tech, macro/Fed/rates/inflation,
              geopolitics & war, energy/oil, supply chains.
NOW: {current_utc}         FRESHNESS WINDOW: {window_hours}h

You are given:
  • LATEST_NEWS: freshly fetched headlines (source, publish_time, snippet).
  • PRIOR_THEMES: what you flagged in the last few hours (for trend continuity).
  • You may also use web search to pull and confirm live news.

For EACH item, first classify:
  temporal_type: breaking | developing | recap_or_roundup | evergreen_analysis
  event_time:    when the underlying EVENT happened (from the text), NOT the
                 publish date. Weekly/monthly summaries describe OLD events.
Rules for freshness:
  • Treat an item as NEW only if its EVENT is within {window_hours}h of NOW.
  • recap_or_roundup / evergreen_analysis are NEVER "new". Cite them only as
    background/trend context, clearly labeled.
  • If event time is unclear, downgrade it — do not assume fresh.

Then analyze:
1. RELEVANCE — drop noise, celebrity, sports, generic listicles. Keep only what
   plausibly affects the watchlist or focus themes.
2. IMPACT — for each kept item: which ticker(s)/theme, direction (bullish /
   bearish / mixed), and WHY in one clause. Separate a real catalyst from chatter.
3. TREND — vs PRIOR_THEMES: is a storyline new, strengthening, fading, or
   reversing? Trends matter more than one-off headlines.
4. MATERIALITY — set has_material_update=false if this hour brings nothing a busy
   investor needs. Repetition of an already-reported story is NOT material unless
   it escalated. Do not invent significance.

Rules:
  • Ground every claim in a real headline (provided or retrieved). Never speculate
    beyond the news. Prefer widely-reported over single-source.
  • No investment advice, no price targets — analysis, not recommendations.
  • Concise and skimmable; a tired human reads this on a phone.
  • Write all human-facing text in: {output_language}.

Return JSON only:
{
  "has_material_update": bool,
  "urgency": "routine" | "notable" | "urgent",
  "headline": "one-line gist, or '' if nothing material",
  "themes": [
    {"theme": "...", "direction": "bullish|bearish|mixed", "tickers": ["..."],
     "insight": "1-2 sentences with the why", "trend": "new|strengthening|fading|reversing",
     "freshness": "new|background", "event_time": "...", "sources": ["..."]}
  ],
  "watchlist_notes": [{"ticker": "...", "note": "...", "direction": "..."}],
  "risk_flags": ["war/geopolitics/oil shocks worth watching, if any"]
}
```

**User message** each run = the freshly fetched (windowed) headlines + the last
2–3 hours of themes.

---

## 6. Delivery

- `has_material_update == false` → **stay silent** (log it; roll context to next run).
- `true` → format the JSON into a clean Telegram brief in `OUTPUT_LANGUAGE`
  (Vietnamese), leading with `freshness: new` themes; background/trend shown as
  context.
- `urgency == "urgent"` bypasses quiet hours, mirroring how `CRITICAL` alerts do.
- Otherwise the existing quiet-hours window is respected (held/skipped).

Example (Vietnamese):
```
📊 StockPulse — Bản tin nhanh · 14:00
🔴 Khẩn: Fed phát tín hiệu giữ lãi suất cao hơn dự kiến
🤖 AI & Bán dẫn (đang mạnh lên) → NVDA, MSFT
 • ... (mới, 13:20)
⚔️ Địa chính trị → rủi ro giá dầu
 • ... (nền, tuần này)
```

---

## 7. Where it lives

- `app/briefing/` — new self-contained package:
  - `retrieval.py` — fetch fresh (reuse collectors) + window/dedupe by `published_at`.
  - `analyst.py` — build prompt, call OpenAI (with optional web-search tool), parse JSON.
  - `render.py` — JSON → localized Telegram text.
  - `state.py` — thin rolling store of recent themes (for trend + dedupe).
- `app/jobs/briefing_monitor.py` — `run_briefing()` orchestrating retrieve → analyze → deliver.
- Scheduled in `app/main.py` via an interval trigger (like the existing jobs),
  reusing the Telegram notifier and quiet-hours check.
- Rolling state: a small table or a JSON file — TBD in build.

---

## 8. Config (proposed)
```
BRIEFING_ENABLED=true
BRIEFING_INTERVAL_MINUTES=60
BRIEFING_FRESHNESS_WINDOW_HOURS=2
BRIEFING_WEB_SEARCH_ENABLED=true       # let the model pull news itself
BRIEFING_MODEL=gpt-4o                   # web-search-capable; separate from classifier
BRIEFING_MEMORY_HOURS=3                 # how far back trend context reaches
BRIEFING_MIN_URGENCY_BYPASS=urgent      # which level ignores quiet hours
# reuses: TIMEZONE, OUTPUT_LANGUAGE, quiet-hours settings, Telegram creds,
#         the existing watchlist + macro collectors.
```

---

## 9. Suggested build order

| Step | Piece | Notes |
|---|---|---|
| A | Retrieval + freshness window (our feeds, `published_at` filter, dedupe) | no AI yet; log what passes |
| B | Analyst call (prompt + JSON parse), web search **off** first | prove synthesis on our feed |
| C | Timestamp/recency guard end-to-end (recap detection) | the "week-in-review" fix |
| D | Delivery + materiality gate + quiet-hours integration | when it actually pings you |
| E | Rolling theme memory (trend continuity + cross-hour dedupe) | "strengthening/fading" |
| F | Turn on web-search tool | model pulls its own news; watch cost |

Start with our feeds (A–E) so it's cheap and deterministic; add web search (F)
once the shape feels right.

---

## 10. Honest caveats
- **Cost & noise of web search.** Live retrieval is less repeatable and costs
  more; the materiality gate is what keeps hourly from becoming a firehose.
- **Timestamps are messy.** Some feeds give no/garbage publish times; those are
  flagged, not trusted. The recap guard is heuristic, not perfect.
- **Not advice.** This is intelligence, not recommendations — no targets, no orders.
- **Correlation, not causation** — same caveat as the evaluation loop.
- **Free data limits.** Same as elsewhere; treat everything as approximate.

## 11. Open questions
1. **Cadence:** hourly, or only during market-relevant hours (e.g. pre-market +
   US session in your timezone)? Hourly overnight may rarely be material.
2. **Web search:** on from the start, or ship A–E first and add it after?
3. **Quiet hours:** should routine briefings be *held and flushed* (like alerts)
   or simply *skipped* overnight? (A held brief may be stale by morning.)
4. **Memory store:** small DB table vs a JSON file for rolling themes?
5. **Overlap with alerts:** dedupe a briefing against alerts already sent this
   hour, so you don't hear the same thing twice?
```
