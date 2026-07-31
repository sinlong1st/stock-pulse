# Getting real data onto your phone — step by step

Two problems to solve, and this guide does both safely:

1. **Reach** — your phone (on cellular/Wi-Fi) needs to talk to your droplet,
   **without exposing the droplet to the public internet** (it has powerful
   unauthenticated endpoints like `POST /run` you must never make public).
   → We use **Tailscale**, a private network just for your own devices.
2. **Code** — the installed app needs the new fetch code + config.
   → We build the APK **once** with over-the-air updates enabled, then push
   future changes with `eas update` (no reinstalling).

---

## Part A — Enable the API on the droplet (one-time)

If you haven't already (from the deploy instructions):

```bash
ssh user@your-droplet-ip
cd ~/stock-pulse
git pull
openssl rand -hex 24          # copy this token
nano .env                     # add the two lines below, paste the token
#   MOBILE_API_ENABLED=true
#   MOBILE_API_TOKEN=<token>
docker compose up -d --build
# verify:
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/feed
```

The app stays bound to `127.0.0.1` — **nothing is public**. Tailscale (next)
reaches it privately.

---

## Part B — Tailscale: a private network for your devices

### On the droplet
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
It prints a URL — open it in a browser and log in (Google/GitHub/email). The
droplet is now on your private "tailnet".

Then expose the local app **over the tailnet only**, with automatic HTTPS:
```bash
sudo tailscale serve --bg 8000
```
It prints a URL like:
```
https://your-droplet.tailXXXX.ts.net/
```
That URL:
- works **only** from devices logged into *your* Tailscale account,
- is **not** reachable from the public internet,
- is **HTTPS**, so your token isn't sent in the clear.

> If it says HTTPS isn't enabled, open the Tailscale admin console → **DNS** →
> enable **MagicDNS** and **HTTPS Certificates**, then re-run the command.

### On your phone
- Install **Tailscale** from the Play Store, log in with the **same account**.
- Toggle it **on**. Your phone can now reach `https://your-droplet.tailXXXX.ts.net`.

Quick test: open that URL (with `/health`) in your phone's browser —
`https://your-droplet.tailXXXX.ts.net/health` should return
`{"status":"ok",...}`.

---

## Part C — Build the APK once (with OTA enabled)

The project is now configured for OTA updates (`expo-updates` + a `runtimeVersion`
+ update URL in `app.json`, and a `preview` channel in `eas.json`). Build once so
the installed app knows how to fetch updates:

```bash
cd mobile
# point the app at your tailnet URL + token FIRST (see Part E), then:
eas login                                   # if not already
eas build -p android --profile preview
```
Install the resulting APK on your phone (open the link it prints, download, tap).
**From now on you rarely rebuild** — see Part D.

---

## Part D — Push changes without reinstalling (the payoff)

Any time you change the app's JavaScript/UI (including `config.ts`):

```bash
cd mobile
eas update --branch preview --message "point at tailnet + tweak feed"
```
Open the app on your phone — it pulls the update on the next launch. No new APK,
no store, no reinstall. (Channel `preview` and branch `preview` auto-link because
they share a name.)

Rebuild the APK **only** when you change native things (new native module, app
icon, SDK bump).

---

## Part E — Point the app at your droplet

You set this **once**, in a gitignored env file (so the token never touches git).
Create `mobile/.env.local` (copy from `.env.example`):
```
EXPO_PUBLIC_API_BASE_URL=https://your-droplet.tailXXXX.ts.net
EXPO_PUBLIC_API_TOKEN=<the same MOBILE_API_TOKEN>
```
Local dev (`npm start` / `npm run web`) and `eas update` read this automatically.
For a cloud `eas build`, set the same two as EAS environment variables once:
```bash
eas env:create --name EXPO_PUBLIC_API_BASE_URL --value https://your-droplet.tailXXXX.ts.net --environment preview
eas env:create --name EXPO_PUBLIC_API_TOKEN   --value <token> --environment preview
```
Then rebuild (Part C) or `eas update` (Part D). Open the app → the **Feed** shows
your real StockPulse alerts, pull-to-refresh works, "SAMPLE DATA" is gone.

> You do **not** re-enter the token each time — it lives in `.env.local` (and, for
> cloud builds, in EAS). Set it once per environment.

---

## Troubleshooting

- **Feed empty ("All caught up")** — backend has no market-relevant classified
  articles yet. Trigger a run or wait for the scheduler, then pull-to-refresh.
- **Can't reach the URL on the phone** — is Tailscale toggled **on**? Is the
  phone logged into the same account? Try `/health` in the phone browser first.
- **401** — `API_TOKEN` in `config.ts` must exactly match `MOBILE_API_TOKEN`
  in the droplet `.env`.
- **Update didn't show** — fully close and reopen the app; `eas update` applies
  on next launch, and only to builds with the same `runtimeVersion` (app version).
```
