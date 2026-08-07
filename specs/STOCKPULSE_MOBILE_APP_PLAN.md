# StockPulse — Mobile App & Multi-User Product Plan

**Status:** proposal / no backend code yet. This is the big one: it turns
StockPulse from a **single-user personal tool** into a **multi-tenant product**
with a native mobile app you can put on the App Store / Play Store and charge
for. It supersedes the "multi-user" idea flagged in earlier specs.

> ✅ **The UI design is done.** A Claude Design handoff bundle lives in
> [`design/`](../design/) — a full "Modernist" system (Archivo type, sharp 0px
> corners, cornflower-blue accent) with every screen mocked in light + dark and
> in all four states. `design/project/StockPulse.dc.html` is the primary file.
> §5.1 below captures the decisions it locks in; the rest of this plan is the
> backend/app work that makes those screens run on real data.

> ⚠️ Reality check up front. Everything shipped so far assumes **one user**: one
> Telegram chat, one `watchlist.json`, one `.env`, one SQLite file, one global
> scheduler. This plan is not an increment on that — it's a rearchitecture of the
> backend plus a brand-new client app plus billing plus ops. Estimate **months**,
> not weeks, and real ongoing cost/support once strangers are on it. The plan is
> phased so each phase ships something usable and de-risks the next.

---

## 1. Why / what the app buys us

Telegram is already a decent "mobile app": push to phone, commands, iOS+Android,
zero store friction. A dedicated app is worth it only for what Telegram can't do:

- **Your own brand + richer UI** — tap-through charts, portfolio views, nicer
  report and alert layouts than a chat bubble.
- **Reach** — people who will never add a Telegram bot but will install an app.
- **Monetization** — subscriptions through the App Store / Play Store.

If any of those is the goal, we need multi-user. So the app and the multi-user
pivot are the same project; the backend work is the bulk of it, the app is a
comparatively thin client once the API exists.

---

## 2. Target architecture

```
        ┌─────────────────────────────┐
        │  Mobile app (Expo / RN)     │  iOS + Android, one codebase
        │  auth · feed · report ·     │
        │  watchlist · settings       │
        └───────────────┬─────────────┘
                        │  HTTPS + JWT (JSON REST)
                        ▼
        ┌─────────────────────────────┐
        │  FastAPI backend (existing) │  now multi-tenant
        │  auth · per-user API ·      │
        │  jobs · delivery fan-out    │
        └───────┬───────────┬─────────┘
                │           │
      ┌─────────▼──┐   ┌────▼─────────────────┐
      │ Postgres   │   │ Delivery layer       │
      │ per-user   │   │  Telegram + App push │──► APNs / FCM (via Expo Push)
      │ data       │   └──────────────────────┘
      └────────────┘
                ▲
      ┌─────────┴───────────┐
      │ Shared news pipeline│  collect once → classify once → fan out per user
      │ + per-user briefings│
      └─────────────────────┘
```

The Python backend **stays** and becomes the API. The server-rendered dashboard
(`app/web/`) can remain as an admin/debug view; the app talks to new JSON
endpoints.

---

## 3. Phase 1 — Multi-tenant backend (the core lift)

Everything else depends on this. Nothing here is user-facing yet; it's the
plumbing that makes "one user" into "many".

### 3.1 Accounts & auth
- New `users` table: `id`, `email`, auth identity (see below), `language`,
  `timezone`, `subscription_tier` (default `free`), `telegram_chat_id` (nullable,
  for users who also link Telegram), `created_at`, `status`.
- **Auth:** JWT access + refresh tokens issued by the backend. Sign-in options:
  **Sign in with Apple** (mandatory on iOS if you offer any social login) +
  **Google**, with **email magic-link** as fallback. A FastAPI dependency
  resolves the JWT → `user_id` and **scopes every query** to that user.
- Account deletion endpoint (Apple requires in-app deletion).

### 3.2 Per-user data (kill the global files)
Today's global config files become per-user DB rows:

| Today (global) | Becomes (per-user) |
|---|---|
| `watchlist.json` | `watchlists` table (`user_id`, ticker, aliases) |
| `runtime_prefs.json` (`app/prefs.py`) | `user_prefs` (`user_id`, language, …) |
| `keywords.json` | shared default + optional per-user overrides |
| single `telegram_chat_id` in `.env` | `users.telegram_chat_id` + push tokens |
| alerts / classifications / predictions | gain a `user_id` FK (delivery is per-user) |

