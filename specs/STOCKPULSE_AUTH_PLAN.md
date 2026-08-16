# StockPulse — Public access and login, a plan

Written to be read as much as followed. Where a choice was made, the rejected
alternatives are here too, with the reason — that is usually the part worth
knowing later.

---

## 1. Why this exists

The phone reaches the droplet through **Tailscale**, which means the Tailscale
VPN runs on the phone all day. A VPN client holds a persistent connection and
wakes the radio to keep it alive, which is why the battery goes down faster.
That is not a bug to tune around; it is what an always-on tunnel costs.

So the goal is: **reach the backend over ordinary HTTPS, with no VPN on the
phone.** Everything else in this document follows from that one sentence.

## 2. What Tailscale is actually doing (and why removing it is not one job)

Tailscale is quietly doing **two** unrelated things:

| Job | How Tailscale does it | What has to replace it |
|---|---|---|
| **Reachability** — the phone can find and connect to the droplet | A private encrypted network; the droplet needs no open port | A public domain + TLS + a reverse proxy |
| **Authentication** — only *your* devices can connect at all | Only devices on your tailnet exist, as far as the server is concerned | Real application-level auth: login |

Almost every plan for "get rid of the VPN" quietly forgets the second column.
That is the dangerous half.

## 3. The thing that makes this urgent

`app/main.py` has **eleven routes with no authentication whatsoever**:

```
GET  /            GET  /alerts         POST /classify
GET  /evaluation  POST /alerts/send    POST /run
POST /evaluate    POST /report         GET  /collect
POST /evaluate/digest                  GET  /health
```

Today that is fine, because the app binds to `127.0.0.1:8000` and the only route
in is the tailnet. The moment a public proxy forwards :443 to :8000, **all of
them are on the open internet**, including:

- `POST /run`, `POST /classify`, `POST /report` — each spends **your OpenAI
  credit**. An attacker doesn't need your data to hurt you; they can just run up
  the bill.
- `POST /alerts/send`, `POST /evaluate/digest` — send **Telegram messages to
  your phone**.
- `GET /`, `/alerts`, `/evaluation` — HTML dashboards showing **your watchlist,
  your positions and your P&L**.

> **"Nobody will find the URL" is not a defence.** The moment Let's Encrypt
> issues a certificate for your domain, that hostname is published in the public
> **Certificate Transparency** logs, which are indexed and scanned continuously.
> Expect automated probes within hours, not months. Obscurity buys nothing.

**Conclusion: the auth work must land before, or in the same change as, the
public endpoint. Never the other way round.**

## 4. Threat model

Worth writing down, because it decides how much machinery is justified.

| Asset | Attack | Cost if it happens |
|---|---|---|
| OpenAI credit | Hitting `/report` or `/predict` in a loop | Money, uncapped |
| Telegram channel | Hitting `/alerts/send` | Spam to your phone |
| Your holdings & P&L | Reading `/alerts`, `/api/positions` | Privacy — this is financial data about you |
| Watchlist / positions | POST/PUT/DELETE | Corrupted data, wrong advice |
| The droplet itself | Anything that leads to code execution | Total |

Attacker profile: **not** someone targeting you personally. It's automated
scanning — bots that walk CT logs, try common paths, and hammer login forms with
credential lists. The defence has to work against volume and indifference, which
is actually easier than defending against a determined human.

---

## 5. The stack, and why

### 5.1 Edge: **Caddy** on the droplet

Caddy is a web server that terminates TLS and forwards to the app.

