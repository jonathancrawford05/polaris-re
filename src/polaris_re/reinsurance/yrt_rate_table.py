"""
YRTRateTable — tabular YRT rates per $1,000 NAR by attained age x duration.

A production YRT treaty quotes premium rates from a table indexed by the
ceded life's (attained_age, sex, smoker_status, duration_in_years). The
existing `YRTTreaty.flat_yrt_rate_per_1000` is a single-cell flat rate
that approximates the schedule with one number — adequate for MVP-era
parity studies but meaningfully understates reinsurer cost as the block
ages, because real YRT rates rise annually with attained age.

This module is the standalone data model. Slice 2 wires it into
`YRTTreaty.apply()`; Slice 3 wires CLI / API / dashboard surfaces. The
storage and lookup contract here is intentionally narrow so those later
slices are mechanical translations.

Storage Contract
----------------
Rates are stored as 2-D float64 arrays of shape
`(n_ages, select_period + 1)`, one array per (sex, smoker) combination,
keyed by the same `f"{sex.value}_{smoker.value}"` string used by
`MortalityTable`. The lookup contract is:

    rate_per_1000 = table.get_rate_vector(ages, sex, smoker, durations_years)

`durations_years` is the policy duration in years from issue (0-indexed
internally so that a brand-new policy queries column 0). Values beyond
`select_period` clamp to the `ultimate` column. Annual quoted rates are
returned; the consumer (Slice 2) is responsible for converting to a
monthly decrement (`/12`) and the per-dollar form (`/1000`).

Why a separate Array class
--------------------------
`MortalityTableArray` validates rates in `[0, 1]` because it stores
mortality probabilities. YRT rates are dollars per $1,000 face per year;
they are routinely > 1 (e.g. $25-$50/$1,000 at advanced ages). Reusing
`MortalityTableArray` would require relaxing its probability invariant,
which is a stronger guarantee we do not want to weaken. A small parallel
array class keeps both invariants intact.
"""

from typing import Self

import numpy as np
from pydantic import ConfigDict, Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus

__all__ = ["YRTRateTable", "YRTRateTableArray"]


