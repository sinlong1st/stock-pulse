"""Server-sent progress for the slow AI endpoints."""

import asyncio
import json

import pytest

import app.config as config
import app.main as main
from app.api.stream import sse_with_progress


def _parse(chunks: list[str]) -> list[tuple[str, dict]]:
    """Turn raw SSE text into (event, data) pairs, ignoring keep-alive comments."""
    out: list[tuple[str, dict]] = []
    for block in "".join(chunks).split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name and data is not None:
            out.append((name, data))
    return out


# --- the generator ---------------------------------------------------------


async def test_stages_stream_then_the_result() -> None:
    async def run(progress):
        progress("news")
        await asyncio.sleep(0)
        progress("analyze")
        return {"ok": True, "value": 42}

    events = _parse([c async for c in sse_with_progress(run)])
    assert events == [
        ("stage", {"stage": "news"}),
        ("stage", {"stage": "analyze"}),
        ("result", {"ok": True, "value": 42}),
    ]


async def test_result_is_sent_even_with_no_stages() -> None:
    async def run(progress):
        return {"ok": True}

    assert _parse([c async for c in sse_with_progress(run)]) == [("result", {"ok": True})]


async def test_stages_emitted_after_the_last_read_are_not_lost() -> None:
    """A stage fired immediately before returning must still reach the client."""

    async def run(progress):
        progress("news")
        progress("prices")
        progress("analyze")
        return {"ok": True}

    events = _parse([c async for c in sse_with_progress(run)])
    assert [d["stage"] for n, d in events if n == "stage"] == ["news", "prices", "analyze"]
    assert events[-1][0] == "result"


async def test_a_crashing_pipeline_still_closes_with_a_result() -> None:
    """The client must never be left waiting on a stream that just stopped."""

    async def run(progress):
        progress("news")
        raise RuntimeError("boom")

    events = _parse([c async for c in sse_with_progress(run)])
    assert events[-1][0] == "result"
    assert events[-1][1]["ok"] is False


async def test_a_handled_failure_passes_through_unchanged() -> None:
    """build_prediction returns {ok: False, reason} rather than raising."""

    async def run(progress):
        return {"ok": False, "reason": "Couldn't find a stock for 'zzz'."}

    events = _parse([c async for c in sse_with_progress(run)])
    assert events[-1] == ("result", {"ok": False, "reason": "Couldn't find a stock for 'zzz'."})


# --- the endpoints ---------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("PREDICTION_ENABLED", "true")
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    config.get_settings.cache_clear()


AUTH = {"Authorization": "Bearer s3cret"}


def test_predict_stream_emits_real_stages(client, monkeypatch) -> None:
    async def fake_build(settings, *, query, session=None, progress=None):
        for stage in ("resolve", "prices", "news", "analyze"):
            progress(stage)
        return {"ok": True, "ticker": query.upper()}

    monkeypatch.setattr(main, "build_prediction", fake_build)
    res = client.get("/api/predict/stream?q=wdc", headers=AUTH)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = _parse([res.text])
    assert [d["stage"] for n, d in events if n == "stage"] == [
        "resolve",
        "prices",
        "news",
        "analyze",
    ]
    assert events[-1] == ("result", {"ok": True, "ticker": "WDC"})


def test_report_stream_emits_real_stages(client, monkeypatch) -> None:
    async def fake_build(settings, *, query=None, progress=None):
        for stage in ("news", "prices", "analyze", "compose"):
            progress(stage)
        return {"takeaway": "hi", "sections": [], "watchlist": []}

    monkeypatch.setattr(main, "build_mobile_report", fake_build)
    res = client.get("/api/report/stream", headers=AUTH)

    events = _parse([res.text])
    assert [d["stage"] for n, d in events if n == "stage"] == [
        "news",
        "prices",
        "analyze",
        "compose",
    ]
    assert events[-1][1]["takeaway"] == "hi"


def test_streams_require_the_token(client) -> None:
    assert client.get("/api/predict/stream?q=wdc").status_code == 401
    assert client.get("/api/report/stream").status_code == 401


def test_predict_stream_400_without_a_query(client) -> None:
    assert client.get("/api/predict/stream", headers=AUTH).status_code == 400


def test_predict_stream_404_when_prediction_is_off(monkeypatch) -> None:
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("PREDICTION_ENABLED", "false")
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        assert c.get("/api/predict/stream?q=wdc", headers=AUTH).status_code == 404
    config.get_settings.cache_clear()
