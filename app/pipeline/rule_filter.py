"""Rule-based relevance filter (pipeline Step 4).

Cheap, deterministic matching that decides whether an article is worth
sending to the (paid) AI classifier. It matches:

- watchlist ticker symbols (case-sensitive, e.g. NVDA or $NVDA),
- company-name aliases (case-insensitive, e.g. "Nvidia"),
- macro keywords (e.g. "Federal Reserve", "CPI"),
- sector keywords (e.g. "semiconductor", "bitcoin").

This does not decide importance — only "plausibly market-relevant or
not". The AI (Phase 4) and the app (Phase 5) make the real decisions.
"""

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from app.models.article import NewsArticle
from app.pipeline.keywords import (
    DEFAULT_COMPANY_ALIASES,
    DEFAULT_MACRO_KEYWORDS,
    DEFAULT_SECTOR_KEYWORDS,
)
from app.watchlist import get_watchlist_config


@dataclass
class RelevanceResult:
    """Outcome of rule-based filtering for a single article."""

    is_relevant: bool
    score: int
    matched_tickers: list[str] = field(default_factory=list)
    matched_macro: list[str] = field(default_factory=list)
    matched_sectors: list[str] = field(default_factory=list)
    category_hint: str | None = None  # "TICKER" | "MACRO" | "SECTOR" | None

    def to_dict(self) -> dict:
        return asdict(self)


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Whole-word, case-insensitive matcher for a keyword or phrase."""
    return re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", re.IGNORECASE)


def _ticker_pattern(ticker: str) -> re.Pattern[str]:
    """Whole-word, case-sensitive matcher for a ticker, allowing a `$` prefix."""
    return re.compile(rf"(?<![\w$])\$?{re.escape(ticker)}(?![\w])")


class RuleFilter:
    """Evaluate articles for cheap, keyword-based relevance."""

    def __init__(
        self,
        watchlist: list[str],
        *,
        company_aliases: dict[str, list[str]] | None = None,
        macro_keywords: list[str] | None = None,
        sector_keywords: dict[str, list[str]] | None = None,
    ) -> None:
        aliases = company_aliases if company_aliases is not None else DEFAULT_COMPANY_ALIASES
        macro = macro_keywords if macro_keywords is not None else DEFAULT_MACRO_KEYWORDS
        sectors = sector_keywords if sector_keywords is not None else DEFAULT_SECTOR_KEYWORDS

        self._ticker_patterns = {t: _ticker_pattern(t) for t in watchlist}
        self._alias_patterns = {
            ticker: [_keyword_pattern(name) for name in names]
            for ticker, names in aliases.items()
        }
        self._macro_patterns = {kw: _keyword_pattern(kw) for kw in macro}
        self._sector_patterns = {
            sector: [_keyword_pattern(kw) for kw in kws] for sector, kws in sectors.items()
        }

    def evaluate(self, article: NewsArticle) -> RelevanceResult:
        text = f"{article.title} {article.summary or ''}"

        matched_tickers: list[str] = []
        for ticker, pattern in self._ticker_patterns.items():
            if pattern.search(text):
                matched_tickers.append(ticker)
        # Company-name aliases also imply their ticker.
        for ticker, patterns in self._alias_patterns.items():
            if ticker in matched_tickers:
                continue
            if any(p.search(text) for p in patterns):
                matched_tickers.append(ticker)

        matched_macro = [kw for kw, p in self._macro_patterns.items() if p.search(text)]
        matched_sectors = [
            sector for sector, patterns in self._sector_patterns.items()
            if any(p.search(text) for p in patterns)
        ]

        score = len(matched_tickers) + len(matched_macro) + len(matched_sectors)
        if matched_tickers:
            category_hint = "TICKER"
        elif matched_macro:
            category_hint = "MACRO"
        elif matched_sectors:
            category_hint = "SECTOR"
        else:
            category_hint = None

        return RelevanceResult(
            is_relevant=score > 0,
            score=score,
            matched_tickers=matched_tickers,
            matched_macro=matched_macro,
            matched_sectors=matched_sectors,
            category_hint=category_hint,
        )

    def is_relevant(self, article: NewsArticle) -> bool:
        return self.evaluate(article).is_relevant


@lru_cache
def get_rule_filter() -> RuleFilter:
    """Return a process-wide RuleFilter built from the watchlist config file."""
    config = get_watchlist_config()
    return RuleFilter(list(config.tickers), company_aliases=config.aliases)
