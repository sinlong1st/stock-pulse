"""Unit tests for article normalization (Phase 1, Step 2)."""

import time
from datetime import UTC, datetime

from app.pipeline.normalizer import (
    clean_title,
    compute_content_hash,
    normalize_article,
    normalize_url,
    struct_time_to_utc,
)


def test_clean_title_unescapes_and_collapses_whitespace() -> None:
    assert clean_title("  Fed   raises\nrates &amp; more  ") == "Fed raises rates & more"


def test_clean_title_handles_none() -> None:
    assert clean_title(None) == ""


def test_normalize_url_strips_tracking_and_fragment() -> None:
    url = "HTTPS://Finance.Yahoo.com/news/story.html?utm_source=rss&id=42#top"
    assert normalize_url(url) == "https://finance.yahoo.com/news/story.html?id=42"


def test_normalize_url_empty() -> None:
    assert normalize_url(None) == ""


def test_struct_time_to_utc() -> None:
    st = time.struct_time((2026, 7, 5, 13, 30, 0, 0, 0, 0))
    dt = struct_time_to_utc(st)
    assert dt == datetime(2026, 7, 5, 13, 30, tzinfo=UTC)


def test_content_hash_is_stable_and_content_sensitive() -> None:
    a = compute_content_hash("Fed holds rates", "Powell speaks")
    b = compute_content_hash("Fed holds rates", "Powell speaks")
    c = compute_content_hash("Fed holds rates", "different summary")
    assert a == b
    assert a != c


def test_normalize_article_builds_model() -> None:
    article = normalize_article(
        source="Yahoo Finance",
        raw_title="  NVDA jumps 5%  ",
        raw_url="https://example.com/a?utm_medium=email",
        raw_summary="Nvidia rallied.",
        published_struct=time.struct_time((2026, 7, 5, 13, 0, 0, 0, 0, 0)),
        external_id="abc-123",
    )
    assert article is not None
    assert article.title == "NVDA jumps 5%"
    assert article.url == "https://example.com/a"
    assert article.source == "Yahoo Finance"
    assert article.external_id == "abc-123"
    assert article.published_at == datetime(2026, 7, 5, 13, 0, tzinfo=UTC)
    assert len(article.content_hash) == 64


def test_normalize_article_skips_when_title_or_url_missing() -> None:
    assert normalize_article(source="X", raw_title="", raw_url="https://a.com") is None
    assert normalize_article(source="X", raw_title="Title", raw_url="") is None
