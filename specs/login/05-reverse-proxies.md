# 05 — Reverse proxies

## The problem

Your app is `uvicorn` serving FastAPI on port 8000, speaking plain HTTP. To be on
the public internet it now needs to:

- speak HTTPS on port 443, with a certificate
- obtain and renew that certificate
- redirect anyone arriving on port 80
- ideally: compress responses, cap request sizes, log requests, survive a restart
  without dropping connections

You *could* make uvicorn do TLS directly. You would then be running certificate
renewal inside your Python process, restarting your API to pick up a new
certificate, and rewriting all of it the day you add a second service.

## The idea

A **reverse proxy** sits in front and does the network-facing work, forwarding
plain HTTP inward.

```
                    ┌─────────── your droplet ───────────┐
                    │                                     │
  Phone ──HTTPS──►  │  Caddy :443        App :8000        │
                    │  ├ TLS termination  (127.0.0.1 only)│
                    │  ├ certificates                     │
                    │  └ proxy ──plain HTTP──►            │
                    │                                     │
                    └─────────────────────────────────────┘
```

"Forward proxy" sits in front of *clients* (a corporate web filter). "Reverse
proxy" sits in front of *servers*. Same machinery, opposite direction.

**Separation of concerns** is the real argument. Your app knows about stocks and
positions. It should not know about certificates. Each side can be replaced
without touching the other.

## Choosing one

| | Caddy | nginx + certbot | Cloudflare Tunnel |
|---|---|---|---|
| Config for this job | ~5 lines | ~30 lines + a cron job | dashboard + daemon |
| HTTPS | automatic | manual setup, cron renewal | automatic |
| Open ports needed | 80, 443 | 80, 443 | **none** |
| Streams SSE by default | yes | **no — buffers** | yes |
| Extra dependency | none | none | Cloudflare in the path |

**Caddy** is the recommendation: automatic HTTPS is a first-class feature, not an
add-on, and the config really is this:

```caddyfile
stockpulse.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

That obtains a certificate, renews it, redirects HTTP→HTTPS, and proxies. Nothing
else to write.

**nginx** is the industry default and enormously capable; it is rejected here
because certificate renewal becomes a separate cron job that fails silently, and
because of the buffering issue below.

**Cloudflare Tunnel** is genuinely attractive — a daemon on your droplet dials
*out* to Cloudflare, so you open **no inbound ports at all** and your droplet's IP
stays private. The trade is a third party in your request path. Worth revisiting
if your domain starts attracting noise.

## The buffering trap — this one bites StockPulse specifically

StockPulse streams. Report, Predict and the Exit Advisor send **Server-Sent
Events** so the loader can show real progress:

```
event: stage   data: {"stage":"prices"}      ← at 0.6s
event: stage   data: {"stage":"news"}        ← at 1.3s
event: result  data: {...}                   ← at 11s
```

A proxy that **buffers** collects the whole response before forwarding any of it.
Your stages then all arrive at once, at the end. The feature does not error — it
silently stops being a feature.

- **nginx buffers proxied responses by default.** You must set
  `proxy_buffering off;` for the streaming routes.
- **Caddy streams by default** and flushes immediately for `text/event-stream`.
- **Tailscale** (today) flushes correctly, which is why streaming works now.

The codebase already sends `X-Accel-Buffering: no`, an **nginx-specific** hint. It
is inert today and kept precisely so that a future nginx just works. See
`STREAMING_AND_PROXIES.md`.

**Verify it live, with the real thing:**

```bash
curl -N https://stockpulse.yourdomain.com/api/report/stream -H "Authorization: Bearer …"
```

Events should appear **as they happen**. If they all land together at the end, you
are buffering.

> A trap this project already fell into: FastAPI's `TestClient` **buffers the
> whole response**, so every event reports an identical timestamp. It cannot
> measure streaming and will "pass" either way. Use `curl -N` or a real
> `httpx.stream`.

## Other things the proxy should do

- **Request size limit** — cap bodies (say 1 MB) so nobody uploads gigabytes.
- **Timeouts** — but note your exit-advisor requests legitimately take ~20 s, so
  do not set an aggressive read timeout.
- **Security headers** — HSTS once you're confident in HTTPS.
- **Real client IP** — Caddy sets `X-Forwarded-For`; your rate limiter (file 13)
  needs it, otherwise every request appears to come from `127.0.0.1` and per-IP
  limiting silently does nothing.

That last one is a genuinely common bug: rate limiting behind a proxy that looks
correct, works in testing, and limits nothing in production.

## In StockPulse

- Caddy runs **on the host**, not in the container.
- `docker-compose.yml` keeps binding `127.0.0.1:8000` — the container is never
  directly reachable (see file 06).
- After switching, re-verify SSE with `curl -N` before turning Tailscale off. Do
  not assume; this project's own history is a list of assumptions that were wrong.

## Misconceptions

**"A reverse proxy makes me secure."** It terminates TLS and can enforce limits.
It has no idea who you are — that is authentication's job, and the proxy will
happily forward an anonymous `POST /run`.

**"Adding a proxy adds meaningful latency."** Sub-millisecond on the same machine.
Irrelevant next to a 20-second AI call.

**"I'll just expose uvicorn on 443."** You then own certificate renewal in
Python, restart your API to load new certificates, and rebuild all of it when you
add a second service.

## Remember this

- The proxy handles the network; your app handles the domain. Neither should
  learn the other's job.
- **Buffering silently kills SSE.** Caddy is fine by default; nginx is not.
  Verify with `curl -N`, never with `TestClient`.
- Behind a proxy, per-IP rate limiting needs the forwarded client IP or it limits
  nothing.
