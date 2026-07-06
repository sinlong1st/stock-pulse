"""Tests for rule-based relevance filtering (Phase 3)."""

from datetime import UTC, datetime

from app.models.article import NewsArticle
from app.pipeline.rule_filter import RuleFilter

WATCHLIST = ["QQQ", "NVDA", "AMD", "PLTR", "SOFI", "HOOD", "META", "AMZN"]


def _article(title: str, summary: str = "") -> NewsArticle:
    return NewsArticle(
        source="Test",
        title=title,
        summary=summary or None,
        url="https://example.com/a",
        collected_at=datetime.now(tz=UTC),
        content_hash="h" * 64,
    )


def _filter() -> RuleFilter:
    return RuleFilter(WATCHLIST)


def test_matches_ticker_symbol() -> None:
    result = _filter().evaluate(_article("NVDA jumps 5% on strong demand"))
    assert result.is_relevant
    assert "NVDA" in result.matched_tickers
    assert result.category_hint == "TICKER"


def test_matches_ticker_with_dollar_prefix() -> None:
    result = _filter().evaluate(_article("Traders pile into $AMD ahead of earnings"))
    assert "AMD" in result.matched_tickers


def test_matches_company_alias_case_insensitive() -> None:
    result = _filter().evaluate(_article("Amazon expands its AWS data centers"))
    assert "AMZN" in result.matched_tickers


def test_alias_implies_ticker_via_name() -> None:
    result = _filter().evaluate(_article("Nvidia unveils next-gen GPU"))
    assert "NVDA" in result.matched_tickers
    assert "AI/Semiconductor" in result.matched_sectors  # GPU keyword


def test_matches_macro_keywords() -> None:
    result = _filter().evaluate(_article("Federal Reserve signals a rate cut amid cooling inflation"))
    assert result.is_relevant
    assert result.category_hint == "MACRO"
    assert "Federal Reserve" in result.matched_macro
    assert "rate cut" in result.matched_macro
    assert "inflation" in result.matched_macro


def test_irrelevant_article_is_filtered_out() -> None:
    result = _filter().evaluate(_article("Local bakery wins a community award"))
    assert not result.is_relevant
    assert result.score == 0
    assert result.category_hint is None


def test_word_boundary_avoids_false_positive_meta_in_metadata() -> None:
    result = _filter().evaluate(_article("New metadata standard proposed for archives"))
    assert "META" not in result.matched_tickers


def test_word_boundary_avoids_false_positive_hood_in_neighborhood() -> None:
    result = _filter().evaluate(_article("A quiet neighborhood sees new construction"))
    assert "HOOD" not in result.matched_tickers


def test_fed_keyword_not_triggered_by_federal_substring_word() -> None:
    # "federated" should not match the "Fed" keyword due to word boundaries.
    result = RuleFilter(WATCHLIST).evaluate(_article("A federated learning breakthrough"))
    assert "Fed" not in result.matched_macro


def test_score_counts_multiple_signals() -> None:
    result = _filter().evaluate(_article("NVDA and AMD rise as the Fed weighs a rate hike"))
    assert result.score >= 3
    assert {"NVDA", "AMD"}.issubset(set(result.matched_tickers))
