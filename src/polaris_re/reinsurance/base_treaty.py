"""
BaseTreaty — abstract base class for all reinsurance treaty engines.

A treaty transforms a gross CashFlowResult into (net, ceded) pair.
The invariant that must hold for all implementations:

    net + ceded == gross   (for every cash flow line)

This is verified via verify_additivity() in the test suite.
"""

from abc import ABC, abstractmethod

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["BaseTreaty"]


class BaseTreaty(ABC):
    """
    Abstract base for all reinsurance treaty engines.

    The sole public interface is `apply()`, which receives the gross
    CashFlowResult and returns a (net, ceded) tuple.
    """

    @abstractmethod
    def apply(self, gross: CashFlowResult) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply the treaty to gross cash flows.

        Args:
            gross: CashFlowResult on GROSS basis from a product engine.

        Returns:
            (net, ceded) tuple. net + ceded must equal gross for all lines.
        """

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
