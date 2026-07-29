"""The market-briefing job (Briefing plan): retrieve → analyze → deliver.

One function powers every trigger — the on-demand `/report`, the morning
brief, the every-2h intraday updates, and the end-of-day wrap. They differ
only in the look-back window and whether they always send:

- **Anchor briefs** (morning, wrap) and **on-demand** always send — a quiet
  window just yields a short "backdrop holds" message.
- **Intraday updates** are gated on materiality (verbosity, not suppression is
  the plan, but a truly empty check-in stays quiet), so they don't spam.

External services are injectable so tests never touch the network.
"""

import logging
from dataclasses import dataclass

from app.alerts import NotifierError, build_telegram_notifier
from app.briefing.analyst import AnalystError, MarketAnalyst, build_analyst
from app.briefing.models import BriefingResult
from app.briefing.render import render_briefing
from app.briefing.retrieval import RetrievalResult, retrieve_fresh_news
from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.jobs.briefing")

_UNSET = object()


@dataclass
class BriefingRun:
    """Summary of one briefing run."""

    trigger: str
    collected: int = 0
    fresh: int = 0
    unverified: int = 0
    has_material_update: bool = False
    urgency: str = "routine"
    sent: bool = False
    skipped_reason: str | None = None
    text: str | None = None
    result: BriefingResult | None = None


def window_for(trigger: str, settings: Settings) -> float:
    """Look-back window (hours) for a trigger — see plan §3."""
    if trigger == "morning":
        return settings.briefing_morning_window_hours
    if trigger == "intraday":
        return settings.briefing_intraday_window_hours
    if trigger == "wrap":
        # The whole trading day; the wide morning window comfortably covers it.
        return settings.briefing_morning_window_hours
    return settings.briefing_ondemand_window_hours  # on-demand /report


async def run_briefing(
    *,
    trigger: str = "report",
    window_hours: float | None = None,
    always_send: bool = True,
    prior_themes: list[str] | None = None,
    deliver: bool = True,
    settings: Settings | None = None,
    analyst: object = _UNSET,
    notifier: object = _UNSET,
    retrieval: RetrievalResult | None = None,
) -> BriefingRun:
    """Run a briefing once and (optionally) deliver it to Telegram.

    ``always_send`` forces delivery even on a quiet window (on-demand and the
    anchor briefs); intraday callers pass ``always_send=False`` so an empty
    check-in stays silent. ``analyst``/``notifier``/``retrieval`` can be
    injected for tests.
    """
    settings = settings or get_settings()
    win = window_hours if window_hours is not None else window_for(trigger, settings)
    run = BriefingRun(trigger=trigger)

    # 1. Analyst (needs an OpenAI key). Missing key => nothing to do.
    if analyst is _UNSET:
        try:
            analyst = build_analyst(settings)
        except AnalystError:
            logger.warning("Briefing skipped: OPENAI_API_KEY not set.")
            run.skipped_reason = "no OpenAI key"
            return run
    assert isinstance(analyst, MarketAnalyst) or analyst is not None

    # 2. Retrieve fresh news (unless injected).
    if retrieval is None:
        retrieval = await retrieve_fresh_news(window_hours=win, settings=settings)
    run.collected = retrieval.collected
    run.fresh = len(retrieval.fresh)
    run.unverified = len(retrieval.unverified)

    # 3. Analyze.
    try:
        result = await analyst.analyze(retrieval, prior_themes=prior_themes)
    except AnalystError as exc:
        logger.warning("Briefing analysis failed: %s", exc)
        run.skipped_reason = f"analysis failed: {exc}"
        return run
    run.result = result
    run.has_material_update = result.has_material_update
    run.urgency = result.urgency

    # 4. Decide whether to send.
    should_send = always_send or result.has_material_update
    if not should_send:
        run.skipped_reason = "no material update"
        logger.info("Briefing [%s] -- quiet window, nothing sent.", trigger)
        return run

    run.text = render_briefing(result, language=settings.output_language, trigger=trigger)

    # 5. Deliver.
    if not deliver:
        return run
    if notifier is _UNSET:
        try:
            notifier = build_telegram_notifier(settings)
        except NotifierError:
            logger.warning("Briefing built but Telegram not configured; not sent.")
            run.skipped_reason = "Telegram not configured"
            return run
    try:
        await notifier.send(run.text)
        run.sent = True
    except NotifierError as exc:
        logger.warning("Failed to send briefing: %s", exc)
        run.skipped_reason = f"send failed: {exc}"
        return run

    logger.info(
        "Briefing [%s] -- collected=%d fresh=%d material=%s urgency=%s sent=%s",
        trigger,
        run.collected,
        run.fresh,
        run.has_material_update,
        run.urgency,
        run.sent,
    )
    return run
