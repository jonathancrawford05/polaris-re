"""A candidate fix, tested: evaluate the penalty quadratic form via per-block
SQUARE ROOTS instead of forming S and contracting.

beta' S beta = sum_j lambda_j * beta' S_j beta = sum_j lambda_j * ||L_j' beta||^2
where S_j = L_j L_j'. Every term is a SUM OF SQUARES -- non-negative, so there is
no cancellation anywhere, and the 1e12 intermediates never form.

Compared against float128 truth at each spread.

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

USAGE:  uv run python scripts/gam_penalty_sqrt_form_diagnostic.py probe7.json
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
        for k in ("AttdAge","PolYear","StudyYear_C","ExposCnt")}
y = np.asarray(payload["y"], dtype=np.float64)
design = assemble_model_design(model, data)
family = resolve_family(model.family, model.link)
blocks = tuple(design["penalty_blocks"]); x = design["x"]; w = data["ExposCnt"]
mgcv_pt = np.log10(np.asarray(payload["sp"], dtype=np.float64))

def block_sqrt(Sj):
    """L with S_j = L L' via symmetric eigendecomposition (S_j is PSD)."""
    ev, V = np.linalg.eigh(Sj)
    ev = np.clip(ev, 0.0, None)
    keep = ev > ev.max() * 1e-14 if ev.max() > 0 else np.zeros_like(ev, dtype=bool)
    return V[:, keep] * np.sqrt(ev[keep])

print(f"{'point':<24}{'formed-S err':>15}{'sqrt-form err':>16}{'improvement':>14}")
for name, pt in (("narrow (spread 2.0)", np.array([2.,3.,4.,3.,2.,4.,3.])),
                 ("wide (spread 11.0)",  np.array([11.,0.,10.,5.,3.,2.,1.])),
                 ("mgcv point (12.9)",   mgcv_pt)):
    lam = 10.0**pt
    S = np.zeros_like(blocks[0])
    for l,b in zip(lam, blocks, strict=True):
        S = S + l*b
    with threadpool_limits(limits=1, user_api="blas"):
        beta,_ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
    beta = np.array(beta, dtype=np.float64, copy=True)

    truth = float(beta.astype(np.longdouble) @ S.astype(np.longdouble) @ beta.astype(np.longdouble))
    formed = float(beta @ S @ beta)
    sqrt_form = float(sum(l * float(np.sum((block_sqrt(b).T @ beta)**2))
                          for l, b in zip(lam, blocks, strict=True)))
    e1, e2 = abs(formed-truth), abs(sqrt_form-truth)
    print(f"{name:<24}{e1:15.3e}{e2:16.3e}{(e1/max(e2,1e-300)):13.1f}x")

print("\nAnd the thread axis on the same quantity:")
print(f"{'point':<24}{'formed-S d':>14}{'sqrt-form d':>15}")
for name, pt in (("wide (spread 11.0)", np.array([11.,0.,10.,5.,3.,2.,1.])),
                 ("mgcv point (12.9)",  mgcv_pt)):
    lam = 10.0**pt
    S = np.zeros_like(blocks[0])
    for l,b in zip(lam, blocks, strict=True):
        S = S + l*b
    roots = [block_sqrt(b) for b in blocks]
    A, B = [], []
    for th in (1,2,4):
        with threadpool_limits(limits=th, user_api="blas"):
            c,_ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
            c = np.array(c, dtype=np.float64, copy=True)
        A.append(float(c @ S @ c))
        B.append(float(sum(l*float(np.sum((L.T @ c)**2)) for l, L in zip(lam, roots, strict=True))))
    dA = max(abs(A[i]-A[j]) for i in range(3) for j in range(i+1,3))
    dB = max(abs(B[i]-B[j]) for i in range(3) for j in range(i+1,3))
    print(f"{name:<24}{dA:14.3e}{dB:15.3e}")
