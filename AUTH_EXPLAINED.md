# Login, tokens and going public — what actually happens, and why

You want to drop the VPN so your phone stops draining. That one change pulls in
about fifteen unfamiliar words. This doc defines them, then walks the whole
machine end to end, then plays out five real scenarios — including two where
things go wrong and you see what saves you.

No prior security knowledge assumed. Companion to
`specs/STOCKPULSE_AUTH_PLAN.md`, which is the build order; this is the *why*.

---

## Part 1 — The dictionary

Each entry: what it means, and why it matters **for StockPulse specifically**.

### The network words

**Domain / DNS / A record**
A domain (`stockpulse.example.com`) is a name. DNS is the phone book that turns
that name into an IP address. An **A record** is one entry in that phone book:
"this name → this IPv4 address". You will point one at your droplet.
*Why it matters:* HTTPS certificates are issued to **names**, not IP addresses.
No domain, no certificate, no HTTPS. This is why the plan waits on a domain.

**TLS (and "SSL")**
The encryption under HTTPS. It does two things at once: **encrypts** the traffic
so nobody in between can read it, and **authenticates** the server so you know
you're talking to the real one. "SSL" is the dead predecessor; people still say
it, everyone means TLS.
*Why it matters:* your password and tokens travel over this. Without it, anyone
on the same café Wi-Fi reads them in plain text.

**Certificate**
A file proving "this server really is stockpulse.example.com", signed by an
authority browsers already trust.

**Certificate Authority (CA) / Let's Encrypt / ACME**
The CA is the trusted signer. **Let's Encrypt** is a free CA. **ACME** is the
protocol for proving you control a domain and getting a certificate
automatically. Caddy speaks ACME, which is why its config is five lines.

**Certificate Transparency (CT) log**
Every certificate issued is published to a **public, append-only log** — a
deliberate anti-fraud measure, so a CA can't secretly issue a certificate for
your bank. The side effect: **the moment you get a certificate, your hostname is
public knowledge.** Bots watch these logs and probe new names within hours.
*Why it matters:* "nobody knows my URL" is worth exactly nothing. This is the
single most important fact in this document.

**Reverse proxy**
A server that sits in front of your app, terminates TLS, and forwards the plain
request inward. Caddy is one. Your app keeps speaking simple HTTP on
`127.0.0.1:8000` and never deals with certificates.

**Port binding (`127.0.0.1:8000` vs `0.0.0.0:8000`)**
`127.0.0.1` means "only processes on this machine may connect". `0.0.0.0` means
"anyone who can route to me". Your Docker compose binds to `127.0.0.1` — that
single line is why your eleven unauthenticated routes are not currently a
disaster.

**VPN / tailnet**
A private encrypted network. Tailscale builds one across your devices. Your
phone is *inside* the network with the droplet, so no public exposure is needed.
The cost is a permanent connection on the phone — your battery.

### The identity words

**Authentication vs Authorization**
**Authn** = *who are you?* (login). **Authz** = *what may you do?* (permissions).
StockPulse needs authn now. Authz becomes real only with multiple users.

**Credential**
Anything that proves identity: a password, a token, an API key. The rule of
thumb: **treat every credential the way you'd treat a password** — never log it,
never store it in plain text, never put it in a URL.

**Hash**
A one-way function: easy forwards, impossible backwards. `hash("hunter2")` always
gives the same output, but you can't reverse it. Passwords are stored **hashed**
so a stolen database doesn't hand over the passwords themselves.

**Salt**
A random value mixed into each password before hashing, so two users with the
same password get different hashes — and so an attacker can't precompute one
giant table of hashes and look yours up. argon2 and bcrypt generate and store the
salt for you; it's inside the string they output.

**Slow hash (argon2id, bcrypt) vs fast hash (SHA-256)**
This is the counter-intuitive one. **SHA-256 is the wrong tool for passwords
precisely because it is fast** — a GPU tries billions per second. A password hash
must be deliberately **slow** and **memory-hard** (needs lots of RAM, which GPUs
have little of per core), so each guess costs real time and real hardware.
`argon2id` is the current recommendation.

> Rule: SHA-256 for *integrity* ("did this file change?"). argon2/bcrypt for
> *passwords*. Never swap them.

**Timing attack / constant-time comparison**
Comparing two secrets with `==` stops at the first differing character, so a
wrong guess starting with the right letter takes measurably longer. Measure
enough attempts and you can recover a secret one character at a time.
`hmac.compare_digest` always takes the same time regardless.
*Why it matters:* `app/main.py` currently compares your API token with `!=`.
Real risk here is low (network noise swamps the signal), but it's free to fix.

### The token words

**Token**
A string that proves you already logged in, so you don't send your password with
every request.

**Bearer token**
"Whoever *bears* this token gets access" — no further proof required. Like cash:
if someone steals it, it works for them too. Hence short lifetimes.

**JWT (JSON Web Token)**
A token with three dot-separated parts: `header.payload.signature`.

