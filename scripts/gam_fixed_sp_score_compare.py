"""The Polaris side of the fixed-`sp` criterion comparison — the `ours` column,
the rank-at-tolerance readings, and the corrected-cut spread.

DIAGNOSTIC ONLY, never committed parity evidence: it reads ``mgcv``'s own REML
score, so the comparison ticks no criterion and declares no ``VerificationClaim``.
Same status as ``gam_deriv_probe.R`` (ADR-201), ``gam_vc_probe.R`` (ADR-202) and
``gam_multiterm_sp_delta_probe.R`` (ADR-208's amendment).

WHAT IT ANSWERS. ADR-208's amendment established that ``mgcv``'s criterion and ours
rank ``mgcv``'s free-``sp`` point and Python's in opposite order. That is consistent
with two different worlds:

  (a) the criteria are the same function up to an additive constant (identical
      argmin) and the flip came from the optimiser, or
  (b) they are genuinely different functions of ``sp``.

Evaluating BOTH criteria at the SAME fixed ``sp``, at several well-separated points,
discriminates them and involves no optimiser at all. A CONSTANT difference means
(a) — same argmin, criterion exonerated. A VARYING difference means (b).

WHY THE SECOND HALF EXISTS. If the difference varies, the shape says where to look.
``log|S|+`` is the generalised determinant over the POSITIVE eigenvalues of
``S = sum_j lambda_j S_j``, so it needs a null-space cut, and
``gam_reml.reml_score_general`` uses a fixed relative tolerance. The null-space
dimension of ``S`` is a property of the MODEL — constant for any strictly positive
lambda — so a rank that MOVES with lambda is the defect. This script reports the
rank at three plausible tolerances, and then applies the null-space correction
analytically to test whether the tolerance CAUSES the discrepancy or merely
correlates with it: counting ``k`` extra eigenvalues as positive raises
``log|S|+`` by ``sum(log e_i)``, moving the score by ``-sum(log e_i)/2`` and
changing nothing else.

Usage:
    Rscript scripts/gam_fixed_sp_score_probe.R out.json
    uv run python scripts/gam_fixed_sp_score_compare.py out.json
"""

import json
import pathlib
import sys

import numpy as np

from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

# The tolerance gam_reml.reml_score_general ships with, and a tighter one used ONLY
# to demonstrate causation. Neither is proposed as a fix: PLAN slice 5c implements
# Wood (2011) Appendix B, and Wood rules the tolerance approach out explicitly.
SHIPPED_TOL = 1e-10
TIGHTER_TOL = 1e-12


def main(payload_path: str) -> None:
    payload = json.loads(pathlib.Path(payload_path).read_text())

    age_knots = tuple(float(v) for v in payload["age_knots"])
    year_knots = tuple(float(v) for v in payload["year_knots"])
    model = _multiterm_model_spec(age_knots, year_knots)
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    y = np.asarray(payload["y"], dtype=np.float64)

    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    weights = data["ExposCnt"]
    blocks = design["penalty_blocks"]
    p = design["x"].shape[1]

    print(f"n={len(y)}  p={p}  blocks={len(blocks)}")
    print(f"mgcv {payload['mgcv_version']} / {payload['r_version']}")
    print()
    print(
        f"{'point':<14}{'spread':>7}{'ours':>13}{'mgcv':>13}"
        f"{'raw diff':>13}{'corr diff':>13}{'k':>3}"
        f"{'r@1e-10':>9}{'r@1e-12':>9}"
    )
    print("-" * 107)

    raw: list[float] = []
    corrected: list[float] = []
    for row in payload["points"]:
        log_lambda = np.asarray(row["log10_sp"], dtype=np.float64)
        _coef, ours = penalized_fit_and_score(
            y, design["x"], family, blocks, log_lambda, weights=weights
        )
        mgcv_score = float(row["mgcv_score"])

        s = np.zeros((p, p), dtype=np.float64)
        for lam, block in zip(10.0**log_lambda, blocks, strict=True):
            s = s + lam * block
        eig = np.linalg.eigvalsh(s)
        largest = eig.max()
        kept_shipped = eig > max(largest, 1e-300) * SHIPPED_TOL
        kept_tight = eig > max(largest, 1e-300) * TIGHTER_TOL
        extra = eig[kept_tight & ~kept_shipped]
        ours_corrected = ours - np.sum(np.log(extra)) / 2.0

        raw.append(ours - mgcv_score)
        corrected.append(ours_corrected - mgcv_score)
        print(
            f"{row['name']:<14}{log_lambda.max() - log_lambda.min():>7.2f}"
            f"{ours:>13.5f}{mgcv_score:>13.5f}"
            f"{ours - mgcv_score:>13.5f}{ours_corrected - mgcv_score:>13.5f}"
            f"{extra.size:>3d}{int(kept_shipped.sum()):>9d}{int(kept_tight.sum()):>9d}"
        )

    raw_arr = np.asarray(raw)
    corr_arr = np.asarray(corrected)
    raw_spread = float(raw_arr.max() - raw_arr.min())
    corr_spread = float(corr_arr.max() - corr_arr.min())
    print("-" * 107)
    print(f"SPREAD, shipped cut {SHIPPED_TOL:g}: {raw_spread:.6f}")
    print(f"SPREAD, tighter cut {TIGHTER_TOL:g}: {corr_spread:.6f}")
    print(f"reduction factor: {raw_spread / max(corr_spread, 1e-15):.1f}x")
    print()
    print(
        "A spread that is NOT ~0 under the shipped cut means the criterion itself "
        "moves with sp.\nA spread that collapses under the tighter cut means the "
        "null-space cut is the cause,\nnot a correlate — see PLAN slice 5c."
    )


if __name__ == "__main__":
    main(sys.argv[1])
