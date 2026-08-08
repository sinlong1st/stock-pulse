"""Standard technical indicators, computed from real bars.

Committee plan Phase 0. These are pure arithmetic over the OHLC bars we already
fetch — no AI, no new dependency, no network. They exist because the rule engine
needs them: ATR sizes "is this stop sane" and "has it already run too far", and
the volatility regime gates several vetoes.

Conventions worth knowing, because indicator definitions vary between sources:

- **ATR and RSI use Wilder's smoothing** (the original 1978 definition), not a
  simple moving average. Wilder's is what charting packages mean by ATR(14).
- **MACD uses the standard 12/26/9 EMA triple.**
- Every function returns ``None`` rather than guessing when there aren't enough
  bars. A missing indicator is a fact the rule engine acts on (RULE-DATA-001);
  a fabricated one would silently corrupt a risk decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.prices import Bar

# Wilder's smoothing needs a full period to seed, plus one bar to produce the
# first true range, so 14-period ATR needs 15 bars.
ATR_PERIOD = 14
RSI_PERIOD = 14


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values."""
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    """Exponential moving average, seeded with the first `period` values' SMA.

    Returns one value per input bar from the seed onwards, so callers can feed
    it into MACD rather than only reading the final figure.
    """
    if period <= 0 or len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    current = sum(values[:period]) / period
    out = [current]
    for value in values[period:]:
        current = (value - current) * multiplier + current
        out.append(current)
    return out


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def _true_ranges(bars: list[Bar]) -> list[float]:
    """True range per bar: the widest of today's span and the gaps from
    yesterday's close. Starts at the second bar, since it needs a previous close."""
    out: list[float] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        if current.high is None or current.low is None or previous.close is None:
            continue
        out.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return out


def _wilder(values: list[float], period: int) -> float | None:
    """Wilder's smoothing: seed with a simple average, then decay by 1/period.

    Not the same as an EMA of the same period — Wilder's is equivalent to an EMA
    of period (2n-1), which is why an ATR computed with a plain EMA reads too
    twitchy compared with any charting package.
    """
    if len(values) < period:
        return None
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = (current * (period - 1) + value) / period
    return current


def atr(bars: list[Bar], period: int = ATR_PERIOD) -> float | None:
    """Average True Range — the stock's typical daily movement, in dollars.

    This is the unit the rule engine measures risk in: a stop closer than ~0.5
    ATR is noise, and a price more than 1 ATR above the intended entry is a chase.
    """
    ranges = _true_ranges(bars)
    value = _wilder(ranges, period)
    return round(value, 4) if value is not None else None


def rsi(closes: list[float], period: int = RSI_PERIOD) -> float | None:
    """Relative Strength Index, 0-100, using Wilder's smoothing."""
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = _wilder(gains, period)
    avg_loss = _wilder(losses, period)
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0  # no downside: maximally overbought
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


@dataclass(frozen=True)
class Macd:
    value: float  # fast EMA minus slow EMA
    signal: float  # EMA of the MACD line
    histogram: float  # value minus signal


def macd(closes: list[float], *, fast: int = 12, slow: int = 26, signal: int = 9) -> Macd | None:
    """Standard MACD. Needs slow + signal bars before the signal line exists."""
    fast_series = ema_series(closes, fast)
    slow_series = ema_series(closes, slow)
    if not fast_series or not slow_series:
        return None
    # The two series start at different bars; align them on the shorter one.
    overlap = min(len(fast_series), len(slow_series))
    line = [f - s for f, s in zip(fast_series[-overlap:], slow_series[-overlap:], strict=True)]

    signal_series = ema_series(line, signal)
    if not signal_series:
        return None
    value, sig = line[-1], signal_series[-1]
    return Macd(value=round(value, 4), signal=round(sig, 4), histogram=round(value - sig, 4))


VolatilityRegime = str  # "low" | "normal" | "high" | "extreme"


def volatility_regime(bars: list[Bar], *, period: int = ATR_PERIOD) -> VolatilityRegime | None:
    """How today's volatility compares with this stock's own recent normal.

    Deliberately relative, not absolute: 3% daily range is calm for a small-cap
    biotech and extreme for a utility, so the comparison is ATR against the
    stock's own median ATR over the window.
    """
    current = atr(bars, period)
    if current is None or len(bars) < period * 3:
        return None

    # ATR at several points across the window, to get its own typical level.
    history: list[float] = []
    for end in range(period * 2, len(bars) + 1, max(1, period // 2)):
        value = atr(bars[:end], period)
        if value is not None:
            history.append(value)
    if len(history) < 3:
        return None

    ordered = sorted(history)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return None

    ratio = current / median
    if ratio >= 2.0:
        return "extreme"
    if ratio >= 1.35:
        return "high"
    if ratio <= 0.7:
        return "low"
    return "normal"


@dataclass(frozen=True)
class Indicators:
    """Everything the evidence package and rule engine need, or None if unknown."""

    atr14: float | None
    rsi14: float | None
    macd: Macd | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    ema9: float | None
    ema21: float | None
    volatility_regime: VolatilityRegime | None

    def as_dict(self) -> dict:
        return {
            "atr14": self.atr14,
            "rsi14": self.rsi14,
            "macd": (
                {
                    "value": self.macd.value,
                    "signal": self.macd.signal,
                    "histogram": self.macd.histogram,
                }
                if self.macd
                else None
            ),
            "sma20": self.sma20,
            "sma50": self.sma50,
            "sma200": self.sma200,
            "ema9": self.ema9,
            "ema21": self.ema21,
            "volatilityRegime": self.volatility_regime,
        }


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def compute_indicators(bars: list[Bar]) -> Indicators:
    """Compute the full set. Each field independently degrades to None."""
    closes = [b.close for b in bars if b.close is not None]
    return Indicators(
        atr14=atr(bars),
        rsi14=rsi(closes),
        macd=macd(closes),
        sma20=_round(sma(closes, 20)),
        sma50=_round(sma(closes, 50)),
        sma200=_round(sma(closes, 200)),
        ema9=_round(ema(closes, 9)),
        ema21=_round(ema(closes, 21)),
        volatility_regime=volatility_regime(bars),
    )
