"""Tests for LapseAssumption duration-based lapse rates."""

from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.core.exceptions import PolarisValidationError

FIXTURES = Path(__file__).parent.parent / "fixtures"


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


class TestLapseCSVLoading:
    """Tests for LapseAssumption.load() from CSV files."""

    def test_load_from_fixture(self):
        """Loads the synthetic lapse CSV fixture successfully."""
        lapse = LapseAssumption.load(FIXTURES / "synthetic_lapse.csv")
        # 11 rows: years 1-10 select, year 11 ultimate
        assert lapse.select_period_years == 10
        assert len(lapse.select_rates) == 10
        np.testing.assert_allclose(lapse.select_rates[0], 0.12)
        np.testing.assert_allclose(lapse.ultimate_rate, 0.03)

    def test_load_round_trip_rates(self):
        """Loaded rates match expected values from the CSV."""
        lapse = LapseAssumption.load(FIXTURES / "synthetic_lapse.csv")
        # Year 1 = 0.12, Year 5 = 0.05, Ultimate = 0.03
        np.testing.assert_allclose(lapse.select_rates[0], 0.12)
        np.testing.assert_allclose(lapse.select_rates[4], 0.05)
        np.testing.assert_allclose(lapse.ultimate_rate, 0.03)

    def test_load_then_get_vector(self):
        """Loaded lapse assumption produces correct monthly vectors."""
        lapse = LapseAssumption.load(FIXTURES / "synthetic_lapse.csv")
        # Year 1 (duration 0 months): annual 0.12
        durs = np.array([0], dtype=np.int32)
        result = lapse.get_lapse_vector(durs)
        expected = 1 - (1 - 0.12) ** (1 / 12)
        np.testing.assert_allclose(result[0], expected, rtol=1e-10)

    def test_load_ultimate_duration(self):
        """Durations beyond the select period use ultimate rate."""
        lapse = LapseAssumption.load(FIXTURES / "synthetic_lapse.csv")
        durs = np.array([120, 240], dtype=np.int32)  # years 11+, 21+
        result = lapse.get_lapse_vector(durs)
        expected = 1 - (1 - 0.03) ** (1 / 12)
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_load_file_not_found(self):
        """Missing CSV raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            LapseAssumption.load(Path("/nonexistent/lapse.csv"))

    def test_load_with_data_dir(self, tmp_path):
        """Loads from data_dir/lapse_tables/ when path is relative."""
        lapse_dir = tmp_path / "lapse_tables"
        lapse_dir.mkdir()
        csv_path = lapse_dir / "test_lapse.csv"
        csv_path.write_text("policy_year,rate\n1,0.10\n2,0.05\n")
        lapse = LapseAssumption.load(Path("test_lapse.csv"), data_dir=tmp_path)
        assert lapse.select_period_years == 1
        np.testing.assert_allclose(lapse.select_rates[0], 0.10)
        np.testing.assert_allclose(lapse.ultimate_rate, 0.05)

    def test_load_single_row(self, tmp_path):
        """Single-row CSV: no select period, just ultimate."""
        csv_path = tmp_path / "single.csv"
        csv_path.write_text("policy_year,rate\n1,0.04\n")
        lapse = LapseAssumption.load(csv_path)
        assert lapse.select_period_years == 0
        assert lapse.select_rates == ()
        np.testing.assert_allclose(lapse.ultimate_rate, 0.04)

    def test_load_invalid_rates_raises(self, tmp_path):
        """Rates outside [0, 1] raise PolarisValidationError."""
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("policy_year,rate\n1,1.50\n2,0.03\n")
        with pytest.raises(PolarisValidationError, match="lapse rates"):
            LapseAssumption.load(csv_path)

    def test_load_non_contiguous_years_raises(self, tmp_path):
        """Non-contiguous policy years raise PolarisValidationError."""
        csv_path = tmp_path / "gaps.csv"
        csv_path.write_text("policy_year,rate\n1,0.10\n3,0.06\n")
        with pytest.raises(PolarisValidationError, match="contiguous"):
            LapseAssumption.load(csv_path)

    def test_load_missing_rate_column_raises(self, tmp_path):
        """CSV without 'rate' column raises PolarisValidationError."""
        csv_path = tmp_path / "no_rate.csv"
        csv_path.write_text("policy_year,lapse_pct\n1,0.10\n2,0.05\n")
        with pytest.raises(PolarisValidationError, match="rate"):
            LapseAssumption.load(csv_path)

    def test_load_30_year_table(self, tmp_path):
        """30-year select table loads correctly."""
        rows = ["policy_year,rate"]
        for yr in range(1, 31):
            rate = max(0.12 - 0.003 * (yr - 1), 0.03)
            rows.append(f"{yr},{rate:.4f}")
        rows.append("31,0.0250")
        csv_path = tmp_path / "long.csv"
        csv_path.write_text("\n".join(rows) + "\n")
        lapse = LapseAssumption.load(csv_path)
        assert lapse.select_period_years == 30
        np.testing.assert_allclose(lapse.ultimate_rate, 0.025)
