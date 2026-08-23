"""Level 4: compare eq. (7)'s corrected covariance against ``mgcv``'s ``Vc``.

The Python half of ``scripts/gam_vc_probe.R``; see
``docs/WORK_ORDER_level4_wps2016.md``. Prints to stdout so a tier-3 reading comes
from plain job-log text (the ADR-194 methodology fix).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from polaris_re.analytics.gam_family import (
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_uncertainty_conformance import VC_CLAIM, compare_vc_case
from polaris_re.core.verification import evidence_markdown

_FAMILIES = {
    ("poisson", "log"): poisson_log,
    ("quasipoisson", "log"): quasipoisson_log,
    ("binomial", "logit"): binomial_logit,
    ("binomial", "cloglog"): binomial_cloglog,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", default="gam_vc_probe.json")
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()

    payload = json.loads(Path(args.probe).read_text())
    design = np.asarray(payload["design"], dtype=np.float64)
    penalties = tuple(np.asarray(b, dtype=np.float64) for b in payload["penalties"])

    lines = [
        "LEVEL 4 — Wood, Pya & Saefken (2016) eq. (7) vs mgcv vcov(unconditional=TRUE)",
        "",
        f"mgcv: r_version={payload['r_version']!r} mgcv_version={payload['mgcv_version']!r}",
        "",
        evidence_markdown(VC_CLAIM),
        "",
        "| case | max rel correction diff (element-wise) | ours inflation | mgcv inflation "
        "| rel inflation diff | agrees | rho-Hessian diff (ours vs mgcv, full matrix) "
        "| correction diff with OUR Hessian |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    any_disagree = False
    for label, case in payload["cases"].items():
        family = _FAMILIES[(case["family"], case["link"])]()
        c = compare_vc_case(case, design, penalties, family, tolerance=args.tolerance)
        if not c.agrees:
            any_disagree = True
        lines.append(
            f"| `{label}` | {c.max_rel_correction_diff:.3%} | {c.ours_inflation:.4f}x "
            f"| {c.mgcv_inflation:.4f}x | {c.rel_inflation_diff:.3%} | {c.agrees} "
            f"| {c.max_rel_own_hessian_diff:.3%} "
            f"| {c.max_rel_correction_diff_own_hessian:.3%} |"
        )

    lines += [
        "",
        f"Tolerance {args.tolerance:.1%} on the ELEMENT-WISE relative residual. Eq. (7) "
        "comes from a first-order Taylor expansion whose remainder the paper drops, so "
        "exact agreement is not available in principle; across five held-out cases the "
        "worst residual was 0.730%, and the tolerance leaves under a factor of three "
        "over that observed spread (Anchor 8).",
        "",
        "**The last two columns are REPORTED, never gated** (PR #207 review [P1]). The "
        "rho Hessian is a shared *input* to this comparison, read from mgcv's "
        "`outer.info$hess` so a Hessian disagreement cannot masquerade as a correction "
        "disagreement. Until 2026-08-23 the disclosure rested on an unpinned claim that "
        "our own Hessian reproduced it — supported only by an EIGENVALUE comparison in a "
        "work order, which is weaker than the matrix `V' = J H^-1 J^T` actually depends "
        "on, and miscited to ADR-201, which contains no Hessian comparison at all. Both "
        "halves are now measured: the full-matrix difference, and the entire correction "
        "recomputed with our finite-difference Hessian substituted. Gating on either "
        "would silently promote a shared input into a compared quantity, which is not "
        "what VC_CLAIM declares.",
        "",
        "**Element-wise is the governing column, not the inflation ratio.** The ratio "
        "averages diagonals: during this slice it read 0.39% while the element-wise "
        "residual was 26.7%, hiding a real structural disagreement behind a green "
        "headline.",
        "",
        "**What this closes and what it does not.** It closes the level-4 FORMULA gap "
        "ADR-190 opened: this engine now reproduces mgcv's unconditional covariance, "
        "where the first-order-only correction inflated 1.11-1.21x against mgcv's "
        "1.49-1.87x. The ten-cell conformance suite's level 4 will STILL DISAGREE, "
        "correctly: it exercises experience_gam_penalized.smoothing_uncertainty, the "
        "shipped path, which this does not touch. Re-pointing production needs PLAN "
        "Anchor 7 sign-off and carries its own determinism question (ADR-186).",
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
