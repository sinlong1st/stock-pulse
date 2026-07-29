"""Focused single-stock reports: `/report WDC`, `/report spacex`, `/report micosoft`.

Two jobs here:

1. **Resolve** the user's free text to a target. A local fuzzy match against the
   watchlist (tickers + company aliases) catches typos like ``wdcc`` -> WDC and
   names like ``spacex`` -> SPCX, so we can fetch the *right* news. If nothing
   matches locally, we keep the raw text and lean on the analyst's common sense.
2. **Retrieve** news narrowed to that one name (its Yahoo per-ticker feed, if we
   resolved a ticker, plus a Google News search).

The analyst still does the final common-sense interpretation (see
``analyst.build_system_prompt`` focus mode) — this module just makes the news
we hand it as on-target as possible.
"""

import difflib
from dataclasses import dataclass
from urllib.parse import quote_plus

from app.collectors.base import NewsCollector
from app.collectors.rss import RSSCollector
from app.config import Settings, get_settings
from app.watchlist import WatchlistConfig, get_watchlist_config


@dataclass
class FocusTarget:
    """A resolved (or best-effort) single-stock report target."""

    query: str  # the raw user text, e.g. "micosoft"
    ticker: str | None  # resolved watchlist ticker, if matched
    name: str | None  # canonical company name, if known
    search_term: str  # what to search news for (company name or raw query)

    @property
    def subject_label(self) -> str:
        """Short label for the report title (ticker if known, else the query)."""
        return self.ticker or self.query.strip().upper()

    @property
    def describe(self) -> str:
        """A hint line for the analyst prompt."""
        if self.ticker and self.name:
            return f'"{self.query}" (looks like {self.name} / {self.ticker})'
        if self.ticker:
            return f'"{self.query}" (looks like {self.ticker})'
        return f'"{self.query}"'


def parse_focus(text: str, command: str) -> str | None:
    """Extract the argument after the command: "/report wdc" -> "wdc".

    Returns None for a bare "/report" (full watchlist briefing).
    """
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    return arg or None


def resolve_focus(query: str, watchlist: WatchlistConfig | None = None) -> FocusTarget:
    """Best-effort map free text to a watchlist ticker + company name."""
    wl = watchlist or get_watchlist_config()
    q = query.strip()
    ql = q.lower()

    def _first_name(ticker: str) -> str | None:
        names = wl.aliases.get(ticker) or []
        return names[0] if names else None

    # Exact ticker (e.g. "WDC", "wdc").
    if q.upper() in wl.tickers:
        name = _first_name(q.upper())
        return FocusTarget(query, q.upper(), name, name or q.upper())

    # Exact alias (e.g. "microsoft").
    for ticker, names in wl.aliases.items():
        if any(n.lower() == ql for n in names):
            name = _first_name(ticker)
            return FocusTarget(query, ticker, name, name or ticker)

    # Fuzzy against tickers + alias names (e.g. "wdcc" -> wdc, "micosoft" -> microsoft).
    candidates: dict[str, tuple[str, str | None]] = {}
    for ticker in wl.tickers:
        candidates.setdefault(ticker.lower(), (ticker, _first_name(ticker)))
    for ticker, names in wl.aliases.items():
        for n in names:
            candidates.setdefault(n.lower(), (ticker, n))
    match = difflib.get_close_matches(ql, list(candidates), n=1, cutoff=0.7)
    if match:
        ticker, name = candidates[match[0]]
        display = name or _first_name(ticker)
        return FocusTarget(query, ticker, display, display or ticker)

    # No local match — free text; the analyst interprets it. Search the raw query.
    return FocusTarget(query, None, None, q)


def build_focus_collectors(
    target: FocusTarget, settings: Settings | None = None
) -> list[NewsCollector]:
    """News sources narrowed to a single name: its Yahoo feed (if we have a
    ticker) plus a Google News search for the company/query."""
    settings = settings or get_settings()
    collectors: list[NewsCollector] = []
    if target.ticker:
        url = settings.yahoo_ticker_feed_url.format(ticker=quote_plus(target.ticker))
        collectors.append(RSSCollector("Yahoo Finance", url))
    gquery = f"{target.search_term} stock"
    gurl = settings.google_news_rss_url.format(query=quote_plus(gquery))
    collectors.append(RSSCollector("Google News", gurl))
    return collectors
