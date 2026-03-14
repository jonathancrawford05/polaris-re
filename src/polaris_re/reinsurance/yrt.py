"""
YRTTreaty - Yearly Renewable Term reinsurance treaty engine.

The most common individual life reinsurance structure in North America.
The reinsurer assumes mortality risk only (not lapse or investment risk).

Treaty Mechanics:
-----------------
1. NAR_t = face_amount - reserve_t (Net Amount at Risk)
2. ceded_prem_t = NAR_t * yrt_rate / 1000 * cession_pct (per $1000 NAR)
3. ceded_claim_t = gross_claim_t * cession_pct
4. Reserves stay fully with the cedant (not transferred).

For aggregate cash flows (Phase 1 MVP), total in-force face amount at each
time step is approximated using the premium runoff ratio as an in-force proxy:
    inforce_ratio_t = gross_premiums[t] / gross_premiums[0]
    total_face_t = total_face_amount * inforce_ratio_t
    NAR_t = total_face_t - reserve_balance_t
"""

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["YRTTreaty"]


class YRTTreaty(PolarisBaseModel, BaseTreaty):
    """
    Yearly Renewable Term reinsurance treaty.

    Transfers mortality risk to the reinsurer via YRT premiums based on
    Net Amount at Risk. Reserves and lapse risk remain with the cedant.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of each policy ceded (e.g. 0.50 = 50%).",
    )
    total_face_amount: float = Field(
        gt=0,
        description=(
            "Total initial in-force face amount for the block ($). "
            "Used to compute aggregate NAR = face * inforce_ratio - reserves."
        ),
    )
    retention_limit: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum face amount retained per policy ($). "
            "Excess above this limit is automatically ceded. "
            "If None, cession_pct applies to full face amount."
        ),
    )
    flat_yrt_rate_per_1000: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Simplified flat annual YRT rate per $1,000 NAR. "
            "MVP placeholder - replaced by a full rate table in Phase 2."
        ),
    )
    treaty_name: str | None = Field(
        default=None, description="Optional treaty identifier."
    )

    def apply(
        self, gross: CashFlowResult
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply YRT treaty to gross cash flows.

        Args:
            gross: GROSS basis CashFlowResult with reserve_balance populated.

        Returns:
            (net, ceded) CashFlowResult tuple.
        """
        if len(gross.reserve_balance) == 0:
            raise PolarisComputationError(
                "YRT treaty requires reserve_balance in gross CashFlowResult."
            )

        c = self.cession_pct

        # Ceded claims: proportional to gross
        ceded_claims = gross.death_claims * c
        net_claims = gross.death_claims * (1.0 - c)

        # YRT premiums: based on NAR
        if self.flat_yrt_rate_per_1000 is not None:
            # Approximate in-force face at each time step using premium runoff
            initial_premium = gross.gross_premiums[0]
            if initial_premium > 0:
                inforce_ratio = gross.gross_premiums / initial_premium
            else:
                inforce_ratio = np.ones_like(gross.gross_premiums)

            # Total in-force face at each time step
            total_face_t = self.total_face_amount * inforce_ratio

            # NAR = face - reserves (floored at 0)
            nar = np.maximum(total_face_t - gross.reserve_balance, 0.0)

            # Monthly YRT rate = annual rate / 12
            monthly_rate_per_dollar = self.flat_yrt_rate_per_1000 / 12.0 / 1000.0

            # Ceded YRT premiums = NAR * monthly_rate * cession_pct
            ceded_yrt_premiums = nar * monthly_rate_per_dollar * c
        else:
            # Without a YRT rate, ceded premiums are zero
            ceded_yrt_premiums = np.zeros_like(gross.gross_premiums)
            nar = None

        # Net premiums: gross premiums minus YRT ceded premiums
        # In YRT, the cedant keeps gross premiums but pays YRT premiums to reinsurer
        ceded_premiums = ceded_yrt_premiums
        net_premiums = gross.gross_premiums - ceded_premiums

        # Reserves: NOT transferred in YRT
        net_reserve_balance = gross.reserve_balance.copy()
        ceded_reserve_balance = np.zeros_like(gross.reserve_balance)
        net_reserve_inc = gross.reserve_increase.copy()
        ceded_reserve_inc = np.zeros_like(gross.reserve_increase)

        # Expenses: stay with cedant
        net_expenses = gross.expenses.copy()
        ceded_expenses = np.zeros_like(gross.expenses)

        # Lapse surrenders: stay with cedant (no cash values for term)
        net_lapses = gross.lapse_surrenders.copy()
        ceded_lapses = np.zeros_like(gross.lapse_surrenders)

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
            nar=nar,
            yrt_premiums=ceded_yrt_premiums,
        )

        return net, ceded
