"""Build the mobile watchlist: your tracked tickers with live-ish prices and
each ticker's most-recent sentiment (derived from recent classified news).

Read-only. Prices are best-effort (Yahoo, same source the reports use); a
ticker whose price can't be fetched still appears, just without a price.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, resolve_briefing_timezone
from app.db import ArticleRepository, ClassificationRepository
from app.prices import maybe_briefing_price_client, price_freshness
from app.watchlist import get_watchlist_config

logger = logging.getLogger("stockpulse.api.watchlist")


def _latest_sentiment_by_ticker(session: Session, *, scan: int = 300) -> dict[str, str]:
    """Map ticker -> the sentiment of the most recent classified article
    that mentions it (newest wins)."""
    articles = ArticleRepository(session).list_recent(limit=scan)  # newest first
    results = ClassificationRepository(session).results_for_articles(
        [int(a.id) for a in articles if a.id]
    )
    out: dict[str, str] = {}
    for a in articles:
        c = results.get(int(a.id)) if a.id else None
        if not c:
            continue
        for ticker in c.related_tickers:
            out.setdefault(ticker, c.sentiment)  # first seen = most recent
    return out


async def build_watchlist(
    settings: Settings,
    *,
    session: Session | None = None,
    tickers: list[str] | None = None,
) -> list[dict]:
    """Return each watchlist ticker with its name, a best-effort price, and
    (when a DB session is given) its most-recent sentiment.

    ``tickers`` overrides the watchlist — used by the focused single-stock
    report, which prices just that one stock (on your watchlist or not)."""
    config = get_watchlist_config()
    wanted = list(tickers) if tickers is not None else list(config.tickers)
    client = maybe_briefing_price_client(settings)
    tz = resolve_briefing_timezone(settings)
    now = datetime.now(tz=UTC)
    sentiment = _latest_sentiment_by_ticker(session) if session is not None else {}

    async def one(ticker: str) -> dict:
        names = config.aliases.get(ticker) or []
        name = names[0] if names else ticker
        snap = None
        if client is not None:
            try:
                snap = await client.snapshot(ticker)
            except Exception:
                logger.debug("Snapshot failed for %s", ticker, exc_info=True)
        row = {
            "ticker": ticker,
            "name": name,
            "price": None,
            "changePct": None,
            "fresh": None,
            "sentiment": sentiment.get(ticker),
        }
        if snap is not None:
            chg = snap.change_from_open_pct
            if chg is None:
                chg = snap.change_from_prev_pct
            row["price"] = f"{snap.price:,.2f}"
            row["changePct"] = round(chg, 1) if chg is not None else None
            row["fresh"] = price_freshness(snap.price_time, now=now, tz_name=tz).upper()
        return row

    return list(await asyncio.gather(*[one(t) for t in wanted]))
