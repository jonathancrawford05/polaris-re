"""Tests for interpolation utilities."""

import numpy as np

from polaris_re.utils.interpolation import (
    constant_force_interpolate_rates,
    linear_interpolate_rates,
)


class TestConstantForceInterpolation:
    """Tests for constant force (exponential) interpolation."""

    def test_monthly_conversion_known_value(self):
        """q_annual=0.012 → q_monthly ≈ 0.001005."""
        q = np.array([0.012], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=1 / 12)
        expected = 1 - (1 - 0.012) ** (1 / 12)
        np.testing.assert_allclose(result[0], expected, rtol=1e-10)

    def test_fraction_one_returns_annual(self):
        """At fraction=1.0, returns the original annual rate."""
        q = np.array([0.05, 0.10, 0.20], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=1.0)
        np.testing.assert_allclose(result, q, rtol=1e-10)

    def test_fraction_zero_returns_zero(self):
        """At fraction=0.0, zero time → zero rate."""
        q = np.array([0.05, 0.10], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=0.0)
        np.testing.assert_allclose(result, 0.0, atol=1e-15)

    def test_vectorized_multiple_rates(self):
        """Operates element-wise on arrays."""
        q = np.array([0.0, 0.01, 0.05, 0.10, 1.0], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=1 / 12)
        expected = 1 - (1 - q) ** (1 / 12)
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_quarterly_conversion(self):
        """fraction=0.25 gives quarterly rate."""
        q = np.array([0.04], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=0.25)
        expected = 1 - (1 - 0.04) ** 0.25
        np.testing.assert_allclose(result[0], expected, rtol=1e-10)

    def test_monthly_rate_less_than_annual(self):
        """Monthly rate must be less than annual for any q in (0, 1)."""
        q = np.array([0.001, 0.01, 0.05, 0.10, 0.50], dtype=np.float64)
        monthly = constant_force_interpolate_rates(q, fraction=1 / 12)
        assert np.all(monthly < q)


class TestLinearInterpolation:
    """Tests for UDD (linear) interpolation."""

    def test_fraction_zero_returns_lower(self):
        """At fraction=0, returns q_lower."""
        q_low = np.array([0.01, 0.05], dtype=np.float64)
        q_up = np.array([0.02, 0.06], dtype=np.float64)
        frac = np.array([0.0, 0.0], dtype=np.float64)
        result = linear_interpolate_rates(q_low, q_up, frac)
        np.testing.assert_allclose(result, q_low, rtol=1e-10)

    def test_fraction_one_returns_upper(self):
        """At fraction=1, returns q_upper."""
        q_low = np.array([0.01], dtype=np.float64)
        q_up = np.array([0.02], dtype=np.float64)
        frac = np.array([1.0], dtype=np.float64)
        result = linear_interpolate_rates(q_low, q_up, frac)
        np.testing.assert_allclose(result, q_up, rtol=1e-10)

    def test_midpoint_interpolation(self):
        """At fraction=0.5, returns average."""
        q_low = np.array([0.01, 0.10], dtype=np.float64)
        q_up = np.array([0.03, 0.20], dtype=np.float64)
        frac = np.array([0.5, 0.5], dtype=np.float64)
        result = linear_interpolate_rates(q_low, q_up, frac)
        expected = np.array([0.02, 0.15], dtype=np.float64)
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_result_clipped_to_unit_interval(self):
        """Rates are clipped to [0, 1]."""
        q_low = np.array([0.99], dtype=np.float64)
        q_up = np.array([1.05], dtype=np.float64)
        frac = np.array([0.5], dtype=np.float64)
        result = linear_interpolate_rates(q_low, q_up, frac)
        assert np.all(result <= 1.0)
        assert np.all(result >= 0.0)
