"""Scheduling arithmetic for comparison schedules. No Django use, so it is unit-testable."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, tzinfo

NONE = "none"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
RECURRENCES = (NONE, DAILY, WEEKLY, MONTHLY)


def _add_months(value: datetime, months: int) -> datetime:
    """Same day of the month ``months`` later; the month's last day when it is shorter."""
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _occurrence(start: datetime, recurrence: str, k: int) -> datetime:
    """The k-th run after ``start`` (naive local wall time)."""
    if recurrence == DAILY:
        return start + timedelta(days=k)
    if recurrence == WEEKLY:
        return start + timedelta(weeks=k)
    return _add_months(start, k)


def next_run_at(start: datetime, recurrence: str, now: datetime, tz: tzinfo) -> datetime | None:
    """The first run time after ``now``, or None when there is none left.

    ``start`` is the first run. A recurring schedule repeats at the same local wall-clock time
    in ``tz`` (unaffected by daylight saving changes): every day, every week, or every month on
    the same day (the last day of shorter months). Runs stay aligned to ``start`` however late
    the previous one finished.
    """
    if recurrence not in RECURRENCES:
        raise ValueError(f"Unknown recurrence {recurrence!r}")
    if start > now:
        return start
    if recurrence == NONE:
        return None
    local_start = start.astimezone(tz).replace(tzinfo=None)
    local_now = now.astimezone(tz).replace(tzinfo=None)
    # Estimate the number of runs elapsed, then step to the first one after now.
    if recurrence == MONTHLY:
        k = max((local_now.year - local_start.year) * 12 + local_now.month - local_start.month, 0)
    else:
        period = timedelta(days=1 if recurrence == DAILY else 7)
        k = max((local_now - local_start) // period, 0)
    while k > 0 and _occurrence(local_start, recurrence, k) > local_now:
        k -= 1
    while True:
        candidate = _occurrence(local_start, recurrence, k).replace(tzinfo=tz)
        if candidate > now:
            return candidate
        k += 1
