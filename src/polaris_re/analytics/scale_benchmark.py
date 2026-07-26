"""Scale benchmark — measure projection throughput across block sizes.

This module backs the README's *vectorized, no loops over policies* claim with
reproducible numbers. It times the **production** pricing path
(``get_product_engine(...).project()`` — the same call the CLI and API use) for
a sequence of block sizes and reports, per size, the wall-clock projection time,
the policies-per-second throughput, the cell-update rate (``N x T`` array
updates per second), and the process peak RSS.

The headline property a reinsurer cares about is *linear scaling*: because the
engine vectorizes over policies (no Python loop over the block), throughput
(policies/second) stays roughly flat as the block grows from a few thousand to
half a million policies — the signature of an ``O(N)`` engine, not an ``O(N^2)``
one. :func:`run_scale_benchmark` produces the evidence; ``scripts/scale_benchmark.py``
renders the committed table published in the README.

Nothing here is on the pricing/import hot path — it is a diagnostic harness. It
takes a caller-supplied :class:`AssumptionSet` and :class:`ProjectionConfig` so
it is agnostic to which mortality basis drives the run.
"""

import gc
import resource
import time
from collections.abc import Callable, Sequence
from datetime import date
from itertools import pairwise

from pydantic import Field

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine

__all__ = [
    "ScaleBenchmarkReport",
    "ScaleBenchmarkRow",
    "build_homogeneous_block",
    "run_scale_benchmark",
]

#: Type of the callable that turns a policy count into an inforce block.
type BlockBuilder = Callable[[int], InforceBlock]


class ScaleBenchmarkRow(PolarisBaseModel):
    """One (block size -> timing) measurement of the projection engine."""

    n_policies: int = Field(gt=0, description="Number of policies projected in this run.")
    projection_months: int = Field(
        gt=0,
        description="Projection horizon T in monthly steps (the second axis of the NxT engine).",
    )
    projection_seconds: float = Field(
        ge=0.0,
        description="Wall-clock seconds for the single ``project()`` call (build time excluded).",
    )
    policies_per_second: float = Field(
        ge=0.0,
        description="Throughput = n_policies / projection_seconds. Flat across sizes => O(N).",
    )
    cell_updates_per_second: float = Field(
        ge=0.0,
        description="(n_policies x projection_months) / projection_seconds — array-cell rate.",
    )
    peak_rss_mb: float | None = Field(
        default=None,
        description="Process peak resident set size (MiB) after this run; None if unmeasured.",
    )


class ScaleBenchmarkReport(PolarisBaseModel):
    """The full set of size->timing rows plus a Markdown renderer."""

    engine_label: str = Field(
        description="Human label for the projected product engine (e.g. 'TermLife')."
    )
    projection_years: int = Field(gt=0, description="Projection horizon in years (config).")
    discount_rate: float = Field(description="Discount rate used for the timed projection.")
    rows: list[ScaleBenchmarkRow] = Field(
        description="One row per benchmarked block size, size-ascending."
    )

    def to_markdown(self) -> str:
        """Render the report as a committed-doc Markdown table."""
        header = (
            f"Scale benchmark — {self.engine_label}, {self.projection_years}-year "
            f"monthly projection @ {self.discount_rate:.0%} discount\n\n"
            "| Policies | Projection time | Policies / sec | Cell-updates / sec | Peak RSS |\n"
            "|---------:|----------------:|---------------:|-------------------:|---------:|"
        )
        lines = [header]
        for r in self.rows:
            rss = f"{r.peak_rss_mb:,.0f} MB" if r.peak_rss_mb is not None else "—"
            lines.append(
                f"| {r.n_policies:,} | {r.projection_seconds:,.2f} s "
                f"| {r.policies_per_second:,.0f} | {r.cell_updates_per_second:,.0f} | {rss} |"
            )
        return "\n".join(lines)


