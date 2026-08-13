"""Position arithmetic for the Exit Advisor (plan Phase 1).

The contract these tests defend:

1. The spec's own worked examples (§5-§8, §21, §31) come out **exactly** right.
   Those numbers are the acceptance criteria, so they are asserted verbatim.
2. Anything undefined for the inputs returns **None**, never a plausible zero.
3. Money is **Decimal-exact** — no float drift, at any position size.
4. Interpretation is a **code**, never English, so the app localizes it.
5. The hold decision never depends on average cost (§3.2).
"""

from decimal import Decimal

import pytest

from app.position.math import (
    PositionError,
    cost_basis_recovery,
    giveback_analysis,
    giveback_at,
    hold_reward_risk,
    normalize_probabilities,
    parse_position,
    parse_price,
    partial_sell,
    partial_sell_options,
    scenario,
    summarize,
)

D = Decimal


def _wdc():
    """The spec's running example: 20 WDC @ $420 average, now $472."""
    position = parse_position(shares=20, average_cost=420)
    return summarize(position, parse_price(472))


# --- validation (RULE-EXIT-002 / -003) -------------------------------------


@pytest.mark.parametrize("shares", [0, -1, "0", Decimal("-0.5")])
def test_shares_must_be_positive(shares) -> None:
    with pytest.raises(PositionError, match="Shares"):
        parse_position(shares=shares, average_cost=420)


@pytest.mark.parametrize("cost", [0, -420, "0"])
def test_average_cost_must_be_positive(cost) -> None:
    with pytest.raises(PositionError, match="Average cost"):
        parse_position(shares=20, average_cost=cost)


@pytest.mark.parametrize("bad", ["abc", "", None, object(), [1]])
def test_non_numeric_input_is_rejected(bad) -> None:
    with pytest.raises(PositionError):
        parse_position(shares=bad, average_cost=420)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_input_is_rejected(bad) -> None:
    """NaN and infinity survive Decimal() intact and would poison every figure
    downstream silently — they have to be caught at the door."""
    with pytest.raises(PositionError, match="finite"):
        parse_position(shares=bad, average_cost=420)


def test_booleans_are_not_share_counts() -> None:
    """`bool` is an `int` subclass, so `True` would quietly become 1 share."""
    with pytest.raises(PositionError):
        parse_position(shares=True, average_cost=420)


@pytest.mark.parametrize("price", [0, -1, "0"])
def test_price_must_be_positive(price) -> None:
    with pytest.raises(PositionError):
        parse_price(price)


def test_strings_from_a_form_are_accepted() -> None:
    """The app's numeric keyboard hands back strings; whitespace included."""
    position = parse_position(shares=" 20 ", average_cost="420.00")
    assert position.shares == D(20) and position.average_cost == D("420.00")


# --- §5 position summary ---------------------------------------------------


def test_position_summary_matches_the_spec_example() -> None:
    """§32: cost basis $8,400 · value $9,440 · P&L +$1,040 · +12.38%."""
    got = _wdc()
    assert got.cost_basis == D("8400.00")
    assert got.current_value == D("9440.00")
    assert got.unrealized_pnl == D("1040.00")
    assert got.unrealized_pnl_pct == D("12.38")
    assert got.in_profit is True


def test_a_losing_position_reports_negative_pnl() -> None:
    got = summarize(parse_position(shares=20, average_cost=500), parse_price(472))
    assert got.unrealized_pnl == D("-560.00")
    assert got.unrealized_pnl_pct == D("-5.60")
    assert got.in_profit is False


def test_money_is_decimal_exact() -> None:
    """The float path gives 0.30000000000000004 for this; Decimal gives 0.30."""
    got = summarize(parse_position(shares=3, average_cost="0.1"), parse_price("0.2"))
    assert got.cost_basis == D("0.30")
    assert got.current_value == D("0.60")
    assert got.unrealized_pnl == D("0.30")


def test_large_positions_do_not_drift() -> None:
    got = summarize(
        parse_position(shares=100000, average_cost="19.99"), parse_price("20.01")
    )
    assert got.unrealized_pnl == D("2000.00")


@pytest.mark.parametrize(
    ("average_cost", "expected"),
    [
        (300, "large-profit"),  # +57%
        (440, "moderate-profit"),  # +7.3%
        (470, "small-profit"),  # +0.4%
        (472, "break-even"),
        (490, "small-loss"),  # -3.7%
        (700, "large-loss"),  # -32.6%
    ],
)
def test_pnl_status_buckets(average_cost, expected) -> None:
    got = summarize(parse_position(shares=20, average_cost=average_cost), parse_price(472))
    assert got.status == expected


