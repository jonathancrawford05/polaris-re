"""
Tests for IFRS 17 measurement models (analytics/ifrs17.py).

Closed-form verification:
1. BEL at inception = PV of net fulfilment cash flows at the given rate
2. BBA: profitable contract → initial_csm > 0, loss_component = 0
3. BBA: onerous contract → loss_component > 0, initial_csm = 0
4. CSM is fully amortised by end of projection (csm_schedule[-1] ≈ 0)
5. PAA: LRC at t=0 equals total premiums; declines to 0 at T
6. VFA: insurance_revenue ≈ variable fees + CSM release
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.ifrs17 import IFRS17Measurement, IFRS17Result
from polaris_re.core.cashflow import CashFlowResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gross_cashflow(
    T: int = 24,
    monthly_premium: float = 100.0,
    monthly_claim: float = 10.0,
    monthly_expense: float = 5.0,
    monthly_lapse: float = 2.0,
    discount_rate: float = 0.05,
    valuation_date: date | None = None,
) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult for IFRS 17 testing."""
    if valuation_date is None:
        valuation_date = date(2025, 1, 1)
    premiums = np.full(T, monthly_premium, dtype=np.float64)
    claims = np.full(T, monthly_claim, dtype=np.float64)
    expenses = np.full(T, monthly_expense, dtype=np.float64)
    lapses = np.full(T, monthly_lapse, dtype=np.float64)
    net_cf = premiums - claims - lapses - expenses
    reserves = np.zeros(T, dtype=np.float64)
    return CashFlowResult(
        run_id="ifrs17_test",
        valuation_date=valuation_date,
        basis="GROSS",
        assumption_set_version="v1",
        product_type="TERM",
        projection_months=T,
        time_index=np.arange(
            np.datetime64("2025-01"), np.datetime64("2025-01") + T, dtype="datetime64[M]"
        ),
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=lapses,
        expenses=expenses,
        reserve_balance=reserves,
        reserve_increase=reserves.copy(),
        net_cash_flow=net_cf,
    )


# ---------------------------------------------------------------------------
# IFRS17Measurement validation
# ---------------------------------------------------------------------------

class TestIFRS17MeasurementValidation:

    def test_raises_on_non_gross_basis(self):
        """IFRS17Measurement requires GROSS basis input."""
        cf = CashFlowResult(
            run_id="x",
            valuation_date=date(2025, 1, 1),
            basis="NET",
            assumption_set_version="v1",
            product_type="TERM",
        )
        with pytest.raises(ValueError, match="GROSS"):
            IFRS17Measurement(cashflows=cf, discount_rate=0.04)

    def test_raises_on_wrong_coverage_units_length(self):
        cf = _make_gross_cashflow(T=24)
        wrong_cu = np.ones(12, dtype=np.float64)  # wrong length
        with pytest.raises(ValueError, match="coverage_units"):
            IFRS17Measurement(cashflows=cf, discount_rate=0.04, coverage_units=wrong_cu)


# ---------------------------------------------------------------------------
# BBA tests
# ---------------------------------------------------------------------------

