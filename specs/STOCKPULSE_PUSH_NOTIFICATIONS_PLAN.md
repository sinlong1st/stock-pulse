# StockPulse — Push Notifications Plan

**Status:** **A–E shipped** — push works end-to-end. Test pushes fire via
`POST /api/push/test`, and **real news now pushes** (gated by `PUSH_ENABLED`,
mirroring the Telegram send + quiet-hours). Remaining: iOS (F) and a
deep-link-to-the-exact-alert nicety (tapping currently just opens the app). This
documents **native push notifications** for the mobile app — an alert on your
phone even when the app is closed, the mobile-native equivalent of the Telegram
pings you already get.

> Scope note: this is a **single-user** design (matches where the app is today —
> your phone, your backend, over Tailscale). It's built so it becomes per-user
> cleanly when the multi-tenant work lands (see
> `STOCKPULSE_MOBILE_APP_PLAN.md` §4).

---

## 1. Why

Today alerts reach you via **Telegram**. A dedicated app should also be able to
notify you directly — a lock-screen notification that taps through to the alert.
Push is a **second channel**, not a replacement: keep Telegram, add push. The
backend already has a per-alert *channel* concept, so push slots in beside it.

---

## 2. Architecture

```
  App (first run)                    Backend                     Expo + Google/Apple
  ─────────────                      ───────                     ───────────────────
  ask permission
  get Expo push token  ──POST /api/push/register──►  store token
                                                     │
  (later) new important alert fires ────────────────►│ send via Expo Push API
                                                     │   (token + title + body + data)
                                                     └──────────────►  exp.host ──► FCM/APNs ──► 🔔 phone
  tap the notification ◄───────────────────────────────────────────────────────────────────────┘
  → app opens the alert (deep link via data.alertId)
```

- **Expo push token** = a device address Expo issues (`ExponentPushToken[…]`).
- The backend calls the **Expo Push API** (`https://exp.host/--/api/v2/push/send`)
  — Expo relays to **FCM** (Android) / **APNs** (iOS). We never talk to FCM/APNs
  directly.

---

## 3. The one real prerequisite — FCM (Android)  ✅ done

A standalone app (your EAS-built APK) needs **Firebase Cloud Messaging**
configured for Android delivery. One-time setup, ~15 min.

> ⚠️ **Two different JSON files — don't mix them up** (this is the confusing part):
> - **`google-services.json`** → lives in your **app** (`mobile/`), referenced by
>   `app.json`. Identifies the app to Firebase.
> - **Service-account key** → uploaded to **EAS**, lets Expo *send* pushes for you.
>   A different file, from a different place in the Firebase console.

**Steps:**
1. **Firebase project** — create one at <https://console.firebase.google.com>.
2. **Add an Android app** with the package name **`com.ndtai2202.stockpulse`**
   (from `mobile/app.json`).
3. **Download `google-services.json`** → drop it in `mobile/`, and reference it in
   `app.json`: `"android": { "googleServicesFile": "./google-services.json" }`.
4. **Generate the service-account key** — Firebase → ⚙️ **Project settings** →
   **Service accounts** tab → **Generate new private key** → downloads a `.json`
   (its contents start with `{"type": "service_account", ...}`). Keep it private;
   **don't commit it.**
5. **Upload it to EAS:** `eas credentials` → **Android** → **Google Service
   Account** → **"Push Notifications (FCM V1)"** →
   **"Set up a Google Service Account Key…"** → give it the path to the JSON from
   step 4.
   - ⚠️ **Do NOT pick "Push Notifications (Legacy)"** — that's the old FCM Legacy
     API, **shut down by Google in June 2024**. It won't deliver.
   - ⚠️ **"Set up…"**, not **"Select an existing…"** — "existing" only lists keys
     already on EAS (you have none the first time). "Set up" is the one that
     *uploads* your downloaded file.
6. **Rebuild the APK** — adding push is a **native** change, so it needs a fresh
   `eas build -p android --profile preview` (**not** an OTA update). Install it
   once. Credentials attach to the *project*, so the `preview` profile is correct.

**Verify:** open the app → grant the notification prompt (this registers the
token) → `POST /api/push/test` on the server → 🔔 (see §7).

> **iOS** additionally needs an **Apple Developer account** ($99/yr) for APNs.
> Deferred — Android first.

---

## 4. Mobile changes

- **Install:** `npx expo install expo-notifications`.
- **`app.json`:** add the `expo-notifications` plugin (notification icon + accent
  color `#6495ED`) and the `googleServicesFile` above.
- **Register (once, after first run):** request permission →
  `Notifications.getExpoPushTokenAsync({ projectId })` (we already have the
  projectId) → `POST /api/push/register` with the token. Store nothing sensitive
  locally.