```
eyJhbGciOiJIUzI1NiJ9 . eyJzdWIiOiIxIiwiZXhwIjoxNzY1NH0 . 4f2a9c...
     header                    payload (claims)              signature
```

The payload holds **claims** — facts like `sub` (subject/user id) and `exp`
(expiry). The signature is made with a secret only the server knows.

> **Crucial and widely misunderstood: a JWT is signed, not encrypted.** The
> payload is merely base64 — anyone holding the token can read it. Signing stops
> *tampering*, not *reading*. Never put anything secret in a JWT payload.

**Stateless vs stateful**
A JWT is **stateless**: the server verifies the signature with maths and never
looks in the database. Fast, scales well — and **impossible to revoke**, because
there's nothing to delete. A database-backed token is **stateful**: slower by one
query, but you can kill it instantly. This trade decides §5.4 of the plan.

**Access token / refresh token**
- **Access token** — JWT, ~15 minutes, sent with every request. Short so that a
  leak expires almost immediately.
- **Refresh token** — opaque random string, ~30 days, sent *only* to the refresh
  endpoint, stored hashed in the database. Its one job is minting new access
  tokens, and because it's a database row, it can be revoked.

**Token rotation + reuse detection**
Each refresh returns a **new** refresh token and retires the old one. If a
retired token is ever presented, someone is replaying a stolen copy — so the
server revokes the whole **family** and forces a real login. This converts a
stolen token from silent permanent access into a *detected* event. Scenario 3
below shows it happening.

**Keychain / Keystore / SecureStore**
OS-level encrypted storage for secrets, backed by hardware on modern phones.
`expo-secure-store` wraps both. Plain `AsyncStorage` is an unencrypted file — fine
for "dark mode: on", wrong for a 30-day credential.

### The abuse words

**Brute force** — guessing passwords by volume.
**Credential stuffing** — replaying email/password pairs leaked from *other*
sites, betting on reuse. Far more effective than brute force, which is why
password reuse is the real danger.
**Rate limiting** — capping attempts per account and per IP. Without it, a public
login form is an open invitation; a login endpoint with no limiter is the single
most attacked thing you will own.

---

## Part 2 — The whole machine, end to end

### Today

```
  Phone ──[ Tailscale VPN, always on ]──► Droplet :8000
          the tunnel IS the security          (127.0.0.1 only)
          shared token, baked into the app
```

Two problems: the VPN drains the battery, and the "password" is a fixed string
compiled into the APK — extractable by anyone who downloads the app file.

### After

```
  Phone ──HTTPS──► Caddy :443 ──plain HTTP──► App :8000
                   (TLS, cert)               (127.0.0.1 only)
           access token (15 min) on every request
           refresh token (30 days) in the Keychain
```

The phone has **no VPN and no baked-in secret**. Your password never leaves your
head; the tokens are minted per device and expire on their own.

### Where every secret lives

| Secret | Lives | Protected by |
|---|---|---|
| Your password | your head | you |
| Password hash | droplet database | argon2id (slow, salted) |
| JWT signing secret | droplet `.env` | file permissions |
| Access token | phone RAM + server memory only | 15-minute expiry |
| Refresh token | phone Keychain; **hash** in database | OS encryption + rotation |
| TLS private key | droplet, Caddy-managed | file permissions |

Note the pattern: **the server never stores anything that lets it impersonate
you.** It stores hashes. A stolen database is bad, not fatal.

---

## Part 3 — Five real scenarios

### Scenario 1 — You log in for the first time

```
  PHONE                          CADDY            SERVER              DATABASE
    │                              │                 │                    │
    │ POST /api/auth/login         │                 │                    │
    │ {email, password} ──────────►│ decrypts TLS    │                    │
    │                              │────────────────►│ look up email ────►│
    │                              │                 │◄─── password_hash ─│
    │                              │                 │                    │
    │                              │        argon2.verify(sent, stored)   │
    │                              │        ~100 ms ON PURPOSE            │
    │                              │                 │                    │
    │                              │                 │ mint access JWT    │
    │                              │                 │ mint refresh, store│
    │                              │                 │ its HASH ─────────►│
    │◄── {accessToken, refreshToken} ────────────────│                    │
    │                              │                 │                    │
    │ SecureStore.setItem('refresh', …)   ← Keychain / Keystore           │
    │ keep access token in memory only                                    │
```

Things worth noticing:

- The password is sent **once**, over TLS, and never stored on the phone.
- `argon2.verify` taking ~100 ms is the **feature**, not a performance bug. It
  caps an attacker at ~10 guesses/second/core instead of billions.
- The server stores the refresh token's **hash**. Someone reading your database
  still cannot log in as you.

### Scenario 2 — Twenty minutes later, you open the Predict tab

Your access token expired five minutes ago. You never notice:

