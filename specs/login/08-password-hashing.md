# 08 — Password hashing

## The problem

To check a password, the server must compare what you typed against something it
stored. The naive version:

```
users
  email                  password
  you@example.com        hunter2          ← plain text
```

Now anyone who reads that table — a SQL injection, a stolen backup, a leaked
laptop, a curious contractor — has your password. And because people reuse
passwords, they have your email provider and your bank too.

So the requirement is strange and specific: **the server must be able to verify
your password without ever being able to learn it.**

## The idea

A **hash** is a one-way function. Easy forwards, computationally impossible
backwards:

```
  hash("hunter2")  →  8b2c1f4e9a…      (fast)
  8b2c1f4e9a…      →  ???              (infeasible)
```

Store the hash. On login, hash what was typed and compare hashes. A stolen
database yields hashes, and hashes are not passwords.

That is the shape. Getting it right takes two more ideas.

## Idea 1 — Salt

Hashing alone has a hole. The function is deterministic, so `hash("password123")`
is the *same value* for every person on earth who chose it. An attacker
precomputes hashes for the ten million most common passwords once (a **rainbow
table**) and then reverses any database instantly by lookup.

A **salt** is a random value stored alongside, mixed in before hashing:

```
  alice:  hash("hunter2" + "x7Kp2m")  →  a1b2c3…   different
  bob:    hash("hunter2" + "9zQr4T")  →  f4e5d6…   hashes
```

Now the precomputed table is worthless — an attacker must redo the entire effort
**per user**. Identical passwords no longer look identical, which also stops
"these 400 accounts share a password" analysis.

You do not manage salts yourself: argon2 and bcrypt generate one per password and
embed it in the output string, along with the parameters used.

## Idea 2 — Slowness, deliberately

This is the counter-intuitive one, and the reason the naive design still fails.

Salting stops *precomputation*. It does not stop an attacker taking your stolen
hashes and guessing, one user at a time. And modern hardware guesses very fast:

| Algorithm | Guesses/second (consumer GPU, order of magnitude) |
|---|---|
| MD5 | ~100,000,000,000 |
| SHA-256 | ~10,000,000,000 |
| bcrypt (cost 12) | ~10,000 |
| argon2id (tuned) | ~1,000 |

SHA-256 is **excellent** at what it was designed for — verifying that a file
hasn't changed — and that design goal is *speed*. For passwords, speed is the
vulnerability.

So password hashes are built to be **deliberately slow**, and the good ones are
also **memory-hard**: they require a large block of RAM per computation. GPUs get
their speed from thousands of tiny cores with little memory each, so a
memory-hard function collapses their advantage. That is argon2's core insight.

```
  Attacker with 8 stolen hashes, guessing a 10-character password:

  SHA-256      →  hours
  bcrypt       →  centuries
  argon2id     →  centuries, and a GPU doesn't help
```

The cost to *you* is ~100 ms once per login. The cost to an attacker is their
entire strategy. **Good security measures are asymmetric like this** — when a
measure hurts you as much as the attacker, it is usually the wrong measure.

### Which one

| | Use it? |
|---|---|
| **argon2id** | ✅ Current recommendation. Memory-hard. Python: `argon2-cffi` |
| **bcrypt** | ✅ Fine. Older, battle-tested, everywhere |
| **scrypt** | ⚠️ Acceptable |
| **PBKDF2** | ⚠️ Acceptable if mandated by compliance |
| **SHA-256 / SHA-3** | ❌ Wrong tool. Too fast |
| **MD5 / SHA-1** | ❌❌ Also broken for other reasons |

## What the stored value looks like

```
$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG
└──┬───┘ └─┬─┘ └──────┬──────┘ └───┬────┘ └──────────────┬──────────────┘
algorithm version   parameters     salt                  hash
```

Everything needed to verify is in one string: which algorithm, which parameters,
which salt. That is what makes upgrades possible — when you raise the cost
parameters, old hashes keep verifying with their old settings, and you re-hash
each password on next successful login.

## Verification, and one more trap

```python
from argon2 import PasswordHasher
ph = PasswordHasher()

hash = ph.hash("hunter2")          # at registration
ph.verify(hash, "hunter2")         # at login — raises on mismatch
```

**Never compare secrets with `==`.** String comparison stops at the first
differing byte, so a wrong guess sharing a prefix takes measurably longer.
Enough measurements and a secret can be recovered a character at a time — a
**timing attack**. Use `hmac.compare_digest`, which always takes the same time.

`argon2.verify` already does this internally. It matters for the *other* secrets:
`app/main.py` currently does

```python
if authorization != f"Bearer {settings.mobile_api_token}":   # ← not constant-time
```

Low real-world risk (network jitter swamps the signal), free to fix, and the plan
fixes it in Phase 3.

## Password rules worth having (and the ones to skip)

Modern guidance (NIST SP 800-63B) inverted the old advice:

- ✅ **Length over complexity.** Minimum ~10; longer is better. A passphrase beats
  `P@ssw0rd!`.
- ✅ **Check against known-breached lists** if convenient.
- ❌ **No composition rules.** "One uppercase, one digit, one symbol" pushes
  people toward `Password1!` — predictable, and hated.
- ❌ **No forced rotation.** Ninety-day expiry produces `Summer2026`, then
  `Summer2027`. Rotate on evidence of compromise, not on a calendar.

## In StockPulse

- **argon2id** via `argon2-cffi`, default parameters (sensible today).
- One user, created by CLI on the droplet. The hash lives in the `users` table.
- **The password never touches the phone's storage** — only tokens do (file 11).
- Reset = re-run the CLI. Honest at one user; real work at two.

## Misconceptions

**"I'll encrypt the passwords."** Encryption is reversible by design, so you'd be
storing a key that turns the database back into passwords. Hashing is one-way on
purpose. (Encryption is right for data you must read back — like an API key you
need to send onward. Never for passwords.)

**"Hash it on the client so it never travels."** Then the hash *is* the password:
anyone who captures it can replay it, and you have gained nothing while breaking
server-side upgrades. Send it over TLS; hash on the server.

**"Salt should be secret."** It need not be, and it's stored right next to the
hash. Its job is uniqueness, not secrecy. (A separate secret *pepper*, stored
outside the database, is an optional extra layer — different mechanism.)

**"argon2 is slow, that's bad for my API."** It runs once per **login**, not per
request. That is exactly what tokens are for.

## Remember this

- Store hashes, never passwords — the server must be unable to learn your secret.
- **Salt** kills precomputation; **slowness** kills guessing. You need both.
- SHA-256 is the wrong tool *because it is fast*. Use argon2id.
- Compare secrets in constant time.
