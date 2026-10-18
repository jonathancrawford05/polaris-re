#!/usr/bin/env python3
"""Slice R3 Stage B (ADR-260 amendments 4-5): the maintainer's REAL-CELL check — MAINTAINER-RUN,
tier L. Follow ``docs/RUNBOOK_bam_local_stage_b.md``.

For one trial cell directory (``cells.csv`` + ``spec.json`` written by
``gam_real_data_trial.py run-cell``):

1. **Polaris** fits ``gam(method="fREML", discrete=True)`` (timed best-of-``--repeats``, peak RSS,
   iterations, edf, ``Vp`` se).
2. **mgcv** fits ``bam(fREML, discrete=TRUE)`` once per ``discrete.mf`` seed (mgcv's 8547, then
   six others) via ``bam_local_seed_probe.R`` (per-row output stays in the scratch dir).
3. The two are reduced to SCALARS: the R2 gates against ``bam`` at the default seed (the claim),
   Polaris's distance to every other seed, and ``bam``'s own seed spread (REFERENCE_INTERNAL,
   the reference's noise floor). If ``probe_gam.json`` exists in the cell dir (from
   ``bam_attribution_local.sh``) the exact-REML ``gam`` baseline is added.

The committable file holds scalars only and is checked against a whitelist before it is written.
Provenance (ADR-193): Polaris vs ``bam`` columns INDEPENDENT (``gam()`` takes the cells and the
formula; ``bam`` the same); the seed spread REFERENCE_INTERNAL; times are MEASUREMENTs.
"""

import argparse
import json
import platform
import shlex
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import GamFit, gam
from polaris_re.gam.real_data_trial import (
    EDF_GATE,
    ETA_GATE,
    SCALED_ETA_FLAG,
    SCALED_ETA_GATE,
    SE_REL_GATE,
    _repeat,
    peak_rss_mb,
    sanitise_refusal,
)

REPO = Path(__file__).resolve().parent.parent
CEILING_S: Final = 600.0
OUTPUT_KEYS: Final = frozenset(
    {
        "schema_version", "tier", "cell", "polaris_commit", "r_version", "mgcv_version",
        "openblas_num_threads", "machine", "n_rows", "n_coef", "n_penalties", "polaris", "mgcv",
        "agreement_vs_default_seed", "seed_noise_floor", "gam_baseline", "fit_seconds",
        "best_seconds", "repeats_used", "peak_rss_mb", "n_iterations", "converged", "edf_total",
        "ceiling_seconds", "ceiling_met", "seeds", "iterations_by_seed", "elapsed_by_seed",
        "eta_max_abs", "eta_rms", "eta_scaled_max", "edf_total_abs", "se_rel_max",
        "eta_gate_met", "edf_gate_met", "se_gate_met", "scaled_gate_met", "scaled_flag",
        "all_gates_met", "polaris_vs_other_seeds_min", "polaris_vs_other_seeds_max",
        "bam_eta_spread", "bam_max_dev_from_default", "envelope_excess_max",
        "n_rows_outside_envelope", "eta_max_abs_vs_seed_median", "bam_seed_eta_max_abs_vs_seed_median", "bam_edf_total_spread",
        "spread_at_least_residual", "eta_max_abs_gam_vs_bam", "edf_total_gam", "chip",
        "python", "os", "status", "refusal", "trials_floor", "n_cells_floored", "ratio_polaris_over_bam_default",
        "bam_default_seconds", "claim", "localisation", "reml_triangle", "eta_max_abs_polaris_reml_vs_polaris_bam", "eta_max_abs_polaris_reml_vs_bam", "polaris_reml_seconds", "polaris_reml_edf_total", "abs_eta_diff_quantiles", "q50", "q90", "q99", "q999",
        "n_rows_over_0p01", "n_rows_over_0p1", "n_rows_over_0p5", "polaris_log10_sp", "bam_log10_sp",
        "polaris_smooth_edf", "bam_smooth_edf", "polaris_smooth_kinds", "bam_default_smooth_kinds",
    }
)  # fmt: skip


