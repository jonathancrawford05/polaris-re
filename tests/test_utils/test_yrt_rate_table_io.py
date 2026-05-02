"""Tests for the dashboard upload helpers (Slice 4b-2 / ADR-055).

Covers:

* ``load_yrt_rate_csv_from_buffer`` — bytes-based variant of
  ``load_yrt_rate_csv``. Same validation contract.
* ``parse_yrt_rate_filename`` — filename-suffix → (Sex, SmokerStatus) parser.
* ``parse_uploaded_yrt_rate_table`` — multi-file packer for the dashboard
  uploader.
"""

from pathlib import Path

import numpy as np
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.table_io import (
    load_yrt_rate_csv,
    load_yrt_rate_csv_from_buffer,
)
from polaris_re.utils.yrt_rate_table_io import (
    find_uncovered_cohorts,
    parse_uploaded_yrt_rate_table,
    parse_yrt_rate_filename,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yrt_rate_tables"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ----------------------------------------------------------------------- #
# load_yrt_rate_csv_from_buffer                                            #
# ----------------------------------------------------------------------- #


class TestLoadYRTRateCSVFromBuffer:
    """Buffer-based loader matches the path-based loader byte-for-byte."""

    def test_round_trip_matches_path_loader(self):
        path = FIXTURES / "synthetic_male_ns.csv"
        from_path = load_yrt_rate_csv(path, select_period=3)
        from_buffer = load_yrt_rate_csv_from_buffer(
            content=path.read_bytes(),
            source_name=path.name,
            select_period=3,
        )
        assert from_path.min_age == from_buffer.min_age
        assert from_path.max_age == from_buffer.max_age
        assert from_path.select_period == from_buffer.select_period
        np.testing.assert_array_equal(from_path.rates, from_buffer.rates)

    def test_invalid_csv_bytes_raises_validation_error(self):
        with pytest.raises(PolarisValidationError, match="Failed to parse"):
            load_yrt_rate_csv_from_buffer(
                content=b"not,a,valid\ncsv\xff\xff body",
                source_name="bogus.csv",
                select_period=3,
            )

    def test_missing_age_column_raises(self):
        bad = b"foo,dur_1,dur_2,dur_3,ultimate\n25,0.1,0.2,0.3,0.4\n"
        with pytest.raises(PolarisValidationError, match="First column must be 'age'"):
            load_yrt_rate_csv_from_buffer(
                content=bad,
                source_name="bad.csv",
                select_period=3,
            )

    def test_missing_dur_column_raises(self):
        bad = b"age,dur_1,dur_2,ultimate\n25,0.1,0.2,0.4\n26,0.1,0.2,0.4\n"
        with pytest.raises(PolarisValidationError, match=r"missing expected columns \['dur_3'\]"):
            load_yrt_rate_csv_from_buffer(
                content=bad,
                source_name="bad.csv",
                select_period=3,
            )

    def test_negative_rate_rejected_via_array_init(self):
        bad = b"age,dur_1,dur_2,dur_3,ultimate\n25,-0.1,0.2,0.3,0.4\n"
        with pytest.raises(PolarisValidationError, match="non-negative"):
            load_yrt_rate_csv_from_buffer(
                content=bad,
                source_name="bad.csv",
                select_period=3,
            )

    def test_select_period_zero_rejected(self):
        with pytest.raises(PolarisValidationError, match="select_period must be >= 1"):
            load_yrt_rate_csv_from_buffer(
                content=b"age,ultimate\n25,1.0\n",
                source_name="bad.csv",
                select_period=0,
            )


# ----------------------------------------------------------------------- #
# parse_yrt_rate_filename                                                  #
# ----------------------------------------------------------------------- #


class TestParseYRTRateFilename:
    """Filename suffix decoding for the dashboard uploader."""

    @pytest.mark.parametrize(
        ("name", "expected_sex", "expected_smoker"),
        [
            ("synthetic_male_ns.csv", Sex.MALE, SmokerStatus.NON_SMOKER),
            ("synthetic_male_smoker.csv", Sex.MALE, SmokerStatus.SMOKER),
            ("synthetic_female_ns.csv", Sex.FEMALE, SmokerStatus.NON_SMOKER),
            ("synthetic_female_smoker.csv", Sex.FEMALE, SmokerStatus.SMOKER),
            ("yrt_male_unknown.csv", Sex.MALE, SmokerStatus.UNKNOWN),
            ("YRT_FEMALE_NS.CSV", Sex.FEMALE, SmokerStatus.NON_SMOKER),
        ],
    )
    def test_recognised_suffix(self, name, expected_sex, expected_smoker):
        sex, smoker = parse_yrt_rate_filename(name)
        assert sex is expected_sex
        assert smoker is expected_smoker

    def test_strips_directory_components(self):
        sex, smoker = parse_yrt_rate_filename("/tmp/upload/yrt_female_smoker.csv")
        assert sex is Sex.FEMALE
        assert smoker is SmokerStatus.SMOKER

    def test_handles_windows_separators(self):
        sex, smoker = parse_yrt_rate_filename("C:\\uploads\\yrt_male_ns.csv")
        assert sex is Sex.MALE
        assert smoker is SmokerStatus.NON_SMOKER

    def test_extra_underscores_in_label_ok(self):
        # Multi-token label; only the last two tokens are inspected.
        sex, smoker = parse_yrt_rate_filename("my_table_v2_male_ns.csv")
        assert sex is Sex.MALE
        assert smoker is SmokerStatus.NON_SMOKER

    def test_non_csv_extension_rejected(self):
        with pytest.raises(PolarisValidationError, match=r"must be a \.csv file"):
            parse_yrt_rate_filename("synthetic_male_ns.tsv")

    def test_unrecognised_sex_rejected(self):
        with pytest.raises(PolarisValidationError, match="cannot extract"):
            parse_yrt_rate_filename("synthetic_other_ns.csv")

    def test_unrecognised_smoker_rejected(self):
        with pytest.raises(PolarisValidationError, match="cannot extract"):
            parse_yrt_rate_filename("synthetic_male_other.csv")

    def test_too_few_tokens_rejected(self):
        with pytest.raises(PolarisValidationError, match="end with"):
            parse_yrt_rate_filename("foo.csv")


# ----------------------------------------------------------------------- #
# parse_uploaded_yrt_rate_table                                            #
# ----------------------------------------------------------------------- #


class TestParseUploadedYRTRateTable:
    """End-to-end multi-file upload → ``YRTRateTable``."""

    def test_smoker_distinct_four_files(self):
        uploads = [
            ("synthetic_male_ns.csv", _fixture_bytes("synthetic_male_ns.csv")),
            ("synthetic_male_smoker.csv", _fixture_bytes("synthetic_male_smoker.csv")),
            ("synthetic_female_ns.csv", _fixture_bytes("synthetic_female_ns.csv")),
            ("synthetic_female_smoker.csv", _fixture_bytes("synthetic_female_smoker.csv")),
        ]
        table = parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="dashboard-upload",
            select_period=3,
        )
        assert table.table_name == "dashboard-upload"
        assert set(table.arrays.keys()) == {"M_NS", "M_S", "F_NS", "F_S"}
        assert table.has_smoker_distinct_rates is True
        assert table.select_period_years == 3
        # CSV-loaded arrays carry no provenance mask (ADR-054).
        for arr in table.arrays.values():
            assert arr.solved_mask is None
            assert arr.is_fully_solved is True

    def test_round_trip_lookup_matches_directory_loader(self):
        from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

        uploads = [
            ("synthetic_male_ns.csv", _fixture_bytes("synthetic_male_ns.csv")),
            ("synthetic_male_smoker.csv", _fixture_bytes("synthetic_male_smoker.csv")),
            ("synthetic_female_ns.csv", _fixture_bytes("synthetic_female_ns.csv")),
            ("synthetic_female_smoker.csv", _fixture_bytes("synthetic_female_smoker.csv")),
        ]
        from_uploads = parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="synthetic",
            select_period=3,
        )
        from_dir = YRTRateTable.load(
            directory=FIXTURES,
            select_period=3,
            table_name="synthetic",
            label="synthetic",
            smoker_distinct=True,
        )
        ages = np.array([25, 26, 27, 28], dtype=np.int32)
        durations = np.array([0, 1, 2, 5], dtype=np.int32)
        for sex in (Sex.MALE, Sex.FEMALE):
            for smoker in (SmokerStatus.NON_SMOKER, SmokerStatus.SMOKER):
                got = from_uploads.get_rate_vector(ages, sex, smoker, durations)
                expected = from_dir.get_rate_vector(ages, sex, smoker, durations)
                np.testing.assert_array_equal(got, expected)

    def test_aggregate_only_two_files_ok(self, tmp_path):
        # Build a minimal aggregate (UNKNOWN smoker) pair on the fly.
        agg = b"age,dur_1,dur_2,dur_3,ultimate\n25,1.0,1.1,1.2,2.0\n26,1.1,1.2,1.3,2.2\n"
        uploads = [
            ("yrt_male_unknown.csv", agg),
            ("yrt_female_unknown.csv", agg),
        ]
        table = parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="agg",
            select_period=3,
        )
        assert set(table.arrays.keys()) == {"M_U", "F_U"}
        assert table.has_smoker_distinct_rates is False

    def test_empty_uploads_rejected(self):
        with pytest.raises(PolarisValidationError, match="at least one"):
            parse_uploaded_yrt_rate_table(
                uploads=[],
                table_name="x",
                select_period=3,
            )

    def test_duplicate_cohort_rejected(self):
        agg = b"age,dur_1,dur_2,dur_3,ultimate\n25,1.0,1.1,1.2,2.0\n26,1.1,1.2,1.3,2.2\n"
        uploads = [
            ("table1_male_ns.csv", agg),
            ("table2_male_ns.csv", agg),
        ]
        with pytest.raises(PolarisValidationError, match="Duplicate YRT rate cohort"):
            parse_uploaded_yrt_rate_table(
                uploads=uploads,
                table_name="x",
                select_period=3,
            )

    def test_inconsistent_age_range_rejected(self):
        # Two uploads with different age coverage — YRTRateTable validators
        # should reject because select_period must be uniform.
        ns_short = b"age,dur_1,dur_2,dur_3,ultimate\n25,1.0,1.1,1.2,2.0\n26,1.1,1.2,1.3,2.2\n"
        sm_long = (
            b"age,dur_1,dur_2,dur_3,ultimate\n"
            b"25,1.0,1.1,1.2,2.0\n26,1.1,1.2,1.3,2.2\n27,1.2,1.3,1.4,2.4\n"
        )
        uploads = [
            ("yrt_male_ns.csv", ns_short),
            ("yrt_male_smoker.csv", sm_long),
        ]
        with pytest.raises(PolarisValidationError, match="age range"):
            parse_uploaded_yrt_rate_table(
                uploads=uploads,
                table_name="x",
                select_period=3,
            )

    def test_per_file_validation_error_propagates(self):
        bad = b"age,dur_1,dur_2,ultimate\n25,0.1,0.2,0.4\n26,0.1,0.2,0.4\n"
        uploads = [
            ("yrt_male_ns.csv", bad),
        ]
        # `dur_3` is missing — error message names the offending file.
        with pytest.raises(PolarisValidationError, match=r"yrt_male_ns\.csv"):
            parse_uploaded_yrt_rate_table(
                uploads=uploads,
                table_name="x",
                select_period=3,
            )


