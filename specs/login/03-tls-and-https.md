# 03 — TLS and HTTPS

## The problem

A request from your phone to your droplet does not travel down a private wire. It
hops through your router, your ISP, several backbone networks, and your hosting
provider's switches. On plain HTTP, **every one of those hops can read and modify
the traffic**.

Concretely, sending your password over HTTP means: the café Wi-Fi, everyone else
on it, the ISP, and anyone who has quietly inserted themselves into the path, all
get your password in readable text.

Three distinct dangers, and it's worth separating them:

1. **Eavesdropping** — someone reads your data
2. **Tampering** — someone changes it in flight
3. **Impersonation** — you connect to an attacker's server thinking it's yours

## The idea

**TLS** (Transport Layer Security) solves all three. HTTPS is simply HTTP running
inside a TLS tunnel. Nothing about HTTP changes — same verbs, same headers, same
JSON. It is wrapped.

> "SSL" is TLS's dead predecessor. Everyone still says SSL; everyone means TLS.
> If you see "SSL certificate", read "TLS certificate".

### What TLS gives you

| Property | Meaning | Stops |
|---|---|---|
| **Confidentiality** | Only the two ends can read it | Eavesdropping |
| **Integrity** | Tampering is detected | Modification |
| **Authentication** | The server proves it is who it claims | Impersonation |

That third one is the one people forget, and it is what makes the first two worth
anything. Encryption to an attacker is perfectly secure and perfectly useless.

### The handshake, conceptually

```
  PHONE                                            SERVER
    │  "hello, I speak TLS 1.3, here are my ciphers"  │
    │ ───────────────────────────────────────────────►│
    │                                                 │
    │  "hello, let's use this one. Here is my         │
    │   CERTIFICATE proving I am stockpulse.you.com"  │
    │ ◄───────────────────────────────────────────────│
    │                                                 │
    │  Phone checks: is this certificate signed by    │
    │  someone I trust? Does the name match what I    │
    │  typed? Is it still valid?                      │
    │                                                 │
    │  ── key exchange ──────────────────────────────►│
    │  Both sides derive the SAME session key without │
    │  ever sending it across the wire.               │
    │                                                 │
    │ ═══════ everything from here is encrypted ═════ │
    │  GET /api/feed  Authorization: Bearer …         │
```

Two ideas worth internalising:

**Asymmetric → symmetric.** The handshake uses slow public-key cryptography just
long enough to agree on a fast shared key, then switches to it. You get the
security properties of the first and the speed of the second.

**The session key is never transmitted.** Both sides *derive* it from exchanged
public values. Someone recording the whole conversation still cannot reconstruct
it. With modern TLS this also gives **forward secrecy**: keys are ephemeral, so
stealing the server's private key later does not decrypt traffic captured
earlier.

### What is *not* encrypted

TLS hides the request path, headers, body and response. It does **not** hide:

- **which server you connected to** — the IP is on the packets, and the hostname
  is visible in the handshake (via SNI) unless Encrypted Client Hello is in use
- **how much data moved, and when**

So an observer knows *that* your phone talked to `stockpulse.yourdomain.com` and
roughly how much. They do not know you asked about WDC.

## In StockPulse

- TLS terminates at **Caddy** on the droplet. Caddy decrypts and forwards plain
  HTTP to `127.0.0.1:8000`. That inner hop is unencrypted, which is fine — it
  never leaves the machine.
- Your **password** only crosses the network at login, and only inside TLS.
- Your **access and refresh tokens** cross on every request. They are bearer
  tokens — whoever holds one can use it — so TLS is the only thing keeping them
  private in transit. Without TLS the entire token design is pointless.
- **HSTS** (`Strict-Transport-Security`) is worth enabling once you're confident:
  it tells the phone "never speak plain HTTP to this host again", which closes
  the small window where a first request could be downgraded.

## Misconceptions

**"HTTPS means the site is safe."** It means the *channel* is private and the
server is who it claims. A phishing site can have perfect HTTPS. And your own API
can be perfectly encrypted while allowing anyone in the world to call `/run`.
Encryption is not authorisation — this is exactly the mistake file 01 warns about.

**"The padlock means the company is verified."** For ordinary certificates it
means only that someone proved control of the domain name. Nothing about who they
are.

**"TLS protects data on the server."** It protects data *in transit*. Once it
arrives, it is plain text in your app's memory and your database. Storage
security is a separate job — which is why passwords are hashed (file 08).

**"I should encrypt the password before sending it."** No. Send it over TLS and
hash it *on the server*. Client-side hashing just makes the hash the password —
an attacker who captures it can replay it. Let TLS do the transport job.

## Remember this

- TLS gives confidentiality, integrity **and** server authentication; the third
  makes the others meaningful.
- HTTPS protects the pipe. It says nothing about who may call your API.
- Your tokens are bearer credentials on every request — TLS is what keeps them
  from being read in transit.
