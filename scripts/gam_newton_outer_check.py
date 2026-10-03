#!/usr/bin/env python3
"""Outer-solver epic Slice 1 (ADR-242): the safeguarded Newton search against
``mgcv`` on the free-scale cells ADR-241 diagnosed.

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
from polaris_re.analytics.gam_reml_newton import MGCV_NEWTON_MAX_NSTEP, NewtonLambdaSelection
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
        "### Outer-solver slice 1 — safeguarded Newton, one start (`initial.spg`), vs mgcv",
        "",
        "**Claim (ADR-193):** the Polaris free-sp fit (producer takes a recipe that excludes "
        "mgcv's eta/coef/sp/edf) and mgcv's own free-sp REML fit compute eta and edf_total "
        "independently. Newton-specific columns are Polaris-only measurements.",
        "",
        "*Caveat on the claim text below:* it names `select_lambdas_continuous` as the "
        "smoothing-parameter search; in THIS report the search is `gam_reml_newton."
        'newton_select_lambdas` (`outer="newton"`). The independence classification is '
        "unchanged — the search is part of the Polaris producer either way.",
        "",
        evidence_markdown(GAUSSIAN_FREE_SP_CLAIM),
        "",
        evidence_markdown(QUASIPOISSON_FREE_SP_CLAIM),
        "",
        "| cell | max abs eta diff | edf_total diff | own score | converged (gradient test) "
        "| agrees (ADR-221) | eta/edf only | max accepted step (decades) | cap (decades) "
        "| max abs proj. gradient | tolerance | eps*cond(H) | fits | exit |",
        "|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    captured: list[NewtonLambdaSelection] = []
    original = gam_model.newton_select_lambdas

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
    report = "\n".join(lines) + "\n"
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
