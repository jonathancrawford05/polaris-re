#!/usr/bin/env python3
"""
scale_benchmark.py — Time the vectorized projection engine across block sizes.

Produces the timing table published in the README's *Performance* section,
backing the "vectorized, no loops over policies" claim with reproducible
numbers. It times the production pricing path
(``get_product_engine(...).project()``) on deterministic synthetic TERM blocks.

Usage:
    # Default sizes (1K / 10K / 100K), pretty table to stdout:
    uv run python scripts/scale_benchmark.py

    # Full published range (1K -> 500K) written to a Markdown file:
    uv run python scripts/scale_benchmark.py --sizes 1000 10000 100000 500000 \
        -o docs/PERFORMANCE.md

Note: 500K policies over a 20-year monthly projection needs ~10 GB RAM and
~60 s; drop the largest size on a constrained machine. Sizes must be ascending.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Allow "uv run python scripts/scale_benchmark.py" without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polaris_re.analytics.scale_benchmark import run_scale_benchmark
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import (
    MortalityTable,
    MortalityTableSource,
)
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import load_mortality_csv

REPO_ROOT = Path(__file__).resolve().parents[1]
VBT_MALE_NS = REPO_ROOT / "data" / "mortality_tables" / "soa_vbt_2015_male_ns.csv"
SYNTHETIC_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_select_ultimate.csv"


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
    return AssumptionSet(mortality=mortality, lapse=lapse, version="scale-benchmark")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[1_000, 10_000, 100_000],
        help="Ascending block sizes to benchmark (default: 1000 10000 100000).",
    )
    parser.add_argument(
        "--horizon-years", type=int, default=20, help="Projection horizon in years (default: 20)."
    )
    parser.add_argument(
        "--discount-rate", type=float, default=0.05, help="Discount rate (default: 0.05)."
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="Write the Markdown table to this file."
    )
    args = parser.parse_args()

    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=args.horizon_years,
        discount_rate=args.discount_rate,
    )
    assumptions = _build_assumptions()

    print(f"Benchmarking sizes {args.sizes} — this may take a while for large blocks...")
    report = run_scale_benchmark(args.sizes, assumptions, config, engine_label="TermLife")
    markdown = report.to_markdown()

    print("\n" + markdown + "\n")
    if args.output is not None:
        args.output.write_text(markdown + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
