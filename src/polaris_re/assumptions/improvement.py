"""
MortalityImprovement — projects base mortality rates forward in time
using standard improvement scales.

Mortality improvement reflects the secular trend of declining death rates
over time. Applying improvement scales is essential when pricing products
issued today but running claims in future decades.

Supported Improvement Scales:
------------------------------
SCALE_AA:   SOA Scale AA (published 1995). Older, commonly used for
            locked-in GAAP assumptions. Flat improvement rates by age.

MP_2020:    SOA Mortality Projection Scale MP-2020. Two-dimensional:
            improvement factors vary by both age and calendar year.
            The current North American industry standard.

CPM_B:      Canadian Pension/Mortality Improvement Scale B.
            Published by CIA. Two-dimensional, Canada-specific.
            Used for Canadian IFRS 17 best estimate assumptions.

Mathematical Formulation:
--------------------------
The improved mortality rate at calendar year Y for a life aged x is:

    q_x(Y) = q_x(base_year) × Π_{y=base_year}^{Y-1} (1 - AI_x(y))

Where AI_x(y) is the annual improvement factor for age x in year y.

For Scale AA (age-only, constant over time):
    q_x(Y) = q_x(base_year) × (1 - AA_x)^(Y - base_year)

For MP-2020 (age × year):
    Requires a 2D lookup table AI[age, year] for each calendar projection year.

Implementation Notes for Claude Code:
--------------------------------------
- Base year for CIA 2014 is 2014. Base year for SOA VBT 2015 is 2015.
- Improvement is applied to the ANNUAL q_x rate before converting to monthly.
- The improvement scale CSV files follow the same path convention:
  $POLARIS_DATA_DIR/improvement_scales/scale_aa.csv
  $POLARIS_DATA_DIR/improvement_scales/mp_2020.csv
  $POLARIS_DATA_DIR/improvement_scales/cpm_b.csv
- For Phase 1, Scale AA is sufficient. MP-2020 can be Phase 2.

TODO (Phase 1, Milestone 1.2 — optional, lower priority):
- Implement MortalityImprovement with Scale AA
- Implement apply_improvement(q_base, calendar_year) method
- Add MP-2020 in Phase 2

TODO test: With Scale AA improvement of 1% per year for age 50,
  after 10 years: q_50(Y+10) = q_50(base) × 0.99^10
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import numpy as np

from polaris_re.core.base import PolarisBaseModel
from pydantic import Field

__all__ = ["MortalityImprovement", "ImprovementScale"]


class ImprovementScale(str, Enum):
    """Supported mortality improvement scales."""
    SCALE_AA = "SCALE_AA"
    MP_2020 = "MP_2020"
    CPM_B = "CPM_B"
    NONE = "NONE"  # No improvement applied — used for locked-in GAAP assumptions


class MortalityImprovement(PolarisBaseModel):
    """
    Applies mortality improvement to base table rates.

    Wraps an improvement scale and provides a vectorised method to project
    mortality rates from a base year to a target calendar year.

    Implementation is STUBBED for Phase 1. Scale AA is the priority.
    """

    scale: ImprovementScale = Field(description="Which improvement scale to apply.")
    base_year: int = Field(description="Calendar year of the base mortality table.")

    @classmethod
    def none(cls, base_year: int) -> "MortalityImprovement":
        """No-improvement instance — rates are returned unchanged."""
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
            q_base: Base annual mortality rates, shape (N,), dtype float64.
            ages: Attained ages corresponding to q_base, shape (N,), dtype int32.
            target_year: Calendar year to project rates to.

        Returns:
            Improved annual mortality rates, shape (N,), dtype float64.

        TODO: Implement for SCALE_AA and NONE. Defer MP_2020 and CPM_B to Phase 2.
        """
        if self.scale == ImprovementScale.NONE:
            return q_base.copy()
        raise NotImplementedError(
            f"MortalityImprovement.apply_improvement() not yet implemented for scale {self.scale}. "
            "Implement Scale AA first per module docstring."
        )
