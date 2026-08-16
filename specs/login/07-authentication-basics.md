# 07 — Authentication basics

## The problem

Part 1 got a connection to your server, encrypted and verified. The server now
knows the connection is private and that *it* is who it claims to be.

It still has no idea who is calling.

Every request arrives as bytes. There are no faces, no voices, nothing that is
inherently "you". Identity has to be *constructed* out of something the caller
can prove.

## Two words people use interchangeably (and shouldn't)

| | Question | Example |
|---|---|---|
| **Authentication** (authn) | *Who are you?* | Logging in with a password |
| **Authorization** (authz) | *What may you do?* | "Only admins may delete users" |

Authn comes first and answers identity. Authz uses that identity to make
decisions. Conflating them produces systems that know your name and let you do
anything — or check permissions for a user nobody verified.

**StockPulse needs authn.** With one user, authz is trivially "the logged-in user
may do everything". It becomes real work only when a second user exists, which is
a product decision, not a security one.

## The three factors

Authentication rests on proving one of:

| Factor | Meaning | Examples |
|---|---|---|
| **Something you know** | a secret in your head | password, PIN |
| **Something you have** | a physical object | phone, security key, TOTP app |
| **Something you are** | a body measurement | fingerprint, face |

**Multi-factor** means two *different* categories. A password plus a security
question is not MFA — both are things you know, and both leak from the same
breach.

StockPulse will use one factor (a password). That is a deliberate, proportionate
choice: one user, a personal tool, and the realistic threat is bots rather than a
targeted attacker. The design leaves room for TOTP later without rework.

> Worth noticing: your **phone's** fingerprint/face unlock is not authenticating
> you to StockPulse. It unlocks the Keychain (file 11), which releases a token
> that was minted earlier by your password. The biometric is a local gate on a
> stored credential — a distinction that matters when reasoning about what a
> stolen unlocked phone gets someone.

## Credentials

A **credential** is anything that proves identity: a password, a token, an API
key, a private key. The working rule:

> **Treat every credential the way you'd treat a password.**
> Never log it. Never store it in plain text. Never put it in a URL.

That last one catches people. URLs end up in server access logs, browser history,
`Referer` headers sent to third parties, and analytics. `?token=abc123` is a
credential leak with extra steps — which is why tokens travel in the
`Authorization` header, not the query string.

## Stateless vs stateful identity

Two ways to remember that someone logged in:

**Stateful (sessions).** The server stores a session record and gives the client
an opaque ID. Every request costs a lookup. Revocation is instant — delete the
row.

**Stateless (tokens).** The server gives out a signed token containing the facts.
Every request verifies a signature — no database. Nothing to delete, so
revocation is *impossible* before expiry.

```
  STATEFUL                          STATELESS
  client: "session abc123"          client: "here is a signed token"
  server: looks it up ───► DB       server: verifies signature (maths only)
  ✓ revoke instantly                ✗ cannot revoke
  ✗ a lookup per request            ✓ no lookup
```

Neither wins outright. StockPulse uses **both, for different jobs** — a stateless
access token for speed and a stateful refresh token for control. That combination
is file 10, and it exists precisely because this trade-off has no single answer.

## What login actually establishes

When you log in, you exchange a **long-term** credential (your password, which
never changes and unlocks everything) for a **short-term** one (a token that
expires and can be scoped).

That exchange is the entire point:

- Your password crosses the network **once per login**, not once per request.
- The phone stores a token, never the password.
- A stolen token expires; a stolen password does not.
- Tokens are per-device, so one can be revoked without touching the others.

Compare today's design: a single shared secret compiled into the app, identical on
every install, never expiring, revocable only by rebuilding the app. Every one of
the properties above is missing.

## In StockPulse

- **One factor**: email + password.
- **No public signup.** One user, created by a CLI command on the droplet. A
  registration endpoint would let anyone create an account and spend your OpenAI
  credit — the attack is that simple.
- **Password reset** is "SSH in and run the command". Fine at one user; genuine
  work at two, because it needs email.
- **Identity replaces the shared token everywhere** — including
  `/api/push/register`, so notifications follow the account rather than the
  build.

## Misconceptions

**"Authentication and authorization are basically the same."** They are adjacent
and distinct. Mixing them is how you get "logged in, therefore allowed to do
anything" — invisible at one user, dangerous at two.

**"A password in a URL is fine over HTTPS."** TLS protects it in transit, then it
lands in access logs, browser history and `Referer` headers. Use headers.

**"More factors are always better."** More factors cost usability, and usability
failures cause worse workarounds. One factor plus rate limiting is a reasonable,
defensible choice for a single-user personal tool.

## Remember this

- Authn is *who*, authz is *what may they do*. Get the first one right first.
- Login exchanges a permanent credential for a temporary one — that swap is the
  whole value.
- Stateless is fast but unrevocable; stateful is revocable but costs a lookup.
  StockPulse uses each where its strength matters.
