"""
BaseTreaty — abstract base class for all reinsurance treaty engines.

A treaty transforms a gross CashFlowResult into (net, ceded) pair.
The invariant that must hold for all implementations:

    net + ceded == gross   (for every cash flow line)

This is verified via verify_additivity() in the test suite.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

if TYPE_CHECKING:
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
    from polaris_re.reinsurance.experience_refund import ExperienceRefund

__all__ = ["BaseTreaty"]


class BaseTreaty(ABC):
    """
    Abstract base for all reinsurance treaty engines.

    The sole public interface is `apply()`, which receives the gross
    CashFlowResult and returns a (net, ceded) tuple.

    Cession percentage resolution (ADR-036):
        Treaty-level ``cession_pct`` is the default. When an ``InforceBlock``
        is passed to ``apply()``, policy-level ``reinsurance_cession_pct``
        overrides the treaty default for individual policies. For aggregate
        cash flows, a face-weighted average of the effective per-policy
        cession rates is used.
    """

    @abstractmethod
    def apply(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock | None" = None,
        *,
        use_policy_cession: bool = True,
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply the treaty to gross cash flows.

        ``inforce`` drives two independent concerns; keep them decoupled:

        * **Cession resolution** — honoring per-policy
          ``reinsurance_cession_pct`` overrides is gated by
          ``use_policy_cession``, NOT by the mere presence of ``inforce``.
        * **Block-aware first-year allowance mapping** — a sliding-scale
          ``ExpenseAllowance`` maps projection month to actual policy duration
          whenever ``inforce`` is supplied (see
          :meth:`_expense_allowance_transfer`), regardless of
          ``use_policy_cession``.

        This lets a renewal (mid-duration) block be priced on a flat treaty
        cession while its allowance is still charged on genuine policy-year-one
        business only.

        Args:
            gross:   CashFlowResult on GROSS basis from a product engine.
            inforce: Optional InforceBlock. Supplied for block-aware allowance
                     mapping and — when ``use_policy_cession`` is True — for
                     per-policy cession overrides (face-weighted average).
            use_policy_cession: When True (default), per-policy
                     ``reinsurance_cession_pct`` overrides on ``inforce`` are
                     honored via a face-weighted average. When False, the flat
                     treaty ``cession_pct`` is used even though ``inforce`` is
                     supplied (the allowance mapping still uses it).

        Returns:
            (net, ceded) tuple. net + ceded must equal gross for all lines.
        """

    def _resolve_cession(
        self,
        treaty_cession_pct: float,
        inforce: "InforceBlock | None",
        use_policy_cession: bool = True,
    ) -> float:
        """Resolve the effective aggregate cession rate.

        If ``inforce`` is provided AND ``use_policy_cession`` is True, computes
        a face-weighted average of per-policy effective cession rates (policy
        override where set, treaty default where not). Otherwise returns the
        flat ``treaty_cession_pct``.
        """
        if inforce is None or not use_policy_cession:
            return treaty_cession_pct
        return inforce.face_weighted_cession(treaty_cession_pct)

    def _expense_allowance_transfer(
        self,
        allowance: "ExpenseAllowance",
        ceded_premiums: np.ndarray,
        ceded_claims: np.ndarray,
        gross: CashFlowResult,
        inforce: "InforceBlock | None",
    ) -> np.ndarray:
        """Per-period sliding-scale expense allowance for a proportional treaty.

        Computes the reinsurer->cedant allowance on the ceded premium stream.
        When an ``InforceBlock`` is supplied, each policy's projection month is
        mapped to its actual policy duration so the first-year rate is only
        applied to business genuinely in policy year one (see
        ``ExpenseAllowance.first_year_fraction_for_block``). Without an
        ``inforce`` the allowance falls back to a new-business basis: the first
        ``months_per_year`` projection periods are treated as first year.

        The caller folds the returned array into the expense lines as a
        transfer (``ceded.expenses += A``, ``net.expenses -= A``) that preserves
        ``net + ceded == gross``.
        """
        first_year_fraction = None
        if inforce is not None:
            first_year_fraction = allowance.first_year_fraction_for_block(
                inforce, len(ceded_premiums), gross.valuation_date
            )
        return allowance.compute_allowance(
            ceded_premiums, ceded_claims, first_year_fraction=first_year_fraction
        )

    def _experience_refund_transfer(
        self,
        refund: "ExperienceRefund",
        ceded_premiums: np.ndarray,
        ceded_claims: np.ndarray,
        allowances: np.ndarray | None,
    ) -> np.ndarray:
        """Terminal experience-refund (profit-sharing) transfer for a treaty.

        Computes the scalar experience refund the reinsurer pays the cedant from
        the accumulated ceded experience — net of any expense allowance already
        paid to the cedant (pass the allowance array so it is not double-counted)
        — and places the whole refund at the **final** projection period. The
        refund settles once at the end of the experience horizon (per-period /
        annual settlement is a future refinement, see ADR-121).

        The caller folds the returned array into the expense lines as a transfer
        (``ceded.expenses += R``, ``net.expenses -= R``) that preserves
        ``net + ceded == gross``: the refund is a reinsurer->cedant payment, not
        a new external cash flow, so it nets to zero across the (net, ceded) pair.
        """
        n = len(ceded_premiums)
        transfer = np.zeros(n, dtype=np.float64)
        if n == 0:
            return transfer
        amount = refund.compute_refund(ceded_premiums, ceded_claims, allowances)
        transfer[-1] = amount
        return transfer

    def verify_additivity(
        self,
        gross: CashFlowResult,
        net: CashFlowResult,
        ceded: CashFlowResult,
        rtol: float = 1e-5,
    ) -> None:
        """
        Assert that net + ceded == gross for premiums and claims.

        Call this in tests after apply() to validate treaty implementations.

        Raises:
            AssertionError: If additivity fails for any cash flow line.
        """
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross.gross_premiums,
            rtol=rtol,
            err_msg="Premium additivity failed: net + ceded != gross",
        )
        np.testing.assert_allclose(
            net.death_claims + ceded.death_claims,
            gross.death_claims,
            rtol=rtol,
            err_msg="Claims additivity failed: net + ceded != gross",
        )
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross.net_cash_flow,
            rtol=rtol,
            err_msg="Net cash flow additivity failed: net + ceded != gross",
        )
