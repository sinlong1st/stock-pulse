"""Deterministic exit rules (spec §28, exit-advisor plan Phase 6).

The contract these tests defend:

1. Rules only ever move toward **lower exposure**. Nothing here can talk you
   into holding more.
2. A rule that can't be evaluated stays **silent** rather than guessing.
3. Findings are **codes plus numbers**, never English.
4. The result does not depend on the order the rules ran in.
"""

import pytest

from app.position.rules import EXPOSURE_LADDER, ExitRuleResult, evaluate


def _evidence(**kw) -> dict:
    """A healthy holding that trips no rules, so each test changes one thing."""
    base = {
        "price": 130.0,
        "trend": "up",
        "enoughHistory": True,
        "hasNearSupport": True,
        "resistance": 140.0,
        "holdRewardRisk": 2.5,
        "supportAtrs": 1.5,
        "resistanceAtrs": 2.0,
        "aboveSma20Atrs": 0.6,
        "indicators": {"rsi14": 55.0, "sma20": 124.0, "ema21": 123.0,
                       "macd": {"histogram": 0.4}, "atr14": 4.0},
        "market": {"relative20d": 3.0, "riskAppetite": "risk-on"},
        "relativeVolume": 1.0,
        "earningsInDays": 40,
        "inProfit": True,
        "stop": 120.0,
        "quoteAgeMinutes": 2.0,
        "sessionToday": True,
    }
    base.update(kw)
    return base


def _codes(result: ExitRuleResult) -> set[str]:
    return {f.code for f in result.findings}


# --- the clean case --------------------------------------------------------


def test_a_healthy_holding_trips_nothing() -> None:
    got = evaluate(None, _evidence())
    assert got.findings == [] and got.final is None and got.refresh_required is False


def test_a_clean_holding_leaves_an_ai_action_alone() -> None:
    for action in ("hold", "partial-sell", "exit"):
        assert evaluate(action, _evidence()).final == action


# --- the ladder only runs one way ------------------------------------------


def test_rules_never_increase_exposure() -> None:
    """A rule demanding `partial-sell` must not pull an `exit` back up to it."""
    got = evaluate("exit", _evidence(holdRewardRisk=0.2))
    assert got.final == "exit" and got.overridden is False
    assert "weak-hold-reward-risk" in _codes(got)  # still reported


@pytest.mark.parametrize("action", EXPOSURE_LADDER)
def test_no_rule_ever_moves_left_on_the_ladder(action) -> None:
    everything = _evidence(
        holdRewardRisk=0.1, hasNearSupport=False, trend="down",
        indicators={"rsi14": 80.0, "sma20": 140.0, "ema21": 141.0,
                    "macd": {"histogram": -1.0}, "atr14": 4.0},
        market={"relative20d": -8.0, "riskAppetite": "risk-off"},
        earningsInDays=1, inProfit=False,
    )
    got = evaluate(action, everything)
    assert EXPOSURE_LADDER.index(got.final) >= EXPOSURE_LADDER.index(action)


def test_findings_do_not_depend_on_rule_order() -> None:
    """Each rule reads the original evidence, never the running verdict — the
    bug Predict's engine had once, invisible until a test looked for it."""
    evidence = _evidence(holdRewardRisk=0.2, earningsInDays=1)
    first = evaluate(None, evidence)
    # Re-running against an already-downgraded action changes nothing reported.
    second = evaluate(first.final, evidence)
    assert _codes(first) == _codes(second)


# --- RULE-EXIT-001 stale quote ---------------------------------------------


def test_a_stale_quote_during_a_session_blocks_a_conclusion() -> None:
    got = evaluate(None, _evidence(quoteAgeMinutes=90.0))
    assert got.refresh_required is True and "stale-quote" in _codes(got)


def test_an_old_quote_outside_a_session_is_normal() -> None:
    """A Friday-afternoon print on a Sunday is not staleness, and warning about
    it every weekend would teach the user to ignore the warning."""
    got = evaluate(None, _evidence(quoteAgeMinutes=3000.0, sessionToday=False))
    assert got.refresh_required is False and "stale-quote" not in _codes(got)


def test_an_unknown_quote_age_stays_silent() -> None:
    got = evaluate(None, _evidence(quoteAgeMinutes=None))
    assert "stale-quote" not in _codes(got)


