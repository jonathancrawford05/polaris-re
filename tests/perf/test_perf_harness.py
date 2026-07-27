"""End-to-end tests for the perf harness (``analytics/perf_harness.py``).

The load-bearing assertion is **reproducibility of the deterministic metrics**:
running the probe twice on the same fixed block must yield byte-identical
structural counts + output fingerprint (the property a CI gate relies on), and a
MiB-peak that is stable to within ±1 MiB. Timing is checked only for its
*arithmetic* invariants (``best_of_k == min(samples)``, sample count, sign) —
never an absolute wall-clock value, which is machine-dependent and informational
only (the maintainer design rule). All fixtures pin ``valuation_date`` (ADR-074).
"""

from datetime import date
from pathlib import Path

import pytest

from polaris_re.analytics.perf_harness import PerfReport, run_perf_probe
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import load_mortality_csv

pytestmark = [pytest.mark.perf, pytest.mark.slow]

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
    return AssumptionSet(mortality=mortality, lapse=lapse, version="perf-harness-test")


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=VAL_DATE,
        projection_horizon_years=10,
        discount_rate=0.05,
    )


class TestRunPerfProbe:
    def test_returns_one_probe_per_hot_path_by_default(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_perf_probe(assumptions, config, n_policies=1_000, k=3)
        assert isinstance(report, PerfReport)
        assert [p.probe for p in report.probes] == ["project"]
        assert report.n_policies == 1_000
        assert report.projection_years == 10

    def test_structural_metrics_are_self_consistent(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_perf_probe(assumptions, config, n_policies=1_000, k=3)
        probe = report.probes[0]
        # 10-year monthly projection => 120 months.
        assert probe.projection_months == 120
        assert probe.n_cells == probe.n_policies * probe.projection_months
        assert probe.n_policies == 1_000

    def test_deterministic_metrics_are_reproducible(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        """The gating property: two runs => identical deterministic metrics.

        Exact structural counts + output fingerprint must match byte-for-byte;
        the coarse MiB-peak must agree to within ±1 MiB. Wall-clock is NOT
        compared — it is informational and machine-dependent.
        """
        a = run_perf_probe(assumptions, config, n_policies=1_000, k=2).probes[0]
        b = run_perf_probe(assumptions, config, n_policies=1_000, k=2).probes[0]

        assert a.deterministic_metrics() == b.deterministic_metrics()
        assert a.output_fingerprint == b.output_fingerprint
        assert abs(a.peak_mib - b.peak_mib) <= 1

    def test_timing_arithmetic_invariants(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        report = run_perf_probe(assumptions, config, n_policies=800, k=4)
        probe = report.probes[0]
        assert probe.k == 4
        assert len(probe.samples_seconds) == 4
        assert all(s >= 0.0 for s in probe.samples_seconds)
        # best_of_k is the minimum sample — the stable estimator.
        assert probe.best_of_k_seconds == min(probe.samples_seconds)

    def test_custom_hot_paths_are_each_probed(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        """Two named hot paths => two probes; identical calls => identical fingerprints."""
        report = run_perf_probe(
            assumptions,
            config,
            n_policies=600,
            k=2,
            hot_paths={
                "project": lambda engine: engine.project(),
                "project_again": lambda engine: engine.project(),
            },
        )
        assert {p.probe for p in report.probes} == {"project", "project_again"}
        by_name = {p.probe: p for p in report.probes}
        # Same computation on the same block => same deterministic fingerprint.
        assert by_name["project"].output_fingerprint == by_name["project_again"].output_fingerprint

    def test_perf_dict_round_trips_and_is_deterministic_first(
        self, assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        import json

        report = run_perf_probe(assumptions, config, n_policies=600, k=2)
        payload = json.loads(report.to_json())
        assert payload["n_policies"] == 600
        probe = payload["probes"][0]
        # Deterministic block precedes the informational timing block.
        assert set(probe["deterministic"]) == {
            "n_policies",
            "projection_months",
            "n_cells",
            "output_fingerprint",
        }
        assert "best_of_k_seconds" in probe["timing"]
