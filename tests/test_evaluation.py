"""Tests for prediction recording (Eval plan, step C)."""

from datetime import UTC, datetime, timedelta

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


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def test_parse_horizon() -> None:
    assert parse_horizon("1h") == timedelta(hours=1)
    assert parse_horizon("2d") == timedelta(days=2)
    with pytest.raises(ValueError):
        parse_horizon("5w")


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
    article = ArticleRepository(session).add(
        NewsArticle(
            source="Test",
            title="t",
            url="https://e.com/a",
            collected_at=datetime.now(tz=UTC),
            content_hash="h",
        )
    )
    session.flush()
    row = ClassificationRepository(session).add(article.id, _classification(tickers))
    session.flush()
    return row.id, article.id


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
    )
    session.commit()

    assert created == 4  # 2 tickers × 2 horizons
    repo = PredictionRepository(session)
    assert repo.count() == 4
    assert repo.count_by_status(PRED_PENDING) == 4


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
