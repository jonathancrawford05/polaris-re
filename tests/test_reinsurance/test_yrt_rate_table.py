"""
Tests for YRTRateTable and YRTRateTableArray (Slice 1 — standalone data model).

These tests verify the lookup contract that Slice 2 will rely on when
wiring tabular YRT rates into `YRTTreaty.apply()`. Closed-form lookup
values are baked into a small synthetic rate grid so future regressions
are obvious.
"""

import numpy as np
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.reinsurance import YRTRateTable, YRTRateTableArray


def _build_array(
    min_age: int = 30,
    max_age: int = 50,
    select_period: int = 5,
    base_rate: float = 1.0,
    age_slope: float = 0.5,
    duration_slope: float = 0.1,
) -> YRTRateTableArray:
    """
    Build a synthetic YRT rate array.

    rates[i, j] = base_rate + age_slope * i + duration_slope * j
    where i is the age offset from min_age and j is the duration column.
    """
    n_ages = max_age - min_age + 1
    n_cols = select_period + 1
    rates = np.zeros((n_ages, n_cols), dtype=np.float64)
    for i in range(n_ages):
        for j in range(n_cols):
            rates[i, j] = base_rate + age_slope * i + duration_slope * j
    return YRTRateTableArray(
        rates=rates,
        min_age=min_age,
        max_age=max_age,
        select_period=select_period,
    )


class TestYRTRateTableArrayConstruction:
    """Validation behaviour at the storage-class boundary."""

    def test_construct_with_float64_rates_succeeds(self) -> None:
        arr = _build_array()
        assert arr.rates.dtype == np.float64
        assert arr.rates.shape == (21, 6)
        assert arr.min_age == 30
        assert arr.max_age == 50
        assert arr.select_period == 5

    def test_int_rates_are_promoted_to_float64(self) -> None:
        rates = np.ones((3, 2), dtype=np.int32)
        arr = YRTRateTableArray(rates=rates, min_age=40, max_age=42, select_period=1)
        assert arr.rates.dtype == np.float64

    def test_non_2d_rates_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="must be 2D"):
            YRTRateTableArray(
                rates=np.array([1.0, 2.0]),
                min_age=40,
                max_age=41,
                select_period=0,
            )

    def test_age_range_mismatch_raises(self) -> None:
        rates = np.ones((5, 3), dtype=np.float64)  # 5 ages claimed
        with pytest.raises(PolarisValidationError, match="row count"):
            YRTRateTableArray(rates=rates, min_age=30, max_age=39, select_period=2)

    def test_select_period_mismatch_raises(self) -> None:
        rates = np.ones((3, 2), dtype=np.float64)  # claims select_period+1 = 2
        with pytest.raises(PolarisValidationError, match="column count"):
            YRTRateTableArray(rates=rates, min_age=40, max_age=42, select_period=5)

    def test_negative_rate_raises(self) -> None:
        rates = np.ones((3, 2), dtype=np.float64)
        rates[1, 0] = -0.01
        with pytest.raises(PolarisValidationError, match="non-negative"):
            YRTRateTableArray(rates=rates, min_age=40, max_age=42, select_period=1)

    def test_nan_rate_raises(self) -> None:
        rates = np.ones((3, 2), dtype=np.float64)
        rates[0, 0] = np.nan
        with pytest.raises(PolarisValidationError, match="finite"):
            YRTRateTableArray(rates=rates, min_age=40, max_age=42, select_period=1)

    def test_large_rate_allowed(self) -> None:
        # YRT rates routinely exceed $50/$1000 at advanced ages — must NOT
        # be capped at 1 (unlike mortality probabilities).
        rates = np.full((3, 2), 75.0, dtype=np.float64)
        arr = YRTRateTableArray(rates=rates, min_age=85, max_age=87, select_period=1)
        assert arr.get_rate(85, 0) == 75.0


