#!/usr/bin/env python3
"""Slice R3 Stage B (ADR-260 amendment 19): WHY does ``S1_mid`` miss criterion (B)? —
MAINTAINER-RUN, tier L, from the scratch ``<cell>/bam_local_seeds.json`` of ``bam_local_run.py``.

Criterion (B) says Polaris lies inside the pointwise [min, max] envelope of ``bam`` over seven
``discrete.mf`` seeds to within 1e-4. A pointwise envelope of n draws is a tail statistic: a FRESH
draw from the same cloud lands outside it on roughly 2/(n+1) of rows. So the question is what (B)
reads for ``bam``'s OWN seeds. This script reports, as scalars only:

1. Polaris vs the 7-seed envelope (as in the runner);
2. each ``bam`` seed vs the envelope of the OTHER six (leave-one-out): the reference distribution
   of the statistic for a legitimate member of the cloud (6-draw envelopes are narrower than the
   7-draw one, so this is the harder test for the seeds);
3. the same ratios to the seed spread;
4. where Polaris's outside rows sit: counts only, by the cell's exposure quartile and whether the
   cell was floored (``deaths == exposure`` after flooring; S1 only).

Nothing here is a row, a level, an age or a curve. It does not change criterion (B).
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.gam import gam

ALLOWED = frozenset(
    {"cell", "n_rows", "n_seeds", "bam_eta_spread", "polaris", "excess_max", "n_rows_outside",
     "frac_rows_outside", "excess_over_spread", "bam_seeds_leave_one_out", "excess_max_min",
     "excess_max_median", "excess_max_max", "frac_rows_outside_min", "frac_rows_outside_median",
     "frac_rows_outside_max", "excess_over_spread_median", "polaris_outside_rows",
     "n_outside_in_floored_cells", "n_floored_cells", "share_outside_in_floored_cells",
     "share_rows_in_floored_cells", "n_outside_by_exposure_quartile", "q1", "q2", "q3", "q4",
     "claim"}
)  # fmt: skip


def _excess(x: np.ndarray, others: np.ndarray) -> tuple[float, int]:
    hi, lo = others.max(axis=0), others.min(axis=0)
    ex = np.maximum(np.maximum(x - hi, lo - x), 0.0)
    return float(ex.max()), int(np.sum(ex > 0.0))


def main(cell: Path) -> int:
    spec = json.loads((cell / "spec.json").read_text())
    df = pl.read_csv(cell / "cells.csv")
    df = df.with_columns(
        [pl.col(n).cast(pl.String).cast(pl.Enum(lv)).alias(n) for n, lv in spec["factors"].items()]
    )
    seeds = json.loads((cell / "bam_local_seeds.json").read_text())["fits"]
    etas = np.vstack([np.atleast_1d(f["eta"]) for f in seeds]).astype(np.float64)
    n_rows = etas.shape[1]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = gam(
            spec["formula"], df, spec["family"], weights=spec.get("weights"),
            select=bool(spec["select"]), method="fREML", discrete=True,
        )  # fmt: skip
    eta_p = np.asarray(fit.eta, dtype=np.float64)
    spread = float(np.max(etas.max(axis=0) - etas.min(axis=0)))
    ex_p, n_out = _excess(eta_p, etas)
    loo = [_excess(etas[i], np.delete(etas, i, axis=0)) for i in range(etas.shape[0])]
    loo_ex = np.array([a for a, _ in loo])
    loo_frac = np.array([b / n_rows for _, b in loo])
    # where Polaris's outside rows sit (counts only)
    hi, lo = etas.max(axis=0), etas.min(axis=0)
    outside = (eta_p > hi) | (eta_p < lo)
    w = spec.get("weights")
    result: dict[str, object] = {
        "cell": cell.name, "n_rows": n_rows, "n_seeds": int(etas.shape[0]),
        "bam_eta_spread": spread,
        "claim": "diagnostic: (B) statistic for bam seeds (leave-one-out) vs Polaris",
        "polaris": {"excess_max": ex_p, "n_rows_outside": n_out,
                    "frac_rows_outside": n_out / n_rows,
                    "excess_over_spread": ex_p / spread},
        "bam_seeds_leave_one_out": {
            "excess_max_min": float(loo_ex.min()), "excess_max_median": float(np.median(loo_ex)),
            "excess_max_max": float(loo_ex.max()), "frac_rows_outside_min": float(loo_frac.min()),
            "frac_rows_outside_median": float(np.median(loo_frac)),
            "frac_rows_outside_max": float(loo_frac.max()),
            "excess_over_spread_median": float(np.median(loo_ex) / spread),
        },
    }  # fmt: skip
    if w and w in df.columns and "deaths" in df.columns:
        expo = df[w].to_numpy().astype(np.float64)
        floored = (df["deaths"].to_numpy().astype(np.float64) == expo) & bool(
            spec.get("trials_floor")
        )
        q = np.quantile(expo, [0.25, 0.5, 0.75])
        bins = np.digitize(expo, q)
        result["polaris_outside_rows"] = {
            "n_floored_cells": int(floored.sum()),
            "n_outside_in_floored_cells": int((outside & floored).sum()),
            "share_outside_in_floored_cells": float(
                (outside & floored).sum() / max(1, outside.sum())
            ),
            "share_rows_in_floored_cells": float(floored.mean()),
            "n_outside_by_exposure_quartile": {
                f"q{i + 1}": int((outside & (bins == i)).sum()) for i in range(4)
            },
        }  # fmt: skip
    bad = set(result) - ALLOWED
    if bad:
        raise SystemExit(f"refusing to write non-whitelisted keys {sorted(bad)}")
    (cell / "bam_envelope_diagnostic.json").write_text(json.dumps(result, indent=2))
    print("\n=== derived scalars (this is what to paste back) ===")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(Path(sys.argv[1])))
