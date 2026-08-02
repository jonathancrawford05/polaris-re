"""Tests for the per-merge performance history log + creep detection.

The load-bearing behaviour is **creep detection over a committed series**: given
a ``perf/history.jsonl`` of per-merge rows, the earliest window vs the most-recent
window must flag a sustained MiB-peak rise as *structural creep* (the gate signal)
while treating wall-time drift as *advisory only* — the same maintainer design
rule that governs the head-vs-main gate (deterministic metrics gate, raw
wall-time informs). Almost every test is closed-form on synthetic rows (no engine,
fast); one slow test runs the real probe end-to-end (record -> file -> load ->
detect) to pin the JSON round-trip and the report projection. All fixtures pin
dates via explicit commit dates (ADR-074) — never the wall clock.
"""

from datetime import date
from pathlib import Path

import pytest

from polaris_re.analytics.perf_harness import PerfProbe, PerfReport, run_perf_probe
from polaris_re.analytics.perf_history import (
    PerfHistoryRow,
    ProbeHistoryEntry,
    append_history_row,
    detect_creep,
    load_history,
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


def _entry(
    peak_mib: int, seconds: float, *, n_policies: int = 3_000, months: int = 120
) -> ProbeHistoryEntry:
    """A single 'project' probe entry with the given peak MiB and wall time."""
    return ProbeHistoryEntry(
        probe="project",
        n_policies=n_policies,
        projection_months=months,
        n_cells=n_policies * months,
        output_fingerprint="deadbeef",
        peak_mib=peak_mib,
        best_of_k_seconds=seconds,
        k=5,
    )


def _row(
    commit: str,
    peak_mib: int,
    seconds: float,
    *,
    entries: list[ProbeHistoryEntry] | None = None,
    n_policies: int = 3_000,
) -> PerfHistoryRow:
    """A history row pinned to a commit (date fixed to VAL_DATE — ADR-074)."""
    return PerfHistoryRow(
        commit=commit,
        commit_date=f"{VAL_DATE.isoformat()}T00:00:00+00:00",
        engine_label="TermLife",
        projection_years=10,
        discount_rate=0.05,
        n_policies=n_policies,
        probes=entries
        if entries is not None
        else [_entry(peak_mib, seconds, n_policies=n_policies)],
    )


def _flat_series(peak_mib: int, seconds: float, n: int) -> list[PerfHistoryRow]:
    """``n`` identical rows — a stable engine with no creep."""
    return [_row(f"c{i:03d}", peak_mib, seconds) for i in range(n)]


# --------------------------------------------------------------------------- #
# append / load round-trip
# --------------------------------------------------------------------------- #


def test_append_creates_file_and_parent(tmp_path: Path) -> None:
    """The first append materialises perf/history.jsonl and its parent dir."""
    path = tmp_path / "perf" / "history.jsonl"
    assert not path.exists()
    append_history_row(_row("abc123", 67, 0.29), path)
    assert path.exists()
    assert path.read_text(encoding="utf-8").count("\n") == 1  # exactly one line


def test_append_load_roundtrip(tmp_path: Path) -> None:
    """Rows survive an append -> load round-trip byte-for-byte, in append order."""
    path = tmp_path / "history.jsonl"
    r1 = _row("aaa", 67, 0.29)
    r2 = _row("bbb", 68, 0.31)
    append_history_row(r1, path)
    append_history_row(r2, path)
    loaded = load_history(path)
    assert [r.commit for r in loaded] == ["aaa", "bbb"]
    assert loaded[0] == r1
    assert loaded[1] == r2


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    """A never-recorded log is an empty series, not an error."""
    assert load_history(tmp_path / "nope.jsonl") == []


def test_load_skips_blank_lines(tmp_path: Path) -> None:
    """Blank / whitespace-only lines are ignored (trailing newline, hand edits)."""
    path = tmp_path / "history.jsonl"
    append_history_row(_row("aaa", 67, 0.29), path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n   \n")
    append_history_row(_row("bbb", 67, 0.30), path)
    assert [r.commit for r in load_history(path)] == ["aaa", "bbb"]


# --------------------------------------------------------------------------- #
# from_report projection
# --------------------------------------------------------------------------- #


def test_from_report_projects_deterministic_first_fields() -> None:
    """from_report copies the report's per-probe metrics into a compact row."""
    probe = PerfProbe(
        probe="project",
        n_policies=3_000,
        projection_months=120,
        n_cells=360_000,
        output_fingerprint="feedface",
        peak_bytes=70_000_000,
        peak_mib=67,
        best_of_k_seconds=0.29,
        k=5,
        samples_seconds=[0.29, 0.31, 0.33, 0.30, 0.32],
    )
    report = PerfReport(
        engine_label="TermLife",
        projection_years=10,
        discount_rate=0.05,
        n_policies=3_000,
        probes=[probe],
    )
    row = PerfHistoryRow.from_report(
        report, commit="sha123", commit_date="2026-08-02T09:00:00+00:00"
    )
    assert row.commit == "sha123"
    assert row.commit_date == "2026-08-02T09:00:00+00:00"
    assert row.engine_label == "TermLife"
    assert len(row.probes) == 1
    entry = row.probes[0]
    assert entry.probe == "project"
    assert entry.n_cells == 360_000
    assert entry.output_fingerprint == "feedface"
    assert entry.peak_mib == 67
    assert entry.best_of_k_seconds == pytest.approx(0.29)
    # peak_bytes / samples_seconds are dropped from the compact row.
    assert not hasattr(entry, "peak_bytes")


# --------------------------------------------------------------------------- #
# creep detection — the core behaviour
# --------------------------------------------------------------------------- #


def test_insufficient_data_below_two_windows() -> None:
    """A young log (< 2*window rows) yields no verdict, no alert."""
    verdict = detect_creep(_flat_series(67, 0.29, 5), window=3)
    assert verdict.insufficient_data is True
    assert verdict.probe_creeps == []
    assert verdict.has_structural_creep is False


def test_flat_series_no_creep() -> None:
    """A stable engine: zero MiB delta, no structural or wall-time creep."""
    verdict = detect_creep(_flat_series(67, 0.29, 6), window=3)
    assert verdict.insufficient_data is False
    assert len(verdict.probe_creeps) == 1
    creep = verdict.probe_creeps[0]
    assert creep.peak_mib_delta == pytest.approx(0.0)
    assert creep.peak_mib_creep is False
    assert verdict.has_structural_creep is False
    assert verdict.has_wall_time_creep is False


def test_peak_mib_creep_gates() -> None:
    """A sustained MiB rise across the series is flagged as structural creep.

    Baseline window medians ~67 MiB, recent window medians ~80 MiB => delta 13,
    well above the default 4 MiB threshold => the gate signal fires. Closed form:
    median of {67,67,67} = 67; median of {80,80,80} = 80.
    """
    rows = _flat_series(67, 0.29, 3) + _flat_series(80, 0.29, 3)
    # distinct commits so the two windows don't share ids
    rows = [_row(f"h{i}", r.probes[0].peak_mib, 0.29) for i, r in enumerate(rows)]
    verdict = detect_creep(rows, window=3, mib_creep_delta=4)
    creep = verdict.probe_creeps[0]
    assert creep.peak_mib_baseline == pytest.approx(67.0)
    assert creep.peak_mib_recent == pytest.approx(80.0)
    assert creep.peak_mib_delta == pytest.approx(13.0)
    assert creep.peak_mib_creep is True
    assert verdict.has_structural_creep is True


def test_small_mib_rise_under_threshold_does_not_gate() -> None:
    """A 3 MiB rise (< the 4 MiB threshold) is jitter, not creep."""
    rows = [_row(f"h{i}", 67, 0.29) for i in range(3)] + [_row(f"r{i}", 70, 0.29) for i in range(3)]
    verdict = detect_creep(rows, window=3, mib_creep_delta=4)
    assert verdict.probe_creeps[0].peak_mib_delta == pytest.approx(3.0)
    assert verdict.has_structural_creep is False


def test_wall_time_creep_is_advisory_only() -> None:
    """A doubled wall-time (flat MiB) alerts but never gates."""
    rows = [_row(f"h{i}", 67, 0.30) for i in range(3)] + [_row(f"r{i}", 67, 0.60) for i in range(3)]
    verdict = detect_creep(rows, window=3, mib_creep_delta=4, band=1.25)
    creep = verdict.probe_creeps[0]
    assert creep.wall_time_ratio == pytest.approx(2.0)
    assert creep.wall_time_creep is True
    assert verdict.has_wall_time_creep is True
    # The gate signal ignores wall-time entirely.
    assert verdict.has_structural_creep is False


def test_wall_time_ratio_none_when_baseline_zero() -> None:
    """A zero baseline wall-time makes the ratio undefined; it never alerts."""
    rows = [_row(f"h{i}", 67, 0.0) for i in range(3)] + [_row(f"r{i}", 67, 0.30) for i in range(3)]
    verdict = detect_creep(rows, window=3)
    creep = verdict.probe_creeps[0]
    assert creep.wall_time_ratio is None
    assert creep.wall_time_creep is False


def test_config_drift_flagged_advisory() -> None:
    """Differing probe inputs across windows flag config drift (advisory)."""
    rows = [_row(f"h{i}", 67, 0.29, n_policies=3_000) for i in range(3)] + [
        _row(f"r{i}", 67, 0.29, n_policies=5_000) for i in range(3)
    ]
    verdict = detect_creep(rows, window=3)
    assert verdict.probe_creeps[0].config_drift is True
    assert verdict.has_config_drift is True
    # config drift alone is advisory — no structural creep from an unchanged peak.
    assert verdict.has_structural_creep is False


def test_median_ignores_single_outlier() -> None:
    """The median estimator ignores one machine-noise spike in a window."""
    # baseline peaks 67,67,200(spike) -> median 67; recent 68,68,68 -> median 68 => delta 1.
    baseline = [_row("b0", 67, 0.29), _row("b1", 67, 0.29), _row("b2", 200, 0.29)]
    recent = [_row("r0", 68, 0.29), _row("r1", 68, 0.29), _row("r2", 68, 0.29)]
    verdict = detect_creep(baseline + recent, window=3, mib_creep_delta=4)
    assert verdict.probe_creeps[0].peak_mib_baseline == pytest.approx(67.0)
    assert verdict.probe_creeps[0].peak_mib_delta == pytest.approx(1.0)
    assert verdict.has_structural_creep is False


def test_multi_probe_one_creeps() -> None:
    """With two hot paths, only the creeping one is flagged; the gate fires."""

    def two(peak_project: int, peak_apply: int) -> list[ProbeHistoryEntry]:
        return [
            _entry(peak_project, 0.29),
            ProbeHistoryEntry(
                probe="apply",
                n_policies=3_000,
                projection_months=120,
                n_cells=360_000,
                output_fingerprint="cafe",
                peak_mib=peak_apply,
                best_of_k_seconds=0.10,
                k=5,
            ),
        ]

    rows = [_row(f"h{i}", 0, 0.0, entries=two(67, 20)) for i in range(3)] + [
        _row(f"r{i}", 0, 0.0, entries=two(67, 40)) for i in range(3)
    ]
    verdict = detect_creep(rows, window=3, mib_creep_delta=4)
    by_probe = {c.probe: c for c in verdict.probe_creeps}
    assert by_probe["project"].peak_mib_creep is False
    assert by_probe["apply"].peak_mib_creep is True
    assert by_probe["apply"].peak_mib_delta == pytest.approx(20.0)
    assert verdict.has_structural_creep is True


def test_verdict_dict_is_gate_signal_first() -> None:
    """to_verdict_dict leads with the verdict block, gate signal first."""
    verdict = detect_creep(_flat_series(67, 0.29, 6), window=3)
    payload = verdict.to_verdict_dict()
    assert next(iter(payload.keys())) == "verdict"
    assert set(payload["verdict"]) == {
        "has_structural_creep",
        "has_wall_time_creep",
        "has_config_drift",
    }


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"window": 0}, "window must be positive"),
        ({"window": -1}, "window must be positive"),
        ({"mib_creep_delta": -1}, "mib_creep_delta must be non-negative"),
        ({"band": 0.0}, "band must be positive"),
        ({"band": -0.5}, "band must be positive"),
    ],
)
def test_detect_creep_validates_inputs(kwargs: dict[str, object], match: str) -> None:
    """Out-of-range knobs raise PolarisValidationError, not a silent bad verdict."""
    with pytest.raises(PolarisValidationError, match=match):
        detect_creep(_flat_series(67, 0.29, 6), **kwargs)


# --------------------------------------------------------------------------- #
# end-to-end with the real engine (slow)
# --------------------------------------------------------------------------- #


@pytest.mark.perf
@pytest.mark.slow
def test_record_and_analyse_real_probe(tmp_path: Path) -> None:
    """Run the real probe, record it, reload, and analyse — wiring + JSON round-trip."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv", select_period=3, min_age=18, max_age=60
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="perfhist",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="perfhist")
    config = ProjectionConfig(
        valuation_date=VAL_DATE, projection_horizon_years=10, discount_rate=0.05
    )
    report = run_perf_probe(assumptions, config, n_policies=500, k=2)

    path = tmp_path / "perf" / "history.jsonl"
    row = PerfHistoryRow.from_report(
        report, commit="testsha", commit_date="2026-08-02T00:00:00+00:00"
    )
    append_history_row(row, path)
    loaded = load_history(path)
    assert len(loaded) == 1
    assert loaded[0].probes[0].output_fingerprint == report.probes[0].output_fingerprint
    # One row is far short of a window -> insufficient, never a false creep alarm.
    verdict = detect_creep(loaded, window=3)
    assert verdict.insufficient_data is True
    assert verdict.has_structural_creep is False
