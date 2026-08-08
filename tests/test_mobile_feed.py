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


async def test_build_feed_shapes_items(session) -> None:
    _classify(session, title="Nvidia slips")
    feed = await build_feed(session, Settings(_env_file=None), limit=10, price_client=None)
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


async def test_build_feed_skips_unclassified_and_irrelevant(session) -> None:
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
    feed = await build_feed(session, Settings(_env_file=None), limit=10, price_client=None)
    assert [i["summary"] for i in feed] == ["Relevant one summary"]


async def test_build_feed_maps_other_category_to_sector(session) -> None:
    _classify(session, title="Macro-ish", category="OTHER")
    feed = await build_feed(session, Settings(_env_file=None), limit=10, price_client=None)
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
    async def _fake_feed(session, settings, limit=30):
        return []

    monkeypatch.setattr(main, "build_feed", _fake_feed)
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


async def test_build_watchlist_derives_sentiment(session, monkeypatch) -> None:
    cfg = WatchlistConfig(tickers=("NVDA",), aliases={"NVDA": ["Nvidia"]})
    monkeypatch.setattr(wl_api, "get_watchlist_config", lambda: cfg)
    monkeypatch.setattr(wl_api, "maybe_briefing_price_client", lambda settings: None)
    _classify(session, title="Nvidia news", tickers=["NVDA"])  # helper sets sentiment BEARISH

    rows = await wl_api.build_watchlist(Settings(_env_file=None), session=session)
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["sentiment"] == "BEARISH"
    assert rows[0]["price"] is None  # no price client configured


def test_watchlist_endpoint_200_with_token(monkeypatch) -> None:
    async def _fake(settings, session=None):
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

    async def fake_run_report(query=None, *, deliver=True, settings=None, progress=None):
        return SimpleNamespace(result=result, skipped_reason=None)

    async def fake_wl(settings):
        return [{"ticker": "NVDA"}]

    async def no_earnings(tickers, **kw):
        return {}

    monkeypatch.setattr(report_api, "run_report", fake_run_report)
    monkeypatch.setattr(report_api, "build_watchlist", fake_wl)
    monkeypatch.setattr(report_api, "fetch_many", no_earnings)

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

    async def fake_run_report(query=None, *, deliver=True, settings=None, progress=None):
        return SimpleNamespace(result=None, skipped_reason="no OpenAI key")

    async def fake_wl(settings):
        return []

    async def no_earnings(tickers, **kw):
        return {}

    monkeypatch.setattr(report_api, "run_report", fake_run_report)
    monkeypatch.setattr(report_api, "build_watchlist", fake_wl)
    monkeypatch.setattr(report_api, "fetch_many", no_earnings)

    out = await report_api.build_report(Settings(_env_file=None))
    assert out["sections"] == []
    assert out["note"] == "no OpenAI key"


async def _report_with(monkeypatch, *, focus_ticker, symbol=None, wl_rows=None):
    """Wire build_report so only the resolution + price-scoping path is exercised."""
    from types import SimpleNamespace

    import app.api.report as report_api
    from app.briefing.focus import FocusTarget

    async def fake_run_report(query=None, *, deliver=True, settings=None, progress=None):
        return SimpleNamespace(result=None, skipped_reason=None)

    seen: dict = {}

    async def fake_wl(settings, *, tickers=None, session=None):
        seen["tickers"] = tickers
        rows = wl_rows if wl_rows is not None else [{"ticker": "NVDA", "name": "Nvidia"}]
        return rows if tickers is None else [r for r in rows if r["ticker"] in tickers]

    async def fake_symbol(q, *, settings):
        return symbol

    async def no_earnings(tickers, **kw):
        return {}

    monkeypatch.setattr(report_api, "run_report", fake_run_report)
    monkeypatch.setattr(report_api, "build_watchlist", fake_wl)
    monkeypatch.setattr(
        report_api, "resolve_focus", lambda q: FocusTarget(q, focus_ticker, None, q)
    )
    monkeypatch.setattr(report_api, "resolve_symbol_smart", fake_symbol)
    monkeypatch.setattr(report_api, "fetch_many", no_earnings)  # never touch Yahoo in tests
    return report_api, seen


async def test_single_stock_report_prices_only_that_stock(monkeypatch) -> None:
    report_api, seen = await _report_with(
        monkeypatch,
        focus_ticker="NVDA",
        wl_rows=[{"ticker": "NVDA", "name": "Nvidia"}, {"ticker": "MU", "name": "Micron"}],
    )
    out = await report_api.build_report(Settings(_env_file=None), query="nvda")
    assert seen["tickers"] == ["NVDA"]
    assert [r["ticker"] for r in out["watchlist"]] == ["NVDA"]  # not the whole watchlist


