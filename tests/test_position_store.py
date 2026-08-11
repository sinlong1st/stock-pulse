"""Saved positions store + /api/positions (exit-advisor plan Phase 3).

The contract these tests defend:

1. A position that can be **saved** is a position that can be **analyzed** —
   the store validates through the same `math.parse_position` the advice uses.
2. Removing a position **archives** it. Ids are forever, because a stored
   analysis points at one.
3. The endpoints are gated by both the mobile-API token and the feature flag.
"""

import json
from decimal import Decimal

import pytest

import app.config as config
import app.main as main
from app.config import Settings
from app.position import store
from app.position.store import (
    MAX_POSITIONS,
    PositionStoreError,
    archive_position,
    clean_ticker,
    create_position,
    get_position,
    list_positions,
    update_position,
)


@pytest.fixture
def settings(tmp_path):
    """A store pointed at a scratch file, with the cache cleared either side."""
    store._load.cache_clear()
    yield Settings(_env_file=None, positions_file=str(tmp_path / "positions.json"))
    store._load.cache_clear()


def _wdc(**overrides) -> dict:
    return {"ticker": "wdc", "shares": 20, "average_cost": 420, **overrides}


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("raw", ["wdc", " WDC ", "Wdc"])
def test_tickers_are_normalized(raw) -> None:
    assert clean_ticker(raw) == "WDC"


@pytest.mark.parametrize("raw", ["", "  ", "not a ticker", "WAYTOOLONGTICKER", "!!"])
def test_nonsense_tickers_are_rejected(raw) -> None:
    with pytest.raises(PositionStoreError):
        clean_ticker(raw)


def test_symbols_with_punctuation_are_accepted() -> None:
    """Symbol resolution can legitimately return these, and people hold them."""
    assert clean_ticker("brk.b") == "BRK.B"
    assert clean_ticker("rds-a") == "RDS-A"


def test_an_index_is_not_a_holding() -> None:
    """`^VIX` is a real symbol our own market module fetches, but nobody owns
    shares of an index — accepting one would produce advice about a position
    that cannot exist."""
    with pytest.raises(PositionStoreError):
        clean_ticker("^VIX")


@pytest.mark.parametrize(
    ("field", "value"),
    [("shares", 0), ("shares", -5), ("average_cost", 0), ("average_cost", -1)],
)
def test_the_store_rejects_what_the_math_rejects(settings, field, value) -> None:
    """RULE-EXIT-002 / -003 are enforced once, in the math module, so the store
    and the analysis can never disagree about what a valid position is."""
    with pytest.raises(PositionStoreError):
        create_position(settings=settings, **_wdc(**{field: value}))


def test_a_present_but_zero_stop_is_a_typo_not_an_intention(settings) -> None:
    with pytest.raises(PositionStoreError):
        create_position(settings=settings, **_wdc(stop=0))


def test_optional_prices_may_be_absent(settings) -> None:
    got = create_position(settings=settings, **_wdc(stop=None, target=""))
    assert got.stop is None and got.target is None


def test_an_unknown_style_or_risk_is_rejected(settings) -> None:
    with pytest.raises(PositionStoreError, match="investmentStyle"):
        create_position(settings=settings, **_wdc(investment_style="yolo"))
    with pytest.raises(PositionStoreError, match="riskTolerance"):
        create_position(settings=settings, **_wdc(risk_tolerance="reckless"))


def test_spec_defaults_apply_when_preferences_are_omitted(settings) -> None:
    """§4: swing / moderate / partial selling allowed."""
    got = create_position(settings=settings, **_wdc())
    assert got.investment_style == "swing"
    assert got.risk_tolerance == "moderate"
    assert got.allow_partial_sell is True


def test_partial_selling_can_be_turned_off(settings) -> None:
    got = create_position(settings=settings, **_wdc(allow_partial_sell=False))
    assert got.allow_partial_sell is False


def test_a_bad_purchase_date_is_rejected(settings) -> None:
    with pytest.raises(PositionStoreError, match="date"):
        create_position(settings=settings, **_wdc(purchase_date="last tuesday"))


def test_a_purchase_date_is_normalized_to_a_plain_date(settings) -> None:
    got = create_position(settings=settings, **_wdc(purchase_date="2026-03-04T10:00:00"))
    assert got.purchase_date == "2026-03-04"


# --- round trip ------------------------------------------------------------


def test_a_saved_position_survives_the_file(settings) -> None:
    created = create_position(
        settings=settings, **_wdc(stop=440, target=520, purchase_date="2026-03-04")
    )
    store._load.cache_clear()  # force a real read from disk

    got = get_position(created.id, settings)
    assert got is not None
    assert got.ticker == "WDC"
    assert float(got.shares) == 20.0 and float(got.average_cost) == 420.0
    assert float(got.stop) == 440.0 and float(got.target) == 520.0
    assert got.purchase_date == "2026-03-04"


def test_money_does_not_round_trip_through_a_float(settings) -> None:
    """Stored as strings on purpose — JSON floats would reintroduce exactly the
    drift the Decimal math module exists to avoid."""
    created = create_position(settings=settings, **_wdc(shares=3, average_cost="0.1"))
    store._load.cache_clear()
    got = get_position(created.id, settings)
    assert got is not None
    assert str(got.average_cost) == "0.1"
    assert got.to_position().cost_basis == Decimal("0.30")


