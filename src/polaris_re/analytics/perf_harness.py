"""Performance-regression harness — deterministic-first timing of engine hot paths.

This module is the *deterministic companion* to the pass/fail CI smoke gate
(ADR-168): where the smoke job proves the deployed entry points **boot**, this
harness proves the projection engine has not gotten **slower** or started
**allocating more**. It times a set of named hot-path callables (default: the
production ``get_product_engine(...).project()`` path — the same call the CLI
and API use) on a *fixed synthetic block* and reports, per hot path, a small set
of metrics split by how they should be consumed:

**Deterministic (hard-gate-safe).** ``n_policies``, ``projection_months``,
``n_cells`` (``N x T``), and an ``output_fingerprint`` (a digest of the rounded
core :class:`CashFlowResult` arrays). These are byte-reproducible for a given
``(code, input)`` pair, so a CI job may gate on any change to them. The
fingerprint doubles as a *correctness tripwire*: it proves the *same*
computation ran on two branches, so a timing comparison between them is
apples-to-apples.

**Coarse / alert-grade.** ``peak_mib`` — the process's ``tracemalloc`` peak
rounded to whole MiB. Raw byte counts carry ~0.005% run-to-run jitter (numpy's
allocator), so the raw ``peak_bytes`` is informational only; the MiB-rounded
figure is stable enough to *alert* on a real allocation regression (an extra
``N x T`` float64 array on the default block is ~6 MiB) but is not a hard gate.

**Informational only.** ``best_of_k_seconds`` and the raw ``samples_seconds``.
GitHub runners vary 2-3x run-to-run, so — per the maintainer's non-negotiable
design rule (2026-07-12) — **raw wall-time never gates or alerts on an absolute
value**; it only informs. The noise-cancelling head-vs-main *ratio* that *can*
alert is built in a later slice (see ``docs/PLAN_perf_harness.md``). Timing uses
the best-of-``k`` **minimum**, the stable estimator (the mean is dragged by the
first-call / GC outlier).

Nothing here is on the pricing/import hot path — it is a sibling diagnostic
harness to :mod:`polaris_re.analytics.scale_benchmark` (ADR-161), whose
:func:`~polaris_re.analytics.scale_benchmark.build_homogeneous_block` it reuses
for block construction. B2 measures *scaling shape* across block sizes; this
measures *head-vs-main drift* at a fixed size. Both take a caller-supplied
:class:`AssumptionSet` / :class:`ProjectionConfig`, so the harness is agnostic
to which mortality basis drives the run. All timings pin ``valuation_date`` via
the caller-pinned config (ADR-074) — never ``date.today()``.
"""

import gc
import hashlib
import json
import time
import tracemalloc
from collections.abc import Callable, Mapping

from pydantic import Field

from polaris_re.analytics.scale_benchmark import BlockBuilder, build_homogeneous_block
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct
from polaris_re.products.dispatch import get_product_engine

__all__ = [
    "PerfDiff",
    "PerfProbe",
    "PerfReport",
    "ProbeDiff",
    "default_hot_paths",
    "diff_reports",
    "output_fingerprint",
    "run_perf_probe",
]

#: A hot path receives a built product engine and returns the projected result.
#: Returning the :class:`CashFlowResult` lets the harness fingerprint the output
#: so head-vs-main timing comparisons are provably on the same computation.
type HotPath = Callable[[BaseProduct], CashFlowResult]

#: The core, always-populated :class:`CashFlowResult` arrays that make up the
#: deterministic output fingerprint. Optional/seriatim arrays are excluded so the
#: fingerprint is stable across configs that do or do not populate them.
_FINGERPRINT_ARRAYS: tuple[str, ...] = (
    "gross_premiums",
    "death_claims",
    "lapse_surrenders",
    "expenses",
    "reserve_balance",
    "reserve_increase",
    "net_cash_flow",
)


def default_hot_paths() -> dict[str, HotPath]:
    """The default hot-path map: the full production ``project()`` path only.

    Returned fresh on each call so callers can extend it without mutating a
    shared default. Later slices / callers add finer sub-paths (rate-array
    build, treaty apply) by passing their own map.
    """
    return {"project": lambda engine: engine.project()}


