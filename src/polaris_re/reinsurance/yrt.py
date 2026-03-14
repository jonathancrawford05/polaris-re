"""
YRTTreaty — Yearly Renewable Term reinsurance treaty engine.

YRT is the most common individual life reinsurance structure in North America.
The reinsurer assumes mortality risk only (not lapse or investment risk).

Treaty Mechanics:
-----------------
1. NET AMOUNT AT RISK (NAR):
       NAR_t = face_amount - reserve_t
   The reinsurer's exposure is NAR, not face amount. As reserves build up,
   the reinsurer's risk (and premium) decreases. For term life in early
   durations, reserves are near zero so NAR ≈ face amount.

2. CEDED YRT PREMIUM:
       ceded_prem_t = Σ_i [lx_i_t * NAR_i_t * yrt_rate_i_t / 1000] * cession_pct
   Where yrt_rate is per $1,000 NAR and is looked up from a YRT rate table
   by age, sex, smoker, and reinsurance duration. Monthly YRT rates are
   annual rates / 12 (simplified) or converted properly via (1+r)^(1/12)-1.

3. CEDED CLAIMS:
       ceded_claim_t = gross_claim_t * cession_pct
   The reinsurer pays their proportional share of death claims.

4. NET CASH FLOWS:
       net_prem_t   = gross_prem_t - ceded_prem_t
       net_claim_t  = gross_claim_t - ceded_claim_t
       net_cf_t     = net_prem_t - net_claim_t - gross_expense_t - Δreserve_t
   (Expenses and reserves stay with the cedant in YRT.)

KEY INVARIANT:
   YRT does NOT transfer reserves. The cedant holds all reserves.
   net_reserve == gross_reserve (reserves are not split).

Implementation Notes for Claude Code:
--------------------------------------
- The YRT rate table is structured like a mortality table: rates by age, sex,
  smoker, and reinsurance duration (year since cession began).
- YRT rates are negotiated commercially and differ from mortality table rates.
  The rate table is stored as a `yrt_rate_table` dict or array input to the treaty.
- NAR requires reserves from the gross CashFlowResult (`reserve_balance` array).
  If reserves are not populated in the gross result, raise PolarisComputationError.
- Retention limits: if face_amount > retention_limit, cession_pct applies only
  to the excess above the retention. Implement as: ceded_face = min(face, face - retention)
  This is optional for Phase 1 but the treaty model should accept retention_limit.

TODO (Phase 1, Milestone 1.4):
- Implement apply() following the mechanics above
- Ensure net + ceded == gross for premiums and claims (use verify_additivity())
- Add tests in tests/test_reinsurance/test_yrt.py with closed-form verification
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["YRTTreaty"]


class YRTTreaty(PolarisBaseModel, BaseTreaty):
    """
    Yearly Renewable Term reinsurance treaty.

    Transfers mortality risk to the reinsurer in exchange for YRT premiums
    based on Net Amount at Risk. Reserves and lapse risk remain with the cedant.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of each policy ceded under this treaty (e.g. 0.50 = 50%).",
    )
    retention_limit: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum face amount retained per policy in dollars. "
            "Excess above this limit is ceded. If None, cession_pct applies to full face amount."
        ),
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    # TODO: yrt_rate_table representation — Phase 1 can use a simplified flat rate
    # or accept a MortalityTable-like object for age/sex/smoker/duration lookup.
    # For MVP, accept a flat annual YRT rate per $1000 NAR:
    flat_yrt_rate_per_1000: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Simplified flat annual YRT rate per $1,000 NAR. "
            "Used for MVP testing before a full YRT rate table is implemented."
        ),
    )

    def apply(self, gross: CashFlowResult) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply YRT treaty to gross cash flows.

        Args:
            gross: GROSS basis CashFlowResult from a TermLife (or other) product engine.
                   Must have reserve_balance populated (required for NAR calculation).

        Returns:
            (net, ceded) CashFlowResult tuple.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "YRTTreaty.apply() not yet implemented. "
            "See module docstring for mechanics and ARCHITECTURE.md §5."
        )
