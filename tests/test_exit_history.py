"""How the exit advice on a holding changed over time (spec §37).

The contract these tests defend:

1. Repeating the same analysis is **collapsed for display**, never deleted —
   the stored rows are what a future scorer depends on.
2. A run is dated when the advice **first** became that, because the timeline is
   about when the thesis changed.
3. Newest change first, and one holding's history never bleeds into another's.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import PositionExitAnalysisRow
from app.position.history import MAX_LIMIT, collapse, list_history, prune


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


_T0 = datetime(2026, 8, 1, tzinfo=UTC)


def _add(session, *, action, day, price=100.0, ticker="WDC", ai=None, final=None):
    row = PositionExitAnalysisRow(
        ticker=ticker,
        shares=20.0,
        average_cost=90.0,
        price=price,
        action=action,
        ai_action=ai,
        rules_final=final,
        created_at=_T0 + timedelta(days=day),
    )
    session.add(row)
    session.commit()
    return row


# --- collapsing ------------------------------------------------------------


def test_the_thesis_timeline_reads_newest_change_first(session) -> None:
    """§37's own example: hold → hold-with-stop → partial-sell."""
    _add(session, action="hold", day=0, price=455.0)
    _add(session, action="hold-with-stop", day=2, price=468.0)
    _add(session, action="partial-sell", day=5, price=492.0)

    got = list_history(session, ticker="WDC")
    assert [e.action for e in got] == ["partial-sell", "hold-with-stop", "hold"]
    assert [e.price for e in got] == [492.0, 468.0, 455.0]


def test_repeating_the_same_analysis_collapses(session) -> None:
    """Three runs in an afternoon is three rows — correct for scoring, noise in
    a timeline."""
    for day in (0, 0, 0):
        _add(session, action="hold", day=day)

    got = list_history(session, ticker="WDC")
    assert len(got) == 1 and got[0].times == 3
    # The rows themselves are untouched: a scorer still sees all three.
    assert session.query(PositionExitAnalysisRow).count() == 3


def test_a_run_is_dated_when_the_advice_first_changed(session) -> None:
    """Not the latest repeat — the timeline is about when the thesis moved."""
    _add(session, action="hold", day=0, price=455.0)
    _add(session, action="hold", day=1, price=460.0)
    _add(session, action="hold", day=2, price=462.0)

    entry = list_history(session, ticker="WDC")[0]
    assert entry.at == _T0
    # SQLite has no timezone type and hands the value back naive; the app
    # would then render a 2pm Pacific analysis at 9pm.
    assert entry.at.tzinfo is not None
    assert entry.as_dict()["at"].endswith("+00:00")
    assert entry.price == 455.0
    assert entry.times == 3


def test_a_verdict_that_returns_starts_a_new_run(session) -> None:
    """hold → trim → hold is three events, not two: changing back is news."""
    _add(session, action="hold", day=0)
    _add(session, action="partial-sell", day=1)
    _add(session, action="hold", day=2)

    got = list_history(session, ticker="WDC")
    assert [e.action for e in got] == ["hold", "partial-sell", "hold"]
    assert all(e.times == 1 for e in got)


def test_an_overridden_call_is_marked(session) -> None:
    """"The AI said hold and was overruled" is a different event from "the AI
    said trim"."""
    _add(session, action="partial-sell", day=0, ai="hold", final="partial-sell")
    _add(session, action="hold", day=1, ai="hold", final="hold")

    got = list_history(session, ticker="WDC")
    assert got[0].overridden is False
    assert got[1].overridden is True


def test_collapse_on_nothing_is_empty() -> None:
    assert collapse([]) == []


# --- filtering and limits --------------------------------------------------


def test_one_holding_never_bleeds_into_another(session) -> None:
    _add(session, action="hold", day=0, ticker="WDC")
    _add(session, action="exit", day=1, ticker="NVDA")

    assert [e.ticker for e in list_history(session, ticker="WDC")] == ["WDC"]
    assert [e.ticker for e in list_history(session, ticker="nvda")] == ["NVDA"]


def test_no_filter_returns_everything(session) -> None:
    _add(session, action="hold", day=0, ticker="WDC")
    _add(session, action="exit", day=1, ticker="NVDA")
    assert len(list_history(session)) == 2


def test_history_can_be_scoped_to_a_saved_position(session) -> None:
    row = _add(session, action="hold", day=0)
    row.position_id = "p_abc"
    session.commit()
    _add(session, action="exit", day=1)  # same ticker, typed in rather than saved

    assert len(list_history(session, position_id="p_abc")) == 1
    assert len(list_history(session, ticker="WDC")) == 2


def test_the_window_is_taken_from_the_recent_end(session) -> None:
    """A limit must return the *latest* N analyses, not the first N — a
    truncated-from-the-wrong-end history would show ancient advice as current."""
    for day in range(10):
        _add(session, action=f"a{day}", day=day)

    got = list_history(session, ticker="WDC", limit=3)
    assert [e.action for e in got] == ["a9", "a8", "a7"]


@pytest.mark.parametrize("limit", [0, -5])
def test_a_nonsense_limit_still_returns_something(session, limit) -> None:
    _add(session, action="hold", day=0)
    assert len(list_history(session, ticker="WDC", limit=limit)) == 1


def test_the_limit_is_capped(session) -> None:
    assert list_history(session, ticker="WDC", limit=10_000) == []  # capped, not crashed
    assert MAX_LIMIT < 10_000


# --- retention -------------------------------------------------------------


def test_old_analyses_are_pruned(session) -> None:
    """Retention is what turns "grows forever" into a fixed ceiling."""
    _add(session, action="hold", day=0)  # Aug 1
    _add(session, action="exit", day=40)  # Sep 10

    removed = prune(session, days=30, now=_T0 + timedelta(days=41))
    session.commit()

    assert removed == 1
    assert [e.action for e in list_history(session)] == ["exit"]


def test_nothing_inside_the_window_is_touched(session) -> None:
    for day in range(5):
        _add(session, action=f"a{day}", day=day)

    assert prune(session, days=30, now=_T0 + timedelta(days=5)) == 0
    assert session.query(PositionExitAnalysisRow).count() == 5


@pytest.mark.parametrize("days", [0, -1])
def test_zero_days_keeps_everything(session, days) -> None:
    """The setting to use if a scorer ever becomes interesting — it would need
    history older than any sensible display window."""
    _add(session, action="hold", day=0)
    assert prune(session, days=days, now=_T0 + timedelta(days=9999)) == 0
    assert session.query(PositionExitAnalysisRow).count() == 1


def test_pruning_an_empty_table_is_fine(session) -> None:
    assert prune(session, days=30) == 0


def test_as_dict_is_camel_case_json(session) -> None:
    _add(session, action="hold", day=0)
    payload = list_history(session, ticker="WDC")[0].as_dict()
    assert set(payload) == {
        "id", "ticker", "action", "price", "unrealizedPnl", "holdRewardRisk",
        "provider", "overridden", "at", "times",
    }
    assert isinstance(payload["at"], str)
