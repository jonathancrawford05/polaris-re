"""Fast unit tests for the head-vs-main perf diff (``analytics.perf_harness.diff_reports``).

Like the sibling ``test_perf_harness_units.py``, these exercise the pure diff
arithmetic and the gate/alert classification on hand-built :class:`PerfReport`s —
no engine run and no git checkout — so they stay in the fast (``-m "not slow"``)
matrix (the git-worktree integration is ``scripts/perfbench.py``'s job). The
load-bearing rule is the split the CI job (a later slice) relies on: a
deterministic-metric mismatch (or an unmatched probe) is a **hard delta**; a
wall-time ratio outside the band or a peak-MiB increase beyond the threshold is
an **advisory alert only** and never gates.
"""

import pytest

from polaris_re.analytics.perf_harness import (
    PerfDiff,
    PerfProbe,
    PerfReport,
    ProbeDiff,
    diff_reports,
)
from polaris_re.core.exceptions import PolarisValidationError


def _probe(
    *,
    name: str = "project",
    n_policies: int = 1_000,
    projection_months: int = 120,
    fingerprint: str = "abc123",
    peak_mib: int = 67,
    best_of_k: float = 0.30,
) -> PerfProbe:
    """A synthetic probe row with self-consistent ``n_cells`` and one timing sample."""
    return PerfProbe(
        probe=name,
        n_policies=n_policies,
        projection_months=projection_months,
        n_cells=n_policies * projection_months,
        output_fingerprint=fingerprint,
        peak_bytes=peak_mib * 1024 * 1024,
        peak_mib=peak_mib,
        best_of_k_seconds=best_of_k,
        k=1,
        samples_seconds=[best_of_k],
    )


def _report(*probes: PerfProbe) -> PerfReport:
    return PerfReport(
        engine_label="TermLife",
        projection_years=10,
        discount_rate=0.05,
        n_policies=probes[0].n_policies if probes else 1_000,
        probes=list(probes),
    )


class TestIdenticalReports:
    def test_identical_reports_have_no_delta_and_no_alerts(self) -> None:
        report = _report(_probe())
        diff = diff_reports(report, _report(_probe()))
        assert isinstance(diff, PerfDiff)
        assert diff.has_hard_delta is False
        assert diff.has_wall_time_alert is False
        assert diff.has_peak_mib_alert is False
        assert diff.head_only_probes == []
        assert diff.main_only_probes == []
        (pd,) = diff.probe_diffs
        assert pd.structural_match is True
        assert pd.structural_mismatches == {}
        assert pd.wall_time_ratio == pytest.approx(1.0)


class TestStructuralHardDelta:
    def test_fingerprint_mismatch_is_a_hard_delta(self) -> None:
        head = _report(_probe(fingerprint="HEAD_DIGEST"))
        main = _report(_probe(fingerprint="MAIN_DIGEST"))
        diff = diff_reports(head, main)
        assert diff.has_hard_delta is True
        (pd,) = diff.probe_diffs
        assert pd.structural_match is False
        assert pd.structural_mismatches["output_fingerprint"] == {
            "head": "HEAD_DIGEST",
            "main": "MAIN_DIGEST",
        }

    def test_cell_count_mismatch_is_a_hard_delta(self) -> None:
        head = _report(_probe(n_policies=1_000))
        main = _report(_probe(n_policies=1_200))
        diff = diff_reports(head, main)
        assert diff.has_hard_delta is True
        (pd,) = diff.probe_diffs
        assert set(pd.structural_mismatches) == {"n_policies", "n_cells"}

    def test_head_only_probe_is_a_hard_delta(self) -> None:
        head = _report(_probe(name="project"), _probe(name="rate_build"))
        main = _report(_probe(name="project"))
        diff = diff_reports(head, main)
        assert diff.has_hard_delta is True
        assert diff.head_only_probes == ["rate_build"]
        assert diff.main_only_probes == []

    def test_main_only_probe_is_a_hard_delta(self) -> None:
        head = _report(_probe(name="project"))
        main = _report(_probe(name="project"), _probe(name="treaty_apply"))
        diff = diff_reports(head, main)
        assert diff.has_hard_delta is True
        assert diff.main_only_probes == ["treaty_apply"]


