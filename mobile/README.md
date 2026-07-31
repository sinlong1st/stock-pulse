# StockPulse — mobile app

The React Native (Expo) client for StockPulse. This is the **kickoff scaffold**:
the design system + navigation are in place and the screens render **mock data**.
It is built faithfully to the Claude Design handoff in
[`../design/`](../design/) — see also
[`../specs/STOCKPULSE_MOBILE_APP_PLAN.md`](../specs/STOCKPULSE_MOBILE_APP_PLAN.md).

## Run it

```bash
cd mobile
npm install          # already done if you see node_modules/
npm start            # opens Expo Dev Tools
```

Then either:
- press **`i`** (iOS simulator, macOS only) or **`a`** (Android emulator), or
- install **Expo Go** on your phone and scan the QR code.

> Tap the **search icon** on the Feed header to flip between **dark and light**
> themes (a stand-in until search is wired), or use the **Dark theme** switch in
> Settings.

## What's built

| Area | Status |
|---|---|
| Design tokens → theme (dark default + light) | ✅ `src/theme/` |
| Semantic system (sentiment, importance meter, freshness) | ✅ `src/theme/semantics.ts` |
| Reusable components (alert card, price line, pills, tags, segmented) | ✅ `src/components/` |
| **Feed** — filter, refresh bar, alert stream | ✅ `src/screens/FeedScreen.tsx` |
| **Report** — takeaway, themed sections, watchlist block | ✅ `src/screens/ReportScreen.tsx` |
| **Watchlist** — rows with sentiment + change | ✅ `src/screens/WatchlistScreen.tsx` |
| **Settings** — preferences, account, live theme toggle | ✅ `src/screens/SettingsScreen.tsx` |
| 4-tab navigation (Feed · Report · Watchlist · Settings) | ✅ `src/navigation/Tabs.tsx` |

## Showing real data

By default the app renders **mock data** (`src/data/mock.ts`) so it always works.
To point the **Feed** at your real backend:

1. On the server, set in `.env` and restart:
   ```
   MOBILE_API_ENABLED=true
   MOBILE_API_TOKEN=<a long random string>
   ```
   and make the port reachable from your device (see below).
2. In [`src/config.ts`](src/config.ts) set `API_BASE_URL` (e.g.
   `http://192.168.1.50:8000` for your computer on the same Wi-Fi, or your
   droplet's address) and `API_TOKEN` to the same token.
3. Reload the app (`npm start` / `npm run web`). The Feed now fetches
   `GET /api/feed`, with loading / empty / error states and pull-to-refresh.

Leave `API_BASE_URL` empty to go back to mock data. The header shows
"SAMPLE DATA" when no backend is configured.

> The endpoint is **read-only** and token-guarded; it does not affect the
> news/alert/Telegram pipeline. Reaching it from a phone means exposing the port
> (and ideally adding HTTPS) — fine for a personal test, see the main plan for
> the production story.

## Not built yet (next steps)

- **Screen states:** loading skeletons, empty, and error variants (design has all
  four per screen).
- **Pushed screens:** Alert detail (with the 5-day sparkline), Evaluation.
- **Onboarding & paywall:** sign-in (Apple/Google/email), notification ask,
  watchlist starter, subscription screen.
- **Real interactions:** search-to-add, swipe-to-remove, pull-to-refresh.
- **Archivo font:** currently the system sans (weights match). Add
  `@expo-google-fonts/archivo` + `expo-font` `useFonts`, then set
  `type.family` in `src/theme/tokens.ts`.
- **Real data:** replace `src/data/mock.ts` with API calls once the multi-tenant
  backend + JSON endpoints exist (Phase 1 of the plan).

## Structure

```
mobile/
  App.tsx                  theme provider + navigation container
  src/
    theme/                 tokens.ts · ThemeContext.tsx · semantics.ts
    components/            AlertCard, PriceLine, ImportanceMeter, SentimentPill, Tags, Segmented, ScreenHeader
    screens/               Feed, Report, Watchlist, Settings
    navigation/Tabs.tsx    bottom tab bar
    data/                  types.ts · mock.ts  ← swap for the API later
```
