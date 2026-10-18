#!/usr/bin/env python3
"""Slice R3 Stage B (ADR-260 amendment 9): WHERE does ``bam``'s design differ from Polaris's? —
MAINTAINER-RUN, tier L, after ``bam_local_design_run.py`` has left ``<cell>/design_probe/``.

Handed the design ``bam`` built (``X.bin``, ``meta.json``) and the design Polaris builds from the
same cells and formula, it reports SCALARS per penalised term:

* ``space_resid_max``: the largest |bam column - best linear combination of Polaris's columns of
  the same term plus the unpenalised columns (intercept, parametric)|. ~1e-12 means the two terms
  span the SAME function space (given the unpenalised part), i.e. only the coordinates differ.
* ``penalty_congruence_rel``: ||S_bam - T' S_polaris T||_F / ||S_bam||_F with T the change of
  coordinates just found. ~1e-12 means the two penalties are the SAME quadratic form on the same
  functions; larger means the penalised model itself differs (a different penalty or constraint).
* ``penalty_scale_ratio``: ||S_bam||_F / ||S_polaris||_F (mgcv's ``S.scale`` rescaling shows here).
* sizes only. No row, level, age or curve.

Provenance (ADR-193): a diagnostic on two designs, one built by each engine; INDEPENDENT producers,
but the question is "where do they differ", not parity.
"""

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.gam.api import _build_model, _numeric
from polaris_re.gam.formula import parse_formula

ALLOWED = frozenset(
    {"cell", "n_rows", "n_coef_bam", "n_coef_polaris", "n_penalties", "penalties", "kind",
     "n_cols_bam", "n_cols_polaris", "space_resid_max", "penalty_congruence_rel",
     "penalty_scale_ratio", "claim"}
)  # fmt: skip


def _frame(cell: Path) -> tuple[pl.DataFrame, dict]:
    spec = json.loads((cell / "spec.json").read_text())
    df = pl.read_csv(cell / "cells.csv")
    cols = [
        pl.col(n).cast(pl.String).cast(pl.Enum(lv)).alias(n) for n, lv in spec["factors"].items()
    ]
    return df.with_columns(cols), spec


def main(cell: Path) -> int:
    df, spec = _frame(cell)
    out = cell / "design_probe"
    meta = json.loads((out / "meta.json").read_text())
    n, p_b = int(meta["n"]), int(meta["p"])
    xb = np.fromfile(out / "X.bin", dtype=np.float64).reshape(p_b, n).T
    pen_b = []
    for q in meta["pen"]:
        s = np.atleast_2d(np.asarray(q["S"], dtype=np.float64))
        pen_b.append((int(q["off"]) - 1, s))
    parsed = parse_formula(spec["formula"])
    model, arrays, _codings, _meta = _build_model(
        parsed, df, spec["family"], "log", spec.get("weights"), parsed.offset,
        bool(spec["select"]), False, tero=True,
    )  # fmt: skip
    design = assemble_model_design(model, arrays)
    xp = design["x"]
    p_p = xp.shape[1]
    # the unpenalised columns of Polaris's design: those in no penalty's support
    pen_p = []
    covered = np.zeros(p_p, dtype=bool)
    for s in design["penalty_blocks"]:
        cols = np.flatnonzero(np.any(s != 0.0, axis=0))
        covered[cols] = True
        pen_p.append((cols, s[np.ix_(cols, cols)]))
    free = np.flatnonzero(~covered)
    rows = []
    for j, ((off_b, s_b), (cols_p, s_p)) in enumerate(zip(pen_b, pen_p, strict=False)):
        cols_b = np.arange(off_b, off_b + s_b.shape[0])
        design_regr = np.hstack([xp[:, cols_p], xp[:, free]])
        target = xb[:, cols_b]
        coef, *_ = np.linalg.lstsq(design_regr, target, rcond=None)
        resid = float(np.max(np.abs(design_regr @ coef - target)))
        t = coef[: cols_p.size, :]  # coordinates change on the penalised columns
        cong = float(np.linalg.norm(s_b - t.T @ s_p @ t) / np.linalg.norm(s_b))
        rows.append({
            "kind": f"penalty {j}", "n_cols_bam": int(cols_b.size), "n_cols_polaris": int(cols_p.size),
            "space_resid_max": resid, "penalty_congruence_rel": cong,
            "penalty_scale_ratio": float(np.linalg.norm(s_b) / np.linalg.norm(s_p)),
        })  # fmt: skip
    result = {
        "cell": cell.name, "n_rows": n, "n_coef_bam": p_b, "n_coef_polaris": int(p_p),
        "n_penalties": len(pen_b), "penalties": rows,
        "claim": "diagnostic: where bam's design differs from Polaris's; scalars per penalty",
    }  # fmt: skip
    bad = set(result) - ALLOWED
    if bad:
        raise SystemExit(f"refusing to write non-whitelisted keys {sorted(bad)}")
    _ = _numeric  # imported for symmetry with the runner
    (cell / "bam_design_compare.json").write_text(json.dumps(result, indent=2))
    print("\n=== derived scalars (this is what to paste back) ===")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(Path(sys.argv[1])))
