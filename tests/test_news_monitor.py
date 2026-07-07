"""Tests for the end-to-end news monitor job (Phase 7).

Everything external is faked: collector, classifier, and notifier. The
database is a shared in-memory SQLite via an injected session factory.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.policy import AlertPolicy
from app.alerts.telegram import Notifier
from app.config import Settings
from app.db.database import Base
from app.db.repository import AlertRepository, ArticleRepository, ClassificationRepository
from app.jobs.news_monitor import analyze_relevant_articles, run_news_monitor
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.pipeline.classifier import Classifier


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _article(title: str, url: str) -> NewsArticle:
    return NewsArticle(
        source="Test",
        title=title,
        url=url,
        published_at=datetime(2026, 7, 5, 12, tzinfo=UTC),
        collected_at=datetime.now(tz=UTC),
        content_hash=f"hash-{url}",
    )


class _FakeCollector:
    source_name = "Test"

    def __init__(self, articles: list[NewsArticle]) -> None:
        self._articles = articles

    async def collect(self) -> list[NewsArticle]:
        return self._articles


class _FakeClassifier(Classifier):
    def __init__(self, importance: str = "HIGH") -> None:
        self.importance = importance
        self.calls = 0

    async def classify(self, article: NewsArticle) -> ClassificationResult:
        self.calls += 1
        return ClassificationResult(
            is_market_relevant=True,
            importance=self.importance,
            category="TICKER",
            related_tickers=["NVDA"],
            summary="s",
            why_it_matters="w",
            should_alert=True,
            confidence=0.9,
        )


class _FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def test_analyze_only_relevant_and_creates_alerts(session_factory) -> None:
    with session_factory() as session:
        repo = ArticleRepository(session)
        repo.add(_article("NVDA surges on strong demand", "https://e.com/nvda"))  # relevant
        repo.add(_article("Local bakery wins award", "https://e.com/bakery"))  # noise
        session.commit()

        summary = await analyze_relevant_articles(
            session,
            classifier=_FakeClassifier("HIGH"),
            policy=AlertPolicy(),
            model="fake",
            limit=10,
        )

    assert summary.classified == 1  # only the relevant one
    assert summary.alerts_created == 1
    with session_factory() as session:
        article_ids = [int(a.id) for a in ArticleRepository(session).list_recent() if a.id]
        classified = ClassificationRepository(session).classified_article_ids(article_ids)
        assert len(classified) == 1  # exactly the relevant article was classified
        assert AlertRepository(session).count_by_status("PENDING") == 1


async def test_run_news_monitor_full_pipeline(session_factory) -> None:
    settings = Settings(
        _env_file=None,
        max_classifications_per_run=5,
        max_alerts_per_run=20,
    )
    collector = _FakeCollector(
        [
            _article("NVDA jumps on AI demand", "https://e.com/1"),
            _article("Fed weighs a rate cut", "https://e.com/2"),
            _article("Cat video goes viral", "https://e.com/3"),  # noise
        ]
    )
    notifier = _FakeNotifier()

    summary = await run_news_monitor(
        session_factory=session_factory,
        settings=settings,
        collector=collector,
        classifier=_FakeClassifier("HIGH"),
        notifier=notifier,
    )

    assert summary.collected == 3
    assert summary.new == 3
    assert summary.relevant == 2  # NVDA + Fed
    assert summary.classified == 2
    assert summary.alerts_created == 2
    assert summary.alerts_sent == 2
    assert len(notifier.sent) == 2


async def test_run_news_monitor_skips_stages_without_credentials(session_factory) -> None:
    settings = Settings(_env_file=None)
    collector = _FakeCollector([_article("NVDA jumps", "https://e.com/1")])

    # Explicitly no classifier and no notifier.
    summary = await run_news_monitor(
        session_factory=session_factory,
        settings=settings,
        collector=collector,
        classifier=None,
        notifier=None,
    )

    assert summary.collected == 1
    assert summary.new == 1
    assert summary.relevant == 1
    assert summary.classified == 0  # classification skipped
    assert summary.alerts_sent == 0  # sending skipped
