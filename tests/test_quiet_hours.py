"""Tests for quiet hours (Eval plan, step A)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.constants import CHANNEL_TELEGRAM, STATUS_PENDING, STATUS_SENT
from app.alerts.quiet_hours import is_quiet_now, should_hold
from app.alerts.router import send_pending_alerts
from app.alerts.telegram import Notifier
from app.config import Settings
from app.db.database import Base
from app.db.repository import AlertRepository, ArticleRepository, ClassificationRepository
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult

TZ = "Asia/Ho_Chi_Minh"


def _settings(**kw) -> Settings:
    base = dict(
        _env_file=None,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        quiet_hours_timezone=TZ,
        quiet_hours_min_importance="CRITICAL",
    )
    base.update(kw)
    return Settings(**base)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 8, hour, minute, tzinfo=ZoneInfo(TZ))


def test_inside_window_crossing_midnight() -> None:
    s = _settings()
    assert is_quiet_now(s, _at(23, 0)) is True  # late night
    assert is_quiet_now(s, _at(3, 0)) is True  # early morning
    assert is_quiet_now(s, _at(6, 59)) is True
    assert is_quiet_now(s, _at(7, 0)) is False  # window end exclusive
    assert is_quiet_now(s, _at(12, 0)) is False  # midday


def test_disabled_is_never_quiet() -> None:
    s = _settings(quiet_hours_enabled=False)
    assert is_quiet_now(s, _at(3, 0)) is False


def test_should_hold_respects_min_importance() -> None:
    s = _settings()  # CRITICAL always sends
    assert should_hold("MEDIUM", s, _at(3, 0)) is True
    assert should_hold("HIGH", s, _at(3, 0)) is True
    assert should_hold("CRITICAL", s, _at(3, 0)) is False  # bypasses
    assert should_hold("MEDIUM", s, _at(12, 0)) is False  # not quiet


def test_same_day_window() -> None:
    s = _settings(quiet_hours_start="13:00", quiet_hours_end="14:00")
    assert is_quiet_now(s, _at(13, 30)) is True
    assert is_quiet_now(s, _at(14, 1)) is False


# --- router integration -----------------------------------------------------


class _FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _seed_alert(session, importance: str) -> None:
    article = ArticleRepository(session).add(
        NewsArticle(
            source="Test",
            title="t",
            url=f"https://e.com/{importance}",
            collected_at=datetime.now(tz=UTC),
            content_hash=f"h-{importance}",
        )
    )
    session.flush()
    ClassificationRepository(session).add(
        article.id,
        ClassificationResult(
            is_market_relevant=True,
            importance=importance,
            category="MACRO",
            sentiment="BEARISH",
            related_tickers=[],
            summary="s",
            why_it_matters="w",
            should_alert=True,
        ),
    )
    AlertRepository(session).create(article.id, importance, CHANNEL_TELEGRAM)
    session.commit()


async def test_quiet_hours_holds_medium_but_sends_critical(session) -> None:
    _seed_alert(session, "MEDIUM")
    _seed_alert(session, "CRITICAL")
    notifier = _FakeNotifier()

    result = await send_pending_alerts(
        session,
        {CHANNEL_TELEGRAM: notifier},
        quiet_now=True,
        quiet_min_importance="CRITICAL",
    )

    assert result.sent == 1  # only CRITICAL went out
    assert result.held == 1  # MEDIUM held
    assert len(notifier.sent) == 1
    # The held MEDIUM alert is still PENDING for later.
    assert AlertRepository(session).count_by_status(STATUS_PENDING) == 1
    assert AlertRepository(session).count_by_status(STATUS_SENT) == 1
