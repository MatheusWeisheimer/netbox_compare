from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from netbox_compare.schedule import next_run_at

SP = ZoneInfo("America/Sao_Paulo")
BERLIN = ZoneInfo("Europe/Berlin")
START = datetime(2026, 1, 1, 3, 0, tzinfo=SP)


@pytest.mark.parametrize("recurrence", ["none", "daily", "weekly", "monthly"])
def test_future_start_is_the_next_run(recurrence):
    assert next_run_at(START, recurrence, START - timedelta(days=1), SP) == START


def test_one_off_has_no_run_after_its_start():
    assert next_run_at(START, "none", START, SP) is None
    assert next_run_at(START, "none", START + timedelta(days=3), SP) is None


def test_daily_stays_aligned_to_start():
    now = datetime(2026, 3, 10, 12, 0, tzinfo=SP)
    assert next_run_at(START, "daily", now, SP) == datetime(2026, 3, 11, 3, 0, tzinfo=SP)
    now = datetime(2026, 3, 10, 2, 59, tzinfo=SP)
    assert next_run_at(START, "daily", now, SP) == datetime(2026, 3, 10, 3, 0, tzinfo=SP)


def test_now_exactly_on_a_run_time_moves_to_the_next_one():
    assert next_run_at(START, "daily", START, SP) == START + timedelta(days=1)


def test_weekly_keeps_the_weekday():
    now = datetime(2026, 2, 3, 0, 0, tzinfo=SP)  # START is a Thursday
    result = next_run_at(START, "weekly", now, SP)
    assert result == datetime(2026, 2, 5, 3, 0, tzinfo=SP)
    assert result.weekday() == START.weekday()


def test_monthly_clamps_to_the_last_day_and_returns_to_the_start_day():
    start = datetime(2026, 1, 31, 3, 0, tzinfo=SP)
    feb = next_run_at(start, "monthly", datetime(2026, 2, 1, tzinfo=SP), SP)
    assert feb == datetime(2026, 2, 28, 3, 0, tzinfo=SP)
    mar = next_run_at(start, "monthly", feb, SP)
    assert mar == datetime(2026, 3, 31, 3, 0, tzinfo=SP)
    apr = next_run_at(start, "monthly", datetime(2026, 4, 15, tzinfo=SP), SP)
    assert apr == datetime(2026, 4, 30, 3, 0, tzinfo=SP)


def test_monthly_across_years():
    now = datetime(2027, 12, 20, tzinfo=SP)
    assert next_run_at(START, "monthly", now, SP) == datetime(2028, 1, 1, 3, 0, tzinfo=SP)


def test_wall_clock_time_survives_daylight_saving_changes():
    start = datetime(2026, 3, 1, 3, 0, tzinfo=BERLIN)  # winter time, UTC+1
    now = datetime(2026, 4, 10, 12, 0, tzinfo=BERLIN)  # summer time, UTC+2
    result = next_run_at(start, "daily", now, BERLIN)
    assert result == datetime(2026, 4, 11, 3, 0, tzinfo=BERLIN)
    assert result.utcoffset() == timedelta(hours=2)


def test_start_given_in_another_timezone():
    start = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)  # 03:00 in Sao Paulo
    now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    assert next_run_at(start, "daily", now, SP) == datetime(2026, 1, 6, 3, 0, tzinfo=SP)


def test_unknown_recurrence():
    with pytest.raises(ValueError):
        next_run_at(START, "hourly", START, SP)
