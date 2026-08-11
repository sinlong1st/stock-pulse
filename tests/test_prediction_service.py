"""Tests for the prediction assembler + /api/predict endpoint."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.config as config
import app.main as main
import app.prediction.evidence as ev
import app.prediction.service as svc
from app.briefing.focus import FocusTarget
from app.config import Settings
from app.prediction.models import HorizonRead, PredictionRead
from app.prices import Bar


def _bars(closes):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(t=t0 + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1)
        for i, c in enumerate(closes)
    ]


class _FakeAnalyst:
    async def analyze(self, **kw):
        self.seen = kw
        return PredictionRead(
            horizons=[HorizonRead(horizon="1w", lean="bounce", confidence="low", rationale="a")],
            drivers=["d1"],
        )


def _wire(monkeypatch, *, ticker="WDC", name="Western Digital"):
    """Stub the outside world. The fetches live in `app.prediction.evidence`,
    the shared research step — patching `service` would miss them and let the
    tests reach the real Yahoo and news feeds."""
    monkeypatch.setattr(ev, "resolve_focus", lambda q: FocusTarget(q, ticker, name, name))
    monkeypatch.setattr(ev, "maybe_briefing_price_client", lambda s: None)

    async def fake_bars(t, **kw):
        return _bars([100, 120, 140, 130, 110])

    async def fake_news(**kw):
        return SimpleNamespace(all=[SimpleNamespace(title="Some headline")])

    async def no_earnings(tickers, **kw):
        return {}

    monkeypatch.setattr(ev, "fetch_bars", fake_bars)
    monkeypatch.setattr(ev, "retrieve_fresh_news", fake_news)
    monkeypatch.setattr(ev, "fetch_many", no_earnings)  # never touch Yahoo in tests


async def test_build_prediction_assembles(monkeypatch) -> None:
    _wire(monkeypatch)
    out = await svc.build_prediction(Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst())

    assert out["ok"] is True
    assert out["ticker"] == "WDC" and out["name"] == "Western Digital"
    assert out["discount"]["level"] in {"cheap", "fair", "rich"}
    assert out["trend"] in {"up", "down", "sideways"}
    assert out["horizons"][0]["lean"] == "bounce"
    assert out["strategy"]["id"] == "default" and out["strategy"]["body"]  # incl. body for the modal
    assert out["price"] == "110.00"  # fell back to the last bar close
    assert out["series"]["closes"] == [100, 120, 140, 130, 110]  # for the app's charts
    assert len(out["series"]["volumes"]) == 5 and len(out["series"]["dates"]) == 5
    # lows = close*0.99 → the only floor under the 110 price is 99.0, and with just
    # 5 bars there is nothing deeper, so long-term is empty rather than echoing it.
    assert out["support"] == {
        "near": 99.0,
        "long": None,
        "nearLevels": [99.0],
        "longLevels": [],
    }
    # default from the fake analyst
    assert out["entry"] == {"assessment": "fair", "note": "", "risks": []}
    assert out["language"] == "English"


async def test_long_term_support_sits_below_near_term(monkeypatch) -> None:
    """Regression: the full window contains the recent one, so ranking both by
    'closest to price' put the long-term floor NEARER than the near-term one."""
    # Deep troughs early (structural), shallower ones in the last month (recent).
    closes = (
        [100, 110, 60, 100, 115, 65, 105, 118, 70, 108]  # older: deep floors
        + [112] * 90
        + [120, 130, 95, 118, 128, 100, 122, 126, 105, 124]  # recent: shallow
        + [130] * 11
    )
    _wire(monkeypatch)

    async def fake_bars(t, **kw):
        return _bars(closes)

    monkeypatch.setattr(ev, "fetch_bars", fake_bars)
    out = await svc.build_prediction(Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst())

    near, long = out["support"]["nearLevels"], out["support"]["longLevels"]
    assert near and long, "both horizons should be populated on a 130-bar series"
    assert max(long) < min(near), f"long-term {long} must sit under near-term {near}"
    assert near == sorted(near, reverse=True)  # closest first
    assert long == sorted(long, reverse=True)


async def test_strategy_is_shown_in_vietnamese_but_prompted_in_english(monkeypatch) -> None:
    """The modal must follow the UI language, while the model keeps the English
    prompt — mixing prompt languages degrades the output."""
    _wire(monkeypatch)
    analyst = _FakeAnalyst()
    out = await svc.build_prediction(
        Settings(_env_file=None), query="wdc", analyst=analyst, language="Vietnamese"
    )

    assert out["strategy"]["id"] == "default"  # enum-ish id never translates
    assert out["strategy"]["name"] == "StockPulse Cân bằng"
    assert "Cân nhắc ba yếu tố" in out["strategy"]["body"]
    # what the model actually received is still English
    assert analyst.seen["strategy"].body.startswith("Weigh three things")


async def test_strategy_display_defaults_to_english(monkeypatch) -> None:
    _wire(monkeypatch)
    out = await svc.build_prediction(Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst())
    assert out["strategy"]["name"] == "StockPulse Balanced"
    assert out["strategy"]["body"].startswith("Weigh three things")


def test_custom_strategy_without_translation_falls_back() -> None:
    """A user-written strategy has no vi text — show it as they wrote it."""
    from app.prediction.strategies import Strategy

    mine = Strategy(id="mine", name="My value lens", body="Buy fear.", builtin=False)
    assert mine.display(vi=True) == ("My value lens", "Buy fear.")


async def test_build_prediction_records_the_read_when_given_a_session(monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base
    from app.db.models import PredictionRow
    from app.status import PRED_SOURCE_PREDICT

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _wire(monkeypatch)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        out = await svc.build_prediction(
            Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst(), session=session
        )
        rows = session.query(PredictionRow).all()

    assert out["ok"] is True
    assert len(rows) == 1  # the fake analyst returns a single 1w horizon
    assert rows[0].source == PRED_SOURCE_PREDICT
    assert rows[0].strategy_id == "default"
    assert rows[0].ticker == "WDC"
    assert rows[0].baseline_price == 110.0  # the raw price, not the display string


async def test_recording_failure_never_costs_the_user_the_prediction(monkeypatch) -> None:
    """Bookkeeping is best-effort — a broken session must not fail the request."""
    _wire(monkeypatch)

    class _BrokenSession:
        def commit(self):
            raise RuntimeError("db is on fire")

        def rollback(self):
            pass

    def boom(*a, **kw):
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(svc, "record_prediction_read", boom)
    out = await svc.build_prediction(
        Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst(), session=_BrokenSession()
    )
    assert out["ok"] is True and out["ticker"] == "WDC"


async def test_recording_can_be_switched_off(monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base
    from app.db.models import PredictionRow

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _wire(monkeypatch)

    settings = Settings(_env_file=None, prediction_recording_enabled=False)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        await svc.build_prediction(
            settings, query="wdc", analyst=_FakeAnalyst(), session=session
        )
        assert session.query(PredictionRow).count() == 0


async def test_active_custom_strategy_drives_and_tags_the_prediction(monkeypatch, tmp_path) -> None:
    """The whole point of the feature: the user's lens reaches the model, and
    the resulting call is tagged with it so accuracy can be compared later."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.prediction.store as store
    import app.prefs as prefs
    from app.db.database import Base
    from app.db.models import PredictionRow

    store._load.cache_clear()
    prefs._load.cache_clear()
    settings = Settings(
        _env_file=None,
        strategies_file=str(tmp_path / "strategies.json"),
        prefs_file=str(tmp_path / "prefs.json"),
    )
    mine = store.create_strategy(
        "Deep value",
        "Favour quality names far off their high when the bad news looks temporary.",
        settings=settings,
    )
    store.set_active_strategy(mine.id, settings=settings)

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _wire(monkeypatch)
    analyst = _FakeAnalyst()

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        out = await svc.build_prediction(settings, query="wdc", analyst=analyst, session=session)
        rows = session.query(PredictionRow).all()

    assert analyst.seen["strategy"].id == mine.id  # the model saw the user's lens
    assert "Favour quality names" in analyst.seen["strategy"].body
    assert out["strategy"]["id"] == mine.id
    assert out["strategy"]["name"] == "Deep value"
    assert [r.strategy_id for r in rows] == [mine.id]  # recorded against it

    store._load.cache_clear()
    prefs._load.cache_clear()


