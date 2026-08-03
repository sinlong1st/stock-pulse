"""Deterministic price signals for the AI prediction feature (spec step A).

The **numbers are real, the narrative is the AI** — so these signals are pure
math on real price bars (no AI): where the price sits in its recent range (the
"discount") and which way the trend leans. The analyst layer consumes them later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.prices import Bar, _epoch_to_dt

logger = logging.getLogger("stockpulse.prediction.signals")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockPulse/1.0"

DiscountLevel = str  # "cheap" | "fair" | "rich"
Trend = str  # "up" | "down" | "sideways"


@dataclass
class Signals:
    """Real, model-free read of a stock's recent price behaviour."""

    range_low: float
    range_high: float
    discount_level: DiscountLevel
    range_note: str  # e.g. "12% above the 3-month low, 22% below the high"
    discount_note: str  # e.g. "Near the lower third of its 3-month range."
    trend: Trend
    enough_history: bool


async def fetch_bars(
    ticker: str,
    *,
    range_: str = "6mo",
    base_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 10.0,
) -> list[Bar]:
    """Fetch daily OHLC bars from Yahoo's v8 chart. Best-effort → [] on failure."""
    base = (base_url or get_settings().yahoo_chart_url).rstrip("/")
    url = f"{base}/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": range_}
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Yahoo bars fetch failed for %s: %s", ticker, exc)
        return []

    result = (((data or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens, highs = quote.get("open") or [], quote.get("high") or []
    lows, closes, vols = quote.get("low") or [], quote.get("close") or [], quote.get("volume") or []

    bars: list[Bar] = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue  # Yahoo pads gaps with nulls
        t = _epoch_to_dt(ts)
        if t is None:
            continue
        bars.append(
            Bar(
                t=t,
                open=opens[i] if i < len(opens) and opens[i] is not None else close,
                high=highs[i] if i < len(highs) and highs[i] is not None else close,
                low=lows[i] if i < len(lows) and lows[i] is not None else close,
                close=close,
                volume=vols[i] if i < len(vols) and vols[i] is not None else 0.0,
            )
        )
    return bars


def _trend(closes: list[float], *, short: int = 10, long: int = 30, band: float = 0.01) -> Trend:
    """Short-vs-long moving-average lean, with a small flat band."""
    if len(closes) < 5:
        return "sideways"
    if len(closes) < long + 1:  # scale windows to what we have
        long = max(4, len(closes) // 2)
        short = max(2, long // 3)
    s = sum(closes[-short:]) / short
    long_ma = sum(closes[-long:]) / long
    if long_ma <= 0:
        return "sideways"
    ratio = (s - long_ma) / long_ma
    if ratio > band:
        return "up"
    if ratio < -band:
        return "down"
    return "sideways"


def _pivot_lows(bars: list[Bar], *, k: int = 2) -> list[float]:
    """Swing lows: bars whose low is the lowest within `k` bars either side.

    These are floors the price actually turned at, which is what makes them
    usable as support — unlike an arbitrary percentile of the range.
    """
    out: list[float] = []
    for i in range(k, len(bars) - k):
        low = bars[i].low
        if low is None:
            continue
        window = [b.low for b in bars[i - k : i + k + 1] if b.low is not None]
        if window and low <= min(window):
            out.append(low)
    return out


def _distinct(levels: list[float], *, count: int, band: float = 0.015) -> list[float]:
    """Keep up to `count` levels, dropping any within `band` of one already kept
    — two floors 0.5% apart are the same floor, not two separate levels."""
    out: list[float] = []
    for level in levels:
        if level <= 0:
            continue
        if all(abs(level - kept) / kept > band for kept in out):
            out.append(round(level, 2))
        if len(out) == count:
            break
    return out


def support_levels(bars: list[Bar], price: float | None, *, count: int = 3) -> list[float]:
    """Up to `count` grounded support levels below `price`, closest first.

    Built from real swing lows plus the window floor. If the price has broken
    below everything in the window there is no support left to name, so we fall
    back to the lowest distinct lows rather than inventing a number.
    """
    lows = [b.low for b in bars if b.low is not None]
    if not lows:
        return []

    candidates = _pivot_lows(bars)
    candidates.append(min(lows))  # the structural floor always counts

    below = sorted((c for c in candidates if price and c < price), reverse=True)
    levels = _distinct(below, count=count)
    if levels:
        return levels
    # Price is at/below every low we know of — offer the deepest floors instead.
    return _distinct(sorted(set(candidates)), count=count)


def compute_signals(bars: list[Bar], price: float | None, *, range_months: int = 3) -> Signals:
    """Turn real bars + the current price into discount + trend signals."""
    closes = [b.close for b in bars if b.close is not None]
    highs = [b.high for b in bars if b.high is not None]
    lows = [b.low for b in bars if b.low is not None]

    if len(closes) < 5 or not highs or not lows or not price or price <= 0:
        p = price or 0.0
        return Signals(
            p, p, "fair", "", "Not enough price history to judge yet.", "sideways", False
        )

    hi, lo = max(highs), min(lows)
    span = hi - lo
    pos = (price - lo) / span if span > 0 else 0.5
    if pos <= 0.33:
        level, where = "cheap", "lower third"
    elif pos >= 0.67:
        level, where = "rich", "upper third"
    else:
        level, where = "fair", "middle"

    above_low = (price - lo) / lo * 100 if lo > 0 else 0.0
    below_high = (hi - price) / hi * 100 if hi > 0 else 0.0
    range_note = (
        f"{above_low:.0f}% above the {range_months}-month low, {below_high:.0f}% below the high"
    )
    discount_note = f"Near the {where} of its {range_months}-month range."

    return Signals(lo, hi, level, range_note, discount_note, _trend(closes), True)
