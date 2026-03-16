"""
Tests for stochastic interest rate models (analytics/stochastic.py).

Closed-form / statistical verification:
1. Shape: output arrays are (n_paths, n_periods)
2. Reproducibility: same seed → identical results
3. Hull-White: mean short rate converges toward r_mean (asymptotically)
4. CIR: all rates non-negative with well-conditioned parameters
5. Discount factors: cumulative, declining, bounded in (0, 1]
6. path_pv: shape (n_paths,), equals sum(CF * disc_factor) manually
"""

import warnings

import numpy as np
import pytest

from polaris_re.analytics.stochastic import CIRModel, HullWhiteModel


class TestHullWhiteModel:

    def test_output_shape(self):
        """simulate() returns RateScenarios with arrays of shape (n_paths, n_periods)."""
        model = HullWhiteModel(n_paths=50, seed=1)
        scenarios = model.simulate(n_periods=60)
        assert scenarios.short_rates.shape == (50, 60)
        assert scenarios.discount_factors.shape == (50, 60)

    def test_reproducibility(self):
        """Same seed produces identical paths."""
        m1 = HullWhiteModel(n_paths=20, seed=99)
        m2 = HullWhiteModel(n_paths=20, seed=99)
        s1 = m1.simulate(24)
        s2 = m2.simulate(24)
        np.testing.assert_array_equal(s1.short_rates, s2.short_rates)

    def test_different_seeds_differ(self):
        """Different seeds produce different paths."""
        m1 = HullWhiteModel(n_paths=20, seed=1)
        m2 = HullWhiteModel(n_paths=20, seed=2)
        s1 = m1.simulate(24)
        s2 = m2.simulate(24)
        assert not np.allclose(s1.short_rates, s2.short_rates)

    def test_initial_rate(self):
        """First column of short_rates should equal r0 for all paths."""
        r0 = 0.03
        model = HullWhiteModel(r0=r0, n_paths=100, seed=42)
        scenarios = model.simulate(12)
        np.testing.assert_array_equal(scenarios.short_rates[:, 0], r0)

    def test_mean_reversion(self):
        """
        STATISTICAL: Long-run mean of simulated short rates should converge
        toward r_mean within 3 standard deviations (95% CI approximately).

        Using tight parameters (high a) for faster convergence in short test.
        """
        r_mean = 0.05
        # High a = fast mean reversion; large n_paths for stability
        model = HullWhiteModel(r0=0.10, r_mean=r_mean, a=0.5, sigma=0.005, n_paths=2000, seed=0)
        scenarios = model.simulate(n_periods=120)

        # Mean of final-year rates should be close to r_mean
        final_rates = scenarios.short_rates[:, -1]
        sim_mean = float(final_rates.mean())
        # Allow ±1% absolute deviation
        np.testing.assert_allclose(sim_mean, r_mean, atol=0.01)

    def test_discount_factors_bounded(self):
        """All discount factors must be in (0, 1] (positive, non-increasing compounding)."""
        model = HullWhiteModel(r0=0.05, n_paths=100, seed=7)
        scenarios = model.simulate(60)
        assert (scenarios.discount_factors > 0).all()
        assert (scenarios.discount_factors <= 1.0 + 1e-10).all()

    def test_discount_factors_non_increasing(self):
        """Cumulative discount factors should be non-increasing across time."""
        model = HullWhiteModel(r0=0.05, n_paths=10, seed=3)
        scenarios = model.simulate(24)
        diff = np.diff(scenarios.discount_factors, axis=1)
        # For positive rates, cumulative disc factors must decrease or stay same
        # Note: allows tiny tolerance for very low or zero rates
        assert (diff <= 1e-6).all()

    def test_model_metadata(self):
        """RateScenarios metadata should reflect model parameters."""
        model = HullWhiteModel(n_paths=50, seed=11)
        scenarios = model.simulate(24)
        assert scenarios.model == "HULL_WHITE"
        assert scenarios.n_paths == 50
        assert scenarios.n_periods == 24
        assert scenarios.seed == 11

    def test_mean_std_properties(self):
        """mean_short_rate and std_short_rate should have shape (n_periods,)."""
        model = HullWhiteModel(n_paths=100, seed=5)
        scenarios = model.simulate(36)
        assert scenarios.mean_short_rate.shape == (36,)
        assert scenarios.std_short_rate.shape == (36,)

    def test_path_pv_shape_and_value(self):
        """
        CLOSED-FORM: path_pv should return shape (n_paths,) and match manual dot product.
        """
        model = HullWhiteModel(n_paths=10, seed=42)
        scenarios = model.simulate(12)

        cash_flows = np.ones(12, dtype=np.float64) * 100.0
        pvs = scenarios.path_pv(cash_flows)
        assert pvs.shape == (10,)

        # Verify first path manually
        manual_pv = float(np.dot(cash_flows, scenarios.discount_factors[0]))
        np.testing.assert_allclose(pvs[0], manual_pv, rtol=1e-10)

    def test_path_pv_wrong_length_raises(self):
        """path_pv should raise if cash_flows length != n_periods."""
        model = HullWhiteModel(n_paths=10, seed=42)
        scenarios = model.simulate(12)
        with pytest.raises(ValueError, match="n_periods"):
            scenarios.path_pv(np.ones(6))

    def test_pv_percentile(self):
        """pv_percentile should return a scalar within the range of path PVs."""
        model = HullWhiteModel(n_paths=200, seed=42)
        scenarios = model.simulate(12)
        cash_flows = np.ones(12) * 100.0
        p50 = scenarios.pv_percentile(cash_flows, 50.0)
        p5 = scenarios.pv_percentile(cash_flows, 5.0)
        p95 = scenarios.pv_percentile(cash_flows, 95.0)
        assert p5 <= p50 <= p95

    def test_terminal_discount_factor(self):
        """terminal_discount_factor() should return shape (n_paths,) = last column."""
        model = HullWhiteModel(n_paths=50, seed=42)
        scenarios = model.simulate(24)
        terminal = scenarios.terminal_discount_factor()
        assert terminal.shape == (50,)
        np.testing.assert_array_equal(terminal, scenarios.discount_factors[:, -1])


