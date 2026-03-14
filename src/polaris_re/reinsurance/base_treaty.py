"""
BaseTreaty — abstract base class for all reinsurance treaty engines.

A treaty takes a gross CashFlowResult and returns ceded and net CashFlowResult
objects. The invariant that must hold for all treaty implementations:

    net_cashflow + ceded_cashflow == gross_cashflow   (for all cash flow lines)

This is verified in the test suite for every concrete treaty implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["BaseTreaty"]


class BaseTreaty(ABC):
    """
    Abstract base for all reinsurance treaty engines.

    The `apply()` method is the sole public interface. It receives the gross
    CashFlowResult and returns a (net, ceded) tuple.
    """

    @abstractmethod
    def apply(self, gross: CashFlowResult) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply the treaty to gross cash flows.

        Args:
            gross: CashFlowResult on GROSS basis from a product engine.

        Returns:
            Tuple of (net CashFlowResult, ceded CashFlowResult).
            net + ceded must equal gross for all cash flow lines.
        """

    def verify_additivity(
        self,
        gross: CashFlowResult,
        net: CashFlowResult,
        ceded: CashFlowResult,
        rtol: float = 1e-5,
    ) -> None:
        """
        Verify that net + ceded == gross for all cash flow lines.
        Call in tests to validate treaty implementations.

        Raises:
            AssertionError if additivity fails.
        """
        import numpy as np
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
