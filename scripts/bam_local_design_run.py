#!/usr/bin/env python3
"""Slice R3 Stage B (ADR-260 amendment 8): the DESIGN-CONDITIONED diagnostic on a REAL cell —
MAINTAINER-RUN, tier L. Follow ``docs/RUNBOOK_bam_local_stage_b.md`` §7.

Runs ``bam_local_design_probe.R`` (bam's own design X/S and its ``maxit = 1..K`` trace, scratch),
then hands that design to ``polaris_re.gam.bam_fitd.bam_fitd`` and reduces the comparison to
SCALARS: per-iteration max |Δ log(sp)| and max |Δ eta|, iteration counts, final eta/edf agreement.
Provenance (ADR-193): ECHO. Polaris is handed mgcv's X and S, so this is a diagnostic that separates
a DESIGN difference from an ALGORITHM difference; it is not parity evidence.
"""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.gam_model import resolve_family
from polaris_re.gam.bam_fitd import bam_fitd

REPO = Path(__file__).resolve().parent.parent
ALLOWED = frozenset(
    {"cell", "n_rows", "n_coef", "n_penalties", "iterations", "final", "per_iteration",
     "iterations_polaris", "iterations_mgcv", "eta_max_abs", "eta_rms", "edf_total_abs",
     "n_rows_over_0p1", "log_sp_max_abs_by_iteration", "eta_max_abs_by_iteration",
     "claim", "mgcv_version", "r_version"}
)  # fmt: skip


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cell", required=True)
    ap.add_argument("--r-command", default="Rscript")
    ap.add_argument("--skip-r", action="store_true", help="reuse an existing <cell>/design_probe/")
    a = ap.parse_args(argv)
    cell = Path(a.cell)
    out = cell / "design_probe"
    if not a.skip_r:
        cmd = [*shlex.split(a.r_command), str(REPO / "scripts" / "bam_local_design_probe.R"),
               str(cell / "cells.csv"), str(cell / "spec.json"), str(out)]  # fmt: skip
        if subprocess.run(cmd, text=True).returncode != 0:
            print("STOP AND REPORT: the R design probe failed.", file=sys.stderr)
            return 1
    meta = json.loads((out / "meta.json").read_text())
    n, p, k_it = int(meta["n"]), int(meta["p"]), int(meta["K"])
    x = np.fromfile(out / "X.bin", dtype=np.float64).reshape(p, n).T  # column-major -> (n, p)
    eta_tr = np.fromfile(out / "trace_eta.bin", dtype=np.float64).reshape(k_it, n)
    lsp_tr = np.vstack([np.atleast_1d(v) for v in meta["trace_log_sp"]])
    blocks = []
    for q in meta["pen"]:
        s = np.atleast_2d(np.asarray(q["S"], dtype=np.float64))
        off = int(q["off"]) - 1
        full = np.zeros((p, p))
        full[off : off + s.shape[0], off : off + s.shape[0]] = s
        blocks.append(full)
    spec = json.loads((cell / "spec.json").read_text())
    df = pl.read_csv(cell / "cells.csv")
    resp = spec["formula"].split("~")[0].strip()
    y = df[resp].to_numpy().astype(np.float64)
    off_col = spec["formula"].split("offset(")[1].split(")")[0]
    offset = df[off_col].to_numpy().astype(np.float64)
    res = bam_fitd(x, tuple(blocks), y, resolve_family(spec["family"], "log"), offset=offset)
    lsp_d, eta_d = [], []
    for it, ref_lsp, ref_eta in zip(res.trace, lsp_tr, eta_tr, strict=False):
        lsp_d.append(float(np.max(np.abs(it.log_sp - ref_lsp))))
        eta_d.append(float(np.max(np.abs(x @ it.coef + offset - ref_eta))))
    d_final = np.abs(res.eta - eta_tr[-1])
    result = {
        "cell": cell.name, "n_rows": n, "n_coef": p, "n_penalties": len(blocks),
        "claim": "ECHO diagnostic: bam_fitd handed bam's own X and S; separates design from "
                 "algorithm; not parity evidence",
        "mgcv_version": meta["mgcv_version"], "r_version": meta["r_version"],
        "iterations_polaris": res.n_iter, "iterations_mgcv": k_it,
        "eta_max_abs": float(d_final.max()), "eta_rms": float(np.sqrt(np.mean(d_final**2))),
        "n_rows_over_0p1": int(np.sum(d_final > 0.1)),
        "log_sp_max_abs_by_iteration": lsp_d, "eta_max_abs_by_iteration": eta_d,
    }  # fmt: skip
    bad = set(result) - ALLOWED
    if bad:
        raise SystemExit(f"refusing to write non-whitelisted keys {sorted(bad)}")
    (cell / "bam_design_local.json").write_text(json.dumps(result, indent=2))
    print("\n=== derived scalars (this is what to paste back) ===")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