# ----------------------------------------------------------------------- #
# find_uncovered_cohorts                                                   #
# ----------------------------------------------------------------------- #


class TestFindUncoveredCohorts:
    """Cross-check inforce (sex, smoker) cohorts against a YRT rate table."""

    @staticmethod
    def _block(*specs: tuple[Sex, SmokerStatus]):
        from datetime import date

        from polaris_re.core.inforce import InforceBlock
        from polaris_re.core.policy import Policy, ProductType

        val_date = date(2026, 1, 1)
        policies = [
            Policy(
                policy_id=f"P{i:03d}",
                issue_age=40,
                attained_age=40,
                sex=sex,
                smoker_status=smoker,
                underwriting_class="STANDARD",
                face_amount=500_000.0,
                annual_premium=1200.0,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=None,
                issue_date=val_date,
                valuation_date=val_date,
            )
            for i, (sex, smoker) in enumerate(specs)
        ]
        return InforceBlock(policies=policies)

    def _smoker_distinct_table(self) -> "object":
        uploads = [
            (name, (FIXTURES / name).read_bytes())
            for name in (
                "synthetic_male_ns.csv",
                "synthetic_male_smoker.csv",
                "synthetic_female_ns.csv",
                "synthetic_female_smoker.csv",
            )
        ]
        return parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="synthetic",
            select_period=3,
        )

    def _aggregate_table(self) -> "object":
        agg = b"age,dur_1,dur_2,dur_3,ultimate\n25,1.0,1.1,1.2,2.0\n26,1.1,1.2,1.3,2.2\n"
        uploads = [
            ("yrt_male_unknown.csv", agg),
            ("yrt_female_unknown.csv", agg),
        ]
        return parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="agg",
            select_period=3,
        )

    def test_full_coverage_returns_empty(self):
        table = self._smoker_distinct_table()
        block = self._block(
            (Sex.MALE, SmokerStatus.NON_SMOKER),
            (Sex.FEMALE, SmokerStatus.SMOKER),
        )
        assert find_uncovered_cohorts(table, block) == []

    def test_missing_cohort_reported(self):
        # Smoker-distinct table covers only male cohorts.
        male_only_uploads = [
            ("synthetic_male_ns.csv", _fixture_bytes("synthetic_male_ns.csv")),
            ("synthetic_male_smoker.csv", _fixture_bytes("synthetic_male_smoker.csv")),
        ]
        table = parse_uploaded_yrt_rate_table(
            uploads=male_only_uploads,
            table_name="male-only",
            select_period=3,
        )
        block = self._block(
            (Sex.MALE, SmokerStatus.NON_SMOKER),
            (Sex.FEMALE, SmokerStatus.NON_SMOKER),
            (Sex.FEMALE, SmokerStatus.SMOKER),
        )
        missing = find_uncovered_cohorts(table, block)
        assert missing == ["F_NS", "F_S"]

    def test_aggregate_table_covers_smoker_distinct_block(self):
        # Aggregate (UNKNOWN-smoker) tables resolve any smoker via the
        # built-in fallback in YRTRateTable._resolve_key.
        table = self._aggregate_table()
        block = self._block(
            (Sex.MALE, SmokerStatus.NON_SMOKER),
            (Sex.MALE, SmokerStatus.SMOKER),
            (Sex.FEMALE, SmokerStatus.NON_SMOKER),
        )
        assert find_uncovered_cohorts(table, block) == []

    def test_smoker_distinct_table_does_not_cover_unknown_smoker_block(self):
        # Reverse direction: distinct M_NS/M_S do NOT collapse to M_U,
        # so an UNKNOWN-smoker policy on a smoker-distinct table is
        # uncovered.
        table = self._smoker_distinct_table()
        block = self._block((Sex.MALE, SmokerStatus.UNKNOWN))
        missing = find_uncovered_cohorts(table, block)
        assert missing == ["M_U"]

    def test_empty_block_returns_empty(self):
        table = self._smoker_distinct_table()

        class _Empty:
            def __init__(self) -> None:
                self.policies: list = []

        assert find_uncovered_cohorts(table, _Empty()) == []

    def test_none_inforce_returns_empty(self):
        table = self._smoker_distinct_table()
        # The dashboard call site passes whatever is in session_state —
        # protect against the no-inforce-yet case.
        assert find_uncovered_cohorts(table, object()) == []

    def test_dedupes_repeated_cohorts(self):
        # 1000 policies with the same (sex, smoker) — the result must
        # be a single key, and the inner _resolve_key call is short-
        # circuited via the seen set (perf invariant).
        male_only_uploads = [
            ("synthetic_male_ns.csv", _fixture_bytes("synthetic_male_ns.csv")),
            ("synthetic_male_smoker.csv", _fixture_bytes("synthetic_male_smoker.csv")),
        ]
        table = parse_uploaded_yrt_rate_table(
            uploads=male_only_uploads,
            table_name="male-only",
            select_period=3,
        )
        block = self._block(
            *([(Sex.FEMALE, SmokerStatus.NON_SMOKER)] * 1000),
        )
        assert find_uncovered_cohorts(table, block) == ["F_NS"]
