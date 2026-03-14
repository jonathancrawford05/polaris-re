"""
Date and age utility functions for actuarial projections.

All age calculations follow Age Nearest Birthday (ANB) convention by default,
which is standard for Canadian actuarial work (CIA tables).
Age Last Birthday (ALB) variants are provided for US tables (VBT, CSO).

Implementation Notes for Claude Code:
--------------------------------------
- ANB: (months_since_birth + 6) // 12
- ALB: months_since_birth // 12
- `months_between` is the workhorse — must handle year-boundary crossings correctly.
- `projection_date_index` generates month-end dates for CashFlowResult.time_index.

TODO (Phase 1, Milestone 1.1):
- Implement all functions below.
- Tests in tests/test_core/ must cover edge cases: month boundaries, leap years,
  same-month dates, end-of-month dates.
"""

from datetime import date

import numpy as np

__all__ = ["age_last_birthday", "age_nearest_birthday", "months_between", "projection_date_index"]


def age_nearest_birthday(birth_date: date, as_of_date: date) -> int:
    """
    Compute Age Nearest Birthday (ANB) as of a given date.

    ANB rounds to the nearest integer age — if the person is within 6 months
    of their next birthday, they are considered that age.

    Args:
        birth_date: Date of birth.
        as_of_date: The date at which to calculate age.

    Returns:
        Age nearest birthday as a non-negative integer.

    Examples:
        Born 1980-01-01, as_of 2025-09-01 → 46 (45y 8m → rounds up)
        Born 1980-01-01, as_of 2025-03-01 → 45 (45y 2m → stays)

    TODO: Implement using months_between.
    """
    total_months = months_between(birth_date, as_of_date)
    return (total_months + 6) // 12


def age_last_birthday(birth_date: date, as_of_date: date) -> int:
    """
    Compute Age Last Birthday (ALB) as of a given date.

    ALB is always the most recently completed birthday age.
    Used for US regulatory tables (VBT 2015, 2001 CSO).

    Args:
        birth_date: Date of birth.
        as_of_date: The date at which to calculate age.

    Returns:
        Age last birthday as a non-negative integer.

    TODO: Implement using months_between.
    """
    total_months = months_between(birth_date, as_of_date)
    return total_months // 12


def months_between(start: date, end: date) -> int:
    """
    Compute the number of complete calendar months between two dates.

    Returns 0 if end <= start.

    Args:
        start: Earlier date.
        end: Later date.

    Returns:
        Complete calendar months between the dates.

    Examples:
        months_between(date(2020, 1, 15), date(2025, 3, 15)) == 62
        months_between(date(2020, 1, 15), date(2025, 3, 10)) == 61

    TODO: Implement. Formula: (end.year - start.year) * 12 + (end.month - start.month),
          minus 1 if end.day < start.day (incomplete month), clamped to >= 0.
    """
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(0, months)


def projection_date_index(start_date: date, n_months: int) -> np.ndarray:
    """
    Generate an array of month-end dates for a projection horizon.

    Args:
        start_date: The valuation/projection start date.
        n_months: Number of monthly time steps.

    Returns:
        np.ndarray of dtype datetime64[M], shape (n_months,).

    Example:
        projection_date_index(date(2025, 1, 1), 3)
        → array(['2025-01', '2025-02', '2025-03'], dtype='datetime64[M]')

    TODO: Implement using np.datetime64 arithmetic:
        base = np.datetime64(start_date, 'M')
        return base + np.arange(1, n_months + 1, dtype='timedelta64[M]')
    """
    base = np.datetime64(start_date, "M")
    return base + np.arange(n_months, dtype="timedelta64[M]")
