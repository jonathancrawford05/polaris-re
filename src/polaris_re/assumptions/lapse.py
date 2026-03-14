"""
LapseAssumption — duration-based lapse (voluntary termination) rates.

Lapse rates represent the probability that a policyholder voluntarily
terminates their policy in a given policy year. They typically follow a
"select and ultimate" pattern — high in early durations, then declining
to a stable ultimate rate.

Implementation Notes for Claude Code:
--------------------------------------
- Lapse rates are per policy year (annual), not per month.
  Monthly lapse rate: w_monthly = 1 - (1 - w_annual)^(1/12)
- Duration is measured in policy years from issue (duration_inforce / 12).
- The select period for lapses is typically 10–20 years.
  After the select period, the "ultimate" lapse rate applies.
- Lapse rates are typically 5–15% in year 1, declining to 2–5% ultimate.
  For reinsurance purposes, lapse assumptions are often more conservative
  (lower lapses = more exposure = more adverse for reinsurer on YRT).

TODO (Phase 1, Milestone 1.2):
- Implement `from_duration_table` factory method
- Implement `get_lapse_vector` (vectorized)
- Add unit tests verifying select and ultimate logic
"""

from __future__ import annotations

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

    # Duration-keyed annual lapse rates: {policy_year: rate}
    # e.g. {1: 0.10, 2: 0.08, 3: 0.06, ..., "ultimate": 0.03}
    # Stored as two arrays for performance
    select_rates: tuple[float, ...]  # rates for years 1..N
    ultimate_rate: float
    select_period_years: int

    @classmethod
    def from_duration_table(
        cls,
        table: dict[int | str, float],
    ) -> "LapseAssumption":
        """
        Construct from a dictionary mapping policy year → annual lapse rate.

        Args:
            table: Dict with integer keys for select years and "ultimate" key.
                   Example: {1: 0.10, 2: 0.08, 3: 0.06, "ultimate": 0.03}

        Returns:
            LapseAssumption instance.
        """
        raise NotImplementedError("LapseAssumption.from_duration_table() is not yet implemented.")

    def get_lapse_vector(self, durations_months: np.ndarray) -> np.ndarray:
        """
        Return monthly lapse rates for a vector of policies.

        Args:
            durations_months: Duration in force in months, shape (N,), dtype int32.

        Returns:
            Monthly lapse rates, shape (N,), dtype float64.
        """
        raise NotImplementedError("LapseAssumption.get_lapse_vector() is not yet implemented.")
