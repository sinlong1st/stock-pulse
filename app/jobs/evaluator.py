"""Scheduled job: score predictions whose horizon has passed (eval step D)."""

import logging

from app.alerts import NotifierError, build_telegram_notifier
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.evaluation import (
    EvalSummary,
    build_evaluation_digest,
    build_evaluation_report,
    evaluate_predictions,
)
from app.prefs import resolve_language
from app.prices import maybe_eval_price_client

logger = logging.getLogger("stockpulse.jobs.evaluator")

_UNSET = object()


async def run_evaluation(
    *,
    session_factory=SessionLocal,
    settings: Settings | None = None,
    price_client: object = _UNSET,
) -> EvalSummary:
    """Score due predictions. No-op if evaluation is disabled or unconfigured."""
    settings = settings or get_settings()
    client = maybe_eval_price_client(settings) if price_client is _UNSET else price_client
    if client is None:
        return EvalSummary()

    with session_factory() as session:
        summary = await evaluate_predictions(
            session,
            price_client=client,
            threshold_pct=settings.evaluation_move_threshold_pct,
            max_move_pct=settings.evaluation_max_move_pct,
        )

    logger.info(
        "Evaluation run -- evaluated=%d hits=%d misses=%d flats=%d skipped=%d",
        summary.evaluated,
        summary.hits,
        summary.misses,
        summary.flats,
        summary.skipped,
    )
    return summary


async def run_daily_digest(
    *,
    session_factory=SessionLocal,
    settings: Settings | None = None,
    notifier: object = _UNSET,
) -> bool:
    """Send the self-evaluation summary to Telegram. Returns True if sent."""
    settings = settings or get_settings()
    if notifier is _UNSET:
        try:
            notifier = build_telegram_notifier(settings)
        except NotifierError:
            logger.warning("Digest enabled but Telegram not configured; skipping.")
            return False

    with session_factory() as session:
        report = build_evaluation_report(session)
    text = build_evaluation_digest(report, resolve_language(settings))
    try:
        await notifier.send(text)
    except NotifierError as exc:
        logger.warning("Failed to send evaluation digest: %s", exc)
        return False
    logger.info("Sent evaluation digest.")
    return True
