"""Unit tests for the once-per-day sync schedule math.

The automatic OneNote sync runs at a fixed local clock time (e.g. 02:00
Europe/Sofia) instead of a seconds interval. These tests pin the next-run
computation, timezone handling, and graceful fallbacks.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sync_worker.ops.daily_schedule import (
    load_timezone,
    next_run_at,
    parse_daily_time,
    seconds_until_next_run,
)

SOFIA = "Europe/Sofia"


def test_parse_daily_time_accepts_valid_and_defaults_invalid() -> None:
    assert parse_daily_time("02:00") == (2, 0)
    assert parse_daily_time("23:59") == (23, 59)
    # Invalid forms fall back to the default rather than crashing the loop.
    assert parse_daily_time("2:5") == (2, 0)
    assert parse_daily_time("25:00") == (2, 0)
    assert parse_daily_time("") == (2, 0)


def test_next_run_is_later_today_when_time_not_yet_passed() -> None:
    now = datetime(2026, 6, 14, 1, 0, tzinfo=ZoneInfo(SOFIA))
    target = next_run_at("02:00", SOFIA, now=now)
    assert target == datetime(2026, 6, 14, 2, 0, tzinfo=ZoneInfo(SOFIA))


def test_next_run_rolls_to_tomorrow_when_time_already_passed() -> None:
    now = datetime(2026, 6, 14, 3, 0, tzinfo=ZoneInfo(SOFIA))
    target = next_run_at("02:00", SOFIA, now=now)
    assert target == datetime(2026, 6, 15, 2, 0, tzinfo=ZoneInfo(SOFIA))


def test_next_run_rolls_over_when_exactly_now() -> None:
    # Exactly at the scheduled time, the *next* run is tomorrow (no double-run).
    now = datetime(2026, 6, 14, 2, 0, tzinfo=ZoneInfo(SOFIA))
    target = next_run_at("02:00", SOFIA, now=now)
    assert target == datetime(2026, 6, 15, 2, 0, tzinfo=ZoneInfo(SOFIA))


def test_next_run_converts_a_utc_now_into_the_target_timezone() -> None:
    # 00:30 UTC == 03:30 Sofia (UTC+3 in summer), which is past 02:00 Sofia,
    # so the next run is tomorrow at 02:00 Sofia.
    now = datetime(2026, 6, 14, 0, 30, tzinfo=ZoneInfo("UTC"))
    target = next_run_at("02:00", SOFIA, now=now)
    assert target == datetime(2026, 6, 15, 2, 0, tzinfo=ZoneInfo(SOFIA))


def test_seconds_until_next_run_is_positive_and_bounded() -> None:
    now = datetime(2026, 6, 14, 1, 0, tzinfo=ZoneInfo(SOFIA))
    seconds = seconds_until_next_run("02:00", SOFIA, now=now)
    assert seconds == 3600.0


def test_unknown_timezone_falls_back_to_utc() -> None:
    tz = load_timezone("Not/AZone")
    assert tz.utcoffset(datetime(2026, 6, 14)) is not None
    # Falls back to UTC, so a fixed UTC 'now' yields a UTC-anchored target.
    now = datetime(2026, 6, 14, 1, 0, tzinfo=ZoneInfo("UTC"))
    target = next_run_at("02:00", "Not/AZone", now=now)
    assert target.hour == 2 and target.utcoffset().total_seconds() == 0
