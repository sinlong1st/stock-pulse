"""Tests for alert record storage (Phase 5)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.constants import CHANNEL_TELEGRAM, STATUS_PENDING, STATUS_SENT
from app.db.database import Base
from app.db.repository import AlertRepository, ArticleRepository
from app.models.article import NewsArticle


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _stored_article(session) -> int:
    row = ArticleRepository(session).add(
        NewsArticle(
            source="Test",
            title="Fed holds rates",
            url="https://e.com/a",
            collected_at=datetime.now(tz=UTC),
            content_hash="h" * 64,
        )
    )
    session.commit()
    return row.id


def test_create_and_exists(session) -> None:
    article_id = _stored_article(session)
    repo = AlertRepository(session)
    assert repo.exists(article_id, CHANNEL_TELEGRAM) is False

    repo.create(article_id, "HIGH", CHANNEL_TELEGRAM)
    session.commit()

    assert repo.exists(article_id, CHANNEL_TELEGRAM) is True
    assert repo.count_by_status(STATUS_PENDING) == 1


def test_pending_listing_and_mark_sent(session) -> None:
    article_id = _stored_article(session)
    repo = AlertRepository(session)
    alert = repo.create(article_id, "MEDIUM", CHANNEL_TELEGRAM)
    session.commit()

    pending = repo.list_by_status(STATUS_PENDING)
    assert len(pending) == 1

    repo.mark_sent(alert)
    session.commit()
    assert repo.count_by_status(STATUS_PENDING) == 0
    assert repo.count_by_status(STATUS_SENT) == 1
    assert alert.sent_at is not None
