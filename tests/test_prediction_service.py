"""Tests for the prediction assembler + /api/predict endpoint."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.config as config
import app.main as main
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
    monkeypatch.setattr(svc, "resolve_focus", lambda q: FocusTarget(q, ticker, name, name))
    monkeypatch.setattr(svc, "maybe_briefing_price_client", lambda s: None)

    async def fake_bars(t, **kw):
        return _bars([100, 120, 140, 130, 110])

    async def fake_news(**kw):
        return SimpleNamespace(all=[SimpleNamespace(title="Some headline")])

    monkeypatch.setattr(svc, "fetch_bars", fake_bars)
    monkeypatch.setattr(svc, "retrieve_fresh_news", fake_news)


async def test_build_prediction_assembles(monkeypatch) -> None:
    _wire(monkeypatch)
    out = await svc.build_prediction(Settings(_env_file=None), query="wdc", analyst=_FakeAnalyst())

    assert out["ok"] is True
    assert out["ticker"] == "WDC" and out["name"] == "Western Digital"
    assert out["discount"]["level"] in {"cheap", "fair", "rich"}
    assert out["trend"] in {"up", "down", "sideways"}
    assert out["horizons"][0]["lean"] == "bounce"
    assert out["strategy"] == {"id": "default", "name": "StockPulse Balanced"}
    assert out["price"] == "110.00"  # fell back to the last bar close


async def test_build_prediction_unknown_ticker(monkeypatch) -> None:
    monkeypatch.setattr(svc, "resolve_focus", lambda q: FocusTarget(q, None, None, q))

    async def none_symbol(q, *, settings):
        return None

    monkeypatch.setattr(svc, "resolve_symbol", none_symbol)
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
    async def fake_build(settings, *, query):
        return {"ok": True, "ticker": query.upper()}

    monkeypatch.setattr(main, "build_prediction", fake_build)
    with _client(monkeypatch) as client:
        h = {"Authorization": "Bearer s3cret"}
        assert client.get("/api/predict", headers=h).status_code == 400  # missing q
        ok = client.get("/api/predict?q=wdc", headers=h)
        assert ok.status_code == 200 and ok.json() == {"ok": True, "ticker": "WDC"}
    config.get_settings.cache_clear()