def build_homogeneous_block(
    n_policies: int,
    *,
    valuation_date: date,
    seed: int = 42,
    issue_age_min: int = 35,
    issue_age_max: int = 55,
    face_amount: float = 500_000.0,
    annual_premium: float = 5_000.0,
    policy_term: int = 20,
) -> InforceBlock:
    """Build a deterministic synthetic TERM block for benchmarking.

    Ages are drawn from a seeded RNG over ``[issue_age_min, issue_age_max)`` so
    two calls with the same ``(n_policies, seed)`` produce byte-identical blocks.
    ``valuation_date`` is a **required, caller-pinned** argument — never
    ``date.today()`` — so benchmarks are reproducible and clock-independent
    (ADR-074 guard).

    All policies are freshly issued TERM (``duration_inforce=0``,
    ``attained_age == issue_age``); the drawn ages must lie within the mortality
    table the caller pairs with this block.
    """
    if n_policies <= 0:
        raise PolarisValidationError(f"n_policies must be positive, got {n_policies}.")
    if issue_age_min >= issue_age_max:
        raise PolarisValidationError(
            f"issue_age_min ({issue_age_min}) must be < issue_age_max ({issue_age_max})."
        )

    # Local import keeps NumPy off this module's import cost when only the models
    # are needed; the RNG is seeded so blocks are reproducible.
    import numpy as np

    # Ages/counts use int32 per the §5 dtype convention (values are unchanged).
    ages = np.random.default_rng(seed).integers(
        issue_age_min, issue_age_max, n_policies, dtype=np.int32
    )
    policies = [
        Policy(
            policy_id=f"BENCH{i:07d}",
            issue_age=int(ages[i]),
            attained_age=int(ages[i]),
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=face_amount,
            annual_premium=annual_premium,
            product_type=ProductType.TERM,
            policy_term=policy_term,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=valuation_date,
            valuation_date=valuation_date,
        )
        for i in range(n_policies)
    ]
    return InforceBlock(policies=policies)


def _peak_rss_mb() -> float:
    """Process peak resident set size in MiB (Linux ``ru_maxrss`` is KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def run_scale_benchmark(
    sizes: Sequence[int],
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    *,
    block_builder: BlockBuilder | None = None,
    measure_memory: bool = True,
    engine_label: str = "TermLife",
) -> ScaleBenchmarkReport:
    """Time ``project()`` for each block size and return a timing report.

    ``sizes`` must be strictly ascending and positive. Ascending order makes the
    per-row ``peak_rss_mb`` accurate: ``ru_maxrss`` is a process high-water mark,
    so each successively larger run's peak *is* that size's peak (nothing bigger
    ran before it). Only the ``project()`` call is timed — block construction is
    excluded so the number reflects engine throughput, not Pydantic build cost.

    Args:
        sizes: Strictly-ascending, positive block sizes to benchmark.
        assumptions: Mortality + lapse basis; must cover the block's ages.
        config: Projection horizon / discount rate (the timed engine config).
        block_builder: Maps a size to an InforceBlock; defaults to
            :func:`build_homogeneous_block` pinned to ``config.valuation_date``.
        measure_memory: Record process peak RSS per row when True.
        engine_label: Label stored on the report (does not change dispatch).

    Returns:
        A :class:`ScaleBenchmarkReport` with one row per size.
    """
    if not sizes:
        raise PolarisValidationError("sizes must contain at least one block size.")
    if any(n <= 0 for n in sizes):
        raise PolarisValidationError(f"All sizes must be positive, got {list(sizes)}.")
    if any(b <= a for a, b in pairwise(sizes)):
        raise PolarisValidationError(
            f"sizes must be strictly ascending (for accurate peak-RSS attribution), "
            f"got {list(sizes)}."
        )

    builder: BlockBuilder = block_builder or (
        lambda n: build_homogeneous_block(n, valuation_date=config.valuation_date)
    )

    rows: list[ScaleBenchmarkRow] = []
    for n in sizes:
        block = builder(n)
        engine = get_product_engine(inforce=block, assumptions=assumptions, config=config)
        gc.collect()

        start = time.perf_counter()
        result = engine.project()
        elapsed = time.perf_counter() - start

        months = len(result.net_cash_flow)
        pps = n / elapsed if elapsed > 0.0 else 0.0
        cps = (n * months) / elapsed if elapsed > 0.0 else 0.0
        rows.append(
            ScaleBenchmarkRow(
                n_policies=n,
                projection_months=months,
                projection_seconds=elapsed,
                policies_per_second=pps,
                cell_updates_per_second=cps,
                peak_rss_mb=_peak_rss_mb() if measure_memory else None,
            )
        )
        # Drop references so the next (larger) run starts from a clean working set.
        del block, engine, result
        gc.collect()

    return ScaleBenchmarkReport(
        engine_label=engine_label,
        projection_years=config.projection_horizon_years,
        discount_rate=config.discount_rate,
        rows=rows,
    )
