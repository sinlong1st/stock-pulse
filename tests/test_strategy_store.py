"""User-written prediction strategies: storage, validation and the API.

The invariant worth protecting is that ids are permanent — recorded predictions
carry `strategy_id`, so reusing or dropping one would misattribute past accuracy.
"""

import pytest

import app.prediction.store as store
import app.prefs as prefs
from app.config import Settings
from app.prediction.store import (
    MAX_BODY_CHARS,
    MAX_NAME_CHARS,
    StrategyError,
    archive_strategy,
    create_strategy,
    get_active_strategy,
    get_strategy,
    list_strategies,
    set_active_strategy,
    update_strategy,
)
from app.prediction.strategies import DEFAULT_STRATEGY

BODY = "Buy quality names 20% off their high when the bad news looks temporary."


@pytest.fixture
def settings(tmp_path):
    """Isolated strategy + prefs files, with both caches cleared around the test."""
    store._load.cache_clear()
    prefs._load.cache_clear()
    s = Settings(
        _env_file=None,
        strategies_file=str(tmp_path / "strategies.json"),
        prefs_file=str(tmp_path / "prefs.json"),
    )
    yield s
    store._load.cache_clear()
    prefs._load.cache_clear()


# --- validation ------------------------------------------------------------


def test_rejects_empty_name(settings) -> None:
    with pytest.raises(StrategyError, match="name"):
        create_strategy("   ", BODY, settings=settings)


def test_rejects_overlong_name(settings) -> None:
    with pytest.raises(StrategyError, match="too long"):
        create_strategy("x" * (MAX_NAME_CHARS + 1), BODY, settings=settings)


def test_rejects_body_that_is_too_short_or_too_long(settings) -> None:
    with pytest.raises(StrategyError, match="at least"):
        create_strategy("Value", "too short", settings=settings)
    with pytest.raises(StrategyError, match="too long"):
        create_strategy("Value", "x" * (MAX_BODY_CHARS + 1), settings=settings)


def test_strips_control_characters_from_user_text(settings) -> None:
    """This text is pasted into a model prompt — no stray control bytes."""
    created = create_strategy("Va\x00lue\x07", BODY + "\x1b", settings=settings)
    assert "\x00" not in created.name and "\x07" not in created.name
    assert "\x1b" not in created.body


def test_collapses_runaway_blank_lines(settings) -> None:
    created = create_strategy("Value", f"{BODY}\n\n\n\n\nMore text here.", settings=settings)
    assert "\n\n\n" not in created.body


# --- create / read ---------------------------------------------------------


