"""
CoinsuranceTreaty — proportional reinsurance transferring all cash flows and reserves.

Coinsurance differs from YRT in that the reinsurer takes a proportional share
of ALL cash flows — premiums, claims, expenses, AND reserves. This means
both mortality and lapse risk (and the investment income on reserves) are shared.

Treaty Mechanics:
-----------------
For a cession percentage c:

    ceded_premium_t   = gross_premium_t   * c
    ceded_claim_t     = gross_claim_t     * c
    ceded_expense_t   = gross_expense_t   * c
    ceded_reserve_t   = gross_reserve_t   * c
    ceded_res_inc_t   = gross_res_inc_t   * c

    net_premium_t     = gross_premium_t   * (1 - c)
    net_claim_t       = gross_claim_t     * (1 - c)
    net_expense_t     = gross_expense_t   * (1 - c)
    net_reserve_t     = gross_reserve_t   * (1 - c)

KEY DISTINCTION FROM YRT:
    In coinsurance, the reinsurer also takes on the reserve liability.
    At treaty inception, the cedant transfers the ceded reserve to the reinsurer
    (coinsurance allowance). This appears as a positive cash flow to the cedant
    at time 0 and is sometimes called the "ceding commission" or "initial allowance."

Implementation Notes for Claude Code:
--------------------------------------
- Since all cash flow lines scale by the same factor c, the implementation is
  simpler than YRT — multiply all arrays by c for ceded, by (1-c) for net.
- The initial reserve transfer (coinsurance allowance) should be modelled as
  a one-time cash flow at t=0. This is critical for accurate IRR calculation.
- Cession percentage is applied uniformly across the entire block. Policy-level
  cession percentages (from Policy.reinsurance_cession_pct) are handled by
  applying the treaty per-policy where needed.
- Unlike YRT, coinsurance does NOT require NAR calculation. Simpler to implement.

TODO (Phase 1, Milestone 1.4):
- Implement apply() following the mechanics above
- Apply initial reserve transfer at t=0
- Verify additivity: net + ceded == gross for all lines
- Add tests in tests/test_reinsurance/test_coinsurance.py
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["CoinsuranceTreaty"]


class CoinsuranceTreaty(PolarisBaseModel, BaseTreaty):
    """
    Coinsurance reinsurance treaty.

    The reinsurer takes a proportional share of all cash flows including reserves.
    Transfers mortality, lapse, and investment risk proportionally.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of all cash flows ceded under this treaty.",
    )
    include_expense_allowance: bool = Field(
        default=True,
        description=(
            "If True, ceded expenses include a proportional expense allowance "
            "paid by the reinsurer to the cedant. Standard in most coinsurance treaties."
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