The `app/prefs.py` and `app/watchlist.py` mutation patterns you already built are
the seed of this — same idea (load → mutate → persist → invalidate), just keyed
by `user_id` in Postgres instead of a JSON file.

### 3.3 SQLite → Postgres
Multiple concurrent users writing = SQLite's single-writer model won't do.
Migrate to **Postgres** (managed: DigitalOcean Managed DB or Supabase). Alembic
migrations already exist; the engine URL and a few types change. Keep SQLite for
local dev/tests.

### 3.4 JSON API
Expose the existing logic as REST (the web views already compute everything):

```
POST /auth/apple  /auth/google  /auth/email        → tokens
GET  /me                                            → profile + tier
GET/POST/DELETE /watchlist                          → per-user CRUD
GET  /alerts?cursor=…                               → paginated feed
POST /report            (body: {ticker?})           → on-demand briefing
GET  /evaluation                                    → accuracy report
GET/PATCH /settings     (language, quiet hours, schedule)
POST /push/register     (Expo push token)
POST /telegram/link     (optional: connect a chat)
```

### 3.5 Jobs at scale — the cost-critical redesign
Today one scheduler runs one pipeline. With many users, **news collection is
shared** (everyone reads the same RSS/macro feeds) but **relevance + alerting is
per-user** (their watchlist, their thresholds). The efficient design:

1. **Collect once** (shared) — unchanged feeds.
2. **Classify once per article, not per user.** An article's AI verdict
   (importance/sentiment/tickers) is the same for everyone → classify it a single
   time, cache the `ClassificationResult`, and **reuse it across all users**. This
   is the single biggest OpenAI-cost saver.
3. **Fan out per user:** cheap rule gate — does this article hit *this* user's
   watchlist and clear *their* importance threshold? If so, create their alert.
4. **Briefings stay per-user** (their watchlist) → one OpenAI call per user per
   briefing. This cost scales linearly with users and **must** be tier-capped
   (§5).

---

## 4. Phase 2 — Delivery / notification layer

Generalize `app/alerts/` so one alert can go to multiple channels per user:

- Abstract `Notifier` → resolve a user's channels: **Telegram** (if linked)
  and/or **app push**.
- **Push:** register the app's push token per device; send via **Expo Push API**
  (simplest — it wraps APNs + FCM), or go direct to APNs/FCM later for control.
- Deep links: a push taps through to the relevant screen (alert detail, report).
- Respect per-user quiet hours / language (already modeled, now per-user).

---

## 5. Phase 3 — The mobile app (Expo / React Native)

**Stack (solo-dev-friendly):** Expo (managed) + TypeScript, React Navigation,
**TanStack Query** for API/cache, **Expo Notifications** for push, **RevenueCat**
for subscriptions, **EAS Build/Submit** for store builds, **EAS Update** for
over-the-air JS updates (ship fixes without a store review).

**Information architecture (locked by the design):** a **4-tab** bottom bar —
**Feed · Report · Watchlist · Settings** — with **Alert detail** and
**Evaluation** as *pushed* screens (not tabs; Evaluation is reached from
Settings). First run is **Sign in → notifications ask → 3-stock watchlist
starter → Feed**.

**Screens** (each designed in light + dark with populated / loading-skeleton /
empty / error states):
- **Onboarding / auth** — Continue with Apple / Google / email → notification
  permission ask → watchlist starter (a few pre-selected tickers).
- **Feed** (home, tab 1) — the alert stream: importance notch-meter + category
  tag + sentiment pill, one-line summary, "WHY" line, ticker chips, inline price
  line. Segmented filter (All / Watchlist / Macro), pull-to-refresh.
- **Alert detail** (pushed from Feed) — headline, sentiment + tickers, a 5-day
  price sparkline, "why it matters", affected-tickers list, source link, a
  "Generate briefing on <ticker>" CTA, and the "not investment advice" line.
- **Report** (tab 2) — scope toggle (whole watchlist / single stock), a
  "today's takeaway", themed sections (each with a sentiment dot + direction),
  and a watchlist "% vs open" block with a freshness stamp.
