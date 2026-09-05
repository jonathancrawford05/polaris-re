"""WHICH term of the REML score carries the thread sensitivity?

`reml_score_general` has four terms. Two involve a determinant:

  * log|S|+          -- ALREADY stabilised via Appendix B (ADR-196/slice 5c)
  * log|X'WX + S|    -- NOT stabilised; `RECALIBRATION_..._2026-08-25` 1.2
                        judged naive slogdet adequate because the matrix is
                        full-rank PD and so "has no null-space decision to get
                        wrong"

Wood (2011) 3.1 names BOTH as corrupted by scale disparity. If the sensitivity
concentrates in log|X'WX + S|, the prior justification's gap is pinned exactly,
and slice 8's first job is named precisely.

Also tested: does an orthogonal similarity transform of the SAME matrix change
the answer? It cannot in exact arithmetic, so any difference is pure
floating-point conditioning -- a direct read of how much precision is available
to recover.

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

USAGE:  uv run python scripts/gam_reml_term_decomposition_diagnostic.py probe7.json
--------------------------------------------------------------------------------
"""

import json
import sys
from dataclasses import replace

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_model import (
    assemble_model_design,
    resolve_family,
)
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_appendix_b import appendix_b_transform
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
    "moderate (spread 6.0)": np.array([0.0, 3.0, 6.0, 2.0, 4.0, 1.0, 5.0]),
    "wide (spread 11.0)": np.array([11.0, 0.0, 10.0, 5.0, 3.0, 2.0, 1.0]),
    "mgcv point (spread 12.9)": mgcv_pt,
}


def terms(pt, threads):
    """The two determinant terms, and the penalized deviance, at `pt`."""
    with threadpool_limits(limits=threads, user_api="blas"):
        coef, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
        lambdas = 10.0**pt
        penalty = np.zeros_like(blocks[0])
        for lam, b in zip(lambdas, blocks, strict=True):
            penalty = penalty + lam * b
        eta = x @ coef
        mu = family.link.linkinv(eta)
        dev = family.deviance(y, mu, w)
        pen_dev = dev + float(coef @ penalty @ coef)
        ow = family.observed_information_weight(y, eta, w)
        h = x.T @ (ow[:, None] * x) + penalty
        _, logdet_h = np.linalg.slogdet(h)
        logdet_s = appendix_b_transform(blocks, lambdas).logdet_s_plus
        # Orthogonal similarity transform of the SAME H: identical in exact
        # arithmetic, so the gap is pure conditioning.
        rng = np.random.default_rng(7)
        q, _ = np.linalg.qr(rng.normal(size=h.shape))
        _, logdet_h_rot = np.linalg.slogdet(q.T @ h @ q)
    return float(pen_dev), float(logdet_h), float(logdet_s), float(logdet_h_rot)


print(f"{'point':<28}{'d pen.dev':>13}{'d log|H|':>13}{'d log|S|+':>13}{'cond(H)':>12}{'rot gap':>13}")
for name, pt in POINTS.items():
    vals = [terms(pt, th) for th in (1, 2, 4)]
    d_pd = max(abs(a[0] - b[0]) for i, a in enumerate(vals) for b in vals[i + 1:])
    d_h = max(abs(a[1] - b[1]) for i, a in enumerate(vals) for b in vals[i + 1:])
    d_s = max(abs(a[2] - b[2]) for i, a in enumerate(vals) for b in vals[i + 1:])
    rot = abs(vals[0][1] - vals[0][3])
    lambdas = 10.0**pt
    penalty = np.zeros_like(blocks[0])
    for lam, b in zip(lambdas, blocks, strict=True):
        penalty = penalty + lam * b
    coef, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
    ow = family.observed_information_weight(y, x @ coef, w)
    cond = float(np.linalg.cond(x.T @ (ow[:, None] * x) + penalty))
    print(f"{name:<28}{d_pd:13.3e}{d_h:13.3e}{d_s:13.3e}{cond:12.2e}{rot:13.3e}")

print("\n  d pen.dev / d log|H| / d log|S|+ : thread-to-thread spread of each term")
print("  rot gap : log|H| minus log|Q'HQ| for a random orthogonal Q at threads=1.")
print("            Exactly 0 in infinite precision; its size IS the precision")
print("            already lost in this determinant before threading enters.")
