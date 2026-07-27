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
    "PerfProbe",
    "PerfReport",
    "default_hot_paths",
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
