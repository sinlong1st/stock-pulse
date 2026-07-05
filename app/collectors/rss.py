"""RSS-based news collector.

Fetching (httpx) is separated from parsing (feedparser) so parsing can be
unit-tested against static feed content without any network access.
"""

import logging

import feedparser
import httpx

from app.collectors.base import NewsCollector
from app.models.article import NewsArticle
from app.pipeline.normalizer import normalize_article

logger = logging.getLogger("stockpulse.collectors.rss")

_USER_AGENT = "StockPulse/0.1 (+https://github.com/stockpulse)"


class RSSCollector(NewsCollector):
    """Collect articles from a single RSS/Atom feed."""

    def __init__(
        self,
        source_name: str,
        feed_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.source_name = source_name
        self.feed_url = feed_url
        self.timeout = timeout
        # transport is an injection seam for tests (httpx.MockTransport).
        self._transport = transport

    async def collect(self) -> list[NewsArticle]:
        """Fetch the feed over HTTP and return normalized articles."""
        raw = await self._fetch()
        return self.parse(raw)

    async def _fetch(self) -> bytes:
        """Download the raw feed bytes with a bounded timeout."""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            return response.content

    def parse(self, raw: bytes | str) -> list[NewsArticle]:
        """Parse raw feed content into normalized articles.

        A single malformed entry is logged and skipped rather than failing
        the whole batch.
        """
        feed = feedparser.parse(raw)
        articles: list[NewsArticle] = []
        for entry in feed.entries:
            try:
                article = normalize_article(
                    source=self.source_name,
                    raw_title=entry.get("title"),
                    raw_url=entry.get("link"),
                    raw_summary=entry.get("summary"),
                    published_struct=entry.get("published_parsed"),
                    external_id=entry.get("id"),
                )
            except Exception:
                logger.exception("Failed to normalize entry from %s", self.source_name)
                continue
            if article is not None:
                articles.append(article)

        logger.info("Parsed %d articles from %s", len(articles), self.source_name)
        return articles
