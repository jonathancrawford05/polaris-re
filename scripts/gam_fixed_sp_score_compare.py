"""The Polaris side of the fixed-`sp` REML score/deviance comparison — PLAN
slice 5c's own parity measurement, now that `reml_score_general` carries
Appendix B and the observed-Hessian weight (ADR-210).

**INDEPENDENT parity evidence, not a diagnostic** (PR #215 review [P1-1]).
An earlier revision of this script's docstring read "DIAGNOSTIC ONLY, never
committed parity evidence: it reads mgcv's own REML score" — written while
`gam_reml.reml_score_general` was still the SUSPECT, not the verified
criterion, and never corrected once ADR-210 fixed it. That framing was
always mechanically wrong: `gam_reml_optimize.penalized_fit_and_score`
(this script's own producer) takes ``y, x, family, penalty_blocks,
log_lambda, weights`` — no `mgcv`-shaped argument exists for it to read even
by accident — and `mgcv_score`/`mgcv_deviance` enter this script only as
the right-hand side of a comparison, never as an input to the fit or score
computed here. That is the identical mechanical shape
`gam_reml_conformance.score_reml_point`/`REML_SCORE_CLAIM` already carry as
INDEPENDENT — see `gam_reml_optimize_conformance.FIXED_SP_MULTITERM_REML_CLAIM`,
declared for THIS fixture (4 blocks, binomial/cloglog, formula-built) rather
than reusing `REML_SCORE_CLAIM` (2 blocks, binomial/logit, `paraPen`-supplied),
which covers a different producer and a different model.

WHAT IT ANSWERS. ADR-208's amendment established that (pre-fix) `mgcv`'s
criterion and ours ranked `mgcv`'s free-`sp` point and Python's in opposite
order. Evaluating BOTH criteria at the SAME fixed `sp`, at several
well-separated points, discriminates a criterion-formula problem from an
optimiser one and involves no optimiser at all — a spread of `ours - mgcv`
that is ~0 across every point means the two criteria agree up to an additive
constant (same argmin); a spread that varies means they disagree as
functions of `sp`. ADR-210 measured this AFTER both of PLAN slice 5c's
defects were fixed: the spread collapses to float round-trip precision (see
that ADR for the full before/after tables at both tiers).

`deviance` is the companion quantity `REML_SCORE_CLAIM` already carries, for
the identical reason: it rules out the most plausible harness artifact
(`mgcv` rescaling the supplied penalty via `gam.control()$scalePenalty`,
which would make both sides fit at a different effective lambda and turn
the whole comparison into an artifact) independently of whether the score
formula itself is right.

Usage:
    Rscript scripts/gam_fixed_sp_score_probe.R out.json
    uv run python scripts/gam_fixed_sp_score_compare.py out.json
"""

import json
import pathlib
import sys

import numpy as np

from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize_conformance import (
    FIXED_SP_MULTITERM_REML_CLAIM,
    compare_fixed_sp_multiterm_case,
)
from polaris_re.core.verification import evidence_markdown


def main(payload_path: str) -> None:
    payload = json.loads(pathlib.Path(payload_path).read_text())

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

    comparison = compare_fixed_sp_multiterm_case(
        y, design["x"], family, blocks, weights, tuple(payload["points"])
    )

    print(f"n={len(y)}  p={design['x'].shape[1]}  blocks={len(blocks)}")
    print(f"mgcv {payload['mgcv_version']} / {payload['r_version']}")
    print()
    print(evidence_markdown(FIXED_SP_MULTITERM_REML_CLAIM))
    print()
    print(f"{'point':<14}{'spread':>7}{'ours':>13}{'mgcv':>13}{'score diff':>13}{'dev diff':>11}")
    print("-" * 71)
    for point in comparison.points:
        spread = float(point.log10_sp.max() - point.log10_sp.min())
        print(
            f"{point.name:<14}{spread:>7.2f}{point.ours_score:>13.5f}"
            f"{point.mgcv_score:>13.5f}{point.score_diff:>13.5f}"
            f"{point.deviance_diff:>11.3e}"
        )
    print("-" * 71)
    print(f"SPREAD (ours - mgcv, score): {comparison.score_diff_spread:.6f}")
    print(f"MAX ABS DEVIANCE DIFF: {comparison.max_abs_deviance_diff:.6e}")
    print()
    print(
        "A score spread that is NOT ~0 means the criterion itself moves with sp\n"
        "relative to mgcv's; ~0 means the two criteria agree up to an additive\n"
        "constant at every tested point. A large deviance diff would point at a\n"
        "rescaled-penalty harness artifact rather than the criterion itself —\n"
        "see the module docstring."
    )


if __name__ == "__main__":
    main(sys.argv[1])
