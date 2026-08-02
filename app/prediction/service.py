"""Assemble a full prediction: resolve → signals (real) → news → AI read.

Ties the deterministic signals (step A) and the AI analyst (step B) together
behind one call. Best-effort on the data fetches; the numbers stay real and the
AI only writes the narrative. See specs/STOCKPULSE_AI_PREDICTION_PLAN.md.
"""

import logging
from datetime import UTC, datetime

from app.briefing.focus import FocusTarget, build_focus_collectors, resolve_focus
from app.briefing.retrieval import retrieve_fresh_news
from app.commands.symbols import resolve_symbol
from app.config import Settings, get_settings, resolve_briefing_timezone
from app.prediction.analyst import PredictionError, build_analyst
from app.prediction.signals import compute_signals, fetch_bars
from app.prediction.strategies import DEFAULT_STRATEGY, Strategy
from app.prices import maybe_briefing_price_client, price_freshness

logger = logging.getLogger("stockpulse.prediction.service")

_RANGE_LABEL = {1: "1mo", 3: "3mo", 6: "6mo", 12: "1y"}


async def _resolve(query: str, settings: Settings) -> FocusTarget:
    """Watchlist match first (typo-tolerant); else a Yahoo symbol search."""
    target = resolve_focus(query)
    if target.ticker:
        return target
    found = await resolve_symbol(query, settings=settings)
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
        logger.debug("News fetch failed for prediction", exc_info=True)
        return []


async def build_prediction(
    settings: Settings | None = None,
    *,
    query: str,
    strategy: Strategy = DEFAULT_STRATEGY,
    analyst=None,
    language: str = "English",
) -> dict:
    """Produce the prediction JSON (spec §2), or `{ok: False, reason}` on failure."""
    settings = settings or get_settings()

    target = await _resolve(query, settings)
    if not target.ticker:
        return {"ok": False, "reason": f"Couldn't find a stock for '{query}'."}
    ticker, name = target.ticker, (target.name or target.ticker)

    months = settings.prediction_range_months
    bars = await fetch_bars(ticker, range_=_RANGE_LABEL.get(months, "6mo"))
    price, fresh = await _current_price(ticker, settings)
    if price is None and bars:
        price = bars[-1].close
    signals = compute_signals(bars, price, range_months=months)

    news = await _news_lines(target, settings)
    horizons = [h.strip() for h in settings.prediction_horizons.split(",") if h.strip()]

    try:
        analyst = analyst or build_analyst(settings)
        read = await analyst.analyze(
            ticker=ticker, name=name, signals=signals, news_lines=news,
            horizons=horizons, strategy=strategy, language=language,
        )
    except PredictionError as exc:
        logger.warning("Prediction analysis failed: %s", exc)
        return {"ok": False, "reason": "AI is unavailable right now (check the OpenAI key)."}

    return {
        "ok": True,
        "ticker": ticker,
        "name": name,
        "price": f"{price:,.2f}" if price else None,
        "priceFresh": fresh,
        "discount": {
            "level": signals.discount_level,
            "vsRangeNote": signals.range_note,
            "note": signals.discount_note,
        },
        "trend": signals.trend,
        "enoughHistory": signals.enough_history,
        "horizons": [
            {
                "horizon": h.horizon,
                "lean": h.lean,
                "confidence": h.confidence,
                "rationale": h.rationale,
            }
            for h in read.horizons
        ],
        "drivers": read.drivers,
        "strategy": {"id": strategy.id, "name": strategy.name},
        "generatedAt": datetime.now(UTC).isoformat(),
        "disclaimer": "AI opinion — not investment advice.",
    }
