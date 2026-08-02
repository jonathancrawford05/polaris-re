#!/usr/bin/env python3
"""
perf_history.py — Append the current commit's perf probe to perf/history.jsonl
and check the whole series for slow multi-month creep.

This is the long-baseline companion to the same-job head-vs-main gate
(``scripts/perfbench.py`` / ADR-176). That gate compares HEAD against
``origin/main`` in one CI job, so it catches a single PR that makes the engine
structurally slower. What it *structurally cannot* catch is slow cumulative
creep: because its baseline is always the moving ``main`` tip, a long run of
merges that each add a fraction of a percent walks the engine steadily slower
without any single comparison ever firing. This script closes that gap: it
records **one deterministic-first row per commit** into a committed append-only
log and runs creep detection over the earliest-vs-recent windows of the series
(``analytics/perf_history``).

Per the maintainer design rule (2026-07-12) — and *more* so across a series
recorded on different CI machines — only the deterministic, machine-portable
``peak_mib`` may gate; the wall-time ratio is advisory. The exit status is
non-zero iff the series shows **structural (MiB-peak) creep**; wall-time / config
drift only inform.

Usage:
    # Record HEAD's probe and check the series (the intended per-merge call):
    uv run python scripts/perf_history.py -o perf_history.json

    # Analyse the existing log without appending a new row:
    uv run python scripts/perf_history.py --check-only

    # Custom probe size / creep knobs:
    uv run python scripts/perf_history.py --n-policies 1000 --k 3 \
        --window 5 --mib-creep-delta 4 --band 1.25

The mortality basis is the committed ``tests/fixtures/synthetic_select_ultimate.csv``
(present on every checkout; the generated ``data/`` tables are not), so the probe
is fast and offline-safe — the same fixture ``perfbench.py`` uses, so the two
harnesses measure the *same* hot path.
"""

import argparse
import contextlib
import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.perf_harness import PerfReport, run_perf_probe  # noqa: E402
from polaris_re.analytics.perf_history import (  # noqa: E402
    PerfHistoryRow,
    append_history_row,
    detect_creep,
    load_history,
)
from polaris_re.assumptions.assumption_set import AssumptionSet  # noqa: E402
from polaris_re.assumptions.lapse import LapseAssumption  # noqa: E402
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource  # noqa: E402
from polaris_re.core.policy import Sex, SmokerStatus  # noqa: E402
from polaris_re.core.projection import ProjectionConfig  # noqa: E402
from polaris_re.utils.table_io import load_mortality_csv  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_select_ultimate.csv"
DEFAULT_HISTORY = REPO_ROOT / "perf" / "history.jsonl"


def _git(*args: str) -> str:
    """Return the stripped stdout of a ``git`` command run at the repo root."""
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _build_report(args: argparse.Namespace) -> PerfReport:
    """Run the deterministic perf probe on HEAD's engine and return the report."""
    val = args.valuation_date
    # Setup may print progress (e.g. load_mortality_csv); silence it so only our
    # summary reaches stdout.
    with contextlib.redirect_stdout(io.StringIO()):
        table_array = load_mortality_csv(FIXTURE, select_period=3, min_age=18, max_age=60)
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
            valuation_date=val,
            projection_horizon_years=args.horizon_years,
            discount_rate=args.discount_rate,
        )
        report = run_perf_probe(assumptions, config, n_policies=args.n_policies, k=args.k)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
        help="Append-only history log (default: perf/history.jsonl).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Analyse the existing log without appending HEAD's probe.",
    )
    parser.add_argument(
        "--n-policies", type=int, default=3_000, help="Fixed block size to project (default: 3000)."
    )
    parser.add_argument(
        "--k", type=int, default=5, help="Timing samples; report keeps the min (default: 5)."
    )
    parser.add_argument(
        "--horizon-years", type=int, default=10, help="Projection horizon in years (default: 10)."
    )
    parser.add_argument(
        "--discount-rate", type=float, default=0.05, help="Discount rate (default: 0.05)."
    )
    parser.add_argument(
        "--valuation-date",
        type=date.fromisoformat,
        default=date(2025, 1, 1),
        help="Pinned valuation date YYYY-MM-DD (ADR-074; default: 2025-01-01).",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="Rows per creep-comparison window (earliest N vs latest N; default: 3).",
    )
    parser.add_argument(
        "--mib-creep-delta",
        type=int,
        default=4,
        help="Median peak-MiB rise (recent over baseline) that gates as creep (default: 4).",
    )
    parser.add_argument(
        "--band",
        type=float,
        default=1.25,
        help="Wall-time recent/baseline ratio that raises an advisory alert (default: 1.25).",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="Write the creep-verdict JSON here."
    )
    args = parser.parse_args()

    if not args.check_only:
        commit = _git("rev-parse", "HEAD")
        commit_date = _git("show", "-s", "--format=%cI", "HEAD")
        existing = load_history(args.history)
        # Idempotency: a per-merge CI job re-run on the same commit must not
        # double-append (which would sit two identical rows in a window and skew
        # the median). The log is per-commit, append-once — so guard on membership
        # anywhere in the series, not just the tail, which stays correct once the
        # one-off backfill (#63) inserts rows for non-tip commits.
        if any(r.commit == commit for r in existing):
            print(
                f"perf_history: {commit[:12]} already recorded — skipping append (idempotent).",
                file=sys.stderr,
            )
        else:
            print(
                f"perf_history: probing HEAD {commit[:12]} "
                f"(n_policies={args.n_policies}, k={args.k})...",
                file=sys.stderr,
            )
            report = _build_report(args)
            row = PerfHistoryRow.from_report(report, commit=commit, commit_date=commit_date)
            append_history_row(row, args.history)
            print(
                f"perf_history: appended row for {commit[:12]} to {args.history}",
                file=sys.stderr,
            )

    rows = load_history(args.history)
    verdict = detect_creep(
        rows,
        window=args.window,
        mib_creep_delta=args.mib_creep_delta,
        band=args.band,
    )
    payload = verdict.to_verdict_dict()
    rendered = json.dumps(payload, indent=2)

    # Human summary to stderr; machine verdict to stdout / file.
    if verdict.insufficient_data:
        print(
            f"perf_history: {verdict.n_rows} row(s) — need >= {2 * args.window} per probe "
            f"for a creep verdict (backfill the log). No alert.",
            file=sys.stderr,
        )
    else:
        print(f"perf_history verdict: {payload['verdict']}", file=sys.stderr)
        for pc in verdict.probe_creeps:
            ratio = "n/a" if pc.wall_time_ratio is None else f"{pc.wall_time_ratio:.3f}x"
            drift = " CONFIG-DRIFT" if pc.config_drift else ""
            print(
                f"  {pc.probe}: peak MiB {pc.peak_mib_baseline:g} -> {pc.peak_mib_recent:g} "
                f"(Δ{pc.peak_mib_delta:+g}, creep={'YES' if pc.peak_mib_creep else 'no'}) "
                f"wall-time recent/baseline={ratio}{drift}",
                file=sys.stderr,
            )

    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"perf_history: wrote {args.output}", file=sys.stderr)
    else:
        print(rendered)

    if verdict.has_structural_creep:
        print(
            "perf_history: STRUCTURAL CREEP — median peak MiB rose beyond the "
            "threshold across the series (gate would fail).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
