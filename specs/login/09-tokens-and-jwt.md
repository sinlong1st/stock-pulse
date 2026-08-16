# 09 — Tokens and JWT

## The problem

You've logged in. Now you open the Predict tab, then Watchlist, then Settings —
twenty requests in a minute. Each one arrives as an independent HTTP request, and
HTTP is **stateless**: the server has no memory that the previous request came
from you.

Sending your password with every request would be terrible:

- it crosses the network twenty times instead of once
- the phone must **store** it to do that — the one thing file 08 avoided
- argon2 takes ~100 ms *per request*, by design
- one leaked request leaks the permanent credential

So: prove you logged in, without resending the thing that logged you in.

## The idea

A **token** is a string issued at login that proves you already authenticated.

Most are **bearer** tokens: whoever *bears* it gets access, no further questions.
Like cash — if someone takes it, it works for them. Two consequences that shape
everything downstream: send them only over TLS (file 03), and keep their
lifetimes short.

```
  Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.4f2a9c…
                 ↑      ↑
                 scheme the token
```

Header, not query string — URLs land in logs, history and `Referer` headers
(file 07).

## Two kinds of token

**Opaque** — a random string meaning nothing by itself. The server looks it up.

```
  8f3a9c2e4b6d1a7f…   →  DB says: user 1, expires Sept 12
```

**Self-describing (JWT)** — carries its own facts, signed. The server verifies
the signature and reads them. No lookup.

Neither is "better"; they trade revocability against speed. File 10 uses one of
each.

## JWT anatomy

Three base64url parts, dot-separated:

```
  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 . eyJzdWIiOiIxIiwiZXhwIjoxNzY1NDMyMTAwfQ . 4f2a9c8e…
  └───────────── header ──────────────┘ └──────────── payload ───────────────┘ └ signature ┘
```

**Header** — which algorithm signed it:
```json
{ "alg": "HS256", "typ": "JWT" }
```

**Payload** — the **claims**, facts the server asserts:
```json
{
  "sub": "1",              // subject — which user
  "iat": 1765431200,       // issued at
  "exp": 1765432100,       // expires at  ← the important one
  "jti": "a3f9…"           // unique id, if you want to blocklist individually
}
```

**Signature** — `HMAC-SHA256(header + "." + payload, server_secret)`.

### Why the signature makes it trustworthy

The server does not need to remember issuing it. To verify, it recomputes the
signature from the received header and payload using its secret. If they match,
the content is untouched — because producing a valid signature requires the
secret, which only the server has.

Change `"sub": "1"` to `"sub": "2"` and the signature no longer matches. You
cannot forge a new one without the secret.

> ### The misconception that matters most
>
> **A JWT is signed, not encrypted.**
>
> The payload is *base64*, which is encoding, not encryption. Anyone holding the
> token can decode and read it — paste one into [jwt.io](https://jwt.io) and see.
>
> Signing prevents **tampering**, not **reading**.
>
> So: never put anything secret in a payload. No passwords, no API keys, no
> personal data you wouldn't publish. A user id and an expiry are exactly right.

### HS256 vs RS256

- **HS256** — one shared secret signs and verifies. Simple. Right when the same
  party does both, which is your case.
- **RS256** — a private key signs, a public key verifies. Right when *other*
  services must verify tokens they cannot mint.

StockPulse: **HS256**, one secret in the droplet's `.env`.

> A historical trap worth knowing: some old libraries honoured `"alg": "none"`
> from the *token itself*, letting anyone submit an unsigned token and be
> believed. Always pin the expected algorithm when verifying (`algorithms=["HS256"]`)
> rather than trusting the header. Modern PyJWT requires this.

## The catch that shapes the whole design

A JWT is verified by **maths**, not by a lookup. That is its speed — and its
flaw:

**You cannot revoke a JWT.** Nothing to delete. Once issued, it is valid until
`exp`, full stop. "Log out this device" cannot be honoured; the token keeps
working.

Two mitigations:

1. **Short lifetimes.** A 15-minute token limits the damage window to 15 minutes.
2. **A blocklist.** Store revoked `jti`s and check every request — which
   reintroduces the database lookup you used a JWT to avoid.

StockPulse takes option 1 for the access token, and pairs it with a revocable
opaque refresh token for everything longer. That is file 10.

## In StockPulse

- **Access token: JWT, HS256, 15 minutes.** Claims: `sub`, `iat`, `exp`.
- **Secret**: `JWT_SECRET` in the droplet `.env` — long and random
  (`openssl rand -hex 32`). Never committed. Rotating it invalidates every token
  at once, which is a blunt but useful emergency lever.
- **Verification** is a FastAPI dependency replacing `_require_mobile_api`, so
  every route gets a real user rather than a shared password.
- Library: `pyjwt`.

## Misconceptions

**"JWTs are encrypted."** No. Signed. Readable by anyone holding one. This is the
single most common JWT misunderstanding and it leads directly to people putting
personal data in payloads.

**"JWTs are more secure than sessions."** Different, not better. Sessions revoke
instantly and cost a lookup. JWTs are fast and cannot be revoked. Choose per job.

**"I'll make the token last a year so users never log in again."** Then a stolen
token is a year of access you cannot cancel. Lifetime *is* your exposure window.

**"Put the user's email and plan in the token so I don't query the DB."** You can
— they're readable by the holder, and they go **stale**. Downgrade someone's plan
and their token still claims the old one until it expires.

## Remember this

- A bearer token is cash: whoever holds it, spends it. TLS always; short lives.
- **Signed ≠ encrypted.** Payloads are public to whoever has the token.
- A JWT's speed and its unrevocability are the same property. That is why one
  token is not enough.
