# StockPulse — Manage-the-Watchlist Telegram Commands Plan

**Status:** proposal / design only. No code yet. This plans letting you view and
edit your watchlist from Telegram — the first commands that *change* config
rather than just report. (An earlier idea, position/P&L tracking, was dropped as
not worth it; this spec is watchlist management only.)

---

## 1. Why

Today the watchlist lives in `watchlist.json` — to change it you SSH to the
server, edit the file, and restart. That's friction for a "just add Tesla"
thought on the go. Goal: manage it from your phone, and have news + reports pick
up the change immediately (no restart).

---

## 2. The commands

| Command | Does | Reply |
|---|---|---|
| `/watchlist` | Show the current watchlist | tickers + their aliases |
| `/watch <name or ticker>` | Add a stock (resolve name → ticker) | "Added TSLA (Tesla)" or "already watching" |
| `/unwatch <ticker>` | Remove a stock | "Removed TSLA" or "not on the list" |
| `/help` | List available commands | one line per command |

Notes:
- `/watch tesla`, `/watch Tesla`, `/watch TSLA` all work — see resolution (§4).
- All reply in `OUTPUT_LANGUAGE` (Vietnamese).
- Owner-chat-only, exactly like `/report` (a stray command from elsewhere is
  ignored, so nobody else can edit your watchlist).

Out of scope (dropped): `/setac`, positions, P&L.

---

## 3. Generalize the listener into a command router

Right now `TelegramListener` matches **one** command (`/report`) and calls one
handler. We generalize it to a small **router**:

- The listener parses the first token of an owner message (already does, via
  `_command_token`) and looks it up in a **registry**: `{ "/report": handler,
  "/watchlist": handler, "/watch": handler, "/unwatch": handler, "/help": handler }`.
- Each handler has the signature `async def handler(args: str) -> str | None`
  where `args` is the text after the command. It returns a **reply string** the
  router sends back — or `None` if it sends its own messages (which `/report`
  does today: an ack, then the full brief).
- Unknown commands: optionally reply with a short help line, or ignore.

This keeps everything already true of the listener — owner-only, backlog-
skipping on boot, sequential handling, one poll loop — and just routes by name.
`/report`'s current behavior is preserved as one registered handler.

### Where it lives
- `app/commands/` (new): `router.py` (registry + dispatch) and
  `watchlist_cmds.py` (the `/watchlist`, `/addwl`, `/rmwl` handlers).
- `TelegramListener` gains a `handlers: dict[str, Handler]` instead of a single
  `command`/`on_command` (with a thin back-compat shim, or just migrate main.py).
- `app/main.py` builds the registry in the lifespan and passes it to the listener.

---

## 4. Name → ticker resolution (`/addwl tesla` → TSLA)

Use **Yahoo's keyless search endpoint** (same provider family as the price feed):

```
GET https://query1.finance.yahoo.com/v1/finance/search?q=tesla&quotesCount=5&newsCount=0
→ quotes: [{symbol: "TSLA", shortname: "Tesla, Inc.", quoteType: "EQUITY", ...}, ...]
```

- Pick the top `EQUITY` (or `ETF`) result: `symbol` becomes the ticker,
  `shortname` becomes the first alias.
- If the user typed something that's already a clean ticker (`TSLA`), the search
  still returns it first; no special-casing needed, but we can short-circuit an
  exact-symbol match to save a call.
- No match / ambiguous → reply "couldn't find a stock for 'xyz' — try the ticker
  symbol." Never guess silently.
- Isolated behind a helper (`resolve_symbol(query)`), injectable transport for
  tests — same pattern as every other outbound client.

Reuses the existing `app/briefing/focus.py` fuzzy matcher only for *existing*
watchlist names; adding a **new** name needs the search endpoint above.

---

## 5. Persisting the change

`watchlist.json` is the single source of truth (format: `{"TICKER": ["alias",
...]}`). On `/addwl` / `/rmwl`:

1. Load the current file (or defaults).
2. Apply the change (add `{"TSLA": ["Tesla, Inc."]}`, or drop the key).
3. Write the file back (pretty JSON, UTF-8, atomic write via temp-then-rename).
4. **Clear the cache:** `get_watchlist_config.cache_clear()` so the next news
   fetch, report, and classification see the new list without a restart.

Effects that follow naturally (no extra work):
- The **watchlist news collector** is rebuilt each run from the config, so it
  starts fetching TSLA's Yahoo feed next cycle.
- **Reports** price the whole watchlist, so TSLA appears in the price block.

### ⚠️ Docker change required
`docker-compose.yml` currently mounts `./watchlist.json:...:ro` (**read-only**).
For in-place edits we drop the `:ro`. `keywords.json` can stay read-only. Both
still live on the host, so edits survive rebuilds and are visible to you.

Concurrency: single process, sequential command handling → no locking needed.

---

## 6. Edge cases & safety
- **Duplicate add** → "already watching TSLA", no-op.
- **Remove a non-member** → "TSLA isn't on your watchlist."
- **Empty watchlist after remove** → allowed, but warn ("watchlist is now
  empty"); the config loader already falls back to built-in defaults if the file
  ends up empty, so we may instead refuse to remove the last one — decide in
  build.
- **Bad input** (`/addwl` with no argument) → short usage hint.
- **Search failure / Yahoo down** → "couldn't look that up right now, try
  again"; never write a broken entry.
- **Owner-only** enforced by the listener before any handler runs.

---

## 7. Config (proposed)
```
# Command names are configurable (defaults shown); the /report command already
# exists via BRIEFING_COMMAND.
WATCHLIST_SHOW_COMMAND=/watchlist
WATCHLIST_ADD_COMMAND=/addwl
WATCHLIST_REMOVE_COMMAND=/rmwl
YAHOO_SEARCH_URL=https://query1.finance.yahoo.com
```
All still gated by `BRIEFING_COMMAND_ENABLED` (the listener must be on).

---

## 8. Suggested build order
| Step | Piece | Notes |
|---|---|---|
| A | Command router (registry + dispatch), migrate `/report` onto it | no behavior change; tests |
| B | `/watchlist` + `/help` (read-only) | safest first — proves routing end-to-end |
| C | Symbol resolver (Yahoo search) + tests | keyless, mocked in tests |
| D | `/watch` + `/unwatch` with atomic write + cache-clear | the mutating part |
| E | Docker: make `watchlist.json` writable; docs | required to work in prod |

Ship A–B first (no writes) so the router is proven before anything edits config.

**Decisions (from review):** commands are `/watch` / `/unwatch` (+ `/watchlist`,
`/help`); removing the last ticker is warned-but-allowed; ambiguous `/watch`
auto-picks the top US equity (name shown so it's easy to `/unwatch` if wrong).

---

## 9. Open questions
1. **Refuse to remove the last ticker?** (An empty watchlist falls back to
   defaults, which may surprise you.) Lean: warn but allow.
2. **`/addwl` ambiguity:** if Yahoo returns several matches (e.g. a foreign
   listing), just take the top US equity, or reply with the choices to confirm?
3. **Aliases:** auto-use Yahoo's `shortname` as the alias — good enough, or let
   you set your own later?
4. **A `/help` command** listing all commands — worth adding while we're here?
5. **Naming:** `/addwl` /`/rmwl` vs `/watch` /`/unwatch` (or your `/setwl`)?
