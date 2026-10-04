#!/usr/bin/env python3
"""Outer-solver epic Slice 3 (ADR-244): where does the REML pipeline's rounding
noise live at an 11-decade ``lambda`` spread, and is the search reproducible?

Usage: gam_precision_floor_probe.py <select_multiterm_probe.json> [report.md]

The payload is ``scripts/gam_select_multiterm_free_sp_probe.R``'s output (the
``select=TRUE`` N=7 structure ADR-222 amendment 1 measured on). Three readings:

A. THREAD AXIS on the Newton search (exact Hessian, ``initial.spg`` start, no
   multistart), ``OPENBLAS`` threads 1/2/4 and a repeat at 1 — ADR-222
   amendment 1's protocol, beside its readings. The SEED axis has no operand
   here: Newton from ``initial.spg`` has no random component.
B. ``beta' S beta`` against ``float128``, beside ADR-222 amendment 2's table —
   formed ``S``, sum of squares over block roots, Appendix B's stable ``E``, and
   the TWO possible definitions of "truth" (formed ``S`` in ``float128`` vs the
   roots' own product in ``float128``).
C. The rounding-noise floor of the score, its analytic gradient and its exact
   Hessian: the same fit re-run with every design entry (``X``) and/or every
   penalty-block entry (``S``) perturbed by one relative ulp. ``X``-only
   isolates EVALUATION noise (the data's representation cannot matter to a
   backward-stable evaluation); ``S``-only is the problem's own sensitivity to
   its penalty's representation.

VERIFICATION PROVENANCE (ADR-193). NO ``mgcv`` comparison and no second
producer: every reading is Polaris measured against itself (across BLAS
threads, across ulp perturbations of its own inputs, or against ``float128`` on
its own expression). ``MEASUREMENT (own criterion)`` — never parity evidence.
The only ``mgcv`` quantity is ``payload['sp']``, used in B/C solely as a POINT
OF EVALUATION (``VERIFICATION_STANDARD.md`` §2.1). Reports; gates nothing.

To reproduce the BEFORE column of ADR-244, run this script at commit
``0bb65dc`` (before the gradient/Hessian quadratic forms moved to sums of
squares): it uses only APIs that exist at both commits.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_initial_sp import initial_log10_lambda
from polaris_re.analytics.gam_model import (
    PRODUCTION_LOG10_BOUNDS,
    assemble_model_design,
    resolve_family,
)
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml import penalty_block_square_roots
from polaris_re.analytics.gam_reml_appendix_b import appendix_b_transform
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.analytics.gam_reml_hessian import reml_score_hessian
from polaris_re.analytics.gam_reml_newton import newton_select_lambdas
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

_HALF_EPS = float(np.finfo(np.float64).eps) / 2.0
_N_PERTURBATIONS = 6


def _load(path: Path):
    payload = json.loads(path.read_text())
    model = replace(
        _multiterm_model_spec(
            tuple(float(v) for v in payload["age_knots"]),
            tuple(float(v) for v in payload["year_knots"]),
        ),
        select=True,
    )
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    y = np.asarray(payload["y"], dtype=np.float64)
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    return payload, y, design["x"], tuple(design["penalty_blocks"]), family, data["ExposCnt"]


def _evaluate(y, x, family, blocks, weights, point):
    lam = 10.0**point
    coef, score = penalized_fit_and_score(y, x, family, blocks, point, weights=weights)
    grad = reml_score_gradient(y, x, family, coef, blocks, lam, weights=weights)
    hess = reml_score_hessian(y, x, family, coef, blocks, lam, weights=weights)
    # The gradient as it was before ADR-244: term 1 contracted the FORMED block with
    # `coef`. Reconstructed exactly (known scale, gamma = 1) so the before/after is
    # measured by one script in one environment, not quoted from another one.
    roots = penalty_block_square_roots(blocks)
    legacy = grad + np.array(
        [
            lam[j]
            * (float(coef @ blocks[j] @ coef) - float(np.sum((roots[j].T @ coef) ** 2)))
            / 2.0
            for j in range(len(blocks))
        ]
    )
    return np.asarray(coef, dtype=np.float64), float(score), grad, hess, legacy


def thread_axis(y, x, family, blocks, weights, payload) -> list[str]:
    x0 = np.clip(
        initial_log10_lambda(y, x, family, blocks, weights=weights), *PRODUCTION_LOG10_BOUNDS
    )
    rows, ref = [], None
    for threads in (1, 2, 4, 1):
        with threadpool_limits(limits=threads, user_api="blas"):
            sel = newton_select_lambdas(
                y, x, family, blocks, x0=x0, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS
            )
        eta = x @ sel.coef
        if ref is None:
            ref = (sel.log_lambda, eta, sel.edf_total, sel.reml_score)
        rows.append(
            f"| {threads} | {sel.converged} | {sel.n_function_evals} | {sel.reml_score:.6f} "
            f"| {sel.edf_total:.4f} "
            f"| {np.max(np.abs(sel.log_lambda - ref[0])):.3e} "
            f"| {np.max(np.abs(eta - ref[1])):.3e} | {abs(sel.edf_total - ref[2]):.3e} "
            f"| {abs(sel.reml_score - ref[3]):.3e} |"
        )
    mg = np.log10(np.asarray(payload["sp"], dtype=np.float64))
    return [
        "### A. Thread axis — Newton (exact Hessian), one start, N=7 `select=TRUE` fixture",
        "",
        "| threads | converged | fits | score | edf_total | max d log10(sp) vs 1-thread "
        "| max d eta | d edf_total | d score |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        f"`mgcv`'s own log10(sp) (point of evaluation elsewhere): {np.round(mg, 3).tolist()}; "
        f"Polaris's stop: {np.round(ref[0], 3).tolist()}.",
        "",
        "ADR-222 amendment 1 beside it (multistart(9) + L-BFGS-B, same fixture, cross-thread): "
        "max d eta 0.356, d edf_total 10.002 (seed 20260830: d edf -9.94, d score +34.34); "
        "single-start finite-difference: d eta 4.65e-03, d edf 0.154.",
        "",
    ]


def float128_axis(y, x, family, blocks, weights, payload) -> list[str]:
    mg = np.log10(np.asarray(payload["sp"], dtype=np.float64))
    roots = penalty_block_square_roots(blocks)
    points = (
        ("narrow (spread 2.0)", np.array([2.0, 3.0, 4.0, 3.0, 2.0, 4.0, 3.0])),
        ("wide (spread 11.0)", np.array([11.0, 0.0, 10.0, 5.0, 3.0, 2.0, 1.0])),
        ("mgcv's point (12.9)", mg),
    )
    rows = []
    for name, point in points:
        lam = 10.0**point
        with threadpool_limits(limits=1, user_api="blas"):
            coef, _ = penalized_fit_and_score(y, x, family, blocks, point, weights=weights)
        coef = np.asarray(coef, dtype=np.float64)
        b128 = coef.astype(np.longdouble)
        s_formed = sum(lam[j] * blocks[j] for j in range(len(blocks)))
        formed = float(coef @ s_formed @ coef)
        sos = sum(lam[j] * float(np.sum((roots[j].T @ coef) ** 2)) for j in range(len(blocks)))
        e = appendix_b_transform(blocks, lam).e
        e_form = float(np.sum((e @ coef) ** 2))
        truth_s = float(
            b128
            @ sum(
                np.longdouble(lam[j]) * blocks[j].astype(np.longdouble) for j in range(len(blocks))
            )
            @ b128
        )
        truth_roots = float(
            sum(
                np.longdouble(lam[j]) * np.sum((roots[j].T.astype(np.longdouble) @ b128) ** 2)
                for j in range(len(blocks))
            )
        )
        rows.append(
            f"| {name} | {truth_s:.8f} | {abs(formed - truth_s):.2e} | {abs(sos - truth_s):.2e} "
            f"| {abs(e_form - truth_s):.2e} | {abs(sos - truth_roots):.2e} "
            f"| {abs(truth_s - truth_roots):.2e} |"
        )
    return [
        "### B. `beta' S beta` against `float128`",
        "",
        "Truth S = float128 sum of the float64 blocks; truth R = float128 sum of squares over the "
        "float64 block ROOTS. Columns 3-5 are errors against truth S (ADR-222 amendment 2's "
        "definition); column 6 is the sum-of-squares evaluation's error against ITS OWN "
        "float128 value (pure evaluation error); column 7 is the gap between the two "
        "definitions of truth.",
        "",
        "| point | truth S | formed S | sum of squares (ADR-223) | Appendix B `E` "
        "| sum of squares vs truth R | truth S vs truth R |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "ADR-222 amendment 2 beside it (formed S, float64 vs float128): narrow 1.137e-13, "
        "wide 6.823e-05, mgcv's point 2.520e-05; sum of squares 1.989e-04 and 5.447e-05.",
        "",
    ]


def noise_floor_axis(y, x, family, blocks, weights, payload, stop) -> list[str]:
    mg = np.log10(np.asarray(payload["sp"], dtype=np.float64))
    points = (
        ("narrow", np.array([2.0, 3.0, 4.0, 3.0, 2.0, 4.0, 3.0])),
        ("wide", np.array([11.0, 0.0, 10.0, 5.0, 3.0, 2.0, 1.0])),
        ("mgcv's point", mg),
        ("Newton stop", stop),
    )
    rows = []
    for name, point in points:
        for what in ("X only", "S only", "X and S"):
            with threadpool_limits(limits=1, user_api="blas"):
                c0, s0, g0, h0, l0 = _evaluate(y, x, family, blocks, weights, point)
                scale = np.sqrt(np.outer(np.abs(np.diag(h0)), np.abs(np.diag(h0))))
                d_score = d_grad = d_eta = d_hess = d_legacy = 0.0
                failures = 0
                for seed in range(_N_PERTURBATIONS):
                    rng = np.random.default_rng(100 + seed)
                    xx = x
                    if what != "S only":
                        xx = x * (1.0 + _HALF_EPS * rng.standard_normal(x.shape))
                    bl = blocks
                    if what != "X only":
                        noisy = []
                        for b in blocks:
                            z = rng.standard_normal(b.shape)
                            noisy.append(b * (1.0 + _HALF_EPS * 0.5 * (z + z.T)))
                        bl = tuple(noisy)
                    try:
                        c1, s1, g1, h1, l1 = _evaluate(y, xx, family, bl, weights, point)
                    except Exception:
                        failures += 1
                        continue
                    d_score = max(d_score, abs(s1 - s0))
                    d_grad = max(d_grad, float(np.max(np.abs(g1 - g0))))
                    d_legacy = max(d_legacy, float(np.max(np.abs(l1 - l0))))
                    d_eta = max(d_eta, float(np.max(np.abs(x @ c1 - x @ c0))))
                    d_hess = max(d_hess, float(np.max(np.abs(h1 - h0) / scale)))
            rows.append(
                f"| {name} | {what} | {d_score:.2e} | {d_grad:.2e} | {d_legacy:.2e} | {d_eta:.2e} "
                f"| {d_hess:.2e} | {failures}/{_N_PERTURBATIONS} |"
            )
    return [
        "### C. Rounding-noise floor (one relative ulp on `X` and/or `S`)",
        "",
        f"Max over {_N_PERTURBATIONS} perturbations. Hessian scaled by `sqrt(|H_ii H_jj|)`.",
        "",
        "| point | perturbed | d score | d gradient | d gradient (pre-ADR-244 term 1) | d eta "
        "| d Hessian (scaled) | inner-fit failures |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
    ]


def main(path: Path, out: Path | None) -> None:
    payload, y, x, blocks, family, weights = _load(path)
    x0 = np.clip(
        initial_log10_lambda(y, x, family, blocks, weights=weights), *PRODUCTION_LOG10_BOUNDS
    )
    with threadpool_limits(limits=1, user_api="blas"):
        stop = newton_select_lambdas(
            y, x, family, blocks, x0=x0, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS
        ).log_lambda
    lines = [
        "## Outer-solver Slice 3 — rounding noise at an 11-decade spread (own criterion)",
        "",
        "**MEASUREMENT (own criterion).** Polaris against itself — across BLAS threads, across "
        "one-ulp perturbations of its own inputs, or against `float128` on its own expression. "
        "No second producer; this is NOT parity evidence and gates nothing. `mgcv`'s `sp` is "
        "used only as a point of evaluation.",
        "",
        *thread_axis(y, x, family, blocks, weights, payload),
        *float128_axis(y, x, family, blocks, weights, payload),
        *noise_floor_axis(y, x, family, blocks, weights, payload, stop),
    ]
    text = "\n".join(lines)
    print(text)
    if out is not None:
        out.write_text(text + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
