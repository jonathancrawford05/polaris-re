"""Cross-start reproducibility of the fitted surface: widened seed axis + thread axis.

Maintainer-directed (2026-09-05). Two axes:

  A. SEED  — 10 seeds of multistart(9). Tests "is best-of-9 enough starts?".
  B. THREAD — the pinned production seed under OPENBLAS_NUM_THREADS in {1,2,4}.
     The local proxy for ADR-219 amendment 3's cross-runner axis; ADR-211/213
     established this search's thread sensitivity, and `threadpool_limits` is
     how this repo's own tests reach an already-imported OpenBLAS (the env var
     alone does not).

Tolerance benchmark: ADR-221's own mgcv-agreement gate, eta < 2e-2 and
|d edf_total| < 1.0. The maintainer asked for self-reproducibility to be held
TIGHTER than that, so clearing it with margin is the bar, not merely clearing it.

--------------------------------------------------------------------------------
PROVENANCE. This is the script that produced ADR-222 amendment 1's numbers. It was written in
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

USAGE:  uv run python scripts/gam_convergence_two_axis_diagnostic.py probe7.json
--------------------------------------------------------------------------------
"""

import json
import sys
from dataclasses import replace

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_model import (
    PRODUCTION_LOG10_BOUNDS,
    assemble_model_design,
    resolve_family,
)
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import (
    select_lambdas_continuous,
    select_lambdas_continuous_multistart,
)

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

PRODUCTION_SEED = 20260830
SEEDS = [
    20260830, 20260901, 20260902, 20260905, 20260906,
    20260907, 20260908, 20260909, 20260910, 20260911,
]


def multi(seed: int, threads: int):
    with threadpool_limits(limits=threads, user_api="blas"):
        ms = select_lambdas_continuous_multistart(
            y, x, family, blocks, weights=w, bounds=PRODUCTION_LOG10_BOUNDS,
            n_starts=9, seed=seed, analytic_gradient=True, max_gtol_restarts=4,
        )
    b = ms.best
    return x @ np.asarray(b.coef, dtype=np.float64), float(b.edf_total), \
        np.asarray(b.log_lambda, dtype=np.float64), float(b.reml_score)


def single_fd(threads: int):
    with threadpool_limits(limits=threads, user_api="blas"):
        s = select_lambdas_continuous(
            y, x, family, blocks, weights=w, bounds=PRODUCTION_LOG10_BOUNDS
        )
    return x @ np.asarray(s.coef, dtype=np.float64), float(s.edf_total), \
        np.asarray(s.log_lambda, dtype=np.float64), float(s.reml_score)


def spreads(label, etas, edfs, sps, n_attempted):
    if len(etas) < 2:
        print(f"\n  {label}: fewer than two fits — no spread", flush=True)
        return
    def pm(v, fn):
        return max(fn(v[i], v[j]) for i in range(len(v)) for j in range(i + 1, len(v)))
    e = pm(etas, lambda a, b: float(np.max(np.abs(a - b))))
    s = pm(sps, lambda a, b: float(np.max(np.abs(a - b))))
    d = pm(edfs, lambda a, b: abs(a - b))
    ok = e < 2e-2 and d < 1.0
    print(f"\n  === {label} ===", flush=True)
    print(f"  fits: {len(etas)}/{n_attempted}", flush=True)
    print(f"  max |d log10(sp)| : {s:12.6f}   <- machinery", flush=True)
    print(f"  max |d eta|       : {e:12.6e}   <- surface   (gate 2e-2)", flush=True)
    print(f"  max |d edf_total| : {d:12.6f}   <- surface   (gate 1.0)", flush=True)
    print(f"  margin on eta: {2e-2 / e:.1f}x   margin on edf: {1.0 / d:.1f}x" if ok
          else "  OUTSIDE the gate", flush=True)
    print(f"  -> {'REPRODUCIBLE' if ok else 'NOT reproducible'}", flush=True)


print("=" * 78, flush=True)
print("AXIS A — 10 seeds of multistart(9), analytic + restarts, threads=1", flush=True)
print("=" * 78, flush=True)
print(f"{'seed':>10}{'edf_total':>12}{'score':>15}   log10(sp)", flush=True)
A = ([], [], [])
for sd in SEEDS:
    try:
        eta, edf, sp, sc = multi(sd, 1)
    except Exception as exc:
        print(f"{sd:>10}   FAILED — {type(exc).__name__}: {str(exc)[:60]}", flush=True)
        continue
    A[0].append(eta); A[1].append(edf); A[2].append(sp)
    print(f"{sd:>10}{edf:12.4f}{sc:15.6f}   [{', '.join(f'{v:6.2f}' for v in sp)}]", flush=True)
spreads("AXIS A: multistart(9) across 10 seeds", A[0], A[1], A[2], len(SEEDS))

print("\n" + "=" * 78, flush=True)
print(f"AXIS B — threads in (1,2,4), multistart(9), pinned seed {PRODUCTION_SEED}", flush=True)
print("=" * 78, flush=True)
print(f"{'threads':>10}{'edf_total':>12}{'score':>15}   log10(sp)", flush=True)
B = ([], [], [])
for th in (1, 2, 4):
    try:
        eta, edf, sp, sc = multi(PRODUCTION_SEED, th)
    except Exception as exc:
        print(f"{th:>10}   FAILED — {type(exc).__name__}: {str(exc)[:60]}", flush=True)
        continue
    B[0].append(eta); B[1].append(edf); B[2].append(sp)
    print(f"{th:>10}{edf:12.4f}{sc:15.6f}   [{', '.join(f'{v:6.2f}' for v in sp)}]", flush=True)
spreads("AXIS B: multistart(9) across thread counts", B[0], B[1], B[2], 3)

print("\n" + "=" * 78, flush=True)
print("AXIS B' — threads in (1,2,4), SINGLE-start finite-difference (the default)", flush=True)
print("=" * 78, flush=True)
print(f"{'threads':>10}{'edf_total':>12}{'score':>15}   log10(sp)", flush=True)
C = ([], [], [])
for th in (1, 2, 4):
    try:
        eta, edf, sp, sc = single_fd(th)
    except Exception as exc:
        print(f"{th:>10}   FAILED — {type(exc).__name__}: {str(exc)[:60]}", flush=True)
        continue
    C[0].append(eta); C[1].append(edf); C[2].append(sp)
    print(f"{th:>10}{edf:12.4f}{sc:15.6f}   [{', '.join(f'{v:6.2f}' for v in sp)}]", flush=True)
spreads("AXIS B': single-start FD across thread counts", C[0], C[1], C[2], 3)
