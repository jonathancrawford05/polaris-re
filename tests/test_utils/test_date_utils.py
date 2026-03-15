"""Tests for date and age utility functions."""

from datetime import date

import numpy as np

from polaris_re.utils.date_utils import (
    age_last_birthday,
    age_nearest_birthday,
    months_between,
    projection_date_index,
)


class TestMonthsBetween:
    """Tests for months_between calculation."""

    def test_exact_month_boundary(self):
        """Same day of month → exact month count."""
        assert months_between(date(2020, 1, 15), date(2025, 3, 15)) == 62

    def test_incomplete_month(self):
        """End day before start day → one fewer month."""
        assert months_between(date(2020, 1, 15), date(2025, 3, 10)) == 61

    def test_same_date_returns_zero(self):
        """Same date → 0 months."""
        assert months_between(date(2020, 6, 1), date(2020, 6, 1)) == 0

    def test_end_before_start_returns_zero(self):
        """End before start → 0."""
        assert months_between(date(2025, 1, 1), date(2020, 1, 1)) == 0

    def test_one_month_exact(self):
        assert months_between(date(2020, 1, 1), date(2020, 2, 1)) == 1

    def test_one_day_short_of_month(self):
        assert months_between(date(2020, 1, 15), date(2020, 2, 14)) == 0

    def test_leap_year_feb_29(self):
        """Leap year: Jan 31 → Feb 29 is not a full month (29 < 31)."""
        assert months_between(date(2020, 1, 31), date(2020, 2, 29)) == 0

    def test_year_boundary(self):
        """Crossing year boundary."""
        assert months_between(date(2019, 11, 1), date(2020, 2, 1)) == 3

    def test_full_year(self):
        assert months_between(date(2020, 1, 1), date(2021, 1, 1)) == 12

    def test_end_of_month_dates(self):
        """March 31 → April 30: end day < start day."""
        assert months_between(date(2020, 3, 31), date(2020, 4, 30)) == 0

    def test_first_of_month(self):
        """Both on first of month."""
        assert months_between(date(2020, 1, 1), date(2020, 7, 1)) == 6


class TestAgeNearestBirthday:
    """Tests for ANB age calculation."""

    def test_just_past_birthday(self):
        """Born Jan 1 1980, as_of Mar 1 2025 → 45y 2m → ANB 45."""
        assert age_nearest_birthday(date(1980, 1, 1), date(2025, 3, 1)) == 45

    def test_rounds_up_past_six_months(self):
        """Born Jan 1 1980, as_of Sep 1 2025 → 45y 8m → ANB 46."""
        assert age_nearest_birthday(date(1980, 1, 1), date(2025, 9, 1)) == 46

    def test_exact_half_year_rounds_up(self):
        """At exactly 6 months past birthday, rounds up."""
        assert age_nearest_birthday(date(1980, 1, 1), date(2025, 7, 1)) == 46

    def test_newborn(self):
        """Same date → ANB 0."""
        assert age_nearest_birthday(date(2025, 1, 1), date(2025, 1, 1)) == 0

    def test_almost_one_year(self):
        """11 months → ANB 1 (rounds up at 6 months)."""
        assert age_nearest_birthday(date(2024, 1, 1), date(2024, 12, 1)) == 1

    def test_five_months(self):
        """5 months → ANB 0 (below 6 months)."""
        assert age_nearest_birthday(date(2024, 1, 1), date(2024, 6, 1)) == 0


class TestAgeLastBirthday:
    """Tests for ALB age calculation."""

    def test_just_past_birthday(self):
        """45y 2m → ALB 45."""
        assert age_last_birthday(date(1980, 1, 1), date(2025, 3, 1)) == 45

    def test_past_six_months_no_rounding(self):
        """45y 8m → ALB 45 (no rounding)."""
        assert age_last_birthday(date(1980, 1, 1), date(2025, 9, 1)) == 45

    def test_exact_birthday(self):
        """Exact birthday → ALB = years elapsed."""
        assert age_last_birthday(date(1980, 1, 1), date(2025, 1, 1)) == 45

    def test_one_day_before_birthday(self):
        """One day before 45th birthday → ALB 44."""
        assert age_last_birthday(date(1980, 6, 15), date(2025, 6, 14)) == 44

    def test_newborn(self):
        assert age_last_birthday(date(2025, 1, 1), date(2025, 1, 1)) == 0


class TestProjectionDateIndex:
    """Tests for projection date array generation."""

    def test_basic_three_months(self):
        result = projection_date_index(date(2025, 1, 1), 3)
        assert result.dtype == np.dtype("datetime64[M]")
        assert len(result) == 3
        expected = np.array(["2025-01", "2025-02", "2025-03"], dtype="datetime64[M]")
        np.testing.assert_array_equal(result, expected)

    def test_year_boundary_crossing(self):
        result = projection_date_index(date(2025, 11, 1), 4)
        expected = np.array(["2025-11", "2025-12", "2026-01", "2026-02"], dtype="datetime64[M]")
        np.testing.assert_array_equal(result, expected)

    def test_single_month(self):
        result = projection_date_index(date(2025, 6, 15), 1)
        assert len(result) == 1

    def test_shape(self):
        result = projection_date_index(date(2025, 1, 1), 120)
        assert result.shape == (120,)
