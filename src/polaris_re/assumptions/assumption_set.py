"""
AssumptionSet — bundles all actuarial assumptions for a projection run.

Immutable (frozen Pydantic model). Every AssumptionSet carries a version
string for full audit traceability — every projection run is tied to
an explicit, documented assumption set.
"""

from datetime import date

from pydantic import Field

from polaris_re.assumptions.improvement import MortalityImprovement
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.base import PolarisBaseModel

__all__ = ["AssumptionSet"]


class AssumptionSet(PolarisBaseModel):
    """
    A versioned, immutable bundle of all actuarial assumptions for a projection.

    Pass an AssumptionSet to any BaseProduct.project() call to ensure
    full traceability across projection runs.
    """

    # --- Required ---
    mortality: MortalityTable = Field(description="Base mortality table.")
    lapse: LapseAssumption = Field(description="Voluntary lapse (termination) rates.")

    # --- Optional ---
    improvement: MortalityImprovement | None = Field(
        default=None,
        description="Mortality improvement projection (Scale AA, MP-2020, CPM-B, or None).",
    )
    # expense: ExpenseAssumption | None = None  # Phase 2+

    # --- Audit metadata ---
    version: str = Field(description="Version identifier, e.g. 'v1.0' or '2025Q1-pricing'.")
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
        """Human-readable one-line summary."""
        return (
            f"AssumptionSet(version={self.version}, "
            f"mortality={self.mortality.source.value}, "
            f"lapse_ultimate={self.lapse.ultimate_rate:.1%})"
        )