def test_staleness_does_not_move_the_ladder() -> None:
    """§28: no conclusion at all until refreshed — which is not the same as
    'sell some'."""
    got = evaluate("hold", _evidence(quoteAgeMinutes=90.0))
    assert got.final == "hold" and got.refresh_required is True


# --- RULE-EXIT-004 stop --------------------------------------------------


@pytest.mark.parametrize("stop", [130.0, 140.0])
def test_a_stop_at_or_above_the_price_is_not_a_stop(stop) -> None:
    assert "invalid-stop" in _codes(evaluate(None, _evidence(stop=stop)))


def test_no_stop_set_is_not_an_error() -> None:
    assert "invalid-stop" not in _codes(evaluate(None, _evidence(stop=None)))


# --- RULE-EXIT-005 earnings ------------------------------------------------


def test_imminent_earnings_require_a_defined_stop() -> None:
    got = evaluate("hold", _evidence(earningsInDays=1))
    assert got.final == "hold-with-stop"
    assert "earnings-imminent" in _codes(got)


def test_earnings_risk_is_not_a_sell_signal() -> None:
    """Holding through a report is a legitimate choice; the rule only insists it
    be a deliberate one."""
    got = evaluate(None, _evidence(earningsInDays=0))
    assert got.final == "hold-with-stop"


def test_earnings_far_out_are_ignored() -> None:
    assert "earnings-imminent" not in _codes(evaluate(None, _evidence(earningsInDays=9)))


def test_a_just_passed_report_does_not_fire() -> None:
    """`days_until` goes negative once the date has passed."""
    assert "earnings-imminent" not in _codes(evaluate(None, _evidence(earningsInDays=-2)))


# --- RULE-EXIT-006 weak incremental reward/risk ----------------------------


def test_a_weak_hold_ratio_biases_toward_trimming() -> None:
    got = evaluate("hold", _evidence(holdRewardRisk=0.4))
    assert got.final == "partial-sell"
    assert got.findings[0].params["ratio"] == 0.4


def test_a_weak_hold_ratio_never_forces_a_full_exit() -> None:
    """§28 is explicit about this: a poor ratio from here means take some off,
    not abandon the position."""
    got = evaluate("hold", _evidence(holdRewardRisk=0.01))
    assert got.final == "partial-sell"
    assert got.final != "exit"


def test_an_undefined_hold_ratio_stays_silent() -> None:
    assert "weak-hold-reward-risk" not in _codes(evaluate(None, _evidence(holdRewardRisk=None)))


# --- RULE-EXIT-007 support broken ------------------------------------------


def test_losing_the_near_term_floor_structure_reduces() -> None:
    got = evaluate("hold", _evidence(hasNearSupport=False))
    assert got.final == "reduce" and "support-broken" in _codes(got)


def test_support_is_not_called_broken_without_enough_history() -> None:
    """Thin history means we never knew where the floor was."""
    got = evaluate(None, _evidence(hasNearSupport=False, enoughHistory=False))
    assert "support-broken" not in _codes(got)


# --- RULE-EXIT-008 trend deterioration -------------------------------------


def _deteriorating(**kw):
    return _evidence(
        trend="down",
        indicators={"rsi14": 40.0, "sma20": 140.0, "ema21": 141.0,
                    "macd": {"histogram": -1.0}, "atr14": 4.0},
        market={"relative20d": -8.0, "riskAppetite": "mixed"},
        **kw,
    )


def test_broad_trend_damage_biases_toward_trimming() -> None:
    got = evaluate("hold", _deteriorating())
    assert got.final == "partial-sell"
    assert "trend-deterioration" in _codes(got)


def test_the_signals_are_named_not_counted() -> None:
    """"Below its 20-day average and MACD rolling over" is a reason; "3" isn't."""
    got = evaluate(None, _deteriorating())
    finding = next(f for f in got.findings if f.code == "trend-deterioration")
    assert "below-sma20" in finding.params["signals"]
    assert "macd-negative" in finding.params["signals"]


def test_one_or_two_soft_signals_are_an_ordinary_pullback() -> None:
    got = evaluate(None, _evidence(trend="down", market={"relative20d": -1.0}))
    assert "trend-deterioration" not in _codes(got)


# --- RULE-EXIT-009 / -010 extension and breakouts --------------------------


def test_an_extended_price_biases_toward_taking_some_profit() -> None:
    got = evaluate("hold", _evidence(aboveSma20Atrs=3.0))
    assert got.final == "partial-sell" and "extended" in _codes(got)


