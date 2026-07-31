"""Build the mobile watchlist: your tracked tickers with live-ish prices.

Read-only. Prices are best-effort (Yahoo, same source the reports use); a
ticker whose price can't be fetched still appears, just without a price.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.config import Settings, resolve_briefing_timezone
from app.prices import maybe_briefing_price_client, price_freshness
from app.watchlist import get_watchlist_config

logger = logging.getLogger("stockpulse.api.watchlist")


async def build_watchlist(settings: Settings) -> list[dict]:
    """Return each watchlist ticker with its name and a best-effort price."""
    config = get_watchlist_config()
    client = maybe_briefing_price_client(settings)
    tz = resolve_briefing_timezone(settings)
    now = datetime.now(tz=UTC)

    async def one(ticker: str) -> dict:
        names = config.aliases.get(ticker) or []
        name = names[0] if names else ticker
        snap = None
        if client is not None:
            try:
                snap = await client.snapshot(ticker)
            except Exception:
                logger.debug("Snapshot failed for %s", ticker, exc_info=True)
        if snap is None:
            return {"ticker": ticker, "name": name, "price": None, "changePct": None, "fresh": None}
        chg = snap.change_from_open_pct
        if chg is None:
            chg = snap.change_from_prev_pct
        return {
            "ticker": ticker,
            "name": name,
            "price": f"{snap.price:,.2f}",
            "changePct": round(chg, 1) if chg is not None else None,
            "fresh": price_freshness(snap.price_time, now=now, tz_name=tz).upper(),
        }

    return list(await asyncio.gather(*[one(t) for t in config.tickers]))
