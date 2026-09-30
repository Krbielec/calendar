"""Date rules for monthly, bimonthly, quarterly, and annual events."""

import calendar
from datetime import date


def _month_date(anchor: date, month_offset: int) -> date:
    month_index = anchor.year * 12 + anchor.month - 1 + month_offset
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def due_dates(anchor: date, interval_months: int, start: date, end: date) -> list[date]:
    """List occurrences in an inclusive range, always anchored to the original day."""
    if end < start or interval_months not in (0, 1, 2, 3, 12):
        return []
    if interval_months == 0:
        return [anchor] if start <= anchor <= end else []

    first_month = anchor.year * 12 + anchor.month - 1
    start_month = start.year * 12 + start.month - 1
    step = max(0, (start_month - first_month) // interval_months)
    while _month_date(anchor, step * interval_months) < start:
        step += 1

    dates: list[date] = []
    while True:
        occurrence = _month_date(anchor, step * interval_months)
        if occurrence > end:
            return dates
        dates.append(occurrence)
        step += 1
