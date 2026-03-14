"""
MortalityImprovement — projects base mortality rates forward using improvement scales.

Mortality improvement reflects the secular trend of declining death rates over time.
Applying improvement scales is essential when pricing products issued today but
running claims in future decades.

Supported Improvement Scales:
------------------------------
SCALE_AA  SOA Scale AA (1995). Age-only, constant over time. Used for locked-in GAAP.
MP_2020   SOA MP-2020. Two-dimensional: improvement factors vary by age and calendar year.
CPM_B     CIA Scale B. Two-dimensional, Canada-specific. Used for IFRS 17 best estimate.
NONE      No improvement — rates returned unchanged.

Mathematical Formulation:
--------------------------
Scale AA (age-only):
    q_x(Y) = q_x(base_year) × (1 - AA_x)^(Y - base_year)

MP-2020 / CPM-B (age × year, two-dimensional):
    q_x(Y) = q_x(base_year) × Π_{y=base_year}^{Y-1} (1 - AI_x(y))

Implementation Notes for Claude Code:
--------------------------------------
- Base year for CIA 2014 = 2014; for SOA VBT 2015 = 2015.
- Improvement applied to ANNUAL q_x before monthly conversion.
- CSV files: $POLARIS_DATA_DIR/improvement_scales/{scale_aa|mp_2020|cpm_b}.csv
- Phase 1: NONE and SCALE_AA only. Defer MP_2020 and CPM_B to Phase 2.

TODO (Phase 1, Milestone 1.2 — lower priority than mortality/lapse):
- Implement apply_improvement for SCALE_AA
- Closed-form test: q_50(Y+10) = q_50(base) × (1 - AA_50)^10
"""

from enum import Enum

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel

__all__ = ["MortalityImprovement", "ImprovementScale"]


class ImprovementScale(str, Enum):
    """Supported mortality improvement scales."""
    SCALE_AA = "SCALE_AA"
    MP_2020 = "MP_2020"
    CPM_B = "CPM_B"
    NONE = "NONE"


class MortalityImprovement(PolarisBaseModel):
    """
    Applies mortality improvement to base table rates.

    Implementation is STUBBED. Phase 1 priority: NONE and SCALE_AA only.
    """

    scale: ImprovementScale = Field(description="Which improvement scale to apply.")
    base_year: int = Field(description="Calendar year of the base mortality table.")

    @classmethod
    def none(cls, base_year: int) -> "MortalityImprovement":
        """No-improvement instance — rates returned unchanged."""
        return cls(scale=ImprovementScale.NONE, base_year=base_year)

    def apply_improvement(
        self,
        q_base: np.ndarray,
        ages: np.ndarray,
        target_year: int,
    ) -> np.ndarray:
        """
        Apply improvement from base_year to target_year.

        Args:
            q_base:      Base annual mortality rates, shape (N,), dtype float64.
            ages:        Attained ages, shape (N,), dtype int32.
            target_year: Calendar year to project rates to.

        Returns:
            Improved annual rates, shape (N,), dtype float64.

        TODO: Implement SCALE_AA case:
            years = target_year - self.base_year
            aa_factors = load_scale_aa_factors(ages)   # age-specific improvement rates
            return q_base * (1 - aa_factors) ** years
        """
        if self.scale == ImprovementScale.NONE:
            return q_base.copy()
        raise NotImplementedError(
            f"apply_improvement not yet implemented for scale {self.scale}. "
            "Implement SCALE_AA first per module docstring."
        )
