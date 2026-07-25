"""Tests for the scale-benchmark harness (analytics/scale_benchmark.py).

These verify the harness's *arithmetic* (closed-form throughput relationships)
and its *scaling invariant* (near-linear time growth — the vectorization
property the README claims), not absolute wall-clock times, which are
machine-dependent. All fixtures pin ``valuation_date`` explicitly (ADR-074).
"""

from datetime import date
from pathlib import Path

import pytest

from polaris_re.analytics.scale_benchmark import (
    ScaleBenchmarkReport,
    build_homogeneous_block,
    run_scale_benchmark,
)
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VAL_DATE = date(2025, 1, 1)


@pytest.fixture()
def assumptions() -> AssumptionSet:
    """Data-independent assumptions built from the committed synthetic fixture."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="scale-bench-test")


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=VAL_DATE,
        projection_horizon_years=5,
        discount_rate=0.05,
    )


class TestBuildHomogeneousBlock:
    def test_deterministic_for_same_seed(self) -> None:
        a = build_homogeneous_block(50, valuation_date=VAL_DATE, seed=7)
        b = build_homogeneous_block(50, valuation_date=VAL_DATE, seed=7)
        assert [p.policy_id for p in a.policies] == [p.policy_id for p in b.policies]
        assert [p.issue_age for p in a.policies] == [p.issue_age for p in b.policies]

    def test_different_seed_changes_ages(self) -> None:
        a = build_homogeneous_block(200, valuation_date=VAL_DATE, seed=1)
        b = build_homogeneous_block(200, valuation_date=VAL_DATE, seed=2)
        assert [p.issue_age for p in a.policies] != [p.issue_age for p in b.policies]

    def test_valuation_date_is_pinned_not_today(self) -> None:
        pinned = date(2019, 6, 30)
        block = build_homogeneous_block(10, valuation_date=pinned)
        assert all(p.valuation_date == pinned for p in block.policies)
        assert all(p.issue_date == pinned for p in block.policies)

    def test_ages_within_requested_bounds(self) -> None:
        block = build_homogeneous_block(
            300, valuation_date=VAL_DATE, issue_age_min=40, issue_age_max=50
        )
        assert all(40 <= p.issue_age < 50 for p in block.policies)
        # Freshly issued: attained age equals issue age.
        assert all(p.attained_age == p.issue_age for p in block.policies)

    def test_rejects_non_positive_size(self) -> None:
        with pytest.raises(PolarisValidationError):
            build_homogeneous_block(0, valuation_date=VAL_DATE)

    def test_rejects_inverted_age_bounds(self) -> None:
        with pytest.raises(PolarisValidationError):
            build_homogeneous_block(10, valuation_date=VAL_DATE, issue_age_min=55, issue_age_max=45)


class TestRunScaleBenchmark:
    def test_row_throughput_is_closed_form(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        """policies_per_second and cell_updates_per_second are exactly the
        harness's own ratios — the defining relationship, checked closed-form."""
        report = run_scale_benchmark([400], assumptions, config)
        (row,) = report.rows
        assert row.n_policies == 400
        # Monthly projection over a 5-year horizon -> 60 steps.
        assert row.projection_months == config.projection_horizon_years * 12
        assert row.projection_seconds > 0.0
        assert row.policies_per_second == pytest.approx(row.n_policies / row.projection_seconds)
        assert row.cell_updates_per_second == pytest.approx(
            row.n_policies * row.projection_months / row.projection_seconds
        )

    def test_report_records_config(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_scale_benchmark([200], assumptions, config, engine_label="TermLife")
        assert report.engine_label == "TermLife"
        assert report.projection_years == 5
        assert report.discount_rate == pytest.approx(0.05)

    def test_one_row_per_size_ascending(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_scale_benchmark([100, 300, 600], assumptions, config)
        assert [r.n_policies for r in report.rows] == [100, 300, 600]

    def test_memory_measurement_toggle(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        off = run_scale_benchmark([200], assumptions, config, measure_memory=False)
        assert off.rows[0].peak_rss_mb is None
        on = run_scale_benchmark([200], assumptions, config, measure_memory=True)
        assert on.rows[0].peak_rss_mb is not None
        assert on.rows[0].peak_rss_mb > 0.0

    def test_custom_block_builder_is_used(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        calls: list[int] = []

        def builder(n: int):
            calls.append(n)
            return build_homogeneous_block(n, valuation_date=VAL_DATE)

        run_scale_benchmark([150], assumptions, config, block_builder=builder)
        assert calls == [150]

    def test_to_markdown_has_header_and_row_per_size(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_scale_benchmark([100, 500], assumptions, config)
        md = report.to_markdown()
        assert "Policies / sec" in md
        assert "Cell-updates / sec" in md
        # A rendered data row for each size (comma-grouped thousands).
        assert "| 100 |" in md
        assert "| 500 |" in md

    def test_rejects_empty_sizes(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        with pytest.raises(PolarisValidationError):
            run_scale_benchmark([], assumptions, config)

    def test_rejects_non_positive_size(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        with pytest.raises(PolarisValidationError):
            run_scale_benchmark([100, 0], assumptions, config)

    def test_rejects_non_ascending_sizes(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        with pytest.raises(PolarisValidationError):
            run_scale_benchmark([500, 100], assumptions, config)
        with pytest.raises(PolarisValidationError):
            run_scale_benchmark([100, 100], assumptions, config)

    def test_report_is_pydantic_and_roundtrips(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_scale_benchmark([200], assumptions, config)
        assert isinstance(report, ScaleBenchmarkReport)
        restored = ScaleBenchmarkReport.model_validate(report.model_dump())
        assert restored.rows[0].n_policies == 200

    @pytest.mark.slow
    def test_scaling_is_near_linear(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        """A vectorized (O(N)) engine keeps per-policy time roughly flat: a 4x
        larger block must not take anywhere near 4^2x longer. Generous 6x bound
        (vs the ideal 4x) tolerates CI noise while still catching an accidental
        Python loop over policies that would make projection O(N^2)."""
        small, large = 2_000, 8_000
        report = run_scale_benchmark([small, large], assumptions, config)
        t_small = report.rows[0].projection_seconds
        t_large = report.rows[1].projection_seconds
        assert t_small > 0.0 and t_large > 0.0
        # 4x the work should be well under 6x the time for a linear engine.
        assert t_large < 6.0 * t_small
