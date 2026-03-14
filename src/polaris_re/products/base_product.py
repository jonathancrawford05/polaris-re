"""
BaseProduct — abstract base class for all Polaris RE product engines.

All product engines must inherit from BaseProduct and implement the
`project()` method, which takes the bound InforceBlock, AssumptionSet,
and ProjectionConfig and returns a CashFlowResult on a GROSS basis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig

__all__ = ["BaseProduct"]


class BaseProduct(ABC):
    """
    Abstract base class for all product projection engines.

    Subclasses implement `project()` to produce gross cash flows.
    They must NOT apply reinsurance modifications — that is the
    responsibility of the treaty layer.

    Args:
        inforce: The inforce block to project.
        assumptions: The assumption set to use.
        config: Projection configuration (horizon, discount rate, etc.).
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
    ) -> None:
        self.inforce = inforce
        self.assumptions = assumptions
        self.config = config

    @abstractmethod
    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run the projection and return gross cash flows.

        Args:
            seriatim: If True, populate seriatim arrays (N×T) in CashFlowResult.
                      Slower but required for policy-level analysis and some treaty calculations.

        Returns:
            CashFlowResult on a GROSS basis.
        """

    @abstractmethod
    def compute_reserves(self) -> "import numpy as np; np.ndarray":
        """
        Compute policy reserves for the full projection horizon.

        Returns shape (N, T) array of per-policy reserve balances.
        Called internally by `project()` and also by treaty engines that need
        reserves (e.g. YRT NAR calculation, coinsurance reserve transfer).
        """
