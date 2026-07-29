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
| Trigger | per important article | scheduled (weekday 08:30→18:00, every 2h) + on-demand |
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
4. **Scheduled briefs always send; length scales with what's happening.** You
   asked for a steady pulse (morning → every 2h → close), so each scheduled run
   delivers. On a busy stretch it's a full brief; on a quiet one it's a short
   "nothing major, backdrop holds" line. The materiality signal controls
   **verbosity, not whether it fires.**
5. **Trend-aware with a thin memory.** The news source is always live, but we
   keep the last few hours' briefing themes as a small rolling state so the
   model can say "strengthening / fading / new" instead of starting blind.

---

## 3. Retrieval — hybrid, with a freshness window

Two sources feed each run:

**A. Our fetch (grounded spine).**
Reuse the existing collectors (Yahoo per-ticker + Google macro search). Filter
to items whose **`published_at`** — not `collected_at` — falls within a
freshness window, and **flag** items with a missing/older publish time as
unverified rather than silently trusting them. The window depends on the
trigger:

- **Morning brief (08:30):** wide — back to ~yesterday's US close (~16h): overnight
  earnings and Asia/Europe moves.
- **Intraday updates (every 2h):** narrow — since the last brief (~2h): just what's new.
- **End-of-day wrap (18:00):** the day — since the open: how it landed.
- **On-demand `/report`:** narrow — the last **~2h**, "what's fresh right now."

(`BRIEFING_MORNING_WINDOW_HOURS` / `BRIEFING_INTRADAY_WINDOW_HOURS` /
`BRIEFING_ONDEMAND_WINDOW_HOURS`.)

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

### Scheduled cadence — weekday, `America/Los_Angeles`

| Tier | Fires (PT) | Look-back | Sends |
|---|---|---|---|
| **Morning brief** | 08:30 | ~16h overnight catch-up | always (full) |
| **Intraday updates** | 10:30, 12:30, 14:30, 16:30 (every 2h) | ~2h since last brief | always (short) |
| **End-of-day wrap** | 18:00 | the day, since the open | always (recap) |

Mon–Fri, via `CronTrigger` (same pattern as the eval digest). You're in
California, so this is simply your local time — no quiet-hours/night concern. A
dedicated `BRIEFING_TIMEZONE` keeps it independent of the app-wide `TIMEZONE`.

### What "materiality" controls now
Because you asked for a steady every-2h pulse, scheduled briefs **always send** —
materiality just controls **length**, not whether it fires:
- Something new/trending → full brief in `OUTPUT_LANGUAGE`, `freshness: new`
  themes first, background/trend as context.
- Quiet stretch → a short "không có thay đổi lớn — bối cảnh giữ nguyên" line.
- `urgency: urgent` (major war/Fed shock) gets a 🔴 flag at the top.

(The silent "say nothing at all" gate is kept only for any future opt-in
"only ping me if it matters" mode.)

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

## 7. On-demand trigger — the `/report` command

You don't just want the hourly push — you want to **ask for it whenever**, from
your phone. Same core job (`run_briefing()`); on-demand is just another caller.

### UX
Text **`/report`** to the StockPulse Telegram bot → it runs a briefing *right
now* against the latest news and replies in the chat, in `OUTPUT_LANGUAGE`.

### The one new piece: the bot must *receive* messages
Today the bot only **sends**. To react to `/report` it needs an inbound
listener. Two ways:
- **Long-polling (`getUpdates`)** — a small always-on loop asking Telegram "any
  new messages?" Works from a local machine, **no public URL / webhook needed**.
  Recommended for how you run today.
- **Webhook** — Telegram pushes updates to a public HTTPS URL. Lower latency,
  but needs a reachable server (later, if you ever deploy).

The listener runs alongside the scheduler in the app lifespan. It parses
incoming updates, and on `/report` calls the briefing job.

### Rules specific to on-demand
- **Always answers.** Unlike the hourly run, `/report` **bypasses the
  materiality gate and quiet hours** — you explicitly asked, so it always
  replies. If nothing's material it says so and gives the current backdrop
  ("Thị trường yên ắng — bối cảnh hiện tại: …") instead of staying silent.
- **Authorized chat only.** Only respond to your own `TELEGRAM_CHAT_ID`; ignore
  messages from any other chat, so a stray `/report` from elsewhere can't spend
  your OpenAI budget.
- **One at a time.** If a report is already running (or one just ran seconds
  ago), reply "đang xử lý…" and reuse/debounce rather than firing duplicate
  OpenAI calls.
- **Ack fast.** Send a quick "⏳ Đang tổng hợp…" immediately, then the full brief
  when ready, since retrieval + analysis takes a few seconds.

### Also exposed as (free, same job)
- `POST /report` (a.k.a. `/briefing`) HTTP endpoint — like your `POST /evaluate`.
- A **"Report now" button** on the dashboard, like the existing "Analyze" button.