def test_overbought_right_under_resistance_counts_as_extended() -> None:
    got = evaluate(None, _evidence(
        aboveSma20Atrs=0.5,
        indicators={"rsi14": 75.0, "sma20": 124.0, "atr14": 4.0},
        resistanceAtrs=0.2,
    ))
    assert "extended" in _codes(got)


def test_a_high_rsi_alone_is_not_a_sell_signal() -> None:
    """§28 RULE-EXIT-010 in spirit: RSI 74 in open space is momentum."""
    got = evaluate(None, _evidence(
        indicators={"rsi14": 78.0, "sma20": 124.0, "atr14": 4.0}, resistanceAtrs=3.0
    ))
    assert "extended" not in _codes(got)


def test_a_confirmed_breakout_suppresses_the_extension_rule() -> None:
    """RULE-EXIT-010 — price through the ceiling on real volume, in a market
    that isn't hostile, with no event pending."""
    got = evaluate("hold", _evidence(
        aboveSma20Atrs=3.0, price=145.0, resistance=140.0, relativeVolume=1.8
    ))
    assert "valid-breakout" in _codes(got)
    assert "extended" not in _codes(got)
    assert got.final == "hold"  # nothing moved


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relativeVolume", 1.0),  # no participation
        ("earningsInDays", 2),  # event inside the window
    ],
)
def test_an_unconfirmed_breakout_does_not_suppress(field, value) -> None:
    got = evaluate(None, _evidence(
        **{"aboveSma20Atrs": 3.0, "price": 145.0, "resistance": 140.0,
           "relativeVolume": 1.8, field: value}
    ))
    assert "extended" in _codes(got)


def test_a_breakout_into_a_risk_off_market_does_not_suppress() -> None:
    got = evaluate(None, _evidence(
        aboveSma20Atrs=3.0, price=145.0, resistance=140.0, relativeVolume=1.8,
        market={"relative20d": 3.0, "riskAppetite": "risk-off"},
    ))
    assert "extended" in _codes(got)


def test_a_breakout_suppressor_cannot_raise_exposure() -> None:
    """The suppressor only cancels one rule; anything else still stands."""
    got = evaluate("hold", _evidence(
        aboveSma20Atrs=3.0, price=145.0, resistance=140.0, relativeVolume=1.8,
        hasNearSupport=False,
    ))
    assert got.final == "reduce"


# --- informational findings ------------------------------------------------


def test_a_position_below_cost_is_flagged_for_wording() -> None:
    """RULE-EXIT-011 — nothing here may be phrased as profit-taking."""
    got = evaluate("hold", _evidence(inProfit=False))
    assert "below-cost" in _codes(got)
    assert got.final == "hold"  # a label, not an exposure change


def test_a_floor_inside_the_daily_noise_is_flagged() -> None:
    """The live WDC 6.62:1 case: a real ratio measured against a level an
    ordinary day takes out."""
    got = evaluate("hold", _evidence(supportAtrs=0.13))
    assert "support-inside-noise" in _codes(got)
    assert got.final == "hold"  # says how far to trust the ratio, nothing more


def test_a_sane_stop_distance_is_not_flagged() -> None:
    codes = _codes(evaluate(None, _evidence(supportAtrs=1.2)))
    assert "support-inside-noise" not in codes and "support-far" not in codes


def test_a_floor_left_far_behind_is_flagged() -> None:
    """Live MSFT: ran $378 to $503 in 21 sessions, leaving its only pivot low
    25% below. Real number, useless as an invalidation."""
    got = evaluate("hold", _evidence(supportAtrs=12.5))
    assert "support-far" in _codes(got)
    # `extended` already carries the exposure consequence for this fact.
    assert got.final == "hold"


def test_the_two_distance_findings_are_exclusive() -> None:
    """A floor cannot be both inside the noise and far away."""
    for atrs in (0.1, 12.5):
        codes = _codes(evaluate(None, _evidence(supportAtrs=atrs)))
        assert not {"support-inside-noise", "support-far"} <= codes


# --- payload ---------------------------------------------------------------


def test_findings_are_codes_and_numbers_not_sentences() -> None:
    payload = evaluate("hold", _evidence(earningsInDays=1)).as_dict()
    finding = payload["findings"][0]
    assert finding["code"] == "earnings-imminent"
    assert finding["params"] == {"days": 1}
    assert finding["atLeast"] == "hold-with-stop"
    assert payload["overridden"] is True
