"""Build the configured news sources and collect from them.

Two independent sources so their fetch cadence can be tuned separately:

- **watchlist** — Yahoo Finance per-ticker feeds, one per watchlist ticker.
- **macro** — a Google News RSS search over the macro keywords.
"""

import asyncio
import logging
from urllib.parse import quote_plus

from app.collectors.base import NewsCollector
from app.collectors.multi import MultiRSSCollector
from app.collectors.rss import RSSCollector
from app.config import Settings, get_settings
from app.keyword_config import get_keyword_config
from app.models.article import NewsArticle
from app.watchlist import get_watchlist_config

logger = logging.getLogger("stockpulse.collectors.sources")


def build_watchlist_collector(settings: Settings | None = None) -> NewsCollector:
    """A collector over Yahoo per-ticker feeds for every watchlist ticker."""
    settings = settings or get_settings()
    tickers = list(get_watchlist_config().tickers)
    urls = [settings.yahoo_ticker_feed_url.format(ticker=quote_plus(t)) for t in tickers]
    return MultiRSSCollector("Yahoo Finance", urls)


def _macro_query(keywords: list[str]) -> str:
    """Build a Google News search query: phrases quoted, joined with OR."""
    terms = [f'"{k}"' if " " in k else k for k in keywords]
    return " OR ".join(terms)


def build_macro_collector(settings: Settings | None = None) -> NewsCollector:
    """A collector over a Google News RSS search for the macro keywords."""
    settings = settings or get_settings()
    query = _macro_query(get_keyword_config().macro)
    url = settings.google_news_rss_url.format(query=quote_plus(query))
    return RSSCollector("Google News", url)


def build_all_collectors(settings: Settings | None = None) -> list[NewsCollector]:
    """Both sources, for a manual full run."""
    settings = settings or get_settings()
    return [build_watchlist_collector(settings), build_macro_collector(settings)]


async def collect_from(collectors: list[NewsCollector]) -> list[NewsArticle]:
    """Collect from several collectors concurrently and merge (dedup by URL)."""
    if not collectors:
        return []
    results = await asyncio.gather(
        *(c.collect() for c in collectors), return_exceptions=True
    )
    articles: list[NewsArticle] = []
    seen: set[str] = set()
    for collector, result in zip(collectors, results):
        if isinstance(result, Exception):
            logger.warning("Collector '%s' failed: %s", collector.source_name, result)
            continue
        for article in result:
            if article.url in seen:
                continue
            seen.add(article.url)
            articles.append(article)
    return articles
