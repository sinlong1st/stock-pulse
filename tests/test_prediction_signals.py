"""Tests for the deterministic prediction signals (AI prediction, step A)."""

from datetime import UTC, datetime, timedelta

import httpx

from app.prediction.signals import compute_signals, fetch_bars, support_levels
from app.prices import Bar


def _bars(closes: list[float]) -> list[Bar]:
    """Daily bars from a list of closes (high/low straddle the close)."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(t=t0 + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


# --- support_levels --------------------------------------------------------


def test_support_levels_finds_three_swing_lows() -> None:
    # Three clear troughs at 90 / 80 / 70 (lows are 1% under the close).
    bars = _bars([100, 110, 90, 100, 110, 80, 90, 100, 110, 70, 80, 90, 120])
    assert support_levels(bars, price=120.0) == [89.1, 79.2, 69.3]  # closest first


def test_support_levels_ignores_levels_above_the_price() -> None:
    bars = _bars([100, 110, 90, 100, 110, 80, 90, 100, 110, 70, 80, 90, 120])
    # At $85 the 89.1 floor is overhead resistance, not support.
    assert support_levels(bars, price=85.0) == [79.2, 69.3]


def test_support_levels_merges_near_identical_floors() -> None:
    # Troughs at 90 and 90.5 are the same floor — the closer one wins and the
    # other is dropped rather than listed as a second level.
    bars = _bars([100, 110, 90, 100, 110, 90.5, 100, 110, 70, 80, 90, 120])
    levels = support_levels(bars, price=120.0)
    assert levels[0] == 89.59  # the 90.5 trough, nearest the price
    assert len([v for v in levels if 88.0 < v < 91.0]) == 1


def test_support_levels_below_every_low_falls_back_to_deepest() -> None:
    bars = _bars([100, 110, 90, 100, 110, 80, 90, 100])
    # Price has broken under the whole window — name the deepest floors instead
    # of returning nothing.
    levels = support_levels(bars, price=50.0)
    assert levels and all(v > 50.0 for v in levels)


def test_support_levels_empty_without_bars() -> None:
    assert support_levels([], price=100.0) == []


# --- compute_signals -------------------------------------------------------


def test_discount_cheap_near_low() -> None:
    bars = _bars([100, 120, 140, 130, 110])  # range low ~99, high ~141.4
    sig = compute_signals(bars, price=101.0, range_months=3)
    assert sig.enough_history
    assert sig.discount_level == "cheap"
    assert "lower third" in sig.discount_note
    assert "3-month low" in sig.range_note


def test_discount_rich_near_high() -> None:
    sig = compute_signals(_bars([100, 120, 140, 130, 110]), price=140.0)
    assert sig.discount_level == "rich"
    assert "upper third" in sig.discount_note


def test_discount_fair_in_middle() -> None:
    sig = compute_signals(_bars([100, 120, 140, 130, 110]), price=120.0)
    assert sig.discount_level == "fair"


def test_trend_up_and_down() -> None:
    up = compute_signals(_bars([100, 102, 104, 106, 108, 110, 112, 114]), price=114.0)
    assert up.trend == "up"
    down = compute_signals(_bars([114, 112, 110, 108, 106, 104, 102, 100]), price=100.0)
    assert down.trend == "down"


def test_not_enough_history_is_safe() -> None:
    sig = compute_signals(_bars([100, 101]), price=100.5)
    assert sig.enough_history is False
    assert sig.discount_level == "fair" and sig.trend == "sideways"


def test_missing_price_is_safe() -> None:
    sig = compute_signals(_bars([100, 101, 102, 103, 104]), price=None)
    assert sig.enough_history is False


# --- fetch_bars ------------------------------------------------------------


async def test_fetch_bars_parses_yahoo_chart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v8/finance/chart/WDC" in str(request.url)
        assert request.url.params.get("interval") == "1d"
        return httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "timestamp": [1735689600, 1735776000, 1735862400],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [10.0, 11.0, None],
                                        "high": [10.5, 11.5, 12.5],
                                        "low": [9.5, 10.5, 11.5],
                                        "close": [10.2, None, 12.2],  # null padded gap dropped
                                        "volume": [1000, 2000, 3000],
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )

    bars = await fetch_bars("WDC", range_="6mo", transport=httpx.MockTransport(handler))
    assert [b.close for b in bars] == [10.2, 12.2]  # the null-close bar is skipped


async def test_fetch_bars_returns_empty_on_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert await fetch_bars("WDC", transport=httpx.MockTransport(boom)) == []
