"""
MortalityImprovement — projects base mortality rates forward using improvement scales.

Mortality improvement reflects the secular trend of declining death rates over time.
Applying improvement scales is essential when pricing products issued today but
running claims in future decades.

Supported Improvement Scales:
------------------------------
SCALE_AA  SOA Scale AA (1995). Age-only, constant over time. Used for locked-in GAAP.
MP_2020   SOA MP-2020. Two-dimensional: improvement factors vary by age and calendar year.
CPM_B     CIA Scale B. Age-only (simplified), Canada-specific. Used for IFRS 17 best estimate.
NONE      No improvement - rates returned unchanged.

Mathematical Formulation:
--------------------------
Scale AA (age-only):
    q_x(Y) = q_x(base_year) * (1 - AA_x)^(Y - base_year)

MP-2020 (age * year, two-dimensional):
    q_x(Y) = q_x(base_year) * product_{y=base_year}^{Y-1} (1 - AI_x(y))
    where AI_x(y) varies by age and calendar year (2015-2031 period factors,
    then ultimate improvement rate applies).

CPM-B (age-only, simplified):
    q_x(Y) = q_x(base_year) * (1 - B_x)^(Y - base_year)
    where B_x is the CIA Scale B age-specific improvement factor.

Implementation Notes:
----------------------
- Base year for CIA 2014 = 2014; for SOA VBT 2015 = 2015.
- Improvement applied to ANNUAL q_x before monthly conversion.
- MP-2020 factors are approximate representative values based on published SOA data.
- CPM-B factors are approximate representative values based on CIA published data.
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

# SOA MP-2020 improvement factors: approximate representative values.
# Shape: (121 ages, 17 calendar-year periods) where period 0 = year 2015,
# period 16 = year 2031. After 2031, the ultimate rate (last column) applies.
# Values are approximations based on published SOA MP-2020 table patterns:
# - Working ages (20-64): ~1.5-2.0% improvement
# - Near-retirement (65-74): ~1.0-1.5%
# - Older ages (75-84): ~0.5-1.0%
# - Very old (85+): ~0.3-0.5%
_MP2020_FACTORS: np.ndarray = np.zeros((121, 17), dtype=np.float64)

# Build MP-2020 factors by age band and calendar year (years 2015-2031)
# Ages 0-17: modest improvement, roughly 1.0% declining to 0.8%
for _age in range(0, 18):
    _MP2020_FACTORS[_age, :] = np.linspace(0.010, 0.008, 17)

# Ages 18-24: higher improvement ~1.5%
for _age in range(18, 25):
    _MP2020_FACTORS[_age, :] = np.linspace(0.018, 0.014, 17)

# Ages 25-44: ~1.8-2.0% improvement, moderate decline over time
for _age in range(25, 45):
    _MP2020_FACTORS[_age, :] = np.linspace(0.020, 0.015, 17)

# Ages 45-64: ~1.5-1.8%, declining
for _age in range(45, 65):
    _MP2020_FACTORS[_age, :] = np.linspace(0.018, 0.013, 17)

# Ages 65-74: ~0.8-1.2%
for _age in range(65, 75):
    _MP2020_FACTORS[_age, :] = np.linspace(0.012, 0.008, 17)

# Ages 75-84: ~0.5-0.8%
for _age in range(75, 85):
    _MP2020_FACTORS[_age, :] = np.linspace(0.008, 0.005, 17)

# Ages 85-94: ~0.3-0.5%
for _age in range(85, 95):
    _MP2020_FACTORS[_age, :] = np.linspace(0.005, 0.003, 17)

# Ages 95-120: ~0.1-0.2%
for _age in range(95, 121):
    _MP2020_FACTORS[_age, :] = np.linspace(0.002, 0.001, 17)

# MP-2020 first calendar year in the table
_MP2020_BASE_YEAR: int = 2015

# CIA CPM-B improvement factors by age (0-120). Age-only (simplified representation).
# Values approximate CIA published Scale B patterns for Canadian population.
# Pattern: lower overall improvement than US, more conservative at advanced ages.
_CPM_B_FACTORS: np.ndarray = np.array(
    [0.008] * 18  # ages 0-17: 0.8%
    + [0.014] * 7  # ages 18-24: 1.4%
    + [0.015] * 10  # ages 25-34: 1.5%
    + [0.015] * 10  # ages 35-44: 1.5%
    + [0.014] * 10  # ages 45-54: 1.4%
    + [0.010] * 10  # ages 55-64: 1.0%
    + [0.007] * 10  # ages 65-74: 0.7%
    + [0.004] * 10  # ages 75-84: 0.4%
    + [0.002] * 10  # ages 85-94: 0.2%
    + [0.000] * 26,  # ages 95-120: 0.0%
    dtype=np.float64,
)


def _get_scale_aa_factors(ages: np.ndarray) -> np.ndarray:
    """Look up Scale AA improvement factors for a vector of ages."""
    capped_ages = np.clip(ages, 0, len(_SCALE_AA_FACTORS) - 1).astype(np.int32)
    return _SCALE_AA_FACTORS[capped_ages].astype(np.float64)  # type: ignore[no-any-return]


def _get_cpm_b_factors(ages: np.ndarray) -> np.ndarray:
    """Look up CPM-B improvement factors for a vector of ages."""
    capped_ages = np.clip(ages, 0, len(_CPM_B_FACTORS) - 1).astype(np.int32)
    return _CPM_B_FACTORS[capped_ages].astype(np.float64)  # type: ignore[no-any-return]


def _get_mp2020_factors_for_year(ages: np.ndarray, calendar_year: int) -> np.ndarray:
    """
    Look up MP-2020 improvement factors for a vector of ages and a specific calendar year.

    For years before 2015, returns zeros (no improvement applied).
    For years after 2031 (last data year), returns ultimate factors (last column).
    """
    capped_ages = np.clip(ages, 0, 120).astype(np.int32)
    year_offset = calendar_year - _MP2020_BASE_YEAR
    year_offset = int(np.clip(year_offset, 0, _MP2020_FACTORS.shape[1] - 1))
    return _MP2020_FACTORS[capped_ages, year_offset].astype(np.float64)  # type: ignore[no-any-return]


class MortalityImprovement(PolarisBaseModel):
    """
    Applies mortality improvement to base table rates.

    Supports NONE, SCALE_AA (age-only), MP_2020 (age by year), and CPM_B (age-only).
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

    @classmethod
    def mp_2020(cls, base_year: int) -> "MortalityImprovement":
        """SOA MP-2020 improvement instance."""
        return cls(scale=ImprovementScale.MP_2020, base_year=base_year)

    @classmethod
    def cpm_b(cls, base_year: int) -> "MortalityImprovement":
        """CIA CPM-B improvement instance."""
        return cls(scale=ImprovementScale.CPM_B, base_year=base_year)

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
        years = target_year - self.base_year
        if years < 0:
            raise PolarisValidationError(
                f"target_year {target_year} is before base_year {self.base_year}."
            )

        if self.scale == ImprovementScale.NONE:
            return q_base.copy()

        if self.scale == ImprovementScale.SCALE_AA:
            if years == 0:
                return q_base.copy()
            aa_factors = _get_scale_aa_factors(ages)
            improved = q_base * (1.0 - aa_factors) ** years
            return np.clip(improved, 0.0, 1.0)

        if self.scale == ImprovementScale.MP_2020:
            if years == 0:
                return q_base.copy()
            # Accumulate year-by-year improvement product: vectorized over ages
            improvement_product = np.ones(len(q_base), dtype=np.float64)
            for y in range(years):
                cal_year = self.base_year + y
                factors = _get_mp2020_factors_for_year(ages, cal_year)
                improvement_product *= 1.0 - factors
            improved = q_base * improvement_product
            return np.clip(improved, 0.0, 1.0)

        if self.scale == ImprovementScale.CPM_B:
            if years == 0:
                return q_base.copy()
            cpmb_factors = _get_cpm_b_factors(ages)
            improved = q_base * (1.0 - cpmb_factors) ** years
            return np.clip(improved, 0.0, 1.0)

        raise PolarisValidationError(f"Unrecognised improvement scale: {self.scale}")
