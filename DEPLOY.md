# Deploying StockPulse 24/7 (small VPS + Docker)

StockPulse is a **single always-on process**: the scheduler (news alerts,
market briefings), the `/report` Telegram listener, and the web dashboard all
run inside one container. It is **not** serverless — it must stay up. A cheap
Linux VPS (~$4–6/mo: Hetzner, DigitalOcean, Linode, …) is the simplest home.

It needs **no inbound ports**: everything is outbound (OpenAI, Telegram,
Alpaca), and Telegram uses polling, not webhooks. The dashboard is optional and
bound to localhost — you reach it over an SSH tunnel. Minimal attack surface.

> **New to servers?** Start with **[BUYING_A_SERVER.md](BUYING_A_SERVER.md)** —
> it walks you through picking a provider, making an SSH key, creating the
> server, and logging in for the first time. Then come back here at step 2.

---

## 1. Provision a server

Create a small VPS running **Ubuntu 24.04 LTS** (1 vCPU / 1 GB RAM is plenty).
SSH in as a sudo user.

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"      # run docker without sudo
# log out and back in so the group change takes effect
docker --version && docker compose version
```

## 3. Get the code

```bash
git clone <your-repo-url> stockpulse
cd stockpulse
```

## 4. Configure

```bash
# Secrets + settings
cp .env.example .env
nano .env        # fill in the keys and toggles (see below)

# Local config (which tickers / keywords to watch)
cp watchlist.example.json watchlist.json && nano watchlist.json
cp keywords.example.json  keywords.json  && nano keywords.json
```

Minimum to set in `.env`:

```
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OUTPUT_LANGUAGE=Vietnamese

# Turn the automation on (off by default so nothing runs unexpectedly):
SCHEDULER_ENABLED=true     # runs the news-alert jobs AND the briefing schedule
BRIEFING_ENABLED=true      # 08:30 -> every 2h -> 18:00 PT briefs (starting times;
                           # change them later from the app, no restart needed)
BRIEFING_COMMAND_ENABLED=true   # /report from your phone (needs Telegram creds)
```

> The `DATABASE_URL` and `BRIEFING_MEMORY_FILE` are overridden by
> `docker-compose.yml` to live in the `./data` volume — leave them alone. Same
> for `PREFS_FILE`, `PUSH_TOKENS_FILE` and `STRATEGIES_FILE`, which hold state
> you set from the app (language, briefing schedule, custom strategies) and must
> survive a rebuild.

## 5. Launch

```bash
docker compose up -d --build
docker compose logs -f          # watch it start (Ctrl+C stops watching, not the app)
```

You should see `Applying database migrations`, then `Scheduler ENABLED …` and
`Briefing scheduled (mon-fri): morning 08:30 … America/Los_Angeles`.

`restart: unless-stopped` means it comes back after a crash or a server reboot.

## 6. See the dashboard (optional)

It's bound to localhost on the server. From your laptop:

```bash
ssh -L 8000:127.0.0.1:8000 user@your-server
# then open http://127.0.0.1:8000 in your browser
```

(To expose it publicly instead, change the compose `ports` to `"8000:8000"` and
put a reverse proxy with authentication in front — don't publish it raw.)

---

## Day-2 operations

**Trigger a briefing now:** `/report` in Telegram, or
`curl -X POST http://127.0.0.1:8000/report` on the server.

**Update to the latest code:**
```bash
cd stockpulse && git pull
docker compose up -d --build
```

**Change settings:** edit `.env`, then `docker compose up -d` (recreates the
container with the new env).

**Logs / status:**
```bash
docker compose logs -f          # follow
docker compose ps               # is it up?
docker compose restart          # bounce it
docker compose down             # stop
```

**Back up your data** (the DB + prediction history + theme memory):
```bash
cp -r data data-backup-$(date +%F)
```
Everything durable lives in `./data`; `.env`, `watchlist.json`, and
`keywords.json` are your config. Nothing else needs backing up.

---

## Notes & gotchas

- **Timezones are in-app.** The briefing fires on `BRIEFING_TIMEZONE`
  (America/Los_Angeles) and quiet hours on `TIMEZONE`, regardless of the
  server's clock — you don't need to set the server timezone. `tzdata` is
  installed in the image.
- **Cost.** Hosting is ~$4–6/mo; the real variable cost is OpenAI usage
  (classification per new article + one briefing call per scheduled/On-demand
  run). Start with the defaults and watch your OpenAI dashboard.
- **`SCHEDULER_ENABLED=true` turns on the news-alert jobs too**, not just
  briefings. If you only want briefings, that's fine — they share the scheduler.
- **Web search (briefing step H) is off.** Retrieval is the two RSS feeds only
  until `BRIEFING_WEB_SEARCH_ENABLED` is wired.
