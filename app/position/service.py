"""Assemble the exit analysis: gather evidence → position math → the answer.

Exit-advisor plan Phase 4. Everything here is **arithmetic over real numbers**.
There is no AI call in this module and there does not need to be one for it to
be useful: §30's regret-minimization card — lock this much now, this much more
if it runs to resistance, this much back if it fails to support — is entirely
computed, and it is the question the whole feature exists to answer.

The AI narrative (Phase 5) layers on top and can be removed without taking the
feature with it. That ordering is deliberate: it means we find out how much the
model actually adds before paying for it on every request.

Framing follows §3.2 throughout. Average cost decides how the numbers *feel* and
what you owe in tax; it has no vote in whether the remaining upside is worth the
remaining risk. Both readings are shown, and they are labelled as different
questions rather than blended into one score.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.config import Settings, get_settings
from app.db.models import PositionExitAnalysisRow
from app.earnings import local_today
from app.position import math as pmath
from app.position import rules as rule_engine
from app.position.advisor import ExitAdvisorError, build_exit_analyst
from app.position.history import prune as prune_history
from app.position.math import Position, PositionError
from app.position.models import ExitRead
from app.position.store import SavedPosition, validate_fields
from app.prediction.evidence import GATHER_STAGES, gather, key_levels
from app.prediction.market import fetch_market_context
from app.prediction.mode import plan as analysis_plan
from app.prefs import resolve_language

logger = logging.getLogger("stockpulse.position.service")

# Same first three stages as Predict, then the market read, then the AI
# judgement. The last stage is skipped when no provider is configured, which
# the app handles the same way it handles any stage it never sees.
EXIT_STAGES = (*GATHER_STAGES, "market", "analyze")


@dataclass(frozen=True)
class ExitRequest:
    """One exit question: this holding, right now."""

    ticker: str
    position: Position
    stop: Decimal | None = None
    target: Decimal | None = None  # the user's own target, not a chart level
    allow_partial_sell: bool = True
    allow_fractional_shares: bool = False
    position_id: str | None = None


def request_from_saved(saved: SavedPosition) -> ExitRequest:
    return ExitRequest(
        ticker=saved.ticker,
        position=saved.to_position(),
        stop=saved.stop,
        target=saved.target,
        allow_partial_sell=saved.allow_partial_sell,
        position_id=saved.id,
    )


def request_from_fields(**fields: object) -> ExitRequest:
    """Validate an unsaved, one-off position through the store's own rules, so
    an inline request can never be accepted where a saved one would be refused."""
    record = validate_fields(**fields)  # type: ignore[arg-type]
    return ExitRequest(
        ticker=record["ticker"],
        position=Position(
            shares=Decimal(record["shares"]),
            average_cost=Decimal(record["average_cost"]),
        ),
        stop=Decimal(record["stop"]) if record["stop"] else None,
        target=Decimal(record["target"]) if record["target"] else None,
        allow_partial_sell=record["allow_partial_sell"],
    )


def _d(value: float | None) -> Decimal | None:
    """A float level from the signals layer as Decimal, for the money math."""
    return Decimal(str(value)) if value is not None else None


def _technicals(package, market) -> dict:
    """The §32 technical card, as values rather than sentences."""
    return {
        "trend": package.signals.trend,
        "discountLevel": package.signals.discount_level,
        "rangeLow": round(package.signals.range_low, 2) or None,
        "rangeHigh": round(package.signals.range_high, 2) or None,
        "rangeNote": package.signals.range_note,
        "enoughHistory": package.signals.enough_history,
        "indicators": package.indicators.as_dict(),
        "market": market.as_dict(),
    }


def _extension(price: float | None, indicators) -> dict:
    """How stretched the price is, in the units the rule engine will use.

    ATRs above the 20-day average is the honest way to say "extended": a stock
    5% above its mean is calm if it moves 3% a day and stretched if it moves
    0.4%. Percent alone would compare two different things.
    """
    sma20, atr = indicators.sma20, indicators.atr14
    if not price or not sma20 or sma20 <= 0:
        return {"aboveSma20Pct": None, "aboveSma20Atrs": None}
    above = price - sma20
    return {
        "aboveSma20Pct": round(above / sma20 * 100, 2),
        "aboveSma20Atrs": round(above / atr, 2) if atr and atr > 0 else None,
    }


def relative_volume(bars, *, window: int = 20) -> float | None:
    """Latest session's volume against its recent average (§10).

    The confirmation leg of RULE-EXIT-010: a breakout on ordinary volume is
    drift, not participation. None when there aren't enough sessions to have an
    average worth comparing to.
    """
    volumes = [b.volume for b in bars if b.volume]
    if len(volumes) < window + 1:
        return None
    average = sum(volumes[-window - 1 : -1]) / window
    return round(volumes[-1] / average, 2) if average > 0 else None


def _session_today(bars, *, now: datetime | None = None) -> bool:
    """Whether the market has traded today, judged from the bars themselves.

    Deliberately not a market calendar. Yahoo starts publishing the current
    day's bar once trading opens, so the data already knows about weekends and
    every exchange holiday — and a hand-rolled calendar would be wrong on
    Juneteenth exactly once and then silently forever. Same instinct as the
    evaluation loop, which defers on the last-trade timestamp rather than
    computing whether the market "should" have been open.
    """
    if not bars:
        return False
    return bars[-1].t.date() == (now or datetime.now(UTC)).date()


def _quote_age_minutes(
    price_time: datetime | None, *, now: datetime | None = None
) -> float | None:
    """How old the quote is, in minutes. None when there is no quote client."""
    if price_time is None:
        return None
    return ((now or datetime.now(UTC)) - price_time).total_seconds() / 60.0


def build_level_menu(
    *, price: float, support: dict, resistance: float | None, atr: float | None
) -> list[tuple[float, str]]:
    """The real levels the AI is allowed to reference, cheapest first.

    This is what stops the model inventing prices: it picks menu *numbers*, so
    "$500" is not expressible. Everything on it came from real price action,
    except the two stretch levels — one ATR beyond the outermost real level —
    which exist so a bull case isn't capped at the nearest ceiling and a bear
    case isn't floored at the last support. Those are computed by us and
    labelled as extensions, which is still not the model making up a number.
    """
    supports = sorted(
        {
            level
            for level in (support.get("nearLevels") or []) + (support.get("longLevels") or [])
            if level and level < price
        }
    )
    menu: list[tuple[float, str]] = []
    if supports and atr and atr > 0:
        menu.append((round(supports[0] - atr, 2), "one ATR below the deepest support"))
    menu += [(level, "support") for level in supports]
    menu.append((round(price, 2), "current price"))
    if resistance:
        menu.append((resistance, "nearest resistance"))
        if atr and atr > 0:
            menu.append((round(resistance + atr, 2), "one ATR above resistance"))
    elif atr and atr > 0:
        menu.append((round(price + atr, 2), "one ATR above the current price"))
    return menu


def _pick(levels: list[tuple[float, str]], value: float | None) -> float | None:
    """Resolve the model's level reference against the menu, or None.

    Accepts either form the model actually uses: the level's **price** (what
    gpt-4o-mini returns in practice, and what the prompt now asks for) or its
    1-based position in the list. Prices are matched first, so a penny-stock
    menu containing $3.00 can't be mistaken for "item 3".

    Anything that matches neither is **dropped, never snapped to the nearest**.
    That is the whole guarantee: an invented $500 has no menu entry, so it
    cannot reach the user. Snapping would convert a hallucination into a
    plausible-looking decision, which is strictly worse than saying nothing.
    """
    if value is None:
        return None
    for price, _label in levels:
        if abs(price - value) < 0.01:
            return price
    if float(value).is_integer() and 1 <= value <= len(levels):
        return levels[int(value) - 1][0]
    logger.info("Dropped level reference %s: not on the menu", value)
    return None


def _level_distances(price: float | None, indicators, nearest_support, resistance) -> dict:
    """How far the two legs are, measured in the stock's own daily range.

    Percentages alone make a hold reward/risk look better than it is. A live WDC
    run returned 6.62:1 "strong" — real arithmetic, from a support 1.6% below a
    stock whose ATR is 12% of its price. That floor is inside a single ordinary
    day's movement, so the risk leg it implies is not a risk anyone could
    actually take.

    This is the same trap as using the window high as the reward leg, from the
    other side: there, the reward was too far to mean anything; here the risk is
    too close. The ratio stays as computed — it isn't wrong — and this carries
    the context that says how much to trust it. The Phase 6 rule engine reads
    these, mirroring RULE-STOP-001 in `app/prediction/rules.py`.
    """
    atr = getattr(indicators, "atr14", None)
    if not price or not atr or atr <= 0:
        return {"supportAtrs": None, "resistanceAtrs": None, "atr14": atr}
    return {
        "supportAtrs": (
            round((price - nearest_support) / atr, 2) if nearest_support else None
        ),
        "resistanceAtrs": round((resistance - price) / atr, 2) if resistance else None,
        "atr14": atr,
    }


def _record(session, settings: Settings, payload: dict, request: ExitRequest) -> int | None:
    """Persist the analysis snapshot for later scoring.

    Best-effort, exactly like the Predict recorder: a bookkeeping failure must
    never cost the user the analysis they just waited for. Nothing reads these
    rows yet — see `PositionExitAnalysisRow` for why capture runs ahead of the
    scorer.

    The whole payload goes into `evidence_json` because §25.7 and §38 both need
    the advice *as given*: recomputing levels later would score a reconstruction,
    and any change to how support is derived would silently rewrite history.
    """
    if session is None or not settings.position_exit_recording_enabled:
        return None
    try:
        levels = payload.get("levels") or {}
        advice = payload.get("advice") or {}
        position = payload.get("position") or {}
        hold = payload.get("holdRewardRisk") or {}
        rules = payload.get("rules") or {}
        row = PositionExitAnalysisRow(
            position_id=request.position_id,
            ticker=payload["ticker"],
            shares=float(request.position.shares),
            average_cost=float(request.position.average_cost),
            price=position.get("currentPrice"),
            # What the user was actually shown, which is what a later review has
            # to judge — not the model's unedited opinion.
            action=advice.get("action") or rules.get("final") or "no-clear-edge",
            ai_action=advice.get("aiAction"),
            rules_final=rules.get("final"),
            confidence=advice.get("confidence"),
            provider=advice.get("provider"),
            support=levels.get("nearestSupport"),
            resistance=levels.get("resistance"),
            invalidation=levels.get("invalidation"),
            atr14=(levels.get("distance") or {}).get("atr14"),
            hold_reward_risk=hold.get("ratio"),
            unrealized_pnl=position.get("unrealizedPnl"),
            evidence_json=payload,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        # Same transaction as the insert, so the table can't grow past the
        # retention window even if something later fails.
        prune_history(session, days=settings.position_exit_history_days)
        session.commit()
        return row.id
    except Exception:
        logger.warning("Could not record the exit analysis", exc_info=True)
        session.rollback()
        return None


async def _analyze(
    settings: Settings,
    *,
    analyst,
    mode: str | None,
    step: Callable[[str], None],
    **analyze_kwargs,
) -> tuple[ExitRead | None, str | None]:
    """Run the AI judgement, or return `(None, None)` if it can't or shouldn't.

    Deliberately single-model even when the user's saved mode is `both`. A
    second opinion doubles the wait on a decision the numbers already answer,
    and the agreement machinery has nothing useful to compare until this format
    has been used in anger. Revisit once there's real usage — see plan §9.3.
    """
    if analyst is None:
        if not settings.position_exit_ai_enabled:
            return None, None
        plan = analysis_plan(settings, mode=mode)
        if plan is None:  # no key configured anywhere
            return None, None
        try:
            analyst = build_exit_analyst(settings, provider=plan.primary)
        except ExitAdvisorError as exc:
            logger.info("Exit analyst unavailable: %s", exc)
            return None, None

    step("analyze")
    try:
        return await analyst.analyze(**analyze_kwargs), getattr(analyst, "name", None)
    except ExitAdvisorError as exc:
        # The numbers are already complete; losing the narrative is a
        # degradation, not a failure.
        logger.warning("Exit analysis failed, returning numbers only: %s", exc)
        return None, None


def _scenarios(read: ExitRead | None, levels, summary) -> list[dict]:
    """§20 — the model's level picks turned into position dollars.

    Scenarios whose levels don't resolve are dropped rather than repaired: a
    partial set of real cases beats a full set containing an invented one.
    Probabilities are renormalized over whatever survives, so the three shown
    always sum to 100.
    """
    if not read or not read.scenarios:
        return []
    resolved = []
    for scenario in read.scenarios:
        low = _pick(levels, scenario.low_level)
        high = _pick(levels, scenario.high_level)
        if low is None or high is None:
            logger.info(
                "Dropped %s scenario: levels %s/%s are not on the menu",
                scenario.name, scenario.low_level, scenario.high_level,
            )
            continue
        resolved.append((scenario, low, high))
    if not resolved:
        return []

    probabilities = pmath.normalize_probabilities([s.probability for s, _, _ in resolved])
    out = []
    for (scenario, low, high), probability in zip(resolved, probabilities, strict=True):
        computed = pmath.scenario(
            summary,
            name=scenario.name,
            probability=probability,
            low=_d(low),
            high=_d(high),
        )
        out.append({**computed.as_dict(), "trigger": scenario.trigger})
    return out


def _plans(
    read: ExitRead | None,
    levels,
    summary,
    request: ExitRequest,
    invalidation: float | None = None,
) -> list[dict]:
    """§23/§24 — each alternative costed out on the user's actual share count."""
    if not read or not read.plans:
        return []
    out = []
    for plan in read.plans:
        sell_pct = plan.sell_pct_now if plan.action != "hold" else None
        if plan.action == "sell-all":
            sell_pct = 100
        # A plan that says trim without saying how much is not a plan; the
        # balanced default from §24 is the honest reading of "partial".
        if plan.action == "partial-sell" and not sell_pct:
            sell_pct = 33

        sale = None
        if sell_pct and request.allow_partial_sell or (sell_pct == 100):
            sale = pmath.partial_sell(
                summary,
                sell_pct,
                target=_d(_pick(levels, plan.first_target_level)),
                allow_fractional=request.allow_fractional_shares,
            ).as_dict()

        picked = _pick(levels, plan.invalidation_level)
        out.append({
            "name": plan.name,
            "action": plan.action,
            "sellPctNow": sell_pct,
            "stop": _pick(levels, plan.stop_level),
            "firstTarget": _pick(levels, plan.first_target_level),
            # Never deeper than the level that actually breaks the near-term
            # thesis. A live MSFT run picked a floor 33% below the price as
            # "thesis breaks", which is not an invalidation — it is a level you
            # would have abandoned the position long before reaching.
            "invalidation": (
                invalidation
                if picked is not None and invalidation is not None and picked < invalidation
                else picked
            ),
            "explanation": plan.explanation,
            "sale": sale,
        })
    return _relabel_by_risk(out)