async def test_whole_watchlist_report_still_prices_everything(monkeypatch) -> None:
    report_api, seen = await _report_with(
        monkeypatch,
        focus_ticker="NVDA",
        wl_rows=[{"ticker": "NVDA", "name": "Nvidia"}, {"ticker": "MU", "name": "Micron"}],
    )
    out = await report_api.build_report(Settings(_env_file=None))
    assert seen["tickers"] is None
    assert [r["ticker"] for r in out["watchlist"]] == ["NVDA", "MU"]


async def test_single_stock_report_prices_off_watchlist_name(monkeypatch) -> None:
    # Not on the watchlist, so resolve_focus misses and the symbol search wins.
    report_api, _ = await _report_with(
        monkeypatch,
        focus_ticker=None,
        symbol=("TSLA", "Tesla"),
        wl_rows=[{"ticker": "TSLA", "name": "TSLA"}],
    )
    out = await report_api.build_report(Settings(_env_file=None), query="tesla")
    assert [r["ticker"] for r in out["watchlist"]] == ["TSLA"]
    assert out["watchlist"][0]["name"] == "Tesla"  # named from the resolved symbol


async def test_report_earnings_sorted_soonest_first(monkeypatch) -> None:
    from datetime import timedelta

    import app.api.report as report_api
    from app.earnings import Earnings, local_today

    today = local_today(Settings(_env_file=None))
    report_api_, _ = await _report_with(
        monkeypatch,
        focus_ticker="NVDA",
        wl_rows=[
            {"ticker": "NVDA", "name": "Nvidia"},
            {"ticker": "MU", "name": "Micron"},
            {"ticker": "WDC", "name": "Western Digital"},
        ],
    )

    async def some_earnings(tickers, **kw):
        return {
            "NVDA": Earnings("NVDA", next_date=today + timedelta(days=30)),
            "MU": Earnings("MU", next_date=today + timedelta(days=3)),
            # WDC has no date but a past result — still worth showing, sorted last.
            "WDC": Earnings("WDC", eps_actual=1.1, eps_estimate=1.0),
        }

    monkeypatch.setattr(report_api_, "fetch_many", some_earnings)
    out = await report_api_.build_report(Settings(_env_file=None))

    assert [r["ticker"] for r in out["earnings"]] == ["MU", "NVDA", "WDC"]
    assert out["earnings"][0]["daysUntil"] == 3
    assert out["earnings"][2]["verdict"] == "beat"


async def test_report_earnings_upcoming_outrank_already_reported(monkeypatch) -> None:
    """A stock that reported yesterday must not sit above one reporting tomorrow."""
    from datetime import timedelta

    import app.api.report as report_api
    from app.earnings import Earnings, local_today

    today = local_today(Settings(_env_file=None))
    report_api_, _ = await _report_with(
        monkeypatch,
        focus_ticker="NVDA",
        wl_rows=[{"ticker": t, "name": t} for t in ("SPCX", "NVDA", "MU")],
    )

    async def some_earnings(tickers, **kw):
        return {
            "SPCX": Earnings("SPCX", next_date=today - timedelta(days=1)),  # reported
            "NVDA": Earnings("NVDA", next_date=today + timedelta(days=1)),  # tomorrow
            "MU": Earnings("MU", next_date=today - timedelta(days=9)),  # older report
        }

    monkeypatch.setattr(report_api_, "fetch_many", some_earnings)
    out = await report_api_.build_report(Settings(_env_file=None))

    # upcoming first, then the most recent report, then the older one
    assert [r["ticker"] for r in out["earnings"]] == ["NVDA", "SPCX", "MU"]


async def test_report_earnings_absent_when_lookup_fails(monkeypatch) -> None:
    """A Yahoo outage hides the section; it must not break the report."""
    report_api_, _ = await _report_with(monkeypatch, focus_ticker="NVDA")
    out = await report_api_.build_report(Settings(_env_file=None))
    assert out["earnings"] == []
    assert "takeaway" in out  # the rest of the report is unaffected


async def test_single_stock_report_unresolvable_shows_no_prices(monkeypatch) -> None:
    report_api, _ = await _report_with(monkeypatch, focus_ticker=None, symbol=None)
    out = await report_api.build_report(Settings(_env_file=None), query="not a stock")
    assert out["watchlist"] == []  # better than showing an unrelated watchlist


