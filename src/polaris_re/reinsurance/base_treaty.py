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
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply the treaty to gross cash flows.

        Args:
            gross:   CashFlowResult on GROSS basis from a product engine.
            inforce: Optional InforceBlock. When provided, policy-level
                     reinsurance_cession_pct values override the treaty-level
                     cession_pct. A face-weighted average is computed for
                     aggregate cash flow splitting.

        Returns:
            (net, ceded) tuple. net + ceded must equal gross for all lines.
        """

    def _resolve_cession(
        self,
        treaty_cession_pct: float,
        inforce: "InforceBlock | None",
    ) -> float:
        """Resolve the effective aggregate cession rate.

        If ``inforce`` is provided, computes a face-weighted average of
        per-policy effective cession rates (policy override where set,
        treaty default where not). Otherwise returns ``treaty_cession_pct``.
        """
        if inforce is None:
            return treaty_cession_pct
        return inforce.face_weighted_cession(treaty_cession_pct)

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