class TestWallTimeAdvisoryAlert:
    def test_ratio_above_band_alerts_but_does_not_gate(self) -> None:
        # head 2x slower than main; structural metrics identical.
        head = _report(_probe(best_of_k=0.60))
        main = _report(_probe(best_of_k=0.30))
        diff = diff_reports(head, main, band=1.5)
        assert diff.has_wall_time_alert is True
        assert diff.has_hard_delta is False  # wall-time NEVER gates
        (pd,) = diff.probe_diffs
        assert pd.wall_time_ratio == pytest.approx(2.0)
        assert pd.wall_time_alert is True

    def test_ratio_inside_band_does_not_alert(self) -> None:
        head = _report(_probe(best_of_k=0.33))
        main = _report(_probe(best_of_k=0.30))
        diff = diff_reports(head, main, band=1.5)
        assert diff.has_wall_time_alert is False

    def test_ratio_exactly_at_band_does_not_alert(self) -> None:
        # ratio == band is not "outside" the band (strictly greater fires).
        head = _report(_probe(best_of_k=0.45))
        main = _report(_probe(best_of_k=0.30))
        diff = diff_reports(head, main, band=1.5)
        (pd,) = diff.probe_diffs
        assert pd.wall_time_ratio == pytest.approx(1.5)
        assert pd.wall_time_alert is False

    def test_zero_main_timing_yields_none_ratio_and_no_alert(self) -> None:
        head = _report(_probe(best_of_k=0.30))
        main = _report(_probe(best_of_k=0.0))
        diff = diff_reports(head, main)
        (pd,) = diff.probe_diffs
        assert pd.wall_time_ratio is None
        assert pd.wall_time_alert is False
        assert diff.has_hard_delta is False


class TestPeakMibAdvisoryAlert:
    def test_peak_mib_increase_beyond_threshold_alerts_only(self) -> None:
        head = _report(_probe(peak_mib=73))  # +6 MiB, an extra NxT array
        main = _report(_probe(peak_mib=67))
        diff = diff_reports(head, main, mib_alert_delta=4)
        assert diff.has_peak_mib_alert is True
        assert diff.has_hard_delta is False  # memory NEVER gates
        (pd,) = diff.probe_diffs
        assert pd.peak_mib_delta == 6
        assert pd.peak_mib_alert is True

    def test_peak_mib_within_threshold_does_not_alert(self) -> None:
        head = _report(_probe(peak_mib=68))  # +1 MiB rounding jitter
        main = _report(_probe(peak_mib=67))
        diff = diff_reports(head, main, mib_alert_delta=4)
        assert diff.has_peak_mib_alert is False

    def test_head_using_less_memory_never_alerts(self) -> None:
        head = _report(_probe(peak_mib=60))
        main = _report(_probe(peak_mib=67))
        diff = diff_reports(head, main)
        (pd,) = diff.probe_diffs
        assert pd.peak_mib_delta == -7
        assert pd.peak_mib_alert is False


class TestDiffDictShape:
    def test_verdict_is_first_and_carries_the_gate_booleans(self) -> None:
        head = _report(_probe(fingerprint="HEAD"))
        main = _report(_probe(fingerprint="MAIN"))
        payload = diff_reports(head, main).to_diff_dict()
        assert next(iter(payload)) == "verdict"
        assert payload["verdict"] == {
            "has_hard_delta": True,
            "has_wall_time_alert": False,
            "has_peak_mib_alert": False,
        }
        assert payload["band"] == pytest.approx(1.5)
        probe = payload["probes"][0]
        assert set(probe["peak_mib"]) == {"head", "main", "delta", "alert"}
        assert set(probe["wall_time"]) == {"head_seconds", "main_seconds", "ratio", "alert"}


class TestValidation:
    def test_non_positive_band_raises(self) -> None:
        report = _report(_probe())
        with pytest.raises(PolarisValidationError, match="band must be positive"):
            diff_reports(report, _report(_probe()), band=0.0)

    def test_negative_mib_alert_delta_raises(self) -> None:
        report = _report(_probe())
        with pytest.raises(PolarisValidationError, match="mib_alert_delta must be non-negative"):
            diff_reports(report, _report(_probe()), mib_alert_delta=-1)

    def test_probe_diff_is_the_expected_model(self) -> None:
        diff = diff_reports(_report(_probe()), _report(_probe()))
        assert all(isinstance(d, ProbeDiff) for d in diff.probe_diffs)
