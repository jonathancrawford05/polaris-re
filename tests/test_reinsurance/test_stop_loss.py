"""
Tests for StopLossTreaty — Aggregate Stop Loss reinsurance treaty.

Verifies attachment/exhaustion logic, annual aggregation, NCF additivity,
and edge cases.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.core.cashflow import CashFlowResult
from polaris_re.reinsurance.stop_loss import StopLossTreaty


def _make_gross(
    n_months: int = 120,
    monthly_claims: float | np.ndarray = 1_000.0,
    monthly_premiums: float = 5_000.0,
) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult."""
    if isinstance(monthly_claims, (int, float)):
        claims = np.full(n_months, float(monthly_claims), dtype=np.float64)
    else:
        claims = monthly_claims.astype(np.float64)
    premiums = np.full(n_months, monthly_premiums, dtype=np.float64)
    zeros = np.zeros(n_months, dtype=np.float64)
    net_cf = premiums - claims
    time_idx = np.array(
        [f"2025-{(m % 12) + 1:02d}" for m in range(n_months)],
        dtype="datetime64[M]",
    )
    return CashFlowResult(
        run_id="TEST",
        valuation_date=date(2025, 1, 1),
        basis="GROSS",
        assumption_set_version="test-v1",
        product_type="TERM",
        projection_months=n_months,
        time_index=time_idx,
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=zeros,
        expenses=zeros,
        reserve_balance=zeros,
        reserve_increase=zeros,
        net_cash_flow=net_cf,
    )


class TestStopLossValidation:
    """Input validation."""

    def test_exhaustion_must_exceed_attachment(self) -> None:
        """exhaustion_point <= attachment_point raises ValueError."""
        with pytest.raises(ValueError, match="exhaustion_point"):
            StopLossTreaty(
                attachment_point=100_000.0,
                exhaustion_point=100_000.0,
                stop_loss_premium=5_000.0,
            )

    def test_exhaustion_below_attachment_raises(self) -> None:
        with pytest.raises(ValueError, match="exhaustion_point"):
            StopLossTreaty(
                attachment_point=200_000.0,
                exhaustion_point=100_000.0,
                stop_loss_premium=5_000.0,
            )


class TestStopLossAttachmentExhaustion:
    """Tests for the stop loss recovery trigger logic."""

    def test_below_attachment_no_recovery(self) -> None:
        """Annual claims below attachment → reinsurer pays nothing."""
        # Monthly claims = 500, annual = 6000; attachment = 100_000
        gross = _make_gross(n_months=24, monthly_claims=500.0)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=1_000.0,
        )
        _net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(ceded.death_claims, 0.0, atol=1e-10)

    def test_above_attachment_below_exhaustion(self) -> None:
        """Annual claims above attachment → partial recovery."""
        # Monthly = 10_000, annual = 120_000; attachment = 100_000, exhaustion = 200_000
        # Reinsurer pays: min(120_000 - 100_000, 200_000 - 100_000) = 20_000 per year
        gross = _make_gross(n_months=24, monthly_claims=10_000.0)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=0.0,
        )
        _net, ceded = treaty.apply(gross)
        # Total ceded claims over 2 years = 2 * 20_000 = 40_000
        np.testing.assert_allclose(ceded.death_claims.sum(), 40_000.0, rtol=1e-8)

    def test_above_exhaustion_capped(self) -> None:
        """Annual claims above exhaustion → reinsurer capped at limit."""
        # Monthly = 20_000, annual = 240_000; attachment = 100_000, exhaustion = 200_000
        # Reinsurer pays: min(240_000 - 100_000, 200_000 - 100_000) = 100_000 per year
        gross = _make_gross(n_months=12, monthly_claims=20_000.0)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=0.0,
        )
        _net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(ceded.death_claims.sum(), 100_000.0, rtol=1e-8)

    def test_closed_form_annual_recovery(self) -> None:
        """
        CLOSED-FORM verification:
        Monthly claims = 15_000 → annual = 180_000
        attachment = 100_000, exhaustion = 300_000
        reinsurer_payment = min(180_000 - 100_000, 300_000 - 100_000) = 80_000
        Over 2 years = 160_000 total ceded claims.
        """
        gross = _make_gross(n_months=24, monthly_claims=15_000.0)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=300_000.0,
            stop_loss_premium=0.0,
        )
        _net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(ceded.death_claims.sum(), 160_000.0, rtol=1e-8)

    def test_uniform_claims_equal_monthly_allocation(self) -> None:
        """With uniform monthly claims, allocation is also uniform."""
        # Monthly = 15_000, annual = 180_000; attachment = 100_000
        # Reinsurer pays = 80_000 per year, spread evenly = 80_000/12 per month
        gross = _make_gross(n_months=24, monthly_claims=15_000.0)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=300_000.0,
            stop_loss_premium=0.0,
        )
        _net, ceded = treaty.apply(gross)
        expected_monthly = 80_000.0 / 12.0
        np.testing.assert_allclose(ceded.death_claims[:12], expected_monthly, rtol=1e-8)


