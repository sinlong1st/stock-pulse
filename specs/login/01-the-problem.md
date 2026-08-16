# 01 — The problem

## The symptom

Your phone's battery drains faster than it used to. The cause is Tailscale: a
VPN client holds a **persistent connection** to keep the tunnel alive, which
means periodically waking the radio even when you aren't using the app. That is
not a misconfiguration you can tune away — a permanently-open tunnel costs
power. It is the price of the design.

So the goal: **reach the backend over ordinary HTTPS, with no VPN on the phone.**

## The trap

Here is where most people go wrong, and it is worth slowing down for.

Tailscale looks like one thing ("how my phone reaches my server"). It is
actually doing **two** unrelated jobs:

```
        ┌──────────────────── TAILSCALE ────────────────────┐
        │                                                    │
        │  JOB 1: REACHABILITY                               │
        │  Your phone can find and connect to the droplet    │
        │  even though the droplet has no public port open.  │
        │                                                    │
        │  JOB 2: AUTHENTICATION                             │
        │  Only devices on your private network exist, as    │
        │  far as the server is concerned. Everyone else      │
        │  cannot even attempt to connect.                   │
        │                                                    │
        └────────────────────────────────────────────────────┘
```

"Replace Tailscale with a domain and HTTPS" replaces **job 1 only**. Job 2 just
silently disappears. That is the whole danger of this project.

## Why job 2 matters more than it sounds

`app/main.py` has **eleven routes with no authentication at all**:

```
GET  /                  the HTML dashboard
GET  /alerts            your alerts, rendered
GET  /evaluation        your accuracy page
POST /run               runs the whole pipeline  ← spends OpenAI credit
POST /classify          classifies articles      ← spends OpenAI credit
POST /report            generates a briefing     ← spends OpenAI credit
POST /alerts/send       sends Telegram messages  ← to your phone
POST /evaluate          scores predictions
POST /evaluate/digest   sends a Telegram digest
GET  /collect           fetches news
GET  /health            status
```

They were written when the only way to reach the server was to already be inside
your private network — so "who is calling?" had an obvious answer: *you*. That
assumption is load-bearing, and it is about to be removed.

Publish port 443 → 8000 without doing anything else, and every one of those
becomes a public URL. An attacker doesn't need your data to hurt you; `POST /run`
in a loop is enough to run up an OpenAI bill.

## "But nobody will know my URL"

They will, within hours, and not because anyone is interested in you.

When you get an HTTPS certificate, it is published to **Certificate Transparency
logs** — public, append-only records of every certificate ever issued. They exist
for a good reason (so a certificate authority cannot secretly issue a certificate
for your bank), but the side effect is that **every new hostname is announced to
the world the moment it exists**. Bots monitor these logs and probe new names
automatically.

This is covered properly in [04-certificates-and-trust.md](04-certificates-and-trust.md).
For now: obscurity is not a security measure. Plan as though the address is
published on a billboard, because effectively it is.

## What has to be true before the VPN goes away

| Tailscale's job | Replacement | Covered in |
|---|---|---|
| Reachability | A domain + TLS + a reverse proxy | Files 02–05 |
| Authentication | Login: passwords, tokens, sessions | Files 07–11 |
| "Only my devices can even try" | Rate limiting + closing open routes | Files 12–13 |

**The order matters.** Auth lands *before* the public endpoint, never after. That
constraint is why the plan's phases look the way they do.

## Misconceptions

**"HTTPS means it's secure."** HTTPS secures the *channel* — nobody can read or
tamper with traffic in transit. It says nothing about *who is allowed to make the
request*. A public API with perfect TLS and no login is perfectly encrypted and
completely open.

**"It's a personal project, nobody cares."** Nobody does care — and that is
precisely the threat model. You will not be attacked by a person who chose you.
You will be scanned by bots that attack everything, indiscriminately, forever.

**"I'll add auth later."** Later means a window during which the server is public
and open. There is no version of this where exposure comes first.

## Remember this

- Tailscale is doing two jobs, and only one of them is obvious.
- Eleven routes are currently protected by nothing but the network.
- Auth before exposure. Always that order.