class TestYRTRateTableArrayLookup:
    """Closed-form scalar and vector lookup."""

    def test_scalar_lookup_known_cell(self) -> None:
        # rates[i, j] = 1.0 + 0.5 * i + 0.1 * j
        arr = _build_array()
        # age=40 → i=10; duration=2 → j=2 → rate = 1.0 + 5.0 + 0.2 = 6.2
        assert arr.get_rate(40, 2) == pytest.approx(6.2)

    def test_duration_beyond_select_period_uses_ultimate(self) -> None:
        # select_period=5 → ultimate column index is 5
        arr = _build_array()
        ultimate_at_age_30 = 1.0 + 0.5 * 0 + 0.1 * 5  # = 1.5
        # Any duration_years >= 5 must clamp to the ultimate column
        assert arr.get_rate(30, 5) == pytest.approx(ultimate_at_age_30)
        assert arr.get_rate(30, 25) == pytest.approx(ultimate_at_age_30)

    def test_scalar_age_below_range_raises(self) -> None:
        arr = _build_array()
        with pytest.raises(PolarisValidationError, match="outside YRT rate table range"):
            arr.get_rate(29, 0)

    def test_scalar_age_above_range_raises(self) -> None:
        arr = _build_array()
        with pytest.raises(PolarisValidationError, match="outside YRT rate table range"):
            arr.get_rate(51, 0)

    def test_negative_duration_raises(self) -> None:
        arr = _build_array()
        with pytest.raises(PolarisValidationError, match="non-negative"):
            arr.get_rate(40, -1)

    def test_vector_lookup_shape_and_dtype(self) -> None:
        arr = _build_array()
        ages = np.array([30, 35, 40, 45, 50], dtype=np.int32)
        durs = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        out = arr.get_rate_vector(ages, durs)
        assert out.shape == (5,)
        assert out.dtype == np.float64

    def test_vector_lookup_values_match_scalar(self) -> None:
        arr = _build_array()
        ages = np.array([30, 35, 40, 45, 50], dtype=np.int32)
        durs = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        out = arr.get_rate_vector(ages, durs)
        expected = np.array([arr.get_rate(int(a), int(d)) for a, d in zip(ages, durs, strict=True)])
        np.testing.assert_allclose(out, expected, rtol=1e-12)

    def test_vector_lookup_clamps_duration_at_select_period(self) -> None:
        arr = _build_array()
        ages = np.array([30, 30, 30], dtype=np.int32)
        durs = np.array([5, 10, 99], dtype=np.int32)
        out = arr.get_rate_vector(ages, durs)
        ultimate = arr.get_rate(30, 5)
        np.testing.assert_allclose(out, np.full(3, ultimate), rtol=1e-12)

    def test_vector_shape_mismatch_raises(self) -> None:
        arr = _build_array()
        ages = np.array([30, 35], dtype=np.int32)
        durs = np.array([0, 1, 2], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="shape"):
            arr.get_rate_vector(ages, durs)

    def test_vector_age_out_of_range_raises(self) -> None:
        arr = _build_array()
        ages = np.array([30, 60], dtype=np.int32)  # 60 > max_age=50
        durs = np.array([0, 0], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="outside"):
            arr.get_rate_vector(ages, durs)

    def test_vector_negative_duration_raises(self) -> None:
        arr = _build_array()
        ages = np.array([30, 35], dtype=np.int32)
        durs = np.array([0, -1], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="non-negative"):
            arr.get_rate_vector(ages, durs)


