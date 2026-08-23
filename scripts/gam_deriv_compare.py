"""Compare Wood (2011)'s analytic ``dη/drho`` / ``dw/drho`` against ``mgcv``.

The Python half of ``scripts/gam_deriv_probe.R``; see
``docs/WORK_ORDER_dw_drho_wood2011.md``.

Prints its report to **stdout** as well as writing it, so a tier-3 reading can be
taken from plain job-log text via ``get_job_logs`` rather than from a job-summary
artifact behind a blocked host — the methodology fix ADR-194 adopted and every
later probe in this epic has followed.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from polaris_re.analytics.gam_derivatives_conformance import (
    DERIVATIVE_CLAIM,
    compare_derivative_case,
)
from polaris_re.core.verification import evidence_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", default="gam_deriv_probe.json")
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()

    payload = json.loads(Path(args.probe).read_text())
    design = np.asarray(payload["design"], dtype=np.float64)
    penalties = tuple(np.asarray(b, dtype=np.float64) for b in payload["penalties"])
    base_rho = np.asarray(payload["base_rho"], dtype=np.float64)

    lines = [
        "PLAN — Wood (2011) derivatives: d(eta)/d(rho) and dw/d(rho) vs mgcv",
        "",
        f"mgcv: r_version={payload['r_version']!r} mgcv_version={payload['mgcv_version']!r}",
        f"base rho: {base_rho.tolist()}   h values: {payload['h_values']}",
        "",
        evidence_markdown(DERIVATIVE_CLAIM),
        "",
        "| case | max abs d(eta)/d(rho) diff | max abs dw/d(rho) diff | max abs eta diff (control) "
        "| Richardson ratio (want ~4) | agrees |",
        "|---|---:|---:|---:|---:|---|",
    ]

    any_disagree = False
    for label, case in payload["cases"].items():
        c = compare_derivative_case(case, design, penalties, base_rho, tolerance=args.tolerance)
        if not c.agrees:
            any_disagree = True
        lines.append(
            f"| `{label}` | {c.max_abs_deta_drho_diff:.3e} | {c.max_abs_dw_drho_diff:.3e} "
            f"| {c.max_abs_eta_diff:.3e} | {c.deta_drho_richardson_ratio:.2f} | {c.agrees} |"
        )

    lines += [
        "",
        f"Tolerance {args.tolerance:.1e} on both derivative columns, set by the "
        "REFERENCE side's own finite-difference error rather than chosen to make "
        "this pass (Anchor 8).",
        "",
        "TWO h REGIMES, because one step size cannot show both things:",
        "  * The diff columns are at the SMALLEST h (1e-4), where agreement is "
        "tightest. There the residual is ROUND-OFF limited — differencing two "
        "separately-converged mgcv fits has its own noise floor, and shrinking h "
        "further makes the reference worse, not better (measured: at h=5e-5 the "
        "residual grows, ratio ~0.6).",
        "  * The Richardson column is from the LARGEST pair (1e-2, 5e-3), where "
        "truncation dominates and a central difference's O(h^2) law is observable. "
        "**A ratio of ~4 is what shows the analytic derivative is the h -> 0 limit "
        "of mgcv's own behaviour**, not merely close to it at one arbitrary step. "
        "A ratio near 1 would mean a real disagreement was being masked.",
        "",
        "Reporting only the small h would overstate what the convergence check "
        "proves; reporting only the large h would understate the agreement.",
        "",
        "`max abs eta diff` is a CONTROL, not the finding: it re-confirms the "
        "already-verified fit (ADR-195) at the base rho, so a derivative "
        "disagreement cannot be blamed on the two sides having fitted different "
        "models.",
        "",
        "**What a zero here does NOT establish:** nothing about "
        "`vcov(unconditional=TRUE)`. This slice builds the ingredient ADR-190 named "
        "as missing for the level-4 correction; the assembly of dw/d(rho) into Vc is "
        "Wood, Pya & Saefken (2016)'s contribution and Wood (2011) contains no such "
        "formula. **Level 4 remains open.**",
    ]
    if any_disagree:
        lines.insert(1, "**A case disagreed — see the table. This is a genuine finding.**")

    report = "\n".join(lines) + "\n"
    print(report)
    if args.markdown:
        Path(args.markdown).write_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
