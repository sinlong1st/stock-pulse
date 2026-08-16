# 02 — DNS and domains

## The problem

Computers find each other by **IP address** — your droplet is something like
`164.90.х.х`. Humans cannot remember those, they change when you rebuild a
server, and — crucially for us — **you cannot get an HTTPS certificate for a bare
IP address** in any practical way.

So we need a stable, human-readable name that points at a machine.

## The idea

**DNS** (Domain Name System) is a distributed phone book. You ask "what is the
address of `stockpulse.example.com`?" and get back an IP.

It is *distributed* and *hierarchical* — no single computer holds the whole
internet's records. Reading right to left:

```
        stockpulse   .   example   .   com   .
             │             │           │      │
             │             │           │      └── the root (implicit)
             │             │           └───────── TLD, run by a registry
             │             └───────────────────── the domain YOU register
             └─────────────────────────────────── a subdomain, yours to invent
```

Once you own `example.com`, every subdomain under it is yours for free. You do
not need to buy `stockpulse.example.com` — you create it.

### How a lookup actually runs

```
  Phone: "where is stockpulse.example.com?"
     │
     ├─► Resolver (your ISP's, or 1.1.1.1) — checks its cache first
     │      │  (miss)
     │      ├─► Root servers:  "ask the .com registry"
     │      ├─► .com registry: "ask example.com's nameservers"
     │      └─► Your nameservers: "164.90.х.х"   ← the answer
     │
     └─◄ 164.90.х.х  (cached for TTL seconds)
```

The resolver caches the answer for the record's **TTL** (time to live). This is
why DNS changes "take time to propagate" — nothing is propagating, old answers
are simply still cached.

### Record types you'll meet

| Type | Maps | Example |
|---|---|---|
| **A** | name → IPv4 | `stockpulse.example.com → 164.90.х.х` |
| **AAAA** | name → IPv6 | same, for IPv6 |
| **CNAME** | name → another *name* | `www → example.com` |
| **MX** | mail servers | email delivery |
| **TXT** | arbitrary text | domain-ownership proofs |

You need exactly one: an **A record** pointing at your droplet.

**TXT** is worth knowing about for a second reason: it is how you can prove domain
ownership to a certificate authority without exposing a web server (the DNS-01
challenge — see file 04).

## In StockPulse

You do not have a domain yet, and everything public waits on that. Concretely:

1. Register a domain (~$10–15/year) or use a subdomain of one you already own.
2. Create an **A record**: `stockpulse.yourdomain.com → your droplet's IP`.
3. Set a **low TTL** (300 s) *before* you start, so mistakes are cheap to fix.
4. Verify from your machine:

```bash
dig +short stockpulse.yourdomain.com     # should print your droplet IP
```

Do this and confirm it works **before** touching Caddy. Certificate issuance
depends on DNS already being correct, and debugging two broken things at once is
how afternoons disappear.

### A note on the registrar

The registrar is who you buy from (Namecheap, Cloudflare, Porkbun…). What matters
practically: whether they include **WHOIS privacy** for free (your name, address
and email are otherwise published in a public registration database) and whether
their DNS control panel is decent. Cloudflare and Porkbun include privacy free;
some others charge for it annually.

## Misconceptions

**"DNS propagation takes 24–48 hours."** Mostly folklore. Nothing propagates —
resolvers cache answers for the TTL you set. Set a 300-second TTL beforehand and
changes are visible in five minutes. The 24-hour figure comes from records left
at a one-day TTL.

**"A CNAME and an A record are interchangeable."** A CNAME points at a *name*,
which then needs its own lookup. You cannot put a CNAME at the root of a domain
(`example.com` itself) in classic DNS, only on subdomains.

**"DNS is a security boundary."** It is not, at all. DNS is a public directory.
Anyone can look up your record; the fact that a name resolves grants nobody
access. Security starts *after* the connection is made.

**"I can just use my IP address."** You can reach the server, but certificate
authorities do not issue certificates for bare IPs in practice, so you would have
no HTTPS — meaning your password would cross the internet in plain text.

## Remember this

- DNS turns names into IPs; it is a **public** phone book, never a lock.
- You need one **A record**. Set a low TTL first so mistakes cost minutes.
- No domain → no certificate → no HTTPS → no safe login. This is the
  prerequisite everything else waits on.
