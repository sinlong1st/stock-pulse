"""Self-evaluation: record AI predictions with a baseline price.

Step C of the evaluation plan. When an article is classified with a
directional sentiment and watchlist tickers, we snapshot the ticker's
price now (the baseline) and schedule it for scoring after each horizon.
Scoring the outcome against the price at the horizon is step D.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.repository import PredictionRepository
from app.models.classification import ClassificationResult
from app.prices import PriceClient
from app.status import OUTCOME_FLAT, OUTCOME_HIT, OUTCOME_MISS

logger = logging.getLogger("stockpulse.evaluation")


def parse_horizon(horizon: str) -> timedelta:
    """Parse a horizon like '1h' or '2d' into a timedelta."""
    h = horizon.strip().lower()
    if not h or not h[:-1].isdigit():
        raise ValueError(f"Invalid horizon: {horizon!r}")
    amount, unit = int(h[:-1]), h[-1]
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise ValueError(f"Invalid horizon unit in {horizon!r} (use 'h' or 'd')")


def horizons_from_settings(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    return [h.strip() for h in settings.evaluation_horizons.split(",") if h.strip()]


def _is_sane_price(price: float | None) -> bool:
    """Basic guard against missing/garbage baseline prices."""
    return price is not None and price > 0


def score_outcome(sentiment: str, return_pct: float, threshold_pct: float) -> str:
    """Score a prediction against the realized return.

    Moves within ±`threshold_pct` count as FLAT (the tolerance band), so a
    small dip doesn't count as "went down" against a bullish call.
    """
    if return_pct > threshold_pct:
        direction = "UP"
    elif return_pct < -threshold_pct:
        direction = "DOWN"
    else:
        direction = "FLAT"

    if direction == "FLAT":
        # A NEUTRAL call is right when nothing much happens; a directional
        # call that barely moved is neither a hit nor a miss.
        return OUTCOME_HIT if sentiment == "NEUTRAL" else OUTCOME_FLAT
    if sentiment == "BULLISH":
        return OUTCOME_HIT if direction == "UP" else OUTCOME_MISS
    if sentiment == "BEARISH":
        return OUTCOME_HIT if direction == "DOWN" else OUTCOME_MISS
    return OUTCOME_MISS  # NEUTRAL predicted but it moved


@dataclass
class EvalSummary:
    evaluated: int = 0
    hits: int = 0
    misses: int = 0
    flats: int = 0
    skipped: int = 0


async def evaluate_predictions(
    session: Session,
    *,
    price_client: PriceClient,
    threshold_pct: float,
    max_move_pct: float,
    limit: int = 200,
    now: datetime | None = None,
) -> EvalSummary:
    """Score predictions whose horizon has passed.

    Fetches the current price, computes the return vs the baseline, and
    records HIT/MISS/FLAT. Predictions with missing prices or an
    implausibly large move (likely bad free-feed data) are marked SKIPPED
    so they don't pollute the stats.
    """
    repo = PredictionRepository(session)
    now = now or datetime.now(tz=UTC)
    summary = EvalSummary()

    for prediction in repo.list_due(now, limit=limit):
        try:
            price = await price_client.latest_price(prediction.ticker)
        except Exception:
            logger.debug("Horizon price lookup failed for %s", prediction.ticker, exc_info=True)
            price = None

        if not price or price <= 0 or not prediction.baseline_price:
            repo.mark_skipped(prediction)
            summary.skipped += 1
            continue

        return_pct = (price - prediction.baseline_price) / prediction.baseline_price * 100
        if abs(return_pct) > max_move_pct:  # implausible → likely bad data
            logger.warning(
                "Skipping %s prediction: implausible move %.1f%% (baseline=%.2f now=%.2f)",
                prediction.ticker,
                return_pct,
                prediction.baseline_price,
                price,
            )
            repo.mark_skipped(prediction)
            summary.skipped += 1
            continue

        outcome = score_outcome(prediction.sentiment, return_pct, threshold_pct)
        repo.mark_evaluated(prediction, price, return_pct, outcome)
        summary.evaluated += 1
        if outcome == OUTCOME_HIT:
            summary.hits += 1
        elif outcome == OUTCOME_MISS:
            summary.misses += 1
        else:
            summary.flats += 1

    session.commit()
    return summary


async def record_predictions(
    session: Session,
    *,
    classification_id: int,
    article_id: int,
    result: ClassificationResult,
    price_client: PriceClient,
    horizons: list[str],
) -> int:
    """Record predictions (one per ticker × horizon) with baseline prices.

    Skips tickers with no/invalid price data. Returns the number created.
    """
    if not result.related_tickers or not horizons:
        return 0

    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    created = 0

    for ticker in result.related_tickers:
        try:
            baseline = await price_client.latest_price(ticker)
        except Exception:
            logger.debug("Baseline price lookup failed for %s", ticker, exc_info=True)
            baseline = None
        if not _is_sane_price(baseline):
            continue  # can't evaluate without a valid baseline
        for horizon in horizons:
            try:
                delta = parse_horizon(horizon)
            except ValueError:
                logger.warning("Skipping invalid evaluation horizon %r", horizon)
                continue
            repo.create(
                classification_id=classification_id,
                article_id=article_id,
                ticker=ticker,
                sentiment=result.sentiment,
                importance=result.importance,
                horizon=horizon,
                created_at=now,
                evaluate_after=now + delta,
                baseline_price=baseline,
                baseline_at=now,
            )
            created += 1

    return created
