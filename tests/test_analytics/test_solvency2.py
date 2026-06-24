"""
Tests for analytics/solvency2.py — EU Solvency II SCR capital module (ADR-100).

Epic 3 (Cross-jurisdiction capital) Slice 3 scope: standalone factor-based
`SolvencyIICapital` calculator with the standard-formula **correlation-matrix**
BSCR aggregation `sqrt(rᵀ · Corr · r)` and the cost-of-capital risk margin, plus
conformance to the shared `CapitalModel` / `CapitalSchedule` protocols in
`analytics/capital_base.py`.

Closed-form verification: the life-underwriting SCR and the top-level BSCR are
both quadratic-form square roots against the Delegated Regulation (EU) 2015/35
standard-formula correlation matrices.

Note: this slice does NOT integrate with the CLI / API / Excel surfaces — the
`--capital solvency2` selector is Slice 4. The default `licat` pricing path is
untouched (goldens byte-identical); `solvency2` remains rejected at the CLI/API
boundary until Slice 4.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.capital import CapitalResult, LICATCapital
from polaris_re.analytics.capital_base import CapitalModel, CapitalSchedule
from polaris_re.analytics.solvency2 import (
    LIFE_CORRELATION,
    TOP_LEVEL_CORRELATION,
    SolvencyIICapital,
    SolvencyIIFactors,
    SolvencyIIResult,
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
    """Construct a minimal CashFlowResult for Solvency II capital tests."""
    arr = np.full(n, reserve, dtype=np.float64)
    return CashFlowResult(
        run_id="test-solvency2",
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
# SolvencyIIFactors
# ----------------------------------------------------------------------


class TestSolvencyIIFactors:
    def test_default_factors(self) -> None:
        f = SolvencyIIFactors()
        # Catastrophe is the citable standard-formula life-CAT shock (1.5 per
        # mille of capital-at-risk); mortality is non-zero; operational stub 0.
        assert f.mortality_factor == 0.0020
        assert f.catastrophe_factor == 0.0015
        assert f.operational_factor == 0.0

    def test_factors_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            SolvencyIIFactors(mortality_factor=-0.01)

    def test_factors_capped_at_one(self) -> None:
        with pytest.raises(ValueError):
            SolvencyIIFactors(market_factor=1.5)

    def test_factors_are_frozen(self) -> None:
        f = SolvencyIIFactors(mortality_factor=0.002)
        with pytest.raises((ValueError, TypeError)):
            f.mortality_factor = 0.003  # type: ignore[misc]


# ----------------------------------------------------------------------
# Correlation matrices (Delegated Regulation 2015/35 Annex IV)
# ----------------------------------------------------------------------


class TestCorrelationMatrices:
    def test_life_matrix_is_symmetric_unit_diagonal(self) -> None:
        c = LIFE_CORRELATION
        assert c.shape == (3, 3)
        np.testing.assert_allclose(c, c.T)
        np.testing.assert_allclose(np.diag(c), np.ones(3))

    def test_life_matrix_offdiagonals(self) -> None:
        # Order: mortality, lapse, catastrophe.
        # mortality-lapse 0; mortality-cat 0.25; lapse-cat 0.25.
        c = LIFE_CORRELATION
        assert c[0, 1] == 0.0
        assert c[0, 2] == 0.25
        assert c[1, 2] == 0.25

    def test_top_matrix_is_symmetric_unit_diagonal(self) -> None:
        c = TOP_LEVEL_CORRELATION
        assert c.shape == (3, 3)
        np.testing.assert_allclose(c, c.T)
        np.testing.assert_allclose(np.diag(c), np.ones(3))

    def test_top_matrix_offdiagonals_all_quarter(self) -> None:
        # Order: market, counterparty, life. All pairwise 0.25.
        c = TOP_LEVEL_CORRELATION
        assert c[0, 1] == 0.25
        assert c[0, 2] == 0.25
        assert c[1, 2] == 0.25


# ----------------------------------------------------------------------
# SolvencyIICapital — product-type defaults
# ----------------------------------------------------------------------


class TestSolvencyIIForProduct:
    @pytest.mark.parametrize(
        "product_type, mortality, lapse, cat",
        [
            (ProductType.TERM, 0.0020, 0.0040, 0.0015),
            (ProductType.WHOLE_LIFE, 0.0020, 0.0030, 0.0015),
            (ProductType.UNIVERSAL_LIFE, 0.0020, 0.0040, 0.0015),
            (ProductType.DISABILITY, 0.0020, 0.0020, 0.0015),
            (ProductType.CRITICAL_ILLNESS, 0.0020, 0.0020, 0.0015),
            (ProductType.ANNUITY, 0.0, 0.0060, 0.0),
        ],
    )
    def test_for_product_factor_schedule(
        self, product_type: ProductType, mortality: float, lapse: float, cat: float
    ) -> None:
        model = SolvencyIICapital.for_product(product_type)
        assert model.factors.mortality_factor == mortality
        assert model.factors.lapse_factor == lapse
        assert model.factors.catastrophe_factor == cat
        # Market / counterparty are uniform across products.
        assert model.factors.market_factor == 0.0050
        assert model.factors.counterparty_factor == 0.0010
        # Operational stays a zero stub.
        assert model.factors.operational_factor == 0.0


# ----------------------------------------------------------------------
# Life-underwriting sub-module: correlation-matrix aggregation
# ----------------------------------------------------------------------


class TestLifeUnderwritingAggregation:
    def test_life_scr_closed_form(self) -> None:
        """life_SCR = sqrt(m² + l² + c² + 0.5·m·c + 0.5·l·c)."""
        n = 12
        reserve = 100_000.0
        nar = np.full(n, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        model = SolvencyIICapital.for_product(ProductType.TERM)
        res = model.required_capital(cf)

        m = 0.0020 * nar[0]  # mortality (x NAR)
        lp = 0.0040 * reserve  # lapse (x reserve)
        c = 0.0015 * nar[0]  # catastrophe (x NAR)
        # mort-lapse 0; mort-cat 0.25; lapse-cat 0.25.
        expected_life = np.sqrt(m**2 + lp**2 + c**2 + 2 * 0.25 * m * c + 2 * 0.25 * lp * c)

        np.testing.assert_allclose(res.life_underwriting_component, np.full(n, expected_life))
        np.testing.assert_allclose(res.mortality_component, np.full(n, m))
        np.testing.assert_allclose(res.lapse_component, np.full(n, lp))
        np.testing.assert_allclose(res.catastrophe_component, np.full(n, c))

    def test_life_scr_diversification_below_simple_sum(self) -> None:
        """Correlation aggregation gives diversification credit (< linear sum)."""
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        simple_sum = res.mortality_component + res.lapse_component + res.catastrophe_component
        assert np.all(res.life_underwriting_component < simple_sum)


# ----------------------------------------------------------------------
# Top-level BSCR: correlation-matrix aggregation
# ----------------------------------------------------------------------


class TestBSCRAggregation:
    def test_bscr_closed_form(self) -> None:
        """BSCR = sqrt(M² + D² + L² + 0.5·(MD + ML + DL)) with all-0.25 corr."""
        n = 6
        reserve = 50_000.0
        nar = np.full(n, 800_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)

        market = res.market_component[0]
        counterparty = res.counterparty_component[0]
        life = res.life_underwriting_component[0]
        expected_bscr = np.sqrt(
            market**2
            + counterparty**2
            + life**2
            + 2 * 0.25 * (market * counterparty + market * life + counterparty * life)
        )
        # Operational is a zero stub → SCR == BSCR.
        np.testing.assert_allclose(res.capital_by_period, np.full(n, expected_bscr))
        np.testing.assert_allclose(res.bscr_component, np.full(n, expected_bscr))

    def test_operational_adds_linearly_outside_bscr(self) -> None:
        """Operational risk adds outside the BSCR correlation matrix (linear)."""
        n = 4
        reserve = 100_000.0
        nar = np.full(n, 500_000.0, dtype=np.float64)
        cf = _make_cashflow(n=n, reserve=reserve, nar=nar)

        base = SolvencyIICapital.for_product(ProductType.TERM)
        with_op = SolvencyIICapital(
            factors=base.factors.model_copy(update={"operational_factor": 0.002})
        )
        res_base = base.required_capital(cf)
        res_op = with_op.required_capital(cf)

        delta = res_op.capital_by_period - res_base.capital_by_period
        np.testing.assert_allclose(delta, np.full(n, 0.002 * reserve))

    def test_initial_and_peak_capital(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        np.testing.assert_allclose(res.initial_capital, res.capital_by_period[0])
        np.testing.assert_allclose(res.peak_capital, res.capital_by_period.max())


# ----------------------------------------------------------------------
# Risk margin (cost-of-capital)
# ----------------------------------------------------------------------


class TestRiskMargin:
    def test_risk_margin_closed_form_flat_schedule(self) -> None:
        """RM = CoC x Σ_t SCR · v^t for a flat SCR schedule."""
        n = 12
        cf = _make_cashflow(n=n, nar=np.full(n, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)

        rate = 0.04
        coc = 0.06
        v = (1.0 + rate) ** (-1.0 / 12.0)
        factors = v ** np.arange(1, n + 1, dtype=np.float64)
        expected = coc * float(np.dot(res.capital_by_period, factors))
        np.testing.assert_allclose(res.risk_margin(rate), expected)

    def test_risk_margin_custom_coc(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        # Linear in CoC: 12% is exactly double 6%.
        np.testing.assert_allclose(
            res.risk_margin(0.04, coc=0.12), 2.0 * res.risk_margin(0.04, coc=0.06)
        )

    def test_risk_margin_zero_for_empty(self) -> None:
        cf = _make_cashflow(n=0, nar=np.array([], dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        assert res.risk_margin(0.04) == 0.0


class TestSolvencyRatio:
    def test_capital_ratio_own_funds_over_scr(self) -> None:
        """Solvency ratio = own funds / SCR₀ (ADR-103)."""
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        own_funds = 2.5 * res.capital_by_period[0]  # a 250% solvency position
        np.testing.assert_allclose(res.capital_ratio(own_funds), 2.5)

    def test_capital_ratio_raises_when_scr_zero(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        # All-zero factor set → zero SCR.
        zeroed = SolvencyIIFactors(
            mortality_factor=0.0,
            lapse_factor=0.0,
            catastrophe_factor=0.0,
            market_factor=0.0,
            counterparty_factor=0.0,
            operational_factor=0.0,
        )
        res = SolvencyIICapital(factors=zeroed).required_capital(cf)
        with pytest.raises(PolarisComputationError):
            res.capital_ratio(1_000_000.0)


# ----------------------------------------------------------------------
# SolvencyIIResult — schedule helpers (CapitalSchedule surface)
# ----------------------------------------------------------------------


class TestSolvencyIIResultHelpers:
    def test_pv_capital_matches_manual_discount(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        rate = 0.10
        v = (1.0 + rate) ** (-1.0 / 12.0)
        factors = v ** np.arange(1, 13, dtype=np.float64)
        expected = float(np.dot(res.capital_by_period, factors))
        np.testing.assert_allclose(res.pv_capital(rate), expected)

    def test_capital_strain_flat_schedule(self) -> None:
        cf = _make_cashflow(n=10, nar=np.full(10, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        strain = res.capital_strain()
        assert strain[0] == pytest.approx(res.capital_by_period[0])
        np.testing.assert_allclose(strain[1:], np.zeros(9))

    def test_pv_capital_strain_flat_collapses_to_initial(self) -> None:
        cf = _make_cashflow(n=10, nar=np.full(10, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        rate = 0.08
        v = (1.0 + rate) ** (-1.0 / 12.0)
        np.testing.assert_allclose(res.pv_capital_strain(rate), res.capital_by_period[0] * v)


# ----------------------------------------------------------------------
# NAR resolution & basis guard
# ----------------------------------------------------------------------


class TestSolvencyIINarAndBasis:
    def test_rejects_ceded_basis(self) -> None:
        cf = _make_cashflow(basis="CEDED", nar=np.full(24, 1.0, dtype=np.float64))
        with pytest.raises(ValueError, match="CEDED"):
            SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)

    def test_requires_nar(self) -> None:
        cf = _make_cashflow(nar=None)
        with pytest.raises(PolarisComputationError, match="requires NAR"):
            SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)

    def test_nar_override_takes_precedence(self) -> None:
        n = 12
        cf = _make_cashflow(n=n, nar=np.full(n, 1.0, dtype=np.float64))
        override = np.full(n, 2_000_000.0, dtype=np.float64)
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf, nar=override)
        np.testing.assert_allclose(res.mortality_component, 0.0020 * override)

    def test_nar_override_length_mismatch_raises(self) -> None:
        cf = _make_cashflow(n=12, nar=np.full(12, 1.0, dtype=np.float64))
        with pytest.raises(PolarisComputationError, match="does not match"):
            SolvencyIICapital.for_product(ProductType.TERM).required_capital(
                cf, nar=np.full(6, 1.0, dtype=np.float64)
            )

    def test_accepts_net_basis(self) -> None:
        cf = _make_cashflow(basis="NET", nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        assert res.projection_months == 24
        assert res.capital_by_period.dtype == np.float64

    def test_empty_projection(self) -> None:
        cf = _make_cashflow(n=0, nar=np.array([], dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        assert res.initial_capital == 0.0
        assert res.peak_capital == 0.0
        assert res.capital_by_period.shape == (0,)


# ----------------------------------------------------------------------
# Shared CapitalModel / CapitalSchedule protocols (ADR-098)
# ----------------------------------------------------------------------


class TestCapitalProtocols:
    def test_solvency2_result_satisfies_capital_schedule(self) -> None:
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        res = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        assert isinstance(res, SolvencyIIResult)
        assert isinstance(res, CapitalSchedule)

    def test_solvency2_capital_satisfies_capital_model(self) -> None:
        assert isinstance(SolvencyIICapital.for_product(ProductType.TERM), CapitalModel)


# ----------------------------------------------------------------------
# Cross-jurisdiction sanity: SCR differs from LICAT on the same block
# ----------------------------------------------------------------------


class TestJurisdictionDifference:
    def test_solvency2_differs_from_licat(self) -> None:
        """The two standards produce different capital on the same block —
        confirming Solvency II is a genuinely distinct jurisdiction."""
        cf = _make_cashflow(nar=np.full(24, 1_000_000.0, dtype=np.float64))
        scr = SolvencyIICapital.for_product(ProductType.TERM).required_capital(cf)
        licat = LICATCapital.for_product(ProductType.TERM).required_capital(cf)
        assert isinstance(licat, CapitalResult)
        assert not np.allclose(scr.capital_by_period, licat.capital_by_period)