class TestStopLossAdditivity:
    """NCF and cash flow additivity invariants."""

    def test_net_cash_flow_additivity(self) -> None:
        """net_ncf + ceded_ncf == gross_ncf."""
        gross = _make_gross(n_months=120, monthly_claims=10_000.0)
        treaty = StopLossTreaty(
            attachment_point=80_000.0,
            exhaustion_point=150_000.0,
            stop_loss_premium=5_000.0,
        )
        net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross.net_cash_flow,
            rtol=1e-8,
        )

    def test_premium_additivity(self) -> None:
        """net_premiums + ceded_premiums == gross_premiums."""
        gross = _make_gross(n_months=24, monthly_claims=5_000.0)
        treaty = StopLossTreaty(
            attachment_point=40_000.0,
            exhaustion_point=80_000.0,
            stop_loss_premium=3_000.0,
        )
        net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums, gross.gross_premiums, rtol=1e-10
        )


class TestStopLossPremium:
    """Stop loss premium distribution."""

    def test_premium_evenly_distributed(self) -> None:
        """Annual premium is evenly distributed across 12 months."""
        gross = _make_gross(n_months=24, monthly_claims=500.0)
        annual_sl_prem = 12_000.0
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=annual_sl_prem,
        )
        _net, ceded = treaty.apply(gross)
        expected_monthly = annual_sl_prem / 12.0
        np.testing.assert_allclose(ceded.gross_premiums[:12], expected_monthly, rtol=1e-10)

    def test_total_premium_correct(self) -> None:
        """Total ceded premiums = annual_sl_prem * projection_years."""
        gross = _make_gross(n_months=60)  # 5 years
        annual_sl_prem = 6_000.0
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=annual_sl_prem,
        )
        _net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(ceded.gross_premiums.sum(), annual_sl_prem * 5, rtol=1e-10)


class TestStopLossEdgeCases:
    """Edge cases."""

    def test_net_claims_non_negative(self) -> None:
        """Net claims should be floored at 0."""
        # Even if stop loss overpays, net claims should not go negative
        gross = _make_gross(n_months=12, monthly_claims=5_000.0)
        treaty = StopLossTreaty(
            attachment_point=1.0,  # very low attachment
            exhaustion_point=100_000_000.0,
            stop_loss_premium=0.0,
        )
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            net, _ceded = treaty.apply(gross)
        assert np.all(net.death_claims >= 0.0)

    def test_multiple_projection_years(self) -> None:
        """Treaty applies year-by-year for multi-year projections."""
        # Year 1: claims = 5_000/mo → annual = 60_000 (below 100_000 attachment)
        # Year 2: claims = 10_000/mo → annual = 120_000 (above 100_000, pays 20_000)
        claims = np.concatenate(
            [
                np.full(12, 5_000.0),
                np.full(12, 10_000.0),
            ]
        )
        gross = _make_gross(n_months=24, monthly_claims=claims)
        treaty = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=200_000.0,
            stop_loss_premium=0.0,
        )
        _net, ceded = treaty.apply(gross)
        # Year 1: no recovery
        np.testing.assert_allclose(ceded.death_claims[:12].sum(), 0.0, atol=1e-8)
        # Year 2: recovery = 120_000 - 100_000 = 20_000
        np.testing.assert_allclose(ceded.death_claims[12:].sum(), 20_000.0, rtol=1e-8)
