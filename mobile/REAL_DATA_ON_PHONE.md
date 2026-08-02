# Real data on your phone — a follow-along walkthrough

Follow top to bottom. After each step there's a **✅ Checkpoint** — don't move on
until it passes. If a checkpoint fails, see **Troubleshooting** at the bottom.

**What you'll end up with:** your real StockPulse alerts on your phone, reached
over a private network (Tailscale) — nothing exposed to the public internet.

**Before you start, have:**
- SSH access to your droplet (the one running StockPulse).
- Your phone.
- The `mobile/` project on your computer (`npm install` already run).

---

## Step 1 — Turn on the API on the droplet

```bash
ssh user@your-droplet-ip
cd ~/stock-pulse
git pull
openssl rand -hex 24          # 👈 COPY this token somewhere; you'll reuse it
nano .env
```
Add these two lines to `.env` (paste your token), then save (`Ctrl+O`, Enter, `Ctrl+X`):
```
MOBILE_API_ENABLED=true
MOBILE_API_TOKEN=<paste-your-token>
```
Rebuild:
```bash
docker compose up -d --build
```

**✅ Checkpoint 1** — on the droplet, this returns JSON (not an error):
```bash
curl -H "Authorization: Bearer <your-token>" http://127.0.0.1:8000/api/feed
```
You should see `{"alerts":[...],"generated_at":"..."}`. (Empty `alerts` is fine —
it just means no fresh classified news yet.)

---

## Step 2 — Install Tailscale on the droplet

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
It prints a URL — open it in any browser and log in (Google/GitHub/email). That
account is your private network ("tailnet").

**✅ Checkpoint 2** — this prints an IP like `100.x.y.z` and your machine name:
```bash
tailscale ip -4
tailscale status
```

---

## Step 3 — Expose the app over the tailnet (private, HTTPS)

```bash
sudo tailscale serve --bg 8000
```
It prints a URL like:
```
https://your-droplet.tailXXXX.ts.net/
```
👉 **Copy that URL.** It's reachable **only by your own devices**, never the
public internet, and it's HTTPS.

> If it complains that HTTPS isn't enabled: open the Tailscale **admin console →
> DNS**, enable **MagicDNS** and **HTTPS Certificates**, then re-run the command.

**✅ Checkpoint 3** — still on the droplet:
```bash
curl https://your-droplet.tailXXXX.ts.net/health
```
returns `{"status":"ok",...}`.

---

## Step 4 — Put your phone on the tailnet

- Install **Tailscale** from the Play Store.
- Log in with the **same account** as the droplet.
- Toggle Tailscale **ON**.

**✅ Checkpoint 4** — in your **phone's browser**, open:
```
https://your-droplet.tailXXXX.ts.net/health
```
You should see `{"status":"ok",...}`. 🎉 Your phone can now reach your droplet
privately.

---

## Step 5 — Point the app at it

On your computer, in the `mobile/` folder, create `.env.local` (copy from
`.env.example`) with your URL + token:
```
EXPO_PUBLIC_API_BASE_URL=https://your-droplet.tailXXXX.ts.net
EXPO_PUBLIC_API_TOKEN=<the same token from Step 1>
```
This file is gitignored — the token stays off git, and you set it **once**.

**✅ Checkpoint 5** — quick sanity in the browser (Tailscale on your computer too,
or you're on the same network): run `npm run web` in `mobile/` and the Feed loads
real alerts, header no longer says "SAMPLE DATA".

---

## Step 6 — Build the APK once (with OTA)

For a cloud build, register the two values with EAS once, then build:
```bash
cd mobile
eas login
eas env:create --name EXPO_PUBLIC_API_BASE_URL --value https://your-droplet.tailXXXX.ts.net --environment preview
eas env:create --name EXPO_PUBLIC_API_TOKEN   --value <token> --environment preview
eas build -p android --profile preview
```
When it finishes, open the link it prints **on your phone**, download the APK, tap
to install.

**✅ Checkpoint 6** — open the app (Tailscale ON). The Feed shows your **real
alerts**. Done. 🎉

---

## Step 7 (from now on) — update without reinstalling

Change any UI/JS and push it over the air:
```bash
cd mobile
eas update --branch preview --message "what changed"
```
Reopen the app on your phone — it pulls the update on next launch. Rebuild the APK
only for native changes (icon, SDK bump, new native module).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Checkpoint 1 fails (curl error) | Container didn't rebuild, or `.env` typo. `docker compose logs -f`. |
| Checkpoint 1 returns `401` | Token in the curl header ≠ `MOBILE_API_TOKEN` in `.env`. |
| Checkpoint 3/4: "HTTPS not enabled" | Enable MagicDNS + HTTPS certs in the Tailscale admin console. |
| Checkpoint 4 fails on phone | Tailscale toggled **on**? Same account as the droplet? |
| App shows `401` | `EXPO_PUBLIC_API_TOKEN` in `.env.local`/EAS ≠ server token. |
| Feed says "All caught up" | Backend has no fresh classified news. Trigger a run or wait, pull-to-refresh. |
| `eas update` didn't show | Fully close & reopen the app; updates apply on next launch. |

Stuck at a checkpoint? Tell me the number and what you saw — I'll help.
