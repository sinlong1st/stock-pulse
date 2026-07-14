"""Quiet hours: decide whether a non-urgent alert should be held for now.

During the configured daily window (in the user's local timezone), alerts
below `QUIET_HOURS_MIN_IMPORTANCE` are held — the delivery step skips them
so they stay PENDING and go out on the next send after the window ends.
"""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.alerts.policy import IMPORTANCE_ORDER
from app.config import Settings, get_settings, resolve_timezone

logger = logging.getLogger("stockpulse.alerts.quiet_hours")


def _parse_hhmm(value: str) -> time:
    hour, _, minute = value.strip().partition(":")
    return time(int(hour), int(minute or 0))


def is_quiet_now(settings: Settings | None = None, now: datetime | None = None) -> bool:
    """True if the current local time is inside the quiet-hours window."""
    settings = settings or get_settings()
    if not settings.quiet_hours_enabled:
        return False

    tz = ZoneInfo(resolve_timezone(settings))
    current = (now or datetime.now(tz)).astimezone(tz).time()
    start = _parse_hhmm(settings.quiet_hours_start)
    end = _parse_hhmm(settings.quiet_hours_end)

    if start <= end:
        return start <= current < end
    # Window crosses midnight (e.g. 22:00–07:00).
    return current >= start or current < end


def should_hold(importance: str, settings: Settings | None = None, now: datetime | None = None) -> bool:
    """True if an alert of this importance should be held during quiet hours."""
    settings = settings or get_settings()
    if not is_quiet_now(settings, now):
        return False
    floor = IMPORTANCE_ORDER.get(settings.quiet_hours_min_importance.upper(), 3)
    return IMPORTANCE_ORDER.get(importance, 0) < floor
