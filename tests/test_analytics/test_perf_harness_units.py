"""Fast unit tests for the perf harness (``analytics/perf_harness.py``).

These exercise the pure pieces — the output fingerprint, the model helpers, the
``perf.json`` renderer, and ``run_perf_probe``'s input validation — WITHOUT
running the projection engine, so they stay in the fast (``-m "not slow"``)
matrix. The engine-driven reproducibility guarantees live in the ``perf``-marked
``tests/perf/test_perf_harness.py``.
"""

import json
from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.perf_harness import (
    PerfProbe,
    PerfReport,
    default_hot_paths,
    output_fingerprint,
    run_perf_probe,
)
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError


def _cash_flow_result(net: list[float]) -> CashFlowResult:
    """Minimal aggregate CashFlowResult with consistent-length core arrays."""
    arr = np.array(net, dtype=np.float64)
    return CashFlowResult(
        run_id="perf-unit",
        valuation_date=date(2025, 1, 1),
        basis="NET",
        assumption_set_version="v-test",
        product_type="TERM",
        projection_months=len(net),
        gross_premiums=arr * 2.0,
        death_claims=arr * 0.5,
        lapse_surrenders=np.zeros_like(arr),
        expenses=arr * 0.1,
        reserve_balance=np.cumsum(arr),
        reserve_increase=arr * 0.0,
        net_cash_flow=arr,
    )


class TestOutputFingerprint:
    def test_identical_results_hash_identically(self) -> None:
        r1 = _cash_flow_result([100.0, -50.0, 25.0])
        r2 = _cash_flow_result([100.0, -50.0, 25.0])
        assert output_fingerprint(r1) == output_fingerprint(r2)

    def test_changed_array_changes_the_hash(self) -> None:
        base = output_fingerprint(_cash_flow_result([100.0, -50.0, 25.0]))
        perturbed = output_fingerprint(_cash_flow_result([100.0, -50.0, 25.001]))
        assert base != perturbed

    def test_negative_zero_is_normalised(self) -> None:
        # -0.0 and 0.0 must fingerprint identically (the ``+ 0.0`` normalisation).
        pos = _cash_flow_result([0.0, 1.0])
        neg = _cash_flow_result([-0.0, 1.0])
        assert output_fingerprint(pos) == output_fingerprint(neg)

    def test_fingerprint_is_a_hex_digest(self) -> None:
        fp = output_fingerprint(_cash_flow_result([1.0]))
        assert isinstance(fp, str)
        assert len(fp) == 32  # blake2b digest_size=16 => 32 hex chars
        int(fp, 16)  # parses as hex


class TestPerfModels:
    def _probe(self) -> PerfProbe:
        return PerfProbe(
            probe="project",
            n_policies=1_000,
            projection_months=120,
            n_cells=120_000,
            output_fingerprint="deadbeef",
            peak_bytes=70_018_996,
            peak_mib=67,
            best_of_k_seconds=0.29,
            k=3,
            samples_seconds=[0.31, 0.29, 0.30],
        )

    def test_deterministic_metrics_excludes_timing_and_raw_bytes(self) -> None:
        metrics = self._probe().deterministic_metrics()
        assert metrics == {
            "n_policies": 1_000,
            "projection_months": 120,
            "n_cells": 120_000,
            "output_fingerprint": "deadbeef",
        }
        # peak_mib, peak_bytes, and timing are intentionally NOT gate metrics.
        assert "peak_mib" not in metrics
        assert "best_of_k_seconds" not in metrics

    def test_perf_dict_orders_deterministic_before_timing(self) -> None:
        report = PerfReport(
            engine_label="TermLife",
            projection_years=10,
            discount_rate=0.05,
            n_policies=1_000,
            probes=[self._probe()],
        )
        payload = report.to_perf_dict()
        assert payload["n_policies"] == 1_000
        probe = payload["probes"][0]
        keys = list(probe)
        assert keys.index("deterministic") < keys.index("timing")
        assert probe["peak_mib"] == 67
        assert probe["timing"]["peak_bytes"] == 70_018_996

    def test_to_json_is_valid_json(self) -> None:
        report = PerfReport(
            engine_label="TermLife",
            projection_years=10,
            discount_rate=0.05,
            n_policies=1_000,
            probes=[self._probe()],
        )
        parsed = json.loads(report.to_json())
        assert parsed["probes"][0]["deterministic"]["n_cells"] == 120_000


class TestDefaultHotPaths:
    def test_default_is_the_project_path_only(self) -> None:
        paths = default_hot_paths()
        assert list(paths) == ["project"]

    def test_default_returns_a_fresh_mutable_map(self) -> None:
        a = default_hot_paths()
        a["extra"] = lambda engine: engine.project()
        assert "extra" not in default_hot_paths()


class TestRunPerfProbeValidation:
    """These raise before any block/engine construction, so they stay fast."""

    def test_non_positive_n_policies_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="n_policies must be positive"):
            run_perf_probe(assumptions=None, config=None, n_policies=0)  # type: ignore[arg-type]

    def test_non_positive_k_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="k must be positive"):
            run_perf_probe(assumptions=None, config=None, n_policies=10, k=0)  # type: ignore[arg-type]

    def test_empty_hot_paths_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="at least one hot path"):
            run_perf_probe(assumptions=None, config=None, n_policies=10, hot_paths={})  # type: ignore[arg-type]