class YRTRateTableArray:
    """
    Loaded YRT rate table as a 2D numpy array for fast vectorized lookups.

    Shape: (n_ages, select_period + 1)
      Columns 0..N-1: select-period rates (duration years 0..N-1)
      Column N:       ultimate rates (duration_years >= select_period)
    Indexed by: [age - min_age, min(duration_years, select_period)]

    Rates are quoted as annual dollars per $1,000 NAR. No upper bound is
    enforced (industry rates can exceed $50/$1,000 at advanced ages).
    Negative rates raise `PolarisValidationError`.
    """

    def __init__(
        self,
        rates: np.ndarray,
        min_age: int,
        max_age: int,
        select_period: int,
    ) -> None:
        # Defensive copy + dtype promotion in one step. Storing the caller's
        # array by reference would let post-construction mutation silently
        # corrupt the validated rates.
        rates = np.asarray(rates, dtype=np.float64).copy()
        if rates.ndim != 2:
            raise PolarisValidationError(f"YRT rate array must be 2D, got shape {rates.shape}.")
        expected_n_ages = max_age - min_age + 1
        if rates.shape[0] != expected_n_ages:
            raise PolarisValidationError(
                f"YRT rate array row count {rates.shape[0]} does not match "
                f"age range [{min_age}, {max_age}] (expected {expected_n_ages})."
            )
        if rates.shape[1] != select_period + 1:
            raise PolarisValidationError(
                f"YRT rate array column count {rates.shape[1]} does not match "
                f"select_period + 1 = {select_period + 1}."
            )
        if np.any(rates < 0):
            raise PolarisValidationError("YRT rates must be non-negative (rates are $/1000/year).")
        if not np.all(np.isfinite(rates)):
            raise PolarisValidationError("YRT rates must be finite (no NaN/Inf).")

        self.rates = rates
        self.min_age = int(min_age)
        self.max_age = int(max_age)
        self.select_period = int(select_period)

    def get_rate(self, age: int, duration_years: int) -> float:
        """Single rate lookup. duration_years is capped at select_period."""
        if not (self.min_age <= age <= self.max_age):
            raise PolarisValidationError(
                f"Age {age} outside YRT rate table range [{self.min_age}, {self.max_age}]."
            )
        if duration_years < 0:
            raise PolarisValidationError(
                f"duration_years must be non-negative, got {duration_years}."
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
            ages:            Attained ages, shape (N,). Coerced to int64
                             internally; callers can pass int32 / int64.
            durations_years: Policy years from issue, shape (N,). Coerced to
                             int64 internally; callers can pass int32 / int64.

        Returns:
            Annual YRT rates per $1,000 NAR, shape (N,), dtype float64.

        Raises:
            PolarisValidationError: If shapes mismatch, any age is outside
                [min_age, max_age], or any duration is negative.
        """
        if ages.shape != durations_years.shape:
            raise PolarisValidationError(
                f"ages shape {ages.shape} must match durations shape {durations_years.shape}."
            )
        # Coerce to int64 once at the boundary — callers commonly pass int32
        # vectors from `InforceBlock.attained_age_vec`. Float inputs would be
        # truncated by numpy fancy indexing, so reject them explicitly.
        if not np.issubdtype(ages.dtype, np.integer):
            raise PolarisValidationError(f"ages must be an integer array, got dtype {ages.dtype}.")
        if not np.issubdtype(durations_years.dtype, np.integer):
            raise PolarisValidationError(
                f"durations_years must be an integer array, got dtype {durations_years.dtype}."
            )
        ages_i = ages.astype(np.int64, copy=False)
        durations_i = durations_years.astype(np.int64, copy=False)
        age_idx = ages_i - self.min_age
        if np.any(age_idx < 0) or np.any(age_idx >= self.rates.shape[0]):
            raise PolarisValidationError(
                f"One or more ages outside YRT rate table range [{self.min_age}, {self.max_age}]."
            )
        if np.any(durations_i < 0):
            raise PolarisValidationError("durations_years must all be non-negative.")
        dur_cols = np.minimum(durations_i, self.select_period)
        return self.rates[age_idx, dur_cols]


class YRTRateTable(PolarisBaseModel):
    """
    Tabular YRT rate schedule keyed by (sex, smoker) → 2D rate array.

    Rates are annual dollars per $1,000 NAR, indexed by attained age and
    duration in years from issue. Use `from_arrays(...)` for in-memory
    construction or `get_rate_vector(...)` for vectorized lookup against a
    cohort. CSV file loading is deferred to Slice 3.

    Note:
        Do not branch on ``has_smoker_distinct_rates`` to decide lookup
        behaviour — ``_resolve_key`` handles the smoker → UNKNOWN
        fallback internally. The flag is display / metadata only and
        is preserved purely so callers can label or audit the loaded
        table. Slice 3's CSV ingest and API surface should also avoid
        switching on it.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    table_name: str = Field(description="Human-readable table identifier.")
    min_age: int = Field(ge=0, le=120, description="Minimum supported attained age.")
    max_age: int = Field(ge=0, le=120, description="Maximum supported attained age.")
    select_period_years: int = Field(
        ge=0,
        le=50,
        description="Number of select-period columns in each rate array.",
    )
    has_smoker_distinct_rates: bool = Field(
        description=(
            "Whether (sex, smoker) keys distinguish smoker status. "
            "INFORMATIONAL ONLY — `_resolve_key` handles the smoker-fallback "
            "logic independently, so consumers must not branch on this flag "
            "to decide lookup behaviour. Display / metadata only."
        )
    )
    arrays: dict[str, YRTRateTableArray] = Field(
        description="Loaded rate arrays keyed by 'sex_smoker' string.",
        exclude=True,
    )

    @model_validator(mode="after")
    def _validate_age_range(self) -> Self:
        if self.max_age < self.min_age:
            raise PolarisValidationError(
                f"max_age ({self.max_age}) must be >= min_age ({self.min_age})."
            )
        return self

    @model_validator(mode="after")
    def _validate_arrays_consistent(self) -> Self:
        if not self.arrays:
            raise PolarisValidationError("YRTRateTable.arrays must contain at least one entry.")
        for key, arr in self.arrays.items():
            if arr.min_age != self.min_age or arr.max_age != self.max_age:
                raise PolarisValidationError(
                    f"YRTRateTableArray[{key}] age range "
                    f"[{arr.min_age}, {arr.max_age}] does not match "
                    f"table range [{self.min_age}, {self.max_age}]."
                )
            if arr.select_period != self.select_period_years:
                raise PolarisValidationError(
                    f"YRTRateTableArray[{key}] select_period {arr.select_period} "
                    f"does not match table select_period_years "
                    f"{self.select_period_years}."
                )
        return self

    @classmethod
    def from_arrays(
        cls,
        table_name: str,
        arrays: dict[tuple[Sex, SmokerStatus], YRTRateTableArray],
    ) -> Self:
        """
        Construct a YRTRateTable from a dict of `YRTRateTableArray`s
        keyed by `(Sex, SmokerStatus)` tuples.

        At least one (sex, smoker) entry is required. All arrays must
        share the same `min_age`, `max_age`, and `select_period`.

        Metadata (`min_age`, `max_age`, `select_period_years`) is derived
        from the first entry in `arrays`; `_validate_arrays_consistent`
        then raises `PolarisValidationError` if any other entry disagrees.
        """
        if not arrays:
            raise PolarisValidationError(
                "YRTRateTable.from_arrays requires at least one (sex, smoker) entry."
            )
        first_arr = next(iter(arrays.values()))
        min_age = first_arr.min_age
        max_age = first_arr.max_age
        select_period = first_arr.select_period

        smoker_distinct = any(smoker != SmokerStatus.UNKNOWN for (_sex, smoker) in arrays)

        keyed: dict[str, YRTRateTableArray] = {}
        for (sex, smoker), arr in arrays.items():
            keyed[f"{sex.value}_{smoker.value}"] = arr

        return cls(
            table_name=table_name,
            min_age=min_age,
            max_age=max_age,
            select_period_years=select_period,
            has_smoker_distinct_rates=smoker_distinct,
            arrays=keyed,
        )

    def _resolve_key(self, sex: Sex, smoker_status: SmokerStatus) -> str:
        """
        Resolve the (sex, smoker) key for a lookup, falling back to
        aggregate (UNKNOWN smoker) if a smoker-specific table is absent.
        """
        key = f"{sex.value}_{smoker_status.value}"
        if key in self.arrays:
            return key
        agg_key = f"{sex.value}_{SmokerStatus.UNKNOWN.value}"
        if agg_key in self.arrays:
            return agg_key
        raise PolarisValidationError(
            f"No YRT rate array for sex={sex.value}, smoker={smoker_status.value}. "
            f"Available keys: {sorted(self.arrays.keys())}"
        )

    def get_rate_vector(
        self,
        ages: np.ndarray,
        sex: Sex,
        smoker_status: SmokerStatus,
        durations_years: np.ndarray,
    ) -> np.ndarray:
        """
        Return annual YRT rates per $1,000 NAR for a vector of policies.

        Args:
            ages:            Attained ages, shape (N,), dtype int32.
            sex:             Single sex value (split block by sex before calling).
            smoker_status:   Single smoker status (split block before calling).
            durations_years: Policy years from issue, shape (N,), dtype int32.

        Returns:
            Annual YRT rates per $1,000 NAR, shape (N,), dtype float64.
            Consumers convert to monthly per-dollar form via `/12 / 1000`.
        """
        key = self._resolve_key(sex, smoker_status)
        return self.arrays[key].get_rate_vector(ages, durations_years)

    def get_rate_scalar(
        self,
        age: int,
        sex: Sex,
        smoker_status: SmokerStatus,
        duration_years: int,
    ) -> float:
        """Convenience: single annual rate per $1,000 NAR. Delegates to vector."""
        ages = np.array([age], dtype=np.int32)
        durations = np.array([duration_years], dtype=np.int32)
        return float(self.get_rate_vector(ages, sex, smoker_status, durations)[0])
