# Streaming, proxies and buffering — why your Predict screen updates twice

When you tap Predict, the answer now arrives in two pieces: the main read at
about 6 seconds, and the second model's opinion 10–20 seconds later. That only
works if every machine between the server and your phone agrees to pass data
along *as it arrives* rather than collecting it all first.

This doc explains what sits in that path, what "buffering" means, and how to
check it yourself. No prior networking knowledge assumed.

> **A correction worth leading with.** While building this I warned you about
> "nginx buffering". **You don't run nginx.** StockPulse reaches your phone
> through **Tailscale**. The concern is real and the mechanism is the same, but I
> named the wrong software — so this doc describes what you actually have.

---

## 1. The problem streaming solves

The two AI models finish at very different times. Measured on your own server:

| Model | Time to answer |
|---|---|
| OpenAI | ~6 seconds |
| DeepSeek | ~20–28 seconds |

Ask both and wait for both, and you stare at a loader for ~25 seconds holding an
answer that was ready at 6. So the server sends the first read the moment it has
it, then sends the second opinion later on the *same open connection*.

That technique is **Server-Sent Events** (SSE): one HTTP response that stays open
and dribbles out messages over time, instead of closing when it's done.

```
event: stage    data: {"stage": "analyze"}
event: result   data: {...the main read...}      ← ~6s
event: second   data: {"secondOpinion": {...}}   ← ~28s
```

Same connection, three deliveries. Ordinary HTTP is one question, one answer,
connection closed. SSE keeps the line open.

---

## 2. What a reverse proxy is, and why you have one

Your app does **not** talk to the Python process directly. Something sits in
front. That something is a **reverse proxy**: a program that accepts the request
from outside, forwards it to your app, and passes the reply back.

"Reverse" because a normal (forward) proxy sits in front of *you* to reach the
internet; this sits in front of the *server* to receive from the internet.

Why bother?

- **HTTPS.** Your app speaks plain HTTP on port 8000. The proxy handles the
  certificate so the phone gets a real `https://` connection.
- **Not exposing the app directly.** `docker-compose.yml` binds the port to
  `127.0.0.1:8000` — reachable only from the server itself. Nothing on the open
  internet can dial it. The proxy is the only door.
- **One address.** `stockpulse.tail50f5ea.ts.net` instead of a raw IP and port.

### Your actual path

```
  phone  ──https──▶  Tailscale  ──http──▶  Docker  ──▶  uvicorn (FastAPI)
                    (the proxy)          127.0.0.1:8000
```

Tailscale is a private network that makes your devices act as if they're on the
same LAN, wherever they are. Its `serve`/`funnel` feature is the reverse proxy
here: it terminates HTTPS, gives you that `.ts.net` name, and forwards inward.

**nginx is the proxy most tutorials use** for this job, which is why it's the
name that comes up. You've simply solved the same problem a different way.

---

## 3. Buffering — the thing that breaks streaming

A proxy has a choice about *when* to pass data along:

**Buffered** — collect the whole response, then send it in one go.
**Streaming** — pass each chunk straight through as it arrives.

Buffering is the sensible default for normal web pages. Sending one 40 KB reply
is more efficient than forty 1 KB ones, and a slow client can't tie up the app
while it dawdles.

But buffering is fatal to SSE. The proxy waits for the response to *finish* — and
an SSE response doesn't finish until the last event. So:

| | What the server does | What you'd see |
|---|---|---|
| **Streaming** | result at 6s, second at 28s | read at 6s, card fills in later ✅ |
| **Buffered** | result at 6s, second at 28s | **nothing until 28s, then everything at once** ❌ |

The server behaves identically. The proxy silently converts a responsive screen
into a slow one. Nothing errors, no log line — it just feels broken.

> This is why the bug is worth understanding rather than guessing at: the symptom
> (slow) points at the AI, but the cause is a middleman being helpful.

---

## 4. What we do about it

