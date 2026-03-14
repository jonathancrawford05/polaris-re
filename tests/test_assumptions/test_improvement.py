"""Tests for MortalityImprovement - Scale AA and NONE."""

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
