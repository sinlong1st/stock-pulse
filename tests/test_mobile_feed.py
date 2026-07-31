"""Tests for the read-only mobile feed: build_feed shaping + /api/feed auth."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.watchlist as wl_api
import app.config as config
import app.main as main
from app.api.feed import build_feed
from app.config import Settings
from app.db.database import Base
from app.db.repository import ArticleRepository, ClassificationRepository
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.prices import PriceSnapshot
from app.watchlist import WatchlistConfig


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


# --- watchlist -------------------------------------------------------------


async def test_build_watchlist_prices_and_tolerates_misses(monkeypatch) -> None:
    from datetime import UTC, datetime

    cfg = WatchlistConfig(tickers=("NVDA", "MU"), aliases={"NVDA": ["Nvidia"], "MU": ["Micron"]})
    monkeypatch.setattr(wl_api, "get_watchlist_config", lambda: cfg)

    class FakeClient:
        async def snapshot(self, ticker):
            if ticker == "MU":
                return None  # simulate a fetch miss — should still appear, price null
            return PriceSnapshot(
                ticker=ticker,
                price=118.44,
                price_time=datetime.now(tz=UTC),
                open=123.60,
                prev_close=120.0,
            )

    monkeypatch.setattr(wl_api, "maybe_briefing_price_client", lambda settings: FakeClient())

    rows = await wl_api.build_watchlist(Settings(_env_file=None))
    by = {r["ticker"]: r for r in rows}
    assert by["NVDA"]["price"] == "118.44"
    assert by["NVDA"]["changePct"] == round((118.44 - 123.60) / 123.60 * 100, 1)
    assert by["NVDA"]["fresh"]  # a freshness label is present
    assert by["MU"]["price"] is None and by["MU"]["changePct"] is None
    assert by["MU"]["name"] == "Micron"


def test_watchlist_endpoint_200_with_token(monkeypatch) -> None:
    async def _fake(settings):
        return []

    monkeypatch.setattr(main, "build_watchlist", _fake)
    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        res = client.get("/api/watchlist", headers={"Authorization": "Bearer s3cret"})
        assert res.status_code == 200
        assert res.json()["watchlist"] == []
    config.get_settings.cache_clear()


# --- report ----------------------------------------------------------------


async def test_build_report_maps_themes(monkeypatch) -> None:
    from types import SimpleNamespace

    import app.api.report as report_api
    from app.briefing.models import BriefingResult, BriefingTheme

    result = BriefingResult(
        has_material_update=True,
        headline="Rates rule the tape",
        themes=[BriefingTheme(theme="AI & semis", direction="bearish", insight="chips wobble")],
    )

    async def fake_run_report(query=None, *, deliver=True, settings=None):
        return SimpleNamespace(result=result, skipped_reason=None)

    async def fake_wl(settings):
        return [{"ticker": "NVDA"}]

    monkeypatch.setattr(report_api, "run_report", fake_run_report)
    monkeypatch.setattr(report_api, "build_watchlist", fake_wl)

    out = await report_api.build_report(Settings(_env_file=None))
    assert out["takeaway"] == "Rates rule the tape"
    assert out["sections"] == [
        {"title": "AI & semis", "sentiment": "BEARISH", "body": "chips wobble"}
    ]
    assert out["watchlist"] == [{"ticker": "NVDA"}]
    assert out["note"] is None


async def test_build_report_handles_no_result(monkeypatch) -> None:
    from types import SimpleNamespace

    import app.api.report as report_api

    async def fake_run_report(query=None, *, deliver=True, settings=None):
        return SimpleNamespace(result=None, skipped_reason="no OpenAI key")

    async def fake_wl(settings):
        return []

    monkeypatch.setattr(report_api, "run_report", fake_run_report)
    monkeypatch.setattr(report_api, "build_watchlist", fake_wl)

    out = await report_api.build_report(Settings(_env_file=None))
    assert out["sections"] == []
    assert out["note"] == "no OpenAI key"
