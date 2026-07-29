"""Briefing retrieval (Step A): pull the latest news and window it by time.

The briefing does NOT read the stored database — each run fetches fresh news
via the existing collectors, then keeps only what is genuinely recent. The
key discipline is timestamps: an item's ``published_at`` (when the world got
the news), never ``collected_at`` (when we happened to poll), decides
freshness. Items with a usable, in-window timestamp are ``fresh``; items with
no timestamp are kept but ``unverified`` (never silently trusted as new);
items with a timestamp older than the window are dropped.

Web search (the model pulling news itself) is a later step; here retrieval is
our two RSS sources only, so it stays cheap and deterministic.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.collectors.base import NewsCollector
from app.collectors.sources import (
    build_macro_collector,
    build_watchlist_collector,
    collect_from,
)
from app.config import Settings, get_settings
from app.models.article import NewsArticle

logger = logging.getLogger("stockpulse.briefing.retrieval")

# Phrases that betray a recap/roundup: a fresh *publish* time but *old* events.
# A mechanical pre-signal only — the model makes the final temporal call.
_RECAP_MARKERS = (
    "week in review",
    "week ahead",
    "weekly recap",
    "weekly wrap",
    "wrap-up",
    "wrap up",
    "roundup",
    "round-up",
    "recap",
    "in case you missed",
    "icymi",
    "what to know",
    "what to watch",
    "here's what happened",
    "biggest stories",
    "top stories",
    "this week in",
    "month in review",
    "year in review",
    "5 things",
    "things to know",
)


def looks_like_recap(title: str | None, summary: str | None = None) -> bool:
    """Heuristic: does this read like a recap/roundup rather than fresh news?"""
    text = f"{title or ''} {summary or ''}".lower()
    return any(marker in text for marker in _RECAP_MARKERS)


@dataclass
class RetrievedItem:
    """A fetched article with a freshness verdict for the briefing."""

    article: NewsArticle
    age_hours: float | None  # hours since published_at; None if no timestamp
    timestamp_verified: bool  # had a usable published_at at all
    within_window: bool  # verified AND within the freshness window
    likely_recap: bool = False  # title/summary reads like a roundup, not fresh news

    @property
    def title(self) -> str:
        return self.article.title

    @property
    def source(self) -> str:
        return self.article.source

    @property
    def url(self) -> str:
        return self.article.url

    @property
    def summary(self) -> str | None:
        return self.article.summary

    @property
    def published_at(self) -> datetime | None:
        return self.article.published_at


@dataclass
class RetrievalResult:
    """The outcome of one retrieval pass."""

    now: datetime
    window_hours: float
    fresh: list[RetrievedItem]  # in-window, timestamp-verified — the spine
    unverified: list[RetrievedItem]  # no usable timestamp — kept but flagged
    collected: int  # total articles fetched before windowing
    stale_dropped: int  # had a timestamp but older than the window

    @property
    def usable(self) -> list[RetrievedItem]:
        """Fresh items first, then unverified ones (flagged for the analyst)."""
        return self.fresh + self.unverified

    @property
    def has_any(self) -> bool:
        return bool(self.fresh or self.unverified)


def _as_utc(value: datetime) -> datetime:
    """Coerce a datetime to UTC; treat naive values as already-UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assess_freshness(
    article: NewsArticle, *, now: datetime, window_hours: float
) -> RetrievedItem:
    """Classify one article's freshness against the window.

    No timestamp => unverified (kept, flagged). A timestamp within
    ``window_hours`` of ``now`` => fresh; older => not within window.
    """
    recap = looks_like_recap(article.title, article.summary)
    published = article.published_at
    if published is None:
        return RetrievedItem(
            article,
            age_hours=None,
            timestamp_verified=False,
            within_window=False,
            likely_recap=recap,
        )

    age_hours = (now - _as_utc(published)).total_seconds() / 3600.0
    # A small negative age (feed clock slightly ahead of ours) still counts
    # as within the window; only clearly-old items fall out.
    within = age_hours <= window_hours
    return RetrievedItem(
        article,
        age_hours=age_hours,
        timestamp_verified=True,
        within_window=within,
        likely_recap=recap,
    )


async def retrieve_fresh_news(
    *,
    window_hours: float,
    now: datetime | None = None,
    collectors: list[NewsCollector] | None = None,
    settings: Settings | None = None,
) -> RetrievalResult:
    """Fetch the latest news and split it into fresh / unverified / stale.

    ``collectors`` defaults to both live sources (watchlist + macro); tests
    pass their own. Deduplication by URL is handled by ``collect_from``.
    """
    settings = settings or get_settings()
    now = now or datetime.now(tz=UTC)
    if collectors is None:
        collectors = [build_watchlist_collector(settings), build_macro_collector(settings)]

    articles = await collect_from(collectors)

    fresh: list[RetrievedItem] = []
    unverified: list[RetrievedItem] = []
    stale_dropped = 0
    for article in articles:
        item = assess_freshness(article, now=now, window_hours=window_hours)
        if item.within_window:
            fresh.append(item)
        elif not item.timestamp_verified:
            unverified.append(item)
        else:
            stale_dropped += 1

    # Freshest first so downstream truncation keeps the most recent news.
    fresh.sort(key=lambda i: i.age_hours if i.age_hours is not None else 1e9)

    logger.info(
        "Briefing retrieval -- collected=%d fresh=%d unverified=%d stale_dropped=%d window=%.0fh",
        len(articles),
        len(fresh),
        len(unverified),
        stale_dropped,
        window_hours,
    )
    return RetrievalResult(
        now=now,
        window_hours=window_hours,
        fresh=fresh,
        unverified=unverified,
        collected=len(articles),
        stale_dropped=stale_dropped,
    )
