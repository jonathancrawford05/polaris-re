"""Tests for MortalityImprovement - Scale AA, NONE, MP-2020, and CPM-B."""

import numpy as np
import pytest

from polaris_re.assumptions.improvement import (
    ImprovementScale,
    MortalityImprovement,
)
from polaris_re.core.exceptions import PolarisValidationError


class TestMortalityImprovementNone:
    """Tests for NONE improvement (identity)."""

    def test_none_returns_copy(self):
        """NONE improvement returns an unchanged copy."""
        imp = MortalityImprovement.none(base_year=2015)
        q = np.array([0.01, 0.05, 0.10], dtype=np.float64)
        ages = np.array([30, 50, 70], dtype=np.int32)
        result = imp.apply_improvement(q, ages, target_year=2025)
        np.testing.assert_allclose(result, q, rtol=1e-15)

    def test_none_does_not_modify_input(self):
        """NONE returns a copy, not a reference."""
        imp = MortalityImprovement.none(base_year=2015)
        q = np.array([0.01], dtype=np.float64)
        ages = np.array([30], dtype=np.int32)
        result = imp.apply_improvement(q, ages, target_year=2025)
        assert result is not q


class TestMortalityImprovementScaleAA:
    """Tests for Scale AA improvement."""

    def test_closed_form_age_50_10_years(self):
        """
        CLOSED-FORM: q_50(Y+10) = q_50(base) * (1 - AA_50)^10
        AA_50 = 0.010 (from lookup), so factor = (1 - 0.010)^10 = 0.990^10
        """
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.005], dtype=np.float64)
        ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)
        expected = 0.005 * (1.0 - 0.010) ** 10
        np.testing.assert_allclose(result[0], expected, rtol=1e-10)

    def test_improvement_reduces_mortality(self):
        """Improved rates should be lower than base rates for positive improvement."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.01, 0.05, 0.10], dtype=np.float64)
        ages = np.array([30, 50, 60], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)
        assert np.all(result < q_base)

    def test_zero_years_returns_copy(self):
        """When target_year == base_year, rates are unchanged."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.01, 0.05], dtype=np.float64)
        ages = np.array([30, 50], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2015)
        np.testing.assert_allclose(result, q_base, rtol=1e-15)

    def test_old_ages_no_improvement(self):
        """Ages 95+ have zero improvement factor, so rates are unchanged."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.30], dtype=np.float64)
        ages = np.array([100], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)
        np.testing.assert_allclose(result[0], 0.30, rtol=1e-15)

    def test_target_before_base_raises(self):
        """Target year before base year raises PolarisValidationError."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.01], dtype=np.float64)
        ages = np.array([30], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="before base_year"):
            imp.apply_improvement(q_base, ages, target_year=2010)

    def test_vectorized_multiple_ages(self):
        """Operates correctly on vectors of different ages."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.001, 0.005, 0.020, 0.100], dtype=np.float64)
        ages = np.array([25, 45, 65, 85], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)

        # Each age has a different improvement factor
        assert result.shape == (4,)
        # All should be reduced (positive improvement factors)
        assert np.all(result <= q_base)

    def test_rates_clipped_to_unit_interval(self):
        """Results should remain in [0, 1]."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        q_base = np.array([0.99], dtype=np.float64)
        ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_scale_property(self):
        """Scale AA instance has correct scale."""
        imp = MortalityImprovement.scale_aa(base_year=2015)
        assert imp.scale == ImprovementScale.SCALE_AA