async def test_build_prediction_unknown_ticker(monkeypatch) -> None:
    monkeypatch.setattr(ev, "resolve_focus", lambda q: FocusTarget(q, None, None, q))

    async def none_symbol(q, *, settings):
        return None

    monkeypatch.setattr(ev, "resolve_symbol_smart", none_symbol)
    out = await svc.build_prediction(Settings(_env_file=None), query="zzzz", analyst=_FakeAnalyst())
    assert out["ok"] is False and "Couldn't find" in out["reason"]


# --- endpoint --------------------------------------------------------------


def _client(monkeypatch, *, prediction=True):
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("PREDICTION_ENABLED", "true" if prediction else "false")
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def test_predict_endpoint_404_when_disabled(monkeypatch) -> None:
    with _client(monkeypatch, prediction=False) as client:
        res = client.get("/api/predict?q=wdc", headers={"Authorization": "Bearer s3cret"})
        assert res.status_code == 404
    config.get_settings.cache_clear()


def test_predict_endpoint_200(monkeypatch) -> None:
    async def fake_build(settings, *, query, session=None, mode=None):
        return {"ok": True, "ticker": query.upper(), "mode": mode}

    monkeypatch.setattr(main, "build_prediction", fake_build)
    with _client(monkeypatch) as client:
        h = {"Authorization": "Bearer s3cret"}
        assert client.get("/api/predict", headers=h).status_code == 400  # missing q
        ok = client.get("/api/predict?q=wdc", headers=h)
        assert ok.status_code == 200
        assert ok.json() == {"ok": True, "ticker": "WDC", "mode": None}
        # ?mode= overrides the saved choice for this call only.
        picked = client.get("/api/predict?q=wdc&mode=deepseek", headers=h)
        assert picked.json()["mode"] == "deepseek"
    config.get_settings.cache_clear()