```caddyfile
stockpulse.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

That is the entire config. Caddy obtains a Let's Encrypt certificate on first
boot, renews it automatically, and redirects HTTP to HTTPS.

**Alternatives considered:**

- **nginx + certbot** — the traditional pairing, and what most tutorials show.
  Rejected because certificate renewal is a separate cron job that fails
  silently, and nginx buffers proxied responses by default, which would break
  SSE (see §9). More moving parts for no gain here.
- **Cloudflare Tunnel** — genuinely good: no open ports at all, free DDoS
  absorption, and the droplet stays invisible. Rejected as the *default* because
  it adds a third-party dependency in the request path and another dashboard to
  understand, and it does not remove the need for login. Worth revisiting if the
  droplet ever gets scanned aggressively.
- **Keep Tailscale, fix the battery** — there is no fix; an always-on tunnel is
  the cost of the model. Turning Tailscale on only when opening the app works
  but is a manual step before every use.

### 5.2 Authentication: **email + password → JWT**

**Alternatives considered:**

- **Magic link (emailed one-time link)** — no passwords to store or leak, which
  is a real advantage. Rejected because it needs a reliable transactional email
  provider, and every login becomes "go find the email", which is miserable for
  an app you open several times a day.
- **Google / Apple sign-in (OAuth)** — no password storage, users already have
  the account. Rejected *for now*: it needs a native SDK (an APK rebuild), a
  Google Cloud project, and platform review for Apple. Worth doing when the app
  goes multi-user; overkill for one user today.
- **Per-device tokens issued after a one-time code** — closest to what exists.
  Rejected because it is a bespoke scheme, and bespoke auth is where security
  bugs live. Standard beats clever.

So: email + password, which is boring, well-understood, and the thing worth
learning properly.

### 5.3 Password storage: **argon2id**, never a plain hash

This is the part people get wrong, so it is worth being explicit.

`sha256(password)` is **wrong**, even with a salt. SHA-256 is designed to be
*fast* — billions of guesses per second on a GPU. A password hash must be
deliberately **slow and memory-hard**, so that each guess costs the attacker
real time and real RAM.

- **argon2id** — winner of the Password Hashing Competition, memory-hard,
  the current default recommendation. Python: `argon2-cffi`.
- **bcrypt** — older, still fine, widely deployed. Acceptable if argon2 is
  awkward to install.
- **scrypt / PBKDF2** — acceptable, in that order of preference.

Salting is not a separate decision: argon2 and bcrypt both generate and embed a
per-password salt automatically. Store the single string they produce.

### 5.4 Sessions: short **access token** + long **refresh token**

Two tokens, doing different jobs:

- **Access token** — a JWT, signed with a server secret, **15 minutes**, sent on
  every request. Stateless: the server verifies the signature and does not touch
  the database. If it leaks, it expires almost immediately.
- **Refresh token** — an **opaque random string** (not a JWT), **30 days**, sent
  only to `/api/auth/refresh`, stored in the database **hashed** (it is a
  credential, so treat it like a password).

**Why the refresh token is deliberately not a JWT:** a JWT cannot be revoked —
it is valid until it expires, because verification is just a signature check.
That is fine for 15 minutes and unacceptable for 30 days. An opaque token is a
database row, so "log out this device" and "revoke everything" are one `UPDATE`.

**Rotation with reuse detection** (the OWASP recommendation): every refresh
issues a *new* refresh token and retires the old one. If a retired token is ever
presented again, that means someone is replaying a stolen one — so revoke the
entire family and force a fresh login. This is what turns a stolen token from
permanent access into a detectable event.

### 5.5 On the phone: **expo-secure-store**

The refresh token is a 30-day credential and must not sit in plain
`AsyncStorage`. `expo-secure-store` uses the iOS Keychain and Android Keystore /
EncryptedSharedPreferences.

> ⚠️ **This is a native dependency, so it needs a full `eas build` APK, not an
> OTA update.** Bump `app.json` version accordingly. Everything else in this
> plan ships over the air; this one line does not. See `mobile/AGENTS.md`.

### 5.6 No public signup

There is one user. A registration endpoint would let anyone create an account on
your server, and "sign up then use their OpenAI credit" is the whole attack.

The first user is created by a **one-off CLI command on the droplet**
(`python -m app.auth.create_user`). Registration can be designed properly if the
app ever goes multi-user — that is a product decision, not an auth one.

---

## 6. Data model

One new table. Refresh tokens get their own rows so they can be revoked
individually — that is the entire point of §5.4.

```
users
  id · email (unique, lowercased) · password_hash · created_at
  last_login_at · failed_attempts · locked_until

refresh_tokens
  id · user_id → users.id · token_hash (unique) · family_id
  issued_at · expires_at · revoked_at · replaced_by · user_agent