# --- §7 profit giveback ----------------------------------------------------


def test_giveback_matches_the_spec_example() -> None:
    """§7: at $450 support — remaining +$600, given back -$440, 42.3% of profit."""
    got = giveback_at(_wdc(), D(450))
    assert got.giveback == D("440.00")
    assert got.remaining_pnl == D("600.00")
    assert got.giveback_pct_of_profit == D("42.31")
    assert got.pct_move == D("-4.66")


def test_giveback_percentage_is_undefined_on_a_losing_position() -> None:
    """§5.9 — "42% of your profit" means nothing when there is no profit, and
    dividing by a negative P&L would produce a confidently-signed absurdity."""
    losing = summarize(parse_position(shares=20, average_cost=500), parse_price(472))
    got = giveback_at(losing, D(450))
    assert got.giveback_pct_of_profit is None
    assert got.giveback == D("440.00")  # the dollar giveback is still real
    assert got.remaining_pnl == D("-1000.00")


def test_giveback_analysis_is_ordered_nearest_first() -> None:
    got = giveback_analysis(_wdc(), [D(430), D(465), D(450)])
    assert [level.support for level in got] == [D(465), D(450), D(430)]
    assert [level.giveback for level in got] == [D("140.00"), D("440.00"), D("840.00")]


def test_levels_at_or_above_the_price_are_not_giveback_scenarios() -> None:
    got = giveback_analysis(_wdc(), [D(480), D(472), D(450)])
    assert [level.support for level in got] == [D(450)]


def test_giveback_analysis_with_no_usable_levels_is_empty() -> None:
    assert giveback_analysis(_wdc(), []) == []


# --- §6 hold reward/risk ---------------------------------------------------


def test_hold_reward_risk_matches_the_spec_example() -> None:
    """§6: current $472, target $500, support $450 → +$28 vs -$22, 1.27 : 1,
    +$560 additional profit against -$440 of giveback."""
    got = hold_reward_risk(_wdc(), target=D(500), support=D(450))
    assert got is not None
    assert got.upside_per_share == D("28.00")
    assert got.downside_per_share == D("22.00")
    assert got.ratio == D("1.27")
    assert got.additional_profit == D("560.00")
    assert got.profit_giveback == D("440.00")
    assert got.label == "balanced"


def test_hold_reward_risk_ignores_average_cost() -> None:
    """§3.2 — the incremental trade is identical whether you are up or down; only
    the room above and below the *current* price matters."""
    winning = summarize(parse_position(shares=20, average_cost=100), parse_price(472))
    losing = summarize(parse_position(shares=20, average_cost=900), parse_price(472))
    a = hold_reward_risk(winning, target=D(500), support=D(450))
    b = hold_reward_risk(losing, target=D(500), support=D(450))
    assert a is not None and b is not None
    assert a.ratio == b.ratio == D("1.27")
    assert a.additional_profit == b.additional_profit


@pytest.mark.parametrize(
    ("target", "support"),
    [
        (D(460), D(450)),  # "target" below the price is not upside
        (D(472), D(450)),  # nor is the price itself
        (D(500), D(480)),  # "support" above the price is not support
        (D(500), D(472)),
        (None, D(450)),
        (D(500), None),
        (None, None),
    ],
)
def test_hold_reward_risk_is_none_when_undefined(target, support) -> None:
    """A negative or inverted ratio would read as a real, catastrophic number."""
    assert hold_reward_risk(_wdc(), target=target, support=support) is None


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (D(516), "strong"),  # 44/22 = 2.00
        (D(505), "attractive"),  # 33/22 = 1.50
        (D(494), "balanced"),  # 22/22 = 1.00
        (D("488.5"), "weak"),  # 16.5/22 = 0.75
        (D(480), "poor"),  # 8/22 = 0.36
    ],
)
def test_reward_risk_bands_are_inclusive_at_the_boundary(target, expected) -> None:
    got = hold_reward_risk(_wdc(), target=target, support=D(450))
    assert got is not None and got.label == expected


# --- §8 partial sell -------------------------------------------------------


def test_partial_sell_matches_the_spec_example() -> None:
    """§8: sell 50% of 20 @ $472 → 10 shares, $4,720 proceeds, ~$520 realized,
    10 left worth $520 unrealized, +$280 more if the rest reaches $500."""
    got = partial_sell(_wdc(), 50, target=D(500))
    assert got.shares_sold == D(10)
    assert got.shares_remaining == D(10)
    assert got.proceeds == D("4720.00")
    assert got.realized_pnl == D("520.00")
    assert got.remaining_value == D("4720.00")
    assert got.remaining_unrealized_pnl == D("520.00")
    assert got.additional_upside_on_remaining == D("280.00")
    assert got.possible is True


