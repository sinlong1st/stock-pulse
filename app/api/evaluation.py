"""Shape the self-evaluation report for the mobile Evaluation screen (read-only)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.evaluation import SentimentStat, build_evaluation_report


def _stat(s: SentimentStat) -> dict:
    return {
        "accuracyPct": s.accuracy_pct,
        "hits": s.hits,
        "misses": s.misses,
        "total": s.total,
        "avgReturnPct": s.avg_return_pct,
    }


def build_evaluation(session: Session) -> dict:
    r = build_evaluation_report(session)
    return {
        "totalEvaluated": r.total_evaluated,
        "accuracyPct": r.accuracy_pct,
        "pending": r.pending,
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
