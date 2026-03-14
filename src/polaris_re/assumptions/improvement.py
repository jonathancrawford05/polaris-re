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
NONE      No improvement - rates returned unchanged.

Mathematical Formulation:
--------------------------
Scale AA (age-only):
    q_x(Y) = q_x(base_year) * (1 - AA_x)^(Y - base_year)

MP-2020 / CPM-B (age * year, two-dimensional):
    q_x(Y) = q_x(base_year) * product_{y=base_year}^{Y-1} (1 - AI_x(y))

Implementation Notes for Claude Code:
--------------------------------------
- Base year for CIA 2014 = 2014; for SOA VBT 2015 = 2015.
- Improvement applied to ANNUAL q_x before monthly conversion.
- Phase 1: NONE and SCALE_AA only. Defer MP_2020 and CPM_B to Phase 2.
"""

from enum import StrEnum

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["ImprovementScale", "MortalityImprovement"]


class ImprovementScale(StrEnum):
    """Supported mortality improvement scales."""

    SCALE_AA = "SCALE_AA"
    MP_2020 = "MP_2020"
    CPM_B = "CPM_B"
    NONE = "NONE"


# SOA Scale AA improvement factors by age (0-120).
# These are representative annual improvement rates. Scale AA is constant over
# calendar years (age-only). Values are approximate based on SOA published data.
# Pattern: higher improvement at younger ages, declining for very old ages.
_SCALE_AA_FACTORS: np.ndarray = np.array(
    [0.010] * 18  # ages 0-17: 1.0%
    + [0.015] * 7  # ages 18-24: 1.5%
    + [0.012] * 10  # ages 25-34: 1.2%
    + [0.010] * 10  # ages 35-44: 1.0%
    + [0.010] * 10  # ages 45-54: 1.0%
    + [0.008] * 10  # ages 55-64: 0.8%
    + [0.006] * 10  # ages 65-74: 0.6%
    + [0.003] * 10  # ages 75-84: 0.3%
    + [0.001] * 10  # ages 85-94: 0.1%
    + [0.000] * 26,  # ages 95-120: 0.0%
    dtype=np.float64,
)


def _get_scale_aa_factors(ages: np.ndarray) -> np.ndarray:
    """Look up Scale AA improvement factors for a vector of ages."""
    capped_ages = np.clip(ages, 0, len(_SCALE_AA_FACTORS) - 1)
    return _SCALE_AA_FACTORS[capped_ages]


class MortalityImprovement(PolarisBaseModel):
    """
    Applies mortality improvement to base table rates.

    Phase 1 supports NONE and SCALE_AA only.
    """

    scale: ImprovementScale = Field(description="Which improvement scale to apply.")
    base_year: int = Field(description="Calendar year of the base mortality table.")

    @classmethod
    def none(cls, base_year: int) -> "MortalityImprovement":
        """No-improvement instance - rates returned unchanged."""
        return cls(scale=ImprovementScale.NONE, base_year=base_year)

    @classmethod
    def scale_aa(cls, base_year: int) -> "MortalityImprovement":
        """Scale AA improvement instance."""
        return cls(scale=ImprovementScale.SCALE_AA, base_year=base_year)

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
        """
        if self.scale == ImprovementScale.NONE:
            return q_base.copy()

        if self.scale == ImprovementScale.SCALE_AA:
            years = target_year - self.base_year
            if years < 0:
                raise PolarisValidationError(
                    f"target_year {target_year} is before base_year {self.base_year}."
                )
            if years == 0:
                return q_base.copy()
            aa_factors = _get_scale_aa_factors(ages)
            improved = q_base * (1.0 - aa_factors) ** years
            return np.clip(improved, 0.0, 1.0)

        raise NotImplementedError(
            f"apply_improvement not yet implemented for scale {self.scale}. "
            "MP_2020 and CPM_B are Phase 2."
        )
