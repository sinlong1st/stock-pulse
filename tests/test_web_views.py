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
    html = render_news_page("Test Source", [_article("Fed holds rates"), _article("NVDA up")])
    assert "Fed holds rates" in html
    assert "NVDA up" in html
    assert "2 articles from Test Source" in html


def test_render_escapes_html_to_prevent_injection() -> None:
    html = render_news_page("Test Source", [_article("<script>alert(1)</script>")])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_handles_empty_list() -> None:
    html = render_news_page("Test Source", [])
    assert "No articles were collected" in html
