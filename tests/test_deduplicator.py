"""Persistence + deduplication tests (Phase 2).

Uses a real in-memory SQLite database so the dedup logic is exercised
end-to-end against SQLAlchemy, without touching the network or a file.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.repository import ArticleRepository
from app.models.article import NewsArticle
from app.pipeline.deduplicator import partition_new_articles, store_new_articles


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s
    Base.metadata.drop_all(engine)


def _article(
    title: str = "NVDA jumps",
    url: str = "https://example.com/nvda",
    summary: str = "Nvidia rallies.",
    external_id: str | None = "guid-1",
    content_hash: str | None = None,
) -> NewsArticle:
    return NewsArticle(
        source="Yahoo Finance",
        external_id=external_id,
        title=title,
        summary=summary,
        url=url,
        published_at=datetime(2026, 7, 5, 13, tzinfo=UTC),
        collected_at=datetime.now(tz=UTC),
        content_hash=content_hash or f"hash-{title}-{url}",
    )


def test_store_persists_new_articles(session) -> None:
    result = store_new_articles(session, [_article("A", "https://e.com/a"), _article("B", "https://e.com/b")])
    assert result.new == 2
    assert result.duplicates == 0
    assert result.stored_total == 2


def test_running_collector_twice_creates_no_duplicates(session) -> None:
    batch = [_article("A", "https://e.com/a"), _article("B", "https://e.com/b")]

    first = store_new_articles(session, batch)
    assert first.new == 2

    # Same batch again — everything is a duplicate now.
    second = store_new_articles(session, batch)
    assert second.new == 0
    assert second.duplicates == 2
    assert second.stored_total == 2  # still only two rows


def test_duplicate_detected_by_url_even_if_hash_differs(session) -> None:
    store_new_articles(session, [_article(url="https://e.com/x", content_hash="hash-1")])
    repo = ArticleRepository(session)
    same_url = _article(url="https://e.com/x", content_hash="different-hash")
    assert repo.exists(same_url) is True


def test_duplicate_detected_by_content_hash_even_if_url_differs(session) -> None:
    store_new_articles(session, [_article(url="https://e.com/1", content_hash="shared-hash")])
    repo = ArticleRepository(session)
    same_content = _article(url="https://e.com/2", content_hash="shared-hash")
    assert repo.exists(same_content) is True


def test_within_batch_duplicates_collapsed(session) -> None:
    repo = ArticleRepository(session)
    dup = _article(url="https://e.com/same", content_hash="h")
    new = partition_new_articles(repo, [dup, dup, dup])
    assert len(new) == 1


def test_list_recent_sorts_newest_published_first(session) -> None:
    older = _article("Older", "https://e.com/old")
    older.published_at = datetime(2026, 7, 1, 12, tzinfo=UTC)
    newer = _article("Newer", "https://e.com/new")
    newer.published_at = datetime(2026, 7, 5, 12, tzinfo=UTC)
    no_date = _article("NoDate", "https://e.com/none")
    no_date.published_at = None

    # Insert out of order.
    store_new_articles(session, [older, no_date, newer])
    titles = [a.title for a in ArticleRepository(session).list_recent()]
    assert titles[0] == "Newer"
    assert titles[1] == "Older"
    assert titles[-1] == "NoDate"  # undated sorts last


def test_list_recent_returns_timezone_aware_datetimes(session) -> None:
    store_new_articles(session, [_article("A", "https://e.com/a")])
    (stored,) = ArticleRepository(session).list_recent()
    assert stored.published_at is not None
    assert stored.published_at.tzinfo is not None
    assert stored.collected_at.tzinfo is not None


def test_distinct_articles_all_kept(session) -> None:
    repo = ArticleRepository(session)
    articles = [
        _article("A", "https://e.com/a", external_id="1", content_hash="ha"),
        _article("B", "https://e.com/b", external_id="2", content_hash="hb"),
    ]
    new = partition_new_articles(repo, articles)
    assert len(new) == 2