def test_mode_endpoint_reports_and_saves(monkeypatch, tmp_path) -> None:
    """The picker only offers modes that a configured key can actually deliver."""
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds")
    monkeypatch.setenv("PREFS_FILE", str(tmp_path / "prefs.json"))
    with _client(monkeypatch) as client:
        h = {"Authorization": "Bearer s3cret"}
        got = client.get("/api/predict/mode", headers=h).json()
        assert got["mode"] == "both"
        assert set(got["available"]) == {"openai", "deepseek", "both"}

        saved = client.put("/api/predict/mode", json={"mode": "deepseek"}, headers=h)
        assert saved.status_code == 200 and saved.json()["mode"] == "deepseek"
        assert client.get("/api/predict/mode", headers=h).json()["mode"] == "deepseek"

        bad = client.put("/api/predict/mode", json={"mode": "claude"}, headers=h)
        assert bad.status_code == 400
    config.get_settings.cache_clear()


def test_mode_endpoint_hides_options_without_a_key(monkeypatch, tmp_path) -> None:
    # Only OpenAI configured: offering "deepseek" or "both" would be offering a
    # choice that silently does something else.
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("PREFS_FILE", str(tmp_path / "prefs.json"))
    with _client(monkeypatch) as client:
        got = client.get("/api/predict/mode", headers={"Authorization": "Bearer s3cret"}).json()
        assert got["available"] == ["openai"]
        assert got["providers"] == ["openai"]
    config.get_settings.cache_clear()