class TestCIRModel:

    def test_output_shape(self):
        """CIR simulate() returns arrays of shape (n_paths, n_periods)."""
        model = CIRModel(n_paths=50, seed=1)
        scenarios = model.simulate(60)
        assert scenarios.short_rates.shape == (50, 60)
        assert scenarios.discount_factors.shape == (50, 60)

    def test_non_negativity_with_feller(self):
        """
        With Feller condition satisfied (2ab > sigma^2), rates should be
        non-negative throughout the simulation.
        """
        # Feller: 2*0.30*0.05 = 0.03 > 0.02^2 = 0.0004 ✓
        model = CIRModel(r0=0.05, b=0.05, a=0.30, sigma=0.02, n_paths=500, seed=42)
        scenarios = model.simulate(60)
        assert (scenarios.short_rates >= 0.0).all()

    def test_feller_warning(self):
        """CIR should warn when Feller condition is violated."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            CIRModel(r0=0.05, b=0.01, a=0.01, sigma=0.20)  # 2*0.01*0.01=0.0002 < 0.04
            assert len(w) == 1
            assert "Feller" in str(w[0].message)

    def test_reproducibility(self):
        """Same seed gives identical results."""
        m1 = CIRModel(n_paths=20, seed=77)
        m2 = CIRModel(n_paths=20, seed=77)
        np.testing.assert_array_equal(m1.simulate(12).short_rates, m2.simulate(12).short_rates)

    def test_initial_rate(self):
        """First column equals r0."""
        r0 = 0.04
        model = CIRModel(r0=r0, n_paths=50, seed=42)
        scenarios = model.simulate(12)
        np.testing.assert_array_equal(scenarios.short_rates[:, 0], r0)

    def test_model_label(self):
        """RateScenarios model label should be 'CIR'."""
        model = CIRModel(n_paths=10, seed=1)
        assert model.simulate(12).model == "CIR"

    def test_discount_factors_bounded(self):
        """Discount factors must be in (0, 1]."""
        model = CIRModel(r0=0.04, b=0.04, a=0.20, sigma=0.02, n_paths=100, seed=42)
        scenarios = model.simulate(60)
        assert (scenarios.discount_factors > 0).all()
        assert (scenarios.discount_factors <= 1.0 + 1e-10).all()

    def test_mean_reversion_cir(self):
        """
        STATISTICAL: Long-run mean of CIR rates should converge toward b.
        """
        b = 0.04
        model = CIRModel(r0=0.08, b=b, a=0.5, sigma=0.01, n_paths=2000, seed=10)
        scenarios = model.simulate(n_periods=120)
        final_mean = float(scenarios.short_rates[:, -1].mean())
        np.testing.assert_allclose(final_mean, b, atol=0.01)

    @pytest.mark.parametrize("n_paths,n_periods", [(10, 6), (50, 120), (1, 24)])
    def test_various_shapes(self, n_paths: int, n_periods: int):
        """Output shapes should be correct for various (n_paths, n_periods) combinations."""
        model = CIRModel(n_paths=n_paths, seed=0)
        scenarios = model.simulate(n_periods)
        assert scenarios.short_rates.shape == (n_paths, n_periods)
        assert scenarios.discount_factors.shape == (n_paths, n_periods)
