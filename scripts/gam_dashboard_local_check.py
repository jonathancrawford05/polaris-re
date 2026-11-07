#!/usr/bin/env python3
"""Local check of the D1 cost model on one real cell (PR #277, maintainer question 1).

MAINTAINER-RUN, tier L. Headless: runs the same functions the page's GAM section calls, so the
numbers match the page without clicking through it. For each engine it prints the pre-run
prediction (time and RAM, as the page warns before a fit) and then the actual time and peak
memory. Each engine runs in its own process so the memory reading is that fit's own.

Data stays where it is: the cell directory is local scratch and only the printed scalars leave.

USAGE:
    uv run python scripts/gam_dashboard_local_check.py "$WORK/T1_mid"
    uv run python scripts/gam_dashboard_local_check.py "$WORK/T1_mid" --engines gam
"""

import argparse
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import polars as pl

from polaris_re.dashboard.views.gam_fit_section import (
    FAMILIES,
    _model,
    prepare_frame,
    run_gam_request,
)
from polaris_re.gam.cost_model import estimate_n_coef, physical_memory_gb, pre_run_warning


def _spec(cell_dir: Path) -> tuple[str, str]:
    """The formula and the FULL family string (the link is kept: ``binomial(link="cloglog")``).

    A spec the page cannot reproduce is refused, never silently simplified: an unsupported
    family, or a weights column (``run_gam_request`` takes none).
    """
    spec = json.loads((cell_dir / "spec.json").read_text())
    family = str(spec["family"]).strip()
    base = family.split("(")[0].strip()
    if base not in FAMILIES:
        raise SystemExit(f"spec family {family!r} is not one the page offers: {FAMILIES}")
    if spec.get("weights"):
        raise SystemExit(
            f"spec has weights={spec['weights']!r}; the page and this check fit without weights, "
            "so the result would not be the same model. Refusing rather than dropping them."
        )
    return spec["formula"], family


def _peak_rss_mb() -> float:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes.
    return raw / 1024**2 if platform.system() == "Darwin" else raw / 1024


def child(cell_dir: Path, engine: str) -> None:
    formula, family = _spec(cell_dir)
    data = prepare_frame(pl.read_csv(cell_dir / "cells.csv"))
    res = run_gam_request(data, formula, family, engine)  # type: ignore[arg-type]
    out: dict[str, object] = {"engine": engine, "peak_rss_mb": round(_peak_rss_mb(), 1)}
    if res.fit is None:
        out["refused"] = res.message
    else:
        out.update(
            seconds=round(res.seconds, 2),
            edf_total=round(res.fit.edf_total, 3),
            converged=bool(res.fit.converged),
            iterations=res.fit.n_function_evals,
        )
    print("CHILD_RESULT " + json.dumps(out))


def parent(cell_dir: Path, engines: list[str]) -> None:
    formula, family = _spec(cell_dir)
    data = prepare_frame(pl.read_csv(cell_dir / "cells.csv"))
    n_rows, n_coef = data.height, estimate_n_coef(formula, data)
    print(f"cell: {cell_dir.name}  rows: {n_rows}  coef: {n_coef}  family: {family}")
    print(f"formula: {formula}")
    print(f"machine RAM: {physical_memory_gb()} GB  ({platform.platform()})")
    for engine in engines:
        warn = pre_run_warning(
            _model(),
            engine,
            n_rows,
            n_coef,  # type: ignore[arg-type]
            formula=formula,
            family=family,
            available_gb=physical_memory_gb(),
        )
        print(f"\n=== {engine} ===")
        print("PREDICTED (shown before the run):")
        for line in warn.lines:
            print(f"  - {line}")
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, __file__, str(cell_dir), "--child", engine],
            capture_output=True,
            text=True,
            check=False,
        )
        wall = time.perf_counter() - t0
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("CHILD_RESULT ")), None)
        if line is None:
            print(f"ACTUAL: process failed (exit {proc.returncode}); last stderr lines:")
            print("\n".join(proc.stderr.splitlines()[-15:]))
            continue
        actual = json.loads(line.removeprefix("CHILD_RESULT "))
        print("ACTUAL:")
        for key, value in actual.items():
            print(f"  {key}: {value}")
        print(f"  wall_seconds_incl_startup: {wall:.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("cell_dir", type=Path)
    ap.add_argument("--engines", nargs="+", default=["gam", "bam"], choices=["gam", "bam"])
    ap.add_argument("--child", choices=["gam", "bam"], help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        child(args.cell_dir, args.child)
    else:
        parent(args.cell_dir, args.engines)


if __name__ == "__main__":
    main()