class TestMortalityImprovementMP2020:
    """Tests for SOA MP-2020 improvement scale."""

    def test_mp2020_factory(self):
        """mp_2020() factory creates correct scale."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        assert imp.scale == ImprovementScale.MP_2020
        assert imp.base_year == 2015

    def test_zero_years_returns_copy(self):
        """When target_year == base_year, rates are unchanged."""
        imp = MortalityImprovement.mp_2020(base_year=2020)
        q_base = np.array([0.005, 0.010], dtype=np.float64)
        ages = np.array([45, 60], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2020)
        np.testing.assert_allclose(result, q_base, rtol=1e-15)

    def test_improvement_reduces_mortality(self):
        """MP-2020 improved rates are lower than base rates over 5 years."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.002, 0.008, 0.025], dtype=np.float64)
        ages = np.array([35, 50, 65], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2020)
        assert np.all(result < q_base)

    def test_closed_form_single_year(self):
        """
        CLOSED-FORM: 1-year improvement for age 45.
        q(2016) = q(2015) * (1 - AI_45(2015))
        AI_45 comes from _MP2020_FACTORS[45, 0] (year offset 0 = 2015).
        """
        from polaris_re.assumptions.improvement import _MP2020_FACTORS

        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.004], dtype=np.float64)
        ages = np.array([45], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2016)
        expected = q_base[0] * (1.0 - _MP2020_FACTORS[45, 0])
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_closed_form_five_years(self):
        """
        CLOSED-FORM: 5-year improvement for age 30.
        q(2020) = q(2015) * product_{y=2015}^{2019} (1 - AI_30(y))
        """
        from polaris_re.assumptions.improvement import _MP2020_FACTORS

        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.001], dtype=np.float64)
        ages = np.array([30], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2020)

        product = 1.0
        for y_offset in range(5):
            product *= 1.0 - _MP2020_FACTORS[30, y_offset]
        expected = q_base[0] * product
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_rates_clipped_to_unit_interval(self):
        """Results remain in [0, 1] even for large base rates."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.95], dtype=np.float64)
        ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2030)
        assert 0.0 <= result[0] <= 1.0

    def test_vectorized_shape(self):
        """Output shape matches input shape."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.full(100, 0.01, dtype=np.float64)
        ages = np.arange(20, 120, dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2025)
        assert result.shape == (100,)

    def test_target_before_base_raises(self):
        """Target year before base year raises PolarisValidationError."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.01], dtype=np.float64)
        ages = np.array([40], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="before base_year"):
            imp.apply_improvement(q_base, ages, target_year=2010)

    def test_post_2031_uses_ultimate(self):
        """Years beyond 2031 data period still returns valid improved rates."""
        imp = MortalityImprovement.mp_2020(base_year=2015)
        q_base = np.array([0.005], dtype=np.float64)
        ages = np.array([45], dtype=np.int32)
        # 2040 is beyond the 2031 last data year — should not raise
        result = imp.apply_improvement(q_base, ages, target_year=2040)
        assert 0.0 <= result[0] < q_base[0]  # rate decreases


class TestMortalityImprovementCPMB:
    """Tests for CIA CPM-B improvement scale."""

    def test_cpmb_factory(self):
        """cpm_b() factory creates correct scale."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        assert imp.scale == ImprovementScale.CPM_B
        assert imp.base_year == 2014

    def test_zero_years_returns_copy(self):
        """When target_year == base_year, rates are unchanged."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.003, 0.015], dtype=np.float64)
        ages = np.array([40, 60], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2014)
        np.testing.assert_allclose(result, q_base, rtol=1e-15)

    def test_closed_form_age_45_10_years(self):
        """
        CLOSED-FORM: q_45(Y+10) = q_45(base) * (1 - CPM_B_45)^10
        CPM_B_45 = 0.014 (ages 35-44 band), so factor = (1 - 0.014)^10
        """
        from polaris_re.assumptions.improvement import _CPM_B_FACTORS

        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.006], dtype=np.float64)
        ages = np.array([45], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2024)
        expected = q_base[0] * (1.0 - _CPM_B_FACTORS[45]) ** 10
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_improvement_reduces_mortality(self):
        """CPM-B improved rates are strictly lower than base rates."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.002, 0.010, 0.040], dtype=np.float64)
        ages = np.array([35, 55, 70], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2024)
        assert np.all(result < q_base)

    def test_old_ages_zero_improvement(self):
        """Ages 95+ have zero CPM-B factor — rates unchanged."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.35], dtype=np.float64)
        ages = np.array([100], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2024)
        np.testing.assert_allclose(result[0], 0.35, rtol=1e-15)

    def test_rates_clipped_to_unit_interval(self):
        """Results remain in [0, 1]."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.95], dtype=np.float64)
        ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2034)
        assert 0.0 <= result[0] <= 1.0

    def test_vectorized_shape(self):
        """Output shape matches input shape."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.full(50, 0.01, dtype=np.float64)
        ages = np.arange(20, 70, dtype=np.int32)
        result = imp.apply_improvement(q_base, ages, target_year=2024)
        assert result.shape == (50,)

    def test_target_before_base_raises(self):
        """Target year before base year raises PolarisValidationError."""
        imp = MortalityImprovement.cpm_b(base_year=2014)
        q_base = np.array([0.01], dtype=np.float64)
        ages = np.array([40], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="before base_year"):
            imp.apply_improvement(q_base, ages, target_year=2010)


class TestMortalityImprovementCustom:
    """Tests for the CUSTOM data-driven MI_x(y) improvement grid (Slice 2c)."""

    @staticmethod
    def _flat_grid(rate: float, n_ages: int = 6, n_years: int = 5):
        """A uniform improvement grid: ages 50.., years 2021.., constant rate."""
        ages = np.arange(50, 50 + n_ages, dtype=np.int32)
        years = np.arange(2021, 2021 + n_years, dtype=np.int32)
        grid = np.full((n_ages, n_years), rate, dtype=np.float64)
        return ages, years, grid

    def test_from_grid_sets_base_year_and_scale(self):
        """from_grid anchors base_year at years[0] - 1 and selects CUSTOM."""
        ages, years, grid = self._flat_grid(0.02)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        assert imp.scale == ImprovementScale.CUSTOM
        assert imp.base_year == 2020  # years[0] (2021) - 1

    def test_closed_form_uniform_grid(self):
        """
        CLOSED-FORM: a uniform 2% grid over 5 steps gives
        q(base + 5) = q_base * (1 - 0.02)^5.
        base_year = 2020, target 2025 -> steps end 2021..2025 (5 steps).
        """
        ages, years, grid = self._flat_grid(0.02)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2025)
        expected = 0.01 * (1.0 - 0.02) ** 5
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_partial_horizon(self):
        """Target inside the grid uses only the steps up to that year."""
        ages, years, grid = self._flat_grid(0.02)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2023)
        expected = 0.01 * (1.0 - 0.02) ** 3  # steps end 2021, 2022, 2023
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_age_varying_grid(self):
        """Each attained age reads its own grid row."""
        ages = np.array([50, 51, 52], dtype=np.int32)
        years = np.array([2021, 2022], dtype=np.int32)
        grid = np.array([[0.01, 0.01], [0.02, 0.02], [0.03, 0.03]], dtype=np.float64)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01, 0.01, 0.01], dtype=np.float64)
        pol_ages = np.array([50, 51, 52], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2022)
        expected = 0.01 * np.array([(1 - 0.01) ** 2, (1 - 0.02) ** 2, (1 - 0.03) ** 2])
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_ultimate_rate_beyond_grid(self):
        """Step-end years past the last grid year use custom_ultimate_rate."""
        ages, years, grid = self._flat_grid(0.02)  # years 2021..2025
        imp = MortalityImprovement.from_grid(ages, years, grid, ultimate_rate=0.01)
        q_base = np.array([0.01], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2027)
        # 2021..2025 at 2%, 2026..2027 at 1%
        expected = 0.01 * (1 - 0.02) ** 5 * (1 - 0.01) ** 2
        np.testing.assert_allclose(result[0], expected, rtol=1e-12)

    def test_age_clamped_to_grid_range(self):
        """Ages outside the grid clamp to the nearest edge row (constant extrap)."""
        ages, years, grid = self._flat_grid(0.02, n_ages=6)  # ages 50..55
        # give the top edge row a distinct rate so we can detect the clamp
        grid = grid.copy()
        grid[-1, :] = 0.05  # age 55 row
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01, 0.01], dtype=np.float64)
        pol_ages = np.array([80, 55], dtype=np.int32)  # 80 clamps to 55
        result = imp.apply_improvement(q_base, pol_ages, target_year=2025)
        np.testing.assert_allclose(result[0], result[1], rtol=1e-12)
        np.testing.assert_allclose(result[0], 0.01 * (1 - 0.05) ** 5, rtol=1e-12)

    def test_zero_years_returns_copy(self):
        """target_year == base_year returns an unchanged copy."""
        ages, years, grid = self._flat_grid(0.02)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01, 0.02], dtype=np.float64)
        pol_ages = np.array([50, 51], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2020)
        np.testing.assert_allclose(result, q_base, rtol=1e-15)
        assert result is not q_base

    def test_result_clipped_to_unit_interval(self):
        """Extreme (negative) improvement cannot push q above 1.0."""
        ages, years, grid = self._flat_grid(-5.0)  # blows up mortality
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.9], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2025)
        assert result[0] == 1.0

    @pytest.mark.parametrize("rate", [0.005, 0.01, 0.02, 0.03])
    def test_sensitivity_uniform_rate(self, rate):
        """Higher uniform improvement rate -> lower projected mortality."""
        ages, years, grid = self._flat_grid(rate)
        imp = MortalityImprovement.from_grid(ages, years, grid)
        q_base = np.array([0.01], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        result = imp.apply_improvement(q_base, pol_ages, target_year=2025)
        np.testing.assert_allclose(result[0], 0.01 * (1 - rate) ** 5, rtol=1e-12)

    def test_serialization_round_trip(self):
        """CUSTOM scale round-trips through model_dump / model_validate (versioning)."""
        ages, years, grid = self._flat_grid(0.02)
        imp = MortalityImprovement.from_grid(ages, years, grid, ultimate_rate=0.01)
        restored = MortalityImprovement.model_validate(imp.model_dump())
        assert restored == imp
        q_base = np.array([0.01], dtype=np.float64)
        pol_ages = np.array([50], dtype=np.int32)
        np.testing.assert_allclose(
            restored.apply_improvement(q_base, pol_ages, 2027),
            imp.apply_improvement(q_base, pol_ages, 2027),
            rtol=1e-15,
        )


class TestMortalityImprovementCustomValidation:
    """Validation guards on the CUSTOM payload."""

    def test_custom_grid_on_non_custom_scale_rejected(self):
        with pytest.raises(PolarisValidationError, match="only be set when"):
            MortalityImprovement(
                scale=ImprovementScale.SCALE_AA,
                base_year=2020,
                custom_ages=(50, 51),
            )

    def test_custom_without_grid_rejected(self):
        with pytest.raises(PolarisValidationError, match="requires custom_ages"):
            MortalityImprovement(scale=ImprovementScale.CUSTOM, base_year=2020)

    def test_row_count_mismatch_rejected(self):
        with pytest.raises(PolarisValidationError, match="rows but"):
            MortalityImprovement(
                scale=ImprovementScale.CUSTOM,
                base_year=2020,
                custom_ages=(50, 51, 52),
                custom_years=(2021,),
                custom_mi_grid=((0.02,), (0.02,)),  # 2 rows, 3 ages
            )

    def test_column_count_mismatch_rejected(self):
        with pytest.raises(PolarisValidationError, match="len\\(custom_years\\)"):
            MortalityImprovement(
                scale=ImprovementScale.CUSTOM,
                base_year=2020,
                custom_ages=(50,),
                custom_years=(2021, 2022),
                custom_mi_grid=((0.02,),),  # 1 col, needs 2
            )

    def test_non_contiguous_ages_rejected(self):
        with pytest.raises(PolarisValidationError, match="custom_ages must be"):
            MortalityImprovement(
                scale=ImprovementScale.CUSTOM,
                base_year=2020,
                custom_ages=(50, 52),
                custom_years=(2021,),
                custom_mi_grid=((0.02,), (0.02,)),
            )

    def test_non_contiguous_years_rejected(self):
        with pytest.raises(PolarisValidationError, match="custom_years must be"):
            MortalityImprovement(
                scale=ImprovementScale.CUSTOM,
                base_year=2020,
                custom_ages=(50,),
                custom_years=(2021, 2023),
                custom_mi_grid=((0.02, 0.02),),
            )

    def test_base_year_mismatch_rejected(self):
        with pytest.raises(PolarisValidationError, match="must equal first grid year"):
            MortalityImprovement(
                scale=ImprovementScale.CUSTOM,
                base_year=2019,  # should be 2020
                custom_ages=(50,),
                custom_years=(2021,),
                custom_mi_grid=((0.02,),),
            )
