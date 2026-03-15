"""
MorbidityTable — incidence and termination rates for Critical Illness (CI)
and Disability Income (DI) products.

Critical Illness:
    - Incidence rate i_x: probability of a first qualifying CI event per year.
    - Policies terminate after a CI claim (lump sum paid, coverage ends).
    - No termination/recovery rates needed.

Disability Income:
    - Incidence rate p_x: probability of becoming disabled per year.
    - Termination rate mu_x: probability of recovery or death while disabled per year.
    - Multiple-state model: Active → Disabled (Active), Active → Dead, Disabled → Active (recovery).

Rate structure mirrors MortalityTable: sex-distinct arrays indexed by attained age.
Ultimate-only supported in Phase 2 (no select period). Vectorized lookups follow
the same pattern as MortalityTable.get_qx_vector().

Rates are stored as ANNUAL rates; monthly conversion is the caller's responsibility.
"""

from enum import StrEnum

import numpy as np
from pydantic import ConfigDict, Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["MorbidityTable", "MorbidityTableType"]


class MorbidityTableType(StrEnum):
    """Morbidity product type."""

    CRITICAL_ILLNESS = "CI"
    DISABILITY_INCOME = "DI"


class MorbidityTable(PolarisBaseModel):
    """
    Age-distinct morbidity incidence and termination rate table.

    Supports CI (incidence only) and DI (incidence + termination).
    All rates are annual probabilities in [0, 1].
    Lookup is by attained age; ages outside [min_age, max_age] are clipped.

    All numpy arrays must be 1D with length (max_age - min_age + 1).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    table_type: MorbidityTableType = Field(description="CI or DI product type.")
    source: str = Field(description="Table source identifier (e.g. 'SOA_2012_CI').")

    min_age: int = Field(ge=0, le=120, description="Minimum age in the table.")
    max_age: int = Field(ge=0, le=120, description="Maximum age in the table.")

    # Incidence rates by age, shape (max_age - min_age + 1,), dtype float64
    male_incidence: np.ndarray = Field(description="Male annual incidence rates by age.")
    female_incidence: np.ndarray = Field(description="Female annual incidence rates by age.")

    # DI only: termination rates (recovery + DI mortality) by age
    male_termination: np.ndarray | None = Field(
        default=None,
        description="Male annual termination rates while disabled. Required for DI.",
    )
    female_termination: np.ndarray | None = Field(
        default=None,
        description="Female annual termination rates while disabled. Required for DI.",
    )

    @model_validator(mode="after")
    def validate_table(self) -> "MorbidityTable":
        n = self.max_age - self.min_age + 1
        if n <= 0:
            raise PolarisValidationError(
                f"max_age must be > min_age. Got {self.min_age}, {self.max_age}."
            )
        for name, arr in [
            ("male_incidence", self.male_incidence),
            ("female_incidence", self.female_incidence),
        ]:
            if arr.shape != (n,):
                raise PolarisValidationError(
                    f"{name} shape must be ({n},), got {arr.shape}."
                )
            if np.any(arr < 0) or np.any(arr > 1):
                raise PolarisValidationError(f"{name} values must be in [0, 1].")
        if self.table_type == MorbidityTableType.DISABILITY_INCOME:
            for name, term_arr in [
                ("male_termination", self.male_termination),
                ("female_termination", self.female_termination),
            ]:
                if term_arr is None:
                    raise PolarisValidationError(
                        f"{name} is required for DI tables."
                    )
                if term_arr.shape != (n,):
                    raise PolarisValidationError(
                        f"{name} shape must be ({n},), got {term_arr.shape}."
                    )
        return self

    def get_incidence_vector(self, ages: np.ndarray, sex: str) -> np.ndarray:
        """
        Return annual incidence rates for a vector of ages.

        Args:
            ages: Attained ages, shape (N,), dtype int32.
            sex:  "M" or "F".

        Returns:
            Annual incidence rates, shape (N,), dtype float64.
        """
        idx = np.clip(ages.astype(np.int32), self.min_age, self.max_age) - self.min_age
        if sex == "M":
            return self.male_incidence[idx]
        return self.female_incidence[idx]

    def get_termination_vector(self, ages: np.ndarray, sex: str) -> np.ndarray:
        """
        Return annual termination (recovery) rates for disabled lives.

        Only applicable for DI. Raises PolarisValidationError for CI tables.

        Args:
            ages: Attained ages of disabled lives, shape (N,), dtype int32.
            sex:  "M" or "F".

        Returns:
            Annual termination rates, shape (N,), dtype float64.
        """
        if self.table_type != MorbidityTableType.DISABILITY_INCOME:
            raise PolarisValidationError(
                "get_termination_vector() is only applicable for DI tables."
            )
        idx = np.clip(ages.astype(np.int32), self.min_age, self.max_age) - self.min_age
        if sex == "M":
            assert self.male_termination is not None
            return self.male_termination[idx]
        assert self.female_termination is not None
        return self.female_termination[idx]

    @classmethod
    def synthetic_ci(cls) -> "MorbidityTable":
        """
        Synthetic CI incidence table for testing.

        Approximate 2012 SOA CI-incidence pattern for ages 18-75.
        Male and female rates based on published SOA data patterns (males ~20% higher).
        Rates in annual probability per life.
        """
        min_age, max_age = 18, 75

        # Approximate CI incidence (all cause) per 1000 insured per year, converted to probabilities
        # Pattern: low at young ages, rising steeply from 50+
        age_grid = np.arange(min_age, max_age + 1, dtype=np.float64)

        # Male: ages 18-75
        male_rates = np.where(
            age_grid < 35,
            0.0005 + (age_grid - 18) * 0.00005,
            np.where(
                age_grid < 50,
                0.00085 + (age_grid - 35) * 0.0002,
                np.where(
                    age_grid < 65,
                    0.0038 + (age_grid - 50) * 0.0006,
                    0.012 + (age_grid - 65) * 0.001,
                ),
            ),
        )
        female_rates = male_rates * 0.85  # females ~15% lower overall CI incidence

        male_rates = np.clip(male_rates, 0.0, 1.0).astype(np.float64)
        female_rates = np.clip(female_rates, 0.0, 1.0).astype(np.float64)

        return cls(
            table_type=MorbidityTableType.CRITICAL_ILLNESS,
            source="SYNTHETIC_CI_2012",
            min_age=min_age,
            max_age=max_age,
            male_incidence=male_rates,
            female_incidence=female_rates,
        )

    @classmethod
    def synthetic_di(cls) -> "MorbidityTable":
        """
        Synthetic DI incidence + termination table for testing.

        Approximate DI incidence and recovery pattern for ages 18-65.
        Termination = recovery + DI mortality combined.
        """
        min_age, max_age = 18, 65

        age_grid = np.arange(min_age, max_age + 1, dtype=np.float64)

        # Incidence: rises with age up to ~60
        male_inc = np.where(
            age_grid < 40,
            0.002 + (age_grid - 18) * 0.0001,
            np.where(
                age_grid < 55,
                0.004 + (age_grid - 40) * 0.0003,
                0.0085 + (age_grid - 55) * 0.0002,
            ),
        )
        female_inc = male_inc * 1.1  # females slightly higher DI incidence

        # Termination (recovery + mortality): decreases with age
        male_term = np.where(
            age_grid < 35,
            0.35,
            np.where(
                age_grid < 50,
                0.35 - (age_grid - 35) * 0.010,
                np.where(
                    age_grid < 60,
                    0.20 - (age_grid - 50) * 0.008,
                    0.12,
                ),
            ),
        )
        female_term = male_term * 1.05

        male_inc = np.clip(male_inc, 0.0, 1.0).astype(np.float64)
        female_inc = np.clip(female_inc, 0.0, 1.0).astype(np.float64)
        male_term = np.clip(male_term, 0.0, 1.0).astype(np.float64)
        female_term = np.clip(female_term, 0.0, 1.0).astype(np.float64)

        return cls(
            table_type=MorbidityTableType.DISABILITY_INCOME,
            source="SYNTHETIC_DI",
            min_age=min_age,
            max_age=max_age,
            male_incidence=male_inc,
            female_incidence=female_inc,
            male_termination=male_term,
            female_termination=female_term,
        )
