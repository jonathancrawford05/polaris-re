"""Is beta'S beta simply EVALUATED inaccurately in float64?

The algebraic identity d(b'Sb) = 2b'S db + db'S db is exact for symmetric S,
so first+second = 1.4e-13 against an exact difference of 2.9e-05 can only mean
each EVALUATION of b'Sb carries ~1e-5 of error. Bit-identical for a fixed beta
(deterministic rounding) is not the same as accurate.

Checked against float128 (longdouble), and the digit loss in forming S@b is
measured directly.

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

USAGE:  uv run python scripts/gam_penalty_float128_precision_diagnostic.py probe7.json
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

    v64 = float(beta @ S @ beta)
    S128, b128 = S.astype(np.longdouble), beta.astype(np.longdouble)
    v128 = float(b128 @ S128 @ b128)

    Sb = S @ beta
    # magnitude of the intermediates that must cancel to produce S@b
    intermediate = float(np.max(np.abs(S) @ np.abs(beta)))
    result_mag = float(np.max(np.abs(Sb)))
    loss = intermediate / max(result_mag, 1e-300)
    print(f"{name}")
    print(f"   b'Sb float64   = {v64:.10f}")
    print(f"   b'Sb float128  = {v128:.10f}")
    print(f"   ABS ERROR      = {abs(v64-v128):.3e}   <- float64 evaluation error")
    print(f"   forming S@b: |S||b| intermediates {intermediate:.3e} -> |S@b| {result_mag:.3e}")
    print(f"   cancellation   = {loss:.2e}x  ({np.log10(loss):.1f} digits lost)")
    print(f"   predicted err ~ eps * |S||b| * ||beta|| = {2.2e-16*intermediate*np.linalg.norm(beta):.3e}")
    print()
