#!/usr/bin/env python3
"""Slice R2 (ADR-259): the ILEC trial runner — MAINTAINER-RUN, tier L.

Follow ``docs/RUNBOOK_gam_real_data_trial.md``. This script never writes a row, a cell key, a
level name, a count, a rate, a fitted curve, a coefficient or a contrast to the file you commit;
``polaris_re.gam.real_data_trial.dumps`` enforces that and refuses anything else.

Subcommands
-----------
check-window  Print exposure by calendar year to the terminal ONLY (the 2018-2019 composition
              check); writes nothing.
prepare       Load the ILEC file, assert the data rules, write the loader cells to --work.
run-cell      One (formula, granularity): Polaris fit + mgcv fit + comparison -> one result file.
all           prepare (if needed) + every run-cell (restartable: finished cells are skipped) +
              collect.
collect       Merge the per-cell result files into the single committable JSON.

Provenance (ADR-193): see ``real_data_trial.CLAIM``. Polaris and mgcv each read the cells and
the formula string; neither reads the other's output. Timings are MEASUREMENTs.
"""

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.experience_loaders import ILEC_2012_19_COLUMN_MAP, load_ilec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import real_data_trial as trial

REPO = Path(__file__).resolve().parent.parent
CEILING_S = 600.0
LOADER_CELLS = "loader_cells.parquet"


def _git_commit() -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _cell_name(formula: str, granularity: str) -> str:
    return f"{formula}_{granularity}"


def cmd_check_window(args: argparse.Namespace) -> int:
    cells = load_ilec(args.ilec, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP, aggregate=True)
    by_year = (
        cells.group_by("calendar_year")
        .agg(pl.col(trial.EXPOSURE).sum().alias("exposure"))
        .sort("calendar_year")
        .with_columns((pl.col("exposure") / pl.col("exposure").sum()).alias("share"))
    )
    print("LOCAL ONLY — do not paste, commit or screenshot this table.")
    print(by_year)
    print("Look for a step in share at 2018-2019 (a new submitting company). See the runbook.")
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    cells = load_ilec(args.ilec, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP, aggregate=True)
    if args.years:
        lo, hi = (int(v) for v in args.years.split("-"))
        cells = cells.filter(pl.col("calendar_year").is_between(lo, hi))
    trial.assert_data_rules(cells)
    cells.write_parquet(work / LOADER_CELLS)
    print(f"prepared {cells.height} loader cells -> {work / LOADER_CELLS} (LOCAL ONLY)")
    return 0


def _shell(cmd: str, repo: Path, work: Path) -> list[str]:
    return shlex.split(cmd.format(work=str(work), repo=str(repo)))


