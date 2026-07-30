"""Resolve a company name (or ticker) to a stock symbol via Yahoo search.

Keyless, same provider family as the price feed. Used by /watch so you can type
'tesla' and get TSLA. Best-effort: returns None on no match or any error, so a
command never crashes over a lookup.
"""

import logging

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.commands.symbols")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockPulse/1.0"
_EQUITY_TYPES = {"EQUITY", "ETF"}


async def resolve_symbol(
    query: str,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str] | None:
    """Return (symbol, display_name) for a query, or None if not found.

    Picks the top EQUITY/ETF result. `transport` is an injection seam for tests.
    """
    query = query.strip()
    if not query:
        return None
    settings = settings or get_settings()
    url = f"{settings.yahoo_search_url.rstrip('/')}/v1/finance/search"
    params = {"q": query, "quotesCount": 5, "newsCount": 0}
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Symbol search failed for %r: %s", query, exc)
        return None

    for quote in data.get("quotes") or []:
        if quote.get("quoteType") in _EQUITY_TYPES and quote.get("symbol"):
            symbol = str(quote["symbol"]).strip().upper()
            name = str(quote.get("shortname") or quote.get("longname") or symbol).strip()
            return symbol, name
    return None
