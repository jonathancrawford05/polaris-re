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
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["MortalityTableArray", "load_mortality_csv"]


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
        age_idx = ages - self.min_age
        if np.any(age_idx < 0) or np.any(age_idx >= self.rates.shape[0]):
            raise PolarisValidationError(
                f"Ages outside table range [{self.min_age}, {self.max_age}]."
            )
        dur_cols = np.minimum(durations_years, self.select_period)
        return self.rates[age_idx, dur_cols]


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

    df = pl.read_csv(path)

    # Expect first column to be "age"
    if df.columns[0] != "age":
        raise PolarisValidationError(f"First column must be 'age', got '{df.columns[0]}'.")

    # Determine table structure
    rate_columns = [c for c in df.columns if c != "age"]

    if select_period == 0:
        # Ultimate-only table: expect a single rate column
        if len(rate_columns) < 1:
            raise PolarisValidationError("Ultimate-only table must have at least one rate column.")
        # Use the first rate column as ultimate
        rate_col = rate_columns[0]
        ages_series = df["age"].to_numpy().astype(np.int32)
        rates_1d = df[rate_col].to_numpy().astype(np.float64)
        # Reshape to (n_ages, 1) — the single column is the ultimate column
        rates = rates_1d.reshape(-1, 1)
    else:
        # Select-and-ultimate table
        # Expect dur_1 .. dur_N plus ultimate column
        expected_cols = [f"dur_{i}" for i in range(1, select_period + 1)] + ["ultimate"]
        for col in expected_cols:
            if col not in df.columns:
                raise PolarisValidationError(
                    f"Missing expected column '{col}' in {path.name}. "
                    f"Expected columns: {expected_cols}"
                )
        ages_series = df["age"].to_numpy().astype(np.int32)
        rate_data = df.select(expected_cols).to_numpy().astype(np.float64)
        rates = rate_data

    # Validate age range
    actual_min_age = int(ages_series.min())
    actual_max_age = int(ages_series.max())
    if actual_min_age > min_age:
        raise PolarisValidationError(f"Table min age {actual_min_age} > expected {min_age}.")
    if actual_max_age < max_age:
        raise PolarisValidationError(f"Table max age {actual_max_age} < expected {max_age}.")

    # Filter to requested age range
    mask = (ages_series >= min_age) & (ages_series <= max_age)
    rates = rates[mask]

    # Validate contiguous ages
    filtered_ages = ages_series[mask]
    expected_ages = np.arange(min_age, max_age + 1, dtype=np.int32)
    if len(filtered_ages) != len(expected_ages) or not np.array_equal(filtered_ages, expected_ages):
        raise PolarisValidationError("Age column must be contiguous integers with no gaps.")

    # Validate rates in [0, 1]
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        raise PolarisValidationError("All mortality rates must be in [0.0, 1.0].")

    return MortalityTableArray(
        rates=rates,
        min_age=min_age,
        max_age=max_age,
        select_period=select_period,
        source_file=path,
    )