def cmd_run_cell(args: argparse.Namespace) -> int:
    work = Path(args.work)
    spec = next(f for f in trial.FORMULAS if f.name == args.formula)
    name = _cell_name(spec.name, args.granularity)
    out_dir = work / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "formula": spec.name,
        "granularity": args.granularity,
        "role": spec.role,
        "family": spec.family,
        "select": spec.select,
        "status": "failed",
    }
    try:
        loader = pl.read_parquet(work / LOADER_CELLS)
        data = trial.aggregate_cells(loader, spec, args.granularity)
        del loader
        factors = [c for c in ("face_band", "smoker") if c in data.columns]
        data = trial.to_factor_frame(data, factors)
        levels = {c: list(data[c].cat.get_categories()) for c in factors}
        result["n_cells"] = data.height
        if spec.name == "S1" and float(data["death_rate"].max()) > 1.0:
            result.update(
                status="not_run",
                refusal="S1 not run: a cell has deaths above exposure (proportion above one).",
            )
            return _write(out_dir, name, result)

        side = trial.fit_polaris(
            spec, data, repeats=args.repeats, budget_s=args.budget_s, profile=not args.no_profile
        )
        if side.status == "refused":
            result.update(
                status="refused",
                refusal=trial.sanitise_refusal(
                    side.refusal or ""  # face_band is renamed B00.. before fitting
                ),
            )
            return _write(out_dir, name, result)
        assert side.fit is not None
        summ = side.fit.summary()
        best = min(side.fit_seconds)
        result["polaris"] = {
            "converged": bool(side.fit.converged),
            "n_iterations": summ.n_iterations,
            "n_function_evals": summ.n_function_evals,
            "rank_deficient_warning": side.rank_deficient,
            "edf_total": summ.edf_total,
            "reml_score": summ.reml_score,
            "scale": summ.scale,
            "peak_rss_mb": side.peak_rss_mb,
            "fit_seconds": side.fit_seconds,
            "best_seconds": best,
            "repeats_used": len(side.fit_seconds),
            "phase_seconds": side.phase_seconds,
        }
        result["n_coef"] = int(side.fit.coef.shape[0])
        result["n_penalties"] = len(side.fit.log_lambda)
        result["n_smooths"] = len(summ.smooths)
        result["terms"] = trial.terms_block(summ.smooths)
        result["timing"] = {"ceiling_seconds": CEILING_S, "ceiling_met": best <= CEILING_S}

        cdir = work / name
        cdir.mkdir(parents=True, exist_ok=True)
        data.write_csv(cdir / "cells.csv")
        (cdir / "spec.json").write_text(
            json.dumps(
                {
                    "formula": spec.formula,
                    "family": spec.family,
                    "weights": spec.weights,
                    "select": spec.select,
                    "factors": levels,
                    "repeats": args.repeats,
                    "budget_s": args.budget_s,
                }
            )
        )
        r_work = args.r_work or str(work)
        rel = f"{r_work}/{name}"
        cmd = [
            *_shell(args.r_command, REPO, work),
            args.r_script or str(REPO / "scripts" / "gam_real_data_trial.R"),
            f"{rel}/cells.csv",
            f"{rel}/spec.json",
            f"{rel}/mgcv.json",
        ]
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        r_wall = time.perf_counter() - t0
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)  # local terminal only
            result["status"] = "failed"
            return _write(out_dir, name, result)
        m = json.loads((cdir / "mgcv.json").read_text())
        m["fit_seconds"] = np.atleast_1d(m["fit_seconds"]).tolist()  # R unboxes length-1
        agree = trial.compare(side, m)
        m_best = min(m["fit_seconds"])
        comparable = args.polaris_env == args.mgcv_env and args.polaris_arch == args.mgcv_arch
        result["status"] = "fitted"
        result["mgcv"] = {
            "converged": bool(m["converged"]),
            "n_iterations": m["outer_iter"],
            "edf_total": m["edf_total"],
            "reml_score": m["reml"],
            "scale": m["scale"],
            "fit_seconds": m["fit_seconds"],
            "best_seconds": m_best,
            "repeats_used": len(m["fit_seconds"]),
            "peak_rss_mb": m.get("peak_mb_gc"),
        }
        _ = r_wall  # includes container start and CSV read; deliberately NOT reported as a fit time
        result["agreement"] = {
            **{k: getattr(agree, k) for k in agree.__dataclass_fields__},
            "all_gates_met": all(
                (agree.eta_gate_met, agree.edf_gate_met, agree.se_gate_met, agree.scaled_gate_met)
            ),
            "ratio_polaris_over_mgcv": best / m_best if m_best > 0 else None,
            "ratio_comparable": comparable,
        }
        return _write(out_dir, name, result)
    except PolarisValidationError as exc:
        print(f"STOP AND REPORT: {exc}", file=sys.stderr)
        result["status"] = "failed"
        return _write(out_dir, name, result)
    except Exception as exc:  # a failed cell is a result, not a crash; class name only is kept
        print(f"{name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        result["status"] = "failed"
        return _write(out_dir, name, result)


def _write(out_dir: Path, name: str, result: dict[str, object]) -> int:
    (out_dir / f"{name}.json").write_text(trial.dumps(result))
    print(f"{name}: {result['status']}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    work = Path(args.work)
    machine = json.loads(Path(args.machine_json).read_text()) if args.machine_json else {}
    results = [json.loads(p.read_text()) for p in sorted((work / "results").glob("*.json"))]
    out = {
        "schema_version": 1,
        "tier": "tier L",
        "claim": trial.CLAIM.claim,
        "oracle_image_digest": args.digest,
        "openblas_num_threads": str(args.threads),
        "polaris_commit": _git_commit(),
        "image_architecture": args.mgcv_arch if args.mgcv_arch != "native" else None,
        "host_architecture": args.host_arch,
        "polaris_environment": args.polaris_env,
        "mgcv_environment": args.mgcv_env,
        "machine": trial.machine_description(machine),
        "results": results,
    }
    if args.r_version:
        out["r_version"] = args.r_version
    if args.mgcv_version:
        out["mgcv_version"] = args.mgcv_version
    Path(args.out).write_text(trial.dumps(out))
    print(f"wrote {args.out}: {len(results)} cell results (derived scalars only)")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    work = Path(args.work)
    if not (work / LOADER_CELLS).exists():
        cmd_prepare(args)
    for f in trial.FORMULAS:
        for g in trial.GRANULARITIES:
            if (work / "results" / f"{_cell_name(f.name, g)}.json").exists():
                continue
            sub = argparse.Namespace(**{**vars(args), "formula": f.name, "granularity": g})
            cmd_run_cell(sub)
    return cmd_collect(args)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--work", required=True, help="LOCAL scratch dir (never committed)")

    def run_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--repeats", type=int, default=3)
        sp.add_argument("--budget-s", type=float, default=300.0, dest="budget_s")
        sp.add_argument("--no-profile", action="store_true")
        sp.add_argument("--r-command", default="Rscript")
        sp.add_argument("--r-work", default=None)
        sp.add_argument("--r-script", default=None)
        sp.add_argument("--polaris-env", choices=["native", "container"], default="native")
        sp.add_argument("--mgcv-env", choices=["native", "container"], default="container")
        sp.add_argument("--polaris-arch", default="native")
        sp.add_argument("--mgcv-arch", default="native")

    def collect_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--out", required=True)
        sp.add_argument("--digest", required=True)
        sp.add_argument("--threads", type=int, required=True)
        sp.add_argument("--host-arch", dest="host_arch", required=True)
        sp.add_argument("--machine-json", dest="machine_json", default=None)
        sp.add_argument("--r-version", dest="r_version", default=None)
        sp.add_argument("--mgcv-version", dest="mgcv_version", default=None)

    for name, fn in (("check-window", cmd_check_window), ("prepare", cmd_prepare)):
        sp = sub.add_parser(name)
        sp.add_argument("--ilec", required=True)
        if name == "prepare":
            common(sp)
            sp.add_argument("--years", default=None, help="calendar-year window, e.g. 2012-2017")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("run-cell")
    common(sp)
    run_opts(sp)
    sp.add_argument("--formula", required=True, choices=[f.name for f in trial.FORMULAS])
    sp.add_argument("--granularity", required=True, choices=list(trial.GRANULARITIES))
    sp.set_defaults(fn=cmd_run_cell)
    sp = sub.add_parser("collect")
    common(sp)
    collect_opts(sp)
    sp.add_argument("--polaris-env", choices=["native", "container"], default="native")
    sp.add_argument("--mgcv-env", choices=["native", "container"], default="container")
    sp.add_argument("--mgcv-arch", default="native")
    sp.set_defaults(fn=cmd_collect)
    sp = sub.add_parser("all")
    common(sp)
    sp.add_argument("--ilec", required=True)
    sp.add_argument("--years", default=None)
    run_opts(sp)
    collect_opts(sp)
    sp.set_defaults(fn=cmd_all)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
