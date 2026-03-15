"""
Mortality table tests.

Tests include closed-form verification against synthetic fixtures with known values.
"""

from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def synthetic_table() -> MortalityTable:
    """Load a MortalityTable from synthetic select-and-ultimate fixture."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic Test Table",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


class TestMortalityTableConstruction:
    """Tests for table loading and validation."""

    def test_from_table_array(self, synthetic_table: MortalityTable):
        """Table loads from a pre-built array without error."""
        assert synthetic_table.min_age == 18
        assert synthetic_table.max_age == 60
        assert synthetic_table.select_period_years == 3

    def test_rates_in_unit_interval(self, synthetic_table: MortalityTable):
        """All monthly rates are in [0, 1]."""
        ages = np.arange(18, 61, dtype=np.int32)
        durs = np.zeros_like(ages)
        q = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert np.all(q >= 0.0)
        assert np.all(q <= 1.0)


class TestMortalityTableLookup:
    """Tests for vectorized rate lookups."""

    def test_get_qx_vector_shape(self, synthetic_table: MortalityTable):
        """Output shape must match input ages array shape."""
        ages = np.array([30, 40, 50], dtype=np.int32)
        durs = np.array([0, 12, 24], dtype=np.int32)
        result = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert result.shape == (3,)

    def test_select_rate_lower_than_ultimate_at_same_age(self, synthetic_table: MortalityTable):
        """Select-period rates must be lower than ultimate rates at the same age."""
        ages = np.array([45, 45], dtype=np.int32)
        # dur=0 months → select year 0 (col 0); dur=36+ months → ultimate (col 3)
        durs = np.array([0, 48], dtype=np.int32)
        result = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert result[0] < result[1]

    def test_monthly_rate_less_than_annual(self, synthetic_table: MortalityTable):
        """Monthly q must be less than annual q."""
        # Known annual rate for age 45, dur_1 (select year 0): 0.0040
        q_annual = 0.0040
        q_monthly_expected = 1 - (1 - q_annual) ** (1 / 12)

        ages = np.array([45], dtype=np.int32)
        durs = np.array([0], dtype=np.int32)
        q_monthly = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        np.testing.assert_allclose(q_monthly[0], q_monthly_expected, rtol=1e-10)
        assert q_monthly[0] < q_annual

    def test_closed_form_monthly_conversion(self, synthetic_table: MortalityTable):
        """
        CLOSED-FORM: For q_annual = 0.012 at a specific age:
        q_monthly = 1 - (1 - q_annual)^(1/12)
        """
        q_annual = 0.012
        expected_monthly = 1 - (1 - q_annual) ** (1 / 12)
        np.testing.assert_allclose(expected_monthly, 0.0010050, rtol=1e-3)

    def test_known_rate_age_50_ultimate(self, synthetic_table: MortalityTable):
        """Age 50, ultimate → annual 0.0095, monthly via constant force."""
        q_annual = 0.0095
        expected_monthly = 1 - (1 - q_annual) ** (1 / 12)
        ages = np.array([50], dtype=np.int32)
        durs = np.array([120], dtype=np.int32)  # well past select period
        result = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        np.testing.assert_allclose(result[0], expected_monthly, rtol=1e-10)

    def test_known_rate_age_30_select_year_2(self, synthetic_table: MortalityTable):
        """Age 30, dur 12 months → year 1 → col index 1 (dur_2) → annual 0.0012."""
        q_annual = 0.0012
        expected_monthly = 1 - (1 - q_annual) ** (1 / 12)
        ages = np.array([30], dtype=np.int32)
        # duration 12-23 months → year 1 → col index 1 (dur_2)
        durs = np.array([12], dtype=np.int32)
        result = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        np.testing.assert_allclose(result[0], expected_monthly, rtol=1e-10)

    def test_scalar_convenience(self, synthetic_table: MortalityTable):
        """get_qx_scalar matches get_qx_vector for a single policy."""
        scalar = synthetic_table.get_qx_scalar(
            age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            duration_months=0,
        )
        vec = synthetic_table.get_qx_vector(
            np.array([40], dtype=np.int32),
            Sex.MALE,
            SmokerStatus.NON_SMOKER,
            np.array([0], dtype=np.int32),
        )
        np.testing.assert_allclose(scalar, vec[0], rtol=1e-15)

    def test_duration_beyond_select_uses_ultimate(self, synthetic_table: MortalityTable):
        """Durations beyond select period all return the same ultimate rate."""
        ages = np.array([40, 40, 40], dtype=np.int32)
        # 36 months = 3 years (last select year), 60 months, 120 months
        durs = np.array([36, 60, 120], dtype=np.int32)
        result = synthetic_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        # All should return ultimate rate
        np.testing.assert_allclose(result[0], result[1], rtol=1e-15)
        np.testing.assert_allclose(result[1], result[2], rtol=1e-15)


class TestInterpolation:
    """Tests for age interpolation utilities."""

    def test_constant_force_monthly_conversion_known_value(self):
        """Verify constant force monthly conversion formula directly."""
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
