"""
ModcoTreaty — Modified Coinsurance reinsurance treaty engine.

Modified coinsurance (Modco) is economically equivalent to coinsurance but the
cedant retains the assets backing the ceded reserves. To compensate the reinsurer
for not holding the reserve assets, the cedant pays modco interest each month:

    modco_interest_t = ceded_reserve_balance_t * modco_interest_rate / 12

Key distinctions vs Coinsurance:
---------------------------------
- Premium split: identical (ceded_premium = gross * c)
- Claims split: identical (ceded_claim = gross * c)
- Reserve: NOT transferred — cedant retains full reserve liability
- Modco interest: cedant pays reinsurer interest on the notional ceded reserve

NCF additivity proof:
    net_ncf = net_prem - net_claims - lapses - expenses - gross_reserve_inc - modco_interest
    ceded_ncf = ceded_prem - ceded_claims + modco_interest
    net_ncf + ceded_ncf = gross_prem - gross_claims - lapses - expenses - gross_reserve_inc
                        = gross_ncf  ✓

The modco_interest is stored in CashFlowResult.modco_interest for auditability.
"""

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.reinsurance.base_treaty import BaseTreaty

if TYPE_CHECKING:
    from polaris_re.core.inforce import InforceBlock

__all__ = ["ModcoTreaty"]


class ModcoTreaty(PolarisBaseModel, BaseTreaty):
    """
    Modified Coinsurance reinsurance treaty.

    Proportional split of premiums and claims (like coinsurance), but the cedant
    retains the assets backing the ceded reserves and pays modco interest to the
    reinsurer in lieu of reserve transfer.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of cash flows ceded (e.g. 0.75 = 75%).",
    )
    modco_interest_rate: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Annual interest rate paid by cedant to reinsurer on ceded reserve balance. "
            "Typically equals the cedant's portfolio yield (e.g. 0.045 for 4.5%)."
        ),
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    @model_validator(mode="after")
    def validate_modco_rate_positive(self) -> "ModcoTreaty":
        if self.modco_interest_rate < 0.0:
            raise ValueError(f"modco_interest_rate must be >= 0.0, got {self.modco_interest_rate}")
        return self

    def apply(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock | None" = None,
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply Modco treaty to gross cash flows.

        Args:
            gross:   GROSS basis CashFlowResult. reserve_balance must be populated
                     for modco interest calculation to be meaningful.
            inforce: Optional InforceBlock for policy-level cession overrides.

        Returns:
            (net, ceded) CashFlowResult tuple.
            net.modco_interest contains the monthly modco interest payments.
        """
        if len(gross.reserve_balance) == 0:
            raise PolarisComputationError(
                "ModcoTreaty requires reserve_balance in gross CashFlowResult."
            )

        c = self._resolve_cession(self.cession_pct, inforce)

        # Premiums: split proportionally (identical to coinsurance)
        net_premiums = gross.gross_premiums * (1.0 - c)
        ceded_premiums = gross.gross_premiums * c

        # Claims: split proportionally
        net_claims = gross.death_claims * (1.0 - c)
        ceded_claims = gross.death_claims * c

        # Lapses: stay with cedant (reserve not transferred, so lapse value stays)
        net_lapses = gross.lapse_surrenders.copy()
        ceded_lapses = np.zeros_like(gross.lapse_surrenders)

        # Expenses: stay with cedant
        net_expenses = gross.expenses.copy()
        ceded_expenses = np.zeros_like(gross.expenses)

        # Reserves: NOT transferred — cedant retains full reserve
        net_reserve_balance = gross.reserve_balance.copy()
        ceded_reserve_balance = gross.reserve_balance * c  # notional only
        net_reserve_inc = gross.reserve_increase.copy()
        ceded_reserve_inc = np.zeros_like(gross.reserve_increase)

        # Modco interest: cedant pays reinsurer on notional ceded reserve
        # modco_interest_t = ceded_reserve_balance_t * annual_rate / 12
        modco_interest = ceded_reserve_balance * self.modco_interest_rate / 12.0

        # Net cash flows — net pays modco interest; ceded receives it
        net_ncf = (
            net_premiums
            - net_claims
            - net_lapses
            - net_expenses
            - net_reserve_inc  # full gross reserve increase stays with cedant
            - modco_interest
        )
        ceded_ncf = ceded_premiums - ceded_claims + modco_interest

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
            modco_interest=modco_interest,
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
            modco_interest=modco_interest,
        )

        return net, ceded
