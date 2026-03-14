"""
Mortality table CSV loader and format utilities.

All standard mortality tables are stored as CSV files with a canonical column schema.
This module handles loading, validation, and normalisation of those files.

CANONICAL CSV SCHEMA
--------------------
Files are named: {source}_{sex}_{smoker}.csv
  e.g. soa_vbt_2015_male_ns.csv, cia_2014_female_smoker.csv, cso_2001_male.csv

Column structure for SELECT-AND-ULTIMATE tables (CIA 2014, SOA VBT 2015):

    age | dur_1 | dur_2 | ... | dur_N | ultimate
    ----|-------|-------|-----|-------|----------
    18  | 0.000 | 0.000 | ... | 0.000 | 0.001
    19  | 0.000 | ...
    ...
    120 | 1.000 | ...

    Where:
    - `age` is the attained age (ANB for CIA, ALB for SOA VBT)
    - `dur_1` through `dur_N` are select-period annual mortality rates
      for policies in their 1st through Nth year since underwriting
    - `ultimate` is the mortality rate for policies past the select period

Column structure for ULTIMATE-ONLY tables (2001 CSO):

    age | male | female
    ----|------|-------
    0   | 0.004| 0.003
    ...

VALIDATION RULES
----------------
1. All rates must be in [0.0, 1.0]
2. Age column must be contiguous integers (no gaps)
3. Ultimate column must be present
4. Rates must be non-decreasing with age in the ultimate column (approximately)

Implementation Notes for Claude Code:
--------------------------------------
- Use `polars.read_csv` for performance on large tables
- Return a dict keyed by (age, duration) → float for select tables
- Or return a 2D numpy array shaped (max_age - min_age + 1, select_period + 1)
  where last column is ultimate — this is the preferred format for fast lookup
- Validate immediately on load; raise PolarisValidationError on bad data

TODO (Phase 1, Milestone 1.2):
- Implement load_mortality_csv
- Implement _validate_mortality_dataframe
- Add tests with a small synthetic CSV fixture in tests/fixtures/
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["load_mortality_csv", "MortalityTableArray"]


class MortalityTableArray:
    """
    Internal representation of a loaded mortality table as a 2D numpy array.

    Attributes:
        rates: shape (n_ages, select_period + 1), dtype float64.
               Columns 0..N-1 are select-period rates (duration 1..N).
               Column N is ultimate rates.
               Indexed by [age - min_age, duration_col].
        min_age: Minimum age in the table.
        max_age: Maximum age in the table.
        select_period: Number of select years (0 for ultimate-only tables).
        source_file: Path of the CSV file loaded.
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
        """
        Look up a single mortality rate.

        Args:
            age: Attained age.
            duration_years: Duration in select period (years since underwriting).
                            If > select_period, uses ultimate column.

        Returns:
            Annual mortality rate q_x.
        """
        if not (self.min_age <= age <= self.max_age):
            raise PolarisValidationError(
                f"Age {age} is outside table range [{self.min_age}, {self.max_age}]."
            )
        age_idx = age - self.min_age
        dur_col = min(duration_years, self.select_period)  # cap at ultimate column
        return float(self.rates[age_idx, dur_col])

    def get_rate_vector(
        self,
        ages: np.ndarray,
        durations_years: np.ndarray,
    ) -> np.ndarray:
        """
        Vectorised rate lookup for arrays of ages and durations.

        Args:
            ages: Integer attained ages, shape (N,).
            durations_years: Integer years in select period, shape (N,).

        Returns:
            Annual mortality rates, shape (N,), dtype float64.

        TODO: Implement using numpy advanced indexing for O(1) vectorised lookup.
        """
        raise NotImplementedError("MortalityTableArray.get_rate_vector() not yet implemented.")


def load_mortality_csv(
    path: Path,
    select_period: int,
    min_age: int = 18,
    max_age: int = 120,
) -> MortalityTableArray:
    """
    Load a mortality table CSV file into a MortalityTableArray.

    Args:
        path: Full path to the CSV file.
        select_period: Number of select years in the table (0 for ultimate-only).
        min_age: Expected minimum age in the table (for validation).
        max_age: Expected maximum age in the table (for validation).

    Returns:
        Validated MortalityTableArray ready for rate lookups.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        PolarisValidationError: If the table fails validation checks.

    TODO: Implement using polars.read_csv + validation + conversion to numpy array.
    """
    if not path.exists():
        raise FileNotFoundError(f"Mortality table CSV not found: {path}")

    raise NotImplementedError(
        "load_mortality_csv not yet implemented. "
        "See module docstring for CSV schema and validation requirements."
    )
