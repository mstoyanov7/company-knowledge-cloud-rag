"""Compute the next run time for a once-per-day schedule.

The automatic OneNote sync runs once per day at a fixed local clock time
(e.g. 02:00 Europe/Sofia) rather than on a seconds interval. Keeping the time
math here makes it unit-testable without a database or a running worker.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("sync_worker.ops.daily_schedule")

_DAILY_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_DAILY_TIME = "02:00"


def parse_daily_time(value: str) -> tuple[int, int]:
    """Return (hour, minute) for an "HH:MM" string, falling back to 02:00."""
    candidate = (value or "").strip()
    if not _DAILY_TIME_RE.match(candidate):
        logger.warning("event=daily_time_invalid value=%r action=using_default default=%s", value, DEFAULT_DAILY_TIME)
        candidate = DEFAULT_DAILY_TIME
    hour, minute = candidate.split(":")
    return int(hour), int(minute)


def load_timezone(name: str) -> ZoneInfo | timezone:
    """Load an IANA timezone, falling back to UTC when it cannot be resolved.

    Falling back keeps the worker running on hosts without the tz database
    instead of crashing the sync loop.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        logger.warning("event=timezone_unavailable name=%r action=using_utc", name)
        return timezone.utc


def next_run_at(daily_time: str, tz_name: str, *, now: datetime | None = None) -> datetime:
    """The next datetime (tz-aware) at which the daily time occurs after ``now``.

    If the time has already passed today (or is exactly now), the next run is
    the same time tomorrow. DST transitions are handled by zoneinfo.
    """
    tz = load_timezone(tz_name)
    current = (now.astimezone(tz) if now is not None else datetime.now(tz))
    hour, minute = parse_daily_time(daily_time)
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return target


def seconds_until_next_run(daily_time: str, tz_name: str, *, now: datetime | None = None) -> float:
    """Seconds from ``now`` until the next occurrence of the daily time."""
    tz = load_timezone(tz_name)
    current = (now.astimezone(tz) if now is not None else datetime.now(tz))
    return max(0.0, (next_run_at(daily_time, tz_name, now=current) - current).total_seconds())
