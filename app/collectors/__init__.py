"""News collectors."""

from app.collectors.base import NewsCollector
from app.collectors.rss import RSSCollector

__all__ = ["NewsCollector", "RSSCollector"]