- **Watchlist** (tab 3) — rows with ticker, name, price, %, sentiment;
  **swipe-to-remove**; add flow with search (`tesla` → TSLA, reuses the Yahoo
  resolver) + a "trending now" shortcut row.
- **Evaluation** (pushed from Settings) — directional-accuracy headline stat,
  per-sentiment accuracy bars, recent-calls history.
- **Settings** (tab 4) — language, quiet hours, briefing schedule, push toggle,
  link Telegram, manage subscription, sign out, delete account.
  *Shipped: language, briefing schedule (editable, live), push + Telegram
  toggles, strategies, theme. Still placeholders: manage subscription, sign out,
  delete account — they need the multi-user work in §5.*
- **Paywall** (modal) — Free vs Pro comparison + pricing (§6).

All screens are thin clients over the Phase-1 API. No business logic in the app.

### 5.1 Design system (from the Claude Design handoff — treat as the source of truth for UI)

Recreate the mocks pixel-faithfully in React Native; translate these tokens into
a theme file. Dark is the **default**, light is opt-in.

- **Type:** Archivo (weights 400–900; headings 800–900), tight tracking. Prices
  use `tabular-nums`.
- **Shape/elevation:** **0px radius everywhere** (sharp corners are the brand);
  three shadow levels; heavy 1–2px dividers.
- **Spacing:** 4px base (4 / 8 / 12 / 16 / 24 / 32).
- **Accent:** cornflower **`#6495ED`** (dark ink `#a9c6f5`, light ink `#2f5aa8`).
  This deliberately overrides the base template's red so sentiment owns green/orange.
- **Surfaces:** dark `bg #151312 / surface #201e1d / surface-2 #2b2827 / text #f3f2f2`;
  light `bg #f3f2f2 / surface #eae9e9 / surface-2 #e0dedd / text #201e1d`.
- **Semantic tokens (never color alone — always icon + label/shape):**
  - **Sentiment** — bullish green (`#3fbf6a` dark / `#1a7d3c` light, ▲), bearish
    **orange** (`#e5942f` / `#b3590f`, ▼), neutral grey (→). Calm, not casino red.
  - **Importance** — LOW→CRITICAL shown as a **1–4 notch meter** + label.
  - **Category** — MACRO / TICKER / SECTOR outline tag.
  - **Price freshness** — a **live** dot vs an honest **"as of Fri 13:00 PDT"**
    stamp (mirrors the existing `price_snapshot_line` honesty rule).
- **Accessibility:** WCAG AA, Dynamic-Type friendly, color-blind safe by design.
- **Brand:** app icon + splash = an abstract "pulse" line mark on the accent
  (evolved from the Telegram shiba); disclaimers ("Not investment advice") are
  baked into alert detail + report.

---

## 6. Phase 4 — Monetization

- **Billing via RevenueCat**, which wraps App Store + Play in-app purchase
  (Apple/Google **require** IAP for digital subscriptions — you can't use Stripe
  for in-app unlocks). RevenueCat webhooks → backend sets `users.subscription_tier`.
- **Tiers & pricing (set by the design — the paywall is built around these):**

  | | Free | Pro |
  |---|---|---|
  | Alerts per day | 3 | unlimited |
  | Watchlist size | 5 | unlimited |
  | AI briefings | weekly | on-demand |
  | Accuracy history (Evaluation) | — | ✓ |
  | Telegram + push | ✓ | ✓ |

  **Price:** **$9.99/mo** or **$79/yr** (save ~34%), with a **7-day free trial**.
- **The economics that make or break it:** every briefing and (uncached)
  classification costs you OpenAI money. Per-user cost must sit **below** the Pro
  price — **validate the $/user/month at this cadence against $79/yr before
  building billing** (still open question #1). Enforce caps server-side (extend
  the existing `MAX_*_PER_RUN` idea into per-user budgets).
- ⚠️ **Product risk to test:** "3 alerts/day" is a sharp cap for a *news-alert*
  app whose promise is "never miss the one that matters." Consider capping
  briefings/reports hard but letting **critical** alerts always through, so the
  free tier still delivers the core value.

---

## 7. Phase 5 — Scale, ops & shipping

- **Infra:** split the web API and the job worker into separate processes
  (still one droplet to start; scale out when needed). Managed Postgres.
- **Guardrails:** per-user rate limits, global + per-user OpenAI budget caps,
  structured logging + a metric or two (users, alerts sent, $ spent).
