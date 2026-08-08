"""Assemble a full prediction: resolve → signals (real) → news → AI read.

Ties the deterministic signals (step A) and the AI analyst (step B) together
behind one call. Best-effort on the data fetches; the numbers stay real and the
AI only writes the narrative. See specs/STOCKPULSE_AI_PREDICTION_PLAN.md.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.briefing.focus import FocusTarget, build_focus_collectors, resolve_focus
from app.briefing.retrieval import retrieve_fresh_news
from app.commands.symbols import resolve_symbol_smart
from app.config import Settings, get_settings, resolve_briefing_timezone
from app.earnings import fetch_many, local_today
from app.evaluation import record_prediction_read
from app.llm import available_providers
from app.prediction.models import PredictionRead
from app.prediction.analyst import PredictionError, build_analyst
from app.prediction import rules as rule_engine
from app.prediction.indicators import compute_indicators
from app.prediction.signals import (
    compute_signals,
    fetch_bars,
    nearest_resistance,
    support_levels,
)
from app.prediction.store import get_active_strategy
from app.prediction.strategies import Strategy
from app.prefs import resolve_language
from app.prices import maybe_briefing_price_client, price_freshness

logger = logging.getLogger("stockpulse.prediction.service")

_RANGE_LABEL = {1: "1mo", 3: "3mo", 6: "6mo", 12: "1y"}

# The stages build_prediction reports, in order. The app renders one step per
# entry, so changing this list changes the loader — keep them aligned.
PREDICT_STAGES = ("resolve", "prices", "news", "analyze")


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


_NEAR_WINDOW_BARS = 21  # ~1 trading month — enough swing lows to name three


def _support_levels(bars: list, price: float | None) -> dict:
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


def _pct(from_price: float, to_level: float) -> float:
    """Signed move from the current price to a level, in percent."""
    return round((to_level - from_price) / from_price * 100, 1)


def _evidence(
    *,
    price: float | None,
    signals,
    support: dict,
    resistance: float | None,
    indicators,
    news_count: int,
    earnings,
    today,
) -> dict:
    """The checkable facts the entry advice rests on — all arithmetic, no AI.

    Sent as numbers rather than sentences so the app can phrase them in the
    user's language. Anything we can't compute is null and the app hides it.
    """
    near = support.get("nearLevels") or []
    long = support.get("longLevels") or []
    nearest = near[0] if near else (long[0] if long else None)
    # The entry thesis rests on the near-term floor structure; a close under the
    # deepest of those levels is what breaks it.
    invalidation = min(near) if near else (long[0] if long else None)

    support_pct = _pct(price, nearest) if price and nearest else None
    # The reward leg is the nearest level price actually stalled at, NOT the
    # window's absolute high — on a stock far off its high the latter yields a
    # flattering ratio (75% upside "vs" 5% risk) that means nothing.
    target_pct = _pct(price, resistance) if price and resistance else None
    reward_risk = None
    if support_pct is not None and target_pct is not None and support_pct < 0 < target_pct:
        reward_risk = round(target_pct / abs(support_pct), 1)

    return {
        # The price everything else here is measured from, so the block is
        # self-contained for the rule engine and for later replay.
        "price": round(price, 2) if price else None,
        "rangeLow": round(signals.range_low, 2) if signals.range_low else None,
        "rangeHigh": round(signals.range_high, 2) if signals.range_high else None,
        "resistance": resistance,
        "targetPct": target_pct,
        "discountLevel": signals.discount_level,  # cheap | fair | rich
        "trend": signals.trend,
        "nearestSupport": nearest,
        "supportPct": support_pct,
        "rewardRisk": reward_risk,
        "invalidation": invalidation,
        "earningsInDays": earnings.days_until(today) if earnings else None,
        "newsCount": news_count,
        "enoughHistory": signals.enough_history,
        # Standard indicators (committee plan Phase 0). Each is null when there
        # aren't enough bars — the rule engine treats missing as a reason to wait.
        "indicators": indicators.as_dict(),
    }


def _confidence(horizons: list, signals) -> dict:
    """Why the confidence is what it is, as facts the app can phrase.

    Three things a reader would actually want to know: do the horizons agree,
    do the deterministic signals point the same way, and was there enough news
    to judge on.
    """
    leans = [h.lean for h in horizons]
    top = max(set(leans), key=leans.count) if leans else None
    agree = leans.count(top) if top else 0

    # A cheap price in a downtrend (or a rich one in an uptrend) is the classic
    # conflict: value says buy, momentum says wait.
    conflict = (signals.discount_level == "cheap" and signals.trend == "down") or (
        signals.discount_level == "rich" and signals.trend == "up"
    )
    return {
        "agree": agree,
        "total": len(leans),
        "lean": top,
        "signalsConflict": conflict,
    }


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


def _record(
    session,
    settings: Settings,
    payload: dict,
    price: float | None,
    *,
    horizons: list[dict] | None = None,
    provider: str | None = None,
) -> None:
    """Persist a read for later scoring. Best-effort: a bookkeeping failure
    must never cost the user the prediction they just paid for.

    `horizons`/`provider` let the second opinion be recorded too, so per-provider
    accuracy has both sides to compare.
    """
    if session is None or not settings.prediction_recording_enabled:
        return
    try:
        record_prediction_read(
            session,
            ticker=payload["ticker"],
            horizons=horizons if horizons is not None else payload["horizons"],
            strategy_id=payload["strategy"]["id"],
            baseline_price=price,
            provider=provider,
            dedupe_minutes=settings.prediction_cache_minutes,
        )
        session.commit()
    except Exception:
        logger.warning("Could not record prediction for evaluation", exc_info=True)
        session.rollback()


async def _second_opinion(
    settings: Settings, *, primary: str, **analyze_kwargs
) -> tuple[str, PredictionRead] | None:
    """Run the same prompt through the other configured provider.

    Returns None when there's no second provider or it fails — a second opinion
    is a bonus, never a reason to lose the prediction the user asked for.
    """
    others = [p for p in available_providers(settings) if p != primary]
    if not others:
        return None
    name = others[0]
    try:
        analyst = build_analyst(settings, provider=name)
        return name, await analyst.analyze(**analyze_kwargs)
    except PredictionError as exc:
        logger.info("Second opinion from %s unavailable: %s", name, exc)
        return None


async def build_prediction(
    settings: Settings | None = None,
    *,
    query: str,
    strategy: Strategy | None = None,
    analyst=None,
    language: str | None = None,
    session=None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Produce the prediction JSON (spec §2), or `{ok: False, reason}` on failure.

    Without an explicit `strategy`, the user's active one is used — that's what
    lets a custom lens actually change the read.

    `progress` is called with a stage key as each phase begins, so a streaming
    caller can show real progress. Stage keys are part of the API — the app maps
    them to its step list — so keep them in sync with PREDICT_STAGES.
    """
    settings = settings or get_settings()
    if strategy is None:
        strategy = get_active_strategy(settings)
    language = language or resolve_language(settings)
    vi = language.strip().lower() == "vietnamese"
    step = progress or (lambda _stage: None)

    step("resolve")
    target = await _resolve(query, settings)
    if not target.ticker:
        return {"ok": False, "reason": f"Couldn't find a stock for '{query}'."}
    ticker, name = target.ticker, (target.name or target.ticker)

    step("prices")
    months = settings.prediction_range_months
    bars = await fetch_bars(ticker, range_=_RANGE_LABEL.get(months, "6mo"))
    price, fresh = await _current_price(ticker, settings)
    if price is None and bars:
        price = bars[-1].close
    signals = compute_signals(bars, price, range_months=months)
    recent = bars[-130:]  # a series for the app's charts (sliced by range client-side)
    series = {
        "closes": [round(b.close, 2) for b in recent],
        "volumes": [round(b.volume) for b in recent],
        "dates": [b.t.date().isoformat() for b in recent],
    }
    support = _support_levels(bars, price)
    indicators = compute_indicators(bars)

    step("news")
    earnings = (await fetch_many([ticker], settings=settings)).get(ticker)
    news = await _news_lines(target, settings)
    horizons = [h.strip() for h in settings.prediction_horizons.split(",") if h.strip()]

    step("analyze")
    analyze_kwargs = dict(
        ticker=ticker, name=name, signals=signals, news_lines=news,
        horizons=horizons, price=price, support=support,
        earnings=earnings, strategy=strategy, language=language,
    )
    # The second opinion runs concurrently, so it costs latency only when it is
    # slower than the primary — DeepSeek currently is, by roughly 3x.
    second_task = (
        asyncio.create_task(_second_opinion(settings, primary="openai", **analyze_kwargs))
        if settings.prediction_second_opinion_enabled and analyst is None
        else None
    )
    try:
        analyst = analyst or build_analyst(settings)
        read = await analyst.analyze(**analyze_kwargs)
    except PredictionError as exc:
        logger.warning("Prediction analysis failed: %s", exc)
        if second_task:
            second_task.cancel()
        return {"ok": False, "reason": "AI is unavailable right now (check the OpenAI key)."}

    second = await second_task if second_task else None

    evidence = _evidence(
        price=price,
        signals=signals,
        support=support,
        resistance=nearest_resistance(bars, price),
        indicators=indicators,
        news_count=len(news),
        earnings=earnings,
        today=local_today(settings),
    )
    # Deterministic vetoes over the AI's entry call. Only ever more cautious.
    rules = (
        rule_engine.evaluate(
            read.entry.assessment,
            evidence,
            min_reward_risk=settings.prediction_min_reward_risk,
            avoid_earnings_within_days=settings.prediction_avoid_earnings_days,
        )
        if settings.prediction_rules_enabled
        else rule_engine.RuleResult(
            original=read.entry.assessment, final=read.entry.assessment, findings=[]
        )
    )
    if rules.overridden:
        logger.info(
            "Rules downgraded %s entry %s -> %s (%s)",
            ticker,
            rules.original,
            rules.final,
            ", ".join(f.code for f in rules.findings),
        )

    payload = {
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
        "series": series,
        "support": support,
        "earnings": earnings.as_dict(local_today(settings)) if earnings else None,
        "entry": {
            # The rule engine may have downgraded this; `rules` below shows what
            # the AI originally said and why it was overridden.
            "assessment": rules.final,
            "note": read.entry.note,
            # With no headlines the model has nothing company-specific to point
            # at and reliably falls back to restating the trend ("the downtrend
            # may continue"), which the evidence chips already say. Better to
            # show nothing than filler dressed up as insight.
            "risks": read.entry.risks if news else [],
        },
        # Checkable facts behind the entry advice, and why confidence is what it
        # is. Numbers, not sentences — the app phrases them per language.
        "evidence": evidence,
        "confidence": _confidence(read.horizons, signals),
        # What the deterministic rules made of it.
        "rules": rules.as_dict(),
        # An independent read of the same evidence by the other model, when one
        # is configured. Deliberately not merged into the main verdict — the
        # point is to see whether they agree, not to average them away.
        "secondOpinion": (
            {
                "provider": second[0],
                "entry": second[1].entry.assessment,
                "note": second[1].entry.note,
                "horizons": [
                    {"horizon": h.horizon, "lean": h.lean, "confidence": h.confidence}
                    for h in second[1].horizons
                ],
                "agrees": second[1].entry.assessment == read.entry.assessment,
            }
            if second
            else None
        ),
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
        # Display text follows the user's language; the analyst above still got
        # the English `body` as its prompt.
        "strategy": dict(
            zip(("name", "body"), strategy.display(vi), strict=True), id=strategy.id
        ),
        "language": language,
        "generatedAt": datetime.now(UTC).isoformat(),
        "disclaimer": (
            "Nhận định của AI — không phải lời khuyên đầu tư."
            if vi
            else "AI opinion — not investment advice."
        ),
    }

    # An injected analyst (tests, or a future custom one) may not be provider-backed.
    _record(session, settings, payload, price, provider=getattr(analyst, "name", None))
    if second:
        # Recorded separately so the accuracy loop can score each model on its
        # own calls — that comparison is the whole point of the second opinion.
        _record(
            session,
            settings,
            payload,
            price,
            horizons=[
                {"horizon": h.horizon, "lean": h.lean, "confidence": h.confidence}
                for h in second[1].horizons
            ],
            provider=second[0],
        )
    return payload
