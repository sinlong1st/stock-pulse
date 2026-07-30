"""Tests for the richer price snapshot + freshness labels."""

from datetime import UTC, datetime, timedelta

import httpx

from app.prices import (
    AlpacaPriceClient,
    PriceSnapshot,
    _parse_ts,
    price_freshness,
    price_snapshot_line,
)

NOW = datetime(2026, 7, 28, 20, 0, tzinfo=UTC)


def test_parse_ts_handles_z_and_nanoseconds() -> None:
    dt = _parse_ts("2026-07-28T19:59:59.912345678Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2026 and dt.minute == 59
    assert _parse_ts(None) is None
    assert _parse_ts("garbage") is None


def _snapshot_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "latestTrade": {"p": 65.2, "t": "2026-07-28T19:59:59.9Z"},
            "dailyBar": {"o": 64.1, "c": 65.0},
            "prevDailyBar": {"c": 63.5},
        },
    )


async def test_alpaca_snapshot_parses_open_price_and_time() -> None:
    client = AlpacaPriceClient(
        "k", "s", transport=httpx.MockTransport(lambda r: _snapshot_response())
    )
    snap = await client.snapshot("WDC")
    assert snap is not None
    assert snap.price == 65.2
    assert snap.open == 64.1
    assert snap.prev_close == 63.5
    assert snap.price_time is not None
    assert round(snap.change_from_open_pct, 1) == 1.7  # (65.2-64.1)/64.1


async def test_snapshot_none_when_no_trade() -> None:
    resp = httpx.Response(200, json={"dailyBar": {"o": 10.0}})
    client = AlpacaPriceClient("k", "s", transport=httpx.MockTransport(lambda r: resp))
    assert await client.snapshot("X") is None


def test_freshness_live_when_recent() -> None:
    recent = NOW - timedelta(minutes=5)
    assert price_freshness(recent, now=NOW) == "live"
    assert price_freshness(recent, now=NOW, language="Vietnamese") == "trực tiếp"


def test_freshness_shows_timestamp_when_stale() -> None:
    old = NOW - timedelta(hours=6)
    label = price_freshness(old, now=NOW, tz_name="America/Los_Angeles")
    assert "as of" in label
    assert ":" in label  # includes a time


def test_freshness_latest_when_no_time() -> None:
    assert price_freshness(None, now=NOW) == "latest"


def test_snapshot_line_shows_current_and_open() -> None:
    snap = PriceSnapshot(
        ticker="WDC", price=65.2, price_time=NOW - timedelta(minutes=2), open=64.1, prev_close=63.5
    )
    line = price_snapshot_line(snap, now=NOW, tz_name="America/Los_Angeles")
    assert "WDC: $65.20 (live)" in line
    assert "open $64.10 (+1.7%)" in line


def test_snapshot_line_vietnamese() -> None:
    snap = PriceSnapshot(ticker="MU", price=100.0, price_time=NOW, open=98.0, prev_close=99.0)
    line = price_snapshot_line(snap, now=NOW, language="Vietnamese")
    assert "mở cửa" in line


# --- Yahoo price source ----------------------------------------------------


def _yahoo_chart_response() -> httpx.Response:
    reg_start = 1_700_000_000
    return httpx.Response(
        200,
        json={
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 64.9,
                            "regularMarketTime": reg_start + 60,
                            "chartPreviousClose": 63.5,
                            "currentTradingPeriod": {"regular": {"start": reg_start}},
                        },
                        "timestamp": [reg_start, reg_start + 60],
                        "indicators": {
                            "quote": [{"open": [64.1, 64.5], "close": [64.3, 65.2]}]
                        },
                    }
                ]
            }
        },
    )


async def test_yahoo_snapshot_parses_current_open_prev() -> None:
    from app.prices import YahooPriceClient

    client = YahooPriceClient(transport=httpx.MockTransport(lambda r: _yahoo_chart_response()))
    snap = await client.snapshot("WDC")
    assert snap is not None
    assert snap.price == 65.2  # last traded bar (incl. post-market)
    assert snap.open == 64.1  # first regular-session open
    assert snap.prev_close == 63.5
    assert snap.price_time is not None


async def test_yahoo_snapshot_none_on_empty() -> None:
    from app.prices import YahooPriceClient

    resp = httpx.Response(200, json={"chart": {"result": []}})
    client = YahooPriceClient(transport=httpx.MockTransport(lambda r: resp))
    assert await client.snapshot("X") is None


def test_briefing_price_client_source_selection() -> None:
    from app.config import Settings
    from app.prices import AlpacaPriceClient, YahooPriceClient, maybe_briefing_price_client

    yahoo = maybe_briefing_price_client(Settings(_env_file=None, briefing_price_source="yahoo"))
    assert isinstance(yahoo, YahooPriceClient)  # no keys needed

    alpaca = maybe_briefing_price_client(
        Settings(
            _env_file=None,
            briefing_price_source="alpaca",
            price_features_enabled=True,
            alpaca_api_key="k",
            alpaca_secret_key="s",
        )
    )
    assert isinstance(alpaca, AlpacaPriceClient)

    off = maybe_briefing_price_client(
        Settings(_env_file=None, briefing_prices_in_report=False)
    )
    assert off is None
