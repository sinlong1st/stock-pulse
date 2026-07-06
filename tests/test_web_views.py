"""Tests for the read-only news HTML view."""

from datetime import UTC, datetime

from app.models.article import NewsArticle
from app.web.views import render_news_page


def _article(title: str, summary: str | None = None) -> NewsArticle:
    return NewsArticle(
        source="Test Source",
        title=title,
        summary=summary,
        url="https://example.com/a",
        published_at=datetime.now(tz=UTC),
        collected_at=datetime.now(tz=UTC),
        content_hash="x" * 64,
    )


def test_render_lists_articles_and_count() -> None:
    html = render_news_page([_article("Fed holds rates"), _article("NVDA up")], stored_total=2)
    assert "Fed holds rates" in html
    assert "NVDA up" in html
    assert "2 stored articles" in html


def test_render_escapes_html_to_prevent_injection() -> None:
    html = render_news_page([_article("<script>alert(1)</script>")])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_handles_empty_list() -> None:
    html = render_news_page([], stored_total=0)
    assert "No stored articles yet" in html


def test_render_shows_match_chips_for_relevant_articles() -> None:
    from app.pipeline.rule_filter import RuleFilter

    article = _article("NVDA jumps on strong demand")
    result = RuleFilter(["NVDA"]).evaluate(article)
    html = render_news_page([article], stored_total=1, evaluations=[result])
    assert "chip-ticker" in html
    assert "NVDA" in html
    assert "1 match the filter" in html


def test_render_bolds_matched_keywords_in_title() -> None:
    from app.pipeline.rule_filter import RuleFilter

    article = _article("Nvidia unveils a new chip")
    result = RuleFilter(["NVDA"]).evaluate(article)
    html = render_news_page([article], stored_total=1, evaluations=[result])
    assert "<strong>Nvidia</strong>" in html


def test_render_adds_data_relevant_attribute_and_toggle() -> None:
    from app.pipeline.rule_filter import RuleFilter

    rf = RuleFilter(["NVDA"])
    relevant = _article("NVDA rallies")
    noise = _article("Local bakery wins award")
    evals = [rf.evaluate(relevant), rf.evaluate(noise)]
    html = render_news_page([relevant, noise], stored_total=2, evaluations=evals)
    assert 'data-relevant="1"' in html
    assert 'data-relevant="0"' in html
    assert 'id="only-matches"' in html


def test_render_shows_ai_verdict_when_classified() -> None:
    from app.models.classification import ClassificationResult

    article = _article("Fed signals rate cuts")
    article.id = "42"
    verdict = ClassificationResult(
        is_market_relevant=True,
        importance="HIGH",
        category="MACRO",
        related_tickers=["QQQ"],
        summary="Fed may delay cuts.",
        why_it_matters="Higher-for-longer pressures tech.",
        should_alert=True,
        confidence=0.9,
    )
    html = render_news_page([article], stored_total=1, classifications={"42": verdict})
    assert "badge-HIGH" in html
    assert "HIGH" in html
    assert "Why it matters:" in html
    assert "Higher-for-longer pressures tech." in html
    assert "1 AI-analyzed" in html


def test_highlight_escapes_and_is_injection_safe() -> None:
    from app.web.views import _highlight

    out = _highlight("<script> NVDA", ["NVDA"])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<strong>NVDA</strong>" in out


def test_render_tolerates_naive_datetime() -> None:
    # Datetimes read back from SQLite are timezone-naive; rendering must not crash.
    article = _article("Fed holds rates")
    article.published_at = datetime(2026, 7, 5, 13, 0)  # naive, no tzinfo
    html = render_news_page([article], stored_total=1)
    assert "Fed holds rates" in html
