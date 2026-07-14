"""Self-evaluation: record AI predictions with a baseline price.

Step C of the evaluation plan. When an article is classified with a
directional sentiment and watchlist tickers, we snapshot the ticker's
price now (the baseline) and schedule it for scoring after each horizon.
Scoring the outcome against the price at the horizon is step D.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.repository import PredictionRepository
from app.models.classification import ClassificationResult
from app.prices import PriceClient

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
