"""Tests for briefing retrieval + freshness windowing (Briefing plan, step A)."""

from datetime import UTC, datetime, timedelta

from app.briefing.retrieval import assess_freshness, retrieve_fresh_news
from app.collectors.base import NewsCollector
from app.models.article import NewsArticle

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)


def _article(title: str, *, published: datetime | None, url: str | None = None) -> NewsArticle:
    return NewsArticle(
        source="Test",
        title=title,
        url=url or f"https://e.com/{title.replace(' ', '-')}",
        published_at=published,
        collected_at=NOW,
        content_hash=title,
    )


class _FakeCollector(NewsCollector):
    def __init__(self, articles: list[NewsArticle], name: str = "Fake") -> None:
        self.source_name = name
        self._articles = articles

    async def collect(self) -> list[NewsArticle]:
        return list(self._articles)


def test_assess_freshness_within_and_outside_window() -> None:
    fresh = assess_freshness(
        _article("fresh", published=NOW - timedelta(hours=1)), now=NOW, window_hours=2
    )
    assert fresh.within_window and fresh.timestamp_verified
    assert 0.9 < (fresh.age_hours or 0) < 1.1

    old = assess_freshness(
        _article("old", published=NOW - timedelta(hours=5)), now=NOW, window_hours=2
    )
    assert not old.within_window and old.timestamp_verified


def test_assess_freshness_missing_timestamp_is_unverified() -> None:
    item = assess_freshness(_article("no-date", published=None), now=NOW, window_hours=2)
    assert not item.timestamp_verified
    assert not item.within_window
    assert item.age_hours is None


def test_clock_skew_slightly_future_counts_as_fresh() -> None:
    # Feed clock a few minutes ahead of ours shouldn't drop the item.
    item = assess_freshness(
        _article("just-out", published=NOW + timedelta(minutes=3)), now=NOW, window_hours=2
    )
    assert item.within_window


async def test_retrieve_splits_fresh_unverified_and_drops_stale() -> None:
    collector = _FakeCollector(
        [
            _article("A recent", published=NOW - timedelta(minutes=30)),
            _article("B recent", published=NOW - timedelta(hours=1, minutes=30)),
            _article("C stale", published=NOW - timedelta(hours=10)),
            _article("D no-date", published=None),
        ]
    )

    result = await retrieve_fresh_news(window_hours=2, now=NOW, collectors=[collector])

    assert result.collected == 4
    assert [i.title for i in result.fresh] == ["A recent", "B recent"]  # freshest first
    assert [i.title for i in result.unverified] == ["D no-date"]
    assert result.stale_dropped == 1
    # usable = fresh + unverified, stale excluded.
    assert [i.title for i in result.usable] == ["A recent", "B recent", "D no-date"]


async def test_retrieve_dedupes_across_collectors_by_url() -> None:
    dup = _article("Shared", published=NOW - timedelta(minutes=10), url="https://e.com/x")
    c1 = _FakeCollector([dup], name="One")
    c2 = _FakeCollector([_article("Shared", published=NOW - timedelta(minutes=10), url="https://e.com/x")], name="Two")

    result = await retrieve_fresh_news(window_hours=2, now=NOW, collectors=[c1, c2])
    assert result.collected == 1
    assert len(result.fresh) == 1


async def test_retrieve_empty_when_no_collectors() -> None:
    result = await retrieve_fresh_news(window_hours=2, now=NOW, collectors=[])
    assert not result.has_any
    assert result.collected == 0