def test_whole_shares_round_down_and_report_the_real_percentage() -> None:
    """33% of 20 shares is 6.6. Selling 7 would dispose of more of the position
    than the user chose, so we sell 6 — and say 30%, not 33%."""
    got = partial_sell(_wdc(), 33)
    assert got.shares_sold == D(6)
    assert got.pct_requested == D("33.00")
    assert got.pct_actual == D("30.00")


def test_fractional_shares_when_the_broker_supports_them() -> None:
    got = partial_sell(_wdc(), 33, allow_fractional=True)
    assert got.shares_sold == D("6.6")
    assert got.pct_actual == D("33.00")


def test_a_preset_that_cannot_be_filled_is_flagged_not_hidden() -> None:
    """50% of a single share rounds to zero. The UI needs to know that so it can
    grey the preset out rather than offer a plan that sells nothing."""
    single = summarize(parse_position(shares=1, average_cost=420), parse_price(472))
    got = partial_sell(single, 50)
    assert got.shares_sold == D(0)
    assert got.possible is False
    assert got.shares_remaining == D(1)


def test_selling_everything_leaves_nothing_behind() -> None:
    got = partial_sell(_wdc(), 100, target=D(500))
    assert got.shares_sold == D(20)
    assert got.shares_remaining == D(0)
    assert got.remaining_unrealized_pnl == D("0.00")
    assert got.additional_upside_on_remaining == D("0.00")


def test_no_upside_reported_without_a_usable_target() -> None:
    assert partial_sell(_wdc(), 50).additional_upside_on_remaining is None
    # A target at or below the current price is not upside either.
    assert partial_sell(_wdc(), 50, target=D(460)).additional_upside_on_remaining is None


@pytest.mark.parametrize("pct", [0, -10, 101, "0"])
def test_sell_percentage_bounds(pct) -> None:
    """RULE-EXIT-012: 0 < sellPct <= 100."""
    with pytest.raises(PositionError, match="percentage"):
        partial_sell(_wdc(), pct)


def test_the_preset_ladder_is_the_spec_set() -> None:
    got = partial_sell_options(_wdc())
    assert [option.pct_requested for option in got] == [D(25), D(33), D(50), D(75)]
    assert [option.shares_sold for option in got] == [D(5), D(6), D(10), D(15)]


def test_realized_and_remaining_pnl_always_reconcile() -> None:
    """Whatever the split, the two halves must add back to the whole position's
    unrealized P&L — otherwise a partial plan quietly invents or loses money."""
    summary = _wdc()
    for option in partial_sell_options(summary):
        assert option.realized_pnl + option.remaining_unrealized_pnl == (
            summary.unrealized_pnl
        )


# Prices and averages that don't land on clean cents, so every figure has to be
# rounded somewhere. Rounding each part on its own leaves the halves a cent off
# the whole, which is visible because the UI shows the split under the headline.
_AWKWARD = [
    ("7", "100.005", "200.007"),
    ("13", "33.333", "47.777"),
    ("101", "9.995", "10.005"),
    ("3.5", "1234.567", "999.001"),
]


@pytest.mark.parametrize(("shares", "average_cost", "price"), _AWKWARD)
def test_the_parts_sum_to_the_whole_even_when_nothing_rounds_cleanly(
    shares, average_cost, price
) -> None:
    summary = summarize(parse_position(shares=shares, average_cost=average_cost),
                        parse_price(price))
    for option in partial_sell_options(summary, allow_fractional=True):
        assert option.proceeds + option.remaining_value == summary.current_value
        assert (
            option.realized_pnl + option.remaining_unrealized_pnl
            == summary.unrealized_pnl
        )


@pytest.mark.parametrize(("shares", "average_cost", "price"), _AWKWARD)
def test_giveback_and_remaining_profit_sum_to_the_whole(
    shares, average_cost, price
) -> None:
    """§7 shows current profit, remaining profit and giveback in one card."""
    summary = summarize(parse_position(shares=shares, average_cost=average_cost),
                        parse_price(price))
    level = giveback_at(summary, summary.current_price / D(2))
    assert level.giveback + level.remaining_pnl == summary.unrealized_pnl


# --- §20/§21 scenarios -----------------------------------------------------


