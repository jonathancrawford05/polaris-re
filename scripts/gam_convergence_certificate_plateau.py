#!/usr/bin/env python3
"""Outer-solver Slice 4 closure (ADR-248): the convergence-certificate plateau
measurement that ``PROPOSAL_convergence_certificate.md`` §6 left owed — the
restricted projected-gradient residual at the point the search actually stops,
on the post-7h criterion, on the N=4 control and the ``select=TRUE`` N=7
structure — and the two numbers it was blocking (``eps_rel`` and the
curvature-to-noise rule).

Usage: gam_convergence_certificate_plateau.py [report.md]

Provenance (ADR-193): MEASUREMENT (own criterion). Every number is a property of
Polaris's own REML criterion at Polaris's own selected point. The fixtures are R
draws (``scripts/gam_multiterm_free_sp_probe.R`` /
``gam_select_multiterm_free_sp_probe.R``) with ``mgcv``'s outputs stripped, so no
``mgcv`` value is read; there is no second producer and no ``VerificationClaim``.

Per fixture and search (Newton — the default after ADR-248 — and L-BFGS-B for
context), at the selected ``rho`` (natural-log lambda, the units of ``mgcv``'s
``conv.tol`` and of the Newton stopping test):

- ``eps_f``: spread of the REML score at that fixed ``rho`` across BLAS threads
  1/2/4, twice — the noise floor (PROPOSAL §3 Part 1).
- identified directions: the step-stability scan
  (:func:`~polaris_re.analytics.gam_sp_identifiability.derive_floor_from_step_stability`,
  ADR-219) — a direction is flat when its diagonal second difference grows like
  ``1/h^2`` over the 8x step range. No chosen constant.
- the projected gradient's inf-norm relative to ``1 + |score|``, unrestricted and
  restricted to the identified-and-free subspace (PROPOSAL §3 Part 2).
- second-order: the smallest eigenvalue of the exact Hessian on that subspace
  (PROPOSAL §3 Part 3).
- the remaining Newton step ``H^-1 g`` (in decades) and the decrement
  ``g'H^-1 g / 2``: how far, and for how much score, the stopping point sits from
  the stationary point.
"""

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_model import assemble_model_design, fit_polaris_gam, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml import penalty_block_square_roots
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.analytics.gam_reml_hessian import reml_score_hessian
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score, projected_gradient
from polaris_re.analytics.gam_sp_identifiability import derive_floor_from_step_stability

_LN10 = float(np.log(10.0))
_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
_CASES = (
    ("N=4 control (cr+by+ti)", "gam_reml_optimize_near_flat_direction.json", False),
    ("select=TRUE N=7", "gam_fit_select7_penalty_spread.json", True),
)
_BOUNDS = (-2.0, 12.0)
_CANDIDATES = (1.0e-6, 1.0e-8)
"""``mgcv``'s ``gam.control()$newton$conv.tol`` and the PROPOSAL's provisional value."""


@dataclass(frozen=True)
class PlateauReading:
    case: str
    outer: str
    converged: bool
    n_fits: int
    score: float
    eps_f: float
    n_identified: int
    n_blocks: int
    min_identified_curvature: float
    rel_projected_gradient: float
    rel_restricted_gradient: float
    min_reduced_curvature: float
    max_remaining_step_decades: float
    remaining_decrement: float
    error: str | None = None