```

`family_id` groups a chain of rotated tokens so reuse detection can kill the
whole lineage at once.

## 7. API surface

```
POST /api/auth/login     {email, password}   → {accessToken, refreshToken, expiresIn}
POST /api/auth/refresh   {refreshToken}      → {accessToken, refreshToken, expiresIn}
POST /api/auth/logout    {refreshToken}      → 204        (revokes one device)
GET  /api/auth/me                            → {email, createdAt}
```

Every existing `/api/*` route swaps `_require_mobile_api` for a
`current_user` dependency. The eleven open routes from §3 get the same treatment
or are removed — see §8, Phase 1.

## 8. Phases

Ordered so that **the server is never publicly reachable without auth**, and
each phase leaves a working system.

### Phase 1 — Close the open routes ⭐ do this first, it is useful regardless

Put every route behind auth, or delete it. The HTML dashboards (`/`, `/alerts`,
`/evaluation`) are developer tools reachable over the SSH tunnel; the trigger
endpoints (`/run`, `/classify`, `/report`, `/collect`, `/alerts/send`) are
operational. Two honest options: gate them behind the same auth, or bind them to
localhost only and keep using `ssh -L`.

`/health` stays open and returns **only** `{"status":"ok"}` — no version, no
config. Uptime checks need it; attackers should learn nothing from it.

*Ships:* a meaningfully safer server, before anything is exposed.

### Phase 2 — Users, hashing, tokens (backend, no wiring yet)

`app/auth/`: the model, argon2 hashing, JWT issue/verify, refresh rotation with
reuse detection, and the `create_user` CLI. Alembic migration. Unit tests with a
frozen clock for expiry.

*Ships:* nothing user-visible. Fully testable without touching the app.

### Phase 3 — Auth on the API, both schemes accepted

`current_user` dependency on every `/api/*` route. **The old
`MOBILE_API_TOKEN` keeps working**, behind `LEGACY_TOKEN_ENABLED=true`, so the
phone keeps working while the app catches up. Fix the token comparison to
`hmac.compare_digest` while here — the current `!=` leaks timing information.

*Ships:* nothing breaks; two doors, one of which is about to close.

### Phase 4 — Login on the phone

Login screen, `expo-secure-store`, an auth context, automatic refresh on 401 with
a single retry, and "log out" in Settings. **Needs an APK rebuild** (§5.5).

*Ships:* a real login. Still over Tailscale — nothing is public yet.

### Phase 5 — Rate limiting

Per-account and per-IP backoff on login (exponential, plus `locked_until`), and a
per-user daily cap on the endpoints that cost money. Without this, a public login
form is a free brute-force target and `/api/predict` is a free OpenAI meter.

*Ships:* the last thing that must exist before going public.

### Phase 6 — Go public

Domain → droplet A record. Caddy. Verify SSE still streams (§9). Point
`EXPO_PUBLIC_API_BASE_URL` at the new host, ship an OTA, confirm, **then** turn
off Tailscale on the phone.

### Phase 7 — Remove the legacy token

Delete `MOBILE_API_TOKEN` and the flag. One door.

---

## 9. StockPulse-specific gotchas

- **SSE must survive the new proxy.** Report, Predict and the Exit Advisor all
  stream stage events. Tailscale flushes `text/event-stream` correctly; Caddy is
  expected to, but **verify it live with `curl -N`, not with `TestClient`** —
  which buffers and would pass either way. This project has already been bitten
  by exactly that. See `STREAMING_AND_PROXIES.md`. The `X-Accel-Buffering: no`
  header we already send is nginx-specific and stays harmlessly inert.
- **`EXPO_PUBLIC_*` is compiled into the JS bundle.** `EXPO_PUBLIC_API_TOKEN` is
  therefore *inside the app* — extractable from the APK in minutes. It is
  acceptable today only because Tailscale gates the network. It would be
  unacceptable as the only lock on a public endpoint. After Phase 7 the app
  ships with **no secret at all**, which is the real win: the user's password
  never leaves their head, and the tokens are minted per device.
- **The push token flow** (`/api/push/register`) is currently gated by the shared
  token; it should become per-user so notifications follow the account.
- **`positions.json`, `strategies.json`, `runtime_prefs.json` are single-user
  files.** They stay that way for now — this plan adds *authentication*, not
  multi-tenancy. Do not let the two become the same project.
- **Docker binding stays `127.0.0.1:8000`.** Caddy runs on the host and proxies
  in; the app container is never directly exposed.

## 10. What it costs

| | |
|---|---|
| Domain | ~$10–15/year (a `.com`; cheaper TLDs exist) |
| TLS certificate | Free (Let's Encrypt, automatic) |
| Caddy | Free, one binary, ~30 MB RAM |
| New Python deps | `argon2-cffi`, `pyjwt` |
| New native dep | `expo-secure-store` → one APK rebuild |
| Time | Phases 1–3 are the bulk; 4 is a screen; 5–7 are short |

## 11. Open questions

1. **Do you have a domain?** Everything in Phase 6 waits on it. A subdomain of
   something you already own is perfect.
2. **Keep the HTML dashboards?** Gating them behind login is more work than
   binding them to localhost and using `ssh -L` when needed. Which do you want?
3. **Password reset.** With one user and no email provider, "reset" is an SSH
   command. That is fine now and not fine later; it becomes real work when the
   app gets a second user.
4. **Should Cloudflare Tunnel be the default after all?** It removes the open
   port entirely. The trade is a dependency in the request path. Worth a look if
   the domain turns out to attract noise.