class TestBBA:

    def test_bel_at_inception_closed_form(self):
        """
        CLOSED-FORM: For a flat cash flow stream, BEL[0] should equal the
        PV of net fulfilment CFs at the given discount rate.

        FCF[t] = claims + lapses + expenses - premiums (positive = net liability)
        BEL[0] = sum_{t=0}^{T-1} FCF[t] * v^(t+1)
        """
        T = 12
        premium = 100.0
        claim = 20.0
        expense = 5.0
        lapse = 3.0
        discount_rate = 0.06

        fcf_per_period = claim + expense + lapse - premium  # = -72.0 (net asset for insurer)
        v = (1.0 + discount_rate) ** (-1.0 / 12.0)
        disc = v ** np.arange(1, T + 1, dtype=np.float64)
        expected_bel = float(np.dot(np.full(T, fcf_per_period), disc))

        cf = _make_gross_cashflow(T=T, monthly_premium=premium, monthly_claim=claim,
                                   monthly_expense=expense, monthly_lapse=lapse,
                                   discount_rate=discount_rate)
        m = IFRS17Measurement(cashflows=cf, discount_rate=discount_rate, ra_factor=0.0)
        result = m.measure_bba()

        np.testing.assert_allclose(result.initial_bel, expected_bel, rtol=1e-6)

    def test_profitable_contract_has_positive_csm(self):
        """A profitable contract (premiums > outflows) yields CSM > 0, loss_component = 0."""
        # Premiums 100, outflows 20 — very profitable
        cf = _make_gross_cashflow(monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04, ra_factor=0.05)
        result = m.measure_bba()

        assert result.initial_csm > 0.0
        assert result.loss_component == 0.0

    def test_onerous_contract_has_positive_loss_component(self):
        """An onerous contract (outflows > premiums) yields loss_component > 0, CSM = 0."""
        # Claims heavily exceed premiums
        cf = _make_gross_cashflow(monthly_premium=10.0, monthly_claim=100.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04, ra_factor=0.05)
        result = m.measure_bba()

        assert result.initial_csm == 0.0
        assert result.loss_component > 0.0

    def test_initial_liability_structure(self):
        """For profitable contract: BEL + RA + CSM = 0 at inception (all profit is deferred)."""
        cf = _make_gross_cashflow(monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04, ra_factor=0.05)
        result = m.measure_bba()

        # At inception: BEL + RA + CSM = 0 (profitable contract, full offset)
        total_fcf = result.initial_bel + result.initial_ra
        np.testing.assert_allclose(
            total_fcf + result.initial_csm, 0.0, atol=1e-6,
            err_msg="BEL + RA + CSM should equal 0 at inception for profitable contract"
        )

    def test_csm_fully_amortised_by_end(self):
        """
        By the end of the coverage period, all CSM should have been released.

        result.csm stores the opening CSM balance for each period (before release).
        The total CSM released (sum of csm_release) equals initial_csm plus
        all interest accreted. Verify this balance-checks to zero.
        """
        T = 24
        cf = _make_gross_cashflow(T=T, monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04, ra_factor=0.05)
        result = m.measure_bba()

        # Total CSM available = initial_csm + all accretions
        # Total CSM released = sum(csm_release)
        # Residual at end = total_available - total_released should ≈ 0
        total_available = result.initial_csm + float(result.csm_interest_accretion.sum())
        total_released = float(result.csm_release.sum())
        np.testing.assert_allclose(
            total_available, total_released, rtol=1e-6,
            err_msg="Total CSM released should equal initial CSM plus all accretions"
        )

    def test_bel_schedule_shape(self):
        """BEL, RA, CSM, insurance_liability arrays should all have shape (T,)."""
        T = 36
        cf = _make_gross_cashflow(T=T)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05)
        result = m.measure_bba()

        assert result.bel.shape == (T,)
        assert result.risk_adjustment.shape == (T,)
        assert result.csm.shape == (T,)
        assert result.insurance_liability.shape == (T,)
        assert result.csm_release.shape == (T,)
        assert result.insurance_revenue.shape == (T,)

    def test_insurance_liability_equals_bel_plus_ra_plus_csm(self):
        """insurance_liability = BEL + RA + CSM at each period."""
        cf = _make_gross_cashflow(T=12)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05, ra_factor=0.05)
        result = m.measure_bba()

        expected = result.bel + result.risk_adjustment + result.csm
        np.testing.assert_allclose(result.insurance_liability, expected, rtol=1e-8)

    def test_total_csm_release_equals_initial_csm(self):
        """
        CLOSED-FORM: Total CSM released plus residual (0) equals initial CSM
        plus accumulated interest. Since the CSM accretes and releases fully,
        the total released should equal initial_csm compounded at the discount rate.
        """
        T = 12
        cf = _make_gross_cashflow(T=T, monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.06)
        result = m.measure_bba()

        # Total released = sum of csm_release + residual (which should be 0)
        total_released = float(result.csm_release.sum())
        # Should equal initial_csm + all accretions (since CSM ends at 0)
        expected = result.initial_csm + float(result.csm_interest_accretion.sum())
        np.testing.assert_allclose(total_released, expected, rtol=1e-6)

    def test_ra_non_negative(self):
        """Risk Adjustment must be non-negative (it is compensation for uncertainty)."""
        cf = _make_gross_cashflow(T=24)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05, ra_factor=0.05)
        result = m.measure_bba()
        assert (result.risk_adjustment >= 0.0).all()

    def test_zero_ra_factor(self):
        """With ra_factor=0, RA array is all zeros and CSM absorbs full initial profit."""
        cf = _make_gross_cashflow(monthly_premium=100.0, monthly_claim=5.0,
                                   monthly_expense=3.0, monthly_lapse=1.0)
        m_with_ra = IFRS17Measurement(cashflows=cf, discount_rate=0.05, ra_factor=0.05)
        m_no_ra = IFRS17Measurement(cashflows=cf, discount_rate=0.05, ra_factor=0.0)
        r_with = m_with_ra.measure_bba()
        r_no = m_no_ra.measure_bba()

        np.testing.assert_allclose(r_no.risk_adjustment, 0.0, atol=1e-12)
        # No RA means CSM must absorb more initial profit
        assert r_no.initial_csm >= r_with.initial_csm

    def test_custom_coverage_units(self):
        """Custom coverage units should not raise and should produce valid output."""
        T = 12
        cf = _make_gross_cashflow(T=T)
        # Uniform coverage units
        cu = np.ones(T, dtype=np.float64)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05, coverage_units=cu)
        result = m.measure_bba()
        assert result.approach == "BBA"
        assert result.bel.shape == (T,)

    def test_pv_insurance_revenue_positive(self):
        """PV of insurance revenue should be positive for a profitable contract."""
        cf = _make_gross_cashflow(monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05)
        result = m.measure_bba()
        assert result.pv_insurance_revenue() > 0.0