def _measure(case: str, fixture: str, select: bool, outer: str) -> PlateauReading:
    payload = json.loads((_FIXTURES / fixture).read_text())
    model = _multiterm_model_spec(
        tuple(float(v) for v in payload["age_knots"]),
        tuple(float(v) for v in payload["year_knots"]),
    )
    if select:
        model = replace(model, select=True)
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    y = np.asarray(payload["y"], dtype=np.float64)
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    x, blocks, w = design["x"], tuple(design["penalty_blocks"]), data["ExposCnt"]
    sqrt_blocks = penalty_block_square_roots(blocks)

    def score_at(rho: np.ndarray) -> float:
        return penalized_fit_and_score(
            y, x, family, blocks, rho / _LN10, weights=w, penalty_sqrt_blocks=sqrt_blocks
        )[1]

    with threadpool_limits(limits=1, user_api="blas"):
        fit = fit_polaris_gam(model, data, y, outer=outer)  # type: ignore[arg-type]
        rho = fit.log_lambda * _LN10
        coef, score = penalized_fit_and_score(
            y, x, family, blocks, fit.log_lambda, weights=w, penalty_sqrt_blocks=sqrt_blocks
        )
        lambdas = np.exp(rho)
        grad = reml_score_gradient(
            y, x, family, coef, blocks, lambdas, weights=w, penalty_sqrt_blocks=sqrt_blocks
        )
        hess = reml_score_hessian(
            y, x, family, coef, blocks, lambdas, weights=w, penalty_sqrt_blocks=sqrt_blocks
        )
        floor = derive_floor_from_step_stability(score_at, score, rho, hess)
    scores = []
    for n in (1, 2, 4, 1, 2, 4):
        with threadpool_limits(limits=n, user_api="blas"):
            scores.append(score_at(rho))
    eps_f = float(max(scores) - min(scores))

    lo, hi = _BOUNDS[0] * _LN10, _BOUNDS[1] * _LN10
    p_grad = projected_gradient(grad, rho, (lo, hi))
    free = ~(np.isclose(fit.log_lambda, _BOUNDS[0]) | np.isclose(fit.log_lambda, _BOUNDS[1]))
    evals, evecs = np.linalg.eigh(hess)
    identified = evals > floor if floor > 0.0 else evals > 0.0
    basis = evecs[:, identified]
    restricted = basis @ (basis.T @ (p_grad * free))
    reduced = hess[np.ix_(free, free)]
    if np.all(identified) and np.all(free):
        step = np.linalg.solve(hess, grad)
    else:
        step = np.full_like(grad, np.nan)
    return PlateauReading(
        case=case,
        outer=outer,
        converged=bool(fit.converged),
        n_fits=int(fit.n_function_evals),
        score=float(score),
        eps_f=eps_f,
        n_identified=int(np.count_nonzero(identified)),
        n_blocks=int(evals.size),
        min_identified_curvature=float(evals[identified].min()) if identified.any() else 0.0,
        rel_projected_gradient=float(np.max(np.abs(p_grad)) / (1.0 + abs(score))),
        rel_restricted_gradient=float(np.max(np.abs(restricted)) / (1.0 + abs(score))),
        min_reduced_curvature=float(np.linalg.eigvalsh(reduced).min()),
        max_remaining_step_decades=float(np.max(np.abs(step)) / _LN10),
        remaining_decrement=float(0.5 * grad @ step),
    )


def _guarded(case: str, fixture: str, select: bool, outer: str) -> PlateauReading:
    """A case whose fit or step-stability probe raises is an ERROR row, never
    dropped and never fatal to the other rows (the gauntlet's own rule). A probe
    at ``rho +- h`` can land in an inner-IRLS non-convergent neighbourhood
    (ADR-222/224), which varies by environment (ADR-224 amendment 1)."""
    try:
        reading = _measure(case, fixture, select, outer)
    except Exception as exc:  # reported in the table, never swallowed
        nan = float("nan")
        reading = PlateauReading(
            case, outer, False, -1, nan, nan, 0, 0, nan, nan, nan, nan, nan, nan, repr(exc)
        )
    print(f"measured: {reading.case} / {reading.outer}: {reading.error or 'ok'}", flush=True)
    return reading


def main(out: Path | None) -> None:
    readings = [
        _guarded(case, fixture, select, outer)
        for case, fixture, select in _CASES
        for outer in ("newton", "lbfgsb")
    ]
    lines = [
        "",
        "### Outer-solver Slice 4 closure — convergence-certificate plateau (ADR-248)",
        "",
        "**MEASUREMENT (own criterion), NOT parity evidence (ADR-193):** Polaris's own "
        "REML criterion at Polaris's own selected point, on two committed R draws with "
        "mgcv's outputs stripped. No mgcv value is read.",
        "",
        "| case | search | converged | fits | score | eps_f | identified (step-stability) "
        "| min identified curvature | rel proj. grad | rel restricted grad "
        "| min reduced curvature | remaining step (decades) | remaining decrement "
        + "".join(f"| certified at eps_rel={c:g} " for c in _CANDIDATES)
        + "| error |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        + "---|" * len(_CANDIDATES)
        + "---|",
        *[
            f"| {r.case} | {r.outer} | {r.converged} | {r.n_fits} | {r.score:.6f} "
            f"| {r.eps_f:.1e} | {r.n_identified} of {r.n_blocks} "
            f"| {r.min_identified_curvature:.3e} | {r.rel_projected_gradient:.2e} "
            f"| {r.rel_restricted_gradient:.2e} | {r.min_reduced_curvature:.3e} "
            f"| {r.max_remaining_step_decades:.3f} | {r.remaining_decrement:.1e} "
            + "".join(
                f"| {r.rel_restricted_gradient <= c and r.min_reduced_curvature > 0.0} "
                for c in _CANDIDATES
            )
            + f"| {r.error or ''} |"
            for r in readings
        ],
        "",
    ]
    report = "\n".join(lines)
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
