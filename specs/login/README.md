# The login library

One concept per file, in reading order. Written to be understood rather than
skimmed: each file explains **the problem the thing was invented to solve**
before explaining the thing, because a mechanism without its problem is just
trivia you forget.

## How to use this

Read in order. Each file assumes only the ones before it. They are short on
purpose — one sitting each, and you can stop anywhere without being left
mid-thought.

Every file has the same shape:

1. **The problem** — what goes wrong without it
2. **The idea** — the mechanism, plainly
3. **In StockPulse** — how it applies to *your* server, with real values
4. **Misconceptions** — what people (including me) get wrong
5. **Remember this** — the two or three sentences worth keeping

## Reading order

### Part 1 — Getting the connection there at all

| # | File | The question it answers |
|---|---|---|
| 01 | [the-problem.md](01-the-problem.md) | Why are we changing anything? |
| 02 | [dns-and-domains.md](02-dns-and-domains.md) | How does a name become a server? |
| 03 | [tls-and-https.md](03-tls-and-https.md) | What does the "s" in https actually do? |
| 04 | [certificates-and-trust.md](04-certificates-and-trust.md) | Why does your phone believe my server is mine? |
| 05 | [reverse-proxies.md](05-reverse-proxies.md) | What is Caddy/nginx for, and why not just the app? |
| 06 | [ports-and-binding.md](06-ports-and-binding.md) | Why is `127.0.0.1` the only reason you're safe today? |

### Part 2 — Proving who you are

| # | File | The question it answers |
|---|---|---|
| 07 | [authentication-basics.md](07-authentication-basics.md) | What is identity, in a system with no faces? |
| 08 | [password-hashing.md](08-password-hashing.md) | How do you store a password you must never know? |
| 09 | [tokens-and-jwt.md](09-tokens-and-jwt.md) | How do you stay logged in without resending a password? |
| 10 | [sessions-access-refresh.md](10-sessions-access-refresh.md) | Why two tokens instead of one? |
| 11 | [secure-storage.md](11-secure-storage.md) | Where does a phone keep a secret? |

### Part 3 — Surviving contact with the internet

| # | File | The question it answers |
|---|---|---|
| 12 | [attacks-and-defences.md](12-attacks-and-defences.md) | Who attacks a small personal server, and how? |
| 13 | [rate-limiting.md](13-rate-limiting.md) | How do you make attempts expensive? |

## The rest of the set

- **`../STOCKPULSE_AUTH_PLAN.md`** — the build order: phases, decisions, and the
  alternatives that were rejected with reasons.
- **`../../AUTH_EXPLAINED.md`** — the end-to-end walkthrough with five real
  scenarios (first login, silent refresh, stolen token, a bot finding you, a lost
  phone). Read it after Part 2; it is where the pieces click together.

## The one-sentence version, if you read nothing else

Your phone currently reaches the server through a VPN, and **that VPN is the only
thing standing between eleven unauthenticated routes and the entire internet** —
so before the VPN can go away, the application itself has to learn who you are.
