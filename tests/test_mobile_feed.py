"""Tests for the read-only mobile feed: build_feed shaping + /api/feed auth."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
import app.main as main
from app.api.feed import build_feed
from app.db.database import Base
from app.db.repository import ArticleRepository, ClassificationRepository
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _classify(session, *, title, category="TICKER", relevant=True, tickers=None):
    art = ArticleRepository(session).add(
        NewsArticle(
            source="Reuters",
            title=title,
            url=f"https://e.com/{title}",
            published_at=datetime.now(tz=UTC),
            collected_at=datetime.now(tz=UTC),
            content_hash=(title * 20)[:64].ljust(64, "x"),
        )
    )
    session.flush()
    ClassificationRepository(session).add(
        art.id,
        ClassificationResult(
            is_market_relevant=relevant,
            importance="HIGH",
            category=category,
            sentiment="BEARISH",
            related_tickers=tickers if tickers is not None else ["NVDA"],
            summary=f"{title} summary",
            why_it_matters="because reasons",
            should_alert=True,
        ),
    )
    session.commit()
    return art.id


# --- build_feed ------------------------------------------------------------


def test_build_feed_shapes_items(session) -> None:
    _classify(session, title="Nvidia slips")
    feed = build_feed(session, limit=10)
    assert len(feed) == 1
    item = feed[0]
    assert item["summary"] == "Nvidia slips summary"
    assert item["why"] == "because reasons"
    assert item["sentiment"] == "BEARISH"
    assert item["tickers"] == ["NVDA"]
    assert item["importance"] == "HIGH"
    assert item["category"] == "TICKER"
    assert item["price"] is None
    assert item["source"] == "Reuters"


def test_build_feed_skips_unclassified_and_irrelevant(session) -> None:
    _classify(session, title="Relevant one")
    _classify(session, title="Noise", relevant=False)
    ArticleRepository(session).add(
        NewsArticle(
            source="X",
            title="Bare",
            url="https://e.com/bare",
            collected_at=datetime.now(tz=UTC),
            content_hash="b" * 64,
        )
    )
    session.commit()
    feed = build_feed(session, limit=10)
    assert [i["summary"] for i in feed] == ["Relevant one summary"]


def test_build_feed_maps_other_category_to_sector(session) -> None:
    _classify(session, title="Macro-ish", category="OTHER")
    feed = build_feed(session, limit=10)
    assert feed[0]["category"] == "SECTOR"


# --- /api/feed auth gate ---------------------------------------------------


def _client_with(monkeypatch, *, enabled: bool, token: str) -> TestClient:
    monkeypatch.setenv("MOBILE_API_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MOBILE_API_TOKEN", token)
    config.get_settings.cache_clear()
    return TestClient(main.app)


def test_feed_endpoint_404_when_disabled(monkeypatch) -> None:
    with _client_with(monkeypatch, enabled=False, token="s3cret") as client:
        assert client.get("/api/feed").status_code == 404
    config.get_settings.cache_clear()


def test_feed_endpoint_401_without_token(monkeypatch) -> None:
    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        assert client.get("/api/feed").status_code == 401
        wrong = client.get("/api/feed", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401
    config.get_settings.cache_clear()


def test_feed_endpoint_200_with_token(monkeypatch) -> None:
    monkeypatch.setattr(main, "build_feed", lambda session, limit=30: [])
    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        res = client.get("/api/feed", headers={"Authorization": "Bearer s3cret"})
        assert res.status_code == 200
        assert res.json()["alerts"] == []
    config.get_settings.cache_clear()
