"""Shape the self-evaluation report for the mobile Evaluation screen (read-only)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.evaluation import (
    MIN_MEANINGFUL_CALLS,
    SentimentStat,
    build_evaluation_report,
    build_strategy_accuracy,
)


def _stat(s: SentimentStat) -> dict:
    return {
        "accuracyPct": s.accuracy_pct,
        "hits": s.hits,
        "misses": s.misses,
        "total": s.total,
        "avgReturnPct": s.avg_return_pct,
    }


def build_evaluation(session: Session, settings: Settings | None = None) -> dict:
    r = build_evaluation_report(session)
    strategies = build_strategy_accuracy(session, settings)
    return {
        "totalEvaluated": r.total_evaluated,
        "accuracyPct": r.accuracy_pct,
        "pending": r.pending,
        # Per-strategy comparison of Predict-tab calls ("yours vs ours").
        "strategies": [
            {
                "id": s.strategy_id,
                "name": s.name,
                "builtin": s.builtin,
                "total": s.total,
                "hits": s.hits,
                "misses": s.misses,
                "flats": s.flats,
                "accuracyPct": s.accuracy_pct,
                "avgReturnPct": s.avg_return_pct,
                "pending": s.pending,
                "enoughData": s.enough_data,
            }
            for s in strategies
        ],
        "minMeaningfulCalls": MIN_MEANINGFUL_CALLS,
        "bullish": _stat(r.bullish),
        "bearish": _stat(r.bearish),
        "recent": [
            {
                "ticker": i.ticker,
                "sentiment": i.sentiment,
                "horizon": i.horizon,
                "returnPct": i.return_pct,
                "outcome": i.outcome,
            }
            for i in r.recent
        ],
    }