```
  PHONE                                          SERVER
    │ GET /api/predict?q=WDC                        │
    │ Authorization: Bearer <expired access> ──────►│ verify signature: OK
    │                                               │ check exp: EXPIRED
    │◄──────────────────────────── 401 Unauthorized │
    │                                               │
    │ (interceptor catches the 401, you see nothing)│
    │ POST /api/auth/refresh {refreshToken} ───────►│ hash it, look it up
    │                                               │ valid, not revoked, not expired
    │                                               │ ROTATE: revoke old,
    │                                               │ issue new pair, same family
    │◄────────────── {new accessToken, new refresh} │
    │ SecureStore.setItem('refresh', new)           │
    │                                               │
    │ retry GET /api/predict (new access) ─────────►│ 200 OK
    │◄──────────────────────────────── the analysis │
```

This is why **one** retry is the right number: if the refresh also fails, the
session is genuinely dead and the user must log in. Retrying more just loops.

### Scenario 3 — Your refresh token is stolen

Say malware copies the token off the phone. It's a bearer token, so it works for
the thief. Rotation is what limits the damage:

```
  t=0   THIEF   refresh(token_A) → gets token_B   ← server retires token_A
  t=1   YOU     refresh(token_A) → token_A is RETIRED
                                    ↓
                server: a retired token was replayed. Only two explanations,
                both bad. Revoke the ENTIRE family (A, B, and any successor).
                                    ↓
        THIEF's token_B is dead. You are logged out and log back in with
        your password — which the thief does not have.
```

Without rotation, a stolen refresh token is **30 days of silent access**. With
it, the theft is *detected* the next time either party refreshes, and the
password becomes the thing that matters again. This is why the plan insists the
refresh token be a revocable database row rather than a JWT.

### Scenario 4 — A bot finds your domain (this will happen)

Hours after your certificate is issued, the hostname appears in CT logs:

```
  BOT                                 WHAT IT HITS         WHAT HAPPENS
   │ GET /                            HTML dashboard       Phase 1: 401 (or not exposed)
   │ POST /run                        pipeline + OpenAI    Phase 1: 401
   │ GET /api/feed                    your alerts          401 — no token
   │ POST /api/auth/login × 10000     login                Phase 5: locked after N,
   │                                                       then exponential backoff
   │ GET /health                      status               200 {"status":"ok"} — and
   │                                                       nothing else. No version,
   │                                                       no config, no hostname.
```

Every one of those is boring **only because Phases 1 and 5 happened first**.
Without Phase 1, `POST /run` is an anonymous button that spends your OpenAI
credit. This is precisely why the plan orders auth before exposure.

### Scenario 5 — You lose the phone

```
  On the droplet:  revoke every refresh token for your user (one UPDATE)
  Result:          the lost phone's next refresh → 401 → forced login screen
                   your new phone logs in with the password, unaffected
```

Try that with the current design: the shared token is compiled into the app, so
"revoking" it means changing the server token and rebuilding the app — and it
locks out every device at once, including yours.

---

## Part 4 — Building the mental model

Three ideas that transfer far beyond this project:

**1. Security is layers, and one of yours is about to be removed.**
Right now: network layer (Tailscale) + a weak shared secret. After: network layer
gone, replaced by TLS + real identity + rate limits. The mistake to avoid is
removing the first layer *before* the replacements exist — which is the entire
reason the plan is ordered the way it is.

**2. Make the expensive operations cheap for you and expensive for attackers.**
argon2 costs you 100 ms once per login, and costs an attacker their entire
strategy. Rate limiting costs you nothing and costs them everything. Good security
is usually asymmetric like this — when a measure hurts you as much as the
attacker, it's usually the wrong measure.

**3. Assume every secret you ship will be read.**
`EXPO_PUBLIC_API_TOKEN` lives inside your APK today. Anything shipped to a client
— mobile app, web page, desktop binary — is readable by whoever holds it. The
only real secrets are the ones that never leave the server, plus the one in your
head. Notice that the end state has **no secret in the app at all**. That's the
actual prize here, more than the battery.

---

## Mini-glossary (the one-line version)

| Term | One line |
|---|---|
| A record | DNS entry mapping a name to an IP |
| ACME | Protocol for getting certificates automatically |
| Access token | Short-lived proof of login, sent on every request |
| argon2id | Slow, memory-hard password hash — the right one |
| Bearer token | Whoever holds it gets in; treat like cash |
| Brute force | Guessing passwords by volume |
| CA | The authority that signs certificates |
| Constant-time compare | Comparison that leaks no timing information |
| Credential stuffing | Replaying passwords leaked from other sites |
| CT log | Public list of every certificate issued — makes hostnames public |
| Hash | One-way function; easy forwards, impossible backwards |
| JWT | Signed (not encrypted!) token carrying claims |
| Keychain / Keystore | OS-level encrypted storage for secrets |
| Rate limiting | Capping attempts per account and per IP |
| Refresh token | Long-lived, revocable, mints access tokens |
| Reverse proxy | Sits in front of your app, terminates TLS |
| Rotation | Each refresh issues a new token, retiring the old |
| Salt | Random per-password value; defeats precomputed tables |
| Stateless | Verifiable without a database lookup — and unrevocable |
| TLS | The encryption + server authentication under HTTPS |
