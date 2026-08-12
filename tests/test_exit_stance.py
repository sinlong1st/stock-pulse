"""Which way each context signal argues (the CONTEXT card's grouping).

The contract these tests defend:

1. A stance is scored on the signal's **own terms**, never relative to the
   verdict — otherwise the same fact would flip its label between runs.
2. Thresholds come from the rule engine, so a chip can never claim more than
   the rule that owns that number would.
3. Unknown is **neutral**, not omitted. A missing RSI is not evidence.
"""

import pytest

from app.position.rules import evaluate
from app.position.stance import HOLD, NEUTRAL, TRIM, read_stances


def _evidence(**kw) -> dict:
    base = {
        "price": 130.0,
        "trend": "sideways",
        "resistance": 140.0,
        "resistanceAtrs": 2.0,
        "aboveSma20Atrs": 0.5,
        "indicators": {"rsi14": 55.0, "atr14": 4.0},
        "market": {"relative20d": 1.0, "riskAppetite": "mixed"},
        "relativeVolume": 1.0,
        "earningsInDays": 40,
    }
    base.update(kw)
    return base


# --- each signal on its own terms ------------------------------------------


@pytest.mark.parametrize(
    ("trend", "expected"), [("up", HOLD), ("down", TRIM), ("sideways", NEUTRAL)]
)
def test_trend(trend, expected) -> None:
    assert read_stances(_evidence(trend=trend))["trend"] == expected


def test_a_high_rsi_at_a_ceiling_argues_for_trimming() -> None:
    got = read_stances(_evidence(indicators={"rsi14": 78.0}, resistanceAtrs=0.2))
    assert got["rsi"] == TRIM


def test_a_high_rsi_in_open_space_is_not_evidence_either_way() -> None:
    """The app's own glossary promises a high RSI is never a sell signal on its
    own — a strong stock can hold above 70 for weeks. The chip must not say
    something the explanation contradicts."""
    got = read_stances(_evidence(indicators={"rsi14": 78.0}, resistanceAtrs=5.0))
    assert got["rsi"] == NEUTRAL


def test_extension_beyond_the_rule_threshold_argues_for_trimming() -> None:
    assert read_stances(_evidence(aboveSma20Atrs=2.5))["extension"] == TRIM
    assert read_stances(_evidence(aboveSma20Atrs=1.0))["extension"] == NEUTRAL


def test_being_far_below_the_average_is_left_to_the_trend_signal() -> None:
    """Counting one fact twice would make the tally read as more evidence than
    there is."""
    assert read_stances(_evidence(aboveSma20Atrs=-4.0))["extension"] == NEUTRAL


def test_volume_only_counts_when_it_confirms_a_breakout() -> None:
    """Volume has no direction of its own. Heavy volume going nowhere is
    activity, not conviction."""
    breaking_out = _evidence(price=145.0, resistance=140.0, relativeVolume=1.8)
    assert read_stances(breaking_out)["volume"] == HOLD
    assert read_stances(_evidence(relativeVolume=1.8))["volume"] == NEUTRAL
    assert read_stances(_evidence(price=145.0, resistance=140.0,
                                 relativeVolume=1.0))["volume"] == NEUTRAL


def test_imminent_earnings_argue_for_trimming() -> None:
    assert read_stances(_evidence(earningsInDays=1))["earnings"] == TRIM
    assert read_stances(_evidence(earningsInDays=30))["earnings"] == NEUTRAL


def test_a_just_passed_report_is_not_event_risk() -> None:
    assert read_stances(_evidence(earningsInDays=-3))["earnings"] == NEUTRAL


@pytest.mark.parametrize(
    ("market", "expected"),
    [
        ({"riskAppetite": "risk-off", "relative20d": 5.0}, TRIM),
        ({"riskAppetite": "risk-on", "relative20d": 5.0}, HOLD),
        ({"riskAppetite": "risk-on", "relative20d": -5.0}, NEUTRAL),
        ({"riskAppetite": "mixed", "relative20d": 5.0}, NEUTRAL),
    ],
)
def test_market(market, expected) -> None:
    assert read_stances(_evidence(market=market))["market"] == expected


# --- the contract ----------------------------------------------------------


def test_every_signal_is_scored_even_when_unknown() -> None:
    """Unknown is neutral, not missing — the card shows a chip either way."""
    got = read_stances({})
    assert set(got) == {"trend", "rsi", "extension", "volume", "earnings", "market"}
    assert set(got.values()) == {NEUTRAL}


def test_a_stance_does_not_depend_on_the_verdict() -> None:
    """The same evidence must score identically however the advice came out —
    a fact that flips its label between runs teaches nothing."""
    evidence = _evidence(trend="down", aboveSma20Atrs=3.0)
    first = read_stances(evidence)
    for action in ("hold", "partial-sell", "exit"):
        evaluate(action, evidence)  # the rule engine has no say here
        assert read_stances(evidence) == first


def test_the_thresholds_are_the_rule_engine_s() -> None:
    """If a chip says "argues for trimming" on extension, the rule that owns
    that threshold must have fired too. Same number, one source."""
    stretched = _evidence(aboveSma20Atrs=2.5, enoughHistory=True, hasNearSupport=True)
    assert read_stances(stretched)["extension"] == TRIM
    assert "extended" in {f.code for f in evaluate(None, stretched).findings}
