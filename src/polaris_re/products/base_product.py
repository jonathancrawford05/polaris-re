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
from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Sex, SmokerStatus
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
        self._sex_smoker_masks_cache: list[tuple[Sex, SmokerStatus, np.ndarray]] | None = None

    # --- Shared mortality lookup --------------------------------------

    def _sex_smoker_masks(self) -> list[tuple[Sex, SmokerStatus, np.ndarray]]:
        """
        Per-(sex, smoker) boolean policy masks, each shape (N,), built once.

        Every mortality-rate builder iterates the block's unique
        (sex, smoker) combinations and looks rates up per masked sub-block.
        The masks depend only on the (immutable) inforce block, so they are
        built once per engine instance and cached.
        """
        if self._sex_smoker_masks_cache is None:
            sex_list = [p.sex for p in self.inforce.policies]
            smoker_list = [p.smoker_status for p in self.inforce.policies]
            combos = sorted(
                set(zip(sex_list, smoker_list, strict=True)),
                key=lambda combo: (str(combo[0]), str(combo[1])),
            )
            self._sex_smoker_masks_cache = [
                (
                    sex,
                    smoker,
                    np.array(
                        [
                            (s == sex and sm == smoker)
                            for s, sm in zip(sex_list, smoker_list, strict=True)
                        ],
                        dtype=bool,
                    ),
                )
                for sex, smoker in combos
            ]
        return self._sex_smoker_masks_cache

    def _lookup_qx_column(
        self,
        table: MortalityTable,
        ages: np.ndarray,
        durations: np.ndarray,
    ) -> np.ndarray:
        """
        One time step's monthly mortality lookup on ``table``, shape (N,).

        The single source of the per-(sex, smoker) masked ``get_qx_vector``
        lookup shared by every product's projection-rate builder and by the
        statutory valuation-q builders (ADR-125; extracted per PR #124 review
        so the copies cannot drift). Callers own everything around it —
        age capping, improvement, substandard rating, max-age forcing, and
        term-expiry masks — because those legitimately differ by product and
        by basis.
        """
        q_col = np.zeros(self.inforce.n_policies, dtype=np.float64)
        for sex, smoker, mask in self._sex_smoker_masks():
            q_col[mask] = table.get_qx_vector(ages[mask], sex, smoker, durations[mask])
        return q_col

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
                "NET_PREMIUM / CRVM / VM20 / GAAP (FAS 60) are all implemented "
                "for TermLife and WholeLife (see ADR-087..092, ADR-127, ADR-128, "
                "docs/PLAN_reserve_basis.md and docs/PLAN_reserve_basis_exactness.md); "
                "other product engines currently support NET_PREMIUM only."
            )
        return basis
