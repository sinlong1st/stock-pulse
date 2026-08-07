"""Resolve a company name (or ticker) to a stock symbol via Yahoo search.

Keyless, same provider family as the price feed. Used by /watch so you can type
'tesla' and get TSLA. Best-effort: returns None on no match or any error, so a
command never crashes over a lookup.
"""

import difflib
import logging
import re

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.commands.symbols")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockPulse/1.0"
_EQUITY_TYPES = {"EQUITY", "ETF"}

# Yahoo's fuzzy mode will answer *something* for almost any string — "rocketlab"
# comes back as ROCKETBOOT (0.74 similar). Naming the wrong company is worse than
# saying "not found", so the bar sits above that and below a real typo like
# "micosoft" -> Microsoft (0.94) or "teslaa" -> Tesla (0.91).
_FUZZY_MIN_SIMILARITY = 0.80


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _is_primary(symbol: str) -> bool:
    """True for a plain US listing. Yahoo suffixes foreign and derivative
    listings with an exchange code (MSFT34.SA, MSFT.NE, TL0.F); those are the
    same company but not the security this app is about."""
    return "." not in symbol


def _pick(hits: list[tuple[str, str]]) -> tuple[str, str]:
    """First primary US listing, else Yahoo's top hit."""
    for symbol, name in hits:
        if _is_primary(symbol):
            return symbol, name
    return hits[0]


def _similarity(query: str, symbol: str, name: str) -> float:
    """How much a candidate looks like what the user typed (0..1).

    Compared against the symbol, the whole name, and the name's first word —
    "teslaa" vs "Tesla, Inc." only scores well on that last one.
    """
    q = _norm(query)
    if not q:
        return 0.0
    candidates = [_norm(symbol), _norm(name)]
    first_word = (name or "").split()
    if first_word:
        candidates.append(_norm(first_word[0]))
    return max(
        (difflib.SequenceMatcher(None, q, c).ratio() for c in candidates if c),
        default=0.0,
    )


async def _search(
    query: str,
    *,
    settings: Settings,
    fuzzy: bool,
    transport: httpx.BaseTransport | None = None,
) -> list[tuple[str, str]]:
    """Yahoo search hits as (symbol, name), equities and ETFs only."""
    url = f"{settings.yahoo_search_url.rstrip('/')}/v1/finance/search"
    params: dict = {"q": query, "quotesCount": 5, "newsCount": 0}
    if fuzzy:
        params["enableFuzzyQuery"] = "true"
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Symbol search failed for %r: %s", query, exc)
        return []

    out: list[tuple[str, str]] = []
    for quote in data.get("quotes") or []:
        if quote.get("quoteType") in _EQUITY_TYPES and quote.get("symbol"):
            symbol = str(quote["symbol"]).strip().upper()
            name = str(quote.get("shortname") or quote.get("longname") or symbol).strip()
            out.append((symbol, name))
    return out


async def resolve_symbol(
    query: str,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str] | None:
    """Return (symbol, display_name) for a query, or None if not found.

    Tries an exact search first, then Yahoo's fuzzy mode — but a fuzzy hit is
    only taken when the result actually resembles the query, because fuzzy will
    otherwise happily map "rocketlab" onto ROCKETBOOT.
    """
    query = query.strip()
    if not query:
        return None
    settings = settings or get_settings()

    exact = await _search(query, settings=settings, fuzzy=False, transport=transport)
    if exact:
        return _pick(exact)

    fuzzy = await _search(query, settings=settings, fuzzy=True, transport=transport)
    if not fuzzy:
        return None

    # Rank by how much it looks like the query, then prefer the primary US
    # listing, then keep Yahoo's own ordering. Without the middle term a search
    # for "micosoft" lands on MSFT34.SA (a Brazilian DRN) instead of MSFT —
    # they score identically on the name.
    best = max(
        (
            (_similarity(query, symbol, name), _is_primary(symbol), -index, symbol, name)
            for index, (symbol, name) in enumerate(fuzzy)
        )
    )
    score, _, _, symbol, name = best
    if score >= _FUZZY_MIN_SIMILARITY:
        logger.info("Fuzzy-matched %r -> %s (%s, similarity %.2f)", query, symbol, name, score)
        return symbol, name
    logger.info(
        "Rejected fuzzy match for %r: best was %s (%s) at %.2f", query, symbol, name, score
    )
    return None


_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_ASK_TICKER = (
    "Which US-listed stock ticker does this refer to? The user may have "
    "misspelled it or run the words together.\n\n"
    "Reply with ONLY the ticker symbol in capitals (e.g. RKLB), or the single "
    "word NONE if you are not confident. No explanation, no punctuation."
)


async def _ask_ai_for_ticker(
    query: str,
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
) -> str | None:
    """Ask a cheap model what the user meant. Returns a ticker or None."""
    if not settings.openai_api_key:
        return None
    payload = {
        "model": settings.openai_model,
        "temperature": 0,
        "max_tokens": 8,  # a ticker, nothing more
        "messages": [
            {"role": "system", "content": _ASK_TICKER},
            {"role": "user", "content": query},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, transport=transport) as client:
            resp = await client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            guess = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        logger.warning("AI ticker lookup failed for %r: %s", query, exc)
        return None

    guess = (guess or "").strip().upper().strip(".,'\"")
    if guess in ("", "NONE") or not _TICKER_RE.match(guess):
        return None
    return guess


async def resolve_symbol_smart(
    query: str,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str] | None:
    """`resolve_symbol`, with an AI fallback for what search can't reach.

    Yahoo's search is unforgiving about run-together words: "rocket lab" finds
    RKLB but "rocketlab" finds nothing, and fuzzy mode returns a different
    company entirely. When both deterministic paths fail we ask a cheap model
    what was meant — then **verify that ticker really exists** through the same
    search, so a hallucinated symbol can never reach the caller.
    """
    settings = settings or get_settings()
    found = await resolve_symbol(query, settings=settings, transport=transport)
    if found:
        return found

    guess = await _ask_ai_for_ticker(query, settings, transport)
    if not guess:
        return None
    verified = await resolve_symbol(guess, settings=settings, transport=transport)
    if verified and verified[0] == guess:
        logger.info("AI resolved %r -> %s (%s)", query, verified[0], verified[1])
        return verified
    logger.info("AI guessed %r for %r but it did not verify; giving up.", guess, query)
    return None
