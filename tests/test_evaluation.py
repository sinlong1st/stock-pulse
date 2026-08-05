"""Tests for prediction recording (Eval plan, step C)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.repository import (
    ArticleRepository,
    ClassificationRepository,
    PredictionRepository,
)
from app.evaluation import (
    build_evaluation_digest,
    build_evaluation_report,
    evaluate_predictions,
    parse_horizon,
    record_predictions,
    score_outcome,
)
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.prices import PriceClient
from app.status import (
    OUTCOME_FLAT,
    OUTCOME_HIT,
    OUTCOME_MISS,
    PRED_EVALUATED,
    PRED_PENDING,
    PRED_SKIPPED,
)


class _FakePriceClient(PriceClient):
    def __init__(self, prices: dict[str, float | None]) -> None:
        self._prices = prices

    async def latest_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    async def change_today(self, ticker: str):  # pragma: no cover - unused here
        return None


class _SnapshotClient(PriceClient):
    """A client whose snapshot carries a controllable last-trade time."""

    def __init__(self, price: float, price_time: datetime) -> None:
        self.price = price
        self.price_time = price_time

    async def latest_price(self, ticker: str) -> float | None:
        return self.price

    async def change_today(self, ticker: str):  # pragma: no cover - unused here
        return None

    async def snapshot(self, ticker: str):
        from app.prices import PriceSnapshot

        return PriceSnapshot(
            ticker=ticker, price=self.price, price_time=self.price_time, open=None, prev_close=None
        )


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def test_parse_horizon() -> None:
    assert parse_horizon("1h") == timedelta(hours=1)
    assert parse_horizon("2d") == timedelta(days=2)
    # Weeks/months exist for the Predict tab's 1w,1mo,3mo horizons.
    assert parse_horizon("5w") == timedelta(weeks=5)
    assert parse_horizon("1mo") == timedelta(days=30)
    assert parse_horizon("3MO") == timedelta(days=90)  # case-insensitive
    for bad in ("", "d", "1y", "mo", "1m", "abc", "1.5d"):
        with pytest.raises(ValueError):
            parse_horizon(bad)


def _classification(tickers: list[str]) -> ClassificationResult:
    return ClassificationResult(
        is_market_relevant=True,
        importance="HIGH",
        category="TICKER",
        sentiment="BULLISH",
        related_tickers=tickers,
        summary="s",
        why_it_matters="w",
        should_alert=True,
    )


def _seed_classification(session, tickers: list[str]) -> tuple[int, int]:
    uid = uuid4().hex
    article = ArticleRepository(session).add(
        NewsArticle(
            source="Test",
            title="t",
            url=f"https://e.com/{uid}",
            collected_at=datetime.now(tz=UTC),
            content_hash=uid,
        )
    )
    session.flush()
    row = ClassificationRepository(session).add(article.id, _classification(tickers))
    session.flush()
    return row.id, article.id


WATCHLIST = {"NVDA", "MU", "MSFT", "SPCX"}


async def test_records_one_prediction_per_ticker_and_horizon(session) -> None:
    class_id, article_id = _seed_classification(session, ["NVDA", "MU"])
    client = _FakePriceClient({"NVDA": 200.0, "MU": 100.0})

    created = await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["NVDA", "MU"]),
        price_client=client,
        horizons=["1h", "1d"],
        watchlist=WATCHLIST,
    )
    session.commit()

    assert created == 4  # 2 tickers × 2 horizons
    repo = PredictionRepository(session)
    assert repo.count() == 4
    assert repo.count_by_status(PRED_PENDING) == 4


async def test_defers_scoring_when_market_closed_then_scores(session) -> None:
    """Weekend/closed market: score deferred until a fresh post-horizon trade."""
    class_id, article_id = _seed_classification(session, ["NVDA"])
    await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["NVDA"]),
        price_client=_FakePriceClient({"NVDA": 100.0}),  # baseline 100
        horizons=["1d"],
        watchlist=WATCHLIST,
    )
    session.commit()

    repo = PredictionRepository(session)
    pred = repo.list_due(datetime.now(tz=UTC) + timedelta(days=9), limit=10)[0]
    deadline = pred.evaluate_after
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)

    # 1) Due, but the last trade is BEFORE the deadline (market closed) → defer.
    stale = _SnapshotClient(price=110.0, price_time=deadline - timedelta(hours=2))
    s1 = await evaluate_predictions(
        session, price_client=stale, threshold_pct=0.5, max_move_pct=40.0,
        now=deadline + timedelta(hours=1),
    )
    assert s1.deferred == 1 and s1.evaluated == 0
    assert repo.count_by_status(PRED_PENDING) == 1  # still pending

    # 2) A real trade prints after the deadline → now it scores (+10% → HIT).
    fresh = _SnapshotClient(price=110.0, price_time=deadline + timedelta(minutes=30))
    s2 = await evaluate_predictions(
        session, price_client=fresh, threshold_pct=0.5, max_move_pct=40.0,
        now=deadline + timedelta(hours=1),
    )
    assert s2.evaluated == 1 and s2.hits == 1
    assert repo.count_by_status(PRED_EVALUATED) == 1


async def test_only_watchlist_tickers_are_recorded(session) -> None:
    # The AI named NVDA (watchlist) and VZ (not) — only NVDA should count.
    class_id, article_id = _seed_classification(session, ["NVDA", "VZ"])
    client = _FakePriceClient({"NVDA": 200.0, "VZ": 40.0})

    created = await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["NVDA", "VZ"]),
        price_client=client,
        horizons=["1d"],
        watchlist=WATCHLIST,
    )
    session.commit()

    assert created == 1  # VZ dropped (off-watchlist)
    assert PredictionRepository(session).count() == 1


async def test_skips_ticker_without_valid_price(session) -> None:
    class_id, article_id = _seed_classification(session, ["NVDA", "SPCX"])
    client = _FakePriceClient({"NVDA": 200.0, "SPCX": None})  # SPCX no data

    created = await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["NVDA", "SPCX"]),
        price_client=client,
        horizons=["1d"],
        watchlist=WATCHLIST,
    )
    session.commit()

    assert created == 1  # only NVDA
    assert PredictionRepository(session).count() == 1


async def test_no_tickers_records_nothing(session) -> None:
    class_id, article_id = _seed_classification(session, [])
    created = await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification([]),
        price_client=_FakePriceClient({}),
        horizons=["1d"],
        watchlist=WATCHLIST,
    )
    assert created == 0


# --- scoring (step D) -------------------------------------------------------


def test_score_outcome_with_tolerance_band() -> None:
    t = 0.5  # ±0.5% counts as flat
    # Bullish: up = hit, real down = miss, small dip within tolerance = flat.
    assert score_outcome("BULLISH", 2.0, t) == OUTCOME_HIT
    assert score_outcome("BULLISH", -2.0, t) == OUTCOME_MISS
    assert score_outcome("BULLISH", -0.4, t) == OUTCOME_FLAT  # a -0.4% dip is tolerated
    # Bearish: down = hit, up = miss.
    assert score_outcome("BEARISH", -2.0, t) == OUTCOME_HIT
    assert score_outcome("BEARISH", 2.0, t) == OUTCOME_MISS
    # Neutral: flat = hit, any real move = miss.
    assert score_outcome("NEUTRAL", 0.2, t) == OUTCOME_HIT
    assert score_outcome("NEUTRAL", 3.0, t) == OUTCOME_MISS


async def test_evaluate_scores_due_prediction(session) -> None:
    from datetime import timedelta

    class_id, article_id = _seed_classification(session, ["NVDA"])
    await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["NVDA"]),
        price_client=_FakePriceClient({"NVDA": 100.0}),  # baseline 100
        horizons=["1d"],
        watchlist={"NVDA"},
    )
    session.commit()

    # Price rose to 105 (+5%); horizon is due.
    summary = await evaluate_predictions(
        session,
        price_client=_FakePriceClient({"NVDA": 105.0}),
        threshold_pct=0.5,
        max_move_pct=40.0,
        now=datetime.now(tz=UTC) + timedelta(days=2),
    )
    assert summary.evaluated == 1
    assert summary.hits == 1  # bullish + up
    assert PredictionRepository(session).count_by_status(PRED_EVALUATED) == 1


async def test_evaluate_skips_implausible_move(session) -> None:
    from datetime import timedelta

    class_id, article_id = _seed_classification(session, ["MU"])
    await record_predictions(
        session,
        classification_id=class_id,
        article_id=article_id,
        result=_classification(["MU"]),
        price_client=_FakePriceClient({"MU": 942.0}),  # bad baseline
        horizons=["1d"],
        watchlist={"MU"},
    )
    session.commit()

    # Real price ~100 → -89% vs bad baseline → implausible → skipped.
    summary = await evaluate_predictions(
        session,
        price_client=_FakePriceClient({"MU": 100.0}),
        threshold_pct=0.5,
        max_move_pct=40.0,
        now=datetime.now(tz=UTC) + timedelta(days=2),
    )
    assert summary.skipped == 1
    assert summary.evaluated == 0
    assert PredictionRepository(session).count_by_status(PRED_SKIPPED) == 1


# --- report + digest (step E) ----------------------------------------------


async def _seed_and_evaluate(session, ticker: str, baseline: float, current: float, sentiment: str):
    class_id, article_id = _seed_classification(session, [ticker])
    result = ClassificationResult(
        is_market_relevant=True, importance="HIGH", category="TICKER", sentiment=sentiment,
        related_tickers=[ticker], summary="s", why_it_matters="w", should_alert=True,
    )
    await record_predictions(
        session, classification_id=class_id, article_id=article_id, result=result,
        price_client=_FakePriceClient({ticker: baseline}), horizons=["1d"], watchlist={ticker},
    )
    session.commit()
    from datetime import timedelta

    await evaluate_predictions(
        session, price_client=_FakePriceClient({ticker: current}),
        threshold_pct=0.5, max_move_pct=40.0,
        now=datetime.now(tz=UTC) + timedelta(days=2),
    )


async def test_report_computes_accuracy(session) -> None:
    await _seed_and_evaluate(session, "NVDA", 100.0, 105.0, "BULLISH")  # +5% -> HIT
    await _seed_and_evaluate(session, "MSFT", 100.0, 95.0, "BULLISH")   # -5% -> MISS

    report = build_evaluation_report(session)
    assert report.total_evaluated == 2
    assert report.hits == 1 and report.misses == 1
    assert report.accuracy_pct == 50.0
    assert report.bullish.total == 2


def test_single_timezone_setting_drives_everything() -> None:
    from app.config import Settings, resolve_timezone

    s = Settings(_env_file=None, timezone="America/Los_Angeles")
    assert resolve_timezone(s) == "America/Los_Angeles"

    # A typo falls back to UTC instead of crashing the scheduler.
    s = Settings(_env_file=None, timezone="Not/AZone")
    assert resolve_timezone(s) == "UTC"


def test_digest_empty_state() -> None:
    from app.evaluation import EvaluationReport, SentimentStat

    empty_stat = SentimentStat("x", 0, 0, 0, 0, None, None)
    report = EvaluationReport(0, 0, 0, 0, None, empty_stat, empty_stat, [], [], 3)
    assert "not enough" in build_evaluation_digest(report).lower()
    assert "chưa đủ" in build_evaluation_digest(report, "Vietnamese")
