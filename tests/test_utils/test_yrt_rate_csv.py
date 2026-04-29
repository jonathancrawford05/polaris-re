"""Tests for YRT rate CSV loading and ``YRTRateTable.load`` (ADR-052)."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray
from polaris_re.utils.table_io import load_yrt_rate_csv

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yrt_rate_tables"


class TestLoadYRTRateCSV:
    """Tests for ``load_yrt_rate_csv`` schema parsing and validation."""

    def test_load_synthetic_male_ns(self) -> None:
        """Loads the synthetic male / non-smoker fixture into an array."""
        arr = load_yrt_rate_csv(FIXTURES / "synthetic_male_ns.csv", select_period=3)
        assert isinstance(arr, YRTRateTableArray)
        assert arr.min_age == 25
        assert arr.max_age == 35
        assert arr.select_period == 3
        assert arr.rates.shape == (11, 4)  # 11 ages, 3 select + 1 ultimate

    def test_known_rate_values(self) -> None:
        """Spot-check that loaded rates match the CSV cells.

        The fixture sets age=30 / dur_2 = 0.80 and age=30 / ultimate = 1.50.
        The user-facing dur_k = (k - 1)-th internal column, so dur_2 maps
        to ``get_rate(age=30, duration_years=1)`` and ultimate is what
        any duration >= select_period returns.
        """
        arr = load_yrt_rate_csv(FIXTURES / "synthetic_male_ns.csv", select_period=3)
        np.testing.assert_allclose(arr.get_rate(age=30, duration_years=1), 0.80)
        np.testing.assert_allclose(arr.get_rate(age=30, duration_years=10), 1.50)
        np.testing.assert_allclose(arr.get_rate(age=25, duration_years=0), 0.50)

    def test_smoker_rates_higher_than_ns(self) -> None:
        """Economic invariant: smokers cost more than non-smokers."""
        ns = load_yrt_rate_csv(FIXTURES / "synthetic_male_ns.csv", select_period=3)
        sm = load_yrt_rate_csv(FIXTURES / "synthetic_male_smoker.csv", select_period=3)
        assert np.all(sm.rates > ns.rates)

    def test_male_rates_higher_than_female(self) -> None:
        """Economic invariant: male rates > female rates at same (age, dur)."""
        m = load_yrt_rate_csv(FIXTURES / "synthetic_male_ns.csv", select_period=3)
        f = load_yrt_rate_csv(FIXTURES / "synthetic_female_ns.csv", select_period=3)
        assert np.all(m.rates > f.rates)

    def test_age_filter_via_min_max(self, tmp_path: Path) -> None:
        """Explicit min_age / max_age filters the loaded rows."""
        arr = load_yrt_rate_csv(
            FIXTURES / "synthetic_male_ns.csv",
            select_period=3,
            min_age=28,
            max_age=32,
        )
        assert arr.min_age == 28
        assert arr.max_age == 32
        assert arr.rates.shape == (5, 4)
        np.testing.assert_allclose(arr.get_rate(age=28, duration_years=0), 0.65)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Missing file path raises ``FileNotFoundError``."""
        with pytest.raises(FileNotFoundError):
            load_yrt_rate_csv(tmp_path / "missing.csv", select_period=3)

    def test_zero_select_period_raises(self) -> None:
        """``select_period=0`` is not supported (YRT tables always have a
        select-and-ultimate structure)."""
        with pytest.raises(PolarisValidationError, match="select_period"):
            load_yrt_rate_csv(FIXTURES / "synthetic_male_ns.csv", select_period=0)

    def test_missing_age_column_raises(self, tmp_path: Path) -> None:
        """First column must be ``age``."""
        bad = tmp_path / "no_age_col.csv"
        bad.write_text("year,dur_1,dur_2,dur_3,ultimate\n25,0.5,0.6,0.7,1.0\n")
        with pytest.raises(PolarisValidationError, match="age"):
            load_yrt_rate_csv(bad, select_period=3)

    def test_missing_duration_column_raises(self, tmp_path: Path) -> None:
        """``dur_2`` missing → validation error names the missing column."""
        bad = tmp_path / "missing_dur.csv"
        bad.write_text("age,dur_1,dur_3,ultimate\n25,0.5,0.7,1.0\n26,0.55,0.75,1.05\n")
        with pytest.raises(PolarisValidationError, match="dur_2"):
            load_yrt_rate_csv(bad, select_period=3)

    def test_missing_ultimate_column_raises(self, tmp_path: Path) -> None:
        """The ``ultimate`` column is mandatory."""
        bad = tmp_path / "no_ultimate.csv"
        bad.write_text("age,dur_1,dur_2,dur_3\n25,0.5,0.6,0.7\n26,0.55,0.65,0.75\n")
        with pytest.raises(PolarisValidationError, match="ultimate"):
            load_yrt_rate_csv(bad, select_period=3)

    def test_negative_rate_raises(self, tmp_path: Path) -> None:
        """Negative rates are rejected by ``YRTRateTableArray.__init__``."""
        bad = tmp_path / "negative.csv"
        bad.write_text(
            "age,dur_1,dur_2,dur_3,ultimate\n25,-0.10,0.55,0.60,1.00\n26,0.55,0.60,0.65,1.10\n"
        )
        with pytest.raises(PolarisValidationError, match="non-negative"):
            load_yrt_rate_csv(bad, select_period=3, min_age=25, max_age=26)

    def test_age_gap_raises(self, tmp_path: Path) -> None:
        """Non-contiguous ages raise validation error."""
        bad = tmp_path / "age_gap.csv"
        bad.write_text(
            "age,dur_1,dur_2,dur_3,ultimate\n25,0.5,0.6,0.7,1.0\n27,0.55,0.65,0.75,1.05\n"
        )
        with pytest.raises(PolarisValidationError, match="contiguous"):
            load_yrt_rate_csv(bad, select_period=3)

    def test_min_age_below_csv_raises(self) -> None:
        """Requested ``min_age`` below the CSV's actual range raises."""
        with pytest.raises(PolarisValidationError, match="age"):
            load_yrt_rate_csv(
                FIXTURES / "synthetic_male_ns.csv",
                select_period=3,
                min_age=20,
            )

    def test_max_age_above_csv_raises(self) -> None:
        """Requested ``max_age`` above the CSV's actual range raises."""
        with pytest.raises(PolarisValidationError, match="age"):
            load_yrt_rate_csv(
                FIXTURES / "synthetic_male_ns.csv",
                select_period=3,
                max_age=40,
            )

    def test_rates_above_unit_interval_accepted(self, tmp_path: Path) -> None:
        """Rates >> 1 are valid (YRT rates are $/$1,000, not probabilities).

        This is the headline difference vs ``load_mortality_csv``.
        """
        big = tmp_path / "advanced_age.csv"
        big.write_text(
            "age,dur_1,dur_2,dur_3,ultimate\n85,40.0,42.0,44.0,75.0\n86,45.0,47.0,49.0,82.0\n"
        )
        arr = load_yrt_rate_csv(big, select_period=3)
        np.testing.assert_allclose(arr.get_rate(age=85, duration_years=10), 75.0)


