"""Recording Predict-tab reads for later scoring (v2 custom strategies, step 1).

These rows share the `predictions` table with the news pipeline and are told
apart by `source` — so the tests here care most about the two kinds staying
separate while sharing one evaluation loop.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import PredictionRow
from app.db.repository import PredictionRepository
from app.evaluation import (
    LEAN_TO_SENTIMENT,
    build_evaluation_report,
    evaluate_predictions,
    record_prediction_read,
)
from app.prices import PriceClient, PriceSnapshot
from app.status import (
    OUTCOME_HIT,
    OUTCOME_MISS,
    PRED_EVALUATED,
    PRED_PENDING,
    PRED_SOURCE_NEWS,
    PRED_SOURCE_PREDICT,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _horizons(lean="bounce", confidence="medium"):
    return [
        {"horizon": "1w", "lean": lean, "confidence": confidence, "rationale": "r"},
        {"horizon": "1mo", "lean": lean, "confidence": confidence, "rationale": "r"},
        {"horizon": "3mo", "lean": lean, "confidence": confidence, "rationale": "r"},
    ]


class _Client(PriceClient):
    def __init__(self, price: float, price_time: datetime) -> None:
        self.price, self.price_time = price, price_time

    async def latest_price(self, ticker: str) -> float | None:
        return self.price

    async def change_today(self, ticker: str):  # pragma: no cover - unused
        return None

    async def snapshot(self, ticker: str):
        return PriceSnapshot(
            ticker=ticker, price=self.price, price_time=self.price_time, open=None, prev_close=None
        )


# --- recording -------------------------------------------------------------


def test_records_one_row_per_horizon_tagged_with_strategy(session) -> None:
    created = record_prediction_read(
        session,
        ticker="WDC",
        horizons=_horizons(),
        strategy_id="default",
        baseline_price=65.0,
    )
    session.commit()

    assert created == 3
    rows = session.query(PredictionRow).all()
    assert {r.horizon for r in rows} == {"1w", "1mo", "3mo"}
    assert all(r.source == PRED_SOURCE_PREDICT for r in rows)
    assert all(r.strategy_id == "default" for r in rows)
    assert all(r.sentiment == "BULLISH" for r in rows)  # bounce -> BULLISH
    assert all(r.confidence == "medium" for r in rows)
    assert all(r.baseline_price == 65.0 for r in rows)
    # No article for a forward-looking read.
    assert all(r.classification_id is None and r.article_id is None for r in rows)


@pytest.mark.parametrize(
    "lean,sentiment", [("bounce", "BULLISH"), ("dip", "BEARISH"), ("hold", "NEUTRAL")]
)
def test_lean_maps_to_the_scorers_sentiment(session, lean, sentiment) -> None:
    record_prediction_read(
        session, ticker="X", horizons=_horizons(lean), strategy_id="s", baseline_price=10.0
    )
    session.commit()
    assert {r.sentiment for r in session.query(PredictionRow).all()} == {sentiment}
    assert LEAN_TO_SENTIMENT[lean] == sentiment


def test_evaluate_after_uses_the_horizon_length(session) -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    record_prediction_read(
        session,
        ticker="X",
        horizons=_horizons(),
        strategy_id="s",
        baseline_price=10.0,
        now=now,
    )
    session.commit()
    by_horizon = {r.horizon: r.evaluate_after for r in session.query(PredictionRow).all()}
    assert by_horizon["1w"].replace(tzinfo=UTC) == now + timedelta(weeks=1)
    assert by_horizon["1mo"].replace(tzinfo=UTC) == now + timedelta(days=30)
    assert by_horizon["3mo"].replace(tzinfo=UTC) == now + timedelta(days=90)


def test_no_baseline_price_records_nothing(session) -> None:
    for bad in (None, 0.0, -5.0):
        assert (
            record_prediction_read(
                session, ticker="X", horizons=_horizons(), strategy_id="s", baseline_price=bad
            )
            == 0
        )
    assert session.query(PredictionRow).count() == 0


def test_unknown_lean_or_horizon_is_skipped(session) -> None:
    created = record_prediction_read(
        session,
        ticker="X",
        strategy_id="s",
        baseline_price=10.0,
        horizons=[
            {"horizon": "1w", "lean": "moon", "confidence": "high"},  # bad lean
            {"horizon": "1y", "lean": "bounce", "confidence": "high"},  # bad horizon
            {"horizon": "1mo", "lean": "dip", "confidence": "low"},  # good
        ],
    )
    session.commit()
    assert created == 1
    assert session.query(PredictionRow).one().horizon == "1mo"


# --- de-duplication --------------------------------------------------------


def test_repeat_read_within_the_window_does_not_stack_rows(session) -> None:
    """A language switch re-runs the prediction; that must not count twice."""
    record_prediction_read(
        session, ticker="WDC", horizons=_horizons(), strategy_id="default", baseline_price=65.0
    )
    session.commit()
    again = record_prediction_read(
        session, ticker="WDC", horizons=_horizons(), strategy_id="default", baseline_price=65.0
    )
    session.commit()

    assert again == 0
    assert session.query(PredictionRow).count() == 3


def test_dedupe_is_scoped_per_strategy(session) -> None:
    """Two strategies reading the same stock are two genuine data points."""
    record_prediction_read(
        session, ticker="WDC", horizons=_horizons(), strategy_id="default", baseline_price=65.0
    )
    mine = record_prediction_read(
        session, ticker="WDC", horizons=_horizons(), strategy_id="mine", baseline_price=65.0
    )
    session.commit()
    assert mine == 3
    assert session.query(PredictionRow).count() == 6


def test_dedupe_expires_after_the_window(session) -> None:
    old = datetime.now(tz=UTC) - timedelta(hours=5)
    record_prediction_read(
        session,
        ticker="WDC",
        horizons=_horizons(),
        strategy_id="default",
        baseline_price=65.0,
        now=old,
    )
    session.commit()
    again = record_prediction_read(
        session,
        ticker="WDC",
        horizons=_horizons(),
        strategy_id="default",
        baseline_price=65.0,
        dedupe_minutes=180,
    )
    session.commit()
    assert again == 3  # the earlier read is older than the window


# --- sharing the evaluation loop -------------------------------------------


async def test_predict_rows_are_scored_by_the_same_loop(session) -> None:
    past = datetime.now(tz=UTC) - timedelta(days=40)
    record_prediction_read(
        session,
        ticker="WDC",
        horizons=[{"horizon": "1w", "lean": "bounce", "confidence": "high"}],
        strategy_id="default",
        baseline_price=100.0,
        now=past,
    )
    session.commit()

    summary = await evaluate_predictions(
        session,
        price_client=_Client(110.0, datetime.now(tz=UTC)),  # +10%
        threshold_pct=0.5,
        max_move_pct=40.0,
    )

    assert summary.evaluated == 1 and summary.hits == 1
    row = session.query(PredictionRow).one()
    assert row.status == PRED_EVALUATED and row.outcome == OUTCOME_HIT
    assert row.strategy_id == "default"  # survives scoring, for later grouping


def test_predict_rows_stay_out_of_the_news_accuracy_screen(session) -> None:
    """The existing Evaluation screen reports on alert calls only."""
    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    common = dict(
        ticker="WDC",
        sentiment="BULLISH",
        horizon="1d",
        created_at=now,
        evaluate_after=now,
        baseline_price=100.0,
        baseline_at=now,
    )
    news = repo.create(source=PRED_SOURCE_NEWS, importance="HIGH", **common)
    predict = repo.create(source=PRED_SOURCE_PREDICT, strategy_id="default", **common)
    for row in (news, predict):
        repo.mark_evaluated(row, 110.0, 10.0, OUTCOME_HIT)
    session.commit()

    report = build_evaluation_report(session)
    assert report.total_evaluated == 1  # the news row only
    assert repo.count_by_status(PRED_EVALUATED) == 2  # both really are stored


# --- per-strategy accuracy -------------------------------------------------


def _scored(session, *, strategy_id: str, hits: int, misses: int, flats: int = 0) -> None:
    """Write already-evaluated Predict rows with a known hit/miss mix."""
    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    plan = [(OUTCOME_HIT, 5.0)] * hits + [(OUTCOME_MISS, -4.0)] * misses
    plan += [("FLAT", 0.1)] * flats
    for outcome, ret in plan:
        row = repo.create(
            source=PRED_SOURCE_PREDICT,
            ticker="WDC",
            sentiment="BULLISH",
            strategy_id=strategy_id,
            horizon="1w",
            created_at=now,
            evaluate_after=now,
            baseline_price=100.0,
            baseline_at=now,
        )
        repo.mark_evaluated(row, 100 + ret, ret, outcome)
    session.commit()


def test_accuracy_is_computed_per_strategy(session, tmp_path) -> None:
    from app.config import Settings
    from app.evaluation import build_strategy_accuracy

    settings = Settings(_env_file=None, strategies_file=str(tmp_path / "s.json"))
    _scored(session, strategy_id="default", hits=6, misses=4)
    _scored(session, strategy_id="s_mine", hits=9, misses=1)

    stats = {s.strategy_id: s for s in build_strategy_accuracy(session, settings)}
    assert stats["default"].accuracy_pct == 60.0
    assert stats["s_mine"].accuracy_pct == 90.0
    assert stats["default"].total == 10 and stats["s_mine"].total == 10


def test_flats_count_as_scored_but_not_against_accuracy(session, tmp_path) -> None:
    from app.config import Settings
    from app.evaluation import build_strategy_accuracy

    settings = Settings(_env_file=None, strategies_file=str(tmp_path / "s.json"))
    _scored(session, strategy_id="default", hits=5, misses=5, flats=4)

    stat = build_strategy_accuracy(session, settings)[0]
    assert stat.total == 14  # flats are shown in the sample size
    assert stat.accuracy_pct == 50.0  # but excluded from the ratio
    assert stat.flats == 4


def test_thin_samples_are_flagged_and_never_rank_first(session, tmp_path) -> None:
    """A 100% from two lucky calls must not crown itself the winner."""
    from app.config import Settings
    from app.evaluation import MIN_MEANINGFUL_CALLS, build_strategy_accuracy

    settings = Settings(_env_file=None, strategies_file=str(tmp_path / "s.json"))
    _scored(session, strategy_id="s_lucky", hits=2, misses=0)  # 100%, tiny
    _scored(session, strategy_id="default", hits=7, misses=5)  # 58%, solid

    stats = build_strategy_accuracy(session, settings)
    assert stats[0].strategy_id == "default"  # trustworthy row leads
    assert stats[0].enough_data is True
    assert stats[1].strategy_id == "s_lucky"
    assert stats[1].enough_data is False
    assert MIN_MEANINGFUL_CALLS > 2


def test_strategies_with_only_pending_calls_still_appear(session, tmp_path) -> None:
    from app.config import Settings
    from app.evaluation import build_strategy_accuracy

    settings = Settings(_env_file=None, strategies_file=str(tmp_path / "s.json"))
    record_prediction_read(
        session, ticker="WDC", horizons=_horizons(), strategy_id="s_new", baseline_price=65.0
    )
    session.commit()

    stat = build_strategy_accuracy(session, settings)[0]
    assert stat.strategy_id == "s_new"
    assert stat.total == 0 and stat.pending == 3
    assert stat.accuracy_pct is None and stat.enough_data is False


def test_news_rows_never_enter_the_strategy_comparison(session, tmp_path) -> None:
    from app.config import Settings
    from app.evaluation import build_strategy_accuracy

    settings = Settings(_env_file=None, strategies_file=str(tmp_path / "s.json"))
    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    row = repo.create(
        source=PRED_SOURCE_NEWS,
        classification_id=1,
        article_id=1,
        ticker="WDC",
        sentiment="BULLISH",
        importance="HIGH",
        horizon="1d",
        created_at=now,
        evaluate_after=now,
        baseline_price=100.0,
        baseline_at=now,
    )
    repo.mark_evaluated(row, 110.0, 10.0, OUTCOME_HIT)
    session.commit()

    assert build_strategy_accuracy(session, settings) == []


def test_archived_strategy_keeps_its_name_in_the_comparison(session, tmp_path) -> None:
    import app.prediction.store as store
    from app.config import Settings

    from app.evaluation import build_strategy_accuracy

    store._load.cache_clear()
    settings = Settings(
        _env_file=None,
        strategies_file=str(tmp_path / "s.json"),
        prefs_file=str(tmp_path / "p.json"),
    )
    mine = store.create_strategy(
        "Deep value", "Favour quality names far off their high.", settings=settings
    )
    _scored(session, strategy_id=mine.id, hits=6, misses=4)
    store.archive_strategy(mine.id, settings=settings)

    stat = build_strategy_accuracy(session, settings)[0]
    assert stat.name == "Deep value"  # history stays labelled
    store._load.cache_clear()


def test_news_recording_still_defaults_to_the_news_source(session) -> None:
    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    row = repo.create(
        classification_id=1,
        article_id=1,
        ticker="WDC",
        sentiment="BULLISH",
        importance="HIGH",
        horizon="1d",
        created_at=now,
        evaluate_after=now,
        baseline_price=100.0,
        baseline_at=now,
    )
    session.commit()
    assert row.source == PRED_SOURCE_NEWS
    assert row.status == PRED_PENDING