class TestYRTRateTableConstruction:
    """Pydantic-level construction and validation of `YRTRateTable`."""

    def test_from_arrays_smoker_distinct(self) -> None:
        ms = _build_array(base_rate=2.0)
        mns = _build_array(base_rate=1.0)
        fs = _build_array(base_rate=1.5)
        fns = _build_array(base_rate=0.7)
        table = YRTRateTable.from_arrays(
            table_name="Synthetic Smoker-Distinct",
            arrays={
                (Sex.MALE, SmokerStatus.SMOKER): ms,
                (Sex.MALE, SmokerStatus.NON_SMOKER): mns,
                (Sex.FEMALE, SmokerStatus.SMOKER): fs,
                (Sex.FEMALE, SmokerStatus.NON_SMOKER): fns,
            },
        )
        assert table.table_name == "Synthetic Smoker-Distinct"
        assert table.has_smoker_distinct_rates is True
        assert table.min_age == 30
        assert table.max_age == 50
        assert table.select_period_years == 5
        assert sorted(table.arrays.keys()) == ["F_NS", "F_S", "M_NS", "M_S"]

    def test_from_arrays_aggregate_only(self) -> None:
        m_agg = _build_array()
        f_agg = _build_array(base_rate=1.5)
        table = YRTRateTable.from_arrays(
            table_name="Aggregate",
            arrays={
                (Sex.MALE, SmokerStatus.UNKNOWN): m_agg,
                (Sex.FEMALE, SmokerStatus.UNKNOWN): f_agg,
            },
        )
        assert table.has_smoker_distinct_rates is False
        assert sorted(table.arrays.keys()) == ["F_U", "M_U"]

    def test_from_arrays_empty_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="at least one"):
            YRTRateTable.from_arrays(table_name="Empty", arrays={})

    def test_inconsistent_age_range_across_arrays_raises(self) -> None:
        a = _build_array(min_age=30, max_age=50, select_period=5)
        b = _build_array(min_age=40, max_age=60, select_period=5)
        with pytest.raises(PolarisValidationError, match="age range"):
            YRTRateTable.from_arrays(
                table_name="Inconsistent",
                arrays={
                    (Sex.MALE, SmokerStatus.NON_SMOKER): a,
                    (Sex.FEMALE, SmokerStatus.NON_SMOKER): b,
                },
            )

    def test_inconsistent_select_period_across_arrays_raises(self) -> None:
        a = _build_array(min_age=30, max_age=50, select_period=5)
        b = _build_array(min_age=30, max_age=50, select_period=3)
        with pytest.raises(PolarisValidationError, match="select_period"):
            YRTRateTable.from_arrays(
                table_name="Inconsistent",
                arrays={
                    (Sex.MALE, SmokerStatus.NON_SMOKER): a,
                    (Sex.FEMALE, SmokerStatus.NON_SMOKER): b,
                },
            )

    def test_frozen_after_construction(self) -> None:
        from pydantic import ValidationError

        table = YRTRateTable.from_arrays(
            table_name="Frozen",
            arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): _build_array()},
        )
        with pytest.raises(ValidationError):
            table.table_name = "Mutated"  # type: ignore[misc]


