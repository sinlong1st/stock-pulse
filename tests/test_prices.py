"""Tests for the Alpaca price client (Eval plan, step B).

The Alpaca API is never called for real: a httpx MockTransport returns
canned snapshot responses.
"""

import httpx
import pytest

from app.prices import AlpacaPriceClient, PriceError, PriceMove, price_context_line


def _client(handler) -> AlpacaPriceClient:
    return AlpacaPriceClient("key", "secret", transport=httpx.MockTransport(handler))


def _snapshot(latest: float | None, prev_close: float | None) -> dict:
    snap: dict = {}
    if latest is not None:
        snap["latestTrade"] = {"p": latest}
    if prev_close is not None:
        snap["prevDailyBar"] = {"c": prev_close}
    return snap


async def test_change_today_computes_percent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stocks/MU/snapshot")
        assert request.headers["APCA-API-KEY-ID"] == "key"
        return httpx.Response(200, json=_snapshot(103.4, 100.0))

    move = await _client(handler).change_today("MU")
    assert move is not None
    assert move.ticker == "MU"
    assert round(move.change_pct, 1) == 3.4


async def test_latest_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_snapshot(150.0, 148.0))

    assert await _client(handler).latest_price("NVDA") == 150.0


async def test_missing_data_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_snapshot(None, None))  # e.g. private ticker

    assert await _client(handler).change_today("SPCX") is None


async def test_http_error_returns_none_not_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await _client(handler).change_today("NOPE") is None


def test_missing_keys_raises() -> None:
    with pytest.raises(PriceError):
        AlpacaPriceClient("", "")


def test_price_context_line_formatting() -> None:
    up = price_context_line(PriceMove("MU", 103.4, 100.0, 3.4))
    down = price_context_line(PriceMove("NVDA", 98.2, 100.0, -1.8), language="Vietnamese")
    assert up == "📈 MU +3.4% today"
    assert down == "📉 NVDA -1.8% hôm nay"
