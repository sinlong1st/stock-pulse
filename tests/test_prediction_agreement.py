"""Tests for §11 agreement scoring between the two analysts."""

from app.prediction.agreement import evaluate
from app.prediction.models import EntryRead, HorizonRead, PredictionRead


def _read(assessment: str, *horizons: tuple[str, str, str]) -> PredictionRead:
    """(horizon, lean, confidence) triples -> a PredictionRead."""
    return PredictionRead(
        entry=EntryRead(assessment=assessment, note="n"),
        horizons=[
            HorizonRead(horizon=h, lean=lean, confidence=conf) for h, lean, conf in horizons
        ],
        drivers=["d"],
    )


# --- action agreement ------------------------------------------------------


def test_same_entry_is_strong() -> None:
    a = _read("good", ("1w", "bounce", "medium"))
    b = _read("good", ("1w", "bounce", "medium"))
    result = evaluate(a, b)
    assert result.action_agreement == "strong"
    assert result.differences == []
    assert not result.requires_debate


def test_adjacent_entry_is_partial_not_conflict() -> None:
    # good vs fair is a difference of emphasis, not a contradiction.
    a = _read("good", ("1w", "bounce", "low"))
    b = _read("fair", ("1w", "bounce", "low"))
    result = evaluate(a, b)
    assert result.action_agreement == "partial"
    assert not result.requires_debate  # partial alone is not worth paying for


def test_opposite_entry_is_conflict() -> None:
    # good vs wait: one says buy, the other says stay out.
    a = _read("good", ("1w", "bounce", "low"))
    b = _read("wait", ("1w", "bounce", "low"))
    result = evaluate(a, b)
    assert result.action_agreement == "conflict"
    assert result.requires_debate
    assert any(d.code == "entry-differs" for d in result.differences)


def test_unknown_entry_grade_does_not_pass_as_agreement() -> None:
    a = _read("good", ("1w", "bounce", "low"))
    b = _read("good", ("1w", "bounce", "low"))
    object.__setattr__(b.entry, "assessment", "bogus")  # bypass validation
    assert evaluate(a, b).action_agreement == "conflict"


# --- direction -------------------------------------------------------------


def test_opposed_leans_flag_disagreement() -> None:
    # The case the old boolean missed entirely: same entry grade, opposite
    # directional call.
    a = _read("fair", ("1w", "bounce", "medium"))
    b = _read("fair", ("1w", "dip", "medium"))
    result = evaluate(a, b)
    assert result.action_agreement == "strong"  # entry grades match...
    assert not result.direction_agreement  # ...but they point opposite ways
    assert result.requires_debate
    diff = next(d for d in result.differences if d.code == "direction-opposed")
    assert diff.params == {"horizon": "1w", "primary": "bounce", "second": "dip"}


def test_hold_against_a_lean_is_not_opposed() -> None:
    # A shrug is weaker conviction, not a contradiction — must not trigger a
    # paid debate round.
    a = _read("fair", ("1w", "bounce", "low"))
    b = _read("fair", ("1w", "hold", "low"))
    result = evaluate(a, b)
    assert result.direction_agreement
    assert not result.requires_debate


def test_only_shared_horizons_are_compared() -> None:
    a = _read("fair", ("1w", "bounce", "low"), ("3mo", "dip", "low"))
    b = _read("fair", ("1w", "bounce", "low"))
    assert evaluate(a, b).direction_agreement  # 3mo has no counterpart


# --- confidence ------------------------------------------------------------


def test_one_step_confidence_gap_is_tolerated() -> None:
    a = _read("fair", ("1w", "bounce", "low"))
    b = _read("fair", ("1w", "bounce", "medium"))
    result = evaluate(a, b)
    assert result.confidence_steps == 1
    assert not result.requires_debate


def test_two_step_confidence_gap_is_material() -> None:
    a = _read("fair", ("1w", "bounce", "low"))
    b = _read("fair", ("1w", "bounce", "high"))
    result = evaluate(a, b)
    assert result.confidence_steps == 2
    assert result.requires_debate
    assert any(d.code == "confidence-gap" for d in result.differences)


def test_widest_gap_wins_not_the_average() -> None:
    # Averaging would hide the 1w blow-up behind two matching horizons.
    steady = (("1mo", "hold", "medium"), ("3mo", "hold", "medium"))
    a = _read("fair", ("1w", "bounce", "low"), *steady)
    b = _read("fair", ("1w", "bounce", "high"), *steady)
    assert evaluate(a, b).confidence_steps == 2


# --- serialization ---------------------------------------------------------


def test_as_dict_is_codes_not_prose() -> None:
    a = _read("good", ("1w", "bounce", "low"))
    b = _read("wait", ("1w", "dip", "high"))
    payload = evaluate(a, b).as_dict()
    assert payload["actionAgreement"] == "conflict"
    assert payload["directionAgreement"] is False
    assert payload["confidenceSteps"] == 2
    assert payload["requiresDebate"] is True
    # Every difference must be a stable code the app can localize.
    assert {d["code"] for d in payload["differences"]} == {
        "entry-differs",
        "direction-opposed",
        "confidence-gap",
    }
    for d in payload["differences"]:
        assert d["code"].islower() and " " not in d["code"]
