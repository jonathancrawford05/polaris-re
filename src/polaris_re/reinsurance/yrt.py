"""
YRTTreaty — Yearly Renewable Term reinsurance treaty engine.

The most common individual life reinsurance structure in North America.
The reinsurer assumes mortality risk only (not lapse or investment risk).

Treaty Mechanics:
-----------------
1. NET AMOUNT AT RISK (NAR):
       NAR_t = face_amount - reserve_t
   The reinsurer's exposure is NAR. For early-duration term life,
   reserves ≈ 0 so NAR ≈ face amount.

2. CEDED YRT PREMIUM:
       ceded_prem_t = Σ_i [lx_i_t * NAR_i_t * yrt_rate_i_t / 1000] * cession_pct
   yrt_rate is per $1,000 NAR, looked up by age/sex/smoker/reinsurance duration.

3. CEDED CLAIMS:
       ceded_claim_t = gross_claim_t * cession_pct

4. NET CASH FLOWS:
       net_prem_t  = gross_prem_t - ceded_prem_t
       net_claim_t = gross_claim_t - ceded_claim_t
       net_cf_t    = net_prem_t - net_claim_t - gross_expense_t - Δreserve_t
   (Expenses and reserves stay fully with the cedant in YRT.)

KEY INVARIANT: YRT does NOT transfer reserves.
   net_reserve_t == gross_reserve_t at all t.

Implementation Notes for Claude Code:
--------------------------------------
- NAR requires reserve_balance from the gross CashFlowResult.
  Raise PolarisComputationError if reserve_balance is empty.
- flat_yrt_rate_per_1000 is the MVP simplification — a full age/sex/smoker/
  duration rate table is a Phase 2 enhancement.
- Monthly YRT rate = flat_yrt_rate_per_1000 / 12 (simplified; proper
  conversion is (1 + annual_rate/1000)^(1/12) - 1, but division by 12 is
  standard industry practice for YRT).

TODO (Phase 1, Milestone 1.4):
- Implement apply() following the mechanics above
- Use verify_additivity() to confirm net + ceded == gross
- Tests: tests/test_reinsurance/test_yrt.py
"""

from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
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
            "MVP placeholder — replaced by a full rate table in Phase 2."
        ),
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    def apply(self, gross: CashFlowResult) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply YRT treaty to gross cash flows.

        Args:
            gross: GROSS basis CashFlowResult with reserve_balance populated.

        Returns:
            (net, ceded) CashFlowResult tuple.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "YRTTreaty.apply() not yet implemented. See module docstring and ARCHITECTURE.md §5."
        )
