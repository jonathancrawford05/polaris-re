"""
Table CSV loader and format utilities for mortality and lapse tables.

MORTALITY CSV SCHEMA
--------------------
Filename convention: {source}_{sex}_{smoker}.csv
  e.g. soa_vbt_2015_male_ns.csv, cia_2014_female_smoker.csv, cso_2001_male.csv

SELECT-AND-ULTIMATE tables (CIA 2014, SOA VBT 2015):
    age | dur_1 | dur_2 | ... | dur_N | ultimate
    18  | 0.000 | 0.000 | ... | 0.000 | 0.001

ULTIMATE-ONLY tables (2001 CSO):
    age | rate

LAPSE CSV SCHEMA
----------------
Lapse rates are 1D (by policy year), not 2D like mortality (age x duration).

Ultimate-only format:
    policy_year | rate
    1           | 0.10
    2           | 0.08
    ...

VALIDATION RULES:
    1. All rates in [0.0, 1.0]
    2. Key column (age or policy_year) must be contiguous integers (no gaps)
    3. Ultimate column must be present for select tables
"""

from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["LapseTableArray", "MortalityTableArray", "load_lapse_csv", "load_mortality_csv"]


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


class LapseTableArray:
    """
    Loaded lapse table as a 1D numpy array for fast vectorized lookups.

    Lapse rates are indexed by policy year (1-based). Years beyond the
    last explicit year use the final rate as the ultimate rate.

    Shape: (n_years,) where index 0 = policy year 1.
    """

    def __init__(
        self,
        rates: np.ndarray,
        max_policy_year: int,
        source_file: Path,
    ) -> None:
        self.rates = rates
        self.max_policy_year = max_policy_year
        self.source_file = source_file

    def get_rate(self, policy_year: int) -> float:
        """Single rate lookup. Years beyond max_policy_year use ultimate (last) rate."""
        idx = min(policy_year, self.max_policy_year) - 1
        return float(self.rates[idx])

    def get_rate_vector(self, policy_years: np.ndarray) -> np.ndarray:
        """
        Vectorized rate lookup.

        Args:
            policy_years: Policy years (1-based), shape (N,), dtype int32.

        Returns:
            Annual lapse rates, shape (N,), dtype float64.
        """
        idx = np.minimum(policy_years, self.max_policy_year) - 1
        return self.rates[idx]


def load_lapse_csv(
    path: Path,
    min_policy_year: int = 1,
    max_policy_year: int | None = None,
) -> LapseTableArray:
    """
    Load and validate a lapse table CSV into a LapseTableArray.

    Expected CSV schema:
        policy_year | rate
        1           | 0.10
        2           | 0.08
        ...

    The last row's rate is treated as the ultimate rate for all years
    beyond the table's range.

    Args:
        path:             Full path to the CSV file.
        min_policy_year:  Expected minimum policy year (default: 1).
        max_policy_year:  If set, truncate table to this many years.
                          If None, use all rows from the CSV.

    Returns:
        Validated LapseTableArray.

    Raises:
        FileNotFoundError: CSV not found.
        PolarisValidationError: Table fails validation.
    """
    if not path.exists():
        raise FileNotFoundError(f"Lapse table CSV not found: {path}")

    df = pl.read_csv(path)

    if df.columns[0] != "policy_year":
        raise PolarisValidationError(
            f"First column must be 'policy_year', got '{df.columns[0]}'."
        )

    if "rate" not in df.columns:
        raise PolarisValidationError(
            f"Missing required 'rate' column in {path.name}. "
            f"Found columns: {df.columns}"
        )

    years = df["policy_year"].to_numpy().astype(np.int32)
    rates = df["rate"].to_numpy().astype(np.float64)

    # Validate contiguous policy years starting at min_policy_year
    actual_min = int(years.min())
    actual_max = int(years.max())

    if actual_min > min_policy_year:
        raise PolarisValidationError(
            f"Table starts at policy year {actual_min}, expected {min_policy_year}."
        )

    expected_years = np.arange(actual_min, actual_max + 1, dtype=np.int32)
    if len(years) != len(expected_years) or not np.array_equal(years, expected_years):
        raise PolarisValidationError(
            "policy_year column must be contiguous integers with no gaps."
        )

    # Validate rates in [0, 1]
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        raise PolarisValidationError("All lapse rates must be in [0.0, 1.0].")

    # Filter to requested range
    mask = years >= min_policy_year
    rates = rates[mask]

    if max_policy_year is not None:
        rates = rates[:max_policy_year]

    n_years = len(rates)

    return LapseTableArray(
        rates=rates,
        max_policy_year=n_years,
        source_file=path,
    )