### Extra config
```
BRIEFING_TELEGRAM_COMMAND_ENABLED=true   # run the /report listener
BRIEFING_COMMAND=/report                  # the trigger word
BRIEFING_COMMAND_MODE=polling             # polling | webhook
```

---

## 8. Where it lives

- `app/briefing/` — new self-contained package:
  - `retrieval.py` — fetch fresh (reuse collectors) + window/dedupe by `published_at`.
  - `analyst.py` — build prompt, call OpenAI (with optional web-search tool), parse JSON.
  - `render.py` — JSON → localized Telegram text.
  - `state.py` — thin rolling store of recent themes (for trend + dedupe).
- `app/jobs/briefing_monitor.py` — `run_briefing()` orchestrating retrieve → analyze → deliver.
- `app/alerts/telegram_listener.py` — inbound `getUpdates` loop that handles the
  `/report` command (the only part that *receives*, not just sends).
- Scheduled in `app/main.py` via an interval trigger (like the existing jobs),
  reusing the Telegram notifier and quiet-hours check; the listener starts in
  the same lifespan.
- Routes: `POST /report` and a dashboard "Report now" button.
- Rolling state: a small table or a JSON file — TBD in build.

---

## 9. Config (proposed)
```
BRIEFING_ENABLED=true
# Scheduled cadence — weekday, your local (Pacific) / US-market time.
BRIEFING_TIMEZONE=America/Los_Angeles   # independent of app TIMEZONE
BRIEFING_SCHEDULE_DAYS=mon-fri
BRIEFING_MORNING_AT=08:30               # full morning brief
BRIEFING_INTRADAY_EVERY_HOURS=2         # updates at 10:30, 12:30, 14:30, 16:30
BRIEFING_INTRADAY_UNTIL=16:30           # last intraday check-in
BRIEFING_WRAP_AT=18:00                  # end-of-day recap
# Look-back windows (see §3).
BRIEFING_MORNING_WINDOW_HOURS=16
BRIEFING_INTRADAY_WINDOW_HOURS=2
BRIEFING_ONDEMAND_WINDOW_HOURS=2
# Retrieval + model.
BRIEFING_WEB_SEARCH_ENABLED=true        # let the model pull news itself
BRIEFING_MODEL=gpt-4o                   # web-search-capable; separate from classifier
BRIEFING_MEMORY_HOURS=3                 # trend-context reach
# reuses: OUTPUT_LANGUAGE, Telegram creds, existing watchlist + macro collectors.
# Scheduled briefs send regardless of quiet hours (you're on Pacific time).
```

---

## 10. Suggested build order

| Step | Piece | Notes |
|---|---|---|
| A | Retrieval + freshness window (our feeds, `published_at` filter, dedupe) | no AI yet; log what passes |
| B | Analyst call (prompt + JSON parse), web search **off** first | prove synthesis on our feed |
| C | Timestamp/recency guard end-to-end (recap detection) | the "week-in-review" fix |
| D | `POST /report` + dashboard button → **on-demand works first** | test the whole job by hand |
| E | Scheduled cadence (08:30 → every 2h → 18:00) + verbosity-by-materiality | the daily pulse |
| F | Telegram `/report` listener (getUpdates, auth to your chat) | the phone-native trigger |
| G | Rolling theme memory (trend continuity + cross-brief dedupe) | "strengthening/fading" |
| H | Turn on web-search tool | model pulls its own news; watch cost |

On-demand (D + F) lands **before** the scheduled cadence (E): once `/report`
works you can pull a briefing whenever, and the scheduled tiers are the same job
on cron triggers. Start with our feeds (A–G) so it's cheap and deterministic;
add web search (H) once the shape feels right.

---

## 11. Honest caveats
- **Cost & noise of web search.** Live retrieval is less repeatable and costs
  more; the materiality gate is what keeps hourly from becoming a firehose.
- **Timestamps are messy.** Some feeds give no/garbage publish times; those are
  flagged, not trusted. The recap guard is heuristic, not perfect.
- **Not advice.** This is intelligence, not recommendations — no targets, no orders.
- **Correlation, not causation** — same caveat as the evaluation loop.
- **Free data limits.** Same as elsewhere; treat everything as approximate.
- **Inbound Telegram = new surface.** The `/report` listener is the first part
  that *receives* messages. It must be locked to your chat id and rate-limited,
  or a stray/abusive message could spend OpenAI budget.

## 12. Open questions
1. ~~**Cadence.**~~ **Decided:** weekday **08:30 PT morning brief → every-2h
   intraday updates (10:30–16:30) → 18:00 PT end-of-day wrap**, all
   `America/Los_Angeles`; plus on-demand `/report` anytime. Scheduled briefs
   always send (short when quiet).
2. **Web search:** on from the start, or ship A–G first and add it after?
3. **Quiet hours:** should routine briefings be *held and flushed* (like alerts)
   or simply *skipped* overnight? (A held brief may be stale by morning.)
4. **Memory store:** small DB table vs a JSON file for rolling themes?
5. **Overlap with alerts:** dedupe a briefing against alerts already sent this
   hour, so you don't hear the same thing twice?
```