def test_created_strategy_is_listed_after_the_builtin(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    listed = list_strategies(settings)

    assert listed[0].id == DEFAULT_STRATEGY.id  # built-in always first
    assert [s.id for s in listed[1:]] == [created.id]
    assert created.builtin is False


def test_ids_are_unique(settings) -> None:
    ids = {create_strategy(f"S{i}", BODY, settings=settings).id for i in range(5)}
    assert len(ids) == 5


def test_get_strategy_returns_the_builtin_for_its_id_and_for_blank(settings) -> None:
    assert get_strategy(DEFAULT_STRATEGY.id, settings).id == DEFAULT_STRATEGY.id
    assert get_strategy("", settings).id == DEFAULT_STRATEGY.id
    assert get_strategy("nope", settings) is None


def test_custom_strategy_shows_its_own_words_in_any_language(settings) -> None:
    """The user wrote it; don't pretend to have a translation."""
    created = create_strategy("Value lens", BODY, settings=settings)
    assert created.display(vi=True) == ("Value lens", created.body)


# --- active selection ------------------------------------------------------


def test_default_is_active_until_one_is_chosen(settings) -> None:
    assert get_active_strategy(settings).id == DEFAULT_STRATEGY.id


def test_activating_a_strategy_sticks(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    set_active_strategy(created.id, settings=settings)
    assert get_active_strategy(settings).id == created.id


def test_activating_an_unknown_strategy_is_rejected(settings) -> None:
    with pytest.raises(StrategyError):
        set_active_strategy("s_nope", settings=settings)


def test_can_switch_back_to_the_builtin(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    set_active_strategy(created.id, settings=settings)
    set_active_strategy(DEFAULT_STRATEGY.id, settings=settings)
    assert get_active_strategy(settings).id == DEFAULT_STRATEGY.id


# --- update / archive ------------------------------------------------------


def test_update_keeps_the_id_so_history_stays_attributed(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    updated = update_strategy(
        created.id, name="Deep value", body=BODY + " Ignore momentum.", settings=settings
    )
    assert updated.id == created.id
    assert updated.name == "Deep value"


def test_builtin_cannot_be_edited_or_removed(settings) -> None:
    with pytest.raises(StrategyError):
        update_strategy(DEFAULT_STRATEGY.id, name="Mine", body=BODY, settings=settings)
    with pytest.raises(StrategyError):
        archive_strategy(DEFAULT_STRATEGY.id, settings=settings)


def test_archived_strategy_leaves_the_picker_but_keeps_its_name(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    archive_strategy(created.id, settings=settings)

    assert [s.id for s in list_strategies(settings)] == [DEFAULT_STRATEGY.id]
    # Still resolvable, so an old prediction can still be labelled.
    still = get_strategy(created.id, settings)
    assert still is not None and still.name == "Value lens"


def test_archiving_the_active_strategy_falls_back_to_the_builtin(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    set_active_strategy(created.id, settings=settings)
    archive_strategy(created.id, settings=settings)
    assert get_active_strategy(settings).id == DEFAULT_STRATEGY.id


def test_archived_strategy_cannot_be_reactivated(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    archive_strategy(created.id, settings=settings)
    with pytest.raises(StrategyError):
        set_active_strategy(created.id, settings=settings)


def test_updating_a_missing_strategy_is_rejected(settings) -> None:
    with pytest.raises(StrategyError):
        update_strategy("s_gone", name="x", body=BODY, settings=settings)


# --- persistence -----------------------------------------------------------


def test_strategies_survive_a_reload(settings) -> None:
    created = create_strategy("Value lens", BODY, settings=settings)
    store._load.cache_clear()  # simulate a fresh process
    assert [s.id for s in list_strategies(settings)] == [DEFAULT_STRATEGY.id, created.id]


def test_unreadable_file_degrades_to_the_builtin(settings, tmp_path) -> None:
    (tmp_path / "strategies.json").write_text("{ not json", encoding="utf-8")
    store._load.cache_clear()
    assert [s.id for s in list_strategies(settings)] == [DEFAULT_STRATEGY.id]


# --- API -------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app.config as config
    import app.main as main

    store._load.cache_clear()
    prefs._load.cache_clear()
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("STRATEGIES_FILE", str(tmp_path / "strategies.json"))
    monkeypatch.setenv("PREFS_FILE", str(tmp_path / "prefs.json"))
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    config.get_settings.cache_clear()
    store._load.cache_clear()
    prefs._load.cache_clear()


AUTH = {"Authorization": "Bearer s3cret"}


def test_api_requires_the_token(client) -> None:
    assert client.get("/api/strategies").status_code == 401


def test_api_lists_the_builtin_and_limits(client) -> None:
    got = client.get("/api/strategies", headers=AUTH).json()
    assert [s["id"] for s in got["strategies"]] == [DEFAULT_STRATEGY.id]
    assert got["activeId"] == DEFAULT_STRATEGY.id
    assert got["strategies"][0]["builtin"] is True
    assert got["strategies"][0]["active"] is True
    assert got["limits"]["bodyChars"] == MAX_BODY_CHARS


def test_api_create_then_activate(client) -> None:
    created = client.post(
        "/api/strategies", headers=AUTH, json={"name": "Value lens", "body": BODY}
    )
    assert created.status_code == 200
    new_id = [s for s in created.json()["strategies"] if not s["builtin"]][0]["id"]

    activated = client.post(f"/api/strategies/{new_id}/activate", headers=AUTH)
    assert activated.status_code == 200
    assert activated.json()["activeId"] == new_id


def test_api_rejects_bad_input_with_400(client) -> None:
    res = client.post("/api/strategies", headers=AUTH, json={"name": "", "body": BODY})
    assert res.status_code == 400
    assert "name" in res.json()["detail"].lower()


def test_api_update_and_archive(client) -> None:
    created = client.post(
        "/api/strategies", headers=AUTH, json={"name": "Value lens", "body": BODY}
    ).json()
    new_id = [s for s in created["strategies"] if not s["builtin"]][0]["id"]

    updated = client.put(
        f"/api/strategies/{new_id}",
        headers=AUTH,
        json={"name": "Deep value", "body": BODY + " And ignore momentum."},
    ).json()
    assert [s for s in updated["strategies"] if s["id"] == new_id][0]["name"] == "Deep value"

    archived = client.delete(f"/api/strategies/{new_id}", headers=AUTH).json()
    assert [s["id"] for s in archived["strategies"]] == [DEFAULT_STRATEGY.id]


def test_api_cannot_edit_the_builtin(client) -> None:
    res = client.put(
        f"/api/strategies/{DEFAULT_STRATEGY.id}",
        headers=AUTH,
        json={"name": "Mine", "body": BODY},
    )
    assert res.status_code == 400
