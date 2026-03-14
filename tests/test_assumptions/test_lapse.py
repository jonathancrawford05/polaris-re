"""Tests for LapseAssumption duration-based lapse rates."""

import numpy as np
import pytest

from polaris_re.assumptions.lapse import LapseAssumption


class TestLapseAssumptionConstruction:
    """Tests for LapseAssumption.from_duration_table."""

    def test_basic_construction(self):
        """Constructs from a simple duration table."""
        table = {1: 0.10, 2: 0.08, 3: 0.06, "ultimate": 0.03}
        lapse = LapseAssumption.from_duration_table(table)
        assert lapse.select_period_years == 3
        assert lapse.select_rates == (0.10, 0.08, 0.06)
        np.testing.assert_allclose(lapse.ultimate_rate, 0.03)

    def test_missing_ultimate_raises(self):
        """Missing 'ultimate' key raises ValueError."""
        with pytest.raises(ValueError, match="ultimate"):
            LapseAssumption.from_duration_table({1: 0.10, 2: 0.08})

    def test_rate_out_of_range_raises(self):
        """Rates outside [0, 1] raise ValueError."""
        with pytest.raises(ValueError, match="outside"):
            LapseAssumption.from_duration_table({1: 1.5, "ultimate": 0.03})

    def test_single_select_year(self):
        """Single select year + ultimate."""
        lapse = LapseAssumption.from_duration_table({1: 0.15, "ultimate": 0.04})
        assert lapse.select_period_years == 1
        assert lapse.select_rates == (0.15,)


class TestLapseVector:
    """Tests for get_lapse_vector vectorized lookup."""

    @pytest.fixture()
    def lapse(self) -> LapseAssumption:
        return LapseAssumption.from_duration_table({1: 0.10, 2: 0.08, 3: 0.06, "ultimate": 0.03})

    def test_select_year_1_rate(self, lapse: LapseAssumption):
        """Duration 0-11 months → policy year 1 → annual 0.10."""
        durs = np.array([0, 6, 11], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        expected_monthly = 1 - (1 - 0.10) ** (1 / 12)
        np.testing.assert_allclose(result, expected_monthly, rtol=1e-10)

    def test_select_year_2_rate(self, lapse: LapseAssumption):
        """Duration 12-23 months → policy year 2 → annual 0.08."""
        durs = np.array([12, 18, 23], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        expected_monthly = 1 - (1 - 0.08) ** (1 / 12)
        np.testing.assert_allclose(result, expected_monthly, rtol=1e-10)

    def test_ultimate_rate(self, lapse: LapseAssumption):
        """Duration beyond select period → ultimate rate."""
        durs = np.array([36, 60, 120], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        expected_monthly = 1 - (1 - 0.03) ** (1 / 12)
        np.testing.assert_allclose(result, expected_monthly, rtol=1e-10)

    def test_monthly_rate_less_than_annual(self, lapse: LapseAssumption):
        """Monthly lapse rate must be less than annual."""
        durs = np.array([0, 12, 24, 36], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        annual_rates = np.array([0.10, 0.08, 0.06, 0.03])
        assert np.all(result < annual_rates)

    def test_vectorized_output_shape(self, lapse: LapseAssumption):
        """Output shape matches input."""
        durs = np.array([0, 12, 24, 36, 48], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        assert result.shape == (5,)

    def test_decreasing_select_rates(self, lapse: LapseAssumption):
        """Select rates should decrease (year 1 > year 2 > year 3 > ultimate)."""
        durs = np.array([0, 12, 24, 36], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        assert result[0] > result[1] > result[2] > result[3]

    def test_closed_form_monthly_conversion(self, lapse: LapseAssumption):
        """Verify monthly conversion: w_monthly = 1 - (1 - 0.10)^(1/12)."""
        w_annual = 0.10
        expected = 1 - (1 - w_annual) ** (1 / 12)
        durs = np.array([0], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        np.testing.assert_allclose(result[0], expected, rtol=1e-10)
