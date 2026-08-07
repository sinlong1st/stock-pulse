"""The briefing schedule, editable at runtime.

Times used to come straight from the env, which meant changing when your
briefings arrive required an SSH session and a container restart. They now live
in the runtime prefs store (like the output language), with the env values as
defaults — so the app can edit them and the scheduler can pick the change up
without a restart.

Reading is cheap and safe to call anywhere. Writing validates first: a bad time
string here would take out the scheduler at startup, so nothing invalid is ever
persisted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from app.config import Settings, get_settings
from app.prefs import get_flag, get_str, set_flag, set_str

logger = logging.getLogger("stockpulse.briefing.schedule")

# Pref keys. Namespaced so they can't collide with other runtime prefs.
_ENABLED = "briefing_enabled"
_MORNING = "briefing_morning_at"
_EVERY = "briefing_intraday_every_hours"
_UNTIL = "briefing_intraday_until"
_WRAP = "briefing_wrap_at"

MAX_EVERY_HOURS = 12


class ScheduleError(ValueError):
    """The requested schedule is not usable."""


@dataclass(frozen=True)
class BriefingSchedule:
    enabled: bool
    morning_at: str  # "HH:MM"
    intraday_every_hours: int
    intraday_until: str  # "HH:MM"
    wrap_at: str  # "HH:MM"

    def as_dict(self, *, timezone: str, editable: bool = True) -> dict:
        return {
            "enabled": self.enabled,
            "timezone": timezone,
            "morningAt": self.morning_at,
            "intradayEveryHours": self.intraday_every_hours,
            "intradayUntil": self.intraday_until,
            "wrapAt": self.wrap_at,
            "editable": editable,
        }


def parse_hhmm(value: str) -> tuple[int, int]:
    """Parse "HH:MM" into (hour, minute). Raises ScheduleError if malformed."""
    try:
        hour_s, minute_s = str(value).strip().split(":")
        hour, minute = int(hour_s), int(minute_s)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ScheduleError(f"'{value}' is not a time like 08:30.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ScheduleError(f"'{value}' is not a real time of day.")
    return hour, minute


def _minutes(value: str) -> int:
    hour, minute = parse_hhmm(value)
    return hour * 60 + minute


def validate(schedule: BriefingSchedule) -> BriefingSchedule:
    """Check a schedule is usable, returning it normalised. Raises ScheduleError.

    Nothing invalid may be persisted: these values build cron triggers at
    startup, so a bad one would stop the scheduler from coming up at all.
    """
    morning = _minutes(schedule.morning_at)
    until = _minutes(schedule.intraday_until)
    wrap = _minutes(schedule.wrap_at)

    if not 1 <= schedule.intraday_every_hours <= MAX_EVERY_HOURS:
        raise ScheduleError(f"Check in every 1 to {MAX_EVERY_HOURS} hours.")
    if until < morning:
        raise ScheduleError("Intraday check-ins can't end before the morning briefing.")
    if wrap < morning:
        raise ScheduleError("The wrap-up can't come before the morning briefing.")

    def norm(value: str) -> str:
        hour, minute = parse_hhmm(value)
        return f"{hour:02d}:{minute:02d}"

    return replace(
        schedule,
        morning_at=norm(schedule.morning_at),
        intraday_until=norm(schedule.intraday_until),
        wrap_at=norm(schedule.wrap_at),
    )


def resolve_briefing_schedule(settings: Settings | None = None) -> BriefingSchedule:
    """The schedule in force: saved prefs where present, else the env defaults.

    Falls back to the env value for any pref that is missing *or corrupt*, so a
    hand-edited prefs file can't stop the scheduler from starting.
    """
    settings = settings or get_settings()

    def time_pref(key: str, default: str) -> str:
        saved = get_str(key, settings)
        if not saved:
            return default
        try:
            parse_hhmm(saved)
        except ScheduleError:
            logger.warning("Ignoring invalid saved %s=%r; using %r.", key, saved, default)
            return default
        return saved

    every = get_str(_EVERY, settings)
    try:
        every_hours = int(every) if every else settings.briefing_intraday_every_hours
    except (TypeError, ValueError):
        every_hours = settings.briefing_intraday_every_hours
    every_hours = max(1, min(MAX_EVERY_HOURS, every_hours))

    return BriefingSchedule(
        enabled=get_flag(_ENABLED, settings.briefing_enabled, settings),
        morning_at=time_pref(_MORNING, settings.briefing_morning_at),
        intraday_every_hours=every_hours,
        intraday_until=time_pref(_UNTIL, settings.briefing_intraday_until),
        wrap_at=time_pref(_WRAP, settings.briefing_wrap_at),
    )


def save_briefing_schedule(
    schedule: BriefingSchedule, *, settings: Settings | None = None
) -> BriefingSchedule:
    """Validate and persist. Returns the normalised schedule that was saved."""
    settings = settings or get_settings()
    valid = validate(schedule)
    path = settings.prefs_file

    set_flag(_ENABLED, valid.enabled, path=path)
    set_str(_MORNING, valid.morning_at, path=path)
    set_str(_EVERY, str(valid.intraday_every_hours), path=path)
    set_str(_UNTIL, valid.intraday_until, path=path)
    set_str(_WRAP, valid.wrap_at, path=path)

    logger.info(
        "Briefing schedule saved: enabled=%s morning=%s every=%sh until=%s wrap=%s",
        valid.enabled,
        valid.morning_at,
        valid.intraday_every_hours,
        valid.intraday_until,
        valid.wrap_at,
    )
    return valid


def intraday_hours(schedule: BriefingSchedule) -> list[int]:
    """Hours the intraday updates fire at (anchored after the morning brief).

    e.g. morning 08:30, every 2h, until 16:30 -> [10, 12, 14, 16].
    """
    start_h, _ = parse_hhmm(schedule.morning_at)
    until_h, _ = parse_hhmm(schedule.intraday_until)
    every = max(1, schedule.intraday_every_hours)
    return list(range(start_h + every, until_h + 1, every))
