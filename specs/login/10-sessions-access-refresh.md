# 10 — Sessions: access and refresh tokens

## The problem

File 09 left us with an impossible-looking choice for token lifetime:

| Lifetime | Consequence |
|---|---|
| **Short** (15 min) | A stolen token dies quickly ✅ … but you re-enter your password four times an hour ❌ |
| **Long** (30 days) | You log in monthly ✅ … but a stolen token grants a month of access you cannot revoke ❌ |

Pick either and something important is wrong. The way out is to stop treating it
as one problem.

## The idea

Issue **two** tokens with different jobs, different lifetimes, and different
security properties.

| | Access token | Refresh token |
|---|---|---|
| Format | **JWT** (self-describing) | **Opaque random string** |
| Lifetime | ~15 minutes | ~30 days |
| Sent | with **every** request | **only** to `/api/auth/refresh` |
| Stored server-side | no | yes — **hashed** |
| Revocable | no | **yes** |
| Its one job | prove identity, cheaply | mint new access tokens |

The insight: **the token used constantly is short-lived, and the long-lived token
is used almost never.** Exposure and lifetime are inverted relative to each other.

```
  ┌────────── 30 days ──────────────────────────────────┐
  │ refresh token — leaves the Keychain ~96 times total  │
  └──────────────────────────────────────────────────────┘
   ┌─ 15m ─┐┌─ 15m ─┐┌─ 15m ─┐┌─ 15m ─┐ …
   access tokens — sent on every single request
```

## Why the refresh token is deliberately *not* a JWT

This is the design decision worth understanding properly.

A JWT cannot be revoked (file 09) — verification is a signature check, so there
is nothing to delete. Tolerable for 15 minutes. **Unacceptable for 30 days.**

Making the refresh token an opaque random string stored in the database turns
revocation into one `UPDATE`:

- "Log out this device" → revoke that row
- "Log out everywhere" (lost phone) → revoke all rows for the user
- "That token was stolen" → revoke and detect

You pay one database lookup — but only on refresh, roughly every 15 minutes, not
on every request. The cost lands exactly where it doesn't matter.

**Store it hashed.** It is a credential (file 07): a stolen database should not
yield working refresh tokens. SHA-256 is fine here, *not* argon2 — the token is
256 bits of randomness, not a guessable human password, so there is nothing to
brute-force and no reason to pay argon2's cost on every refresh.

> Notice this is the mirror of file 08's lesson. Slow hashing is right for
> low-entropy secrets humans choose; fast hashing is right for high-entropy
> secrets machines generate. The reason is the same in both cases: guessability.

## Rotation and reuse detection

Now the part that turns theft from a silent disaster into a detected event.

**Rotation**: every refresh returns a **new** refresh token and retires the old
one. Tokens form a chain, all sharing a `family_id`.

```
  login    → refresh_A
  refresh  → refresh_B   (A retired)
  refresh  → refresh_C   (B retired)
```

**Reuse detection**: if a *retired* token is ever presented, something is wrong.
The legitimate client always holds the newest one. A retired token in flight means
a copy exists — so the server revokes **the entire family** and forces a real
login.

```
  t=0  THIEF   refresh(A) → gets B          server retires A
  t=1  YOU     refresh(A) → A is RETIRED
                 │
                 ├─► "someone is replaying a retired token"
                 └─► revoke family: A, B, C, everything
                      │
        thief's B is dead; you log in with your PASSWORD,
        which the thief does not have.
```

Without rotation, a stolen refresh token is **30 days of silent access**. With
it, the theft surfaces the next time *either* party refreshes — usually minutes.

It costs you one extra column and one `if`.

## The client dance

The phone never shows the user any of this:

```
  1. Request with access token
  2. 401? → the access token expired
  3. POST /api/auth/refresh with the refresh token
  4. Store the new refresh token; keep the new access token in memory
  5. Retry the original request — ONCE
  6. Refresh also failed? → the session is genuinely over → login screen
```

**Once** is the right number of retries. If the refresh fails, retrying again
cannot help; it only loops. And two concurrent 401s must not fire two refreshes —
the second would present a token the first just retired, and reuse detection
would correctly log you out. Serialise refreshes behind a single in-flight
promise; this is the classic bug in this design.

## Where each token lives

| | Where | Why |
|---|---|---|
| Access token | **memory only** | Lives 15 min; writing it to disk adds risk for no benefit |
| Refresh token | **Keychain / Keystore** (file 11) | Must survive app restarts; a 30-day credential |
| Password | **nowhere on the device** | Typed at login and forgotten |

That last row is the point of the whole design. Compare today: a permanent shared
secret compiled into the app, identical on every install.

## In StockPulse

- Access: JWT, HS256, 15 min, claims `sub`/`iat`/`exp`.
- Refresh: 32 random bytes, hex; SHA-256 hash stored; 30 days; rotating with
  reuse detection.
- Table `refresh_tokens`: `token_hash`, `family_id`, `issued_at`, `expires_at`,
  `revoked_at`, `replaced_by`, `user_agent`.
- `user_agent` is there so a future "your sessions" screen can say *"iPhone,
  last used Tuesday"* — and so an unfamiliar device is visible.
- Logout revokes one token. Lost phone → revoke all rows for the user.

## Misconceptions

**"Two tokens is over-engineering for one user."** It is roughly forty lines
more than one token, and it buys revocation and theft detection — the two things
a single token fundamentally cannot have. That is a good trade at any scale.

**"Just make the access token last 30 days and skip refresh."** Then you cannot
revoke, cannot detect theft, and a lost phone means rotating the signing secret
and logging out every device including yours.

**"Rotation means the user gets logged out constantly."** Rotation is invisible —
it happens inside the refresh call. Users notice only when reuse is *detected*,
which should mean something genuinely went wrong.

**"Store the refresh token hashed with argon2 for extra safety."** Unnecessary and
slow. Argon2's cost defends *guessable* secrets. A 256-bit random token cannot be
guessed; SHA-256 is correct here.

## Remember this

- Short-lived token used constantly; long-lived token used rarely and revocably.
- The refresh token is **not a JWT on purpose** — revocability is the entire
  reason.
- **Rotation + reuse detection** turns a stolen token from silent permanent
  access into a detected event.
- Retry a failed request **once**, and never let two refreshes run at the same
  time.
