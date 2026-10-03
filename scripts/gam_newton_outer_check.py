#!/usr/bin/env python3
"""Outer-solver epic Slices 1-2 (ADR-242, ADR-243): the safeguarded Newton search
against ``mgcv`` on the free-scale cells ADR-241 diagnosed — with the EXACT
Hessian (Slice 2, the default) beside Slice 1's differenced Hessian and the
L-BFGS-B search from the same ``initial.spg`` start, so function evaluations
per fit are reported side by side.

Usage: gam_newton_outer_check.py <probe_dir> [report.md]

For gaussian L1, quasipoisson 3b and the quasipoisson 3c draw it fits with
``fit_polaris_gam(outer="newton")`` — ONE start (``initial.spg``), no
multistart — and compares against the R payload under ADR-221's committed
``eta``/``edf_total`` gate, plus the search's own behaviour (largest accepted
step, how it stopped, gradient against its tolerance).

Provenance (ADR-193): the comparison is the SAME as the existing free-sp
claims' — ``fit_*_free_sp_case`` takes an ``R*FreeSpRecipe`` that structurally
excludes ``eta``/``coef``/``sp``/``edf``, so ``eta`` and ``edf_total`` are
INDEPENDENT; the headline comes from ``evidence_markdown`` of those claims.
The step/gradient columns are Polaris-only MEASUREMENTS (own criterion), not a
comparison. Reports; gates nothing.
"""

import functools
import json
import sys
from pathlib import Path

import numpy as np

from polaris_re.analytics import gam_model
from polaris_re.analytics.gam_gaussian_conformance import (
    GAUSSIAN_FREE_SP_CLAIM,
    compare_gaussian_free_sp_case,
    fit_gaussian_free_sp_case,
)
from polaris_re.analytics.gam_initial_sp_default_conformance import dispersion_draw_payload
from polaris_re.analytics.gam_quasipoisson_conformance import (
    QUASIPOISSON_FREE_SP_CLAIM,
    compare_quasipoisson_free_sp_case,
    fit_quasipoisson_free_sp_case,
)
from polaris_re.analytics.gam_reml_newton import (
    MGCV_NEWTON_MAX_NSTEP,
    NewtonLambdaSelection,
    newton_variant,
)
from polaris_re.core.verification import evidence_markdown

CELLS = (
    ("gaussian L1", "gam_gaussian_free_sp_probe.json", "gaussian"),
    ("quasipoisson 3b", "gam_quasipoisson_free_sp_probe.json", "quasipoisson"),
    ("quasipoisson 3c draw", "gam_dispersion_two_stage_probe.json", "quasipoisson"),
)
_LN10 = float(np.log(10.0))


def main(probe_dir: Path, out: Path | None) -> None:
    lines = [
        "",
        "### Outer-solver slices 1-2 — safeguarded Newton (exact Hessian), one start, vs mgcv",
        "",
        "**Claim (ADR-193):** the Polaris free-sp fit (producer takes a recipe that excludes "
        "mgcv's eta/coef/sp/edf) and mgcv's own free-sp REML fit compute eta and edf_total "
        "independently. Newton-specific columns are Polaris-only measurements.",
        "",
        evidence_markdown(newton_variant(GAUSSIAN_FREE_SP_CLAIM)),
        "",
        evidence_markdown(newton_variant(QUASIPOISSON_FREE_SP_CLAIM)),
        "",
        "| cell | max abs eta diff | edf_total diff | own score | converged (gradient test) "
        "| agrees (ADR-221) | eta/edf only | max accepted step (decades) | cap (decades) "
        "| max abs proj. gradient | tolerance | eps*cond(H) | fits | exit |",
        "|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    captured: list[NewtonLambdaSelection] = []
    original = gam_model.newton_select_lambdas
    cost_rows: list[str] = []

    def spy(*args: object, **kwargs: object) -> NewtonLambdaSelection:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        captured.append(result)
        return result

    gam_model.newton_select_lambdas = spy  # type: ignore[assignment]
    try:
        for label, name, kind in CELLS:
            probe = json.loads((probe_dir / name).read_text())
            payload = dispersion_draw_payload(probe) if "joint" in probe else probe
            if kind == "gaussian":
                fit = fit_gaussian_free_sp_case(payload, outer="newton")
                comp = compare_gaussian_free_sp_case(fit, payload)
            else:
                fit = fit_quasipoisson_free_sp_case(payload, outer="newton")
                comp = compare_quasipoisson_free_sp_case(fit, payload)
            sel = captured[-1]
            # Cost comparison, same cell and start: Slice 1's differenced
            # Hessian, and L-BFGS-B from initial.spg. Both are Polaris-only
            # measurements (fits spent), not comparisons against mgcv.
            gam_model.newton_select_lambdas = functools.partial(  # type: ignore[assignment]
                original, hessian="difference"
            )
            try:
                if kind == "gaussian":
                    diff_fit = fit_gaussian_free_sp_case(payload, outer="newton")
                    lb_fit = fit_gaussian_free_sp_case(payload, initial_sp_start=True)
                else:
                    diff_fit = fit_quasipoisson_free_sp_case(payload, outer="newton")
                    lb_fit = fit_quasipoisson_free_sp_case(payload, initial_sp_start=True)
            finally:
                gam_model.newton_select_lambdas = spy  # type: ignore[assignment]
            cost_rows.append(
                f"| {label} | {sel.n_function_evals} | {diff_fit.n_function_evals} "
                f"| {lb_fit.n_function_evals} | {fit.reml_score:.4f} | {diff_fit.reml_score:.4f} "
                f"| {lb_fit.reml_score:.4f} |"
            )
            eta_edf_only = comp["max_abs_eta_diff"] < 2e-2 and abs(comp["edf_total_diff"]) < 1.0
            lines.append(
                f"| {label} | {comp['max_abs_eta_diff']:.3e} | {comp['edf_total_diff']:+.3f} "
                f"| {fit.reml_score:.4f} | {sel.converged} | {comp['agrees']} | {eta_edf_only} "
                f"| {sel.max_accepted_step_decades:.3f} | {MGCV_NEWTON_MAX_NSTEP / _LN10:.3f} "
                f"| {sel.max_abs_projected_gradient:.3e} | {sel.gradient_tolerance:.3e} "
                f"| {sel.gradient_precision_floor:.2e} | {sel.n_function_evals} "
                f"| {sel.message} |"
            )
    finally:
        gam_model.newton_select_lambdas = original  # type: ignore[assignment]
    lines += [
        "",
        "#### Function evaluations per fit (Polaris-only measurement, same start)",
        "",
        "| cell | Newton, exact Hessian (Slice 2) | Newton, differenced Hessian (Slice 1) "
        "| L-BFGS-B from initial.spg | own score (exact) | own score (differenced) "
        "| own score (L-BFGS-B) |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *cost_rows,
    ]
    report = "\n".join(lines) + "\n"
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
