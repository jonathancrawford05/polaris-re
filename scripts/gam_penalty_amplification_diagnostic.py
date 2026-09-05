"""Where inside the penalized deviance does the thread sensitivity live, and is
the amplification chain what it looks like?

Term decomposition put the whole cross-thread spread in
`penalized_deviance = deviance + beta' S beta`, with BOTH determinants
thread-stable. Two sub-terms to separate, and one amplification to check:

  deviance(y, mu)      -- depends on beta only through eta = X beta
  beta' S beta         -- a quadratic form in a penalty whose entries span
                          ~13 decades at these lambdas

Hypothesis: beta_hat is thread-stable to ~1e-15 (already measured), but
||S|| ~ 1e12, so a 1e-15 perturbation in beta enters beta'S beta multiplied by
2*S*beta and lands at ~1e-4. That would make the chain
  BLAS summation order -> beta_hat at 1e-15 -> beta'S beta at 1e-4
  -> score at 1e-5 -> optimiser path -> a different basin.

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

USAGE:  uv run python scripts/gam_penalty_amplification_diagnostic.py probe7.json
--------------------------------------------------------------------------------
"""

import json
import sys
from dataclasses import replace

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

payload = json.load(open(sys.argv[1]))
age_knots = tuple(float(v) for v in payload["age_knots"])
year_knots = tuple(float(v) for v in payload["year_knots"])
model = replace(_multiterm_model_spec(age_knots, year_knots), select=True)
data = {
    k: np.asarray(payload[k], dtype=np.float64)
    for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
}
y = np.asarray(payload["y"], dtype=np.float64)
design = assemble_model_design(model, data)
family = resolve_family(model.family, model.link)
blocks = tuple(design["penalty_blocks"])
x = design["x"]
w = data["ExposCnt"]
mgcv_pt = np.log10(np.asarray(payload["sp"], dtype=np.float64))

POINTS = {
    "narrow (spread 2.0)": np.array([2.0, 3.0, 4.0, 3.0, 2.0, 4.0, 3.0]),
    "wide (spread 11.0)": np.array([11.0, 0.0, 10.0, 5.0, 3.0, 2.0, 1.0]),
    "mgcv point (spread 12.9)": mgcv_pt,
}

print(
    f"{'point':<26}{'d beta (abs)':>14}{'d deviance':>13}"
    f"{'d b\'Sb':>13}{'|b\'Sb|':>13}{'||S||':>11}{'predicted':>12}"
)
for name, pt in POINTS.items():
    lambdas = 10.0**pt
    penalty = np.zeros_like(blocks[0])
    for lam, b in zip(lambdas, blocks, strict=True):
        penalty = penalty + lam * b
    got = []
    for th in (1, 2, 4):
        with threadpool_limits(limits=th, user_api="blas"):
            coef, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
            eta = x @ coef
            dev = float(family.deviance(y, family.link.linkinv(eta), w))
            quad = float(coef @ penalty @ coef)
        got.append((np.asarray(coef, float), dev, quad))
    d_beta = max(
        float(np.max(np.abs(a[0] - b[0]))) for i, a in enumerate(got) for b in got[i + 1:]
    )
    d_dev = max(abs(a[1] - b[1]) for i, a in enumerate(got) for b in got[i + 1:])
    d_quad = max(abs(a[2] - b[2]) for i, a in enumerate(got) for b in got[i + 1:])
    beta = got[0][0]
    norm_s = float(np.linalg.norm(penalty, 2))
    # First-order: d(b'Sb) ~ 2 |S b| . |d b|
    predicted = 2.0 * float(np.linalg.norm(penalty @ beta)) * d_beta
    print(
        f"{name:<26}{d_beta:14.3e}{d_dev:13.3e}{d_quad:13.3e}"
        f"{abs(got[0][2]):13.3e}{norm_s:11.2e}{predicted:12.3e}"
    )

print("\n  'predicted' is the first-order estimate 2*||S beta||*|d beta| for the")
print("  quadratic form's own sensitivity to the measured beta perturbation.")
print("  If it tracks the observed d b'Sb, the amplification chain is confirmed.")
