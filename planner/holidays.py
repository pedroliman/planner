"""Company holidays observed by the planner.

Holiday dates are excluded from scheduling and from availability/allocation
analysis. Update HOLIDAYS each year as new dates are announced.
"""

from datetime import date

HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2026
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # Martin Luther King, Jr. Day
        date(2026, 5, 25),   # Memorial Day
        date(2026, 6, 19),   # Juneteenth
        date(2026, 7, 3),    # Independence Day
        date(2026, 9, 7),    # Labor Day
        date(2026, 11, 11),  # Veterans Day
        date(2026, 11, 26),  # Thanksgiving Day
        date(2026, 12, 25),  # Christmas Day
        # 2027
        date(2027, 1, 1),    # New Year's Day
        date(2027, 1, 18),   # Martin Luther King, Jr. Day
        date(2027, 5, 31),   # Memorial Day
        date(2027, 6, 18),   # Juneteenth (Observed)
        date(2027, 7, 5),    # Independence Day (Observed)
        date(2027, 9, 6),    # Labor Day
        date(2027, 11, 11),  # Veterans Day
        date(2027, 11, 25),  # Thanksgiving Day
        date(2027, 12, 24),  # Christmas Day (Observed)
    }
)


def is_holiday(d: date) -> bool:
    """Return True if d is a recognized company holiday."""
    return d in HOLIDAYS


def is_workday(d: date) -> bool:
    """Return True if d is a weekday and not a holiday."""
    return d.weekday() < 5 and d not in HOLIDAYS
