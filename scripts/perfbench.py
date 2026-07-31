#!/usr/bin/env python3
"""
perfbench.py — Benchmark the projection engine head-vs-main in one process/job.

Runs the deterministic perf probe (``analytics/perf_harness.run_perf_probe``) on
the current worktree ("head") **and** on a throwaway ``git worktree`` checkout of
a reference ("main"), then diffs the two with
``analytics/perf_harness.diff_reports``. Because both runs happen on the *same
machine in the same invocation*, the 2-3x run-to-run wall-clock noise cancels in
the head/main **ratio** — the only wall-time signal the harness trusts (maintainer
design rule, 2026-07-12). The deterministic structural metrics (counts +
output fingerprint) gate; the wall-time ratio and the peak-MiB delta only alert.

Both branches are measured by executing the *same* self-contained probe snippet
as a subprocess with ``sys.path`` pointed at that branch's ``src`` (the trick
``scripts/scale_benchmark.py`` uses), so each branch times *its own* engine code
via *its own* harness copy while sharing the current interpreter's installed
dependencies. The committed ``tests/fixtures/synthetic_select_ultimate.csv`` is
the mortality basis (present on both branches; the generated ``data/`` tables are
not, so they can't be used across a worktree).

Usage:
    # Compare the current worktree against origin/main, write perf.json:
    uv run python scripts/perfbench.py -o perf.json

    # Smaller/faster probe, custom ref and alert band:
    uv run python scripts/perfbench.py --ref origin/main --n-policies 1000 \
        --k 3 --band 1.5 -o perf.json

Exit status is non-zero iff the diff carries a **hard delta** (a structural
mismatch or an unmatched probe) — the gate a later CI slice consumes. Wall-time
and memory alerts are advisory and never change the exit status.
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# Allow "uv run python scripts/perfbench.py" without an editable install; this is
# the HEAD src, used both for the diff import here and as the head probe worktree.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.perf_harness import PerfReport, diff_reports  # noqa: E402

# The probe body run inside each worktree. Kept to Slice-1 public APIs only, so it
# executes identically on head and on an origin/main checkout. It prints the
# report as native Pydantic JSON (round-trips via PerfReport.model_validate_json)
# and nothing else on stdout; the leading sys.path.insert selects THIS worktree's
# src over any installed editable package.
_PROBE_SNIPPET = """\
import contextlib
import io
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, "src")
from polaris_re.analytics.perf_harness import run_perf_probe
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import load_mortality_csv

# Setup + probe may print progress (e.g. load_mortality_csv); capture it so the
# ONLY thing on real stdout is the report JSON the parent parses.
with contextlib.redirect_stdout(io.StringIO()):
    table_array = load_mortality_csv(
        Path("tests/fixtures/synthetic_select_ultimate.csv"),
        select_period=3, min_age=18, max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015, table_name="perfbench",
        table_array=table_array, sex=Sex.MALE, smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({{1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03}})
    assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="perfbench")
    config = ProjectionConfig(
        valuation_date=date({year}, {month}, {day}),
        projection_horizon_years={horizon}, discount_rate={rate!r},
    )
    report = run_perf_probe(assumptions, config, n_policies={n_policies}, k={k})
sys.stdout.write(report.model_dump_json())
"""


def _run_probe(worktree: Path, snippet: str, *, label: str) -> PerfReport:
    """Execute the probe snippet in ``worktree`` and parse the emitted report.

    Runs with ``cwd=worktree`` so the snippet's ``sys.path.insert(0, "src")`` and
    the relative fixture path resolve against that branch's tree; the interpreter
    (and thus every installed dependency) is the current one. Stdout must be the
    single ``model_dump_json`` line — anything else is treated as a probe failure.
    """
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"perfbench: {label} probe failed (exit {proc.returncode}).\n"
            f"--- stderr ---\n{proc.stderr}"
        )
    try:
        return PerfReport.model_validate_json(proc.stdout.strip())
    except Exception as exc:
        raise SystemExit(
            f"perfbench: could not parse {label} probe output as a PerfReport: {exc}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        ) from exc


def _add_worktree(ref: str, dest: Path) -> None:
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(dest), ref],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _remove_worktree(dest: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(dest)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default="origin/main",
        help="Baseline git ref to compare against (default: origin/main).",
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
        "--band",
        type=float,
        default=1.5,
        help="Wall-time head/main ratio alert threshold (default: 1.5).",
    )
    parser.add_argument(
        "--mib-alert-delta",
        type=int,
        default=4,
        help="peak-MiB head-over-main increase that alerts (default: 4).",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip 'git fetch' of the ref's remote before checkout.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="Write the perf.json payload here."
    )
    args = parser.parse_args()

    val = args.valuation_date
    snippet = _PROBE_SNIPPET.format(
        year=val.year,
        month=val.month,
        day=val.day,
        horizon=args.horizon_years,
        rate=args.discount_rate,
        n_policies=args.n_policies,
        k=args.k,
    )

    # Best-effort fetch so 'origin/<branch>' refs are current (skippable / offline-safe).
    if not args.no_fetch and "/" in args.ref:
        remote = args.ref.split("/", 1)[0]
        subprocess.run(
            ["git", "fetch", remote], cwd=REPO_ROOT, check=False, capture_output=True, text=True
        )

    print(f"perfbench: probing HEAD (n_policies={args.n_policies}, k={args.k})...", file=sys.stderr)
    head = _run_probe(REPO_ROOT, snippet, label="head")

    worktree = REPO_ROOT / ".perfbench_main_worktree"
    _remove_worktree(worktree)  # clear a stale one from an interrupted prior run
    print(f"perfbench: checking out {args.ref} and probing...", file=sys.stderr)
    _add_worktree(args.ref, worktree)
    try:
        main_report = _run_probe(worktree, snippet, label=f"main ({args.ref})")
    finally:
        _remove_worktree(worktree)

    diff = diff_reports(head, main_report, band=args.band, mib_alert_delta=args.mib_alert_delta)
    payload: dict[str, object] = {
        "ref": args.ref,
        "diff": diff.to_diff_dict(),  # verdict + per-probe detail, gate-signal first
        "head": head.to_perf_dict(),
        "main": main_report.to_perf_dict(),
    }
    rendered = json.dumps(payload, indent=2)

    # Human summary to stderr; machine payload to stdout / file.
    verdict = diff.to_diff_dict()["verdict"]
    print(f"perfbench verdict: {verdict}", file=sys.stderr)
    for pd in diff.probe_diffs:
        ratio = "n/a" if pd.wall_time_ratio is None else f"{pd.wall_time_ratio:.3f}x"
        print(
            f"  {pd.probe}: structural={'OK' if pd.structural_match else 'MISMATCH'} "
            f"wall-time head/main={ratio} peak MiB Δ={pd.peak_mib_delta:+d}",
            file=sys.stderr,
        )

    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"perfbench: wrote {args.output}", file=sys.stderr)
    else:
        print(rendered)

    if diff.has_hard_delta:
        print("perfbench: HARD DELTA — structural regression (gate would fail).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
