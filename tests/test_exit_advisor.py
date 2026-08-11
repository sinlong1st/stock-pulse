"""The numbers-only exit analysis (exit-advisor plan Phase 4).

The contract these tests defend:

1. **No AI runs.** Every figure is arithmetic over real bars, so the feature
   works — and can be tested — with no provider configured at all.
2. The analysis reads the **same levels as Predict**. One definition, one answer.
3. Missing inputs degrade to `null` fields or a stated reason, never to a
   plausible-looking number.
"""

from datetime import UTC, datetime, timedelta

import pytest

import app.config as config
import app.main as main
import app.prediction.evidence as ev
import app.prediction.market as market
from app.briefing.focus import FocusTarget
from app.config import Settings
from app.position import store
from app.position.service import build_exit_advice, request_from_fields
from app.prices import Bar


def _bars(closes):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(t=t0 + timedelta(days=i), open=c, high=c * 1.02, low=c * 0.98, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


# A shape with real swing structure: floors under the price and a ceiling above.
_CLOSES = (
    [100, 108, 92, 104, 112, 96, 106, 116, 98, 110]
    + [112] * 40
    + [120, 132, 118, 126, 136, 122, 130, 128, 124, 130]
)


@pytest.fixture
def wired(monkeypatch):
    """Stub every outside call. No network, no AI, no provider key."""
    monkeypatch.setattr(
        ev, "resolve_focus", lambda q: FocusTarget(q, "WDC", "Western Digital", "WDC")
    )
    monkeypatch.setattr(ev, "maybe_briefing_price_client", lambda s: None)

    async def fake_bars(t, **kw):
        return _bars(_CLOSES)

    async def fake_news(**kw):
        return type("R", (), {"all": [type("I", (), {"title": "A headline"})()]})()

    async def no_earnings(tickers, **kw):
        return {}

    monkeypatch.setattr(ev, "fetch_bars", fake_bars)
    monkeypatch.setattr(ev, "retrieve_fresh_news", fake_news)
    monkeypatch.setattr(ev, "fetch_many", no_earnings)

    async def fake_market(symbol, **kw):
        return _bars([400.0] * 30)

    monkeypatch.setattr(market, "fetch_bars", fake_market)
    market.clear_cache()
    yield Settings(_env_file=None)
    market.clear_cache()


def _request(**overrides):
    fields = {"ticker": "WDC", "shares": 20, "average_cost": 100, **overrides}
    return request_from_fields(**fields)


async def _advice(settings, **overrides):
    return await build_exit_advice(settings, request=_request(**overrides))


# --- the headline numbers --------------------------------------------------


async def test_the_analysis_needs_no_ai_provider(wired) -> None:
    """The whole point of Phase 4: a useful answer for zero tokens."""
    got = await _advice(wired)
    assert got["ok"] is True
    assert got["ticker"] == "WDC"
    # Nothing resembling a model response appears anywhere in the payload.
    assert "entry" not in got and "horizons" not in got and "drivers" not in got


async def test_position_summary_is_computed_from_the_last_close(wired) -> None:
    got = await _advice(wired)
    position = got["position"]
    assert position["currentPrice"] == 130.0  # last bar
    assert position["costBasis"] == 2000.0  # 20 @ 100
    assert position["currentValue"] == 2600.0
    assert position["unrealizedPnl"] == 600.0
    assert position["status"] == "large-profit"


async def test_giveback_is_listed_nearest_floor_first(wired) -> None:
    got = await _advice(wired)
    supports = [level["support"] for level in got["giveback"]]
    assert supports, "the shape has real swing lows below the price"
    assert supports == sorted(supports, reverse=True)
    # Every level must sit below the current price to be a giveback at all.
    assert all(level < got["position"]["currentPrice"] for level in supports)


async def test_giveback_and_remaining_profit_reconcile(wired) -> None:
    got = await _advice(wired)
    total = got["position"]["unrealizedPnl"]
    for level in got["giveback"]:
        assert level["giveback"] + level["remainingPnl"] == total


async def test_hold_reward_risk_uses_the_nearest_swing_high(wired) -> None:
    """Never the window high — on a stock far off its high that flatters the
    ratio into meaninglessness."""
    got = await _advice(wired)
    hold = got["holdRewardRisk"]
    # Not conditional on purpose: this fixture has a swing high above the price,
    # so a None here means resistance detection regressed, not that the shape
    # happened to lack a ceiling.
    assert hold is not None
    assert hold["target"] == got["levels"]["resistance"]
    assert hold["support"] == got["levels"]["nearestSupport"]
    assert hold["label"] in {"strong", "attractive", "balanced", "weak", "poor"}
    # The legs must agree with the dollar figures they imply.
    shares = got["position"]["shares"]
    assert hold["additionalProfit"] == pytest.approx(hold["upsidePerShare"] * shares)
    assert hold["profitGiveback"] == pytest.approx(hold["downsidePerShare"] * shares)


async def test_the_users_own_target_is_reported_separately(wired) -> None:
    """One is what the chart offers, the other what they're hoping for. Blending
    them would hide the difference."""
    got = await _advice(wired, target=200)
    assert got["atYourTarget"] is not None
    assert got["atYourTarget"]["target"] == 200.0
    assert got["levels"]["target"] == 200.0
    # The chart-based reading is untouched by the user's hope.
    assert got["holdRewardRisk"] != got["atYourTarget"]


async def test_no_user_target_means_no_second_reading(wired) -> None:
    assert (await _advice(wired))["atYourTarget"] is None


# --- partial selling -------------------------------------------------------


async def test_the_partial_sell_ladder_is_offered_by_default(wired) -> None:
    got = await _advice(wired)
    assert [option["pctRequested"] for option in got["partialSell"]] == [25.0, 33.0, 50.0, 75.0]
    assert got["partialSell"][2]["sharesSold"] == 10.0


async def test_partial_selling_can_be_declined(wired) -> None:
    """§4 lets the user say partial selling isn't for them; offering the ladder
    anyway would be advice they've already refused."""
    got = await _advice(wired, allow_partial_sell=False)
    assert got["partialSell"] == [] and got["allowPartialSell"] is False


async def test_cost_basis_recovery_is_reported(wired) -> None:
    got = await _advice(wired)
    recovery = got["costBasisRecovery"]
    assert recovery["sharesNeeded"] == 16.0  # 2000 / 130 = 15.4 → round up
    assert recovery["possible"] is True


# --- context ---------------------------------------------------------------


async def test_levels_match_what_predict_would_read(wired) -> None:
    """Both features call `key_levels` on the same support dict."""
    from app.prediction.evidence import gather, key_levels

    package = await gather("WDC", wired)
    nearest, invalidation = key_levels(package.support)

    got = await _advice(wired)
    assert got["levels"]["nearestSupport"] == nearest
    assert got["levels"]["invalidation"] == invalidation


async def test_market_context_is_included(wired) -> None:
    got = await _advice(wired)
    assert got["technicals"]["market"]["marketTrend"] is not None


async def test_extension_is_measured_in_atrs_not_just_percent(wired) -> None:
    """A stock 5% above its mean is calm if it moves 3% a day and stretched if
    it moves 0.4%."""
    got = await _advice(wired)
    assert got["extension"]["aboveSma20Pct"] is not None
    assert got["extension"]["aboveSma20Atrs"] is not None


async def test_a_support_inside_the_daily_noise_is_reported_as_such(wired) -> None:
    """A live WDC run produced 6.62:1 "strong" off a support 1.6% below a stock
    whose ATR is 12% of its price — a floor inside one ordinary day's movement.
    The ratio isn't wrong; without this it is just easy to over-trust."""
    got = await _advice(wired)
    distance = got["levels"]["distance"]
    assert distance["supportAtrs"] is not None
    assert distance["resistanceAtrs"] is not None
    assert distance["atr14"] == got["technicals"]["indicators"]["atr14"]


async def test_levels_under_the_average_cost_are_flagged(wired) -> None:
    """Falling below cost isn't "giving back profit", it's taking a loss — and
    the percentage-of-profit figure goes past 100% to say so. RULE-EXIT-011
    forbids phrasing these as profit-taking, so the app is told which they are."""
    got = await _advice(wired, average_cost=125)  # price 130, floors well below
    flagged = [level for level in got["giveback"] if level["belowCostBasis"]]
    assert flagged, "this shape has support levels under the average cost"
    for level in flagged:
        assert level["remainingPnl"] < 0
        assert level["givebackPctOfProfit"] > 100


async def test_levels_above_the_average_cost_are_not_flagged(wired) -> None:
    """Bought at 90, with every floor in this shape above that — the position
    stays profitable even at the deepest support, so nothing is a loss."""
    got = await _advice(wired, average_cost=90)
    assert got["giveback"], "the shape has floors below the price"
    assert not any(level["belowCostBasis"] for level in got["giveback"])
    assert all(level["remainingPnl"] > 0 for level in got["giveback"])


async def test_indicators_come_through(wired) -> None:
    indicators = (await _advice(wired))["technicals"]["indicators"]
    assert indicators["rsi14"] is not None and indicators["atr14"] is not None


# --- degradation -----------------------------------------------------------


async def test_an_unknown_ticker_says_so(wired, monkeypatch) -> None:
    monkeypatch.setattr(ev, "resolve_focus", lambda q: FocusTarget(q, None, None, q))

    async def none_symbol(q, *, settings):
        return None

    monkeypatch.setattr(ev, "resolve_symbol_smart", none_symbol)
    got = await _advice(wired)
    assert got["ok"] is False and "Couldn't find" in got["reason"]


async def test_no_price_means_no_analysis_rather_than_a_guess(wired, monkeypatch) -> None:
    """§41 — without a verified price, every number on the screen is invented."""

    async def no_bars(t, **kw):
        return []

    monkeypatch.setattr(ev, "fetch_bars", no_bars)
    got = await _advice(wired)
    assert got["ok"] is False and "could not be verified" in got["reason"]


async def test_a_failed_market_read_does_not_cost_the_analysis(wired, monkeypatch) -> None:
    async def boom(symbol, **kw):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(market, "fetch_bars", boom)
    market.clear_cache()
    got = await _advice(wired)
    assert got["ok"] is True
    assert got["technicals"]["market"]["marketTrend"] is None


async def test_a_position_under_water_is_still_analyzed(wired) -> None:
    """§ RULE-EXIT-011 territory: nothing here may describe this as profit."""
    got = await _advice(wired, average_cost=500)
    assert got["ok"] is True
    assert got["position"]["unrealizedPnl"] < 0
    assert got["position"]["inProfit"] is False
    assert got["position"]["status"] == "large-loss"
    # A giveback percentage of a profit that doesn't exist would be nonsense.
    assert all(level["givebackPctOfProfit"] is None for level in got["giveback"])


async def test_stages_are_reported_in_order(wired) -> None:
    seen: list[str] = []
    await build_exit_advice(wired, request=_request(), progress=seen.append)
    assert seen == ["resolve", "prices", "news", "market"]


# --- endpoint --------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path, wired):
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("POSITION_EXIT_ENABLED", "true")
    monkeypatch.setenv("POSITIONS_FILE", str(tmp_path / "positions.json"))
    config.get_settings.cache_clear()
    store._load.cache_clear()
    from fastapi.testclient import TestClient

    yield TestClient(main.app)
    config.get_settings.cache_clear()
    store._load.cache_clear()


_AUTH = {"Authorization": "Bearer s3cret"}


def test_endpoint_accepts_an_inline_position(client) -> None:
    got = client.post(
        "/api/positions/exit-advisor",
        json={"ticker": "WDC", "shares": 20, "averageCost": 100},
        headers=_AUTH,
    )
    assert got.status_code == 200
    assert got.json()["position"]["unrealizedPnl"] == 600.0


def test_endpoint_accepts_a_saved_position(client) -> None:
    saved = client.post(
        "/api/positions",
        json={"ticker": "WDC", "shares": 20, "averageCost": 100},
        headers=_AUTH,
    ).json()["positions"][0]

    got = client.post(
        "/api/positions/exit-advisor", json={"positionId": saved["id"]}, headers=_AUTH
    ).json()
    assert got["ok"] is True and got["positionId"] == saved["id"]


def test_an_unknown_saved_position_is_a_404(client) -> None:
    got = client.post(
        "/api/positions/exit-advisor", json={"positionId": "p_nope"}, headers=_AUTH
    )
    assert got.status_code == 404


def test_an_empty_request_explains_what_is_needed(client) -> None:
    got = client.post("/api/positions/exit-advisor", json={}, headers=_AUTH)
    assert got.status_code == 400 and "positionId" in got.json()["detail"]


def test_an_inline_position_is_validated_like_a_saved_one(client) -> None:
    got = client.post(
        "/api/positions/exit-advisor",
        json={"ticker": "WDC", "shares": 0, "averageCost": 100},
        headers=_AUTH,
    )
    assert got.status_code == 400 and "Shares" in got.json()["detail"]


def test_the_endpoint_needs_the_token(client) -> None:
    assert client.post("/api/positions/exit-advisor", json={}).status_code == 401