- **Android channel:** create a default notification channel (required on
  Android 8+) with the brand accent.
- **Tap handling:** `addNotificationResponseReceivedListener` → read
  `data.alertId` → navigate to **Alert detail**. (v1 can just open the Feed and
  refresh; a fetch-by-id deep link is a small follow-up — needs a
  `GET /api/feed/{id}` or reuse the feed list.)
- **Where it lives:** a small `mobile/src/push.ts` (register + listeners), called
  from `App.tsx` on mount.

---

## 5. Backend changes

All additive; nothing in the existing alert/Telegram path changes.

- **Token storage (MVP):** a `push_tokens.json` in the `./data` volume (like
  `runtime_prefs.json`) holding a list of registered tokens. Becomes a per-user
  `push_devices` table in the multi-tenant phase.
- **Push notifier:** `app/push/notifier.py` — `send_push(tokens, *, title, body,
  data)` posting to the Expo Push API (batched, best-effort, logs failures).
  Isolated behind a function with an injectable transport, like every other
  outbound client (testable with `httpx.MockTransport`).
- **Endpoints** (token-guarded, same as the other `/api/*`):
  - `POST /api/push/register` `{token, platform?}` → save token.
  - `POST /api/push/test` → send a test push to all registered tokens (verify the
    whole path before wiring to alerts).
  - `POST /api/push/unregister` `{token}` → remove (e.g. on sign-out).
- **Wire into alerts:** in the news monitor's send step (where Telegram alerts go
  out), also push registered tokens for each newly-sent alert:
  - `title` = e.g. `🔴 HIGH · NVDA` (importance + sentiment + primary ticker)
  - `body` = the AI summary
  - `data` = `{ alertId }` for the deep link
  - Respect the same **quiet hours** + **importance threshold** already applied to
    Telegram (don't push what you wouldn't send).

---

## 6. Config (proposed)

```
PUSH_ENABLED=false                 # master switch
PUSH_TOKENS_FILE=push_tokens.json  # redirected into ./data in Docker
EXPO_ACCESS_TOKEN=                 # optional; enables Expo's enhanced push security
```
All gated by the existing `MOBILE_API_ENABLED` (the endpoints live under `/api`).

---

## 7. Testing

- **Unit:** `send_push` against `httpx.MockTransport` (payload shape, batching,
  failure handling); endpoint auth (404 disabled / 401 no-token / 200).
- **End-to-end (manual, needs the rebuilt APK):**
  1. Open the app → grant notification permission → it registers the token.
  2. `POST /api/push/test` → a notification appears on the phone. ✅
  3. (Or paste the token into <https://expo.dev/notifications> to send a test.)
  4. Then let a real alert fire (or `POST /run`) and confirm the push arrives and
     taps through.

---

## 8. Suggested build order

| Step | Piece | Needs FCM? | Status |
|---|---|---|---|
| A | Backend: token storage + `send_push` (Expo API) + register/test endpoints + tests | no | ✅ done |
| B | Mobile: `expo-notifications`, permission, get token, register, Android channel | no | ✅ done |
| C | **FCM setup** (Firebase + EAS credentials) + rebuild APK | **yes** | ✅ done |
| D | Verify with `POST /api/push/test` on the real device | yes | ⬜ verify |
| E | Wire push into the alert send path (quiet hours + threshold) | yes | ✅ done |
| F | (later) iOS: Apple Developer account + APNs; deep-link tap → exact alert | — | ⬜ |

A–E are shipped. Turn it on with **`PUSH_ENABLED=true`** on the server; every
alert that goes to Telegram now also pushes (same quiet-hours + importance
gating). Tapping a notification opens the app; jumping to the *exact* alert
(needs a `GET /api/feed/{id}` + a navigation ref) is the remaining nicety.

---

## 9. Risks & open questions

1. **FCM setup friction.** The Firebase + service-account steps are the only
   fiddly part; §3 lists them. One-time.
2. **Expo Go can't do remote push** (dropped in SDK 53+) — testing is on the
   **EAS build** only. You already use one.
3. **Deep link depth for v1.** Open the app to the Feed (simple) vs fetch the
   exact alert by id (needs a small `GET /api/feed/{id}`)? Lean: Feed first,
   by-id as a fast follow.
4. **Token lifecycle.** Tokens can rotate; re-register on each app launch and
   dedupe server-side. Prune tokens Expo reports as invalid (from receipts) —
   nice-to-have, not v1.
5. **Notification volume.** Reuse the existing importance threshold + quiet hours
   so push isn't noisier than Telegram. Consider a separate
   `PUSH_MIN_IMPORTANCE` later.
6. **Single- vs multi-user.** MVP stores tokens globally; the multi-tenant phase
   keys them by user and routes per-user (already anticipated in the mobile plan).
