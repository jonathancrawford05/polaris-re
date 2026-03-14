"""
AssumptionSet — bundles all actuarial assumptions for a projection run.

The AssumptionSet is the single versioned object passed to projection engines.
It is immutable (frozen Pydantic model) to ensure assumptions cannot be
accidentally modified mid-projection.

Every AssumptionSet must carry a version string for audit traceability.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.base import PolarisBaseModel

__all__ = ["AssumptionSet"]


class AssumptionSet(PolarisBaseModel):
    """
    A versioned, immutable bundle of all actuarial assumptions for a projection.

    Pass an AssumptionSet to any BaseProduct.project() call. This ensures
    full traceability — every run is tied to an explicit, auditable assumption set.
    """

    # --- Required assumptions ---
    mortality: MortalityTable = Field(description="Base mortality table.")
    lapse: LapseAssumption = Field(description="Voluntary lapse (termination) rates.")

    # --- Optional assumptions (required for Phase 2+) ---
    # improvement: MortalityImprovement | None = None   # Phase 1: improvement optional
    # expense: ExpenseAssumption | None = None          # Phase 2

    # --- Versioning and audit metadata ---
    version: str = Field(
        description="Version identifier for this assumption set (e.g. 'v1.0', '2025Q1-pricing')."
    )
    effective_date: date | None = Field(
        default=None,
        description="Date from which these assumptions are effective.",
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes on assumption sources, adjustments, or approvals.",
    )

    @property
    def summary(self) -> str:
        """Human-readable one-line summary of this assumption set."""
        return (
            f"AssumptionSet(version={self.version}, "
            f"mortality={self.mortality.source.value}, "
            f"lapse_ultimate={self.lapse.ultimate_rate:.1%})"
        )
