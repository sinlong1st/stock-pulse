"""News collectors."""

from app.collectors.base import NewsCollector
from app.collectors.multi import MultiRSSCollector
from app.collectors.rss import RSSCollector
from app.collectors.sources import (
    build_all_collectors,
    build_macro_collector,
    build_watchlist_collector,
    collect_from,
)

__all__ = [
    "NewsCollector",
    "RSSCollector",
    "MultiRSSCollector",
    "build_all_collectors",
    "build_macro_collector",
    "build_watchlist_collector",
    "collect_from",
]
