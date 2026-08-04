#!/usr/bin/env python3
"""
bench_portfolio_parallel.py — Measure Portfolio.run(max_workers=N) speed-up.

The measurement behind ADR-180's parallel-execution claim. Builds a synthetic
multi-deal portfolio, runs it at a series of worker counts, and reports the
best-of-k wall clock plus the serial/parallel ratio — after proving every
worker count produced a **bit-identical** aggregate.

Three properties are non-negotiable, because each one is easy to get wrong in
the flattering direction:

1. **Cold cache.** Every timed sample builds a *fresh* ``Portfolio`` with
   ``cache=False``. Re-running a warm caching portfolio would parallelise
   nothing and still show an arbitrarily good ratio.
2. **Best-of-k minimum**, not the mean — the stable estimator the perf harness
   is built around (``analytics/perf_harness.run_perf_probe``); the mean is
   dragged by the first-call / GC outlier. This script measures a *portfolio*
   run, which does not fit the harness's engine-level
   ``Callable[[BaseProduct], CashFlowResult]`` hot-path contract, so it reuses
   the harness's estimator discipline and the shared
   ``scale_benchmark.build_homogeneous_block`` builder rather than its entry
   point.
3. **Correctness first.** The aggregate cash flows and per-deal PVs from every
   worker count are compared to the serial run under ``assert_array_equal``
   (exact, never ``allclose``). A mismatch aborts with a non-zero exit status —
   a speed-up on different numbers is not a speed-up.

Wall-clock ratios still obey the harness rule (maintainer, 2026-07-12): they
inform, they never gate. This script exits non-zero only on a *correctness*
mismatch, never on a disappointing ratio.

Usage:
    # Default: 8 deals x 5,000 policies, workers 1/2/4/8
    uv run python scripts/bench_portfolio_parallel.py

    # Bigger book, JSON for a session log / ADR:
    uv run python scripts/bench_portfolio_parallel.py \
        --n-deals 12 --n-policies 20000 --workers 1 2 4 8 16 -o /tmp/par.json
"""

import argparse
import gc
import json
import sys
import time
from datetime import date
from pathlib import Path

# Allow "uv run python scripts/bench_portfolio_parallel.py" without an editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from polaris_re.analytics.portfolio import Portfolio, PortfolioResult  # noqa: E402
from polaris_re.analytics.scale_benchmark import build_homogeneous_block  # noqa: E402
from polaris_re.assumptions.assumption_set import AssumptionSet  # noqa: E402
from polaris_re.assumptions.lapse import LapseAssumption  # noqa: E402
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource  # noqa: E402
from polaris_re.core.inforce import InforceBlock  # noqa: E402
from polaris_re.core.policy import Sex, SmokerStatus  # noqa: E402
from polaris_re.core.projection import ProjectionConfig  # noqa: E402
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty  # noqa: E402
from polaris_re.utils.table_io import load_mortality_csv  # noqa: E402

VBT_MALE_NS = REPO_ROOT / "data" / "mortality_tables" / "soa_vbt_2015_male_ns.csv"
SYNTHETIC_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_select_ultimate.csv"

#: Pinned, never ``date.today()`` (ADR-074) — the benchmark must be reproducible.
VALUATION_DATE = date(2025, 1, 1)

#: Compared exactly across worker counts before any timing is reported.
_AGGREGATE_ARRAYS = (
    "gross_premiums",
    "death_claims",
    "lapse_surrenders",
    "expenses",
    "reserve_balance",
    "reserve_increase",
    "net_cash_flow",
)


def _build_assumptions() -> AssumptionSet:
    """Prefer the real SOA VBT 2015 table; fall back to the committed fixture."""
    if VBT_MALE_NS.exists():
        table_array = load_mortality_csv(VBT_MALE_NS, select_period=25, min_age=18)
        table_name = "SOA VBT 2015 Male NS"
    else:
        table_array = load_mortality_csv(SYNTHETIC_FIXTURE, select_period=3, min_age=18, max_age=60)
        table_name = "Synthetic (VBT table missing)"
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name=table_name,
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="portfolio-parallel-bench")


def _build_blocks(n_deals: int, n_policies: int) -> list[InforceBlock]:
    """One deterministic synthetic block per deal (distinct seeds, same size).

    Blocks are built **once** and shared by every timed sample, so block
    construction (Pydantic validation) is excluded from the measured window —
    the same separation ``run_perf_probe`` makes between block build and
    projection.
    """
    return [
        build_homogeneous_block(n_policies, valuation_date=VALUATION_DATE, seed=100 + i)
        for i in range(n_deals)
    ]


def _build_portfolio(
    blocks: list[InforceBlock], assumptions: AssumptionSet, config: ProjectionConfig
) -> Portfolio:
    """A fresh, **cold** (``cache=False``) portfolio over the shared blocks."""
    portfolio = Portfolio(name="parallel-bench")
    for i, block in enumerate(blocks):
        portfolio.add_deal(
            deal_id=f"DEAL_{i:02d}",
            cedant=f"Cedant{i % 3}",
            inforce=block,
            assumptions=assumptions,
            config=config,
            treaty=CoinsuranceTreaty(cession_pct=0.5, treaty_name=f"coins-{i:02d}"),
        )
    return portfolio


