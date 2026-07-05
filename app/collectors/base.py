"""Collector interface.

Every news source is wrapped in a collector that returns normalized
`NewsArticle` objects, so adding a source does not change the rest of the
pipeline.
"""

from abc import ABC, abstractmethod

from app.models.article import NewsArticle


class NewsCollector(ABC):
    """Fetches articles from a single news source."""

    #: Human-readable source name attached to every article (e.g. "Yahoo Finance").
    source_name: str

    @abstractmethod
    async def collect(self) -> list[NewsArticle]:
        """Fetch and return normalized articles from this source."""
        raise NotImplementedError
