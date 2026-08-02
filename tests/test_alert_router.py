"""Tests for the alert delivery router (Phase 6)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.constants import CHANNEL_TELEGRAM, STATUS_FAILED, STATUS_SENT
from app.alerts.router import send_pending_alerts
from app.alerts.telegram import Notifier, NotifierError
from app.db.database import Base
from app.db.repository import AlertRepository, ArticleRepository, ClassificationRepository
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult


class _FakeNotifier(Notifier):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        if self.fail:
            raise NotifierError("boom")
        self.sent.append(text)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _seed_pending_alert(session) -> None:
    article = ArticleRepository(session).add(
        NewsArticle(
            source="Yahoo Finance",
            title="Fed holds rates",
            url="https://e.com/a",
            collected_at=datetime.now(tz=UTC),
            content_hash="h" * 64,
        )
    )
    session.flush()
    ClassificationRepository(session).add(
        article.id,
        ClassificationResult(
            is_market_relevant=True,
            importance="HIGH",
            category="MACRO",
            related_tickers=["QQQ"],
            summary="s",
            why_it_matters="w",
            should_alert=True,
            confidence=0.9,
        ),
    )
    AlertRepository(session).create(article.id, "HIGH", CHANNEL_TELEGRAM)
    session.commit()


async def test_sends_pending_and_marks_sent(session) -> None:
    _seed_pending_alert(session)
    notifier = _FakeNotifier()

    result = await send_pending_alerts(session, {CHANNEL_TELEGRAM: notifier})

    assert result.sent == 1
    assert result.failed == 0
    assert len(notifier.sent) == 1
    assert "Fed holds rates" in notifier.sent[0]
    assert AlertRepository(session).count_by_status(STATUS_SENT) == 1


async def test_failed_send_marks_failed_with_error(session) -> None:
    _seed_pending_alert(session)
    notifier = _FakeNotifier(fail=True)

    result = await send_pending_alerts(session, {CHANNEL_TELEGRAM: notifier})

    assert result.sent == 0
    assert result.failed == 1
    assert AlertRepository(session).count_by_status(STATUS_FAILED) == 1


async def test_unknown_channel_is_marked_failed(session) -> None:
    _seed_pending_alert(session)
    # No notifier registered for the telegram channel.
    result = await send_pending_alerts(session, {})
    assert result.failed == 1
    assert AlertRepository(session).count_by_status(STATUS_FAILED) == 1


async def test_push_fires_for_sent_alert(session, monkeypatch) -> None:
    import app.alerts.router as router

    calls: list[dict] = []

    async def fake_send_push(tokens, *, title, body, data=None, **kwargs):
        calls.append({"tokens": tokens, "title": title, "body": body, "data": data})
        return len(tokens)

    monkeypatch.setattr(router, "send_push", fake_send_push)

    _seed_pending_alert(session)
    result = await send_pending_alerts(
        session, {CHANNEL_TELEGRAM: _FakeNotifier()}, push_tokens=["ExponentPushToken[z]"]
    )

    assert result.sent == 1
    assert len(calls) == 1
    assert calls[0]["tokens"] == ["ExponentPushToken[z]"]
    assert "HIGH" in calls[0]["title"] and "QQQ" in calls[0]["title"]
    assert calls[0]["body"] == "s"
    assert calls[0]["data"]["type"] == "alert"


async def test_no_push_without_tokens(session, monkeypatch) -> None:
    import app.alerts.router as router

    called = False

    async def fake_send_push(*args, **kwargs):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(router, "send_push", fake_send_push)

    _seed_pending_alert(session)
    await send_pending_alerts(session, {CHANNEL_TELEGRAM: _FakeNotifier()})  # no push_tokens
    assert called is False


async def test_telegram_off_push_still_delivers(session, monkeypatch) -> None:
    """App-primary: Telegram disabled, push on → alert is still delivered."""
    import app.alerts.router as router

    calls: list = []

    async def fake_send_push(tokens, **kwargs):
        calls.append(tokens)
        return len(tokens)

    monkeypatch.setattr(router, "send_push", fake_send_push)
    tg = _FakeNotifier()

    _seed_pending_alert(session)
    result = await send_pending_alerts(
        session,
        {CHANNEL_TELEGRAM: tg},
        telegram_enabled=False,
        push_tokens=["ExponentPushToken[z]"],
    )

    assert result.sent == 1 and result.failed == 0
    assert tg.sent == []  # telegram was skipped
    assert calls == [["ExponentPushToken[z]"]]
    assert AlertRepository(session).count_by_status(STATUS_SENT) == 1


async def test_no_channel_enabled_marks_failed(session) -> None:
    _seed_pending_alert(session)
    result = await send_pending_alerts(session, {}, telegram_enabled=False)  # nothing on
    assert result.failed == 1