@pytest.mark.parametrize(
    ("name", "low", "high", "pnl", "change"),
    [
        # Straight from §21's worked display.
        ("bull", 495, 505, ("1500.00", "1700.00"), ("460.00", "660.00")),
        ("base", 460, 490, ("800.00", "1400.00"), ("-240.00", "360.00")),
        ("bear", 435, 455, ("300.00", "700.00"), ("-740.00", "-340.00")),
    ],
)
def test_scenarios_match_the_spec_display(name, low, high, pnl, change) -> None:
    got = scenario(_wdc(), name=name, probability=30, low=D(low), high=D(high))
    assert (got.pnl_low, got.pnl_high) == (D(pnl[0]), D(pnl[1]))
    assert (got.change_from_current_low, got.change_from_current_high) == (
        D(change[0]),
        D(change[1]),
    )


def test_a_swapped_range_is_ordered_rather_than_rendered_broken() -> None:
    got = scenario(_wdc(), name="bull", probability=30, low=D(505), high=D(495))
    assert got.price_low == D(495) and got.price_high == D(505)
    assert got.value_low < got.value_high


def test_probabilities_are_left_alone_when_they_already_sum_to_100() -> None:
    assert normalize_probabilities([30, 45, 25]) == [30, 45, 25]


def test_probabilities_are_normalized_to_whole_percents() -> None:
    """Whole numbers on purpose — 33.33% would be the false precision §3.5
    forbids. The rounding remainder goes to the largest scenario."""
    assert sum(normalize_probabilities([50, 30, 25])) == 100
    assert normalize_probabilities([1, 2]) == [33, 67]


def test_equal_probabilities_still_sum_to_100() -> None:
    assert normalize_probabilities([1, 1, 1]) == [34, 33, 33]


def test_a_malformed_probability_set_degrades_instead_of_failing() -> None:
    """A bad model response should cost a slightly wrong weighting, not the
    whole analysis."""
    assert normalize_probabilities([0, 0, 0]) == [34, 33, 33]
    assert normalize_probabilities([-10, 50, 50]) == [0, 50, 50]
    assert normalize_probabilities([]) == []


# --- §31 cost-basis recovery ----------------------------------------------


def test_cost_basis_recovery_rounds_up_to_actually_recover_the_stake() -> None:
    """$8,400 / $472 = 17.79 shares. Selling 17 leaves the stake short, which is
    the one thing this view promises not to do."""
    got = cost_basis_recovery(_wdc())
    assert got.shares_needed == D(18)
    assert got.shares_remaining == D(2)
    assert got.possible is True
    assert got.proceeds == D("8496.00")


def test_cost_basis_recovery_is_impossible_under_water() -> None:
    """At $300 the whole position is worth less than the original stake, so
    there is no partial sale that recovers it."""
    losing = summarize(parse_position(shares=20, average_cost=420), parse_price(300))
    got = cost_basis_recovery(losing)
    assert got.possible is False
    assert got.shares_remaining == D(0)


def test_cost_basis_recovery_supports_fractional_shares() -> None:
    got = cost_basis_recovery(_wdc(), allow_fractional=True)
    assert got.shares_needed == D("8400.00") / D(472)


# --- payload shape ---------------------------------------------------------


def test_dicts_are_camel_case_json_scalars() -> None:
    """The API boundary hands the app plain JSON numbers, never Decimals — and
    structured values, never English sentences."""
    summary = _wdc()
    payload = summary.as_dict()
    assert payload["unrealizedPnl"] == 1040.0
    assert isinstance(payload["unrealizedPnl"], float)
    assert payload["status"] == "moderate-profit"

    rr = hold_reward_risk(summary, target=D(500), support=D(450))
    assert rr is not None and rr.as_dict()["label"] == "balanced"
    assert giveback_at(summary, D(450)).as_dict()["givebackPctOfProfit"] == 42.31
    assert scenario(
        summary, name="bull", probability=30, low=D(495), high=D(505)
    ).as_dict()["priceRange"] == {"low": 495.0, "high": 505.0}


# --- recovery from a loss --------------------------------------------------


def test_recovery_is_measured_from_here_not_from_the_fall() -> None:
    """A 10% fall needs an 11.1% rise to undo. Quoting the fall would understate
    the climb — and understating it is what makes "wait to get back to even"
    sound reasonable."""
    got = summarize(parse_position(shares=8, average_cost=490), parse_price(441))
    assert got.unrealized_pnl_pct == D("-10.00")
    assert got.recovery_pct == D("11.11")


def test_a_winning_position_has_nothing_to_recover() -> None:
    assert _wdc().recovery_pct is None


def test_break_even_needs_nothing() -> None:
    got = summarize(parse_position(shares=8, average_cost=490), parse_price(490))
    assert got.recovery_pct is None


def test_recovery_reaches_the_payload() -> None:
    got = summarize(parse_position(shares=8, average_cost=490), parse_price(456))
    assert got.as_dict()["recoveryPct"] == pytest.approx(7.46, abs=0.01)
