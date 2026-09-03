"""Diagnostic (not parity evidence): does the analytic REML gradient
(:mod:`~polaris_re.analytics.gam_reml_gradient`, PLAN slice 7d) actually
change `select_lambdas_continuous`'s own behaviour on the 7-block
`select=TRUE` structure, and is SciPy's own `converged` flag trustworthy now
that the gradient it receives is exact rather than finite-differenced?

WHAT THIS PROBES
-----------------
1. **Blind single-start, finite-difference vs analytic gradient.** Same
   starting point, same criterion — only the gradient SciPy receives
   differs. PLAN slice 7d's own registered prediction is about the score
   gap on the IDENTIFIED directions, never about raw `log10(sp)` (slice 7c
   Part 0 already found two of the seven directions unidentified at mgcv's
   own point).
2. **Is `converged=True` trustworthy?** The TRUE gradient
   (:func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`,
   the SAME function supplied to SciPy as `jac=`) is recomputed at whatever
   point SciPy reports, independently of the search — if its norm is large
   despite `converged=True`, that is either a genuinely unidentified
   direction (slice 7c Part 0's own finding) or a different SciPy stopping
   criterion firing (read from `message`) rather than the gradient
   tolerance the caller set.
3. **Warm-start, analytic gradient.** Same discriminator ADR-211/212 used
   at N=4 and ``gam_select_free_sp_warmstart_diagnostic.py`` uses here:
   supplying `mgcv`'s own selection as `x0` makes this DIAGNOSTIC (the
   mechanical test in ``docs/VERIFICATION_STANDARD.md`` fails on sight —
   the input includes the other side's own selection), never
   `SELECT_FREE_SP_MODEL_CLAIM` evidence.

Usage:
    Rscript scripts/gam_select_multiterm_free_sp_probe.R \\
        gam_select_multiterm_free_sp_probe.json
    uv run python scripts/gam_reml_gradient_diagnostic.py \\
        gam_select_multiterm_free_sp_probe.json
"""

import json
import sys
from dataclasses import replace

import numpy as np

from polaris_re.analytics.gam_model import (
    PRODUCTION_LOG10_BOUNDS,
    assemble_model_design,
    resolve_family,
)
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.analytics.gam_reml_optimize import (
    select_lambdas_continuous,
    select_lambdas_continuous_multistart,
)


def _true_gradient_norm_log10(
    y: np.ndarray,
    x: np.ndarray,
    family: object,
    blocks: tuple[np.ndarray, ...],
    weights: np.ndarray,
    log10_lambda: np.ndarray,
    coef: np.ndarray,
) -> float:
    lambdas = 10.0**log10_lambda
    gradient_natural = reml_score_gradient(y, x, family, coef, blocks, lambdas, weights=weights)
    return float(np.linalg.norm(gradient_natural * np.log(10.0)))


def main(payload_path: str) -> None:
    with open(payload_path) as fh:
        payload = json.load(fh)

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
    weights = data["ExposCnt"]
    blocks = tuple(design["penalty_blocks"])
    x = design["x"]
    mgcv_log10_sp = np.log10(np.asarray(payload["sp"], dtype=np.float64))

    print(f"n={len(y)}  p={x.shape[1]}  blocks={len(blocks)}")
    print(f"mgcv {payload.get('mgcv_version', '?')} / {payload.get('r_version', '?')}")
    print()
    print(
        "NOT SELECT_FREE_SP_MODEL_CLAIM evidence: the warm-start row's x0 IS "
        "mgcv's own selection (TRANSPORT, docs/VERIFICATION_STANDARD.md). The "
        "blind rows ARE the same INDEPENDENT comparator as SELECT_FREE_SP_MODEL_"
        "CLAIM (see that step's own table) — this script adds the true-gradient-"
        "norm and SciPy-message columns that comparator does not carry."
    )
    print()

    multi_fd = select_lambdas_continuous_multistart(
        y, x, family, blocks, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS, n_starts=9
    )
    multi_an = select_lambdas_continuous_multistart(
        y,
        x,
        family,
        blocks,
        weights=weights,
        bounds=PRODUCTION_LOG10_BOUNDS,
        n_starts=9,
        analytic_gradient=True,
    )
    # (selection, total nfev across every start it took to find it — 1 for a
    # plain single-start selection, the multistart run's own summed cost
    # otherwise, so the reported nfev is the search's real total cost, not
    # just the winning start's own count).
    runs: dict[str, tuple[object, int]] = {
        "blind, finite-difference (default)": (
            (
                s := select_lambdas_continuous(
                    y, x, family, blocks, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS
                )
            ),
            s.n_function_evals,
        ),
        "blind, analytic gradient (slice 7d)": (
            (
                s := select_lambdas_continuous(
                    y,
                    x,
                    family,
                    blocks,
                    weights=weights,
                    bounds=PRODUCTION_LOG10_BOUNDS,
                    analytic_gradient=True,
                )
            ),
            s.n_function_evals,
        ),
        "multistart(9), finite-difference": (multi_fd.best, multi_fd.total_function_evals),
        "multistart(9), analytic gradient (slice 7d)": (
            multi_an.best,
            multi_an.total_function_evals,
        ),
        "warm-start at mgcv's point, analytic gradient": (
            (
                s := select_lambdas_continuous(
                    y,
                    x,
                    family,
                    blocks,
                    weights=weights,
                    x0=mgcv_log10_sp,
                    bounds=PRODUCTION_LOG10_BOUNDS,
                    analytic_gradient=True,
                )
            ),
            s.n_function_evals,
        ),
    }

    header = (
        f"{'search':<46}{'total nfev':>11}{'score':>12}{'converged':>11}"
        f"{'at_bound':>10}{'|true grad|':>13}"
    )
    print(header)
    for label, (sel, total_nfev) in runs.items():
        true_grad_norm = _true_gradient_norm_log10(
            y, x, family, blocks, weights, sel.log_lambda, sel.coef
        )
        print(
            f"{label:<46}{total_nfev:>11}{sel.reml_score:>12.6f}"
            f"{sel.converged!s:>11}{sel.at_bound!s:>10}{true_grad_norm:>13.6f}"
        )
        print(f"{'':<46}message: {sel.message}")
    print()

    warm, _warm_nfev = runs["warm-start at mgcv's point, analytic gradient"]
    warm_vs_mgcv = float(np.max(np.abs(warm.log_lambda - mgcv_log10_sp)))
    print(f"MAX ABS (warm-start log10(sp) - mgcv's own log10(sp)): {warm_vs_mgcv:.6f}")
    print()

    blind_an, _blind_an_nfev = runs["blind, analytic gradient (slice 7d)"]
    blind_an_grad_norm = _true_gradient_norm_log10(
        y, x, family, blocks, weights, blind_an.log_lambda, blind_an.coef
    )
    if blind_an.converged and blind_an_grad_norm > 1.0:
        print(
            "READING: SciPy reports converged=True at a point whose TRUE gradient "
            "(the exact analytic one, not a finite-difference estimate) has a large "
            "norm. Read the message column above — if it names a RELATIVE REDUCTION "
            "OF F (ftol-style) criterion rather than the gradient tolerance this "
            "caller set, that is a genuinely NEW finding, independent of ADR-212's "
            "finite-difference-noise mechanism: L-BFGS-B can report success via its "
            "own function-reduction stopping rule while leaving a large residual "
            "gradient on directions not pinned at a search bound."
        )
    else:
        print(
            "READING: the blind analytic-gradient search's own converged flag is "
            "consistent with its true gradient norm on this reading."
        )


if __name__ == "__main__":
    main(sys.argv[1])
