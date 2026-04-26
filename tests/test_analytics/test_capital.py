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