def output_fingerprint(result: CashFlowResult) -> str:
    """Deterministic digest of the core cash-flow arrays.

    Each array in :data:`_FINGERPRINT_ARRAYS` is rounded to 6 decimals (``+ 0.0``
    normalises ``-0.0`` to ``0.0``) and its native-endian bytes are folded into a
    blake2b hash. The result is byte-identical for a given ``(code, input)`` pair
    on the same platform, so it proves two branches ran the *same* computation.
    It is deliberately coarse (a correctness tripwire, not a replacement for the
    ``tests/qa/`` goldens).
    """
    # Local import keeps NumPy off this module's import cost (mirrors B2).
    import numpy as np

    digest = hashlib.blake2b(digest_size=16)
    for name in _FINGERPRINT_ARRAYS:
        arr = np.asarray(getattr(result, name), dtype=np.float64)
        digest.update(name.encode("utf-8"))
        digest.update(str(arr.shape).encode("utf-8"))
        digest.update((np.round(arr, 6) + 0.0).tobytes())
    return digest.hexdigest()


class PerfProbe(PolarisBaseModel):
    """One hot-path measurement on the fixed synthetic block.

    Fields are grouped by how a consumer (e.g. a CI gate) should treat them:
    the deterministic set (:meth:`deterministic_metrics`) is hard-gate-safe,
    ``peak_mib`` is coarse alert-grade, and the timing fields are informational.
    """

    probe: str = Field(description="Hot-path name (e.g. 'project').")
    n_policies: int = Field(gt=0, description="Block size projected (deterministic input).")
    projection_months: int = Field(
        gt=0, description="Projection horizon T in months (the NxT second axis; deterministic)."
    )
    n_cells: int = Field(
        gt=0, description="N x T array-cell count — the work volume (deterministic)."
    )
    output_fingerprint: str = Field(
        description="blake2b digest of the rounded core cash-flow arrays (deterministic tripwire)."
    )
    peak_bytes: int = Field(
        ge=0,
        description="Raw tracemalloc peak (bytes). INFORMATIONAL — ~0.005% run-to-run jitter.",
    )
    peak_mib: int = Field(
        ge=0,
        description="tracemalloc peak rounded to whole MiB. Coarse ALERT-grade (not a hard gate).",
    )
    best_of_k_seconds: float = Field(
        ge=0.0,
        description="Minimum wall-clock over k timed runs. INFORMATIONAL — never gates absolutely.",
    )
    k: int = Field(gt=0, description="Number of timing samples taken.")
    samples_seconds: list[float] = Field(
        description="Raw per-run wall-clock seconds (informational; best_of_k = min)."
    )

    def deterministic_metrics(self) -> dict[str, int | str]:
        """The exactly-reproducible, hard-gate-safe subset of this probe.

        A CI gate (a later slice) compares this dict between branches; any change
        is a hard delta. ``peak_mib`` and the timings are intentionally excluded
        (coarse / informational), per the maintainer design rule.
        """
        return {
            "n_policies": self.n_policies,
            "projection_months": self.projection_months,
            "n_cells": self.n_cells,
            "output_fingerprint": self.output_fingerprint,
        }


class PerfReport(PolarisBaseModel):
    """All hot-path probes for one harness run, plus the ``perf.json`` renderer."""

    engine_label: str = Field(description="Human label for the projected engine (e.g. 'TermLife').")
    projection_years: int = Field(gt=0, description="Projection horizon in years (config).")
    discount_rate: float = Field(description="Discount rate used for the timed projection.")
    n_policies: int = Field(gt=0, description="Fixed block size the probes ran on.")
    probes: list[PerfProbe] = Field(description="One probe per timed hot path.")

    def to_perf_dict(self) -> dict[str, object]:
        """The ``perf.json`` payload, deterministic metrics first, timing last.

        Ordering is deliberate: a reader (or a diff tool in a later slice) sees
        the gate-relevant deterministic block before the informational timing.
        """
        return {
            "engine_label": self.engine_label,
            "projection_years": self.projection_years,
            "discount_rate": self.discount_rate,
            "n_policies": self.n_policies,
            "probes": [
                {
                    "probe": p.probe,
                    "deterministic": p.deterministic_metrics(),
                    "peak_mib": p.peak_mib,
                    "timing": {
                        "best_of_k_seconds": p.best_of_k_seconds,
                        "k": p.k,
                        "samples_seconds": p.samples_seconds,
                        "peak_bytes": p.peak_bytes,
                    },
                }
                for p in self.probes
            ],
        }

    def to_json(self) -> str:
        """Render :meth:`to_perf_dict` as an indented JSON string."""
        return json.dumps(self.to_perf_dict(), indent=2)