- **Store compliance (don't skip):**
  - **Disclaimers** — "not investment advice", no performance guarantees, on
    reports and at onboarding. Finance apps get scrutinized.
  - **Privacy policy** + data handling; **in-app account deletion** (Apple).
  - IAP for subscriptions (via RevenueCat); App Privacy "nutrition label".
- **Legal:** you're distributing market commentary to paying strangers — a plain
  terms-of-service + disclaimer is worth getting right.

---

## 8. Data model changes (summary)

New tables: `users`, `user_prefs`, `watchlists`, `push_devices`, `subscriptions`
(mirrors RevenueCat entitlement). Existing tables (`articles` stay global;
`classifications` become a shared cache; `alerts`, `predictions`) gain `user_id`.
Alembic migrations, Postgres.

---

## 9. Tech-stack decisions (recommended)

| Concern | Choice | Why |
|---|---|---|
| App framework | **Expo / React Native** | one codebase, built-in push + OTA, fastest solo path |
| Backend | **keep FastAPI** | reuse all existing pipeline/AI/price logic |
| DB | **Postgres** (managed) | concurrent multi-user writes |
| Auth | **Apple + Google + email**, JWT | store requirements + a fallback |
| Push | **Expo Push** → APNs/FCM | least plumbing to start |
| Billing | **RevenueCat** | wraps mandatory store IAP; entitlement webhooks |
| Store CI | **EAS Build / Submit / Update** | builds + OTA without full re-review |
| Design system | **done** — `design/` handoff (Archivo · 0px · `#6495ED`) | tokens → RN theme; see §5.1 |

---

## 10. Suggested build order

Backend first — the app is thin once the API exists. Nothing here is shipped yet.

| Step | Piece | Status |
|---|---|---|
| A | Postgres migration; keep single-user working end-to-end | ⬜ |
| B | `users` + auth (Apple/Google/email, JWT); scope existing data to one seed user | ⬜ |
| C | Per-user data: move watchlist + prefs + delivery target into DB (retire the global JSON for multi-user) | ⬜ |
| D | JSON API for watchlist / alerts / report / settings / evaluation | ⬜ |
| E | Shared-classification cache + per-user fan-out in the news job (cost saver) | ⬜ |
| F | Delivery layer: per-user Telegram **and** app push (Expo Push) | ⬜ |
| G | Expo app: auth + feed + watchlist + report + settings (build to the `design/` mocks; §5.1) | ⬜ |
| H | RevenueCat subscriptions + tier gating + per-user OpenAI budget caps | ⬜ |
| I | Compliance (disclaimers, privacy, account deletion) + store submission | ⬜ |
| J | Split web/worker processes, rate limits, metrics | ⬜ |

**Cheaper stepping stone (optional):** before the full app, ship a **PWA** of the
existing dashboard (installable + web push). It validates demand and reuses the
Phase-1 API — but it does **not** replace Phase 1; multi-user is still required
the moment there's more than one account.

---

## 11. Risks & open questions

**Resolved by the design handoff:** the full UI (screens, states, IA, tokens),
the tier structure + pricing ($9.99/mo · $79/yr), the onboarding flow, and the
"not investment advice" disclaimers. Telegram is **kept** as an optional linked
channel (§4, Settings). These are no longer open.

**Still open:**
1. **Unit economics (the go/no-go).** What's the real OpenAI $/user/month at the
   design's cadence, and does **$79/yr** clear it with margin? Model this *before*
   building billing — it decides whether the product is viable.
2. **Free-tier shape.** The design sets 3 alerts/day + 5-stock watchlist. Verify
   that doesn't gut the core "never miss the one that matters" promise — likely
   cap **briefings/reports** hard but always let **critical** alerts through (§6).
3. **Apple review risk for finance apps.** Disclaimers are in the design; still
   be ready for review pushback on "market advice" framing.
4. **Do you actually want to run a business here?** Multi-user means support,
   uptime, refunds, and cost risk. If the honest goal is "a nicer app for me and
   friends," the **PWA path** (much cheaper) may be the better call — decide
   before committing to Phase 1.
5. **Build sequencing.** App-first on **mock data** (fast to a demo, matches the
   finished design) vs backend-first (no throwaway). The design makes app-first
   attractive for momentum; either way Phase 1 (multi-tenant backend) is required
   before real data flows.
