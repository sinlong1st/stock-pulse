"""Scheduled job: score predictions whose horizon has passed (eval step D)."""

import logging

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.evaluation import EvalSummary, evaluate_predictions
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