class ProbeDiff(PolarisBaseModel):
    """Head-vs-main comparison of one hot-path probe.

    A probe present under the same name on both branches is compared field by
    field. The **deterministic** metrics (counts + output fingerprint) are the
    hard-gate signal: any mismatch means head and main did not run the *same*
    computation (a structural regression, or a correctness change that
    invalidates the timing comparison) and is flagged as a hard delta. The
    ``peak_mib`` delta and the wall-time ratio are **advisory alerts only** —
    they never contribute to a hard delta, per the maintainer design rule
    (2026-07-12): noise-normalized metrics may alert, raw wall-time only informs.
    """

    probe: str = Field(description="Hot-path name compared across the two branches.")
    structural_match: bool = Field(
        description="True iff every deterministic metric is byte-identical head vs main."
    )
    structural_mismatches: dict[str, dict[str, int | str]] = Field(
        default_factory=dict,
        description="metric -> {'head': ..., 'main': ...} for each differing deterministic metric.",
    )
    peak_mib_head: int = Field(ge=0, description="Head tracemalloc peak (MiB-rounded).")
    peak_mib_main: int = Field(ge=0, description="Main tracemalloc peak (MiB-rounded).")
    peak_mib_delta: int = Field(
        description="head - main peak MiB. Positive => head allocates more (advisory alert)."
    )
    peak_mib_alert: bool = Field(
        description="True iff peak_mib_delta exceeds the alert threshold (advisory, never gates)."
    )
    wall_time_head_seconds: float = Field(
        ge=0.0, description="Head best-of-k wall-clock seconds (informational)."
    )
    wall_time_main_seconds: float = Field(
        ge=0.0, description="Main best-of-k wall-clock seconds (informational)."
    )
    wall_time_ratio: float | None = Field(
        description="head / main best-of-k ratio; None if main timing is zero (undivisible)."
    )
    wall_time_alert: bool = Field(
        description="True iff wall_time_ratio exceeds the band (advisory, never a hard delta)."
    )


class PerfDiff(PolarisBaseModel):
    """The verdict for one head-vs-main harness comparison.

    Splits into exactly two categories, mirroring the CI job a later slice wires
    up: a **hard delta** (structural — a probe present on only one branch, or any
    deterministic-metric mismatch) that a gate blocks on, and **advisory alerts**
    (wall-time ratio outside the band, or a peak-MiB increase beyond the
    threshold) that inform but never block. :attr:`has_hard_delta` is the single
    boolean a gate reads.
    """

    band: float = Field(
        gt=0.0, description="Wall-time head/main ratio above which an advisory alert fires."
    )
    mib_alert_delta: int = Field(
        ge=0,
        description="peak_mib head-over-main increase (MiB) above which an advisory alert fires.",
    )
    head_only_probes: list[str] = Field(
        default_factory=list, description="Probe names present in head but not main (hard delta)."
    )
    main_only_probes: list[str] = Field(
        default_factory=list, description="Probe names present in main but not head (hard delta)."
    )
    probe_diffs: list[ProbeDiff] = Field(
        default_factory=list,
        description="Per-probe comparison for probes present on both branches.",
    )

    @property
    def has_hard_delta(self) -> bool:
        """The gate signal: an unmatched probe or any deterministic-metric mismatch."""
        return bool(self.head_only_probes or self.main_only_probes) or any(
            not d.structural_match for d in self.probe_diffs
        )

    @property
    def has_wall_time_alert(self) -> bool:
        """Advisory: any probe's wall-time ratio exceeded the band."""
        return any(d.wall_time_alert for d in self.probe_diffs)

    @property
    def has_peak_mib_alert(self) -> bool:
        """Advisory: any probe's peak MiB grew beyond the alert threshold."""
        return any(d.peak_mib_alert for d in self.probe_diffs)

    def to_diff_dict(self) -> dict[str, object]:
        """The verdict payload — hard-gate signal first, then advisories, then detail."""
        return {
            "verdict": {
                "has_hard_delta": self.has_hard_delta,
                "has_wall_time_alert": self.has_wall_time_alert,
                "has_peak_mib_alert": self.has_peak_mib_alert,
            },
            "band": self.band,
            "mib_alert_delta": self.mib_alert_delta,
            "head_only_probes": self.head_only_probes,
            "main_only_probes": self.main_only_probes,
            "probes": [
                {
                    "probe": d.probe,
                    "structural_match": d.structural_match,
                    "structural_mismatches": d.structural_mismatches,
                    "peak_mib": {
                        "head": d.peak_mib_head,
                        "main": d.peak_mib_main,
                        "delta": d.peak_mib_delta,
                        "alert": d.peak_mib_alert,
                    },
                    "wall_time": {
                        "head_seconds": d.wall_time_head_seconds,
                        "main_seconds": d.wall_time_main_seconds,
                        "ratio": d.wall_time_ratio,
                        "alert": d.wall_time_alert,
                    },
                }
                for d in self.probe_diffs
            ],
        }