# ---------------------------------------------------------------------------
# PAA tests
# ---------------------------------------------------------------------------

class TestPAA:

    def test_lrc_at_inception_equals_total_premiums(self):
        """PAA: LRC at t=0 should equal the total premiums over the coverage period."""
        T = 12
        monthly_premium = 100.0
        cf = _make_gross_cashflow(T=T, monthly_premium=monthly_premium)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()

        assert result.lrc is not None
        expected_lrc_0 = monthly_premium * T  # total premiums = 1200
        np.testing.assert_allclose(result.lrc[0], expected_lrc_0, rtol=1e-6)

    def test_lrc_declines_monotonically(self):
        """
        PAA: LRC should be monotonically non-increasing over time.

        LRC[t] represents the unearned premium at the START of period t.
        It declines from total_premiums at t=0 toward zero as coverage is provided.
        The final value LRC[T-1] is one period's worth of unearned premium
        (the last period is earned during period T-1, not before it).
        """
        T = 12
        monthly_premium = 100.0
        cf = _make_gross_cashflow(T=T, monthly_premium=monthly_premium)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()

        assert result.lrc is not None
        # LRC should be monotonically non-increasing
        assert (np.diff(result.lrc) <= 1e-9).all(), "LRC must be non-increasing"
        # LRC[0] is the total unearned (all premiums); LRC[-1] = one period unearned
        np.testing.assert_allclose(result.lrc[0], monthly_premium * T, rtol=1e-6)
        # LRC declines by monthly_premium per period (flat premium assumption)
        np.testing.assert_allclose(result.lrc[-1], monthly_premium, rtol=1e-6)

    def test_paa_shape(self):
        """PAA output arrays should have shape (T,)."""
        T = 24
        cf = _make_gross_cashflow(T=T)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()

        assert result.lrc is not None
        assert result.lic is not None
        assert result.lrc.shape == (T,)
        assert result.lic.shape == (T,)
        assert result.insurance_liability.shape == (T,)

    def test_paa_approach_label(self):
        """PAA result should have approach == 'PAA'."""
        cf = _make_gross_cashflow()
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()
        assert result.approach == "PAA"

    def test_paa_lic_non_negative(self):
        """LIC (incurred claims liability) must be non-negative."""
        cf = _make_gross_cashflow()
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()
        assert result.lic is not None
        assert (result.lic >= 0.0).all()

    def test_paa_insurance_revenue_sums_to_total_premiums(self):
        """
        PAA insurance revenue across all periods should sum to total premiums
        (unearned premium fully earned by end of coverage).
        """
        T = 12
        monthly_premium = 100.0
        cf = _make_gross_cashflow(T=T, monthly_premium=monthly_premium)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_paa()

        total_earned = float(result.insurance_revenue.sum())
        total_premiums = monthly_premium * T
        np.testing.assert_allclose(total_earned, total_premiums, rtol=1e-6)


