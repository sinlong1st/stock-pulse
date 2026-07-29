"""Tests for the timestamp/recap guard (Briefing plan, step C).

The "week-in-review" trap: an article freshly PUBLISHED today but summarizing
OLD events must not be treated as breaking news. Two layers are checked here —
the mechanical recap heuristic, and that the guard reaches the prompt.
"""

from datetime import UTC, datetime, timedelta

from app.briefing.analyst import build_system_prompt, build_user_message
from app.briefing.retrieval import assess_freshness, looks_like_recap
from app.models.article import NewsArticle

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)


def _article(title: str, *, published: datetime | None, summary: str = "") -> NewsArticle:
    return NewsArticle(
        source="Test",
        title=title,
        summary=summary or None,
        url=f"https://e.com/{title.replace(' ', '-')}",
        published_at=published,
        collected_at=NOW,
        content_hash=title,
    )


def test_looks_like_recap_detects_roundups() -> None:
    assert looks_like_recap("Markets Week in Review: what moved")
    assert looks_like_recap("Tech roundup", None)
    assert looks_like_recap("ICYMI: the biggest stories")
    assert looks_like_recap("Normal headline", "5 things to know before the open")
    assert not looks_like_recap("Nvidia beats earnings, guides higher")
    assert not looks_like_recap("Fed holds rates steady")


def test_recap_article_is_flagged_even_when_freshly_published() -> None:
    # Published 20 min ago (within window) but it's a weekly recap.
    item = assess_freshness(
        _article("This Week in AI: the recap", published=NOW - timedelta(minutes=20)),
        now=NOW,
        window_hours=2,
    )
    assert item.within_window  # timestamp is recent...
    assert item.likely_recap  # ...but flagged as a roundup


def test_fresh_breaking_item_is_not_flagged() -> None:
    item = assess_freshness(
        _article("Nvidia unveils new chip", published=NOW - timedelta(minutes=10)),
        now=NOW,
        window_hours=2,
    )
    assert not item.likely_recap


def _retrieval(*items):
    from app.briefing.retrieval import RetrievalResult

    fresh = [i for i in items if i.within_window]
    unverified = [i for i in items if not i.within_window and not i.timestamp_verified]
    return RetrievalResult(
        now=NOW, window_hours=2, fresh=fresh, unverified=unverified,
        collected=len(items), stale_dropped=0,
    )


def test_user_message_marks_recap_items() -> None:
    recap = assess_freshness(
        _article("Weekly recap: chips", published=NOW - timedelta(minutes=15)),
        now=NOW, window_hours=2,
    )
    msg = build_user_message(_retrieval(recap))
    assert "[likely RECAP/roundup]" in msg


def test_system_prompt_carries_temporal_guard() -> None:
    p = build_system_prompt(watchlist=["NVDA"], now=NOW, window_hours=2, language="English")
    assert "temporal_type" in p
    assert "recap_or_roundup" in p
    assert "event_time" in p
    assert "publish time is recent" in p
