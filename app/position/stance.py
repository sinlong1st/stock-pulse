"""Which way each context signal argues (for the CONTEXT card).

A row of numbers — trend, RSI, ATR, volume, earnings, market — tells you what is
true without telling you what it is *for*. This scores each one as arguing for
holding, for trimming, or neither.

Two decisions worth stating, because both were tempting to get wrong:

- **The stance is not "does it agree with the verdict".** A signal that argues
  for trimming argues for trimming whether the verdict was hold or exit; making
  it relative to the answer would flip the same fact's label between runs and
  teach the reader nothing. Each signal is scored on its own terms and the
  reader sees the balance.
- **Thresholds are imported from the rule engine, never restated.** These are
  the same numbers that actually move the advice, so a chip can't say "for
  trimming" while the rule that owns that threshold stayed silent.

Anything unknown is `neutral`, not omitted: a missing RSI is not evidence.
"""

from __future__ import annotations

from app.position.rules import (
    _BREAKOUT_VOLUME,
    _EXTENDED_ATRS,
    _NEAR_RESISTANCE_ATRS,
    _OVERBOUGHT_RSI,
)

# What one signal argues for. Named after the position, not the verdict.
HOLD = "supports-hold"
NEUTRAL = "neutral"
TRIM = "supports-trim"


def _trend(evidence: dict) -> str:
    trend = evidence.get("trend")
    if trend == "up":
        return HOLD
    if trend == "down":
        return TRIM
    return NEUTRAL


def _rsi(evidence: dict) -> str:
    """Overbought only counts against you *at a ceiling*.

    This mirrors what the app's own glossary promises: a high RSI is never a
    sell signal on its own, because a strong stock can hold above 70 for weeks.
    In open space it is momentum, which is why it reads neutral rather than
    supportive — it is not a reason to hold either.
    """
    rsi = (evidence.get("indicators") or {}).get("rsi14")
    if rsi is None:
        return NEUTRAL
    at_ceiling = (
        evidence.get("resistanceAtrs") is not None
        and evidence["resistanceAtrs"] <= _NEAR_RESISTANCE_ATRS
    )
    return TRIM if rsi >= _OVERBOUGHT_RSI and at_ceiling else NEUTRAL


def _extension(evidence: dict) -> str:
    """Stretched above the 20-day average argues for taking something off.

    Only the upside is scored. Well *below* the average is weakness, but the
    trend signal already carries that, and counting one fact twice would make
    the tally read as more evidence than there is.
    """
    atrs = evidence.get("aboveSma20Atrs")
    if atrs is None:
        return NEUTRAL
    return TRIM if atrs >= _EXTENDED_ATRS else NEUTRAL


def _volume(evidence: dict) -> str:
    """Volume has no direction of its own — it only confirms a move.

    So it supports holding when it is confirming a genuine breakout, and reads
    neutral otherwise. Heavy volume going nowhere is activity, not conviction.
    """
    relative = evidence.get("relativeVolume")
    price, resistance = evidence.get("price"), evidence.get("resistance")
    if relative is None:
        return NEUTRAL
    broke_out = bool(price and resistance and price > resistance)
    return HOLD if relative >= _BREAKOUT_VOLUME and broke_out else NEUTRAL


def _earnings(evidence: dict, *, within_days: int) -> str:
    days = evidence.get("earningsInDays")
    if days is None or days < 0:
        return NEUTRAL
    return TRIM if days <= within_days else NEUTRAL


def _market(evidence: dict) -> str:
    market = evidence.get("market") or {}
    appetite = market.get("riskAppetite")
    relative = market.get("relative20d")
    if appetite == "risk-off":
        return TRIM
    if appetite == "risk-on" and relative is not None and relative > 0:
        return HOLD
    return NEUTRAL


def read_stances(evidence: dict, *, earnings_within_days: int = 3) -> dict[str, str]:
    """Score every context signal. Keys match the chips the app already shows."""
    return {
        "trend": _trend(evidence),
        "rsi": _rsi(evidence),
        "extension": _extension(evidence),
        "volume": _volume(evidence),
        "earnings": _earnings(evidence, within_days=earnings_within_days),
        "market": _market(evidence),
    }
