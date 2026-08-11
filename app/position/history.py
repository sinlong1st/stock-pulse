"""How the exit advice on a holding has changed over time (spec §37).

The first thing that reads `position_exit_analyses`. The point is not accuracy —
that needs a scorer and matured horizons — but *evolution*:

    Aug 5   HOLD             $455
    Aug 7   HOLD WITH STOP   $468
    Aug 10  PARTIAL SELL     $492

That sequence is the feature's own credibility. A tool that quietly said
something different every day, with no way to see it had, would deserve less
trust than one whose changes of mind are on the record.

**Consecutive identical verdicts are collapsed.** Running the same analysis
three times in an afternoon is three rows in the table — correct for scoring,
noise in a history. A run is shown once, dated when the advice *first* became
that, with a count. Nothing is deleted: this is a read-time view over rows that
stay whole, because the stored data is what a future scorer depends on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.models import PositionExitAnalysisRow

logger = logging.getLogger("stockpulse.position.history")

# A sane ceiling for one holding's history; the app shows far fewer.
DEFAULT_LIMIT = 40
MAX_LIMIT = 200


@dataclass(frozen=True)
class HistoryEntry:
    """One verdict, possibly standing in for a run of identical ones."""

    id: int
    ticker: str
    action: str
    price: float | None
    unrealized_pnl: float | None
    hold_reward_risk: float | None
    provider: str | None
    # True when the rules moved the model's call — worth seeing in the timeline,
    # because "the AI said hold and was overruled" is a different event from
    # "the AI said trim".
    overridden: bool
    at: datetime
    # How many analyses this row stands for, including itself.
    times: int

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "action": self.action,
            "price": self.price,
            "unrealizedPnl": self.unrealized_pnl,
            "holdRewardRisk": self.hold_reward_risk,
            "provider": self.provider,
            "overridden": self.overridden,
            "at": self.at.isoformat(),
            "times": self.times,
        }


def prune(session, *, days: int, now: datetime | None = None) -> int:
    """Delete analyses older than `days`, returning how many went.

    Retention is what turns "grows forever" into a fixed ceiling: at a 30-day
    window this table settles at a couple of megabytes and stays there, however
    long the feature is used. That is the whole reason the full snapshot can be
    kept without thinking about it again.

    `days <= 0` keeps everything, which is the setting to use if a scorer ever
    becomes interesting — it would need history older than the window.

    Called on write rather than from a scheduled job on purpose: the scheduler
    can be switched off (and is, on every test boot), and a retention policy that
    silently stops applying is worse than none.
    """
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = session.execute(
        delete(PositionExitAnalysisRow).where(PositionExitAnalysisRow.created_at < cutoff)
    )
    return result.rowcount or 0


def _utc(value: datetime) -> datetime:
    """Re-attach UTC to a timestamp SQLite handed back naive.

    The column is `DateTime(timezone=True)` and every write is
    `datetime.now(UTC)`, but SQLite has no timezone type and returns a naive
    value. Without this the payload's `isoformat()` carries no offset, and a
    phone rendering it would place an analysis made at 2pm Pacific at 9pm.
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def collapse(rows: list[PositionExitAnalysisRow]) -> list[HistoryEntry]:
    """Collapse consecutive same-verdict rows, newest run first.

    `rows` must be **oldest first** — a run is defined by adjacency in time, and
    the entry keeps the *earliest* row of its run, because that is the moment the
    advice changed. The price shown is that moment's price for the same reason.
    """
    entries: list[HistoryEntry] = []
    for row in rows:
        if entries and entries[-1].action == row.action and entries[-1].ticker == row.ticker:
            last = entries[-1]
            entries[-1] = HistoryEntry(**{**last.__dict__, "times": last.times + 1})
            continue
        entries.append(
            HistoryEntry(
                id=row.id,
                ticker=row.ticker,
                action=row.action,
                price=row.price,
                unrealized_pnl=row.unrealized_pnl,
                hold_reward_risk=row.hold_reward_risk,
                provider=row.provider,
                overridden=bool(
                    row.ai_action and row.rules_final and row.ai_action != row.rules_final
                ),
                at=_utc(row.created_at),
                times=1,
            )
        )
    entries.reverse()  # newest change first, which is what a timeline reads as
    return entries


def list_history(
    session,
    *,
    ticker: str | None = None,
    position_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[HistoryEntry]:
    """Recent analyses, collapsed. Filter by ticker, by saved position, or neither.

    Filtering by ticker rather than position id by default: the same holding may
    have been analysed inline before it was ever saved, and those are still the
    same story about the same stock.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    stmt = select(PositionExitAnalysisRow)
    if ticker:
        stmt = stmt.where(PositionExitAnalysisRow.ticker == ticker.strip().upper())
    if position_id:
        stmt = stmt.where(PositionExitAnalysisRow.position_id == position_id)
    # Newest `limit` rows, then flipped: the window has to be taken from the
    # recent end, but collapsing runs needs them in chronological order.
    stmt = stmt.order_by(PositionExitAnalysisRow.created_at.desc()).limit(limit)
    rows = list(session.scalars(stmt))
    rows.reverse()
    return collapse(rows)
