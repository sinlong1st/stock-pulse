"""The briefing schedule: computation, validation, and runtime editing.

The schedule is env-defaulted but prefs-overridden, and the values build cron
triggers at startup — so the tests here care most about invalid input never
reaching storage, and a corrupt prefs file never stopping the scheduler.
"""

import pytest

import app.prefs as prefs
from app.briefing.schedule import (
    MAX_EVERY_HOURS,
    BriefingSchedule,
    ScheduleError,
    intraday_hours,
    parse_hhmm,
    resolve_briefing_schedule,
    save_briefing_schedule,
    validate,
)
from app.config import Settings, resolve_briefing_timezone


@pytest.fixture
def settings(tmp_path):
    prefs._load.cache_clear()
    # briefing_enabled defaults to False; these tests are about the schedule, so
    # turn it on to exercise the paths that actually install jobs.
    yield Settings(
        _env_file=None,
        prefs_file=str(tmp_path / "prefs.json"),
        briefing_enabled=True,
    )
    prefs._load.cache_clear()


def _schedule(**kw) -> BriefingSchedule:
    base = dict(
        enabled=True,
        morning_at="08:30",
        intraday_every_hours=2,
        intraday_until="16:30",
        wrap_at="18:00",
    )
    return BriefingSchedule(**{**base, **kw})


# --- parsing + computation -------------------------------------------------


def test_parse_hhmm() -> None:
    assert parse_hhmm("08:30") == (8, 30)
    assert parse_hhmm("18:00") == (18, 0)
    assert parse_hhmm(" 9:05 ") == (9, 5)


@pytest.mark.parametrize("bad", ["", "8", "8:", ":30", "25:00", "08:61", "-1:00", "abc", "8:30:00"])
def test_parse_hhmm_rejects_nonsense(bad) -> None:
    with pytest.raises(ScheduleError):
        parse_hhmm(bad)


def test_intraday_hours_default() -> None:
    assert intraday_hours(_schedule()) == [10, 12, 14, 16]


def test_intraday_hours_custom() -> None:
    s = _schedule(morning_at="09:00", intraday_every_hours=3, intraday_until="18:00")
    assert intraday_hours(s) == [12, 15, 18]


def test_intraday_hours_empty_when_until_before_first() -> None:
    # First intraday would be 10:30, which is past the 09:00 cut-off.
    assert intraday_hours(_schedule(intraday_until="09:00")) == []


# --- validation ------------------------------------------------------------


def test_validate_normalises_times() -> None:
    got = validate(_schedule(morning_at="8:5", intraday_until="9:00", wrap_at="18:00"))
    assert got.morning_at == "08:05" and got.intraday_until == "09:00"


def test_validate_rejects_bad_cadence() -> None:
    for every in (0, -1, MAX_EVERY_HOURS + 1):
        with pytest.raises(ScheduleError, match="every"):
            validate(_schedule(intraday_every_hours=every))


def test_validate_rejects_backwards_days() -> None:
    with pytest.raises(ScheduleError, match="end before"):
        validate(_schedule(morning_at="10:00", intraday_until="09:00"))
    with pytest.raises(ScheduleError, match="wrap-up"):
        validate(_schedule(morning_at="10:00", wrap_at="09:00"))


def test_validate_rejects_malformed_times() -> None:
    with pytest.raises(ScheduleError):
        validate(_schedule(morning_at="half eight"))


# --- resolution + persistence ----------------------------------------------


def test_defaults_come_from_the_env_when_nothing_is_saved(settings) -> None:
    got = resolve_briefing_schedule(settings)
    assert got.morning_at == settings.briefing_morning_at
    assert got.intraday_every_hours == settings.briefing_intraday_every_hours
    assert got.wrap_at == settings.briefing_wrap_at


def test_saved_schedule_wins_and_survives_a_reload(settings) -> None:
    save_briefing_schedule(
        _schedule(morning_at="07:15", intraday_every_hours=3, wrap_at="19:00"),
        settings=settings,
    )
    prefs._load.cache_clear()  # simulate a fresh process

    got = resolve_briefing_schedule(settings)
    assert got.morning_at == "07:15"
    assert got.intraday_every_hours == 3
    assert got.wrap_at == "19:00"


def test_disabling_persists(settings) -> None:
    save_briefing_schedule(_schedule(enabled=False), settings=settings)
    assert resolve_briefing_schedule(settings).enabled is False


def test_invalid_schedules_are_never_persisted(settings) -> None:
    before = resolve_briefing_schedule(settings)
    with pytest.raises(ScheduleError):
        save_briefing_schedule(_schedule(morning_at="99:99"), settings=settings)
    prefs._load.cache_clear()
    assert resolve_briefing_schedule(settings) == before


def test_a_corrupt_saved_value_falls_back_instead_of_breaking(settings) -> None:
    """A hand-edited prefs file must not stop the scheduler from starting."""
    prefs.set_str("briefing_morning_at", "not a time", path=settings.prefs_file)
    prefs.set_str("briefing_intraday_every_hours", "banana", path=settings.prefs_file)

    got = resolve_briefing_schedule(settings)
    assert got.morning_at == settings.briefing_morning_at
    assert got.intraday_every_hours == settings.briefing_intraday_every_hours