# §24's names describe how much risk each plan accepts, not how decisive it is.
_PLAN_NAMES = ("conservative", "balanced", "aggressive")


def _relabel_by_risk(plans: list[dict]) -> list[dict]:
    """Force the §24 names to mean what §24 says: conservative sells the most.

    A live MSFT run came back with conservative="hold it all" and
    aggressive="sell 100%" — exactly inverted, because "aggressive" reads as
    "decisive" unless you are told otherwise. The prompt now says so explicitly,
    but a wording change is a hope, not a guarantee, and advice whose labels
    invert their meaning is worse than no labels.

    Relabelling rather than reordering is safe because each explanation
    describes its *action* ("exiting position due to lack of clear edge"), not
    its former name — so "conservative: sell 100%, exiting the position" still
    reads true. Ties keep the model's original order.
    """
    if not plans:
        return plans
    ordered = sorted(plans, key=lambda p: p["sellPctNow"] or 0, reverse=True)
    return [{**plan, "name": name} for plan, name in zip(ordered, _PLAN_NAMES, strict=False)]


async def build_exit_advice(
    settings: Settings | None = None,
    *,
    request: ExitRequest,
    analyst=None,
    mode: str | None = None,
    session=None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Produce the exit analysis JSON, or `{ok: False, reason}` on failure.

    `progress` reports EXIT_STAGES as each phase begins, for the streaming
    caller. No LLM is involved, so this costs one set of data fetches and no
    tokens at all.
    """
    settings = settings or get_settings()
    step = progress or (lambda _stage: None)
    language = resolve_language(settings)
    vi = language.strip().lower() == "vietnamese"

    package = await gather(request.ticker, settings, progress=step)
    if package is None:
        return {"ok": False, "reason": f"Couldn't find a stock for '{request.ticker}'."}

    if package.price is None:
        # §41: without a verified price there is no current value, no P&L and no
        # risk/reward — every number on the screen would be a guess.
        return {
            "ok": False,
            "reason": (
                "Current market price could not be verified, so StockPulse can't "
                "evaluate this position yet."
            ),
            "ticker": package.ticker,
        }

    step("market")
    market = await fetch_market_context(package.bars)

    try:
        price = pmath.parse_price(package.price)
    except PositionError:
        return {"ok": False, "reason": "The market price came back unusable."}

    summary = pmath.summarize(request.position, price)

    # Levels, read exactly as Predict reads them.
    nearest_support, invalidation = key_levels(package.support)
    supports = [
        _d(level)
        for level in (package.support.get("nearLevels") or [])
        + (package.support.get("longLevels") or [])
    ]
    resistance = _d(package.resistance)

    # The headline trade: what the chart says is above, against what's below.
    # The reward leg is the nearest level price actually stalled at — never the
    # window high, which on a stock far off its high flatters the ratio into
    # meaninglessness.
    hold = pmath.hold_reward_risk(
        summary, target=resistance, support=_d(nearest_support)
    )
    # The same question against the user's own target, when they set one. Kept
    # separate rather than substituted: one is what the chart offers, the other
    # is what they are hoping for, and conflating them hides the difference.
    at_target = (
        pmath.hold_reward_risk(summary, target=request.target, support=_d(nearest_support))
        if request.target is not None
        else None
    )

    partials = (
        pmath.partial_sell_options(
            summary,
            target=resistance or request.target,
            allow_fractional=request.allow_fractional_shares,
        )
        if request.allow_partial_sell
        else []
    )

    earnings_days = (
        package.earnings.days_until(local_today(settings)) if package.earnings else None
    )
    distances = _level_distances(
        package.price, package.indicators, nearest_support, package.resistance
    )
    extension = _extension(package.price, package.indicators)

    # The flat fact sheet the rule engine reads. Assembled here so the engine
    # itself stays pure arithmetic over a dict — trivially testable, and with no
    # opinion about where the numbers came from.
    rule_evidence = {
        "price": package.price,
        "trend": package.signals.trend,
        "enoughHistory": package.signals.enough_history,
        "hasNearSupport": bool(package.support.get("nearLevels")),
        "resistance": package.resistance,
        "holdRewardRisk": float(hold.ratio) if hold else None,
        "supportAtrs": distances["supportAtrs"],
        "resistanceAtrs": distances["resistanceAtrs"],
        "aboveSma20Atrs": extension["aboveSma20Atrs"],
        "indicators": package.indicators.as_dict(),
        "market": market.as_dict(),
        "relativeVolume": relative_volume(package.bars),
        "earningsInDays": earnings_days,
        "inProfit": summary.in_profit,
        "stop": float(request.stop) if request.stop is not None else None,
        "quoteAgeMinutes": _quote_age_minutes(package.price_time),
        "sessionToday": _session_today(package.bars),
    }
    # The AI judgement, when a provider is configured. Everything above this
    # point is already a complete answer, so a failure here costs the narrative
    # and nothing else.
    levels = build_level_menu(
        price=package.price,
        support=package.support,
        resistance=package.resistance,
        atr=package.indicators.atr14,
    )
    read, analysis_provider = await _analyze(
        settings,
        analyst=analyst,
        mode=mode,
        ticker=package.ticker,
        name=package.name,
        facts={
            **rule_evidence,
            **summary.as_dict(),
            **extension,
            "freshness": package.freshness,
            "holdRewardRisk": hold.as_dict() if hold else None,
            "discountLevel": package.signals.discount_level,
            "rangeNote": package.signals.range_note,
        },
        levels=levels,
        news=package.news,
        language=language,
        step=step,
    )

    rules = (
        rule_engine.evaluate(
            read.action if read else None,
            rule_evidence,
            min_hold_reward_risk=settings.position_exit_min_hold_reward_risk,
            earnings_within_days=settings.position_exit_earnings_days,
            stale_quote_minutes=settings.position_exit_stale_quote_minutes,
        )
        if settings.position_exit_rules_enabled
        else rule_engine.ExitRuleResult(
            original=read.action if read else None,
            final=read.action if read else None,
            findings=[],
        )
    )
    if rules.overridden:
        logger.info(
            "Exit rules moved %s from %s to %s (%s)",
            package.ticker, rules.original, rules.final,
            ", ".join(f.code for f in rules.findings),
        )

    payload = {
        "ok": True,
        "positionId": request.position_id,
        "ticker": package.ticker,
        "name": package.name,
        "price": f"{package.price:,.2f}",
        "priceFresh": package.freshness,
        # §32 position header + summary.
        "position": summary.as_dict(),
        # §7 — what falling to each real floor would cost, nearest first.
        "giveback": [level.as_dict() for level in pmath.giveback_analysis(summary, supports)],
        # §6 — the incremental trade, judged from here forward.
        "holdRewardRisk": hold.as_dict() if hold else None,
        "atYourTarget": at_target.as_dict() if at_target else None,
        # §8 — the compromise the spec insists must be first-class.
        "partialSell": [option.as_dict() for option in partials],
        "allowPartialSell": request.allow_partial_sell,
        # §31 — informational sizing. Never described as "free shares".
        "costBasisRecovery": pmath.cost_basis_recovery(
            summary, allow_fractional=request.allow_fractional_shares
        ).as_dict(),
        "levels": {
            "nearestSupport": nearest_support,
            "invalidation": invalidation,
            "resistance": package.resistance,
            "supports": package.support,
            "stop": float(request.stop) if request.stop is not None else None,
            "target": float(request.target) if request.target is not None else None,
            # How far each leg is in ATRs — the context that says how much the
            # reward/risk ratio above is worth trusting.
            "distance": distances,
        },
        "technicals": _technicals(package, market),
        "extension": extension,
        # What the deterministic rules made of it. `final` is the least exposure
        # the evidence justifies; with no AI recommendation to cap, it is null
        # whenever nothing fired.
        "rules": rules.as_dict(),
        "relativeVolume": rule_evidence["relativeVolume"],
        # The AI's judgement, with `action` already capped by the rules above.
        # Null when no provider is configured — the numbers stand on their own.
        "advice": (
            {
                "action": rules.final or read.action,
                "aiAction": read.action,
                "confidence": read.confidence,
                "thesis": read.thesis,
                "reasonsToHold": read.reasons_to_hold,
                "reasonsToSell": read.reasons_to_sell,
                "warnings": read.warnings,
                "provider": analysis_provider,
            }
            if read
            else None
        ),
        # §20/§21 — the model chose which real levels bound each case; every
        # dollar here was computed from them.
        "scenarios": _scenarios(read, levels, summary),
        # §24's conservative / balanced / aggressive alternatives.
        "plans": _plans(read, levels, summary, request, invalidation),
        "earnings": (
            package.earnings.as_dict(local_today(settings)) if package.earnings else None
        ),
        "earningsInDays": earnings_days,
        "news": package.news,
        "newsCount": len(package.news),
        "series": package.series,
        "language": language,
        "generatedAt": datetime.now(UTC).isoformat(),
        # No AI ran, so this is arithmetic — but it is still not advice.
        "disclaimer": (
            "Số liệu tính toán — không phải lời khuyên đầu tư."
            if vi
            else "Calculated figures — not investment advice."
        ),
    }

    # Capture the snapshot for a scorer that doesn't exist yet. The price,
    # levels and verdict as of this moment cannot be reconstructed later.
    # The row id goes back into the payload (spec §9's `analysisId`) so the
    # history view can leave out the analysis you are currently reading.
    payload["analysisId"] = _record(session, settings, payload, request)
    return payload