# ---------------------------------------------------------------------------
# VFA tests
# ---------------------------------------------------------------------------

class TestVFA:

    def test_vfa_produces_result(self):
        """VFA measurement should produce a valid IFRS17Result."""
        T = 24
        cf = _make_gross_cashflow(T=T, monthly_premium=100.0, monthly_claim=15.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        underlying = np.linspace(10_000, 8_000, T)  # declining AV
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_vfa(underlying_items_fair_value=underlying, variable_fee_rate=0.01)

        assert result.approach == "VFA"
        assert result.bel.shape == (T,)
        assert result.csm.shape == (T,)

    def test_vfa_raises_on_wrong_length(self):
        """VFA should raise if underlying_items_fair_value has wrong length."""
        cf = _make_gross_cashflow(T=24)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        wrong_length = np.ones(12, dtype=np.float64)  # wrong length
        with pytest.raises(ValueError, match="underlying_items_fair_value"):
            m.measure_vfa(wrong_length)

    def test_vfa_csm_fully_amortised(self):
        """VFA: Total CSM released should equal initial CSM plus all accretions."""
        T = 12
        cf = _make_gross_cashflow(T=T, monthly_premium=50.0, monthly_claim=5.0,
                                   monthly_expense=3.0, monthly_lapse=1.0)
        underlying = np.linspace(5_000, 4_000, T)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.04)
        result = m.measure_vfa(underlying, variable_fee_rate=0.02)

        total_available = result.initial_csm + float(result.csm_interest_accretion.sum())
        total_released = float(result.csm_release.sum())
        np.testing.assert_allclose(total_available, total_released, rtol=1e-6)


# ---------------------------------------------------------------------------
# IFRS17Result helper methods
# ---------------------------------------------------------------------------

class TestIFRS17ResultHelpers:

    def test_total_initial_liability(self):
        """total_initial_liability = initial_bel + initial_ra + initial_csm."""
        cf = _make_gross_cashflow()
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05, ra_factor=0.05)
        result = m.measure_bba()
        expected = result.initial_bel + result.initial_ra + result.initial_csm
        np.testing.assert_allclose(result.total_initial_liability(), expected, rtol=1e-10)

    def test_cumulative_csm_released_monotone(self):
        """Cumulative CSM released should be monotonically non-decreasing."""
        cf = _make_gross_cashflow(monthly_premium=100.0, monthly_claim=10.0,
                                   monthly_expense=5.0, monthly_lapse=2.0)
        m = IFRS17Measurement(cashflows=cf, discount_rate=0.05)
        result = m.measure_bba()
        cum = result.cumulative_csm_released()
        assert (np.diff(cum) >= -1e-10).all()
