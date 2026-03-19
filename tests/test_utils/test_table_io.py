"""Tests for mortality and lapse table CSV loading and vectorized lookups."""

from pathlib import Path

import numpy as np
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.utils.table_io import (
    LapseTableArray,
    MortalityTableArray,
    load_lapse_csv,
    load_mortality_csv,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestLoadMortalityCSV:
    """Tests for CSV loading and validation."""

    def test_load_select_ultimate_table(self):
        """Loads a select-and-ultimate table successfully."""
        table = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        assert table.min_age == 18
        assert table.max_age == 60
        assert table.select_period == 3
        assert table.rates.shape == (43, 4)  # 43 ages, 3 select + 1 ultimate

    def test_load_ultimate_only_table(self):
        """Loads an ultimate-only table successfully."""
        table = load_mortality_csv(
            FIXTURES / "synthetic_ultimate_only.csv",
            select_period=0,
            min_age=18,
            max_age=60,
        )
        assert table.min_age == 18
        assert table.max_age == 60
        assert table.select_period == 0
        assert table.rates.shape == (43, 1)

    def test_file_not_found_raises(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_mortality_csv(
                Path("/nonexistent/table.csv"),
                select_period=3,
            )

    def test_rates_in_unit_interval(self):
        """All loaded rates are in [0, 1]."""
        table = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        assert np.all(table.rates >= 0.0)
        assert np.all(table.rates <= 1.0)

    def test_known_rate_value(self):
        """Verify a specific rate from the fixture matches expected value."""
        table = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        # Age 45, dur_1 (col 0) → 0.0040
        np.testing.assert_allclose(table.get_rate(45, 0), 0.0040, rtol=1e-10)
        # Age 45, ultimate (col 3) → 0.0055
        np.testing.assert_allclose(table.get_rate(45, 3), 0.0055, rtol=1e-10)
        # Age 45, duration beyond select → ultimate
        np.testing.assert_allclose(table.get_rate(45, 10), 0.0055, rtol=1e-10)

    def test_invalid_rates_raises(self, tmp_path):
        """Rates outside [0, 1] raise PolarisValidationError."""
        csv = tmp_path / "bad.csv"
        csv.write_text("age,rate\n18,-0.01\n19,0.50\n20,1.50\n")
        with pytest.raises(PolarisValidationError, match="rates must be in"):
            load_mortality_csv(csv, select_period=0, min_age=18, max_age=20)


class TestMortalityTableArrayLookup:
    """Tests for vectorized rate lookups."""

    @pytest.fixture()
    def table(self) -> MortalityTableArray:
        return load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )

    def test_get_rate_vector_shape(self, table: MortalityTableArray):
        """Output shape matches input."""
        ages = np.array([30, 40, 50], dtype=np.int32)
        durs = np.array([0, 1, 2], dtype=np.int32)
        result = table.get_rate_vector(ages, durs)
        assert result.shape == (3,)

    def test_get_rate_vector_known_values(self, table: MortalityTableArray):
        """Vectorized lookup matches scalar lookups."""
        ages = np.array([30, 45, 50], dtype=np.int32)
        durs = np.array([0, 2, 3], dtype=np.int32)
        result = table.get_rate_vector(ages, durs)
        expected = np.array(
            [
                table.get_rate(30, 0),
                table.get_rate(45, 2),
                table.get_rate(50, 3),
            ]
        )
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_duration_capped_at_select_period(self, table: MortalityTableArray):
        """Durations beyond select period use ultimate rate."""
        ages = np.array([40, 40], dtype=np.int32)
        durs = np.array([3, 100], dtype=np.int32)
        result = table.get_rate_vector(ages, durs)
        # Both should return ultimate rate
        np.testing.assert_allclose(result[0], result[1], rtol=1e-10)

    def test_select_rate_lower_than_ultimate(self, table: MortalityTableArray):
        """Select-period rates should be lower than ultimate at the same age."""
        ages = np.array([45, 45], dtype=np.int32)
        durs = np.array([0, 3], dtype=np.int32)  # select yr 1 vs ultimate
        result = table.get_rate_vector(ages, durs)
        assert result[0] < result[1]

    def test_age_out_of_range_raises(self, table: MortalityTableArray):
        """Ages outside table range raise PolarisValidationError."""
        ages = np.array([15], dtype=np.int32)  # below min_age
        durs = np.array([0], dtype=np.int32)
        with pytest.raises(PolarisValidationError):
            table.get_rate_vector(ages, durs)


# =========================================================================
# Lapse table tests
# =========================================================================


class TestLoadLapseCSV:
    """Tests for lapse CSV loading and validation."""

    def test_load_lapse_fixture(self):
        """Loads the synthetic lapse CSV fixture successfully."""
        table = load_lapse_csv(FIXTURES / "synthetic_lapse.csv")
        assert table.max_policy_year == 11
        assert table.rates.shape == (11,)
        np.testing.assert_allclose(table.rates[0], 0.12)

    def test_known_rate_values(self):
        """Verify specific rates match expected values."""
        table = load_lapse_csv(FIXTURES / "synthetic_lapse.csv")
        np.testing.assert_allclose(table.get_rate(1), 0.12)
        np.testing.assert_allclose(table.get_rate(5), 0.05)
        np.testing.assert_allclose(table.get_rate(11), 0.03)

    def test_beyond_max_year_uses_ultimate(self):
        """Policy years beyond the table use the last rate."""
        table = load_lapse_csv(FIXTURES / "synthetic_lapse.csv")
        np.testing.assert_allclose(table.get_rate(100), table.get_rate(11))

    def test_file_not_found_raises(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_lapse_csv(Path("/nonexistent/lapse.csv"))

    def test_rates_in_unit_interval(self):
        """All loaded rates are in [0, 1]."""
        table = load_lapse_csv(FIXTURES / "synthetic_lapse.csv")
        assert np.all(table.rates >= 0.0)
        assert np.all(table.rates <= 1.0)

    def test_invalid_rates_raises(self, tmp_path):
        """Rates outside [0, 1] raise PolarisValidationError."""
        csv = tmp_path / "bad_lapse.csv"
        csv.write_text("policy_year,rate\n1,-0.05\n2,0.10\n")
        with pytest.raises(PolarisValidationError, match="lapse rates"):
            load_lapse_csv(csv)

    def test_missing_rate_column_raises(self, tmp_path):
        """Missing 'rate' column raises PolarisValidationError."""
        csv = tmp_path / "no_rate.csv"
        csv.write_text("policy_year,lapse_pct\n1,0.10\n")
        with pytest.raises(PolarisValidationError, match="rate"):
            load_lapse_csv(csv)

    def test_non_contiguous_years_raises(self, tmp_path):
        """Non-contiguous policy years raise PolarisValidationError."""
        csv = tmp_path / "gaps.csv"
        csv.write_text("policy_year,rate\n1,0.10\n3,0.05\n")
        with pytest.raises(PolarisValidationError, match="contiguous"):
            load_lapse_csv(csv)

    def test_wrong_first_column_raises(self, tmp_path):
        """First column not 'policy_year' raises PolarisValidationError."""
        csv = tmp_path / "wrong_col.csv"
        csv.write_text("year,rate\n1,0.10\n2,0.05\n")
        with pytest.raises(PolarisValidationError, match="policy_year"):
            load_lapse_csv(csv)


class TestLapseTableArrayLookup:
    """Tests for vectorized lapse rate lookups."""

    @pytest.fixture()
    def table(self) -> LapseTableArray:
        return load_lapse_csv(FIXTURES / "synthetic_lapse.csv")

    def test_get_rate_vector_shape(self, table: LapseTableArray):
        """Output shape matches input."""
        years = np.array([1, 5, 10], dtype=np.int32)
        result = table.get_rate_vector(years)
        assert result.shape == (3,)

    def test_get_rate_vector_known_values(self, table: LapseTableArray):
        """Vectorized lookup matches scalar lookups."""
        years = np.array([1, 5, 11], dtype=np.int32)
        result = table.get_rate_vector(years)
        expected = np.array([table.get_rate(1), table.get_rate(5), table.get_rate(11)])
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_beyond_max_capped(self, table: LapseTableArray):
        """Years beyond max use ultimate (last) rate."""
        years = np.array([11, 50, 100], dtype=np.int32)
        result = table.get_rate_vector(years)
        np.testing.assert_allclose(result[0], result[1], rtol=1e-10)
        np.testing.assert_allclose(result[0], result[2], rtol=1e-10)

    def test_decreasing_rates(self, table: LapseTableArray):
        """Rates decrease from year 1 to ultimate (for this fixture)."""
        years = np.array([1, 3, 5, 11], dtype=np.int32)
        result = table.get_rate_vector(years)
        assert result[0] > result[1] > result[2] > result[3]