class TestYRTRateTableLoad:
    """Tests for ``YRTRateTable.load`` directory loader."""

    def test_load_smoker_distinct_directory(self) -> None:
        """Loads four CSVs (M/F x NS/SM) from the fixtures directory."""
        table = YRTRateTable.load(
            directory=FIXTURES,
            select_period=3,
            table_name="synthetic",
            smoker_distinct=True,
        )
        assert isinstance(table, YRTRateTable)
        assert table.table_name == "synthetic"
        assert table.has_smoker_distinct_rates is True
        assert table.min_age == 25
        assert table.max_age == 35
        assert table.select_period_years == 3
        assert set(table.arrays.keys()) == {"M_S", "M_NS", "F_S", "F_NS"}

    def test_lookup_smoker_distinct(self) -> None:
        """Loaded table reproduces the fixture rates per sex/smoker."""
        table = YRTRateTable.load(
            directory=FIXTURES,
            select_period=3,
            table_name="synthetic",
            smoker_distinct=True,
        )
        # Male NS, age 30, duration_years 0 → fixture dur_1 = 0.75.
        np.testing.assert_allclose(
            table.get_rate_scalar(
                age=30, sex=Sex.MALE, smoker_status=SmokerStatus.NON_SMOKER, duration_years=0
            ),
            0.75,
        )
        # Female smoker, age 35, ultimate = 4.20.
        np.testing.assert_allclose(
            table.get_rate_scalar(
                age=35, sex=Sex.FEMALE, smoker_status=SmokerStatus.SMOKER, duration_years=99
            ),
            4.20,
        )

    def test_load_aggregate_only(self, tmp_path: Path) -> None:
        """``smoker_distinct=False`` expects ``_unknown`` files per sex."""
        # Build a tiny aggregate fixture in tmp_path.
        for sex_label in ("male", "female"):
            (tmp_path / f"aggblock_{sex_label}_unknown.csv").write_text(
                "age,dur_1,dur_2,ultimate\n30,0.80,0.85,1.50\n31,0.85,0.90,1.60\n"
            )
        table = YRTRateTable.load(
            directory=tmp_path,
            select_period=2,
            table_name="aggblock",
            smoker_distinct=False,
        )
        assert table.has_smoker_distinct_rates is False
        assert set(table.arrays.keys()) == {"M_U", "F_U"}
        np.testing.assert_allclose(
            table.get_rate_scalar(
                age=30, sex=Sex.MALE, smoker_status=SmokerStatus.UNKNOWN, duration_years=0
            ),
            0.80,
        )

    def test_smoker_fallback_after_load(self, tmp_path: Path) -> None:
        """Aggregate-loaded table answers smoker-specific lookups via fallback."""
        for sex_label in ("male", "female"):
            (tmp_path / f"agg_{sex_label}_unknown.csv").write_text(
                "age,dur_1,dur_2,ultimate\n30,1.00,1.10,2.00\n31,1.10,1.20,2.10\n"
            )
        table = YRTRateTable.load(
            directory=tmp_path,
            select_period=2,
            table_name="agg",
            smoker_distinct=False,
        )
        rate = table.get_rate_scalar(
            age=30, sex=Sex.MALE, smoker_status=SmokerStatus.SMOKER, duration_years=0
        )
        np.testing.assert_allclose(rate, 1.00)

    def test_label_override(self, tmp_path: Path) -> None:
        """``label`` overrides the filename slug derived from ``table_name``."""
        for sex_label in ("male", "female"):
            for smoker_label in ("ns", "smoker"):
                (tmp_path / f"customlbl_{sex_label}_{smoker_label}.csv").write_text(
                    "age,dur_1,dur_2,ultimate\n30,0.5,0.6,1.0\n31,0.55,0.65,1.05\n"
                )
        table = YRTRateTable.load(
            directory=tmp_path,
            select_period=2,
            table_name="Pretty Display Name",
            label="customlbl",
            smoker_distinct=True,
        )
        assert table.table_name == "Pretty Display Name"

    def test_default_label_slug_handles_spaces(self, tmp_path: Path) -> None:
        """When ``label`` is omitted, the table_name is slugified."""
        # ``YRT Rate 2026`` → ``yrt_rate_2026``.
        for sex_label in ("male", "female"):
            for smoker_label in ("ns", "smoker"):
                (tmp_path / f"yrt_rate_2026_{sex_label}_{smoker_label}.csv").write_text(
                    "age,dur_1,dur_2,ultimate\n30,0.5,0.6,1.0\n31,0.55,0.65,1.05\n"
                )
        table = YRTRateTable.load(
            directory=tmp_path,
            select_period=2,
            table_name="YRT Rate 2026",
            smoker_distinct=True,
        )
        assert table.table_name == "YRT Rate 2026"

    def test_missing_csv_raises(self, tmp_path: Path) -> None:
        """A missing per-cohort CSV bubbles ``FileNotFoundError``."""
        # Only male files; female files are missing.
        for smoker_label in ("ns", "smoker"):
            (tmp_path / f"part_male_{smoker_label}.csv").write_text(
                "age,dur_1,dur_2,ultimate\n30,0.5,0.6,1.0\n31,0.55,0.65,1.05\n"
            )
        with pytest.raises(FileNotFoundError):
            YRTRateTable.load(
                directory=tmp_path,
                select_period=2,
                table_name="part",
                smoker_distinct=True,
            )

    def test_inconsistent_age_range_raises(self, tmp_path: Path) -> None:
        """All loaded arrays must share a common age range."""
        (tmp_path / "mix_male_ns.csv").write_text(
            "age,dur_1,dur_2,ultimate\n30,0.5,0.6,1.0\n31,0.55,0.65,1.05\n"
        )
        (tmp_path / "mix_male_smoker.csv").write_text(
            "age,dur_1,dur_2,ultimate\n30,0.6,0.7,1.2\n31,0.65,0.75,1.25\n"
        )
        # Female files cover a different age range.
        (tmp_path / "mix_female_ns.csv").write_text(
            "age,dur_1,dur_2,ultimate\n40,0.5,0.6,1.0\n41,0.55,0.65,1.05\n"
        )
        (tmp_path / "mix_female_smoker.csv").write_text(
            "age,dur_1,dur_2,ultimate\n40,0.6,0.7,1.2\n41,0.65,0.75,1.25\n"
        )
        with pytest.raises(PolarisValidationError, match="age range"):
            YRTRateTable.load(
                directory=tmp_path,
                select_period=2,
                table_name="mix",
                smoker_distinct=True,
            )

    def test_round_trip_through_treaty(self) -> None:
        """A loaded table can be fed into ``YRTTreaty.apply`` via the
        existing tabular path with no errors (smoke test of the data
        pipeline end-to-end)."""
        from polaris_re.assumptions.assumption_set import AssumptionSet
        from polaris_re.assumptions.lapse import LapseAssumption
        from polaris_re.assumptions.mortality import (
            MortalityTable,
            MortalityTableSource,
        )
        from polaris_re.core.inforce import InforceBlock
        from polaris_re.core.policy import Policy, ProductType
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.products.term_life import TermLife
        from polaris_re.reinsurance.yrt import YRTTreaty
        from polaris_re.utils.table_io import load_mortality_csv

        # Synthetic mortality + lapse for projection inputs.
        mort_array = load_mortality_csv(
            FIXTURES.parent / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        mortality = MortalityTable.from_table_array(
            source=MortalityTableSource.SOA_VBT_2015,
            table_name="synthetic",
            table_array=mort_array,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.UNKNOWN,
        )
        lapse = LapseAssumption.from_duration_table({1: 0.10, 2: 0.08, 3: 0.06, "ultimate": 0.05})
        assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="csv-test")
        from datetime import date

        config = ProjectionConfig(
            projection_horizon_years=10,
            discount_rate=0.06,
            valuation_date=date(2026, 1, 1),
        )
        policies = [
            Policy(
                policy_id=f"P{i}",
                issue_age=30,
                attained_age=30,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=500_000.0,
                annual_premium=600.0,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2026, 1, 1),
                valuation_date=date(2026, 1, 1),
            )
            for i in range(5)
        ]
        inforce = InforceBlock(policies=policies)
        engine = TermLife(inforce=inforce, assumptions=assumptions, config=config)
        gross = engine.project()

        rate_table = YRTRateTable.load(
            directory=FIXTURES,
            select_period=3,
            table_name="synthetic",
            smoker_distinct=True,
        )
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=inforce.total_face_amount(),
            yrt_rate_table=rate_table,
        )
        net, ceded = treaty.apply(gross, inforce=inforce)
        assert ceded.gross_premiums.sum() > 0  # non-trivial ceded premium
        # Net + ceded == gross for premiums (additivity).
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross.gross_premiums,
            rtol=1e-12,
        )


class TestPublicExports:
    """The new symbol must be re-exported from utils.table_io."""

    def test_load_yrt_rate_csv_in_dunder_all(self) -> None:
        from polaris_re.utils import table_io as module

        assert "load_yrt_rate_csv" in module.__all__

    def test_yrt_rate_csv_round_trip_via_polars(self, tmp_path: Path) -> None:
        """Sanity: writing a polars DataFrame in the schema and reading
        it back produces the same rates (defensive against polars
        regressions in column type inference)."""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "dur_1": [0.5, 0.55, 0.60],
                "dur_2": [0.6, 0.65, 0.70],
                "ultimate": [1.0, 1.05, 1.10],
            }
        )
        path = tmp_path / "round.csv"
        df.write_csv(path)
        arr = load_yrt_rate_csv(path, select_period=2)
        np.testing.assert_allclose(arr.get_rate(age=31, duration_years=0), 0.55)