def _assert_identical(candidate: PortfolioResult, baseline: PortfolioResult, label: str) -> None:
    """Exact comparison of every number a run produces. Raises on any drift."""
    np.testing.assert_array_equal(
        candidate.aggregate_net_cash_flow,
        baseline.aggregate_net_cash_flow,
        err_msg=f"{label}: aggregate net cash flow differs from the serial run",
    )
    np.testing.assert_array_equal(
        candidate.aggregate_ceded_nar,
        baseline.aggregate_ceded_nar,
        err_msg=f"{label}: aggregate ceded NAR differs from the serial run",
    )
    for field_name in _AGGREGATE_ARRAYS:
        np.testing.assert_array_equal(
            getattr(candidate.aggregate_cash_flow, field_name),
            getattr(baseline.aggregate_cash_flow, field_name),
            err_msg=f"{label}: aggregate {field_name} differs from the serial run",
        )
    if candidate.total_pv_profits != baseline.total_pv_profits:
        raise AssertionError(
            f"{label}: total_pv_profits {candidate.total_pv_profits!r} != "
            f"serial {baseline.total_pv_profits!r}"
        )
    if [dr.deal_id for dr in candidate.deal_results] != [
        dr.deal_id for dr in baseline.deal_results
    ]:
        raise AssertionError(f"{label}: deal order differs from the serial run")
    for left, right in zip(candidate.deal_results, baseline.deal_results, strict=True):
        if left.profit_test.pv_profits != right.profit_test.pv_profits:
            raise AssertionError(f"{label}: deal {left.deal_id} PV differs from the serial run")


def _time_run(
    blocks: list[InforceBlock],
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    hurdle_rate: float,
    max_workers: int | None,
    k: int,
) -> tuple[PortfolioResult, list[float]]:
    """Best-of-k timing of a cold portfolio run at one worker count.

    Each sample builds its own ``Portfolio`` (``cache=False``) so no projection
    is ever reused across samples, and ``gc.collect()`` runs before the clock
    starts. Returns the last sample's result (for the exactness check) and the
    raw per-sample seconds; the caller keeps the minimum.
    """
    samples: list[float] = []
    result: PortfolioResult | None = None
    for _ in range(k):
        portfolio = _build_portfolio(blocks, assumptions, config)
        gc.collect()
        start = time.perf_counter()
        result = portfolio.run(hurdle_rate, max_workers=max_workers)
        samples.append(time.perf_counter() - start)
    assert result is not None  # k >= 1 is enforced by the CLI parser
    return result, samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-deals", type=int, default=8, help="Deals in the book (default: 8).")
    parser.add_argument(
        "--n-policies", type=int, default=5_000, help="Policies per deal (default: 5000)."
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8],
        help="Worker counts to time (default: 1 2 4 8). 1 is the serial baseline.",
    )
    parser.add_argument("--k", type=int, default=3, help="Timing samples per setting (default: 3).")
    parser.add_argument(
        "--horizon-years", type=int, default=20, help="Projection horizon in years (default: 20)."
    )
    parser.add_argument("--hurdle-rate", type=float, default=0.10, help="Hurdle rate (0.10).")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write JSON here.")
    args = parser.parse_args()

    if args.k < 1:
        parser.error("--k must be at least 1")
    if any(w < 1 for w in args.workers):
        parser.error("--workers entries must be >= 1")

    config = ProjectionConfig(
        valuation_date=VALUATION_DATE,
        projection_horizon_years=args.horizon_years,
        discount_rate=0.05,
    )
    assumptions = _build_assumptions()

    print(
        f"Building {args.n_deals} deals x {args.n_policies:,} policies "
        f"({args.n_deals * args.n_policies:,} policies total)..."
    )
    blocks = _build_blocks(args.n_deals, args.n_policies)

    # Serial baseline: max_workers=None is the shipped default path, not a
    # one-worker pool, so the ratio compares against what callers actually run.
    print("Timing the serial baseline (max_workers=None)...")
    baseline_result, baseline_samples = _time_run(
        blocks, assumptions, config, args.hurdle_rate, None, args.k
    )
    serial_best = min(baseline_samples)

    rows: list[dict[str, object]] = [
        {
            "max_workers": None,
            "best_of_k_seconds": serial_best,
            "samples_seconds": baseline_samples,
            "speedup_vs_serial": 1.0,
            "bit_identical": True,
        }
    ]

    for workers in args.workers:
        print(f"Timing max_workers={workers}...")
        result, samples = _time_run(blocks, assumptions, config, args.hurdle_rate, workers, args.k)
        _assert_identical(result, baseline_result, f"max_workers={workers}")
        best = min(samples)
        rows.append(
            {
                "max_workers": workers,
                "best_of_k_seconds": best,
                "samples_seconds": samples,
                "speedup_vs_serial": serial_best / best if best > 0.0 else None,
                "bit_identical": True,
            }
        )

    payload: dict[str, object] = {
        "n_deals": args.n_deals,
        "n_policies_per_deal": args.n_policies,
        "projection_horizon_years": args.horizon_years,
        "hurdle_rate": args.hurdle_rate,
        "k": args.k,
        "cache": False,
        "valuation_date": VALUATION_DATE.isoformat(),
        "total_pv_profits": baseline_result.total_pv_profits,
        "rows": rows,
    }

    print()
    print(f"{'max_workers':>12} | {'best-of-k (s)':>14} | {'speed-up':>9} | bit-identical")
    print(f"{'-' * 12}-+-{'-' * 14}-+-{'-' * 9}-+--------------")
    for row in rows:
        label = "serial" if row["max_workers"] is None else str(row["max_workers"])
        speedup = row["speedup_vs_serial"]
        speedup_text = "—" if speedup is None else f"{speedup:.2f}x"
        print(
            f"{label:>12} | {row['best_of_k_seconds']:>14.3f} | "
            f"{speedup_text:>9} | {'yes' if row['bit_identical'] else 'NO'}"
        )
    print()
    print("Wall-clock ratios are INFORMATIONAL (harness design rule, 2026-07-12).")

    if args.output is not None:
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