def test_positions_are_listed_oldest_first(settings) -> None:
    first = create_position(settings=settings, **_wdc())
    second = create_position(settings=settings, **_wdc(ticker="NVDA"))
    assert [p.id for p in list_positions(settings)] == [first.id, second.id]


def test_the_same_ticker_can_be_held_twice(settings) -> None:
    """Separate tax lots are a real thing; the store doesn't second-guess it."""
    a = create_position(settings=settings, **_wdc())
    b = create_position(settings=settings, **_wdc(average_cost=390))
    assert a.id != b.id
    assert len(list_positions(settings)) == 2


def test_the_list_is_capped(settings) -> None:
    for i in range(MAX_POSITIONS):
        create_position(settings=settings, **_wdc(ticker=f"AA{i}"))
    with pytest.raises(PositionStoreError, match="at most"):
        create_position(settings=settings, **_wdc())


# --- updates and archiving -------------------------------------------------


def test_updating_keeps_the_id_and_moves_the_timestamp(settings) -> None:
    created = create_position(settings=settings, **_wdc())
    updated = update_position(created.id, settings=settings, **_wdc(shares=30))

    assert updated.id == created.id
    assert float(updated.shares) == 30.0
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at


def test_updating_something_that_is_gone_says_so(settings) -> None:
    with pytest.raises(PositionStoreError, match="no longer exists"):
        update_position("p_nope", settings=settings, **_wdc())


def test_removing_a_position_archives_it(settings) -> None:
    """Ids are forever — a stored analysis points at one."""
    created = create_position(settings=settings, **_wdc())
    archive_position(created.id, settings=settings)

    assert list_positions(settings) == []
    still_there = get_position(created.id, settings)
    assert still_there is not None and still_there.archived is True
    assert [p.id for p in list_positions(settings, include_archived=True)] == [created.id]


def test_an_archived_position_frees_a_slot(settings) -> None:
    for i in range(MAX_POSITIONS):
        create_position(settings=settings, **_wdc(ticker=f"AA{i}"))
    archive_position(list_positions(settings)[0].id, settings=settings)
    create_position(settings=settings, **_wdc())  # no longer at the cap


def test_archiving_something_that_is_gone_says_so(settings) -> None:
    with pytest.raises(PositionStoreError, match="no longer exists"):
        archive_position("p_nope", settings=settings)


# --- file robustness -------------------------------------------------------


def test_a_corrupt_file_is_ignored_rather_than_fatal(tmp_path) -> None:
    path = tmp_path / "positions.json"
    path.write_text("{not json", encoding="utf-8")
    store._load.cache_clear()
    settings = Settings(_env_file=None, positions_file=str(path))
    assert list_positions(settings) == []
    store._load.cache_clear()


def test_a_record_missing_optional_fields_still_loads(tmp_path) -> None:
    """A hand-edited or older file shouldn't take the whole list down."""
    path = tmp_path / "positions.json"
    path.write_text(
        json.dumps(
            {"positions": {"p_old": {"id": "p_old", "ticker": "WDC",
                                     "shares": "20", "average_cost": "420"}}}
        ),
        encoding="utf-8",
    )
    store._load.cache_clear()
    settings = Settings(_env_file=None, positions_file=str(path))
    got = list_positions(settings)
    assert len(got) == 1
    assert got[0].investment_style == "swing" and got[0].allow_partial_sell is True
    store._load.cache_clear()


# --- endpoints -------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
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
_BODY = {"ticker": "wdc", "shares": 20, "averageCost": 420}


def test_the_endpoints_need_the_token(client) -> None:
    assert client.get("/api/positions").status_code == 401


def test_the_endpoints_404_when_the_feature_is_off(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("POSITION_EXIT_ENABLED", "false")
    monkeypatch.setenv("POSITIONS_FILE", str(tmp_path / "positions.json"))
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    assert TestClient(main.app).get("/api/positions", headers=_AUTH).status_code == 404
    config.get_settings.cache_clear()


def test_create_list_update_delete(client) -> None:
    created = client.post("/api/positions", json=_BODY, headers=_AUTH)
    assert created.status_code == 200
    positions = created.json()["positions"]
    assert len(positions) == 1
    assert positions[0]["ticker"] == "WDC" and positions[0]["shares"] == 20.0
    position_id = positions[0]["id"]

    listed = client.get("/api/positions", headers=_AUTH).json()
    assert [p["id"] for p in listed["positions"]] == [position_id]
    assert listed["limits"]["maxPositions"] == MAX_POSITIONS
    assert "swing" in listed["limits"]["investmentStyles"]

    updated = client.put(
        f"/api/positions/{position_id}", json={**_BODY, "shares": 30}, headers=_AUTH
    ).json()
    assert updated["positions"][0]["shares"] == 30.0

    removed = client.delete(f"/api/positions/{position_id}", headers=_AUTH)
    assert removed.status_code == 200 and removed.json()["positions"] == []


def test_a_bad_position_is_a_400_not_a_500(client) -> None:
    got = client.post("/api/positions", json={**_BODY, "shares": 0}, headers=_AUTH)
    assert got.status_code == 400 and "Shares" in got.json()["detail"]


def test_updating_an_unknown_id_is_a_400(client) -> None:
    got = client.put("/api/positions/p_nope", json=_BODY, headers=_AUTH)
    assert got.status_code == 400
