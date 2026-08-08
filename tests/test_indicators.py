"""Technical indicators (committee plan, Phase 0).

These feed the rule engine, so a wrong value silently corrupts a risk decision
rather than showing up as a crash. The tests therefore check against
independently computed values, not against the implementation's own output.

The Wilder-vs-EMA distinction is the classic trap: ATR(14) and RSI(14) use
Wilder's smoothing, which is equivalent to an EMA of period 27, so computing
them with a plain 14-period EMA gives a plausible-looking but wrong number.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.prediction.indicators import (
    atr,
    compute_indicators,
    ema,
    ema_series,
    macd,
    rsi,
    sma,
    volatility_regime,
)
from app.prices import Bar


def _bars(rows: list[tuple[float, float, float]]) -> list[Bar]:
    """Bars from (high, low, close) triples."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(t=t0 + timedelta(days=i), open=c, high=h, low=low, close=c, volume=1000)
        for i, (h, low, c) in enumerate(rows)
    ]


def _flat_bars(closes: list[float], *, spread: float = 1.0) -> list[Bar]:
    return _bars([(c + spread / 2, c - spread / 2, c) for c in closes])


# --- moving averages -------------------------------------------------------


def test_sma_is_the_mean_of_the_last_n() -> None:
    assert sma([1, 2, 3, 4, 5], 5) == 3
    assert sma([1, 2, 3, 4, 5], 2) == 4.5


def test_sma_needs_enough_values() -> None:
    assert sma([1, 2], 5) is None
    assert sma([], 5) is None
    assert sma([1, 2, 3], 0) is None


def test_ema_seeds_on_the_sma_then_decays() -> None:
    # Seed = mean(1,2,3) = 2. Multiplier = 2/(3+1) = 0.5.
    # Next: (4-2)*0.5+2 = 3. Then: (5-3)*0.5+3 = 4.
    assert ema_series([1, 2, 3, 4, 5], 3) == [2, 3, 4]
    assert ema([1, 2, 3, 4, 5], 3) == 4


def test_ema_of_a_constant_series_is_that_constant() -> None:
    assert ema([7.0] * 20, 9) == pytest.approx(7.0)


def test_ema_needs_enough_values() -> None:
    assert ema([1, 2], 5) is None
    assert ema_series([1, 2], 5) == []


# --- ATR -------------------------------------------------------------------


def test_atr_of_a_constant_range_is_that_range() -> None:
    """Every bar spans exactly 2.0 with no gaps, so ATR must be 2.0."""
    bars = _bars([(101.0, 99.0, 100.0)] * 30)
    assert atr(bars) == pytest.approx(2.0)


def test_atr_counts_overnight_gaps_not_just_the_daily_span() -> None:
    """True range includes the gap from the previous close — that's the whole
    point of ATR over a simple high-minus-low."""
    tight = _bars([(100.5, 99.5, 100.0)] * 20)  # 1.0 span, no gaps
    gappy = _bars(
        [(100.5, 99.5, 100.0), (110.5, 109.5, 110.0)] * 10  # same span, 10-point gaps
    )
    assert atr(tight) == pytest.approx(1.0)
    assert atr(gappy) > 9.0  # the gap dominates


def test_atr_uses_wilder_smoothing_not_a_plain_ema() -> None:
    """A step up in volatility should be absorbed slowly. A 14-period EMA would
    react roughly twice as fast as Wilder's."""
    bars = _bars([(100.5, 99.5, 100.0)] * 20 + [(105.0, 95.0, 100.0)] * 5)
    value = atr(bars)
    # Wilder's after 5 wide bars lands nearer the old level than the new one.
    assert value is not None
    assert 1.0 < value < 5.0


def test_atr_needs_enough_bars() -> None:
    assert atr(_flat_bars([100.0] * 10)) is None  # 14-period needs 15 bars
    assert atr([]) is None


# --- RSI -------------------------------------------------------------------


def test_rsi_of_an_unbroken_rise_is_one_hundred() -> None:
    closes = [float(100 + i) for i in range(30)]
    assert rsi(closes) == 100.0


