"""
LapseAssumption — duration-based lapse (voluntary termination) rates.

Lapse rates represent the probability that a policyholder voluntarily
terminates their policy in a given policy year. They follow a
"select and ultimate" pattern — high in early durations, declining to a
stable ultimate rate after the select period.

Implementation Notes for Claude Code:
--------------------------------------
- Lapse rates are per policy year (annual), not per month.
  Monthly: w_monthly = 1 - (1 - w_annual)^(1/12)
- Duration measured in policy years from issue (duration_inforce / 12).
- Select period for lapses is typically 10–20 years.
- Lapse rates typically 5–15% in year 1, declining to 2–5% ultimate.
- For reinsurance: lower lapses = more exposure = more adverse for YRT reinsurer.

TODO (Phase 1, Milestone 1.2):
- Implement `from_duration_table` factory method
- Implement `get_lapse_vector` (vectorized over policies)
- Unit tests verifying select and ultimate logic with closed-form values
"""

import numpy as np

from polaris_re.core.base import PolarisBaseModel

__all__ = ["LapseAssumption"]


class LapseAssumption(PolarisBaseModel):
    """
    Duration-based voluntary lapse rate assumption.

    Stores annual lapse rates by policy year, with a configurable select period
    after which the ultimate rate applies.

    Implementation is STUBBED. Claude Code must implement per module docstring.
    """

    select_rates: tuple[float, ...]   # annual rates for policy years 1..N
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
        raise NotImplementedError("LapseAssumption.from_duration_table() not yet implemented.")

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
        raise NotImplementedError("LapseAssumption.get_lapse_vector() not yet implemented.")
