"""
CoinsuranceTreaty - proportional reinsurance transferring all cash flows and reserves.

The reinsurer takes a proportional share of ALL cash flows - premiums,
claims, expenses, AND reserves. Both mortality and lapse risk are transferred.

Treaty Mechanics (cession percentage = c):
-------------------------------------------
    ceded_premium_t    = gross_premium_t    * c
    ceded_claim_t      = gross_claim_t      * c
    ceded_expense_t    = gross_expense_t    * c
    ceded_reserve_t    = gross_reserve_t    * c
    ceded_res_inc_t    = gross_res_inc_t    * c

    net_*_t            = gross_*_t          * (1 - c)

KEY DISTINCTION FROM YRT:
    Coinsurance transfers the reserve liability. net_reserve != gross_reserve.
"""

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["CoinsuranceTreaty"]


class CoinsuranceTreaty(PolarisBaseModel, BaseTreaty):
    """
    Coinsurance reinsurance treaty.

    Proportional share of all cash flows including reserves.
    Transfers mortality, lapse, and investment risk proportionally.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of all cash flows ceded.",
    )
    include_expense_allowance: bool = Field(
        default=True,
        description=(
            "If True, reinsurer pays a proportional expense allowance to cedant. "
            "Standard in most coinsurance treaties."
        ),
    )
    treaty_name: str | None = Field(
        default=None, description="Optional treaty identifier."
    )

    def apply(
        self, gross: CashFlowResult
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply coinsurance treaty to gross cash flows.

        All cash flow lines are split proportionally by cession_pct,
        including reserves (unlike YRT where reserves stay with cedant).

        Args:
            gross: GROSS basis CashFlowResult.

        Returns:
            (net, ceded) CashFlowResult tuple.
        """
        c = self.cession_pct
        r = 1.0 - c  # retention proportion

        # All lines split proportionally
        net_premiums = gross.gross_premiums * r
        ceded_premiums = gross.gross_premiums * c

        net_claims = gross.death_claims * r
        ceded_claims = gross.death_claims * c

        net_lapses = gross.lapse_surrenders * r
        ceded_lapses = gross.lapse_surrenders * c

        if self.include_expense_allowance:
            net_expenses = gross.expenses * r
            ceded_expenses = gross.expenses * c
        else:
            # Expenses stay with cedant if no allowance
            net_expenses = gross.expenses.copy()
            ceded_expenses = np.zeros_like(gross.expenses)

        # Reserves: transferred proportionally (key difference from YRT)
        net_reserve_balance = gross.reserve_balance * r
        ceded_reserve_balance = gross.reserve_balance * c
        net_reserve_inc = gross.reserve_increase * r
        ceded_reserve_inc = gross.reserve_increase * c

        # Net cash flows
        net_ncf = net_premiums - net_claims - net_lapses - net_expenses - net_reserve_inc
        ceded_ncf = (
            ceded_premiums - ceded_claims - ceded_lapses - ceded_expenses - ceded_reserve_inc
        )

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
