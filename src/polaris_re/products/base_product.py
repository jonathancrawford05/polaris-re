"""
BaseProduct — abstract base class for all Polaris RE product projection engines.

All concrete product engines must inherit from BaseProduct and implement:
  - project()         → CashFlowResult on GROSS basis
  - compute_reserves() → np.ndarray shape (N, T)

Product engines must NOT apply reinsurance modifications — that is the
responsibility of the treaty layer (BaseTreaty subclasses).
"""

from abc import ABC, abstractmethod

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig

__all__ = ["BaseProduct"]


class BaseProduct(ABC):
    """
    Abstract base for all product projection engines.

    Args:
        inforce:     The inforce block to project.
        assumptions: The assumption set (mortality, lapse, etc.).
        config:      Projection configuration (horizon, discount rate, time step).
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
            seriatim: If True, populate (N, T) arrays in CashFlowResult.
                      Required for policy-level analysis and some treaty engines.

        Returns:
            CashFlowResult on GROSS basis.
        """

    @abstractmethod
    def compute_reserves(self) -> np.ndarray:
        """
        Compute policy reserves for the full projection horizon.

        Returns:
            Reserve array, shape (N, T), dtype float64.
            Called by project() and by treaty engines that need reserves
            (YRT NAR calculation, coinsurance reserve transfer).
        """
