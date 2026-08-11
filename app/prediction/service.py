"""Assemble a full prediction: gather evidence (real) → AI read.

Ties the deterministic evidence (step A) and the AI analyst (step B) together
behind one call. Best-effort on the data fetches; the numbers stay real and the
AI only writes the narrative. See specs/STOCKPULSE_AI_PREDICTION_PLAN.md.

The gathering half now lives in `app/prediction/evidence.py`, shared with the
Position Exit Advisor — both features must reason from identical facts.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.earnings import local_today
from app.evaluation import record_prediction_read
from app.prediction import rules as rule_engine
from app.prediction.agreement import evaluate as evaluate_agreement
from app.prediction.analyst import PredictionError, build_analyst
from app.prediction.evidence import GATHER_STAGES, gather, key_levels
from app.prediction.mode import plan as analysis_plan
from app.prediction.models import PredictionRead
from app.prediction.store import get_active_strategy
from app.prediction.strategies import Strategy
from app.prefs import resolve_language

logger = logging.getLogger("stockpulse.prediction.service")

# The stages build_prediction reports, in order. The app renders one step per
# entry, so changing this list changes the loader — keep them aligned.
# Built on GATHER_STAGES so the shared research steps can never drift apart from
# the ones the Exit Advisor reports.
PREDICT_STAGES = (*GATHER_STAGES, "analyze")


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
    # One shared definition — the Exit Advisor reads the same levels the same way.
    nearest, invalidation = key_levels(support)

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


def _second_payload(read: PredictionRead, second: tuple[str, PredictionRead] | None) -> dict | None:
    """The second-opinion block, or None when there isn't one (yet).

    Split out because it is built at two different moments: inline for the plain
    endpoint, and late for the streaming one once the slower model returns.
    """
    if not second:
        return None
    provider, other = second
    return {
        "provider": provider,
        "entry": other.entry.assessment,
        "note": other.entry.note,
        "horizons": [
            {"horizon": h.horizon, "lean": h.lean, "confidence": h.confidence}
            for h in other.horizons
        ],
        # Kept for the app already in people's hands: the backend and the OTA
        # bundle deploy separately, so removing this would break whatever build
        # is live. `agreement` supersedes it.
        "agrees": other.entry.assessment == read.entry.assessment,
        # Structured agreement (§11): catches the two cases the boolean cannot —
        # same entry grade with opposite directional leans, and a wide gap in
        # how sure the two models are.
        "agreement": evaluate_agreement(read, other).as_dict(),
    }


async def _second_opinion(
    settings: Settings, *, provider: str, **analyze_kwargs
) -> tuple[str, PredictionRead] | None:
    """Run the same prompt through a named second provider.

    Returns None when it fails — a second opinion is a bonus, never a reason to
    lose the prediction the user asked for.
    """
    try:
        analyst = build_analyst(settings, provider=provider)
        return provider, await analyst.analyze(**analyze_kwargs)
    except PredictionError as exc:
        logger.info("Second opinion from %s unavailable: %s", provider, exc)
        return None


async def build_prediction(
    settings: Settings | None = None,
    *,
    query: str,
    strategy: Strategy | None = None,
    analyst=None,
    language: str | None = None,
    session=None,
    mode: str | None = None,
    progress: Callable[[str], None] | None = None,
    emit: Callable[[str, dict], None] | None = None,
) -> dict:
    """Produce the prediction JSON (spec §2), or `{ok: False, reason}` on failure.

    Without an explicit `strategy`, the user's active one is used — that's what
    lets a custom lens actually change the read.

    `mode` picks the analyst(s) — "openai", "deepseek" or "both". Omitted, the
    user's saved choice applies. It is a request, not a guarantee: a mode naming
    a provider with no key falls back to one that works and says so in `analysis`.

    `progress` is called with a stage key as each phase begins, so a streaming
    caller can show real progress. Stage keys are part of the API — the app maps
    them to its step list — so keep them in sync with PREDICT_STAGES.

    `emit(name, payload)` turns on split delivery: the main read is emitted as
    `result` the moment it is ready, and the slower second opinion follows as a
    `second` event. Without it the second opinion is awaited inline and folded
    into the single returned payload, exactly as before.
    """
    settings = settings or get_settings()
    if strategy is None:
        strategy = get_active_strategy(settings)
    language = language or resolve_language(settings)
    vi = language.strip().lower() == "vietnamese"
    step = progress or (lambda _stage: None)

    # The shared research step — identical facts to the ones the Exit Advisor
    # reasons from. Reports the "resolve", "prices" and "news" stages itself.
    package = await gather(query, settings, progress=step)
    if package is None:
        return {"ok": False, "reason": f"Couldn't find a stock for '{query}'."}
    ticker, name = package.ticker, package.name
    price, fresh = package.price, package.freshness
    signals, support, news = package.signals, package.support, package.news
    earnings = package.earnings

    horizons = [h.strip() for h in settings.prediction_horizons.split(",") if h.strip()]

    step("analyze")
    analyze_kwargs = dict(
        ticker=ticker, name=name, signals=signals, news_lines=news,
        horizons=horizons, price=price, support=support,
        earnings=earnings, strategy=strategy, language=language,
    )
    # Who runs: the user's model choice, reconciled against the keys actually
    # configured. An injected analyst (tests, custom) bypasses the whole thing.
    analysis = analysis_plan(settings, mode=mode) if analyst is None else None
    if analyst is None and analysis is None:
        return {"ok": False, "reason": "No AI provider is configured (set an API key)."}
    # `prediction_second_opinion_enabled` stays a master kill-switch above the
    # user's choice, so an operator can stop the extra spend without touching it.
    run_second = bool(
        analysis and analysis.second and settings.prediction_second_opinion_enabled
    )
    # The second opinion runs concurrently, so it costs latency only when it is
    # slower than the primary — DeepSeek currently is, by roughly 3x.
    second_task = (
        asyncio.create_task(_second_opinion(settings, provider=analysis.second, **analyze_kwargs))
        if run_second
        else None
    )
    try:
        analyst = analyst or build_analyst(settings, provider=analysis.primary)
        read = await analyst.analyze(**analyze_kwargs)
    except PredictionError as exc:
        logger.warning("Prediction analysis failed: %s", exc)
        if second_task:
            second_task.cancel()
        return {"ok": False, "reason": "AI is unavailable right now (check the OpenAI key)."}

    # With `emit`, the slow model is NOT awaited here — the primary read goes out
    # as soon as it is ready and the second opinion follows in its own event.
    # Measured live: OpenAI ~6s, DeepSeek ~20s, so blocking costs ~11s of staring
    # at a loader for a result that was already finished.
    defer_second = bool(emit and second_task)
    second = None if defer_second else (await second_task if second_task else None)

    evidence = _evidence(
        price=price,
        signals=signals,
        support=support,
        resistance=package.resistance,
        indicators=package.indicators,
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
        "series": package.series,
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
        # Which analyst(s) actually ran. `downgraded` tells the app to explain
        # why the user didn't get the model they picked.
        "analysis": analysis.as_dict() if analysis else None,
        # An independent read of the same evidence by the other model, when one
        # is configured. Deliberately not merged into the main verdict — the
        # point is to see whether they agree, not to average them away.
        # None here when the second opinion is being streamed separately; the
        # `second` SSE event carries it instead.
        "secondOpinion": _second_payload(read, second),
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

    if defer_second:
        # The headline read is complete — send it now, then wait on the slower
        # model. The request stays open until the second event goes out, so the
        # opinion is still recorded even though the user is already reading.
        emit("result", payload)
        second = await second_task
        payload["secondOpinion"] = _second_payload(read, second)
        if payload["secondOpinion"]:
            emit("second", {"secondOpinion": payload["secondOpinion"]})
        else:
            # It failed or returned nothing. Say so rather than leaving the app
            # waiting on a card that will never arrive.
            emit("second", {"secondOpinion": None})

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
