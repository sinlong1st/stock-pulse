# How the mobile app builds, deploys, and runs — a plain-English guide

You already run a **server** (StockPulse's backend on a droplet). A mobile app is
a different animal: instead of running on a computer you control, it's a program
that gets **installed onto each person's phone**. This guide explains, briefly,
how that works and how you ship it.

---

## 1. The big picture

- The app is written once in **TypeScript** (with React Native / Expo).
- That code gets **compiled into a native app** — a single install file per
  platform (Android and iOS).
- People **install that file** on their phone. From then on it runs on *their*
  device, talking to your backend over the internet for data.

So there are really two halves:
- **Your backend** (already live) — the brain: news, AI, prices, the API.
- **The app** — a thin client on the phone that shows the data and sends taps
  back to the backend.

---

## 2. The three ways to run the app (this trips everyone up)

| Way | What it is | When you use it | Ships to users? |
|---|---|---|---|
| **Expo Go** | A generic preview app from the store you load your code into | Quick tests while coding — but its SDK must match your project (the annoying error) | ❌ never |
| **Development build** | *Your own* preview app, compiled for your project | Testing on a real phone without Expo Go's version limits | ❌ dev only |
| **Production build** | The real, standalone app | The finished product | ✅ yes |
| **Web** (`npm run web`) | The same UI in a browser | Fastest loop for UI work, no phone needed | (separate web target) |

**Expo Go = training wheels. The APK/store build = the actual bike.**

---

## 3. The build formats

When you "build" the app, you get a file. Which one depends on the target:

- **APK** (Android) — a standalone install file. **Put it on your phone and tap
  to install**, or send it to a friend. No app store needed. Best for testing.
- **AAB** (Android App Bundle) — the format **Google Play requires** for store
  submission. You can't install it directly; Google turns it into APKs.
- **IPA** (iOS) — the iOS equivalent. iPhones are locked down, so you can't just
  sideload it like an APK — it goes through Apple's TestFlight or the App Store.

For StockPulse, your fastest path onto your own phone is an **APK**.

---

## 4. How you actually build it — EAS

You don't need Xcode or Android Studio. **EAS Build** is Expo's cloud service:
you run a command, Expo compiles the app on their servers, and hands you back a
download link.

The build profiles are set up in [`eas.json`](eas.json):

- **`development`** → a dev build (replaces Expo Go for on-device testing).
- **`preview`** → an **APK** you sideload. ← what you want first.
- **`production`** → an **AAB** for the Play Store.

### The commands (run these on your machine)

```bash
cd mobile
npm install -g eas-cli        # once (or use `npx eas-cli@latest ...`)
eas login                     # once — sign in to a free Expo account (interactive)

# Build an APK you can install directly on your phone:
eas build -p android --profile preview
```

Expo builds it in the cloud (~10–15 min) and prints a **URL**. Open that URL on
your phone → download the APK → tap it → **Install** (Android will ask you to
allow "install from unknown sources" the first time). Done — StockPulse is on
your phone as a real app, no Expo Go involved.

> First run will ask to create an EAS project and add a `projectId` to
> `app.json` — say yes; it's a one-time thing.

---

## 5. Updating the app after it's installed

Two kinds of changes:

- **JavaScript/UI changes** (most of your work) → **`eas update`** pushes an
  **over-the-air** update. Installed apps pick it up on next launch — **no
  rebuild, no store review**. This is a big Expo perk.
- **Native changes** (adding a new native capability, changing the app icon,
  bumping the SDK) → you must **rebuild** the APK/AAB and reinstall / resubmit.

---

## 6. Getting to the stores (later)

When you want strangers to install it:

- **Android:** `eas build -p android --profile production` → an AAB →
  `eas submit -p android` uploads it to the Play Console. ($25 one-time Google fee.)
- **iOS:** needs an **Apple Developer account** ($99/yr). `eas build -p ios` →
  `eas submit -p ios` → TestFlight → App Store review.

This is Phase 5 (§7) of [`../specs/STOCKPULSE_MOBILE_APP_PLAN.md`](../specs/STOCKPULSE_MOBILE_APP_PLAN.md).
It also needs the multi-user backend first — right now the app shows mock data.

---

## 7. Mini-glossary

- **Expo** — the framework the app is built on (stays in the final app).
- **Expo Go** — throwaway preview app for development only.
- **EAS** — Expo's cloud build/submit/update service.
- **APK / AAB / IPA** — the built app files (Android install / Android store / iOS).
- **Sideload** — installing an APK directly, bypassing the store.
- **OTA update** — pushing JS changes to installed apps without a rebuild.
- **Dev build** — your own compiled preview app; the permanent fix for the
  "incompatible Expo Go" error.
```
