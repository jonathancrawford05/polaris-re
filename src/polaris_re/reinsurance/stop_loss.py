"""
StopLossTreaty — Aggregate Stop Loss reinsurance treaty engine.

An aggregate stop loss treaty provides protection against adverse aggregate
claims experience within a treaty year. The reinsurer pays the excess of
annual aggregate claims above an attachment point, up to an exhaustion point.

Treaty Mechanics (per treaty year):
-------------------------------------
    annual_claims_y = sum of death_claims for months in year y
    reinsurer_payment_y = min(max(annual_claims_y - attachment_point, 0),
                              exhaustion_point - attachment_point)

Reinsurer premium is spread evenly across all 12 months of each year.
Reinsurer payments within each year are allocated back to months pro-rata
by the month's share of annual claims (to maintain (T,) output arrays).

NCF Additivity:
    The additivity invariant holds for premiums and net cash flows.
    (Claims: ceded_claims are the reinsurer payments; net_claims are residual.)
"""

import warnings
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.reinsurance.base_treaty import BaseTreaty

if TYPE_CHECKING:
    from polaris_re.core.inforce import InforceBlock

__all__ = ["StopLossTreaty"]


class StopLossTreaty(PolarisBaseModel, BaseTreaty):
    """
    Aggregate stop loss reinsurance treaty.

    Covers aggregate claims within each treaty year above the attachment point
    up to the exhaustion point. Cedant pays a flat annual stop loss premium.
    """

    attachment_point: float = Field(
        gt=0.0,
        description="Annual aggregate claims above which reinsurer pays ($).",
    )
    exhaustion_point: float = Field(
        gt=0.0,
        description="Annual aggregate claims at which reinsurer's liability is exhausted ($). "
        "Must be > attachment_point.",
    )
    stop_loss_premium: float = Field(
        ge=0.0,
        description="Annual stop loss premium paid by cedant ($). "
        "Distributed evenly across 12 months per year.",
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    @model_validator(mode="after")
    def validate_exhaustion_gt_attachment(self) -> "StopLossTreaty":
        if self.exhaustion_point <= self.attachment_point:
            raise ValueError(
                f"exhaustion_point ({self.exhaustion_point}) must be > "
                f"attachment_point ({self.attachment_point})"
            )
        return self

    def apply(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock | None" = None,
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply aggregate stop loss treaty to gross cash flows.

        Note: Stop loss does not use cession_pct — the inforce parameter
        is accepted for interface consistency but is not used.

        Args:
            gross:   GROSS basis CashFlowResult.
            inforce: Not used by stop loss. Accepted for interface consistency.

        Returns:
            (net, ceded) CashFlowResult tuple.
        """
        t = len(gross.death_claims)
        if t == 0:
            return gross, _zero_ceded(gross)

        monthly_claims = gross.death_claims  # (T,)

        # Compute reinsurer payments and premium by treaty year
        ceded_claims = np.zeros(t, dtype=np.float64)
        ceded_premiums = np.zeros(t, dtype=np.float64)

        n_full_years = t // 12
        remainder = t % 12

        # Process full years
        for y in range(n_full_years):
            start = y * 12
            end = start + 12
            self._process_year(monthly_claims, ceded_claims, ceded_premiums, start, end)

        # Process partial final year (if any)
        if remainder > 0:
            start = n_full_years * 12
            end = t
            # Pro-rate annual premium and attachment/exhaustion for partial year
            year_fraction = remainder / 12.0
            self._process_partial_year(
                monthly_claims, ceded_claims, ceded_premiums, start, end, year_fraction
            )

        # Net claims: gross minus reinsurer payments
        net_claims = monthly_claims - ceded_claims
        if np.any(net_claims < -1e-8):
            warnings.warn(
                "Stop loss produced negative net claims in some months. "
                "This can occur when attachment_point is very low.",
                stacklevel=2,
            )
        net_claims = np.maximum(net_claims, 0.0)

        # Net premiums = gross minus stop loss premium
        net_premiums = gross.gross_premiums - ceded_premiums

        # Non-claims items stay with cedant
        net_lapses = gross.lapse_surrenders.copy()
        ceded_lapses = np.zeros_like(gross.lapse_surrenders)

        net_expenses = gross.expenses.copy()
        ceded_expenses = np.zeros_like(gross.expenses)

        net_reserve_balance = gross.reserve_balance.copy()
        ceded_reserve_balance = np.zeros_like(gross.reserve_balance)
        net_reserve_inc = gross.reserve_increase.copy()
        ceded_reserve_inc = np.zeros_like(gross.reserve_increase)

        net_ncf = net_premiums - net_claims - net_lapses - net_expenses - net_reserve_inc
        ceded_ncf = ceded_premiums - ceded_claims

        net = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="NET",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=net_premiums,
            death_claims=net_claims,
            lapse_surrenders=net_lapses,
            expenses=net_expenses,
            reserve_balance=net_reserve_balance,
            reserve_increase=net_reserve_inc,
            net_cash_flow=net_ncf,
        )

        ceded = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="CEDED",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=ceded_premiums,
            death_claims=ceded_claims,
            lapse_surrenders=ceded_lapses,
            expenses=ceded_expenses,
            reserve_balance=ceded_reserve_balance,
            reserve_increase=ceded_reserve_inc,
            net_cash_flow=ceded_ncf,
        )

        return net, ceded

    def _process_year(
        self,
        monthly_claims: np.ndarray,
        ceded_claims: np.ndarray,
        ceded_premiums: np.ndarray,
        start: int,
        end: int,
    ) -> None:
        """Process one full treaty year (12 months)."""
        annual_claims = monthly_claims[start:end].sum()
        reinsurer_payment = min(
            max(annual_claims - self.attachment_point, 0.0),
            self.exhaustion_point - self.attachment_point,
        )

        # Allocate reinsurer payment back to months pro-rata by claims
        if reinsurer_payment > 0.0:
            month_claims_slice = monthly_claims[start:end]
            if annual_claims > 0.0:
                allocation = month_claims_slice / annual_claims * reinsurer_payment
            else:
                allocation = np.full(end - start, reinsurer_payment / (end - start))
            ceded_claims[start:end] = allocation

        # Stop loss premium: distributed evenly across 12 months
        ceded_premiums[start:end] = self.stop_loss_premium / 12.0

    def _process_partial_year(
        self,
        monthly_claims: np.ndarray,
        ceded_claims: np.ndarray,
        ceded_premiums: np.ndarray,
        start: int,
        end: int,
        year_fraction: float,
    ) -> None:
        """Process a partial treaty year at end of projection."""
        # Pro-rate attachment and exhaustion by year fraction
        pro_attachment = self.attachment_point * year_fraction
        pro_exhaustion = self.exhaustion_point * year_fraction

        annual_claims = monthly_claims[start:end].sum()
        reinsurer_payment = min(
            max(annual_claims - pro_attachment, 0.0),
            pro_exhaustion - pro_attachment,
        )

        if reinsurer_payment > 0.0:
            month_claims_slice = monthly_claims[start:end]
            if annual_claims > 0.0:
                allocation = month_claims_slice / annual_claims * reinsurer_payment
            else:
                n_months = end - start
                allocation = np.full(n_months, reinsurer_payment / n_months)
            ceded_claims[start:end] = allocation

        # Pro-rate premium
        n_months = end - start
        ceded_premiums[start:end] = self.stop_loss_premium * year_fraction / n_months


def _zero_ceded(gross: CashFlowResult) -> CashFlowResult:
    """Return a zero CEDED result (no claims above attachment)."""
    zeros = np.array([], dtype=np.float64)
    return CashFlowResult(
        run_id=gross.run_id,
        valuation_date=gross.valuation_date,
        basis="CEDED",
        assumption_set_version=gross.assumption_set_version,
        product_type=gross.product_type,
        block_id=gross.block_id,
        projection_months=0,
        time_index=gross.time_index,
        gross_premiums=zeros,
        death_claims=zeros,
        lapse_surrenders=zeros,
        expenses=zeros,
        reserve_balance=zeros,
        reserve_increase=zeros,
        net_cash_flow=zeros,
    )