class TestYRTRateTableLookup:
    """Lookup integration through the Pydantic wrapper."""

    @pytest.fixture()
    def smoker_distinct_table(self) -> YRTRateTable:
        return YRTRateTable.from_arrays(
            table_name="Synthetic Smoker-Distinct",
            arrays={
                (Sex.MALE, SmokerStatus.SMOKER): _build_array(base_rate=2.0),
                (Sex.MALE, SmokerStatus.NON_SMOKER): _build_array(base_rate=1.0),
                (Sex.FEMALE, SmokerStatus.SMOKER): _build_array(base_rate=1.5),
                (Sex.FEMALE, SmokerStatus.NON_SMOKER): _build_array(base_rate=0.7),
            },
        )

    def test_scalar_lookup_smoker_lower_than_smoker(
        self, smoker_distinct_table: YRTRateTable
    ) -> None:
        # Hand-verifiable: at age=30, dur=0:
        #   M_S    = 2.0
        #   M_NS   = 1.0
        #   F_S    = 1.5
        #   F_NS   = 0.7
        assert smoker_distinct_table.get_rate_scalar(
            30, Sex.MALE, SmokerStatus.SMOKER, 0
        ) == pytest.approx(2.0)
        assert smoker_distinct_table.get_rate_scalar(
            30, Sex.MALE, SmokerStatus.NON_SMOKER, 0
        ) == pytest.approx(1.0)
        assert smoker_distinct_table.get_rate_scalar(
            30, Sex.FEMALE, SmokerStatus.NON_SMOKER, 0
        ) == pytest.approx(0.7)

    def test_smoker_higher_than_non_smoker(self, smoker_distinct_table: YRTRateTable) -> None:
        # Closed-form economic invariant — smokers cost more than non-smokers
        # at every (age, duration) cell.
        ages = np.arange(30, 51, dtype=np.int32)
        durs = np.zeros_like(ages)
        smoker = smoker_distinct_table.get_rate_vector(ages, Sex.MALE, SmokerStatus.SMOKER, durs)
        nonsmoker = smoker_distinct_table.get_rate_vector(
            ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs
        )
        assert np.all(smoker > nonsmoker)

    def test_vector_lookup_shape_and_dtype(self, smoker_distinct_table: YRTRateTable) -> None:
        ages = np.array([30, 35, 40], dtype=np.int32)
        durs = np.array([0, 2, 4], dtype=np.int32)
        out = smoker_distinct_table.get_rate_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert out.shape == (3,)
        assert out.dtype == np.float64

    def test_smoker_specific_falls_back_to_aggregate_when_absent(self) -> None:
        # If only UNKNOWN-keyed arrays are present, smoker-specific
        # lookups must transparently fall back to the aggregate rate.
        agg = _build_array(base_rate=1.2)
        table = YRTRateTable.from_arrays(
            table_name="Aggregate Fallback",
            arrays={(Sex.MALE, SmokerStatus.UNKNOWN): agg},
        )
        rate_smoker = table.get_rate_scalar(40, Sex.MALE, SmokerStatus.SMOKER, 0)
        rate_nonsmoker = table.get_rate_scalar(40, Sex.MALE, SmokerStatus.NON_SMOKER, 0)
        rate_unknown = table.get_rate_scalar(40, Sex.MALE, SmokerStatus.UNKNOWN, 0)
        assert rate_smoker == rate_nonsmoker == rate_unknown

    def test_missing_sex_raises(self) -> None:
        table = YRTRateTable.from_arrays(
            table_name="Male Only",
            arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): _build_array()},
        )
        ages = np.array([40], dtype=np.int32)
        durs = np.array([0], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="No YRT rate array"):
            table.get_rate_vector(ages, Sex.FEMALE, SmokerStatus.NON_SMOKER, durs)

    def test_age_progression_increases_within_smoker_class(
        self, smoker_distinct_table: YRTRateTable
    ) -> None:
        # Closed-form: synthetic table has age_slope=0.5 — rates rise
        # monotonically with age at any fixed duration.
        ages = np.arange(30, 51, dtype=np.int32)
        durs = np.zeros_like(ages)
        rates = smoker_distinct_table.get_rate_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert np.all(np.diff(rates) > 0)

    def test_duration_progression_within_select_period(
        self, smoker_distinct_table: YRTRateTable
    ) -> None:
        # duration_slope=0.1 — rates rise with duration up to ultimate
        ages = np.full(6, 30, dtype=np.int32)
        durs = np.arange(0, 6, dtype=np.int32)
        rates = smoker_distinct_table.get_rate_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        # Strictly increasing through select period, then equal to ultimate
        assert np.all(np.diff(rates[:-1]) > 0)


class TestPublicExports:
    """The Slice 1 contract for downstream slices is the package export."""

    def test_yrt_rate_table_exported_from_reinsurance(self) -> None:
        from polaris_re.reinsurance import YRTRateTable as Exported

        assert Exported is YRTRateTable

    def test_yrt_rate_table_array_exported_from_reinsurance(self) -> None:
        from polaris_re.reinsurance import YRTRateTableArray as Exported

        assert Exported is YRTRateTableArray
