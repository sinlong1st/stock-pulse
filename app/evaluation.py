"""Self-evaluation: record AI predictions with a baseline price.

Step C of the evaluation plan. When an article is classified with a
directional sentiment and watchlist tickers, we snapshot the ticker's
price now (the baseline) and schedule it for scoring after each horizon.
Scoring the outcome against the price at the horizon is step D.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.repository import PredictionRepository
from app.models.classification import ClassificationResult
from app.prices import PriceClient
from app.status import (
    OUTCOME_FLAT,
    OUTCOME_HIT,
    OUTCOME_MISS,
    PRED_PENDING,
    PRED_SOURCE_NEWS,
    PRED_SOURCE_PREDICT,
)

logger = logging.getLogger("stockpulse.evaluation")


# A month is approximated as 30 days — timedelta has no calendar months, and the
# scorer already defers when the market is shut on the deadline, so a couple of
# days either way changes nothing.
_HORIZON_UNITS = {
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "mo": timedelta(days=30),
}
_HORIZON_RE = re.compile(r"(\d+)(mo|[hdw])")


def parse_horizon(horizon: str) -> timedelta:
    """Parse a horizon like '1h', '2d', '1w' or '3mo' into a timedelta.

    The news pipeline uses hours/days; the Predict tab uses weeks/months.
    """
    match = _HORIZON_RE.fullmatch(horizon.strip().lower())
    if not match:
        raise ValueError(f"Invalid horizon: {horizon!r} (use e.g. 1h, 2d, 1w, 3mo)")
    return int(match.group(1)) * _HORIZON_UNITS[match.group(2)]


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
    deferred: int = 0  # market closed at the horizon — retry on the next trading day


def _accuracy(hits: int, misses: int) -> float | None:
    """Directional accuracy = hits / (hits + misses); FLATs excluded."""
    decided = hits + misses
    return (hits / decided * 100) if decided else None


@dataclass
class SentimentStat:
    label: str
    total: int
    hits: int
    misses: int
    flats: int
    accuracy_pct: float | None
    avg_return_pct: float | None


@dataclass
class ImportanceStat:
    importance: str
    total: int
    accuracy_pct: float | None


@dataclass
class RecentItem:
    ticker: str
    sentiment: str
    horizon: str
    return_pct: float | None
    outcome: str


@dataclass
class EvaluationReport:
    total_evaluated: int
    hits: int
    misses: int
    flats: int
    accuracy_pct: float | None
    bullish: SentimentStat
    bearish: SentimentStat
    by_importance: list[ImportanceStat]
    recent: list[RecentItem]
    pending: int


def build_evaluation_digest(report: "EvaluationReport", language: str = "English") -> str:
    """Short text summary of the evaluation, for a Telegram digest."""
    vi = language.strip().lower() == "vietnamese"

    def pct(v: float | None) -> str:
        return f"{v:.0f}%" if v is not None else "—"

    def signed(v: float | None) -> str:
        return f"{v:+.1f}%" if v is not None else "—"

    if report.total_evaluated == 0:
        return (
            "📊 StockPulse — chưa đủ dữ liệu đánh giá."
            if vi
            else "📊 StockPulse — not enough evaluation data yet."
        )

    b, r = report.bullish, report.bearish
    if vi:
        return "\n".join(
            [
                "📊 StockPulse — Tự đánh giá",
                "",
                f"Đã đánh giá: {report.total_evaluated} dự đoán",
                f"🟢 Tin tốt: {pct(b.accuracy_pct)} đúng ({b.hits}/{b.hits + b.misses}) · LN TB {signed(b.avg_return_pct)}",
                f"🟠 Tin xấu: {pct(r.accuracy_pct)} đúng ({r.hits}/{r.hits + r.misses}) · LN TB {signed(r.avg_return_pct)}",
                f"Tổng chính xác: {pct(report.accuracy_pct)}",
                "",
                "⚠️ Mẫu nhỏ, chỉ tham khảo — không phải lời khuyên đầu tư.",
            ]
        )
    return "\n".join(
        [
            "📊 StockPulse — Self-evaluation",
            "",
            f"Evaluated: {report.total_evaluated} predictions",
            f"🟢 Bullish: {pct(b.accuracy_pct)} correct ({b.hits}/{b.hits + b.misses}) · avg {signed(b.avg_return_pct)}",
            f"🟠 Bearish: {pct(r.accuracy_pct)} correct ({r.hits}/{r.hits + r.misses}) · avg {signed(r.avg_return_pct)}",
            f"Overall accuracy: {pct(report.accuracy_pct)}",
            "",
            "⚠️ Small sample — for reference only, not investment advice.",
        ]
    )


def _sentiment_stat(rows: list, label: str, sentiment: str) -> SentimentStat:
    subset = [r for r in rows if r.sentiment == sentiment]
    hits = sum(1 for r in subset if r.outcome == OUTCOME_HIT)
    misses = sum(1 for r in subset if r.outcome == OUTCOME_MISS)
    flats = sum(1 for r in subset if r.outcome == OUTCOME_FLAT)
    returns = [r.return_pct for r in subset if r.return_pct is not None]
    avg_return = sum(returns) / len(returns) if returns else None
    return SentimentStat(
        label=label,
        total=len(subset),
        hits=hits,
        misses=misses,
        flats=flats,
        accuracy_pct=_accuracy(hits, misses),
        avg_return_pct=avg_return,
    )


def build_evaluation_report(session: Session, *, recent_limit: int = 15) -> EvaluationReport:
    """Aggregate scored predictions into an accuracy report."""
    repo = PredictionRepository(session)
    # News rows only: this screen reports on alert calls, and it breaks results
    # down by importance, which a Predict-tab read doesn't have.
    rows = repo.list_evaluated(limit=2000, source=PRED_SOURCE_NEWS)

    hits = sum(1 for r in rows if r.outcome == OUTCOME_HIT)
    misses = sum(1 for r in rows if r.outcome == OUTCOME_MISS)
    flats = sum(1 for r in rows if r.outcome == OUTCOME_FLAT)

    importances: dict[str, list] = {}
    for r in rows:
        importances.setdefault(r.importance, []).append(r)
    by_importance = [
        ImportanceStat(
            importance=imp,
            total=len(items),
            accuracy_pct=_accuracy(
                sum(1 for r in items if r.outcome == OUTCOME_HIT),
                sum(1 for r in items if r.outcome == OUTCOME_MISS),
            ),
        )
        for imp, items in sorted(
            importances.items(),
            key=lambda kv: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(kv[0], 9),
        )
    ]

    recent = [
        RecentItem(
            ticker=r.ticker,
            sentiment=r.sentiment,
            horizon=r.horizon,
            return_pct=r.return_pct,
            outcome=r.outcome or OUTCOME_FLAT,
        )
        for r in rows[:recent_limit]
    ]

    return EvaluationReport(
        total_evaluated=len(rows),
        hits=hits,
        misses=misses,
        flats=flats,
        accuracy_pct=_accuracy(hits, misses),
        bullish=_sentiment_stat(rows, "Bullish", "BULLISH"),
        bearish=_sentiment_stat(rows, "Bearish", "BEARISH"),
        by_importance=by_importance,
        recent=recent,
        pending=repo.count_by_status(PRED_PENDING),
    )


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def evaluate_predictions(
    session: Session,
    *,
    price_client: PriceClient,
    threshold_pct: float,
    max_move_pct: float,
    limit: int = 200,
    now: datetime | None = None,
    stale_grace_days: int = 4,
) -> EvalSummary:
    """Score predictions whose horizon has passed.

    Fetches the price, computes the return vs the baseline, and records
    HIT/MISS/FLAT. Two guards keep the stats honest:

    - **Market closed:** if the last trade printed at/before the horizon
      deadline (weekend, holiday, after hours), there is no real post-horizon
      price yet — the prediction is left PENDING and retried on the next
      trading day (up to `stale_grace_days`, after which it's skipped).
    - **Bad data:** missing prices or an implausibly large move are SKIPPED.
    """
    repo = PredictionRepository(session)
    now = now or datetime.now(tz=UTC)
    summary = EvalSummary()

    for prediction in repo.list_due(now, limit=limit):
        price: float | None = None
        price_time: datetime | None = None
        try:
            snap = await price_client.snapshot(prediction.ticker)
            if snap is not None:
                price, price_time = snap.price, _as_utc(snap.price_time)
            else:  # client without snapshot support — fall back, no freshness check
                price = await price_client.latest_price(prediction.ticker)
        except Exception:
            logger.debug("Horizon price lookup failed for %s", prediction.ticker, exc_info=True)

        # Market closed at the horizon: the newest trade is not after the
        # deadline. Defer (retry later) unless we've waited past the grace.
        deadline = _as_utc(prediction.evaluate_after)
        overdue = now - deadline if deadline else timedelta(0)
        if price_time is not None and deadline is not None and price_time <= deadline:
            if overdue <= timedelta(days=stale_grace_days):
                summary.deferred += 1
                continue
            # Waited long enough with no fresh trade (e.g. delisted) — skip.
            repo.mark_skipped(prediction)
            summary.skipped += 1
            continue

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
    watchlist: set[str],
) -> int:
    """Record predictions (one per ticker × horizon) with baseline prices.

    Only tickers in `watchlist` are recorded — the AI often names extra,
    off-watchlist tickers, and evaluating those would waste price lookups
    and pollute the accuracy stats. Tickers with no/invalid price data are
    skipped. Returns the number created.
    """
    tickers = [t for t in result.related_tickers if t in watchlist]
    if not tickers or not horizons:
        return 0

    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    created = 0

    for ticker in tickers:
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
                source=PRED_SOURCE_NEWS,
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


# The Predict tab speaks in leans; the scorer speaks in sentiment. Same three
# directions, so one mapping lets both kinds of prediction share a scorer.
LEAN_TO_SENTIMENT = {"bounce": "BULLISH", "dip": "BEARISH", "hold": "NEUTRAL"}


def record_prediction_read(
    session: Session,
    *,
    ticker: str,
    horizons: list[dict],
    strategy_id: str,
    baseline_price: float | None,
    dedupe_minutes: float = 180.0,
    now: datetime | None = None,
) -> int:
    """Record a Predict-tab read so it can be scored later, per horizon.

    `horizons` are the AI's per-horizon entries (``horizon``/``lean``/
    ``confidence``). Tagging each row with `strategy_id` is what later makes
    "your strategy vs ours" measurable.

    Returns the number of rows created. Never raises — a recording failure must
    not cost the user the prediction they asked for.
    """
    if not _is_sane_price(baseline_price) or not horizons:
        return 0

    repo = PredictionRepository(session)
    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(minutes=dedupe_minutes)
    created = 0

    for entry in horizons:
        label = str(entry.get("horizon") or "").strip()
        lean = str(entry.get("lean") or "").strip().lower()
        sentiment = LEAN_TO_SENTIMENT.get(lean)
        if not label or sentiment is None:
            continue
        try:
            delta = parse_horizon(label)
        except ValueError:
            logger.warning("Skipping unparsable prediction horizon %r", label)
            continue
        if repo.has_recent_pending(
            ticker=ticker, horizon=label, strategy_id=strategy_id, since=cutoff
        ):
            continue  # same call already awaiting evaluation
        repo.create(
            source=PRED_SOURCE_PREDICT,
            ticker=ticker,
            sentiment=sentiment,
            strategy_id=strategy_id,
            confidence=str(entry.get("confidence") or "").strip().lower() or None,
            horizon=label,
            created_at=now,
            evaluate_after=now + delta,
            baseline_price=float(baseline_price),
            baseline_at=now,
        )
        created += 1

    return created
