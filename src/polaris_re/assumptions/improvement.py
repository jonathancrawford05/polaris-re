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
CUSTOM    Data-driven age x calendar-year improvement grid supplied at construction —
          e.g. an experience-fitted ``MI_x(y)`` surface/projection from the experience
          GAM (analytics/experience_gam.py). Years beyond the grid use an ultimate rate.
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

CUSTOM (age * year, two-dimensional, data-driven):
    q_x(Y) = q_x(base_year) * product_{Z=base_year+1}^{Y} (1 - MI_x(Z))
    where MI_x(Z) is the supplied annual improvement for the step ending in
    calendar year Z (base_year = first_grid_year - 1). Ages outside the grid clamp
    to the nearest grid age; step-end years beyond the last grid year use the
    supplied ``custom_ultimate_rate``. Build via ``MortalityImprovement.from_grid``
    (or ``MISurface.to_mortality_improvement`` / ``MIProjection.to_mortality_improvement``).

Implementation Notes:
----------------------
- Base year for CIA 2014 = 2014; for SOA VBT 2015 = 2015.
- Improvement applied to ANNUAL q_x before monthly conversion.
- MP-2020 factors are approximate representative values based on published SOA data.
- CPM-B factors are approximate representative values based on CIA published data.
"""

from enum import StrEnum

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["ImprovementScale", "MortalityImprovement"]


class ImprovementScale(StrEnum):
    """Supported mortality improvement scales."""

    SCALE_AA = "SCALE_AA"
    MP_2020 = "MP_2020"
    CPM_B = "CPM_B"
    CUSTOM = "CUSTOM"
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
    return _SCALE_AA_FACTORS[capped_ages]  # type: ignore[no-any-return]


def _get_cpm_b_factors(ages: np.ndarray) -> np.ndarray:
    """Look up CPM-B improvement factors for a vector of ages."""
    capped_ages = np.clip(ages, 0, len(_CPM_B_FACTORS) - 1).astype(np.int32)
    return _CPM_B_FACTORS[capped_ages]  # type: ignore[no-any-return]


def _get_mp2020_factors_for_year(ages: np.ndarray, calendar_year: int) -> np.ndarray:
    """
    Look up MP-2020 improvement factors for a vector of ages and a specific calendar year.

    For years before 2015, returns zeros (no improvement applied).
    For years after 2031 (last data year), returns ultimate factors (last column).
    """
    capped_ages = np.clip(ages, 0, 120).astype(np.int32)
    year_offset = calendar_year - _MP2020_BASE_YEAR
    year_offset = int(np.clip(year_offset, 0, _MP2020_FACTORS.shape[1] - 1))
    return _MP2020_FACTORS[capped_ages, year_offset]  # type: ignore[no-any-return]


class MortalityImprovement(PolarisBaseModel):
    """
    Applies mortality improvement to base table rates.

    Supports NONE, SCALE_AA (age-only), MP_2020 (age by year), CPM_B (age-only),
    and CUSTOM (a data-driven age x calendar-year MI_x(y) grid — e.g. an
    experience-fitted improvement surface/projection; see :meth:`from_grid`).
    """

    scale: ImprovementScale = Field(description="Which improvement scale to apply.")
    base_year: int = Field(description="Calendar year of the base mortality table.")

    # CUSTOM-scale payload (a data-driven MI_x(y) grid). None for all built-in
    # scales — the defaults preserve backward compatibility for existing callers.
    # Stored as immutable tuples so the frozen model stays hashable and the grid
    # round-trips cleanly through JSON (assumption versioning).
    custom_ages: tuple[int, ...] | None = Field(
        default=None,
        description="Attained ages of the CUSTOM grid rows (strictly increasing, "
        "contiguous). None unless scale is CUSTOM.",
    )
    custom_years: tuple[int, ...] | None = Field(
        default=None,
        description="Step-end calendar years of the CUSTOM grid columns (strictly "
        "increasing, contiguous). None unless scale is CUSTOM.",
    )
    custom_mi_grid: tuple[tuple[float, ...], ...] | None = Field(
        default=None,
        description="Annual improvement rate MI_x(y), shape (len(custom_ages), "
        "len(custom_years)). None unless scale is CUSTOM.",
    )
    custom_ultimate_rate: float = Field(
        default=0.0,
        description="Annual improvement rate applied to step-end years beyond the "
        "last CUSTOM grid year (the long-term/ultimate assumption).",
    )

    @model_validator(mode="after")
    def _validate_custom_payload(self) -> "MortalityImprovement":
        """Enforce grid consistency for CUSTOM and absence of a grid otherwise."""
        has_grid = (
            self.custom_ages is not None
            or self.custom_years is not None
            or self.custom_mi_grid is not None
        )
        if self.scale != ImprovementScale.CUSTOM:
            if has_grid:
                raise PolarisValidationError(
                    "custom_ages/custom_years/custom_mi_grid may only be set when "
                    f"scale is CUSTOM (got scale={self.scale})."
                )
            return self

        # scale == CUSTOM: grid is mandatory and must be internally consistent.
        if self.custom_ages is None or self.custom_years is None or self.custom_mi_grid is None:
            raise PolarisValidationError(
                "CUSTOM improvement requires custom_ages, custom_years, and "
                "custom_mi_grid (use MortalityImprovement.from_grid)."
            )
        if len(self.custom_ages) == 0 or len(self.custom_years) == 0:
            raise PolarisValidationError("CUSTOM grid axes must be non-empty.")
        if len(self.custom_mi_grid) != len(self.custom_ages):
            raise PolarisValidationError(
                f"custom_mi_grid has {len(self.custom_mi_grid)} rows but "
                f"custom_ages has {len(self.custom_ages)} entries."
            )
        if any(len(row) != len(self.custom_years) for row in self.custom_mi_grid):
            raise PolarisValidationError(
                "every custom_mi_grid row must have len(custom_years) entries."
            )
        if any(b - a != 1 for a, b in zip(self.custom_ages, self.custom_ages[1:], strict=False)):
            raise PolarisValidationError(
                "custom_ages must be strictly increasing contiguous integers."
            )
        if any(b - a != 1 for a, b in zip(self.custom_years, self.custom_years[1:], strict=False)):
            raise PolarisValidationError(
                "custom_years must be strictly increasing contiguous integers."
            )
        expected_base = self.custom_years[0] - 1
        if self.base_year != expected_base:
            raise PolarisValidationError(
                f"base_year ({self.base_year}) must equal first grid year minus one "
                f"({expected_base}); the grid's first step ends in "
                f"{self.custom_years[0]}."
            )
        return self

    @classmethod
    def from_grid(
        cls,
        ages: np.ndarray,
        years: np.ndarray,
        mi_grid: np.ndarray,
        ultimate_rate: float = 0.0,
    ) -> "MortalityImprovement":
        """
        Build a CUSTOM improvement scale from an experience-fitted MI_x(y) grid.

        This is the Slice-2c hand-off from the experience GAM: an ``MISurface`` or
        ``MIProjection`` exposes ``ages``, ``years`` (step-end calendar years) and a
        ``mi_grid`` of annual improvement rates; this turns them into a
        ``MortalityImprovement`` that plugs into :meth:`apply_improvement` as
        ``q(Y) = q(base) * Π (1 - MI_x(Z))``.

        Args:
            ages:          Attained ages, shape (A,), strictly increasing contiguous.
            years:         Step-end calendar years, shape (Y,), strictly increasing
                           contiguous. The base year is ``years[0] - 1`` — i.e. the
                           anchor whose mortality the grid improves forward.
            mi_grid:       Annual improvement rates MI_x(y), shape (A, Y), float64.
            ultimate_rate: Improvement applied to step-end years beyond ``years[-1]``.

        Returns:
            A CUSTOM ``MortalityImprovement`` with ``base_year = years[0] - 1``.
        """
        ages_arr = np.asarray(ages)
        years_arr = np.asarray(years)
        grid_arr = np.asarray(mi_grid, dtype=np.float64)
        if grid_arr.ndim != 2:
            raise PolarisValidationError(f"mi_grid must be 2-D (A, Y); got shape {grid_arr.shape}.")
        return cls(
            scale=ImprovementScale.CUSTOM,
            base_year=int(years_arr[0]) - 1,
            custom_ages=tuple(int(a) for a in ages_arr),
            custom_years=tuple(int(y) for y in years_arr),
            custom_mi_grid=tuple(tuple(float(v) for v in row) for row in grid_arr),
            custom_ultimate_rate=float(ultimate_rate),
        )

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

        if self.scale == ImprovementScale.CUSTOM:
            if years == 0:
                return q_base.copy()
            improvement_product = self._custom_improvement_product(ages, target_year)
            improved = q_base * improvement_product
            return np.clip(improved, 0.0, 1.0)

        raise PolarisValidationError(f"Unrecognised improvement scale: {self.scale}")

    def _custom_improvement_product(self, ages: np.ndarray, target_year: int) -> np.ndarray:
        """
        Cumulative CUSTOM improvement factor ``Π (1 - MI_x(Z))`` per policy, from
        ``base_year`` to ``target_year``.

        Steps end in years ``base_year + 1 .. target_year``. For each step-end year
        ``Z``: within the grid the column ``Z - custom_years[0]`` is used; beyond
        ``custom_years[-1]`` the ``custom_ultimate_rate`` applies to every age. Ages
        are clamped to the grid's age range (constant extrapolation at the edges).
        """
        grid_ages = np.asarray(self.custom_ages, dtype=np.int64)
        grid_years = np.asarray(self.custom_years, dtype=np.int64)
        grid = np.asarray(self.custom_mi_grid, dtype=np.float64)  # (A, Y)

        # Row index per policy: clamp attained age into the grid range, then offset
        # (grid ages are validated contiguous).
        capped_ages = np.clip(ages, grid_ages[0], grid_ages[-1]).astype(np.int64)
        row_idx = capped_ages - grid_ages[0]

        first_year = int(grid_years[0])
        last_year = int(grid_years[-1])
        product = np.ones(len(ages), dtype=np.float64)
        for end_year in range(self.base_year + 1, target_year + 1):
            if end_year > last_year:
                factors = np.full(len(ages), self.custom_ultimate_rate, dtype=np.float64)
            else:
                factors = grid[row_idx, end_year - first_year]
            product *= 1.0 - factors
        return product
