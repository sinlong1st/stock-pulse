"""A collector that fetches several RSS feeds and merges the results."""

import asyncio
import logging

import httpx

from app.collectors.base import NewsCollector
from app.collectors.rss import RSSCollector
from app.models.article import NewsArticle

logger = logging.getLogger("stockpulse.collectors.multi")


class MultiRSSCollector(NewsCollector):
    """Fetch multiple RSS feeds (e.g. one per ticker) under one source name.

    Feeds are fetched concurrently; a single failing feed is logged and
    skipped. Articles with the same URL across feeds are de-duplicated.
    """

    def __init__(
        self,
        source_name: str,
        feed_urls: list[str],
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.source_name = source_name
        self._collectors = [
            RSSCollector(source_name, url, timeout=timeout, transport=transport)
            for url in feed_urls
        ]

    async def collect(self) -> list[NewsArticle]:
        if not self._collectors:
            return []
        results = await asyncio.gather(
            *(c.collect() for c in self._collectors), return_exceptions=True
        )
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for collector, result in zip(self._collectors, results):
            if isinstance(result, Exception):
                logger.warning("Feed failed (%s): %s", collector.feed_url, result)
                continue
            for article in result:
                if article.url in seen:
                    continue
                seen.add(article.url)
                articles.append(article)
        logger.info("Collected %d articles from %d feeds", len(articles), len(self._collectors))
        return articles
