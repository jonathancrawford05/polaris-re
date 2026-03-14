"""
Mortality table tests.

CRITICAL: These tests must include closed-form verification against known table values.
The best way to verify: pick a specific age/sex/smoker from the published table,
hardcode the expected rate, and assert the loader returns that exact value.

Reference values (to be confirmed against published tables when CSV files are available):
  SOA VBT 2015, Male NS, Age 45, Select Year 1: q ≈ 0.000710  (illustrative)
  CIA 2014, Male NS, Age 50, Ultimate: q ≈ 0.003240            (illustrative)

NOTE: Exact values must be verified against the actual published tables.
      Do not use these illustrative values as ground truth.
"""

import pytest
import numpy as np

from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.policy import Sex, SmokerStatus


class TestMortalityTableConstruction:
    """Tests for table loading and validation."""

    @pytest.mark.xfail(reason="MortalityTable.load() not yet implemented.", strict=False)
    def test_load_soa_vbt_2015(self, tmp_path):
        """Table loads without error given a valid CSV fixture."""
        pytest.skip("Requires CSV fixture and implementation")

    @pytest.mark.xfail(reason="MortalityTable.load() not yet implemented.", strict=False)
    def test_rates_in_unit_interval(self, tmp_path):
        """All loaded rates must be in [0, 1]."""
        pytest.skip("Requires CSV fixture and implementation")

    @pytest.mark.xfail(reason="MortalityTable.load() not yet implemented.", strict=False)
    def test_rates_non_decreasing_at_old_ages(self, tmp_path):
        """Ultimate rates should be non-decreasing above age 80 (standard actuarial expectation)."""
        pytest.skip("Requires CSV fixture and implementation")


class TestMortalityTableLookup:
    """Tests for vectorised rate lookups."""

    @pytest.mark.xfail(reason="MortalityTable.get_qx_vector() not yet implemented.", strict=False)
    def test_get_qx_vector_shape(self):
        """Output shape must match input ages array shape."""
        pytest.skip("Requires implementation")

    @pytest.mark.xfail(reason="Not yet implemented.", strict=False)
    def test_select_rate_lower_than_ultimate_at_same_age(self):
        """
        ACTUARIAL INVARIANT: Select-period rates must be lower than ultimate rates
        for the same attained age. This is the definition of select mortality.
        """
        pytest.skip("Requires implementation")

    @pytest.mark.xfail(reason="Not yet implemented.", strict=False)
    def test_monthly_rate_less_than_annual(self):
        """
        Monthly q must be less than annual q.
        q_monthly = 1 - (1 - q_annual)^(1/12) < q_annual for q_annual in (0, 1).
        """
        pytest.skip("Requires implementation")

    @pytest.mark.xfail(reason="Not yet implemented.", strict=False)
    def test_closed_form_monthly_conversion(self):
        """
        CLOSED-FORM: For q_annual = 0.012:
        q_monthly = 1 - (1 - 0.012)^(1/12) = 1 - 0.988^(1/12)
        Expected: ≈ 0.001005  (compute independently to verify)
        """
        q_annual = 0.012
        expected_monthly = 1 - (1 - q_annual) ** (1 / 12)
        # Once implemented, assert get_qx_vector returns this monthly rate
        np.testing.assert_allclose(expected_monthly, 0.0010050, rtol=1e-4)
        pytest.skip("Loader not yet implemented — formula verified in isolation above")


class TestInterpolation:
    """Tests for age interpolation utilities."""

    def test_constant_force_monthly_conversion_known_value(self):
        """
        CLOSED-FORM: Verify constant force monthly conversion formula directly.
        This test does NOT require MortalityTable implementation — tests the util.
        """
        from polaris_re.utils.interpolation import constant_force_interpolate_rates
        q_annual = np.array([0.012], dtype=np.float64)
        q_monthly = constant_force_interpolate_rates(q_annual, fraction=1 / 12)
        expected = 1 - (1 - 0.012) ** (1 / 12)
        np.testing.assert_allclose(q_monthly[0], expected, rtol=1e-10)

    def test_constant_force_at_fraction_one_returns_annual(self):
        """At fraction=1, constant force conversion should return the original annual rate."""
        from polaris_re.utils.interpolation import constant_force_interpolate_rates
        q = np.array([0.05, 0.10, 0.20], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=1.0)
        np.testing.assert_allclose(result, q, rtol=1e-10)

    def test_constant_force_at_fraction_zero_returns_zero(self):
        """At fraction=0 (zero time), no deaths can occur → rate = 0."""
        from polaris_re.utils.interpolation import constant_force_interpolate_rates
        q = np.array([0.05, 0.10], dtype=np.float64)
        result = constant_force_interpolate_rates(q, fraction=0.0)
        np.testing.assert_allclose(result, 0.0, atol=1e-15)
