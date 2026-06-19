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
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis

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

    # --- Reserve basis dispatch ---------------------------------------

    #: Reserve bases this product engine can currently compute. Concrete
    #: engines override this as additional bases are implemented in later
    #: slices of the reserve-basis epic. NET_PREMIUM is always supported.
    _supported_reserve_bases: frozenset[ReserveBasis] = frozenset({ReserveBasis.NET_PREMIUM})

    def _check_reserve_basis(self) -> ReserveBasis:
        """
        Validate that this engine implements the configured reserve basis.

        Returns the active basis so callers can dispatch on it. Raises
        PolarisComputationError (never silently falls back) when the
        configured basis is not yet implemented for this product, so a
        pricing run can never report a reserve on a basis the engine did
        not actually compute.
        """
        basis = self.config.reserve_basis
        if basis not in self._supported_reserve_bases:
            supported = ", ".join(sorted(b.value for b in self._supported_reserve_bases))
            raise PolarisComputationError(
                f"Reserve basis {basis.value!r} is not yet implemented for "
                f"{type(self).__name__}. Supported bases: {supported}. "
                "CRVM / VM20 / GAAP bases are added in later slices of the "
                "reserve-basis epic (see docs/PLAN_reserve_basis.md)."
            )
        return basis
