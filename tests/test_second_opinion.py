"""The measured second opinion (committee plan Phase 3).

The premise being tested: run the *same* evidence through a second model, record
both under their own provider, and let the accuracy loop say whether two models
beat one. The invariants that matter are that a second opinion never costs the
user their prediction, and that the two reads stay separate rather than being
averaged into a false consensus.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.prediction.mode as mode_mod
import app.prediction.service as svc
from app.config import Settings
from app.db.database import Base
from app.db.models import PredictionRow
from app.db.repository import PredictionRepository
from app.evaluation import build_provider_accuracy, record_prediction_read
from app.prediction.models import EntryRead, HorizonRead, PredictionRead
from app.status import OUTCOME_HIT, OUTCOME_MISS, PRED_SOURCE_PREDICT


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _read(lean: str = "bounce", entry: str = "good") -> PredictionRead:
    return PredictionRead(
        horizons=[HorizonRead(horizon="1w", lean=lean, confidence="medium", rationale="r")],
        drivers=["d"],
        entry=EntryRead(assessment=entry, note="n"),
    )


# --- recording keeps the models apart --------------------------------------


def test_each_provider_is_recorded_separately(session) -> None:
    for provider, lean in (("openai", "bounce"), ("deepseek", "dip")):
        record_prediction_read(
            session,
            ticker="NVDA",
            horizons=[{"horizon": "1w", "lean": lean, "confidence": "high"}],
            strategy_id="default",
            baseline_price=100.0,
            provider=provider,
        )
    session.commit()

    rows = session.query(PredictionRow).all()
    assert {r.provider for r in rows} == {"openai", "deepseek"}
    assert {r.sentiment for r in rows} == {"BULLISH", "BEARISH"}


def test_dedupe_is_scoped_per_provider(session) -> None:
    """Two models reading the same stock are two data points, not a duplicate."""
    horizons = [{"horizon": "1w", "lean": "bounce", "confidence": "high"}]
    first = record_prediction_read(
        session, ticker="NVDA", horizons=horizons, strategy_id="default",
        baseline_price=100.0, provider="openai",
    )
    other = record_prediction_read(
        session, ticker="NVDA", horizons=horizons, strategy_id="default",
        baseline_price=100.0, provider="deepseek",
    )
    same_again = record_prediction_read(
        session, ticker="NVDA", horizons=horizons, strategy_id="default",
        baseline_price=100.0, provider="openai",
    )
    session.commit()

    assert first == 1 and other == 1
    assert same_again == 0  # the openai row is already pending


# --- per-provider accuracy -------------------------------------------------


def _scored(session, *, provider: str, hits: int, misses: int) -> None:
    repo = PredictionRepository(session)
    now = datetime.now(tz=UTC)
    for outcome, ret in [(OUTCOME_HIT, 5.0)] * hits + [(OUTCOME_MISS, -4.0)] * misses:
        row = repo.create(
            source=PRED_SOURCE_PREDICT, ticker="NVDA", sentiment="BULLISH",
            strategy_id="default", provider=provider, horizon="1w",
            created_at=now, evaluate_after=now, baseline_price=100.0, baseline_at=now,
        )
        repo.mark_evaluated(row, 100 + ret, ret, outcome)
    session.commit()


def test_accuracy_is_computed_per_provider(session) -> None:
    _scored(session, provider="openai", hits=6, misses=4)
    _scored(session, provider="deepseek", hits=8, misses=2)

    stats = {s.provider: s for s in build_provider_accuracy(session)}
    assert stats["openai"].accuracy_pct == 60.0
    assert stats["deepseek"].accuracy_pct == 80.0
    assert stats["deepseek"].total == 10


def test_a_thin_sample_never_outranks_a_solid_one(session) -> None:
    """Same honesty as the per-strategy view — two lucky calls prove nothing."""
    _scored(session, provider="deepseek", hits=2, misses=0)  # 100%, tiny
    _scored(session, provider="openai", hits=7, misses=5)  # 58%, real

    stats = build_provider_accuracy(session)
    assert stats[0].provider == "openai" and stats[0].enough_data is True
    assert stats[1].provider == "deepseek" and stats[1].enough_data is False


def test_providers_with_only_pending_calls_still_appear(session) -> None:
    record_prediction_read(
        session, ticker="NVDA",
        horizons=[{"horizon": "1w", "lean": "bounce", "confidence": "low"}],
        strategy_id="default", baseline_price=100.0, provider="deepseek",
    )
    session.commit()

    stat = build_provider_accuracy(session)[0]
    assert stat.provider == "deepseek" and stat.total == 0 and stat.pending == 1


# --- the service path ------------------------------------------------------


class _Analyst:
    def __init__(self, name: str, read: PredictionRead) -> None:
        self.name, self.model, self._read = name, f"{name}-model", read

    async def analyze(self, **kw):
        return self._read


def _settings(tmp_path, **kw) -> Settings:
    return Settings(
        _env_file=None,
        openai_api_key="oa",
        strategies_file=str(tmp_path / "s.json"),
        prefs_file=str(tmp_path / "p.json"),
        **kw,
    )


async def test_second_opinion_is_reported_without_being_merged(monkeypatch, tmp_path) -> None:
    """Disagreement must stay visible — averaging would hide the useful signal."""
    svc._wired = None
    monkeypatch.setattr(mode_mod, "available_providers", lambda s: ["openai", "deepseek"])
    monkeypatch.setattr(
        svc, "build_analyst", lambda s, provider="openai": _Analyst(provider, _read("dip", "wait"))
    )

    got = await svc._second_opinion(
        _settings(tmp_path, deepseek_api_key="ds"), provider="deepseek", ticker="NVDA"
    )
    assert got is not None
    name, read = got
    assert name == "deepseek" and read.entry.assessment == "wait"


def test_no_second_provider_means_no_second_opinion(monkeypatch, tmp_path) -> None:
    """Choosing who runs is `plan`'s job now, not `_second_opinion`'s."""
    from app.prediction import mode as mode_mod

    monkeypatch.setattr(mode_mod, "available_providers", lambda s: ["openai"])
    got = mode_mod.plan(_settings(tmp_path), mode="both")
    assert got is not None and got.primary == "openai" and got.second is None


async def test_a_failing_second_opinion_is_swallowed(monkeypatch, tmp_path) -> None:
    """A bonus opinion must never cost the user the prediction they asked for."""
    from app.prediction.analyst import PredictionError

    def boom(settings, provider="openai"):
        raise PredictionError("deepseek is down")

    monkeypatch.setattr(mode_mod, "available_providers", lambda s: ["openai", "deepseek"])
    monkeypatch.setattr(svc, "build_analyst", boom)

    assert await svc._second_opinion(
        _settings(tmp_path, deepseek_api_key="ds"), provider="deepseek"
    ) is None
