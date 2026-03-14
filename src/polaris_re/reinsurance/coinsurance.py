"""
CoinsuranceTreaty — proportional reinsurance transferring all cash flows and reserves.

The reinsurer takes a proportional share of ALL cash flows — premiums,
claims, expenses, AND reserves. Both mortality and lapse risk are transferred.

Treaty Mechanics (cession percentage = c):
-------------------------------------------
    ceded_premium_t    = gross_premium_t    * c
    ceded_claim_t      = gross_claim_t      * c
    ceded_expense_t    = gross_expense_t    * c
    ceded_reserve_t    = gross_reserve_t    * c
    ceded_res_inc_t    = gross_res_inc_t    * c

    net_*_t            = gross_*_t          * (1 - c)

Initial reserve transfer at t=0 (coinsurance allowance):
    At treaty inception the cedant transfers ceded_reserve_0 to the reinsurer.
    This is a POSITIVE cash flow to the cedant at t=0 (they receive the allowance).
    It must be included for accurate IRR calculation.

KEY DISTINCTION FROM YRT:
    Coinsurance transfers the reserve liability. net_reserve != gross_reserve.

Implementation Notes for Claude Code:
--------------------------------------
- All cash flow lines scale uniformly by c — simpler than YRT.
- Initial reserve transfer = gross_reserve_balance[0] * c, added as positive
  cash flow at t=0 in the net result.
- No NAR calculation required.

TODO (Phase 1, Milestone 1.4):
- Implement apply() following the mechanics above
- Apply initial reserve transfer at t=0
- Verify additivity via verify_additivity()
- Tests: tests/test_reinsurance/test_coinsurance.py
"""

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
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    def apply(self, gross: CashFlowResult) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply coinsurance treaty to gross cash flows.

        Returns:
            (net, ceded) CashFlowResult tuple.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "CoinsuranceTreaty.apply() not yet implemented. "
            "See module docstring for mechanics."
        )
