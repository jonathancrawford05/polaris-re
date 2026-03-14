"""
Mortality table CSV loader and format utilities.

CANONICAL CSV SCHEMA
--------------------
Filename convention: {source}_{sex}_{smoker}.csv
  e.g. soa_vbt_2015_male_ns.csv, cia_2014_female_smoker.csv, cso_2001_male.csv

SELECT-AND-ULTIMATE tables (CIA 2014, SOA VBT 2015):
    age | dur_1 | dur_2 | ... | dur_N | ultimate
    18  | 0.000 | 0.000 | ... | 0.000 | 0.001
    ...
    age     = attained age (ANB for CIA; ALB for SOA VBT)
    dur_1..N = select-period rates for years 1..N since underwriting
    ultimate = rate for policies past the select period

ULTIMATE-ONLY tables (2001 CSO):
    age | rate
    0   | 0.004
    ...

VALIDATION RULES:
    1. All rates in [0.0, 1.0]
    2. Age column must be contiguous integers (no gaps)
    3. Ultimate column must be present for select tables
    4. Ultimate rates non-decreasing above age 80 (approximately)

Implementation Notes for Claude Code:
--------------------------------------
- Use polars.read_csv for performance
- Return MortalityTableArray: 2D numpy array (n_ages, select_period + 1)
  where last column is ultimate; indexed by [age - min_age, duration_col]
- Validate on load; raise PolarisValidationError on bad data

TODO (Phase 1, Milestone 1.2):
- Implement load_mortality_csv using polars + validation
- Implement MortalityTableArray.get_rate_vector with numpy advanced indexing
- Tests with synthetic CSV fixtures in tests/fixtures/
"""

from pathlib import Path

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["load_mortality_csv", "MortalityTableArray"]


class MortalityTableArray:
    """
    Loaded mortality table as a 2D numpy array for fast vectorized lookups.

    Shape: (n_ages, select_period + 1)
      Columns 0..N-1: select-period rates (duration years 1..N)
      Column N:       ultimate rates
    Indexed by: [age - min_age, min(duration_years, select_period)]
    """

    def __init__(
        self,
        rates: np.ndarray,
        min_age: int,
        max_age: int,
        select_period: int,
        source_file: Path,
    ) -> None:
        self.rates = rates
        self.min_age = min_age
        self.max_age = max_age
        self.select_period = select_period
        self.source_file = source_file

    def get_rate(self, age: int, duration_years: int) -> float:
        """Single rate lookup. duration_years is capped at select_period."""
        if not (self.min_age <= age <= self.max_age):
            raise PolarisValidationError(
                f"Age {age} outside table range [{self.min_age}, {self.max_age}]."
            )
        age_idx = age - self.min_age
        dur_col = min(duration_years, self.select_period)
        return float(self.rates[age_idx, dur_col])

    def get_rate_vector(
        self,
        ages: np.ndarray,
        durations_years: np.ndarray,
    ) -> np.ndarray:
        """
        Vectorized rate lookup.

        Args:
            ages:            Attained ages, shape (N,), dtype int32.
            durations_years: Policy years in select period, shape (N,), dtype int32.

        Returns:
            Annual mortality rates, shape (N,), dtype float64.

        TODO: Implement using numpy advanced indexing:
            age_idx  = ages - self.min_age
            dur_cols = np.minimum(durations_years, self.select_period)
            return self.rates[age_idx, dur_cols]
        """
        raise NotImplementedError("MortalityTableArray.get_rate_vector() not yet implemented.")


def load_mortality_csv(
    path: Path,
    select_period: int,
    min_age: int = 18,
    max_age: int = 120,
) -> MortalityTableArray:
    """
    Load and validate a mortality table CSV into a MortalityTableArray.

    Args:
        path:          Full path to the CSV file.
        select_period: Number of select years (0 for ultimate-only tables).
        min_age:       Expected minimum age (for validation).
        max_age:       Expected maximum age (for validation).

    Returns:
        Validated MortalityTableArray.

    Raises:
        FileNotFoundError: CSV not found.
        PolarisValidationError: Table fails validation.

    TODO: Implement using polars.read_csv + numpy array construction.
    """
    if not path.exists():
        raise FileNotFoundError(f"Mortality table CSV not found: {path}")
    raise NotImplementedError(
        "load_mortality_csv not yet implemented. "
        "See module docstring for CSV schema and validation rules."
    )
