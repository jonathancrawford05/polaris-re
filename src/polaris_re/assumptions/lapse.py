"""
LapseAssumption — duration-based lapse (voluntary termination) rates.

Lapse rates represent the probability that a policyholder voluntarily
terminates their policy in a given policy year. They follow a
"select and ultimate" pattern — high in early durations, declining to a
stable ultimate rate after the select period.

Supports two construction methods:
  1. ``from_duration_table()`` — from an in-memory dict (testing/hardcoded)
  2. ``load()`` — from a CSV file matching the Polaris RE lapse schema

Lapse rates are per policy year (annual), not per month.
Monthly: w_monthly = 1 - (1 - w_annual)^(1/12)
"""

from pathlib import Path
from typing import Self

import numpy as np

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["LapseAssumption"]


class LapseAssumption(PolarisBaseModel):
    """
    Duration-based voluntary lapse rate assumption.

    Stores annual lapse rates by policy year, with a configurable select period
    after which the ultimate rate applies.

    Implementation is STUBBED. Claude Code must implement per module docstring.
    """

    select_rates: tuple[float, ...]  # annual rates for policy years 1..N
    ultimate_rate: float
    select_period_years: int

    @classmethod
    def from_duration_table(
        cls,
        table: dict[int | str, float],
    ) -> "LapseAssumption":
        """
        Construct from a dict mapping policy year → annual lapse rate.

        Args:
            table: Integer keys for select years plus an "ultimate" key.
                   Example: {1: 0.10, 2: 0.08, 3: 0.06, "ultimate": 0.03}

        Returns:
            LapseAssumption instance.

        TODO: Implement — extract select rates into a tuple, validate all rates
              are in [0, 1], infer select_period_years from max integer key.
        """
        if "ultimate" not in table:
            raise ValueError("Table must contain an 'ultimate' key.")

        ultimate_rate = float(table["ultimate"])

        # Extract integer keys and sort them
        int_keys = sorted(k for k in table if isinstance(k, int))
        if not int_keys:
            raise ValueError("Table must contain at least one integer policy year key.")

        select_rates = tuple(float(table[k]) for k in int_keys)
        select_period_years = max(int_keys)

        # Validate all rates in [0, 1]
        all_rates = [*list(select_rates), ultimate_rate]
        for rate in all_rates:
            if not (0.0 <= rate <= 1.0):
                raise ValueError(f"Lapse rate {rate} outside [0, 1].")

        return cls(
            select_rates=select_rates,
            ultimate_rate=ultimate_rate,
            select_period_years=select_period_years,
        )

    @classmethod
    def load(
        cls,
        path: Path,
        data_dir: Path | None = None,
    ) -> Self:
        """
        Load a lapse assumption from a CSV file.

        The CSV must have columns ``policy_year`` and ``rate``. The last
        row's rate is treated as the ultimate rate; all preceding rows
        form the select-period rates.

        Args:
            path: Path to the CSV file, or just a filename to resolve
                  relative to *data_dir*.
            data_dir: Optional base directory. When *path* is relative,
                      it is resolved against ``data_dir / lapse_tables/``.

        Returns:
            A validated LapseAssumption instance.

        Raises:
            FileNotFoundError: CSV not found.
            PolarisValidationError: Table fails validation.
        """
        from polaris_re.utils.table_io import load_lapse_csv

        resolved = Path(path)
        if not resolved.is_absolute() and data_dir is not None:
            resolved = data_dir / "lapse_tables" / path

        if not resolved.exists():
            raise FileNotFoundError(f"Lapse table CSV not found: {resolved}")

        table_array = load_lapse_csv(resolved)

        n_years = len(table_array.rates)
        if n_years < 1:
            raise PolarisValidationError("Lapse table must have at least one rate row.")

        # All rates except the last form select rates; last is ultimate
        if n_years == 1:
            select_rates: tuple[float, ...] = ()
            ultimate_rate = float(table_array.rates[0])
            select_period_years = 0
        else:
            select_rates = tuple(float(r) for r in table_array.rates[:-1])
            ultimate_rate = float(table_array.rates[-1])
            select_period_years = n_years - 1

        return cls(
            select_rates=select_rates,
            ultimate_rate=ultimate_rate,
            select_period_years=select_period_years,
        )

    def get_lapse_vector(self, durations_months: np.ndarray) -> np.ndarray:
        """
        Return monthly lapse rates for a vector of policies.

        Args:
            durations_months: Duration in force (months), shape (N,), dtype int32.

        Returns:
            Monthly lapse rates, shape (N,), dtype float64.
            Conversion: w_monthly = 1 - (1 - w_annual)^(1/12)

        TODO: Implement — convert months to policy years, look up select or
              ultimate annual rate, convert to monthly.
        """
        # Convert months to policy years (1-based: months 0-11 → year 1)
        policy_years = durations_months // 12 + 1

        # Build a lookup array: select_rates for years 1..N, then ultimate
        # Index 0 = year 1, ..., index N-1 = year N, index N = ultimate
        rate_lookup = np.array([*list(self.select_rates), self.ultimate_rate], dtype=np.float64)

        # Map policy years to lookup indices, capping at select_period_years
        # Year 1 → index 0, ..., year N → index N-1, year > N → index N (ultimate)
        lookup_idx = np.minimum(policy_years - 1, self.select_period_years)
        w_annual = rate_lookup[lookup_idx]

        # Convert annual to monthly: w_monthly = 1 - (1 - w_annual)^(1/12)
        w_monthly = 1.0 - (1.0 - w_annual) ** (1.0 / 12.0)

        return w_monthly
