#!/usr/bin/env python3
"""Outer-solver epic Slice 2 (ADR-243): Polaris's exact REML Hessian against
``mgcv``'s own ``outer.info$hess``.

Usage: gam_hessian_compare.py --probe gam_hessian_probe.json [--markdown out.md]

The Python half of ``scripts/gam_hessian_probe.R``. Provenance (ADR-193): the
Polaris producer is handed ``RHessianRecipe`` only (no ``mgcv`` Hessian or scale
key), so ``rho_hessian`` and — for gaussian — ``scale_hat`` are INDEPENDENT; the
headline is derived with ``evidence_markdown`` from the declared claim, never
hand-written. ``selected_sp`` is the shared POINT OF EVALUATION, not an operand.
Reports; gates nothing (the CI step is ``continue-on-error``).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from polaris_re.analytics.gam_hessian_conformance import (
    HESSIAN_AGREEMENT_TOL,
    HESSIAN_CLAIM,
    compare_hessian_case,
)
from polaris_re.core.verification import evidence_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", default="gam_hessian_probe.json")
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = json.loads(Path(args.probe).read_text())
    design = np.asarray(payload["design"], dtype=np.float64)
    penalties = tuple(np.asarray(b, dtype=np.float64) for b in payload["penalties"])

    lines = [
        "",
        "### Outer-solver slice 2 — exact REML Hessian vs mgcv `outer.info$hess`",
        "",
        f"mgcv: r_version={payload['r_version']!r} mgcv_version={payload['mgcv_version']!r}",
        "",
        evidence_markdown(HESSIAN_CLAIM),
        "",
        "| case | mgcv hess layout | max scaled diff (`abs(dH_ij) / sqrt(H_ii H_jj)`) "
        "| max abs diff | scale_hat rel diff (gaussian) | agrees "
        f"(< {HESSIAN_AGREEMENT_TOL:g}) |",
        "|---|---|---:|---:|---:|---|",
    ]
    all_agree = True
    for label, case in payload["cases"].items():
        c = compare_hessian_case(case, design, penalties)
        all_agree &= c.agrees
        layout = (
            f"{case['hess_dim']}x{case['hess_dim']} (Schur over log phi)"
            if case["scale_estimated"]
            else f"{case['hess_dim']}x{case['hess_dim']}"
        )
        scale = "n/a" if c.scale_rel_diff is None else f"{c.scale_rel_diff:.3e}"
        lines.append(
            f"| `{label}` | {layout} | {c.max_scaled_diff:.3e} | {c.max_abs_diff:.3e} "
            f"| {scale} | {c.agrees} |"
        )
    lines += [
        "",
        f"Tolerance {HESSIAN_AGREEMENT_TOL:g} is `gam.control()$newton$conv.tol`, the "
        "resolution at which `mgcv` certifies the point it evaluates its Hessian at "
        "(module docstring of `gam_hessian_conformance`); it was not fitted to these readings. "
        "For quasipoisson `m$sig2` is a Pearson-type reporting estimate, not the REML "
        "profile's `phi_hat`, so the scale is compared for gaussian only.",
        "",
        f"**Overall:** {'every case agrees' if all_agree else 'AT LEAST ONE CASE DISAGREES'}.",
        "",
    ]
    report = "\n".join(lines)
    print(report)
    if args.markdown:
        Path(args.markdown).write_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