def test_as_dict_is_the_app_shape(settings) -> None:
    got = resolve_briefing_schedule(settings).as_dict(timezone="America/Los_Angeles")
    assert set(got) == {
        "enabled",
        "timezone",
        "morningAt",
        "intradayEveryHours",
        "intradayUntil",
        "wrapAt",
        "editable",
    }
    assert got["editable"] is True


# --- live rescheduling -----------------------------------------------------


def _installed(scheduler) -> dict[str, str]:
    """job id -> cron trigger string, for the briefing jobs only."""
    return {
        j.id: str(j.trigger) for j in scheduler.get_jobs() if j.id.startswith("briefing_")
    }


def test_apply_briefing_schedule_installs_and_replaces_jobs(settings) -> None:
    """Changing the time must move the existing job, not add a second one."""
    from apscheduler.schedulers.background import BackgroundScheduler

    import app.main as main

    scheduler = BackgroundScheduler()  # not started: we only inspect triggers
    main.apply_briefing_schedule(scheduler, settings)
    first = _installed(scheduler)
    assert set(first) == {"briefing_morning", "briefing_intraday", "briefing_wrap"}
    assert "hour='8'" in first["briefing_morning"]

    save_briefing_schedule(_schedule(morning_at="06:45"), settings=settings)
    main.apply_briefing_schedule(scheduler, settings)
    second = _installed(scheduler)

    assert len(second) == 3  # replaced, not duplicated
    assert "hour='6'" in second["briefing_morning"]
    assert "minute='45'" in second["briefing_morning"]


def test_disabling_removes_the_jobs(settings) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler

    import app.main as main

    scheduler = BackgroundScheduler()
    main.apply_briefing_schedule(scheduler, settings)
    assert _installed(scheduler)

    save_briefing_schedule(_schedule(enabled=False), settings=settings)
    main.apply_briefing_schedule(scheduler, settings)
    assert _installed(scheduler) == {}


def test_no_intraday_job_when_the_window_is_empty(settings) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler

    import app.main as main

    save_briefing_schedule(_schedule(intraday_until="09:00"), settings=settings)
    scheduler = BackgroundScheduler()
    main.apply_briefing_schedule(scheduler, settings)

    assert "briefing_intraday" not in _installed(scheduler)
    assert "briefing_morning" in _installed(scheduler)


# --- API -------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app.config as config
    import app.main as main

    prefs._load.cache_clear()
    monkeypatch.setenv("MOBILE_API_ENABLED", "true")
    monkeypatch.setenv("MOBILE_API_TOKEN", "s3cret")
    monkeypatch.setenv("PREFS_FILE", str(tmp_path / "prefs.json"))
    monkeypatch.setenv("BRIEFING_ENABLED", "true")
    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    config.get_settings.cache_clear()
    prefs._load.cache_clear()


AUTH = {"Authorization": "Bearer s3cret"}
BODY = {
    "enabled": True,
    "morningAt": "07:15",
    "intradayEveryHours": 3,
    "intradayUntil": "16:00",
    "wrapAt": "19:00",
}


def test_api_requires_the_token(client) -> None:
    assert client.post("/api/briefing", json=BODY).status_code == 401


def test_api_saves_and_reflects_in_settings(client) -> None:
    res = client.post("/api/briefing", headers=AUTH, json=BODY)
    assert res.status_code == 200
    assert res.json()["morningAt"] == "07:15"

    got = client.get("/api/settings", headers=AUTH).json()["briefing"]
    assert got["morningAt"] == "07:15"
    assert got["intradayEveryHours"] == 3
    assert got["wrapAt"] == "19:00"


def test_api_rejects_an_impossible_schedule(client) -> None:
    # Only the wrap rule should trip here — intradayUntil stays after morning.
    res = client.post(
        "/api/briefing",
        headers=AUTH,
        json={**BODY, "morningAt": "18:00", "intradayUntil": "19:00", "wrapAt": "09:00"},
    )
    assert res.status_code == 400
    assert "wrap-up" in res.json()["detail"]

    # and nothing was persisted
    assert client.get("/api/settings", headers=AUTH).json()["briefing"]["wrapAt"] != "09:00"


def test_api_rejects_a_malformed_time(client) -> None:
    res = client.post("/api/briefing", headers=AUTH, json={**BODY, "morningAt": "8.30"})
    assert res.status_code == 400


# --- timezone --------------------------------------------------------------


def test_briefing_timezone_resolves_and_falls_back() -> None:
    assert resolve_briefing_timezone(Settings(_env_file=None)) == "America/Los_Angeles"
    assert (
        resolve_briefing_timezone(Settings(_env_file=None, briefing_timezone="Not/AZone"))
        == "UTC"
    )
    # Independent of the app-wide timezone.
    s = Settings(_env_file=None, timezone="Asia/Ho_Chi_Minh", briefing_timezone="America/New_York")
    assert resolve_briefing_timezone(s) == "America/New_York"
