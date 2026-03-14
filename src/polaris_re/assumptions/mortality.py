"""
MortalityTable — loads, validates, and queries actuarial mortality tables.

Supports CIA 2014, SOA VBT 2015 (select & ultimate), and 2001 CSO.
All public query methods operate on numpy arrays (vectorized over policies).

Implementation Notes for Claude Code:
--------------------------------------
- Core method: `get_qx_vector(ages, sex, smoker, durations)` → shape (N,).
- Tables loaded from CSV in $POLARIS_DATA_DIR/mortality_tables/.
- Select-and-ultimate tables: 2D lookup (attained_age, duration_in_select).
  Duration beyond select period → use ultimate column.
- Rates must lie in [0, 1] after loading.
- CIA 2014: sex-distinct, smoker-distinct, select period = 25 years.
- SOA VBT 2015: sex-distinct, smoker-distinct, select period = 25 years.
- 2001 CSO: sex-distinct, aggregate (no smoker split), ultimate only.

TODO (Phase 1, Milestone 1.2):
- Implement CSV loader for each table source via load_mortality_csv in utils/table_io.py
- Implement `get_qx_vector` with select/ultimate logic
- Implement `get_qx_scalar` convenience wrapper
- Add age range validation on construction
- Add unit tests with closed-form verification
"""

from enum import Enum
from pathlib import Path
from typing import Self

import numpy as np

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus

__all__ = ["MortalityTable", "MortalityTableSource"]


class MortalityTableSource(str, Enum):
    """Supported base mortality table sources."""
    CIA_2014 = "CIA_2014"
    SOA_VBT_2015 = "SOA_VBT_2015"
    CSO_2001 = "CSO_2001"


class MortalityTable(PolarisBaseModel):
    """
    A loaded and validated actuarial mortality table.

    Stores base q_x rates by age, sex, smoker status, and select duration.
    Provides vectorized lookup methods for use in projection engines.

    Implementation is STUBBED. Claude Code must implement per module docstring
    and ARCHITECTURE.md §3.
    """

    source: MortalityTableSource
    table_name: str
    min_age: int
    max_age: int
    select_period_years: int
    has_smoker_distinct_rates: bool

    @classmethod
    def load(
        cls,
        source: MortalityTableSource,
        data_dir: Path | None = None,
    ) -> Self:
        """
        Load a mortality table from CSV.

        Args:
            source: Which standard table to load.
            data_dir: Directory containing mortality table CSVs.
                      Defaults to $POLARIS_DATA_DIR/mortality_tables/.

        Returns:
            A validated MortalityTable instance.

        Raises:
            PolarisValidationError: If the file is missing or contains invalid rates.

        TODO: Implement via utils.table_io.load_mortality_csv.
        """
        raise NotImplementedError(
            "MortalityTable.load() not yet implemented. "
            "See module docstring and ARCHITECTURE.md §3."
        )

    def get_qx_vector(
        self,
        ages: np.ndarray,
        sex: Sex,
        smoker_status: SmokerStatus,
        durations: np.ndarray,
    ) -> np.ndarray:
        """
        Return monthly mortality rates for a vector of policies.

        Args:
            ages:          Attained ages, shape (N,), dtype int32.
            sex:           Single sex value (split block by sex before calling).
            smoker_status: Single smoker status (split block before calling).
            durations:     Duration in select period (months), shape (N,), dtype int32.

        Returns:
            Monthly q_x rates, shape (N,), dtype float64.
            q_monthly = 1 - (1 - q_annual)^(1/12)

        Raises:
            PolarisValidationError: If any age is outside [min_age, max_age].

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "MortalityTable.get_qx_vector() not yet implemented. "
            "See ARCHITECTURE.md §3 for vectorization spec."
        )

    def get_qx_scalar(
        self,
        age: int,
        sex: Sex,
        smoker_status: SmokerStatus,
        duration_months: int,
    ) -> float:
        """Convenience: single monthly mortality rate. Delegates to get_qx_vector."""
        ages = np.array([age], dtype=np.int32)
        durations = np.array([duration_months], dtype=np.int32)
        return float(self.get_qx_vector(ages, sex, smoker_status, durations)[0])
