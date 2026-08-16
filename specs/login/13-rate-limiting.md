# 13 — Rate limiting

## The problem

Two things become free the moment your server is public:

**Guessing.** A login endpoint with no limit accepts a thousand password attempts
a second. argon2 (file 08) slows each attempt to ~100 ms, which helps — but ten
attempts a second, forever, still works through a lot of common passwords.

**Spending.** `POST /api/predict` calls OpenAI. Authenticated or not, a loop
against it converts your credit into someone else's amusement. Nothing is stolen,
nothing alarms — you just get an invoice.

Both are volume problems. The answer is to make volume expensive.

## The idea

**Rate limiting** caps how often an action may be attempted, per identity, per
window. Three approaches worth knowing:

### Fixed window
Count per clock interval: 5 per minute, reset at each minute boundary.
Simple; has an edge case — 5 at 10:00:59 and 5 at 10:01:00 is 10 in two seconds.

### Sliding window
Count over "the last 60 seconds" continuously. No boundary spike; slightly more
bookkeeping.

### Token bucket
A bucket holds N tokens and refills at a steady rate; each request spends one.
Allows short **bursts** while capping the long-run average — usually the nicest
behaviour for humans, who act in bursts.

For a login endpoint, none of these is quite right on its own, because you want
something harsher.

## Login deserves special treatment

Failed logins should get **exponentially** more expensive, and the counter should
attach to the **account**, not just the IP:

```
  attempt 1–3   → no delay
  attempt 4     → locked 1 minute
  attempt 5     → locked 2 minutes
  attempt 6     → locked 4 minutes
  attempt 7     → locked 8 minutes
  …
  successful login → counter resets to zero
```

Ten guesses costs an attacker hours. You, having mistyped twice, notice nothing.
**Asymmetric, in your favour** — the property file 08 identified as the mark of a
good measure.

Track it on the user row:

```
users
  … failed_attempts INT   locked_until TIMESTAMP
```

### Per-account *and* per-IP

Each alone has a hole:

- **Per-account only** → an attacker with a list of emails tries one password
  against thousands of accounts (*password spraying*) and never trips a per-account
  limit.
- **Per-IP only** → a botnet spreads attempts across thousands of addresses.

You have one account, so per-account is the load-bearing control here. Per-IP
still helps against noise.

> ### The lockout trap
> An account-lockout that anyone can trigger by guessing is a **denial of service
> against you**: someone spams your email address with wrong passwords and you can
> never log in. Mitigations: cap the lockout duration (say 15 minutes rather than
> forever), and never lock out a *correct* password — if the credentials are right,
> let them in and reset the counter. Locking the attacker out of your own account
> is a real bug pattern, not a hypothetical.

## Don't leak which part was wrong

```
  ❌ "No account with that email"     ← confirms which emails exist
  ❌ "Incorrect password"             ← confirms this email DOES exist
  ✅ "Email or password is incorrect" ← says nothing either way
```

Same for timing: if a missing email returns instantly while a wrong password
takes 100 ms of argon2, the *timing* leaks what the message didn't. Run the hash
comparison against a dummy hash even when the user doesn't exist, so both paths
cost the same.

This matters less with one user than with a public product — but it costs one
line and it's the sort of habit worth having.

## Protecting the expensive endpoints

Rate limiting for money is a different shape: a **daily cap per user**, not a
per-second limiter.

| Endpoint | Costs | Sensible cap |
|---|---|---|
| `/api/predict`, `/api/positions/exit-advisor` | 1–2 model calls | ~50/day |
| `/api/report` | 1 model call, sometimes web search | ~30/day |
| `/api/feed`, `/api/watchlist` | a database read | generous or none |

Set caps well above your real use, so they are invisible until something is
wrong. They are a **circuit breaker**, not a budget.

There is already a related control in the codebase worth noting:
`MAX_CLASSIFICATIONS_PER_RUN` caps cost per pipeline run. Same instinct, different
layer.

## Where to implement it

**In the application**, not the proxy. The app knows *which user* is calling;
Caddy only sees an IP, and per-IP is the weaker control.

For a single container, an in-process counter is fine — no Redis needed. Note the
one condition: it resets on restart, and it does not survive scaling to multiple
processes. Both are acceptable here and worth writing down so a future reader
knows it was a decision rather than an oversight.

> **The bug that makes rate limiting silently useless:** behind a reverse proxy,
> every request appears to come from `127.0.0.1` unless you read
> `X-Forwarded-For`. Per-IP limiting then buckets the entire internet together —
> which either blocks everyone at once or, more likely, never triggers. Test it
> from a phone on mobile data, not just localhost.

## What to return

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 120
```

`429` is the correct status. `Retry-After` lets a well-behaved client wait
properly instead of hammering. The app should show "too many attempts, try again
in two minutes" rather than a generic failure — otherwise you will think the
server is broken and retry, which extends the lockout.

## In StockPulse

Phase 5 of the plan, and **the last thing that must exist before going public**:

- Login: `failed_attempts` + `locked_until` on `users`, exponential backoff,
  15-minute maximum, reset on success.
- Uniform error message and uniform timing for wrong-email vs wrong-password.
- Per-user daily caps on the model-calling endpoints, set generously.
- In-process counters; no Redis.
- `X-Forwarded-For` honoured so per-IP means something behind Caddy.

## Misconceptions

**"argon2 is slow, so I don't need rate limiting."** Slow hashing defends the
*database after a leak*. Rate limiting defends the *live endpoint*. Different
attacks, both needed.

**"Rate limiting will annoy me."** Set thresholds an order of magnitude above real
use. You should never meet them; an attacker meets them immediately.

**"I'll add it after launch."** Launch is when the probes start. This is the one
piece that has to be there on day one.

**"Lock the account forever after 5 failures."** Then anyone who knows your email
can permanently lock you out. Cap the duration.

## Remember this

- Make attempts **exponentially** expensive; reset on success.
- Per-account *and* per-IP — each covers the other's blind spot.
- Never reveal *which* credential was wrong, in the message **or** the timing.
- Behind a proxy, read `X-Forwarded-For` or your per-IP limiting does nothing.
