"""
Tests for analytics/rbc.py — US NAIC Life RBC capital module (ADR-098).

Epic 3 (Cross-jurisdiction capital) Slice 1 scope: standalone factor-based
`RBCCapital` calculator with the NAIC covariance square-root aggregation, plus
the shared `CapitalModel` / `CapitalSchedule` protocols in
`analytics/capital_base.py`.

Closed-form verification: RBC = C0 + C4a + sqrt[(C1o+C3a)^2 + C1cs^2 + C2^2 +
C3b^2 + C3c^2 + C4b^2], ACL = 1/2 RBC.

Note: this slice does NOT integrate with ProfitTester — RoC with an RBC model
is Slice 2. The default `licat` pricing path is untouched (goldens
byte-identical).
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.capital import CapitalResult, LICATCapital
from polaris_re.analytics.capital_base import (
    CapitalModel,
    CapitalSchedule,
    discount_stream,
    strain_of,
)
from polaris_re.analytics.rbc import RBCCapital, RBCFactors
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
    """Construct a minimal CashFlowResult for RBC capital tests."""
    arr = np.full(n, reserve, dtype=np.float64)
    return CashFlowResult(
        run_id="test-rbc",
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
# RBCFactors
# ----------------------------------------------------------------------


class TestRBCFactors:
    def test_default_factors(self) -> None:
        f = RBCFactors()
        # Only C-2 is non-zero by default; the rest are stubs.
        assert f.c2_factor == 0.00150
        assert f.c1o_other_assets == 0.0
        assert f.c3a_interest_rate == 0.0
        assert f.c0_affiliates == 0.0
        assert f.c4a_business == 0.0

    def test_factors_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            RBCFactors(c2_factor=-0.01)

    def test_factors_capped_at_one(self) -> None:
        with pytest.raises(ValueError):
            RBCFactors(c1o_other_assets=1.5)

    def test_factors_are_frozen(self) -> None:
        f = RBCFactors(c2_factor=0.002)
        with pytest.raises((ValueError, TypeError)):
            f.c2_factor = 0.003  # type: ignore[misc]


# ----------------------------------------------------------------------
# RBCCapital — product-type defaults
# ----------------------------------------------------------------------


class TestRBCForProduct:
    @pytest.mark.parametrize(
        "product_type, c2, c3a",
        [
            (ProductType.TERM, 0.00150, 0.0077),
            (ProductType.WHOLE_LIFE, 0.00150, 0.0154),
            (ProductType.UNIVERSAL_LIFE, 0.00150, 0.0154),
            (ProductType.DISABILITY, 0.00150, 0.0077),
            (ProductType.CRITICAL_ILLNESS, 0.00150, 0.0077),
            (ProductType.ANNUITY, 0.0, 0.0231),
        ],
    )
    def test_for_product_factor_schedule(
        self, product_type: ProductType, c2: float, c3a: float
    ) -> None:
        model = RBCCapital.for_product(product_type)
        assert model.factors.c2_factor == c2
        assert model.factors.c3a_interest_rate == c3a
        # C-1o is uniform across products.
        assert model.factors.c1o_other_assets == 0.010
        # Stubs stay zero.
        assert model.factors.c0_affiliates == 0.0
        assert model.factors.c4a_business == 0.0


# ----------------------------------------------------------------------
# RBCCapital — closed-form covariance aggregation
# ----------------------------------------------------------------------


class TestRBCCovariance:
    def test_covariance_closed_form_term(self) -> None:
        """RBC = sqrt[(C1o+C3a)^2 + C2^2] with only C1o/C2/C3a non-zero."""
        n = 12
        reserve = 100_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        model = RBCCapital.for_product(ProductType.TERM)
        res = model.required_capital(cf)

        c1o = 0.010 * reserve  # 1000
        c3a = 0.0077 * reserve  # 770
        c2 = 0.00150 * nar[0]  # 1500
        expected_cal = np.sqrt((c1o + c3a) ** 2 + c2**2)
        expected_acl = 0.5 * expected_cal

        np.testing.assert_allclose(res.capital_by_period, np.full(n, expected_cal))
        np.testing.assert_allclose(res.authorized_control_level, np.full(n, expected_acl))
        np.testing.assert_allclose(res.initial_capital, expected_cal)
        np.testing.assert_allclose(res.peak_capital, expected_cal)

    def test_covariance_full_formula_all_components(self) -> None:
        """All nine components present: C0 + C4a outside, the rest inside."""
        n = 6
        reserve = 50_000.0
        nar = np.full(n, 800_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        f = RBCFactors(
            c0_affiliates=0.001,
            c1cs_common_stock=0.02,
            c1o_other_assets=0.010,
            c2_factor=0.00150,
            c3a_interest_rate=0.0154,
            c3b_health_credit=0.003,
            c3c_market=0.004,
            c4a_business=0.002,
            c4b_health_admin=0.001,
        )
        res = RBCCapital(factors=f).required_capital(cf)

        c0 = 0.001 * reserve
        c1cs = 0.02 * reserve
        c1o = 0.010 * reserve
        c2 = 0.00150 * nar[0]
        c3a = 0.0154 * reserve
        c3b = 0.003 * reserve
        c3c = 0.004 * reserve
        c4a = 0.002 * reserve
        c4b = 0.001 * reserve
        inside = (c1o + c3a) ** 2 + c1cs**2 + c2**2 + c3b**2 + c3c**2 + c4b**2
        expected = c0 + c4a + np.sqrt(inside)

        np.testing.assert_allclose(res.capital_by_period, np.full(n, expected))
        # Components carried through individually.
        np.testing.assert_allclose(res.c1o_component, np.full(n, c1o))
        np.testing.assert_allclose(res.c2_component, np.full(n, c2))
        np.testing.assert_allclose(res.c3a_component, np.full(n, c3a))

    def test_acl_is_half_cal(self) -> None:
        cf = _make_cashflow(nar=np.full(24, 500_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.WHOLE_LIFE).required_capital(cf)
        np.testing.assert_allclose(res.authorized_control_level, 0.5 * res.capital_by_period)

    def test_c0_c4a_outside_root_no_diversification(self) -> None:
        """C-0 and C-4a add linearly (no covariance credit)."""
        n = 4
        reserve = 100_000.0
        nar = np.full(n, 200_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        base = RBCCapital(factors=RBCFactors(c2_factor=0.00150)).required_capital(cf)
        with_c0 = RBCCapital(
            factors=RBCFactors(c2_factor=0.00150, c0_affiliates=0.005)
        ).required_capital(cf)

        # Adding C-0 shifts CAL by exactly c0 (linear, outside the root).
        delta = with_c0.capital_by_period - base.capital_by_period
        np.testing.assert_allclose(delta, np.full(n, 0.005 * reserve))


# ----------------------------------------------------------------------
# RBCResult — schedule helpers & RBC ratio
# ----------------------------------------------------------------------


class TestRBCResultHelpers:
    def test_pv_capital_matches_manual_discount(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        rate = 0.10
        v = (1.0 + rate) ** (-1.0 / 12.0)
        factors = v ** np.arange(1, 13, dtype=np.float64)
        expected = float(np.dot(res.capital_by_period, factors))
        np.testing.assert_allclose(res.pv_capital(rate), expected)

    def test_capital_strain_flat_schedule(self) -> None:
        """Flat capital → one injection at t=0, zero thereafter."""
        cf = _make_cashflow(n=10, nar=np.full(10, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        strain = res.capital_strain()
        assert strain[0] == pytest.approx(res.capital_by_period[0])
        np.testing.assert_allclose(strain[1:], np.zeros(9))

    def test_pv_capital_strain_flat_collapses_to_initial(self) -> None:
        cf = _make_cashflow(n=10, nar=np.full(10, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        rate = 0.08
        v = (1.0 + rate) ** (-1.0 / 12.0)
        np.testing.assert_allclose(res.pv_capital_strain(rate), res.capital_by_period[0] * v)

    def test_rbc_ratio_closed_form(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        acl0 = res.authorized_control_level[0]
        tac = 5.0 * acl0
        np.testing.assert_allclose(res.rbc_ratio(tac), 5.0)

    def test_rbc_ratio_raises_when_acl_zero(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        # All-stub factor set → zero capital → ACL zero.
        res = RBCCapital(factors=RBCFactors(c2_factor=0.0)).required_capital(cf)
        with pytest.raises(PolarisComputationError):
            res.rbc_ratio(1_000_000.0)

    def test_capital_ratio_is_rbc_ratio(self) -> None:
        """The protocol `capital_ratio` is the RBC ratio (TAC / ACL₀); ADR-103."""
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        tac = 5.0 * res.authorized_control_level[0]
        np.testing.assert_allclose(res.capital_ratio(tac), 5.0)
        # rbc_ratio is now an alias of capital_ratio — identical for any input.
        np.testing.assert_allclose(res.capital_ratio(tac), res.rbc_ratio(tac))

    def test_capital_ratio_raises_when_acl_zero(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = RBCCapital(factors=RBCFactors(c2_factor=0.0)).required_capital(cf)
        with pytest.raises(PolarisComputationError):
            res.capital_ratio(1_000_000.0)


# ----------------------------------------------------------------------
# RBCCapital — NAR resolution & basis guard
# ----------------------------------------------------------------------


class TestRBCNarAndBasis:
    def test_rejects_ceded_basis(self) -> None:
        cf = _make_cashflow(basis="CEDED", nar=np.full(24, 1.0, dtype=np.float64))
        with pytest.raises(ValueError, match="CEDED"):
            RBCCapital.for_product(ProductType.TERM).required_capital(cf)

    def test_requires_nar(self) -> None:
        cf = _make_cashflow(nar=None)
        with pytest.raises(PolarisComputationError, match="requires NAR"):
            RBCCapital.for_product(ProductType.TERM).required_capital(cf)

    def test_nar_override_takes_precedence(self) -> None:
        n = 12
        cf = _make_cashflow(n=n, nar=np.full(n, 1.0, dtype=np.float64))
        override = np.full(n, 2_000_000.0, dtype=np.float64)
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf, nar=override)
        np.testing.assert_allclose(res.c2_component, 0.00150 * override)

    def test_nar_override_length_mismatch_raises(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1.0, dtype=np.float64))
        with pytest.raises(PolarisComputationError, match="does not match"):
            RBCCapital.for_product(ProductType.TERM).required_capital(
                cf, nar=np.full(6, 1.0, dtype=np.float64)
            )

    def test_accepts_net_basis(self) -> None:
        cf = _make_cashflow(basis="NET", nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        assert res.projection_months == 24
        assert res.capital_by_period.dtype == np.float64

    def test_empty_projection(self) -> None:
        cf = _make_cashflow(n=0, nar=np.array([], dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        assert res.initial_capital == 0.0
        assert res.peak_capital == 0.0


# ----------------------------------------------------------------------
# Shared CapitalModel / CapitalSchedule protocols (ADR-098)
# ----------------------------------------------------------------------


class TestCapitalProtocols:
    def test_rbc_result_satisfies_capital_schedule(self) -> None:
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        assert isinstance(res, CapitalSchedule)

    def test_licat_result_satisfies_capital_schedule(self) -> None:
        """The pre-existing LICAT result conforms structurally — no changes."""
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = LICATCapital.for_product(ProductType.TERM).required_capital(cf)
        assert isinstance(res, CapitalResult)
        assert isinstance(res, CapitalSchedule)

    def test_rbc_capital_satisfies_capital_model(self) -> None:
        assert isinstance(RBCCapital.for_product(ProductType.TERM), CapitalModel)

    def test_licat_capital_satisfies_capital_model(self) -> None:
        assert isinstance(LICATCapital.for_product(ProductType.TERM), CapitalModel)

    def test_discount_stream_helper_empty(self) -> None:
        assert discount_stream(np.array([], dtype=np.float64), 0.10) == 0.0

    def test_strain_of_helper_empty(self) -> None:
        out = strain_of(np.array([], dtype=np.float64))
        assert out.shape == (0,)
        assert out.dtype == np.float64

    def test_strain_of_helper_increasing(self) -> None:
        cap = np.array([100.0, 250.0, 400.0], dtype=np.float64)
        np.testing.assert_allclose(strain_of(cap), np.array([100.0, 150.0, 150.0]))


# ----------------------------------------------------------------------
# Cross-jurisdiction sanity: RBC and LICAT differ on the same block
# ----------------------------------------------------------------------


class TestJurisdictionDifference:
    def test_rbc_differs_from_licat(self) -> None:
        """The two standards produce different capital on the same block —
        confirming RBC is a genuinely distinct jurisdiction, not a LICAT alias."""
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        rbc = RBCCapital.for_product(ProductType.TERM).required_capital(cf)
        licat = LICATCapital.for_product(ProductType.TERM).required_capital(cf)
        assert not np.allclose(rbc.capital_by_period, licat.capital_by_period)
