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
from app.briefing.memory import ThemeMemory
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
    memory: object = _UNSET,
) -> BriefingRun:
    """Run a briefing once and (optionally) deliver it to Telegram.

    ``always_send`` forces delivery even on a quiet window (on-demand and the
    anchor briefs); intraday callers pass ``always_send=False`` so an empty
    check-in stays silent. Rolling ``memory`` supplies PRIOR_THEMES for trend
    continuity and records this run's themes; pass ``None`` to disable it.
    ``analyst``/``notifier``/``retrieval``/``memory`` can be injected for tests.
    """
    settings = settings or get_settings()
    win = window_hours if window_hours is not None else window_for(trigger, settings)
    run = BriefingRun(trigger=trigger)

    if memory is _UNSET:
        memory = ThemeMemory(
            settings.briefing_memory_file, memory_hours=settings.briefing_memory_hours
        )

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

    # Trend continuity: feed recent themes unless the caller supplied their own.
    if prior_themes is None and memory is not None:
        prior_themes = memory.recent_theme_lines(retrieval.now)

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

    # Remember material themes so the next run can judge trend and avoid
    # re-announcing the same storyline as brand new.
    if memory is not None and result.has_material_update:
        memory.record(result, retrieval.now)

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


# --- scheduled triggers -----------------------------------------------------


async def run_morning_brief() -> BriefingRun:
    """08:30 PT: the full morning read. Always sends."""
    return await run_briefing(trigger="morning", always_send=True)


async def run_intraday_update() -> BriefingRun:
    """Every 2h 10:30–16:30 PT: a short check-in, gated on materiality."""
    return await run_briefing(trigger="intraday", always_send=False)


async def run_end_of_day_wrap() -> BriefingRun:
    """18:00 PT: how the day landed. Always sends."""
    return await run_briefing(trigger="wrap", always_send=True)


def parse_hhmm(value: str) -> tuple[int, int]:
    """Parse "HH:MM" into (hour, minute)."""
    hour, minute = value.strip().split(":")
    return int(hour), int(minute)


def intraday_hours(settings: Settings) -> list[int]:
    """Hours the intraday updates fire at (anchored after the morning brief).

    e.g. morning 08:30, every 2h, until 16:30 -> [10, 12, 14, 16].
    """
    start_h, _ = parse_hhmm(settings.briefing_morning_at)
    until_h, _ = parse_hhmm(settings.briefing_intraday_until)
    every = max(1, settings.briefing_intraday_every_hours)
    return list(range(start_h + every, until_h + 1, every))
