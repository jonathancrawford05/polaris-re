"""
TermLife — cash flow projection engine for term life insurance.

Produces monthly gross cash flows for a block of term life policies over
the full projection horizon. Applies mortality and lapse decrements to an
in-force factor array and computes premiums, claims, and net premium reserves.

Implementation Notes for Claude Code:
--------------------------------------
VECTORIZATION CONTRACT:
    All intermediate arrays must have shape (N, T) where N = n_policies,
    T = projection_months. No Python loops over policies are permitted.
    Loops over time steps (T) are acceptable when unavoidable (reserve recursion).

IN-FORCE FACTOR RECURSION (monthly):
    lx[:, 0] = 1.0
    lx[:, t] = lx[:, t-1] * (1 - q[:, t-1]) * (1 - w[:, t-1])

RESERVE RECURSION (backward, net premium basis):
    V[:, T] = 0.0
    For t = T-1 down to 0:
        V[:, t] = (q[:, t] * face_vec + (1 - q[:, t]) * V[:, t+1]) / (1 + i)^(1/12) - P_net_vec

NET PREMIUM:
    P_net = APV(death benefit) / APV(annuity)

CASH FLOW AGGREGATION:
    premiums[:,t]   = lx[:,t] * monthly_premium_vec   → sum over N → (T,)
    claims[:,t]     = lx[:,t-1] * q[:,t] * face_vec   → sum over N → (T,)
    reserve_inc[:,t]= lx[:,t]*V[:,t] - lx[:,t-1]*V[:,t-1]

MORTALITY TABLE CALL PATTERN:
    age_at_t (N,)      = attained_age_vec + (duration_inforce_vec + t) // 12
    duration_at_t (N,) = duration_inforce_vec + t
    q_annual = mortality.get_qx_vector(age_at_t, sex, smoker, duration_at_t)
    q_monthly = 1 - (1 - q_annual) ** (1/12)

    Since sex/smoker vary by policy, iterate over unique (sex, smoker) combos
    and use np.where masking to assemble the full (N,) rate vector.

POLICY TERM HANDLING:
    active[:,t] = (duration_inforce_vec[:,None] + t) < remaining_term_months_vec[:,None]
    q[:,t] *= active[:,t]   # zero out mortality/lapse after term expiry

TODO (Phase 1, Milestone 1.3):
- Implement _build_rate_arrays() → (q, w) shape (N, T)
- Implement _compute_inforce_factors(q, w) → lx shape (N, T)
- Implement _compute_net_premiums() → P_net shape (N,)
- Implement compute_reserves() → V shape (N, T)
- Implement project() → CashFlowResult (GROSS basis)
- Tests: tests/test_products/test_term_life.py (closed-form verification required)
"""


import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct

__all__ = ["TermLife"]


class TermLife(BaseProduct):
    """
    Monthly cash flow projection engine for term life insurance.

    Handles level term products on a gross premium basis.
    Net premium reserves are computed using backward recursion.
    All calculations are vectorized over the N policies in the inforce block.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
    ) -> None:
        super().__init__(inforce, assumptions, config)
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate the inforce block is compatible with TermLife projection."""
        non_term = [
            p.policy_id for p in self.inforce.policies if p.product_type != ProductType.TERM
        ]
        if non_term:
            raise PolarisValidationError(
                f"TermLife received non-TERM policies: {non_term[:5]}"
                f"{'...' if len(non_term) > 5 else ''}"
            )
        missing_term = [p.policy_id for p in self.inforce.policies if p.policy_term is None]
        if missing_term:
            raise PolarisValidationError(
                f"Term policies must have policy_term set. Missing on: {missing_term[:5]}"
            )

    def _build_rate_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Build monthly mortality (q) and lapse (w) rate arrays, shape (N, T).

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "TermLife._build_rate_arrays() not yet implemented. "
            "See module docstring for vectorization spec."
        )

    def _compute_inforce_factors(self, q: np.ndarray, w: np.ndarray) -> np.ndarray:
        """
        Forward recursion for in-force factor lx, shape (N, T).

        lx[:,0] = 1.0
        lx[:,t] = lx[:,t-1] * (1 - q[:,t-1]) * (1 - w[:,t-1])

        TODO: Implement per module docstring.
        """
        raise NotImplementedError("TermLife._compute_inforce_factors() not yet implemented.")

    def compute_reserves(self) -> np.ndarray:
        """
        Backward recursion for net premium reserves, shape (N, T).

        V[:,T] = 0.0 (terminal condition)

        TODO: Implement per ARCHITECTURE.md §4 reserve recursion formula.
        """
        raise NotImplementedError(
            "TermLife.compute_reserves() not yet implemented. "
            "See ARCHITECTURE.md §4 for the reserve recursion formula."
        )

    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run the full term life projection → CashFlowResult (GROSS basis).

        Args:
            seriatim: If True, populate (N,T) arrays in the result.

        TODO: Implement — call _build_rate_arrays, _compute_inforce_factors,
              compute_reserves, then assemble CashFlowResult.
        """
        raise NotImplementedError(
            "TermLife.project() not yet implemented. "
            "Implement rate arrays, inforce factors, and reserves first."
        )
