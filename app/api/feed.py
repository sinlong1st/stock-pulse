"""Build the mobile feed from stored, classified articles.

Read-only: it reads the same rows the web dashboard shows and reshapes them
into the JSON the mobile app expects. It never writes, and touches nothing in
the news/alert/Telegram pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import ArticleRepository, ClassificationRepository

# The mobile app only renders these enums; map the backend's extras onto them.
_CATEGORIES = {"MACRO", "TICKER", "SECTOR"}
_IMPORTANCES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


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


def build_feed(session: Session, *, limit: int = 30) -> list[dict]:
    """Return recent, market-relevant classified articles in the app's shape."""
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
                "price": None,  # price context comes later (per-ticker fetch)
            }
        )
        if len(feed) >= limit:
            break
    return feed