Three defences, in the order they matter:

**1. The right content type.** The server replies with
`Content-Type: text/event-stream`. This is the important one — it's the standard
signal for "this is a live stream, don't hold it". Well-behaved proxies key off
it automatically. Tailscale's proxy is built on Go's standard reverse proxy,
which flushes immediately when it sees that type, so it should stream correctly
without configuration.

**2. `X-Accel-Buffering: no`.** An **nginx-specific** header meaning "don't
buffer this response". We send it from `app/api/stream.py`:

```python
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
```

Since you don't run nginx, **this header currently does nothing for you.** It's
harmless — unknown headers are ignored — and it's there so that putting nginx in
front later works without anyone remembering why.

**3. Keep-alive comments.** If nothing happens for 15 seconds, the server emits a
bare `: keep-alive` line. Proxies and phone networks close connections that look
idle, and a stream waiting on a slow model looks exactly like a dead one. The
comment is ignored by the client but proves the connection is alive.

**4. A fallback.** If streaming fails for any reason, the app quietly retries the
plain `/api/predict` endpoint, which waits for everything and returns one JSON
blob. Slower, but you still get your answer. See `streamOrFallback` in
`mobile/src/data/api.ts`.

That last one matters: **buffering degrades the experience, it never loses your
prediction.**

---

## 5. Checking it yourself

The honest test is watching the timestamps. From your laptop:

```bash
curl -N -H "Authorization: Bearer <your token>" \
  "https://stockpulse.tail50f5ea.ts.net/api/predict/stream?q=WDC&mode=both"
```

`-N` disables *curl's own* buffering — leave it off and you'll blame the proxy
for something curl did.

Watch how the lines appear:

- **Streaming works:** a few `stage` lines immediately, `result` after ~6s, a
  pause, then `second`.
- **Something is buffering:** nothing at all for ~30 seconds, then the whole lot
  in one burst.

In the app, the tell is the dashed *"Asking deepseek for a second opinion…"* box.
If you see it, streaming works — the main read arrived while the second was still
running. If the screen goes straight from loader to a complete result with the
second-opinion card already filled in, something buffered.

### A trap I fell into

My first end-to-end test used FastAPI's `TestClient`, and every event came back
with an identical timestamp. That looks like total buffering — but `TestClient`
collects the whole response before handing it over. **The test was incapable of
measuring the thing it was testing**, and would have "passed" either way.

The numbers in this doc come from a real `uvicorn` process over real HTTP. If you
ever check this, make sure your tool actually streams.

---

## 6. If you ever put nginx (or Cloudflare) in front

Should you move off Tailscale to a normal domain, this becomes live again.

**nginx** buffers proxied responses by default. The SSE location needs:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;          # the important line
    proxy_cache off;
    proxy_read_timeout 300s;      # a slow model must not look like a hang
    proxy_set_header Connection '';
    proxy_http_version 1.1;       # SSE needs HTTP/1.1, not 1.0
}
```

The `X-Accel-Buffering: no` header we already send does the same job per-response,
so in practice either would work — belt and braces.

**Cloudflare** proxying (the orange cloud) buffers some responses. It generally
passes `text/event-stream` through, but it's a known source of this exact
confusion. If streaming breaks the day you add Cloudflare, that's your suspect.

---

## Mini-glossary

- **Reverse proxy** — a program in front of your app that receives outside
  requests and forwards them in. Handles HTTPS so your app doesn't have to.
- **SSE (Server-Sent Events)** — one HTTP response held open, carrying multiple
  messages over time. Server → client only.
- **Buffering** — holding data to send it in fewer, larger pieces. Good for
  pages, fatal for streams.
- **Flush** — pushing buffered bytes onward immediately instead of waiting.
- **Keep-alive** — traffic sent purely to prove a connection is still alive.
- **`127.0.0.1` / localhost** — "this machine only". A port bound here cannot be
  reached from the internet.
