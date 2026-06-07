"""
Tests for analytics/capital.py — LICAT regulatory capital module (ADR-047).

Slice 1 scope: standalone factor-based LICATCapital calculator.
Closed-form verification: capital = c2_factor * NAR (with C-1 and C-3 stubs).

Note: this slice does NOT integrate with ProfitTester. RoC computation lives
in Slice 2.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.capital import (
    CapitalResult,
    LICATCapital,
    LICATFactors,
)
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.policy import ProductType


def _make_cashflow(
    *,
    n: int = 24,
    reserve: float = 100_000.0,
    nar: np.ndarray | None = None,
    basis: str = "GROSS",
) -> CashFlowResult:
    """Construct a minimal CashFlowResult for capital tests."""
    arr = np.full(n, reserve, dtype=np.float64)
    return CashFlowResult(
        run_id="test-capital",
        valuation_date=date(2025, 1, 1),
        basis=basis,  # type: ignore[arg-type]
        assumption_set_version="test-v1",
        product_type="TERM",
        projection_months=n,
        time_index=np.arange("2025-01", n + 1, dtype="datetime64[M]")[:n],
        gross_premiums=np.full(n, 1000.0, dtype=np.float64),
        death_claims=np.full(n, 200.0, dtype=np.float64),
        lapse_surrenders=np.zeros(n, dtype=np.float64),
        expenses=np.full(n, 50.0, dtype=np.float64),
        reserve_balance=arr,
        reserve_increase=np.zeros(n, dtype=np.float64),
        net_cash_flow=np.full(n, 750.0, dtype=np.float64),
        nar=nar,
    )


# ----------------------------------------------------------------------
# LICATFactors
# ----------------------------------------------------------------------


class TestLICATFactors:
    def test_default_factors(self) -> None:
        f = LICATFactors()
        assert f.c2_mortality_factor == 0.10
        assert f.c1_asset_default == 0.0
        assert f.c3_interest_rate == 0.0

    def test_factors_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_mortality_factor=-0.01)

    def test_factors_capped_at_one(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_mortality_factor=1.5)

    def test_factors_are_frozen(self) -> None:
        f = LICATFactors(c2_mortality_factor=0.12)
        with pytest.raises((ValueError, TypeError)):
            f.c2_mortality_factor = 0.20  # type: ignore[misc]


# ----------------------------------------------------------------------
# LICATCapital — product-type defaults
# ----------------------------------------------------------------------


class TestLICATCapitalForProduct:
    @pytest.mark.parametrize(
        "product_type, expected_factor",
        [
            (ProductType.TERM, 0.15),
            (ProductType.WHOLE_LIFE, 0.10),
            (ProductType.UNIVERSAL_LIFE, 0.08),
            (ProductType.DISABILITY, 0.05),
            (ProductType.CRITICAL_ILLNESS, 0.05),
            (ProductType.ANNUITY, 0.03),
        ],
    )
    def test_for_product_uses_published_factor(
        self, product_type: ProductType, expected_factor: float
    ) -> None:
        cap = LICATCapital.for_product(product_type)
        assert cap.factors.c2_mortality_factor == pytest.approx(expected_factor)

    def test_for_product_returns_zero_c1_c3_stubs(self) -> None:
        cap = LICATCapital.for_product(ProductType.TERM)
        assert cap.factors.c1_asset_default == 0.0
        assert cap.factors.c3_interest_rate == 0.0


# ----------------------------------------------------------------------
# LICATCapital — closed-form NAR computation
# ----------------------------------------------------------------------


class TestLICATCapitalRequiredCapital:
    def test_c2_equals_factor_times_nar(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        np.testing.assert_allclose(result.c2_component, 0.10 * nar)

    def test_c1_c3_stubs_zero_by_default(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        np.testing.assert_array_equal(result.c1_component, np.zeros(n))
        np.testing.assert_array_equal(result.c3_component, np.zeros(n))

    def test_total_capital_equals_sum_of_components(self) -> None:
        n = 12
        nar = np.full(n, 800_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(
            factors=LICATFactors(
                c2_mortality_factor=0.12,
                c1_asset_default=0.0,
                c3_interest_rate=0.0,
            )
        )
        result = cap.required_capital(cf)

        np.testing.assert_allclose(
            result.capital_by_period,
            result.c1_component + result.c2_component + result.c3_component,
        )

    def test_initial_and_peak_capital(self) -> None:
        nar = np.array([1000.0, 2000.0, 3000.0, 2500.0, 1500.0], dtype=np.float64)
        cf = _make_cashflow(n=5, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        # initial = first period
        assert result.initial_capital == pytest.approx(0.10 * 1000.0)
        # peak = max
        assert result.peak_capital == pytest.approx(0.10 * 3000.0)

    def test_doubling_factor_doubles_c2(self) -> None:
        n = 6
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap_low = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.05))
        cap_high = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))

        r_low = cap_low.required_capital(cf)
        r_high = cap_high.required_capital(cf)

        np.testing.assert_allclose(r_high.c2_component, 2.0 * r_low.c2_component)

    def test_zero_factor_zero_capital(self) -> None:
        n = 8
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.0))
        result = cap.required_capital(cf)

        np.testing.assert_array_equal(result.capital_by_period, np.zeros(n))
        assert result.peak_capital == 0.0
        assert result.initial_capital == 0.0


# ----------------------------------------------------------------------
# LICATCapital — NAR resolution
# ----------------------------------------------------------------------


class TestLICATCapitalNarResolution:
    def test_uses_cashflow_nar_when_present(self) -> None:
        n = 12
        nar = np.full(n, 750_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        np.testing.assert_allclose(result.c2_component, 0.10 * nar)

    def test_explicit_nar_overrides_cashflow_nar(self) -> None:
        n = 12
        cf_nar = np.full(n, 100.0, dtype=np.float64)  # tiny in cashflow
        explicit_nar = np.full(n, 1_000_000.0, dtype=np.float64)  # large explicit
        cf = _make_cashflow(n=n, nar=cf_nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf, nar=explicit_nar)

        np.testing.assert_allclose(result.c2_component, 0.10 * explicit_nar)

    def test_missing_nar_raises(self) -> None:
        cf = _make_cashflow(n=12, nar=None)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        with pytest.raises(PolarisComputationError, match="NAR"):
            cap.required_capital(cf)

    def test_nar_wrong_length_raises(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1000.0, dtype=np.float64))
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        with pytest.raises(PolarisComputationError, match="length"):
            cap.required_capital(cf, nar=np.full(6, 1000.0, dtype=np.float64))


# ----------------------------------------------------------------------
# LICATCapital — basis acceptance
# ----------------------------------------------------------------------


class TestLICATCapitalBasis:
    def test_gross_basis_accepted(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1000.0, dtype=np.float64), basis="GROSS")
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)
        assert result.projection_months == 12

    def test_net_basis_accepted(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1000.0, dtype=np.float64), basis="NET")
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)
        assert result.projection_months == 12

    def test_ceded_basis_rejected(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1000.0, dtype=np.float64), basis="CEDED")
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        with pytest.raises(ValueError, match="CEDED"):
            cap.required_capital(cf)


# ----------------------------------------------------------------------
# CapitalResult — derived metrics
# ----------------------------------------------------------------------


class TestCapitalResult:
    def test_shape_consistency(self) -> None:
        n = 24
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        assert result.capital_by_period.shape == (n,)
        assert result.c1_component.shape == (n,)
        assert result.c2_component.shape == (n,)
        assert result.c3_component.shape == (n,)
        assert result.projection_months == n

    def test_dtypes_are_float64(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        assert result.capital_by_period.dtype == np.float64
        assert result.c1_component.dtype == np.float64
        assert result.c2_component.dtype == np.float64
        assert result.c3_component.dtype == np.float64

    def test_pv_capital_strain_monotone_in_rate(self) -> None:
        """PV of a positive capital stream decreases as discount rate rises."""
        n = 60
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        pv_low = result.pv_capital(discount_rate=0.05)
        pv_high = result.pv_capital(discount_rate=0.20)

        assert pv_low > pv_high > 0.0

    def test_pv_capital_zero_rate_equals_undiscounted_sum(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        result = cap.required_capital(cf)

        # At rate=0, discount factor is 1.0 — PV equals the undiscounted sum
        pv_zero = result.pv_capital(discount_rate=0.0)
        assert pv_zero == pytest.approx(float(result.capital_by_period.sum()))


# ----------------------------------------------------------------------
# Closed-form C-2 verification vs published factor (acceptance criterion)
# ----------------------------------------------------------------------


class TestC2ClosedFormOSFI:
    """
    Verifies the C-2 mortality risk computation against a hand-calculated
    figure derived from the published OSFI factor for term life.

    Setup: $1M NAR for 12 months, factor = 0.15 (term life default).
    Expected C-2 capital each month = 0.15 * 1,000,000 = $150,000.
    """

    def test_c2_term_factor_vs_hand_calc(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital.for_product(ProductType.TERM)
        result = cap.required_capital(cf)

        np.testing.assert_allclose(result.c2_component, np.full(n, 150_000.0, dtype=np.float64))
        assert result.peak_capital == pytest.approx(150_000.0)

    def test_c2_whole_life_factor_vs_hand_calc(self) -> None:
        n = 12
        nar = np.full(n, 2_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital.for_product(ProductType.WHOLE_LIFE)
        result = cap.required_capital(cf)

        # 0.10 * 2M = 200K
        np.testing.assert_allclose(result.c2_component, np.full(n, 200_000.0, dtype=np.float64))


# ----------------------------------------------------------------------
# Lapse-risk and morbidity-risk factor components (ADR-065)
# ----------------------------------------------------------------------


class TestLICATFactorsExtendedC2:
    """LICATFactors gains c2_lapse_factor and c2_morbidity_factor (ADR-065)."""

    def test_default_lapse_factor_is_zero(self) -> None:
        f = LICATFactors()
        assert f.c2_lapse_factor == 0.0

    def test_default_morbidity_factor_is_zero(self) -> None:
        f = LICATFactors()
        assert f.c2_morbidity_factor == 0.0

    def test_lapse_factor_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_lapse_factor=-0.01)

    def test_morbidity_factor_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_morbidity_factor=-0.05)

    def test_lapse_factor_capped_at_one(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_lapse_factor=1.2)

    def test_morbidity_factor_capped_at_one(self) -> None:
        with pytest.raises(ValueError):
            LICATFactors(c2_morbidity_factor=1.5)


class TestLapseRiskComponent:
    """c2_lapse_component = c2_lapse_factor * reserve_balance (ADR-065)."""

    def test_lapse_equals_factor_times_reserve(self) -> None:
        n = 12
        reserve = 250_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.04))
        result = cap.required_capital(cf)

        np.testing.assert_allclose(
            result.c2_lapse_component, np.full(n, 0.04 * reserve, dtype=np.float64)
        )

    def test_zero_lapse_factor_zero_lapse_component(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.0))
        result = cap.required_capital(cf)

        np.testing.assert_array_equal(result.c2_lapse_component, np.zeros(n))

    def test_doubling_lapse_factor_doubles_lapse_component(self) -> None:
        n = 6
        reserve = 100_000.0
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap_low = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.03))
        cap_high = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.06))

        r_low = cap_low.required_capital(cf)
        r_high = cap_high.required_capital(cf)

        np.testing.assert_allclose(r_high.c2_lapse_component, 2.0 * r_low.c2_lapse_component)

    def test_lapse_component_tracks_reserve_balance(self) -> None:
        """Lapse capital follows the time-shape of reserve_balance, not NAR."""
        n = 5
        nar = np.array([1000.0, 1000.0, 1000.0, 1000.0, 1000.0], dtype=np.float64)
        # Build a cashflow with a stepped reserve schedule.
        reserve_arr = np.array([100.0, 200.0, 400.0, 300.0, 150.0], dtype=np.float64)
        cf = CashFlowResult(
            run_id="lapse-shape",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="test-v1",
            product_type="TERM",
            projection_months=n,
            time_index=np.arange("2025-01", n + 1, dtype="datetime64[M]")[:n],
            gross_premiums=np.full(n, 1000.0, dtype=np.float64),
            death_claims=np.full(n, 200.0, dtype=np.float64),
            lapse_surrenders=np.zeros(n, dtype=np.float64),
            expenses=np.full(n, 50.0, dtype=np.float64),
            reserve_balance=reserve_arr,
            reserve_increase=np.zeros(n, dtype=np.float64),
            net_cash_flow=np.full(n, 750.0, dtype=np.float64),
            nar=nar,
        )
        cap = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.05))
        result = cap.required_capital(cf)

        np.testing.assert_allclose(result.c2_lapse_component, 0.05 * reserve_arr)


class TestMorbidityRiskComponent:
    """c2_morbidity_component = c2_morbidity_factor * NAR (ADR-065)."""

    def test_morbidity_equals_factor_times_nar(self) -> None:
        n = 12
        nar = np.full(n, 800_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_morbidity_factor=0.12))
        result = cap.required_capital(cf)

        np.testing.assert_allclose(result.c2_morbidity_component, 0.12 * nar)

    def test_zero_morbidity_factor_zero_morbidity_component(self) -> None:
        n = 12
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_morbidity_factor=0.0))
        result = cap.required_capital(cf)

        np.testing.assert_array_equal(result.c2_morbidity_component, np.zeros(n))

    def test_doubling_morbidity_factor_doubles_morbidity_component(self) -> None:
        n = 6
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap_low = LICATCapital(factors=LICATFactors(c2_morbidity_factor=0.05))
        cap_high = LICATCapital(factors=LICATFactors(c2_morbidity_factor=0.10))

        r_low = cap_low.required_capital(cf)
        r_high = cap_high.required_capital(cf)

        np.testing.assert_allclose(
            r_high.c2_morbidity_component, 2.0 * r_low.c2_morbidity_component
        )

    def test_morbidity_uses_explicit_nar_override(self) -> None:
        n = 6
        cf_nar = np.full(n, 100.0, dtype=np.float64)
        explicit_nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=cf_nar)
        cap = LICATCapital(factors=LICATFactors(c2_morbidity_factor=0.10))
        result = cap.required_capital(cf, nar=explicit_nar)

        np.testing.assert_allclose(result.c2_morbidity_component, 0.10 * explicit_nar)


class TestExtendedC2Aggregate:
    """capital_by_period and c2_insurance_risk aggregate all C-2 components."""

    def test_total_capital_sums_all_components(self) -> None:
        n = 8
        reserve = 100_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital(
            factors=LICATFactors(
                c2_mortality_factor=0.10,
                c2_lapse_factor=0.04,
                c2_morbidity_factor=0.05,
                c1_asset_default=0.01,
                c3_interest_rate=0.02,
            )
        )
        result = cap.required_capital(cf)

        expected = (
            result.c1_component
            + result.c2_component
            + result.c2_lapse_component
            + result.c2_morbidity_component
            + result.c3_component
        )
        np.testing.assert_allclose(result.capital_by_period, expected)

    def test_c2_insurance_risk_sums_mortality_lapse_morbidity(self) -> None:
        n = 6
        reserve = 200_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital(
            factors=LICATFactors(
                c2_mortality_factor=0.10,
                c2_lapse_factor=0.04,
                c2_morbidity_factor=0.05,
            )
        )
        result = cap.required_capital(cf)

        expected = result.c2_component + result.c2_lapse_component + result.c2_morbidity_component
        np.testing.assert_allclose(result.c2_insurance_risk, expected)

    def test_components_have_consistent_shape_and_dtype(self) -> None:
        n = 24
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, nar=nar)
        cap = LICATCapital(factors=LICATFactors(c2_lapse_factor=0.04, c2_morbidity_factor=0.03))
        result = cap.required_capital(cf)

        assert result.c2_lapse_component.shape == (n,)
        assert result.c2_morbidity_component.shape == (n,)
        assert result.c2_lapse_component.dtype == np.float64
        assert result.c2_morbidity_component.dtype == np.float64
        assert result.c2_insurance_risk.shape == (n,)
        assert result.c2_insurance_risk.dtype == np.float64

    def test_peak_capital_includes_extended_components(self) -> None:
        n = 6
        reserve = 100_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital(
            factors=LICATFactors(
                c2_mortality_factor=0.10,
                c2_lapse_factor=0.04,
                c2_morbidity_factor=0.05,
            )
        )
        result = cap.required_capital(cf)

        # 0.10 * 1M + 0.04 * 100K + 0.05 * 1M = 100K + 4K + 50K = 154K
        expected_peak = 0.10 * 1_000_000.0 + 0.04 * 100_000.0 + 0.05 * 1_000_000.0
        assert result.peak_capital == pytest.approx(expected_peak)
        assert result.initial_capital == pytest.approx(expected_peak)


class TestForProductBackwardCompat:
    """`for_product` is unchanged — lapse and morbidity remain at zero."""

    @pytest.mark.parametrize(
        "product_type",
        [
            ProductType.TERM,
            ProductType.WHOLE_LIFE,
            ProductType.UNIVERSAL_LIFE,
            ProductType.DISABILITY,
            ProductType.CRITICAL_ILLNESS,
            ProductType.ANNUITY,
        ],
    )
    def test_for_product_leaves_extended_factors_at_zero(self, product_type: ProductType) -> None:
        cap = LICATCapital.for_product(product_type)
        assert cap.factors.c2_lapse_factor == 0.0
        assert cap.factors.c2_morbidity_factor == 0.0


class TestForProductExtended:
    """`for_product_extended` populates all three C-2 sub-factors per product."""

    @pytest.mark.parametrize(
        "product_type, expected_mortality, expected_lapse, expected_morbidity",
        [
            (ProductType.TERM, 0.15, 0.05, 0.00),
            (ProductType.WHOLE_LIFE, 0.10, 0.03, 0.00),
            (ProductType.UNIVERSAL_LIFE, 0.08, 0.04, 0.00),
            (ProductType.DISABILITY, 0.05, 0.02, 0.15),
            (ProductType.CRITICAL_ILLNESS, 0.05, 0.02, 0.12),
            (ProductType.ANNUITY, 0.03, 0.06, 0.00),
        ],
    )
    def test_for_product_extended_factors_per_product(
        self,
        product_type: ProductType,
        expected_mortality: float,
        expected_lapse: float,
        expected_morbidity: float,
    ) -> None:
        cap = LICATCapital.for_product_extended(product_type)
        assert cap.factors.c2_mortality_factor == pytest.approx(expected_mortality)
        assert cap.factors.c2_lapse_factor == pytest.approx(expected_lapse)
        assert cap.factors.c2_morbidity_factor == pytest.approx(expected_morbidity)

    def test_for_product_extended_c1_c3_remain_zero(self) -> None:
        cap = LICATCapital.for_product_extended(ProductType.TERM)
        assert cap.factors.c1_asset_default == 0.0
        assert cap.factors.c3_interest_rate == 0.0

    def test_for_product_extended_di_has_higher_morbidity_than_term(self) -> None:
        di = LICATCapital.for_product_extended(ProductType.DISABILITY)
        term = LICATCapital.for_product_extended(ProductType.TERM)
        assert di.factors.c2_morbidity_factor > term.factors.c2_morbidity_factor
        assert term.factors.c2_morbidity_factor == 0.0


# ----------------------------------------------------------------------
# `for_product_interim` — interim C-1 / C-3 placeholders (ADR-072)
# ----------------------------------------------------------------------


class TestForProductInterim:
    """
    `for_product_interim` populates all five LICAT factors with conservative
    committee-stage placeholders. The interim C-1 / C-3 factors are intended
    to make the capital number less visibly incomplete before the Phase 5.4
    shock-based asset / ALM model lands. See ADR-072.
    """

    @pytest.mark.parametrize(
        "product_type, expected_mortality, expected_lapse, expected_morbidity",
        [
            (ProductType.TERM, 0.15, 0.05, 0.00),
            (ProductType.WHOLE_LIFE, 0.10, 0.03, 0.00),
            (ProductType.UNIVERSAL_LIFE, 0.08, 0.04, 0.00),
            (ProductType.DISABILITY, 0.05, 0.02, 0.15),
            (ProductType.CRITICAL_ILLNESS, 0.05, 0.02, 0.12),
            (ProductType.ANNUITY, 0.03, 0.06, 0.00),
        ],
    )
    def test_interim_preserves_extended_c2_factors_per_product(
        self,
        product_type: ProductType,
        expected_mortality: float,
        expected_lapse: float,
        expected_morbidity: float,
    ) -> None:
        """C-2 factors match `for_product_extended` — interim only adds C-1 / C-3."""
        cap = LICATCapital.for_product_interim(product_type)
        assert cap.factors.c2_mortality_factor == pytest.approx(expected_mortality)
        assert cap.factors.c2_lapse_factor == pytest.approx(expected_lapse)
        assert cap.factors.c2_morbidity_factor == pytest.approx(expected_morbidity)

    @pytest.mark.parametrize(
        "product_type, expected_c1, expected_c3",
        [
            (ProductType.TERM, 0.005, 0.005),
            (ProductType.WHOLE_LIFE, 0.005, 0.010),
            (ProductType.UNIVERSAL_LIFE, 0.005, 0.015),
            (ProductType.DISABILITY, 0.005, 0.005),
            (ProductType.CRITICAL_ILLNESS, 0.005, 0.005),
            (ProductType.ANNUITY, 0.005, 0.020),
        ],
    )
    def test_interim_c1_c3_factors_per_product(
        self,
        product_type: ProductType,
        expected_c1: float,
        expected_c3: float,
    ) -> None:
        cap = LICATCapital.for_product_interim(product_type)
        assert cap.factors.c1_asset_default == pytest.approx(expected_c1)
        assert cap.factors.c3_interest_rate == pytest.approx(expected_c3)

    def test_interim_annuity_has_highest_c3(self) -> None:
        """Long-duration annuity reserves carry the most interest-rate risk."""
        annuity = LICATCapital.for_product_interim(ProductType.ANNUITY)
        term = LICATCapital.for_product_interim(ProductType.TERM)
        wl = LICATCapital.for_product_interim(ProductType.WHOLE_LIFE)
        assert annuity.factors.c3_interest_rate > wl.factors.c3_interest_rate
        assert wl.factors.c3_interest_rate > term.factors.c3_interest_rate

    def test_interim_c1_uniform_across_products(self) -> None:
        """Asset-default C-1 is the same placeholder for all products in the interim schedule."""
        factors_seen = {
            LICATCapital.for_product_interim(p).factors.c1_asset_default for p in ProductType
        }
        assert len(factors_seen) == 1
        assert factors_seen == {0.005}


class TestForProductInterimBackwardCompat:
    """`for_product` and `for_product_extended` are unchanged — C-1 / C-3 stay zero."""

    @pytest.mark.parametrize(
        "product_type",
        [
            ProductType.TERM,
            ProductType.WHOLE_LIFE,
            ProductType.UNIVERSAL_LIFE,
            ProductType.DISABILITY,
            ProductType.CRITICAL_ILLNESS,
            ProductType.ANNUITY,
        ],
    )
    def test_for_product_c1_c3_remain_zero(self, product_type: ProductType) -> None:
        cap = LICATCapital.for_product(product_type)
        assert cap.factors.c1_asset_default == 0.0
        assert cap.factors.c3_interest_rate == 0.0

    @pytest.mark.parametrize(
        "product_type",
        [
            ProductType.TERM,
            ProductType.WHOLE_LIFE,
            ProductType.UNIVERSAL_LIFE,
            ProductType.DISABILITY,
            ProductType.CRITICAL_ILLNESS,
            ProductType.ANNUITY,
        ],
    )
    def test_for_product_extended_c1_c3_remain_zero(self, product_type: ProductType) -> None:
        cap = LICATCapital.for_product_extended(product_type)
        assert cap.factors.c1_asset_default == 0.0
        assert cap.factors.c3_interest_rate == 0.0


class TestForProductInterimAppliesToCapital:
    """
    Closed-form check: when the interim constructor is used, C-1 and C-3
    contribute the expected factor * reserve to `capital_by_period`.
    """

    def test_term_interim_c1_and_c3_applied(self) -> None:
        n = 12
        reserve = 100_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital.for_product_interim(ProductType.TERM)
        result = cap.required_capital(cf)

        # TERM: C-1 = 0.005 * 100K = 500; C-3 = 0.005 * 100K = 500
        np.testing.assert_allclose(result.c1_component, np.full(n, 500.0, dtype=np.float64))
        np.testing.assert_allclose(result.c3_component, np.full(n, 500.0, dtype=np.float64))

    def test_annuity_interim_c3_largest(self) -> None:
        n = 6
        reserve = 1_000_000.0
        nar = np.zeros(n, dtype=np.float64)  # annuities have no NAR
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital.for_product_interim(ProductType.ANNUITY)
        result = cap.required_capital(cf)

        # ANNUITY: C-3 = 0.02 * 1M = 20K
        np.testing.assert_allclose(result.c3_component, np.full(n, 20_000.0, dtype=np.float64))

    def test_interim_capital_sums_all_five_components(self) -> None:
        n = 8
        reserve = 200_000.0
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        cap = LICATCapital.for_product_interim(ProductType.WHOLE_LIFE)
        result = cap.required_capital(cf)

        # WL interim: mortality=0.10, lapse=0.03, morbidity=0.00, C-1=0.005, C-3=0.010
        expected_mortality = 0.10 * 500_000.0
        expected_lapse = 0.03 * 200_000.0
        expected_morbidity = 0.0
        expected_c1 = 0.005 * 200_000.0
        expected_c3 = 0.010 * 200_000.0
        expected_total = (
            expected_mortality + expected_lapse + expected_morbidity + expected_c1 + expected_c3
        )
        np.testing.assert_allclose(
            result.capital_by_period, np.full(n, expected_total, dtype=np.float64)
        )

    def test_interim_increases_capital_vs_extended(self) -> None:
        """Interim adds non-zero C-1 and C-3 on top of extended → higher capital."""
        n = 6
        reserve = 100_000.0
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)
        extended = LICATCapital.for_product_extended(ProductType.WHOLE_LIFE).required_capital(cf)
        interim = LICATCapital.for_product_interim(ProductType.WHOLE_LIFE).required_capital(cf)

        # Interim is strictly higher because c1 and c3 are positive and reserves > 0.
        assert (interim.capital_by_period > extended.capital_by_period).all()
        # Difference is exactly the C-1 + C-3 contribution.
        diff = interim.capital_by_period - extended.capital_by_period
        expected_diff = (0.005 + 0.010) * reserve
        np.testing.assert_allclose(diff, np.full(n, expected_diff, dtype=np.float64))


def test_module_exports() -> None:
    """LICAT capital symbols are exposed via the analytics package."""
    from polaris_re.analytics import (
        CapitalResult as ExportedCapitalResult,
    )
    from polaris_re.analytics import (
        LICATCapital as ExportedLICATCapital,
    )
    from polaris_re.analytics import (
        LICATFactors as ExportedLICATFactors,
    )

    assert ExportedLICATCapital is LICATCapital
    assert ExportedLICATFactors is LICATFactors
    assert ExportedCapitalResult is CapitalResult