# --- settings + watchlist mutation endpoints -------------------------------


def test_settings_get_and_set_language(monkeypatch) -> None:
    monkeypatch.setattr(main, "set_language", lambda name: None)
    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        h = {"Authorization": "Bearer s3cret"}
        got = client.get("/api/settings", headers=h)
        assert got.status_code == 200
        assert {"code": "en", "name": "English"} in got.json()["languages"]

        ok = client.post("/api/settings/language", json={"code": "vi"}, headers=h)
        assert ok.status_code == 200 and ok.json()["language"] == "Vietnamese"

        bad = client.post("/api/settings/language", json={"code": "fr"}, headers=h)
        assert bad.status_code == 400
    config.get_settings.cache_clear()


def test_evaluation_endpoint_maps_report(monkeypatch) -> None:
    import app.api.evaluation as eval_api
    from app.evaluation import EvaluationReport, RecentItem, SentimentStat

    def _s(label):
        return SentimentStat(
            label, total=2, hits=1, misses=1, flats=0, accuracy_pct=50.0, avg_return_pct=1.0
        )

    report = EvaluationReport(
        total_evaluated=4,
        hits=2,
        misses=2,
        flats=0,
        accuracy_pct=50.0,
        bullish=_s("Bullish"),
        bearish=_s("Bearish"),
        by_importance=[],
        recent=[RecentItem("NVDA", "BEARISH", "5d", -3.2, "HIT")],
        pending=3,
    )
    monkeypatch.setattr(eval_api, "build_evaluation_report", lambda session: report)
    # This test covers the response mapping, not the DB — stub the per-strategy
    # aggregation too so it doesn't reach for a real predictions table.
    monkeypatch.setattr(eval_api, "build_strategy_accuracy", lambda session, settings=None: [])
    monkeypatch.setattr(eval_api, "build_provider_accuracy", lambda session: [])
    monkeypatch.setattr(main, "build_evaluation", eval_api.build_evaluation)

    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        res = client.get("/api/evaluation", headers={"Authorization": "Bearer s3cret"})
        assert res.status_code == 200
        body = res.json()
        assert body["totalEvaluated"] == 4 and body["pending"] == 3
        assert body["bullish"]["accuracyPct"] == 50.0
        assert body["recent"][0] == {
            "ticker": "NVDA",
            "sentiment": "BEARISH",
            "horizon": "5d",
            "returnPct": -3.2,
            "outcome": "HIT",
        }
    config.get_settings.cache_clear()


def test_settings_channels_and_toggle(monkeypatch) -> None:
    monkeypatch.setattr(main, "set_flag", lambda k, v: None)
    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        h = {"Authorization": "Bearer s3cret"}
        got = client.get("/api/settings", headers=h).json()
        assert "telegram" in got["channels"] and "push" in got["channels"]
        assert got["briefing"]["editable"] is True  # the app can now edit the schedule

        ok = client.post(
            "/api/settings/channels", json={"channel": "push", "enabled": False}, headers=h
        )
        assert ok.status_code == 200 and ok.json() == {"channel": "push", "enabled": False}

        bad = client.post(
            "/api/settings/channels", json={"channel": "sms", "enabled": True}, headers=h
        )
        assert bad.status_code == 400
    config.get_settings.cache_clear()


def test_watch_add_and_remove_endpoints(monkeypatch) -> None:
    async def fake_resolve(query, *, settings, transport=None):
        return ("TSLA", "Tesla, Inc.") if query.lower() == "tesla" else None

    monkeypatch.setattr(main, "resolve_symbol", fake_resolve)
    monkeypatch.setattr(main, "add_ticker", lambda symbol, aliases=None: True)
    monkeypatch.setattr(main, "remove_ticker", lambda ticker: True)

    with _client_with(monkeypatch, enabled=True, token="s3cret") as client:
        h = {"Authorization": "Bearer s3cret"}
        added = client.post("/api/watchlist", json={"query": "tesla"}, headers=h)
        assert added.status_code == 200 and added.json() == {
            "added": True,
            "ticker": "TSLA",
            "name": "Tesla, Inc.",
            "reason": None,
        }

        miss = client.post("/api/watchlist", json={"query": "zzz"}, headers=h)
        assert miss.json()["added"] is False

        removed = client.request("DELETE", "/api/watchlist/tsla", headers=h)
        assert removed.status_code == 200 and removed.json()["removed"] is True
    config.get_settings.cache_clear()
