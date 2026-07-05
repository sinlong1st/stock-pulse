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


def test_render_tolerates_naive_datetime() -> None:
    # Datetimes read back from SQLite are timezone-naive; rendering must not crash.
    article = _article("Fed holds rates")
    article.published_at = datetime(2026, 7, 5, 13, 0)  # naive, no tzinfo
    html = render_news_page([article], stored_total=1)
    assert "Fed holds rates" in html