def test_rsi_of_an_unbroken_fall_is_zero() -> None:
    closes = [float(200 - i) for i in range(30)]
    assert rsi(closes) == pytest.approx(0.0, abs=0.01)


def test_rsi_of_a_flat_series_is_neutral() -> None:
    assert rsi([100.0] * 30) == 50.0


def test_rsi_of_an_alternating_series_sits_near_fifty() -> None:
    closes = [100.0 + (1 if i % 2 else 0) for i in range(40)]
    value = rsi(closes)
    assert value is not None and 40 < value < 60


def test_rsi_needs_enough_closes() -> None:
    assert rsi([100.0] * 10) is None


# --- MACD ------------------------------------------------------------------


def test_macd_of_a_constant_series_is_zero() -> None:
    got = macd([50.0] * 80)
    assert got is not None
    assert got.value == pytest.approx(0.0, abs=1e-6)
    assert got.histogram == pytest.approx(0.0, abs=1e-6)


def test_macd_is_positive_in_an_uptrend() -> None:
    """The fast EMA leads the slow one when price is rising."""
    got = macd([float(100 + i) for i in range(80)])
    assert got is not None and got.value > 0


def test_macd_is_negative_in_a_downtrend() -> None:
    got = macd([float(200 - i) for i in range(80)])
    assert got is not None and got.value < 0


def test_macd_histogram_is_value_minus_signal() -> None:
    got = macd([float(100 + i * 0.5) for i in range(90)])
    assert got is not None
    assert got.histogram == pytest.approx(got.value - got.signal, abs=1e-6)


def test_macd_needs_enough_closes() -> None:
    assert macd([100.0] * 20) is None  # needs 26 + 9


# --- volatility regime -----------------------------------------------------


def test_steady_volatility_reads_as_normal() -> None:
    assert volatility_regime(_bars([(101.0, 99.0, 100.0)] * 60)) == "normal"


def test_a_volatility_explosion_reads_as_extreme() -> None:
    calm = [(100.5, 99.5, 100.0)] * 50
    wild = [(110.0, 90.0, 100.0)] * 10
    assert volatility_regime(_bars(calm + wild)) == "extreme"


def test_regime_is_relative_to_the_stocks_own_normal() -> None:
    """A wide but *consistently* wide stock is normal for itself, not extreme —
    otherwise every volatile name would be permanently vetoed."""
    assert volatility_regime(_bars([(110.0, 90.0, 100.0)] * 60)) == "normal"


def test_regime_is_none_without_enough_history() -> None:
    assert volatility_regime(_bars([(101.0, 99.0, 100.0)] * 20)) is None


# --- the bundle ------------------------------------------------------------


def test_compute_indicators_fills_everything_with_enough_history() -> None:
    bars = _flat_bars([100.0 + i * 0.3 for i in range(220)], spread=2.0)
    got = compute_indicators(bars)

    assert got.atr14 is not None
    assert got.rsi14 == 100.0  # unbroken rise
    assert got.macd is not None and got.macd.value > 0
    assert got.sma20 is not None and got.sma50 is not None and got.sma200 is not None
    assert got.ema9 is not None and got.ema21 is not None
    assert got.volatility_regime is not None


def test_each_indicator_degrades_independently() -> None:
    """Short history must yield None per field, never a fabricated number — the
    rule engine treats missing data as a reason to wait."""
    got = compute_indicators(_flat_bars([100.0 + i for i in range(30)]))

    assert got.atr14 is not None and got.rsi14 is not None  # 14-period: fine
    assert got.sma20 is not None
    assert got.sma50 is None and got.sma200 is None  # not enough bars
    assert got.macd is None  # needs 35


def test_no_bars_at_all_is_safe() -> None:
    got = compute_indicators([])
    assert got.as_dict() == {
        "atr14": None,
        "rsi14": None,
        "macd": None,
        "sma20": None,
        "sma50": None,
        "sma200": None,
        "ema9": None,
        "ema21": None,
        "volatilityRegime": None,
    }


def test_as_dict_shape_matches_the_evidence_contract() -> None:
    got = compute_indicators(_flat_bars([100.0 + i * 0.2 for i in range(120)])).as_dict()
    assert set(got["macd"]) == {"value", "signal", "histogram"}
