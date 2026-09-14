"""PLAN slice 7i -- re-justify `_FINITE_DIFF_STEP` post-slice-7h.

Slice 7h's sum-of-squares penalty evaluation (ADR-223) removed the specific
cancellation `_FINITE_DIFF_STEP=1e-5` (ADR-212) was originally measured
against, so `TestFiniteDiffStep`'s historical tests no longer discriminate it
on their own fixture (PR #229 review [P1], ADR-223 amendment 2). This script
re-measures the actual trade-off directly, against the independently-derived
ANALYTIC gradient (`gam_reml_gradient.reml_score_gradient`, slice 7d) rather
than only a central-difference cross-check, at forward-difference step sizes
spanning `1e-3` to `1e-10`, on:

  (a) a well-conditioned toy problem (single penalty block, no near-flat
      direction) -- the "uncommitted, well-conditioned fixture" PR #216's
      review used, now committed and reproducible;
  (b) the SAME N=4 near-flat fixture `_FINITE_DIFF_STEP` was derived on
      (`tests/fixtures/gam_reml_optimize_near_flat_direction.json`), at its
      own production-converged point AND at a wide (11-decade) synthetic
      `log10(lambda)` spread -- the badly-conditioned regime this module's
      `select=TRUE` callers actually reach (ADR-217/218).

--------------------------------------------------------------------------------
VERIFICATION PROVENANCE (ADR-193). MEASUREMENT (own criterion). Both operands
in every comparison below are Polaris's own (a forward-difference estimate of
`penalized_fit_and_score`'s score, against `reml_score_gradient`'s analytic
value at the same point) -- no `mgcv` quantity is an operand anywhere in this
script, so no `VerificationClaim` applies and nothing here may be cited as
parity or agreement evidence.

USAGE:  uv run python scripts/gam_finite_diff_step_tradeoff_diagnostic.py
--------------------------------------------------------------------------------
"""

import json
import pathlib

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_family import poisson_log
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.analytics.gam_reml_optimize import _FINITE_DIFF_STEP, penalized_fit_and_score

STEPS = (1e-3, 1e-4, 1e-5, 1.49e-8, 1e-6, 1e-7, 1e-9, 1e-10)


def scan(name: str, y, x, family, blocks, weights, point: np.ndarray) -> None:
    with threadpool_limits(limits=1, user_api="blas"):
        coef, base = penalized_fit_and_score(y, x, family, blocks, point, weights=weights)
        analytic = reml_score_gradient(
            y, x, family, np.asarray(coef), blocks, 10.0**point, weights=weights
        ) * np.log(10.0)  # d/d(log10 lambda) -- matches this module's own convention

    def score_at(p: np.ndarray) -> float:
        with threadpool_limits(limits=1, user_api="blas"):
            _, s = penalized_fit_and_score(y, x, family, blocks, p, weights=weights)
        return s

    n = len(point)
    print(f"\n=== {name} ===  analytic grad: {analytic}  (norm={np.linalg.norm(analytic):.6g})")
    print(f"{'h':>10}", *(f"err(coord{i})".rjust(14) for i in range(n)), f"{'norm err':>14}")
    for h in sorted(STEPS):
        fd = np.zeros(n)
        for i in range(n):
            d = np.zeros(n)
            d[i] = h
            fd[i] = (score_at(point + d) - base) / h
        err = fd - analytic
        marker = (
            " <- production"
            if h == _FINITE_DIFF_STEP
            else (" <- scipy default" if h == 1.49e-8 else "")
        )
        print(f"{h:10.2e}", *(f"{e:14.3e}" for e in err), f"{np.linalg.norm(err):14.3e}{marker}")


rng = np.random.default_rng(20260907)
n, p = 200, 6
x_toy = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
beta_true = rng.normal(scale=0.3, size=p)
y_toy = rng.poisson(np.exp(x_toy @ beta_true)).astype(np.float64)
d = np.diff(np.eye(p), n=2, axis=0)
s_toy = d.T @ d
scan(
    "(a) well-conditioned toy (n=200,p=6, single block)",
    y_toy,
    x_toy,
    poisson_log(),
    (s_toy,),
    None,
    np.array([0.7]),
)

payload = json.loads(
    pathlib.Path("tests/fixtures/gam_reml_optimize_near_flat_direction.json").read_text()
)
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
blocks = tuple(design["penalty_blocks"])
x4 = design["x"]

converged_point = np.array([6.6936256, 10.87308158, 3.29210116, 3.02948975])
scan(
    "(b1) N=4 near-flat fixture, production-converged point",
    y,
    x4,
    family,
    blocks,
    weights,
    converged_point,
)

wide_point = np.array([11.0, 0.0, 6.0, 2.0])
scan(
    "(b2) N=4 near-flat fixture, WIDE synthetic spread", y, x4, family, blocks, weights, wide_point
)