def diff_reports(
    head: PerfReport,
    main: PerfReport,
    *,
    band: float = 1.5,
    mib_alert_delta: int = 4,
) -> PerfDiff:
    """Compare a head :class:`PerfReport` against a main one, probe by probe.

    Probes are matched by name. A probe present on only one side is a hard delta
    (the branches expose different hot paths — the comparison is not
    apples-to-apples). For each matched probe the deterministic metrics are
    compared exactly (any difference => hard delta); the ``peak_mib`` delta and
    the best-of-k wall-time ratio are computed as **advisory** signals only.

    The wall-time ratio is ``head / main`` on the best-of-k minimum — the
    noise-cancelling estimator the whole harness is built around (run head and
    main in the same job so machine noise divides out). It is ``None`` when the
    main timing is zero (not divisible); a ``None`` ratio never alerts.

    Args:
        head: Report from the current worktree.
        main: Report from the ``origin/main`` checkout.
        band: Wall-time ratio above which an advisory alert fires. Positive.
        mib_alert_delta: head-over-main peak MiB increase above which an advisory
            memory alert fires. Non-negative (a coarse guard above the ±1 MiB
            rounding jitter).

    Returns:
        A :class:`PerfDiff` verdict; read :attr:`PerfDiff.has_hard_delta` to gate.

    Raises:
        PolarisValidationError: if ``band`` is not positive or ``mib_alert_delta``
            is negative.
    """
    if band <= 0.0:
        raise PolarisValidationError(f"band must be positive, got {band}.")
    if mib_alert_delta < 0:
        raise PolarisValidationError(
            f"mib_alert_delta must be non-negative, got {mib_alert_delta}."
        )

    head_probes = {p.probe: p for p in head.probes}
    main_probes = {p.probe: p for p in main.probes}
    head_only = sorted(head_probes.keys() - main_probes.keys())
    main_only = sorted(main_probes.keys() - head_probes.keys())

    probe_diffs: list[ProbeDiff] = []
    for name in sorted(head_probes.keys() & main_probes.keys()):
        h = head_probes[name]
        m = main_probes[name]
        h_det = h.deterministic_metrics()
        m_det = m.deterministic_metrics()
        mismatches: dict[str, dict[str, int | str]] = {
            key: {"head": h_det[key], "main": m_det[key]}
            for key in h_det
            if h_det[key] != m_det[key]
        }
        peak_delta = h.peak_mib - m.peak_mib
        ratio = h.best_of_k_seconds / m.best_of_k_seconds if m.best_of_k_seconds > 0.0 else None
        probe_diffs.append(
            ProbeDiff(
                probe=name,
                structural_match=not mismatches,
                structural_mismatches=mismatches,
                peak_mib_head=h.peak_mib,
                peak_mib_main=m.peak_mib,
                peak_mib_delta=peak_delta,
                peak_mib_alert=peak_delta > mib_alert_delta,
                wall_time_head_seconds=h.best_of_k_seconds,
                wall_time_main_seconds=m.best_of_k_seconds,
                wall_time_ratio=ratio,
                wall_time_alert=ratio is not None and ratio > band,
            )
        )

    return PerfDiff(
        band=band,
        mib_alert_delta=mib_alert_delta,
        head_only_probes=head_only,
        main_only_probes=main_only,
        probe_diffs=probe_diffs,
    )


