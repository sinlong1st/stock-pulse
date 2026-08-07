"""The checkable facts behind the entry advice.

None of this is AI: it's arithmetic over the same real numbers the charts use,
sent as values rather than sentences so the app can phrase them per language.
The point is that a user can audit the entry call instead of trusting it.
"""

from types import SimpleNamespace

import pytest

from app.prediction.service import _confidence, _evidence


def _signals(*, low=60.0, high=100.0, level="fair", trend="up", enough=True):
    return SimpleNamespace(
        range_low=low,
        range_high=high,
        discount_level=level,
        trend=trend,
        enough_history=enough,
        range_note="",
        discount_note="",
    )


def _support(near=None, long=None):
    near = near if near is not None else [63.0, 61.5, 60.0]
    long = long if long is not None else [58.2, 55.4]
    return {
        "near": near[0] if near else None,
        "long": long[0] if long else None,
        "nearLevels": near,
        "longLevels": long,
    }


def _ev(**kw):
    base = dict(
        price=65.0,
        signals=_signals(),
        support=_support(),
        resistance=71.5,
        news_count=4,
        earnings=None,
        today=None,
    )
    return _evidence(**{**base, **kw})


# --- distances and ratio ---------------------------------------------------


def test_distances_are_signed_from_the_current_price() -> None:
    got = _ev()
    assert got["supportPct"] == pytest.approx(-3.1, abs=0.05)  # 63 is below 65
    assert got["targetPct"] == pytest.approx(10.0, abs=0.05)  # 71.5 is above
    assert got["nearestSupport"] == 63.0 and got["resistance"] == 71.5


def test_reward_risk_is_upside_over_downside() -> None:
    got = _ev(price=65.0, resistance=71.5, support=_support(near=[61.75]))
    # +10% up, -5% down -> 2.0 : 1
    assert got["rewardRisk"] == pytest.approx(2.0, abs=0.05)


def test_reward_uses_nearby_resistance_not_the_far_off_range_high() -> None:
    """Regression: using the window high gave a 12.7:1 ratio on a stock 75% off
    its high — flattering and meaningless."""
    got = _ev(price=65.0, signals=_signals(high=400.0), resistance=71.5)
    assert got["rewardRisk"] == pytest.approx(3.2, abs=0.1)  # not ~170:1


def test_no_ratio_without_a_resistance_above_the_price() -> None:
    """At a new high there is nothing overhead to measure against."""
    got = _ev(price=120.0, resistance=None)
    assert got["targetPct"] is None and got["rewardRisk"] is None


def test_no_ratio_when_support_sits_above_the_price() -> None:
    got = _ev(price=59.0, support=_support(near=[63.0]))  # support above price
    assert got["rewardRisk"] is None


def test_missing_price_leaves_the_distances_null() -> None:
    got = _ev(price=None)
    assert got["supportPct"] is None and got["targetPct"] is None
    assert got["rewardRisk"] is None


# --- invalidation ----------------------------------------------------------


def test_invalidation_is_the_deepest_near_term_floor() -> None:
    """The entry thesis rests on the near structure — under it, it's broken."""
    assert _ev(support=_support(near=[63.0, 61.5, 60.0]))["invalidation"] == 60.0


def test_invalidation_falls_back_to_long_term_without_near_levels() -> None:
    assert _ev(support=_support(near=[], long=[58.2, 55.4]))["invalidation"] == 58.2


def test_invalidation_is_null_without_any_support() -> None:
    assert _ev(support=_support(near=[], long=[]))["invalidation"] is None


# --- passthrough facts -----------------------------------------------------


def test_carries_the_signal_facts_the_chips_render() -> None:
    got = _ev(signals=_signals(level="cheap", trend="down", enough=False), news_count=0)
    assert got["discountLevel"] == "cheap"
    assert got["trend"] == "down"
    assert got["newsCount"] == 0
    assert got["enoughHistory"] is False
    assert got["rangeLow"] == 60.0 and got["rangeHigh"] == 100.0


def test_earnings_days_come_through_when_known() -> None:
    from datetime import date

    from app.earnings import Earnings

    got = _ev(earnings=Earnings("WDC", next_date=date(2026, 8, 12)), today=date(2026, 8, 6))
    assert got["earningsInDays"] == 6
    assert _ev(earnings=None)["earningsInDays"] is None


# --- confidence basis ------------------------------------------------------


def _h(*leans):
    return [SimpleNamespace(lean=lean) for lean in leans]


def test_confidence_reports_horizon_agreement() -> None:
    got = _confidence(_h("bounce", "bounce", "dip"), _signals())
    assert got["agree"] == 2 and got["total"] == 3 and got["lean"] == "bounce"


def test_unanimous_horizons() -> None:
    got = _confidence(_h("dip", "dip", "dip"), _signals())
    assert got["agree"] == 3 and got["lean"] == "dip"


def test_cheap_but_falling_is_flagged_as_conflicting() -> None:
    """Value says buy, momentum says wait — the classic disagreement."""
    assert _confidence(_h("hold"), _signals(level="cheap", trend="down"))["signalsConflict"]
    assert _confidence(_h("hold"), _signals(level="rich", trend="up"))["signalsConflict"]


def test_aligned_signals_are_not_flagged() -> None:
    assert not _confidence(_h("bounce"), _signals(level="cheap", trend="up"))["signalsConflict"]
    assert not _confidence(_h("hold"), _signals(level="fair", trend="sideways"))["signalsConflict"]


def test_no_horizons_is_safe() -> None:
    got = _confidence([], _signals())
    assert got["total"] == 0 and got["agree"] == 0 and got["lean"] is None
