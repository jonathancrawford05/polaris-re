"""Is beta' S beta lost to CATASTROPHIC CANCELLATION when S is formed first?

The beta-perturbation chain is refuted (predicted 5.7e-12 against an observed
1.0e-04). The remaining candidate is Wood 3.1's own statement: a large
lambda_j S_j has a numerical footprint OUTSIDE its range space, so forming
S = sum_j lambda_j S_j and contracting once sums terms of wildly different
magnitude that cancel down to O(10).

Two algebraically identical evaluations:
  (a) coef @ (sum_j lambda_j S_j) @ coef      <- what reml_score_general does
  (b) sum_j lambda_j * (coef @ S_j @ coef)    <- contract per block, then sum

(b) never forms the mixed-scale matrix. If (b) is thread-stable where (a) is
not, the mechanism is cancellation in the contraction, and (b) is a cheap
partial fix that needs no reparameterisation at all.

--------------------------------------------------------------------------------
PROVENANCE. This is the script that produced ADR-222 amendment 2's numbers. It was written in
the slice 7f session (2026-09-05) and promoted from that session's scratchpad so
slice 7h can RE-RUN it rather than reconstruct it from prose.

VERIFICATION PROVENANCE (ADR-193). This script makes NO mgcv comparison. Every
reading below is Polaris measured against ITSELF -- across BLAS thread counts,
across starts, or against `float128` on the same expression. There is no second
producer, so there is no `VerificationClaim`: this is `MEASUREMENT (own
criterion)`, the same class as ADR-211's BLAS-thread table, and it must never be
reported as parity or agreement evidence.

FIXTURE. Takes the `select=TRUE` multiterm payload as argv[1]. Regenerate it with:

    Rscript scripts/gam_select_multiterm_free_sp_probe.R probe7.json

USAGE:  uv run python scripts/gam_penalty_cancellation_diagnostic.py probe7.json
--------------------------------------------------------------------------------
"""

import json, sys
from dataclasses import replace
import numpy as np
from threadpoolctl import threadpool_limits
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

payload = json.load(open(sys.argv[1]))
model = replace(_multiterm_model_spec(
    tuple(float(v) for v in payload["age_knots"]),
    tuple(float(v) for v in payload["year_knots"])), select=True)
data = {k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")}
y = np.asarray(payload["y"], dtype=np.float64)
design = assemble_model_design(model, data)
family = resolve_family(model.family, model.link)
blocks = tuple(design["penalty_blocks"]); x = design["x"]; w = data["ExposCnt"]
mgcv_pt = np.log10(np.asarray(payload["sp"], dtype=np.float64))

POINTS = {
    "narrow (spread 2.0)": np.array([2.0,3.0,4.0,3.0,2.0,4.0,3.0]),
    "wide (spread 11.0)":  np.array([11.0,0.0,10.0,5.0,3.0,2.0,1.0]),
    "mgcv point (12.9)":   mgcv_pt,
}
print(f"{'point':<24}{'(a) d formed-S':>17}{'(b) d per-block':>18}{'(a) value':>14}{'largest term':>15}")
for name, pt in POINTS.items():
    lam = 10.0**pt
    pen = np.zeros_like(blocks[0])
    for l, b in zip(lam, blocks, strict=True):
        pen = pen + l * b
    A, B = [], []
    for th in (1, 2, 4):
        with threadpool_limits(limits=th, user_api="blas"):
            coef, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
            A.append(float(coef @ pen @ coef))
            B.append(float(sum(l * float(coef @ b @ coef) for l, b in zip(lam, blocks, strict=True))))
    dA = max(abs(A[i]-A[j]) for i in range(3) for j in range(i+1,3))
    dB = max(abs(B[i]-B[j]) for i in range(3) for j in range(i+1,3))
    coef, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
    largest = max(abs(l * float(coef @ b @ coef)) for l, b in zip(lam, blocks, strict=True))
    print(f"{name:<24}{dA:17.3e}{dB:18.3e}{A[0]:14.4f}{largest:15.3e}")
print("\n  'largest term' is max_j |lambda_j * beta' S_j beta| — against an (a) value")
print("  of O(10), it is the size of the cancellation the formed-S contraction eats.")