def run_perf_probe(
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    *,
    n_policies: int = 3_000,
    k: int = 5,
    block_builder: BlockBuilder | None = None,
    hot_paths: Mapping[str, HotPath] | None = None,
    engine_label: str = "TermLife",
) -> PerfReport:
    """Time each hot path on a fixed synthetic block and return a perf report.

    For each hot path the harness performs (1) a single *instrumented* run under
    ``tracemalloc`` to capture the deterministic structural metrics + output
    fingerprint + peak memory, then (2) ``k`` clean timing runs — each on a
    freshly built engine over the *same* block, so no cross-call caching skews
    the number and block-build (Pydantic) cost is excluded from the timing. The
    reported ``best_of_k_seconds`` is the minimum of those ``k`` samples.

    The block is built once via ``block_builder`` (default:
    :func:`~polaris_re.analytics.scale_benchmark.build_homogeneous_block` pinned
    to ``config.valuation_date`` — ADR-074, never ``date.today()``). ``sizes``
    is a single fixed ``n_policies`` on purpose: this harness measures
    head-vs-main drift at one size, not scaling shape (that is B2's job).

    Args:
        assumptions: Mortality + lapse basis; must cover the block's ages.
        config: Projection horizon / discount rate (the timed engine config).
        n_policies: Fixed block size to project. Positive.
        k: Number of timing samples; the report keeps the minimum. Positive.
        block_builder: Maps a size to an InforceBlock; defaults to the B2 builder.
        hot_paths: Name -> callable(engine) -> CashFlowResult; defaults to the
            full ``project()`` path.
        engine_label: Label stored on the report (does not change dispatch).

    Returns:
        A :class:`PerfReport` with one :class:`PerfProbe` per hot path.

    Raises:
        PolarisValidationError: if ``n_policies``/``k`` is not positive or
            ``hot_paths`` is empty.
    """
    if n_policies <= 0:
        raise PolarisValidationError(f"n_policies must be positive, got {n_policies}.")
    if k <= 0:
        raise PolarisValidationError(f"k must be positive, got {k}.")
    paths: Mapping[str, HotPath] = hot_paths if hot_paths is not None else default_hot_paths()
    if not paths:
        raise PolarisValidationError("hot_paths must contain at least one hot path.")

    builder: BlockBuilder = block_builder or (
        lambda n: build_homogeneous_block(n, valuation_date=config.valuation_date)
    )
    block = builder(n_policies)

    def _fresh_engine() -> BaseProduct:
        return get_product_engine(inforce=block, assumptions=assumptions, config=config)

    probes: list[PerfProbe] = []
    for name, fn in paths.items():
        # (1) Instrumented run: deterministic metrics + fingerprint + peak memory.
        engine = _fresh_engine()
        gc.collect()
        tracemalloc.start()
        result = fn(engine)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        months = len(result.net_cash_flow)
        fingerprint = output_fingerprint(result)
        peak_mib = round(peak_bytes / (1024 * 1024))

        # (2) k clean timing runs on fresh engines over the same block.
        samples: list[float] = []
        for _ in range(k):
            engine = _fresh_engine()
            gc.collect()
            start = time.perf_counter()
            fn(engine)
            samples.append(time.perf_counter() - start)

        probes.append(
            PerfProbe(
                probe=name,
                n_policies=n_policies,
                projection_months=months,
                n_cells=n_policies * months,
                output_fingerprint=fingerprint,
                peak_bytes=int(peak_bytes),
                peak_mib=int(peak_mib),
                best_of_k_seconds=min(samples),
                k=k,
                samples_seconds=samples,
            )
        )

    return PerfReport(
        engine_label=engine_label,
        projection_years=config.projection_horizon_years,
        discount_rate=config.discount_rate,
        n_policies=n_policies,
        probes=probes,
    )
