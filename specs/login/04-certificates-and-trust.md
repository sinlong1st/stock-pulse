# 04 — Certificates and trust

## The problem

File 03 ended with a question it did not answer. During the handshake, the server
says *"I am stockpulse.yourdomain.com."*

Why should the phone believe it?

Anyone can claim any name. If your DNS is hijacked, or you're on a hostile
network, the machine that answers might not be yours. Encrypting a conversation
with an impostor is worse than useless — it *feels* secure.

## The idea

A **certificate** is a file that binds a **name** to a **public key**, signed by
someone the phone already trusts.

```
  CERTIFICATE
  ├─ Subject:      stockpulse.yourdomain.com     ← the name
  ├─ Public key:   30 82 01 0a 02 82 01 01 …     ← the matching key
  ├─ Valid:        2026-08-13 → 2026-11-11       ← ~90 days
  ├─ Issuer:       Let's Encrypt R3              ← who vouched
  └─ Signature:    (Issuer's signature over all of the above)
```

The server also holds the **private key** that pairs with that public key, and it
never leaves the machine. During the handshake the server proves it possesses
that private key. So the chain of reasoning is:

1. I trust the issuer.
2. The issuer signed "this public key belongs to `stockpulse.yourdomain.com`".
3. This server just proved it holds the matching private key.
4. Therefore this server is `stockpulse.yourdomain.com`.

### Where the trust bottoms out

Your phone ships with a **root store** — a few dozen Certificate Authority
certificates baked into the OS by Apple/Google. Those are the axioms.

```
  Root CA  (in your phone's OS, trusted by definition)
     │ signs
  Intermediate CA  (Let's Encrypt R3)
     │ signs
  Your certificate  (stockpulse.yourdomain.com)
```

Roots sign intermediates, intermediates sign your certificate. Roots stay offline
in vaults; intermediates do daily work and can be revoked if compromised without
re-flashing every phone on earth.

### What the CA actually checks

For an ordinary (Domain Validated) certificate, exactly one thing: **do you
control this domain?** Not who you are, not whether you're trustworthy. Two ways
to prove it:

- **HTTP-01** — the CA gives you a token; you serve it at
  `http://yourdomain/.well-known/acme-challenge/<token>`. Requires port 80 open.
- **DNS-01** — you publish the token as a TXT record. Works with no web server at
  all, and is the only way to get **wildcard** certificates (`*.yourdomain.com`).

**ACME** is the protocol that automates this whole dance. **Let's Encrypt** is a
free CA that speaks it. Caddy has an ACME client built in — which is why its
config is five lines and renewal is not your problem.

### Why 90 days

Let's Encrypt certificates are short-lived on purpose:

- A stolen private key is only useful until expiry.
- Short lifetimes *force* automation, and automated renewal doesn't get forgotten
  the way an annual calendar reminder does.

Caddy renews at around 60 days, silently. The failure mode people fear —
"certificate expired, site down" — is a property of *manual* certificate
management.

## Certificate Transparency: the part that changes your threat model

Every certificate a public CA issues is submitted to **Certificate Transparency
logs**: public, append-only, cryptographically verifiable records.

They exist for an excellent reason. In 2011 a CA was compromised and issued a
valid certificate for `*.google.com` to attackers. Nobody could detect it, because
issuance was invisible. CT makes issuance auditable: domain owners can watch for
certificates they didn't request.

**The side effect matters to you.** The moment Caddy gets your certificate, the
hostname `stockpulse.yourdomain.com` is published to a public log that anyone can
read — and bots do read them, continuously, looking for fresh hosts to probe.

You can see it yourself at [crt.sh](https://crt.sh) — type any domain and read
every certificate ever issued for it.

```
  You run Caddy  ──►  Let's Encrypt issues  ──►  CT log entry (public)
                                                        │
                                     scanners ingest the feed
                                                        │
                          probes hit /, /admin, /run within hours
```

This is *the* reason `specs/STOCKPULSE_AUTH_PLAN.md` puts auth before exposure.
Your defence cannot be that nobody knows the address, because publishing the
address is a mandatory part of getting a certificate.

## In StockPulse

- Caddy obtains and renews the certificate automatically. You configure a domain
  name and nothing else.
- **Port 80 must be reachable** for the HTTP-01 challenge (Caddy also uses it to
  redirect visitors to HTTPS). If you'd rather not open 80, use DNS-01 with your
  registrar's API.
- **Do not** use a self-signed certificate. React Native rejects untrusted
  certificates, and the workarounds all amount to disabling verification — which
  removes the impersonation protection that is most of TLS's value.
- Assume your hostname is public from day one. Design as if it is on a billboard.

## Misconceptions

**"The padlock means the site is legitimate."** It means someone proved control of
the domain. Phishing sites have valid certificates. The padlock is about the
*channel*, never the *character* of the operator.

**"Certificates cost money."** They did, historically. Let's Encrypt is free and
issues hundreds of millions. Paid certificates buy warranties and organisation
validation, neither of which you need.

**"Expiry means my site breaks."** With automated renewal, no. With manual
renewal, absolutely — which is the argument for automation, not for long
lifetimes.

**"My certificate proves my server is secure."** It proves the *name* matches.
Your server can be perfectly certified and completely open, which is exactly the
state you would be in if you skipped the auth work.

## Remember this

- A certificate binds a **name** to a **key**, signed by someone the phone
  already trusts.
- Domain-validated certificates prove **control of a name** — nothing more.
- **Certificate Transparency makes your hostname public the moment you get a
  certificate.** Obscurity is not available to you. Plan accordingly.
