"""Diagnostic (not parity evidence): does `select_lambdas_continuous`'s own
DEFAULT starting point explain the free-sp residual on the 7-block
select=TRUE structure -- PLAN slice 7b's own registered prediction, checked
with the same discriminator ADR-211/ADR-212 used at N=4 (slice 5d).

WHAT THIS PROBES
----------------
`gam_select_free_sp_conformance`'s own measurement (ADR-218) found:
single-start `fit_polaris_gam` disagrees with `mgcv`'s own free-sp
`select=TRUE` selection by up to 5.1 decades of `log10(sp)`;
`multistart=True` (9 starts) brings that to ~1.5 decades while closing `eta`
agreement from ~0.45 to ~0.003 and `edf_total` agreement from ~2.4 to ~0.1.
This script discriminates WHY the raw `log10(sp)` residual survives
multistart, with the SAME two cheap, no-new-math checks ADR-211/212 used at
N=4:

1. **Warm-start test.** Re-run `select_lambdas_continuous` starting AT
   `mgcv`'s own selected `log10(sp)` (read from the R payload -- this is why
   the result is DIAGNOSTIC, not INDEPENDENT: the mechanical test in
   `docs/VERIFICATION_STANDARD.md` fails on sight, the input includes the
   other side's own selection). If the search stays there (or converges to
   something with an EQUAL OR BETTER score than the best multistart result),
   `mgcv`'s point is a genuine, REACHABLE optimum of OUR OWN criterion --
   this is hypothesis (1) evidence (optimiser convergence on a
   weakly-identified surface), not hypothesis (2) (mgcv reaching somewhere
   ours structurally cannot).
2. **Score comparison.** The warm-started score against best-of-9
   multistart's own score, under the SAME (already fixed-sp-verified,
   ADR-217) criterion.

Usage:
    Rscript scripts/gam_select_multiterm_free_sp_probe.R \\
        gam_select_multiterm_free_sp_probe.json
    uv run python scripts/gam_select_free_sp_warmstart_diagnostic.py \\
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
from polaris_re.analytics.gam_reml_optimize import (
    select_lambdas_continuous,
    select_lambdas_continuous_multistart,
)
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
    evidence_markdown,
)

WARM_START_CLAIM = VerificationClaim(
    claim=(
        "gam_reml_optimize.select_lambdas_continuous computes a converged "
        "log10(lambda) and REML score from a supplied starting point x0; the "
        "warm-start reading below supplies mgcv's own free-sp select=TRUE "
        "selection (scripts/gam_select_multiterm_free_sp_probe.R's payload) "
        "as that x0 -- so the mechanical test (docs/VERIFICATION_STANDARD.md) "
        "fails on sight, the same reasoning "
        "scripts/gam_free_sp_warmstart_diagnostic.py's own docstring gives; "
        "compared on log10(sp) and the REML score against mgcv's own "
        "selection and against our own best-of-9 multistart result."
    ),
    quantities=(
        ComparedQuantity(
            quantity="warm_log10_sp",
            left_producer="select_lambdas_continuous(x0=mgcv's own log10(sp))",
            right_producer=(
                "mgcv's own free-sp select=TRUE selection (the SAME values supplied as x0)"
            ),
            provenance=ComparisonProvenance.TRANSPORT,
        ),
        ComparedQuantity(
            quantity="warm_reml_score",
            left_producer="select_lambdas_continuous(x0=mgcv's own log10(sp))'s own score",
            right_producer="gam_reml.reml_score_general at mgcv's own selection (same x0)",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
    ),
)
"""Same status as `scripts/gam_free_sp_warmstart_diagnostic.py`'s own
WARM_START_CLAIM (ADR-193/`docs/VERIFICATION_STANDARD.md`): TRANSPORT, not
INDEPENDENT -- the warm start's own `x0` IS `mgcv`'s output. Never gates a
parity claim and never folds into `SELECT_FREE_SP_MODEL_CLAIM`."""


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
    mgcv_log10_sp = np.log10(np.asarray(payload["sp"], dtype=np.float64))

    blind = select_lambdas_continuous(
        y, design["x"], family, blocks, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS
    )
    multi = select_lambdas_continuous_multistart(
        y, design["x"], family, blocks, weights=weights, bounds=PRODUCTION_LOG10_BOUNDS, n_starts=9
    )
    warm = select_lambdas_continuous(
        y,
        design["x"],
        family,
        blocks,
        weights=weights,
        x0=mgcv_log10_sp,
        bounds=PRODUCTION_LOG10_BOUNDS,
    )

    print(f"n={len(y)}  p={design['x'].shape[1]}  blocks={len(blocks)}")
    print(f"mgcv {payload.get('mgcv_version', '?')} / {payload.get('r_version', '?')}")
    print()
    print(evidence_markdown(WARM_START_CLAIM))
    print()
    print(
        "Never part of SELECT_FREE_SP_MODEL_CLAIM (that comparison's own quantities "
        "are unchanged, still INDEPENDENT) — what this establishes is a "
        "REACHABILITY fact about our own criterion, not a second parity comparison."
    )
    print()
    print(f"mgcv's own log10(sp):        {np.round(mgcv_log10_sp, 6)}")
    print(
        f"blind (single-start) fit:   log10(sp)={np.round(blind.log_lambda, 6)}  "
        f"score={blind.reml_score:.6f}  converged={blind.converged} at_bound={blind.at_bound}"
    )
    print(
        f"multistart(9) fit:          log10(sp)={np.round(multi.best.log_lambda, 6)}  "
        f"score={multi.best.reml_score:.6f}  converged={multi.best.converged} "
        f"at_bound={multi.best.at_bound}"
    )
    print(
        f"warm (start-at-mgcv) fit:   log10(sp)={np.round(warm.log_lambda, 6)}  "
        f"score={warm.reml_score:.6f}  converged={warm.converged} at_bound={warm.at_bound}"
    )
    print()
    score_gap_blind = blind.reml_score - warm.reml_score
    score_gap_multi = multi.best.reml_score - warm.reml_score
    warm_vs_mgcv = float(np.max(np.abs(warm.log_lambda - mgcv_log10_sp)))
    print(f"SCORE GAP (blind - warm):        {score_gap_blind:+.6f}")
    print(f"SCORE GAP (multistart - warm):   {score_gap_multi:+.6f}")
    print(f"MAX ABS (warm log10(sp) - mgcv): {warm_vs_mgcv:.6f}")
    print()
    if score_gap_multi > 1e-6 and warm_vs_mgcv < 0.05:
        print(
            "READING: mgcv's own point is a REACHABLE, BETTER-SCORING optimum of "
            "our OWN criterion than even best-of-9 multistart finds. This is "
            "hypothesis (1) evidence (optimiser convergence on a weakly-identified "
            "surface, the same mechanism ADR-212 found at N=4), not hypothesis (2) "
            "(mgcv reaching somewhere ours cannot)."
        )
    elif warm_vs_mgcv >= 0.05:
        print(
            "READING: even started AT mgcv's own point, our optimiser moves away "
            "from it — mgcv's point is not a local optimum of our own criterion "
            "under this warm start. Re-examine before concluding hypothesis (1)."
        )
    else:
        print(
            "READING: multistart and warm starts land at essentially the same "
            "score — multistart already reaches mgcv's region; the residual is "
            "not explained by this mechanism."
        )


if __name__ == "__main__":
    main(sys.argv[1])
