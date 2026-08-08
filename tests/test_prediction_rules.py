"""Deterministic risk rules over the AI's entry advice (committee plan Phase 1).

The contract these tests defend:

1. Rules only ever make the advice **more cautious** — `wait` never becomes `good`.
2. A rule that can't be evaluated stays **silent** rather than guessing.
3. Findings are **codes plus numbers**, never English, so the app localizes them.
"""

import pytest

from app.prediction.rules import RuleResult, evaluate


def _evidence(**kw) -> dict:
    """A clean setup that trips no rules, so each test changes exactly one thing."""
    base = {
        "price": 100.0,
        "enoughHistory": True,
        "nearestSupport": 96.0,
        "supportPct": -4.0,
        "rewardRisk": 3.0,
        "invalidation": 94.0,
        "earningsInDays": 40,
        "newsCount": 5,
        "indicators": {"atr14": 5.0, "volatilityRegime": "normal"},
    }
    base.update(kw)
    return base


def _codes(result: RuleResult) -> set[str]:
    return {f.code for f in result.findings}


# --- the clean case --------------------------------------------------------


def test_a_sound_setup_passes_untouched() -> None:
    got = evaluate("good", _evidence())
    assert got.final == "good" and not got.overridden and got.findings == []


@pytest.mark.parametrize("assessment", ["good", "fair", "wait"])
def test_a_clean_setup_never_changes_the_assessment(assessment) -> None:
    assert evaluate(assessment, _evidence()).final == assessment


# --- rules only tighten ----------------------------------------------------


def test_rules_never_upgrade_caution() -> None:
    """A `wait` stays `wait` even when every rule is happy."""
    got = evaluate("wait", _evidence())
    assert got.final == "wait"


def test_findings_do_not_depend_on_rule_order() -> None:
    """Regression: high-volatility was guarded on the *running* assessment, so it
    silently stopped firing whenever an earlier rule had already downgraded."""
    high_vol = {"atr14": 5.0, "volatilityRegime": "high"}

    alone = evaluate("good", _evidence(indicators=high_vol))
    alongside = evaluate("good", _evidence(indicators=high_vol, rewardRisk=0.5))

    assert "high-volatility" in _codes(alone)
    assert "high-volatility" in _codes(alongside)  # still reported


def test_the_strictest_rule_wins_when_several_fire() -> None:
    got = evaluate(
        "good",
        _evidence(rewardRisk=0.5, indicators={"atr14": 5.0, "volatilityRegime": "high"}),
    )
    # high volatility caps at "fair", weak reward:risk caps at "wait" — wait wins.
    assert got.final == "wait"
    assert {"weak-reward-risk", "high-volatility"} <= _codes(got)


# --- individual rules ------------------------------------------------------


def test_weak_reward_risk_downgrades_to_wait() -> None:
    got = evaluate("good", _evidence(rewardRisk=0.4))
    assert got.final == "wait" and "weak-reward-risk" in _codes(got)
    finding = next(f for f in got.findings if f.code == "weak-reward-risk")
    assert finding.params == {"ratio": 0.4, "minimum": 1.5}


def test_reward_risk_at_the_threshold_is_allowed() -> None:
    assert evaluate("good", _evidence(rewardRisk=1.5)).final == "good"


def test_the_reward_risk_minimum_is_configurable() -> None:
    assert evaluate("good", _evidence(rewardRisk=1.8), min_reward_risk=2.0).final == "wait"


def test_imminent_earnings_downgrade_to_wait() -> None:
    got = evaluate("good", _evidence(earningsInDays=1))
    assert got.final == "wait" and "earnings-imminent" in _codes(got)
    assert next(f for f in got.findings if f.code == "earnings-imminent").params == {"days": 1}


def test_distant_earnings_are_ignored() -> None:
    assert evaluate("good", _evidence(earningsInDays=30)).final == "good"


def test_past_earnings_are_ignored() -> None:
    """A negative countdown means it already reported — not a reason to wait."""
    assert evaluate("good", _evidence(earningsInDays=-3)).final == "good"


def test_extreme_volatility_downgrades_to_wait() -> None:
    got = evaluate(
        "good", _evidence(indicators={"atr14": 5.0, "volatilityRegime": "extreme"})
    )
    assert got.final == "wait" and "extreme-volatility" in _codes(got)


def test_high_volatility_only_softens_a_good_call() -> None:
    """Not a veto — but "good" overstates a setup this wide."""
    high = {"atr14": 5.0, "volatilityRegime": "high"}
    assert evaluate("good", _evidence(indicators=high)).final == "fair"
    # It shouldn't add noise to an already-cautious call.
    assert evaluate("fair", _evidence(indicators=high)).findings == []


def test_chasing_is_flagged_when_support_is_over_one_atr_away() -> None:
    # 8% of 100 = $8 away, ATR is $5 -> 1.6 ATR.
    got = evaluate("good", _evidence(supportPct=-8.0))
    assert got.final == "fair" and "chasing" in _codes(got)
    assert next(f for f in got.findings if f.code == "chasing").params == {"atrs": 1.6}


def test_price_near_support_is_not_chasing() -> None:
    assert evaluate("good", _evidence(supportPct=-3.0)).final == "good"  # $3 < $5 ATR


def test_a_stop_inside_the_daily_noise_is_rejected() -> None:
    # Invalidation $2 below on a $5 ATR — an ordinary day would hit it.
    got = evaluate("good", _evidence(invalidation=98.0))
    assert got.final == "wait" and "stop-too-tight" in _codes(got)


def test_an_invalidation_above_the_price_is_invalid() -> None:
    got = evaluate("good", _evidence(invalidation=105.0))
    assert got.final == "wait" and "invalid-stop" in _codes(got)


def test_missing_history_or_support_forces_a_wait() -> None:
    assert evaluate("good", _evidence(enoughHistory=False)).final == "wait"
    assert "missing-data" in _codes(evaluate("good", _evidence(nearestSupport=None)))


# --- unknowns stay silent --------------------------------------------------


def test_rules_needing_atr_stay_silent_without_it() -> None:
    """No ATR means chase and stop distance can't be judged — say nothing."""
    got = evaluate("good", _evidence(indicators={"atr14": None, "volatilityRegime": None}))
    assert _codes(got) & {"chasing", "stop-too-tight", "invalid-stop"} == set()
    assert got.final == "good"


def test_missing_reward_risk_is_not_treated_as_zero() -> None:
    assert evaluate("good", _evidence(rewardRisk=None)).final == "good"


def test_missing_earnings_date_is_not_treated_as_imminent() -> None:
    assert evaluate("good", _evidence(earningsInDays=None)).final == "good"


def test_an_empty_evidence_block_does_not_crash() -> None:
    got = evaluate("good", {})
    assert got.final == "wait"  # missing data is itself a finding
    assert "missing-data" in _codes(got)


def test_an_unknown_assessment_is_treated_as_fair() -> None:
    assert evaluate("banana", _evidence()).final == "fair"


# --- the shape the app consumes --------------------------------------------


def test_as_dict_carries_codes_and_numbers_not_prose() -> None:
    got = evaluate("good", _evidence(rewardRisk=0.4)).as_dict()
    assert got["original"] == "good"
    assert got["final"] == "wait"
    assert got["overridden"] is True
    assert got["findings"] == [
        {"code": "weak-reward-risk", "params": {"ratio": 0.4, "minimum": 1.5}}
    ]
    # No English anywhere — the app phrases these per language.
    assert all(isinstance(f["params"], dict) for f in got["findings"])
