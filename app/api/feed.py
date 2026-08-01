"""Build the mobile feed from stored, classified articles.

Read-only: it reads the same rows the web dashboard shows and reshapes them
into the JSON the mobile app expects. It never writes, and touches nothing in
the news/alert/Telegram pipeline. Best-effort prices are attached for each
item's primary ticker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, resolve_briefing_timezone
from app.db import ArticleRepository, ClassificationRepository
from app.prices import PriceClient, PriceSnapshot, maybe_briefing_price_client, price_freshness

logger = logging.getLogger("stockpulse.api.feed")

# The mobile app only renders these enums; map the backend's extras onto them.
_CATEGORIES = {"MACRO", "TICKER", "SECTOR"}
_IMPORTANCES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

_UNSET = object()


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _relative_time(dt: datetime | None, now: datetime) -> str:
    dt = _as_utc(dt)
    if dt is None:
        return ""
    secs = int((now - dt).total_seconds())
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


async def _snapshot_many(client: PriceClient, tickers: set[str]) -> dict[str, PriceSnapshot]:
    """Fetch a price snapshot for each ticker, concurrently and best-effort."""
    async def one(ticker: str) -> tuple[str, PriceSnapshot | None]:
        try:
            return ticker, await client.snapshot(ticker)
        except Exception:
            logger.debug("Snapshot failed for %s", ticker, exc_info=True)
            return ticker, None

    results = await asyncio.gather(*[one(t) for t in tickers])
    return {t: s for t, s in results if s is not None}


def _price_dict(snap: PriceSnapshot, *, tz: str, now: datetime) -> dict:
    chg = snap.change_from_open_pct
    if chg is None:
        chg = snap.change_from_prev_pct
    return {
        "symbol": snap.ticker,
        "price": f"{snap.price:,.2f}",
        "changePct": round(chg, 1) if chg is not None else None,
        "fresh": price_freshness(snap.price_time, now=now, tz_name=tz).upper(),
    }


async def build_feed(
    session: Session, settings: Settings, *, limit: int = 30, price_client: object = _UNSET
) -> list[dict]:
    """Return recent, market-relevant classified articles in the app's shape,
    with a best-effort price on each item's primary ticker."""
    # Over-fetch: not every recent article is classified/relevant.
    articles = ArticleRepository(session).list_recent(limit=limit * 4)
    ids = [int(a.id) for a in articles if a.id]
    results = ClassificationRepository(session).results_for_articles(ids)
    now = datetime.now(tz=UTC)

    feed: list[dict] = []
    for a in articles:
        if not a.id:
            continue
        c = results.get(int(a.id))
        if c is None or not c.is_market_relevant:
            continue
        feed.append(
            {
                "id": str(a.id),
                "importance": c.importance if c.importance in _IMPORTANCES else "LOW",
                "category": c.category if c.category in _CATEGORIES else "SECTOR",
                "time": _relative_time(a.published_at or a.collected_at, now),
                "summary": c.summary,
                "why": c.why_it_matters,
                "tickers": c.related_tickers,
                "sentiment": c.sentiment,
                "source": a.source,
                "url": a.url,
                "price": None,
            }
        )
        if len(feed) >= limit:
            break

    # Attach prices for each item's primary (first) ticker.
    client = maybe_briefing_price_client(settings) if price_client is _UNSET else price_client
    if client is not None:
        primary = {item["tickers"][0] for item in feed if item["tickers"]}
        if primary:
            snaps = await _snapshot_many(client, primary)
            tz = resolve_briefing_timezone(settings)
            for item in feed:
                ticker = item["tickers"][0] if item["tickers"] else None
                snap = snaps.get(ticker) if ticker else None
                if snap is not None:
                    item["price"] = _price_dict(snap, tz=tz, now=now)
    return feed
