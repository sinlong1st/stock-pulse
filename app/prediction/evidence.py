"""Gather everything known about one stock, before anyone forms an opinion.

Exit-advisor plan Phase 2. This is the shared research step: resolve the query
to a real ticker, then collect price bars, the current quote, deterministic
signals, support/resistance, indicators, earnings and fresh headlines.

It exists because Predict and the Exit Advisor need **exactly the same facts**
and ask different questions of them. Two copies of this would drift, and the day
they disagree about where WDC's support is — on the same stock, on the same
afternoon — both features stop being believable. So there is one copy.

Nothing here has an opinion. No AI call, no scoring, no recommendation: the
consumers do that. Everything is best-effort, and a field that couldn't be
fetched is ``None`` rather than a guess.

Not to be confused with `service._evidence()`, which shapes a *sub-block of the
Predict payload* from what this returns. That one is presentation; this one is
collection.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.briefing.focus import FocusTarget, build_focus_collectors, resolve_focus
from app.briefing.retrieval import retrieve_fresh_news
from app.commands.symbols import resolve_symbol_smart
from app.config import Settings, get_settings, resolve_briefing_timezone
from app.earnings import fetch_many
from app.prediction.indicators import Indicators, compute_indicators
from app.prediction.signals import (
    Signals,
    compute_signals,
    fetch_bars,
    nearest_resistance,
    support_levels,
)
from app.prices import Bar, maybe_briefing_price_client, price_freshness

logger = logging.getLogger("stockpulse.prediction.evidence")

_RANGE_LABEL = {1: "1mo", 3: "3mo", 6: "6mo", 12: "1y"}

_NEAR_WINDOW_BARS = 21  # ~1 trading month — enough swing lows to name three

_CHART_BARS = 130  # what the app's charts get; sliced by range client-side

# The stages `gather` reports, in order. Both PREDICT_STAGES and the exit
# advisor's stage list are built on top of these, so the app's loader shows the
# same first three steps for both features.
GATHER_STAGES = ("resolve", "prices", "news")


@dataclass(frozen=True)
class EvidencePackage:
    """The facts. What any analyst — human, AI or rule engine — starts from."""

    ticker: str
    name: str
    target: FocusTarget  # kept so callers can re-run news with the same collectors

    bars: list[Bar]
    price: float | None
    freshness: str | None  # FRESH | STALE | None when no quote client

    signals: Signals
    support: dict  # near/long single levels + nearLevels/longLevels lists
    resistance: float | None  # nearest swing high above the price
    indicators: Indicators
    series: dict  # closes/volumes/dates for the app's charts

    earnings: object | None
    news: list[str]


async def _resolve(query: str, settings: Settings) -> FocusTarget:
    """Watchlist match first (typo-tolerant), then search, then an AI guess.

    The watchlist match only covers stocks you already track, so anything else
    leans on `resolve_symbol_smart` to survive typos and run-together words.
    """
    target = resolve_focus(query)
    if target.ticker:
        return target
    found = await resolve_symbol_smart(query, settings=settings)
    if found:
        symbol, name = found
        return FocusTarget(query=query, ticker=symbol, name=name, search_term=name or symbol)
    return target  # ticker stays None → caller reports "couldn't find"


async def _current_price(ticker: str, settings: Settings) -> tuple[float | None, str | None]:
    client = maybe_briefing_price_client(settings)
    if client is None:
        return None, None
    try:
        snap = await client.snapshot(ticker)
    except Exception:
        return None, None
    if snap is None:
        return None, None
    fresh = price_freshness(snap.price_time, tz_name=resolve_briefing_timezone(settings)).upper()
    return snap.price, fresh


def _support_levels(bars: list[Bar], price: float | None) -> dict:
    """Grounded support from real price lows: up to three NEAR levels (the last
    ~month of swing lows — the floors just under today's price) and up to three
    LONG-term levels (the structural floors *below those*). Closest first.

    The long-term levels are deliberately drawn from below the near ones. The
    full window contains the recent window, so ranking both by "closest to the
    price" would let the long-term number land nearer than the near-term one —
    which reads as a bug, because it is one.

    `near`/`long` stay as the single closest level of each so older app builds
    keep working; `nearLevels`/`longLevels` carry the full list.
    """
    if not bars:
        return {"near": None, "long": None, "nearLevels": [], "longLevels": []}

    near_window = bars[-_NEAR_WINDOW_BARS:] if len(bars) >= _NEAR_WINDOW_BARS else bars
    near = support_levels(near_window, price)

    # Everything long-term must sit under the deepest near-term floor.
    ceiling = min(near) if near else price
    long = support_levels(bars, ceiling)
    if near:
        floor = min(near)
        long = [v for v in long if v < floor]  # guards the fallback branch too

    return {
        "near": near[0] if near else None,
        "long": long[0] if long else None,
        "nearLevels": near,
        "longLevels": long,
    }


def key_levels(support: dict) -> tuple[float | None, float | None]:
    """The nearest floor under the price, and the level that breaks the thesis.

    One definition, used by Predict's evidence block and by the Exit Advisor.
    Two copies would eventually disagree about the same stock on the same day,
    which is the failure this whole module exists to prevent.

    The thesis rests on the near-term floor *structure*, so it isn't broken by
    losing the closest level — it's broken by closing under the deepest of them.
    """
    near = support.get("nearLevels") or []
    long = support.get("longLevels") or []
    nearest = near[0] if near else (long[0] if long else None)
    invalidation = min(near) if near else (long[0] if long else None)
    return nearest, invalidation


async def _news_lines(target: FocusTarget, settings: Settings) -> list[str]:
    try:
        collectors = build_focus_collectors(target, settings)
        retrieval = await retrieve_fresh_news(
            window_hours=settings.briefing_focus_window_hours,
            settings=settings,
            collectors=collectors,
        )
        return [item.title for item in retrieval.all][:12]
    except Exception:
        logger.debug("News fetch failed for %s", target.ticker, exc_info=True)
        return []


async def gather(
    query: str,
    settings: Settings | None = None,
    *,
    progress: Callable[[str], None] | None = None,
) -> EvidencePackage | None:
    """Collect the facts for one stock, or ``None`` if the query names nothing.

    `progress` is called with a stage key as each phase begins — see
    GATHER_STAGES. The caller owns the wording of a failure, because "couldn't
    find a stock" reads differently in Predict and in the Exit Advisor.
    """
    settings = settings or get_settings()
    step = progress or (lambda _stage: None)

    step("resolve")
    target = await _resolve(query, settings)
    if not target.ticker:
        return None
    ticker, name = target.ticker, (target.name or target.ticker)

    step("prices")
    months = settings.prediction_range_months
    bars = await fetch_bars(ticker, range_=_RANGE_LABEL.get(months, "6mo"))
    price, freshness = await _current_price(ticker, settings)
    if price is None and bars:
        price = bars[-1].close

    recent = bars[-_CHART_BARS:]
    step("news")
    earnings = (await fetch_many([ticker], settings=settings)).get(ticker)
    news = await _news_lines(target, settings)

    return EvidencePackage(
        ticker=ticker,
        name=name,
        target=target,
        bars=bars,
        price=price,
        freshness=freshness,
        signals=compute_signals(bars, price, range_months=months),
        support=_support_levels(bars, price),
        resistance=nearest_resistance(bars, price),
        indicators=compute_indicators(bars),
        series={
            "closes": [round(b.close, 2) for b in recent],
            "volumes": [round(b.volume) for b in recent],
            "dates": [b.t.date().isoformat() for b in recent],
        },
        earnings=earnings,
        news=news,
    )
