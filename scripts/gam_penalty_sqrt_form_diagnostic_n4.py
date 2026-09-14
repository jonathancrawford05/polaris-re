"""PLAN slice 7i -- re-run ADR-223's own `gam_penalty_sqrt_form_diagnostic.py`
methodology (the penalty quadratic form as per-block square roots vs. formed-
S, compared against `float128` truth and across BLAS thread counts) on the
N=4 (non-`select`) structure, alongside the N=7 `select=TRUE` one that script
already covers -- PLAN slice 7i's own Definition of Done asks for both.

--------------------------------------------------------------------------------
PROVENANCE. Adapted from `gam_penalty_sqrt_form_diagnostic.py` (ADR-223,
slice 7h) for the N=4, non-`select` three-term structure (reference age + MI
by-term + ti(), 4 penalty blocks) ADR-208/210/211/212 measured
`_FINITE_DIFF_STEP` on, rather than the N=7 `select=TRUE` structure the
original script covers.

VERIFICATION PROVENANCE (ADR-193). MEASUREMENT (own criterion) -- no `mgcv`
comparison anywhere in this script.

FIXTURE. Takes the N=4 multiterm payload (age_knots, year_knots, AttdAge,
PolYear, StudyYear_C, ExposCnt, y, sp) as argv[1]. Regenerate it with:

    Rscript scripts/gam_multiterm_free_sp_probe.R probe4.json

USAGE:  uv run python scripts/gam_penalty_sqrt_form_diagnostic_n4.py probe4.json
--------------------------------------------------------------------------------
"""

import json
import sys

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

payload = json.load(open(sys.argv[1]))
model = _multiterm_model_spec(
    tuple(float(v) for v in payload["age_knots"]),
    tuple(float(v) for v in payload["year_knots"]),
)
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
print("mgcv point (log10 sp):", mgcv_pt)


def block_sqrt(Sj: np.ndarray) -> np.ndarray:
    """L with S_j = L L' via symmetric eigendecomposition (S_j is PSD)."""
    ev, V = np.linalg.eigh(Sj)
    ev = np.clip(ev, 0.0, None)
    keep = ev > ev.max() * 1e-14 if ev.max() > 0 else np.zeros_like(ev, dtype=bool)
    return V[:, keep] * np.sqrt(ev[keep])


points = {
    "narrow (spread 2.0)": np.array([2.0, 3.0, 4.0, 3.0]),
    "wide (spread 11.0)": np.array([11.0, 0.0, 6.0, 2.0]),
    "mgcv point": mgcv_pt,
}

print(f"{'point':<24}{'formed-S err':>15}{'sqrt-form err':>16}{'improvement':>14}")
for name, pt in points.items():
    lam = 10.0**pt
    S = np.zeros_like(blocks[0])
    for lm, b in zip(lam, blocks, strict=True):
        S = S + lm * b
    with threadpool_limits(limits=1, user_api="blas"):
        beta, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
    beta = np.array(beta, dtype=np.float64, copy=True)

    truth = float(beta.astype(np.longdouble) @ S.astype(np.longdouble) @ beta.astype(np.longdouble))
    formed = float(beta @ S @ beta)
    sqrt_form = float(
        sum(
            lm * float(np.sum((block_sqrt(b).T @ beta) ** 2))
            for lm, b in zip(lam, blocks, strict=True)
        )
    )
    e1, e2 = abs(formed - truth), abs(sqrt_form - truth)
    print(f"{name:<24}{e1:15.3e}{e2:16.3e}{(e1 / max(e2, 1e-300)):13.1f}x")

print("\nAnd the thread axis on the same quantity:")
print(f"{'point':<24}{'formed-S d':>14}{'sqrt-form d':>15}")
for name, pt in points.items():
    lam = 10.0**pt
    S = np.zeros_like(blocks[0])
    for lm, b in zip(lam, blocks, strict=True):
        S = S + lm * b
    roots = [block_sqrt(b) for b in blocks]
    A, B = [], []
    for th in (1, 2, 4):
        with threadpool_limits(limits=th, user_api="blas"):
            c, _ = penalized_fit_and_score(y, x, family, blocks, pt, weights=w)
            c = np.array(c, dtype=np.float64, copy=True)
        A.append(float(c @ S @ c))
        B.append(
            float(sum(lm * float(np.sum((L.T @ c) ** 2)) for lm, L in zip(lam, roots, strict=True)))
        )
    dA = max(abs(A[i] - A[j]) for i in range(3) for j in range(i + 1, 3))
    dB = max(abs(B[i] - B[j]) for i in range(3) for j in range(i + 1, 3))
    print(f"{name:<24}{dA:14.3e}{dB:15.3e}")
