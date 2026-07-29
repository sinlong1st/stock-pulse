"""Tests for the briefing schedule computation (Briefing plan, step E)."""

from app.config import Settings, resolve_briefing_timezone
from app.jobs.briefing import intraday_hours, parse_hhmm


def test_parse_hhmm() -> None:
    assert parse_hhmm("08:30") == (8, 30)
    assert parse_hhmm("18:00") == (18, 0)


def test_intraday_hours_default() -> None:
    s = Settings(_env_file=None)  # morning 08:30, every 2h, until 16:30
    assert intraday_hours(s) == [10, 12, 14, 16]


def test_intraday_hours_custom() -> None:
    s = Settings(
        _env_file=None,
        briefing_morning_at="09:00",
        briefing_intraday_every_hours=3,
        briefing_intraday_until="18:00",
    )
    assert intraday_hours(s) == [12, 15, 18]


def test_intraday_hours_empty_when_until_before_first() -> None:
    s = Settings(
        _env_file=None,
        briefing_morning_at="08:30",
        briefing_intraday_every_hours=2,
        briefing_intraday_until="09:00",  # first intraday (10:30) is past this
    )
    assert intraday_hours(s) == []


def test_briefing_timezone_resolves_and_falls_back() -> None:
    assert resolve_briefing_timezone(Settings(_env_file=None)) == "America/Los_Angeles"
    assert (
        resolve_briefing_timezone(Settings(_env_file=None, briefing_timezone="Not/AZone"))
        == "UTC"
    )
    # Independent of the app-wide timezone.
    s = Settings(_env_file=None, timezone="Asia/Ho_Chi_Minh", briefing_timezone="America/New_York")
    assert resolve_briefing_timezone(s) == "America/New_York"
