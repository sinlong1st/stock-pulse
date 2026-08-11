"""Broad market context: what the tide is doing (spec §17).

Exit-advisor plan Phase 2. An exit decision needs to know whether a stock's move
is its own or the market's. "Up 6% while SPY is up 5.5%" is a very different
hold-or-trim question from "up 6% while SPY is flat", and the difference is not
visible anywhere in a single stock's own chart.

Everything here is deterministic arithmetic over real index bars — no AI, no new
dependency, no API key. SPY stands in for the S&P 500 and ^VIX for implied
volatility, both from the same free Yahoo chart endpoint the rest of the feature
uses.

Every field degrades to ``None`` independently. A market read is *context*, and
losing it must never cost the user their analysis — so the caller shows what it
has and hides what it doesn't.

Deliberately not here: sector ETFs and peers (§16). Peer selection has no source
of truth in this project, and a confidently wrong peer list is worse than no peer
comparison at all. See the plan's §3.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.prediction.signals import classify_trend, fetch_bars
from app.prices import Bar

logger = logging.getLogger("stockpulse.prediction.market")

MARKET_PROXY = "SPY"  # the S&P 500, as a tradable and always-available proxy
VIX_SYMBOL = "^VIX"

_RANGE = "3mo"  # enough bars for a 30-day trend read, no more

# SPY and the VIX are identical for every ticker anyone asks about, so a short
# cache turns N analyses per session into one pair of fetches. Kept small
# because the point of the number is that it's current.
_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, list[Bar]]] = {}

# Conventional VIX bands, not derived from anything in this project. They are
# the levels the market itself talks in, which is what makes them legible.
_VIX_BANDS = ((30.0, "stressed"), (20.0, "elevated"), (15.0, "normal"))
_VIX_FLOOR = "calm"


def clear_cache() -> None:
    """Drop the cached index bars. For tests and for a forced refresh."""
    _cache.clear()


async def _cached_bars(symbol: str, *, ttl: float = _CACHE_TTL_SECONDS) -> list[Bar]:
    now = time.monotonic()
    hit = _cache.get(symbol)
    if hit and hit[0] > now:
        return hit[1]
    bars = await fetch_bars(symbol, range_=_RANGE)
    if bars:  # never cache a failure — the next call should try again
        _cache[symbol] = (now + ttl, bars)
    return bars


def _closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars if b.close is not None]


def pct_change(closes: list[float], sessions: int) -> float | None:
    """Percent move over the last `sessions` trading days, or None if unknown."""
    if len(closes) < sessions + 1:
        return None
    then = closes[-1 - sessions]
    if then <= 0:
        return None
    return round((closes[-1] - then) / then * 100, 2)


def _same_session(stock_bars: list[Bar], market_bars: list[Bar]) -> bool:
    """Whether the two series end on the same trading day.

    Relative strength lines the series up by position from the end, which is only
    meaningful if both end on the same date. A foreign listing (symbol resolution
    can legitimately return one) trades a different calendar, and a stock halted
    for a week would look like it had outrun a market that moved without it.
    Rather than publish a confident wrong number, we publish nothing.
    """
    if not stock_bars or not market_bars:
        return False
    return stock_bars[-1].t.date() == market_bars[-1].t.date()


def _vix_regime(value: float | None) -> str | None:
    if value is None:
        return None
    for threshold, label in _VIX_BANDS:
        if value >= threshold:
            return label
    return _VIX_FLOOR


@dataclass(frozen=True)
class MarketContext:
    """§17 — the market backdrop, plus how the stock is doing against it."""

    market_trend: str | None  # up | down | sideways
    market_change_5d: float | None
    market_change_20d: float | None
    vix: float | None
    vix_regime: str | None  # calm | normal | elevated | stressed
    # The stock's move minus the market's, in percentage points. Positive means
    # the stock outran the tide; negative means the tide carried it and then some.
    relative_5d: float | None
    relative_20d: float | None

    @property
    def risk_appetite(self) -> str | None:
        """§17's risk-on / risk-off read, from the two signals we actually have.

        Stated as a combination rule rather than a judgement so it can't drift:
        a rising market with non-stressed volatility is risk-on, a falling market
        or stressed volatility is risk-off, anything else is mixed.
        """
        if self.market_trend is None and self.vix_regime is None:
            return None
        if self.vix_regime == "stressed" or self.market_trend == "down":
            return "risk-off"
        if self.market_trend == "up" and self.vix_regime in {"calm", "normal"}:
            return "risk-on"
        return "mixed"

    def as_dict(self) -> dict:
        return {
            "marketTrend": self.market_trend,
            "marketChange5d": self.market_change_5d,
            "marketChange20d": self.market_change_20d,
            "vix": self.vix,
            "vixRegime": self.vix_regime,
            "relative5d": self.relative_5d,
            "relative20d": self.relative_20d,
            "riskAppetite": self.risk_appetite,
        }


EMPTY = MarketContext(None, None, None, None, None, None, None)


async def fetch_market_context(stock_bars: list[Bar] | None = None) -> MarketContext:
    """Read the market backdrop, and the stock's strength against it.

    `stock_bars` are the bars already fetched for the stock — reused rather than
    re-requested, and compared window-for-window so relative strength means what
    it says. Omit them for the market read alone.

    Best-effort throughout: any failure yields a context with `None` fields, not
    an exception.
    """
    try:
        market_bars, vix_bars = await asyncio.gather(
            _cached_bars(MARKET_PROXY), _cached_bars(VIX_SYMBOL)
        )
    except Exception:  # network, parsing, anything
        logger.debug("Market context unavailable", exc_info=True)
        return EMPTY

    market_closes = _closes(market_bars)
    if not market_closes:
        return EMPTY

    market_5d = pct_change(market_closes, 5)
    market_20d = pct_change(market_closes, 20)

    stock_closes = _closes(stock_bars or [])
    relative_5d = relative_20d = None
    if stock_closes and _same_session(stock_bars, market_bars):
        stock_5d, stock_20d = pct_change(stock_closes, 5), pct_change(stock_closes, 20)
        if stock_5d is not None and market_5d is not None:
            relative_5d = round(stock_5d - market_5d, 2)
        if stock_20d is not None and market_20d is not None:
            relative_20d = round(stock_20d - market_20d, 2)

    vix_closes = _closes(vix_bars)
    vix = round(vix_closes[-1], 2) if vix_closes else None

    return MarketContext(
        market_trend=classify_trend(market_closes) if len(market_closes) >= 5 else None,
        market_change_5d=market_5d,
        market_change_20d=market_20d,
        vix=vix,
        vix_regime=_vix_regime(vix),
        relative_5d=relative_5d,
        relative_20d=relative_20d,
    )