def _check_whitelist(obj: object, path: str = "$") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in OUTPUT_KEYS:
                raise SystemExit(f"refusing to write non-whitelisted key {path}.{k}")
            _check_whitelist(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_whitelist(v, f"{path}[{i}]")


def _frame(cell: Path) -> tuple[pl.DataFrame, dict[str, object]]:
    spec = json.loads((cell / "spec.json").read_text())
    df = pl.read_csv(cell / "cells.csv")
    casts = [pl.col(n).cast(pl.String).cast(pl.Enum(lv)) for n, lv in spec["factors"].items()]
    names = list(spec["factors"])
    return df.with_columns([c.alias(n) for c, n in zip(casts, names, strict=True)]), spec


def _git_commit() -> str:
    """HEAD sha, or ``"unknown"``. ``check=False`` covers a non-zero exit (not a checkout) but
    NOT a missing binary: the runtime image is ``python:3.12-slim``, which ships no ``git``, and
    the ``FileNotFoundError`` took down every Docker run of this script (PR #273)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
    except OSError:
        return "unknown"
    return out.stdout.strip() or "unknown"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cell", required=True, help="cell dir, e.g. $WORK/T1_mid")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--budget-s", type=float, default=300.0, dest="budget_s")
    ap.add_argument(
        "--r-command", default="Rscript", help="e.g. 'docker run --rm -v ... IMG Rscript'"
    )
    ap.add_argument("--seeds", default="1,2,3,4,5,6")
    ap.add_argument(
        "--reml-baseline",
        action="store_true",
        dest="reml_baseline",
        help="also fit Polaris EXACT REML (slow at mid: minutes) and report its eta distance to\n                    Polaris-bam and to bam; the triangle that says who moved off the optimum",
    )
    ap.add_argument(
        "--reuse-seeds",
        action="store_true",
        dest="reuse_seeds",
        help="do not rerun R: read the existing <cell>/bam_local_seeds.json (fast re-score)",
    )
    ap.add_argument("--skip-r", action="store_true", help="Polaris half only (timing/memory)")
    ap.add_argument("--out", default=None, help="default: <cell>/bam_local.json")
    ap.add_argument("--chip", default="unrecorded")
    a = ap.parse_args(argv)
    cell = Path(a.cell)
    df, spec = _frame(cell)

    # ---- Polaris half ---------------------------------------------------------------------
    def run() -> GamFit:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return gam(
                spec["formula"], df, spec["family"], weights=spec.get("weights"),
                select=bool(spec["select"]), method="fREML", discrete=True,
            )  # fmt: skip

    try:
        fit_obj, times = _repeat(run, a.repeats, a.budget_s)
    except PolarisValidationError as exc:
        # a refusal by name IS a result (e.g. a rank-deficient design: bgam.fitd pivots, the port
        # does not). Recorded, not worked around.
        refused = {
            "schema_version": 1, "tier": "L (maintainer-run, real data)", "cell": cell.name,
            "polaris_commit": _git_commit(), "status": "refused",
            "refusal": sanitise_refusal(str(exc)),
        }  # fmt: skip
        return _finish(refused, cell, a.out)
    assert isinstance(fit_obj, GamFit)
    fit = fit_obj
    best = min(times)
    _, se_p = fit.predict(df, "link", se_fit=True)
    rss = peak_rss_mb()
    print(
        f"Polaris: best {best:.1f} s of {len(times)}, {fit.n_iterations} iterations, "
        f"edf_total {fit.edf_total:.3f}, peak RSS {rss:.0f} MB, converged {fit.converged}"
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "tier": "L (maintainer-run, real data)",
        "cell": cell.name,
        "polaris_commit": _git_commit(),
        "openblas_num_threads": __import__("os").environ.get("OPENBLAS_NUM_THREADS", "unset"),
        "machine": {"chip": a.chip, "python": platform.python_version(), "os": platform.platform()},
        "n_rows": df.height,
        **({"trials_floor": True, "n_cells_floored": int(spec["n_cells_floored"])}
           if spec.get("trials_floor") else {}),
        "n_coef": int(fit.coef.shape[0]),
        "n_penalties": len(fit.log_lambda),
        "claim": "Polaris gam(fREML, discrete=True) vs bam(fREML, discrete=TRUE); INDEPENDENT; "
        "seed spread REFERENCE_INTERNAL; times are MEASUREMENTs",
        "polaris": {
            "fit_seconds": times, "best_seconds": best, "repeats_used": len(times),
            "peak_rss_mb": rss, "n_iterations": fit.n_iterations, "converged": bool(fit.converged),
            "edf_total": float(fit.edf_total), "ceiling_seconds": CEILING_S,
            "ceiling_met": best <= CEILING_S,
        },
    }  # fmt: skip
    if a.skip_r:
        return _finish(result, cell, a.out)

    # ---- mgcv half (per-row output stays in the scratch dir) -------------------------------
    scratch = cell / "bam_local_seeds.json"
    cmd = [
        *shlex.split(a.r_command), str(REPO / "scripts" / "bam_local_seed_probe.R"),
        str(cell / "cells.csv"), str(cell / "spec.json"), str(scratch), *a.seeds.split(","),
    ]  # fmt: skip
    if a.reuse_seeds:
        if not scratch.is_file():
            print(f"STOP AND REPORT: --reuse-seeds but {scratch} does not exist.", file=sys.stderr)
            return 1
    else:
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, text=True)
        if proc.returncode != 0:
            print(
                "STOP AND REPORT: the R seed probe failed (see its output above).", file=sys.stderr
            )
            return 1
        print(f"(R wall {time.perf_counter() - t0:.0f} s, includes startup and CSV read)")
    m = json.loads(scratch.read_text())
    fits = m["fits"]
    etas = np.vstack([np.atleast_1d(f["eta"]) for f in fits]).astype(np.float64)
    ses = np.vstack([np.atleast_1d(f["se_fit"]) for f in fits]).astype(np.float64)
    eta_p = np.asarray(fit.eta, dtype=np.float64)
    d0 = np.abs(eta_p - etas[0])
    edf_abs = abs(float(fit.edf_total) - float(fits[0]["edf_total"]))
    se_rel = float(np.max(np.abs(se_p - ses[0]) / ses[0]))
    scaled = float(np.max(d0 / ses[0]))
    p_vs = np.max(np.abs(etas - eta_p[None, :]), axis=1)
    spread = float(np.max(etas.max(axis=0) - etas.min(axis=0)))
    result.update(
        r_version=m["r_version"], mgcv_version=m["mgcv_version"],
        mgcv={"seeds": [f["seed"] for f in fits],
              "iterations_by_seed": [int(f["iter"]) for f in fits],
              "elapsed_by_seed": [float(f["elapsed_s"]) for f in fits],
              "edf_total": float(fits[0]["edf_total"])},
        agreement_vs_default_seed={
            "eta_max_abs": float(d0.max()), "eta_rms": float(np.sqrt(np.mean(d0**2))),
            "eta_scaled_max": scaled, "edf_total_abs": edf_abs, "se_rel_max": se_rel,
            "eta_gate_met": float(d0.max()) < ETA_GATE, "edf_gate_met": edf_abs < EDF_GATE,
            "se_gate_met": se_rel < SE_REL_GATE, "scaled_gate_met": scaled <= SCALED_ETA_GATE,
            "scaled_flag": scaled > SCALED_ETA_FLAG,
            "all_gates_met": bool(float(d0.max()) < ETA_GATE and edf_abs < EDF_GATE
                                  and se_rel < SE_REL_GATE and scaled <= SCALED_ETA_GATE),
        },
        seed_noise_floor={
            "bam_eta_spread": spread,
            "bam_max_dev_from_default": float(np.max(np.abs(etas[1:] - etas[0]))),
            "bam_edf_total_spread": float(np.ptp([f["edf_total"] for f in fits])),
            "polaris_vs_other_seeds_min": float(p_vs[1:].min()),
            "polaris_vs_other_seeds_max": float(p_vs[1:].max()),
            "spread_at_least_residual": bool(spread >= float(d0.max())),
            # Cloud-membership statistics (ADR-260 amendment 10): where Polaris sits relative to the
            # POINTWISE [min, max] envelope and median of bam over the seeds. Counts and magnitudes.
            "envelope_excess_max": float(np.max(np.maximum(
                np.maximum(eta_p - etas.max(axis=0), etas.min(axis=0) - eta_p), 0.0))),
            "n_rows_outside_envelope": int(np.sum((eta_p > etas.max(axis=0))
                                                  | (eta_p < etas.min(axis=0)))),
            "eta_max_abs_vs_seed_median": float(np.max(np.abs(eta_p - np.median(etas, axis=0)))),
            "bam_seed_eta_max_abs_vs_seed_median": float(np.max(np.abs(
                etas - np.median(etas, axis=0)[None, :]))),
        },
        ratio_polaris_over_bam_default=best / float(fits[0]["elapsed_s"]),
        bam_default_seconds=float(fits[0]["elapsed_s"]),
    )  # fmt: skip
    # Localisation scalars (counts and magnitudes only: no row, level, age or curve). Needed because
    # a disagreement larger than bam's own seed cloud (T3c_mid, 2026-10-18) cannot be read from the
    # max alone. Per-smooth edf and log10(sp) are model scalars the PLAN §3 contract allows.
    q = np.quantile(d0, [0.5, 0.9, 0.99, 0.999])
    result["localisation"] = {
        "abs_eta_diff_quantiles": {"q50": float(q[0]), "q90": float(q[1]),
                                   "q99": float(q[2]), "q999": float(q[3])},
        "n_rows_over_0p01": int(np.sum(d0 > 0.01)),
        "n_rows_over_0p1": int(np.sum(d0 > 0.1)),
        "n_rows_over_0p5": int(np.sum(d0 > 0.5)),
        "polaris_log10_sp": [float(v) for v in np.asarray(fit.log_lambda)],
        "bam_log10_sp": [float(v) for v in np.atleast_1d(fits[0]["log10_sp"])],
        "polaris_smooth_edf": [
            float(fit.edf_per_term[tb["label"]])
            for tb in fit.design["term_blocks"]
            if tb["n_penalties"] > 0
        ],
        "bam_smooth_edf": [float(v) for v in np.atleast_1d(fits[0]["smooth_edf"])],
    }  # fmt: skip
    if a.reml_baseline:
        t_r = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reml = gam(spec["formula"], df, spec["family"], weights=spec.get("weights"),
                       select=bool(spec["select"]))  # fmt: skip
        result["reml_triangle"] = {
            "eta_max_abs_polaris_reml_vs_polaris_bam": float(np.max(np.abs(reml.eta - eta_p))),
            "eta_max_abs_polaris_reml_vs_bam": float(np.max(np.abs(reml.eta - etas[0]))),
            "polaris_reml_seconds": time.perf_counter() - t_r,
            "polaris_reml_edf_total": float(reml.edf_total),
        }
    g = cell / "probe_gam.json"
    if g.is_file():
        gm = json.loads(g.read_text())
        result["gam_baseline"] = {
            "eta_max_abs_gam_vs_bam": float(np.max(np.abs(np.asarray(gm["eta"]) - etas[0]))),
            "edf_total_gam": float(gm["edf_total"]),
        }
    return _finish(result, cell, a.out)


def _finish(result: dict[str, object], cell: Path, out: str | None) -> int:
    _check_whitelist(result)
    path = Path(out) if out else cell / "bam_local.json"
    path.write_text(json.dumps(result, indent=2))
    print("\n=== derived scalars (this is what to paste back) ===")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
