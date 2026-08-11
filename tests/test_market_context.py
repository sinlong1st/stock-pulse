"""Broad market context (spec §17, exit-advisor plan Phase 2).

The contract these tests defend:

1. Relative strength is only reported when the two series are **comparable**.
2. Every field degrades to `None` on its own — a market read is context, and
   losing it must never cost the caller their analysis.
3. The index bars are **cached**, because they are identical for every ticker,
   but a failure is never cached.
"""

from datetime import UTC, datetime, timedelta

import pytest

import app.prediction.market as market
from app.prediction.market import (
    EMPTY,
    MarketContext,
    clear_cache,
    fetch_market_context,
    pct_change,
)
from app.prices import Bar


def _bars(closes, *, end=datetime(2026, 8, 10, tzinfo=UTC)):
    """Daily bars ending on `end`, one per day backwards."""
    start = end - timedelta(days=len(closes) - 1)
    return [
        Bar(t=start + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1)
        for i, c in enumerate(closes)
    ]


@pytest.fixture(autouse=True)
def _no_cache_between_tests():
    clear_cache()
    yield
    clear_cache()


def _wire(monkeypatch, *, spy=None, vix=None, calls=None):
    """Stub the two index fetches. `calls` collects symbols for cache tests."""
    spy = spy if spy is not None else _bars([100.0] * 20 + [110.0])
    vix = vix if vix is not None else _bars([16.0] * 21)

    async def fake_fetch(symbol, **kw):
        if calls is not None:
            calls.append(symbol)
        return {market.MARKET_PROXY: spy, market.VIX_SYMBOL: vix}.get(symbol, [])

    monkeypatch.setattr(market, "fetch_bars", fake_fetch)


# --- pct_change ------------------------------------------------------------


def test_pct_change_over_a_window() -> None:
    assert pct_change([100.0, 105.0, 110.0], 2) == 10.0


def test_pct_change_needs_enough_history() -> None:
    """Five sessions means six closes. Four is not "roughly five"."""
    assert pct_change([100.0, 105.0], 5) is None
    assert pct_change([], 1) is None


def test_pct_change_survives_a_zero_baseline() -> None:
    assert pct_change([0.0, 10.0], 1) is None


# --- VIX bands -------------------------------------------------------------


@pytest.mark.parametrize(
    ("vix", "expected"),
    [(35.0, "stressed"), (30.0, "stressed"), (25.0, "elevated"), (20.0, "elevated"),
     (17.0, "normal"), (15.0, "normal"), (12.0, "calm")],
)
async def test_vix_regime_bands(monkeypatch, vix, expected) -> None:
    _wire(monkeypatch, vix=_bars([vix] * 21))
    got = await fetch_market_context()
    assert got.vix == vix and got.vix_regime == expected


# --- risk appetite ---------------------------------------------------------


@pytest.mark.parametrize(
    ("trend", "regime", "expected"),
    [
        ("up", "calm", "risk-on"),
        ("up", "normal", "risk-on"),
        ("up", "elevated", "mixed"),
        ("up", "stressed", "risk-off"),  # stress overrides a rising market
        ("down", "calm", "risk-off"),
        ("sideways", "normal", "mixed"),
        (None, None, None),
    ],
)
def test_risk_appetite_is_a_stated_combination(trend, regime, expected) -> None:
    got = MarketContext(trend, None, None, None, regime, None, None)
    assert got.risk_appetite == expected


# --- relative strength -----------------------------------------------------


async def test_relative_strength_is_the_gap_in_percentage_points(monkeypatch) -> None:
    """The whole point of §17: was that move the stock, or the tide?"""
    _wire(monkeypatch, spy=_bars([100.0] * 16 + [101.0] * 5 + [102.0]))
    stock = _bars([100.0] * 16 + [101.0] * 5 + [120.0])
    got = await fetch_market_context(stock)
    assert got.relative_5d is not None and got.relative_5d > 15


async def test_a_sector_wide_move_shows_near_zero_relative_strength(monkeypatch) -> None:
    _wire(monkeypatch, spy=_bars([100.0] * 20 + [105.0]))
    got = await fetch_market_context(_bars([200.0] * 20 + [210.0]))
    assert got.relative_5d == 0.0


async def test_relative_strength_needs_the_same_trading_day(monkeypatch) -> None:
    """A foreign listing or a halted stock ends on a different date, so lining
    the series up by position would compare two different weeks."""
    _wire(monkeypatch)
    stale = _bars([100.0] * 21, end=datetime(2026, 8, 3, tzinfo=UTC))
    got = await fetch_market_context(stale)
    assert got.relative_5d is None and got.relative_20d is None
    assert got.market_change_5d is not None  # the market read still lands


async def test_no_stock_bars_still_gives_the_market_read(monkeypatch) -> None:
    _wire(monkeypatch)
    got = await fetch_market_context()
    assert got.relative_5d is None
    assert got.market_trend is not None and got.vix is not None


async def test_a_short_stock_history_drops_only_the_longer_window(monkeypatch) -> None:
    _wire(monkeypatch)
    got = await fetch_market_context(_bars([100.0] * 7))
    assert got.relative_5d is not None
    assert got.relative_20d is None


# --- degradation -----------------------------------------------------------


async def test_a_failed_market_fetch_is_empty_not_an_exception(monkeypatch) -> None:
    async def no_bars(symbol, **kw):
        return []

    monkeypatch.setattr(market, "fetch_bars", no_bars)
    assert await fetch_market_context(_bars([100.0] * 21)) == EMPTY


async def test_a_raising_fetch_is_caught(monkeypatch) -> None:
    async def boom(symbol, **kw):
        raise RuntimeError("yahoo is down")

    monkeypatch.setattr(market, "fetch_bars", boom)
    assert await fetch_market_context() == EMPTY


async def test_a_missing_vix_does_not_cost_the_market_read(monkeypatch) -> None:
    _wire(monkeypatch, vix=[])
    got = await fetch_market_context()
    assert got.vix is None and got.vix_regime is None
    assert got.market_change_5d is not None


# --- caching ---------------------------------------------------------------


async def test_index_bars_are_cached_across_calls(monkeypatch) -> None:
    """SPY and the VIX are the same for every ticker anyone asks about."""
    calls: list[str] = []
    _wire(monkeypatch, calls=calls)
    await fetch_market_context()
    await fetch_market_context()
    assert sorted(calls) == [market.MARKET_PROXY, market.VIX_SYMBOL]


async def test_a_failure_is_never_cached(monkeypatch) -> None:
    """Otherwise one blip blanks the market read for the whole TTL."""
    calls: list[str] = []

    async def no_bars(symbol, **kw):
        calls.append(symbol)
        return []

    monkeypatch.setattr(market, "fetch_bars", no_bars)
    await fetch_market_context()
    await fetch_market_context()
    assert len(calls) == 4


# --- payload ---------------------------------------------------------------


async def test_as_dict_is_camel_case_json(monkeypatch) -> None:
    _wire(monkeypatch)
    payload = (await fetch_market_context(_bars([100.0] * 21))).as_dict()
    assert set(payload) == {
        "marketTrend", "marketChange5d", "marketChange20d", "vix",
        "vixRegime", "relative5d", "relative20d", "riskAppetite",
    }
