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
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Self

import numpy as np
from pydantic import ConfigDict, Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.interpolation import constant_force_interpolate_rates
from polaris_re.utils.table_io import MortalityTableArray, load_mortality_csv

__all__ = ["MortalityTable", "MortalityTableSource"]


class MortalityTableSource(StrEnum):
    """Supported base mortality table sources."""

    CIA_2014 = "CIA_2014"
    SOA_VBT_2015 = "SOA_VBT_2015"
    CSO_2001 = "CSO_2001"


# Table source configuration: maps source → metadata needed for loading.
_SOURCE_CONFIG: dict[MortalityTableSource, dict[str, object]] = {
    MortalityTableSource.CIA_2014: {
        "table_name": "CIA 2014 Individual Life",
        "select_period": 20,  # CIA2014 uses 20-year select period
        "min_age": 18,
        "max_age": None,  # auto-detect from CSV
        "smoker_distinct": True,
        "file_pattern": "cia_2014_{sex}_{smoker}.csv",
    },
    MortalityTableSource.SOA_VBT_2015: {
        "table_name": "SOA VBT 2015",
        "select_period": 25,
        "min_age": 18,
        "max_age": None,  # auto-detect from CSV
        "smoker_distinct": True,
        "file_pattern": "soa_vbt_2015_{sex}_{smoker}.csv",
    },
    MortalityTableSource.CSO_2001: {
        "table_name": "2001 CSO",
        "select_period": 0,
        "min_age": 0,
        "max_age": None,  # auto-detect from CSV
        "smoker_distinct": False,
        "file_pattern": "cso_2001_{sex}.csv",
    },
}


def _sex_label(sex: Sex) -> str:
    """Map Sex enum to file naming convention."""
    return "male" if sex == Sex.MALE else "female"


def _smoker_label(smoker: SmokerStatus) -> str:
    """Map SmokerStatus enum to file naming convention."""
    mapping = {
        SmokerStatus.SMOKER: "smoker",
        SmokerStatus.NON_SMOKER: "ns",
        SmokerStatus.UNKNOWN: "aggregate",
    }
    return mapping[smoker]


class MortalityTable(PolarisBaseModel):
    """
    A loaded and validated actuarial mortality table.

    Stores base q_x rates by age, sex, smoker status, and select duration.
    Provides vectorized lookup methods for use in projection engines.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    source: MortalityTableSource
    table_name: str
    min_age: int
    max_age: int
    select_period_years: int
    has_smoker_distinct_rates: bool
    tables: dict[str, MortalityTableArray] = Field(
        description="Loaded table arrays keyed by 'sex_smoker' string.",
        exclude=True,
    )

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
        """
        if data_dir is None:
            env_dir = os.environ.get("POLARIS_DATA_DIR")
            if env_dir is None:
                raise PolarisValidationError("data_dir not specified and POLARIS_DATA_DIR not set.")
            data_dir = Path(env_dir) / "mortality_tables"

        config = _SOURCE_CONFIG[source]
        select_period = int(str(config["select_period"]))
        min_age = int(str(config["min_age"]))
        raw_max_age = config["max_age"]
        max_age_param: int | None = int(str(raw_max_age)) if raw_max_age is not None else None
        smoker_distinct = bool(config["smoker_distinct"])
        file_pattern = str(config["file_pattern"])
        table_name = str(config["table_name"])

        tables: dict[str, MortalityTableArray] = {}

        sexes = [Sex.MALE, Sex.FEMALE]
        if smoker_distinct:
            smoker_statuses = [SmokerStatus.SMOKER, SmokerStatus.NON_SMOKER]
        else:
            smoker_statuses = [SmokerStatus.UNKNOWN]

        for sex in sexes:
            for smoker in smoker_statuses:
                filename = file_pattern.format(
                    sex=_sex_label(sex),
                    smoker=_smoker_label(smoker),
                )
                filepath = data_dir / filename
                table_array = load_mortality_csv(
                    filepath,
                    select_period=select_period,
                    min_age=min_age,
                    max_age=max_age_param,
                )
                key = f"{sex.value}_{smoker.value}"
                tables[key] = table_array

        # Derive actual max_age from the loaded tables
        actual_max_age = max(t.max_age for t in tables.values())

        return cls(
            source=source,
            table_name=table_name,
            min_age=min_age,
            max_age=actual_max_age,
            select_period_years=select_period,
            has_smoker_distinct_rates=smoker_distinct,
            tables=tables,
        )

    @classmethod
    def from_table_array(
        cls,
        source: MortalityTableSource,
        table_name: str,
        table_array: MortalityTableArray,
        sex: Sex,
        smoker_status: SmokerStatus,
    ) -> Self:
        """
        Construct a MortalityTable from a single pre-loaded MortalityTableArray.

        Useful for testing with synthetic fixtures.
        """
        key = f"{sex.value}_{smoker_status.value}"
        return cls(
            source=source,
            table_name=table_name,
            min_age=table_array.min_age,
            max_age=table_array.max_age,
            select_period_years=table_array.select_period,
            has_smoker_distinct_rates=(smoker_status != SmokerStatus.UNKNOWN),
            tables={key: table_array},
        )

    def _get_table_key(self, sex: Sex, smoker_status: SmokerStatus) -> str:
        """Resolve the table lookup key for a given sex and smoker status."""
        key = f"{sex.value}_{smoker_status.value}"
        if key in self.tables:
            return key
        # Fall back to aggregate if smoker-specific table not available
        agg_key = f"{sex.value}_{SmokerStatus.UNKNOWN.value}"
        if agg_key in self.tables:
            return agg_key
        raise PolarisValidationError(
            f"No table loaded for sex={sex.value}, smoker={smoker_status.value}. "
            f"Available keys: {list(self.tables.keys())}"
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
        """
        key = self._get_table_key(sex, smoker_status)
        table = self.tables[key]

        # Convert durations from months to years for select-period lookup
        durations_years = durations // 12

        # Get annual rates via vectorized lookup
        q_annual = table.get_rate_vector(ages, durations_years)

        # Convert annual to monthly using constant force assumption
        q_monthly = constant_force_interpolate_rates(q_annual, fraction=1.0 / 12.0)

        return q_monthly

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
