"""Diagnostic (not parity evidence): does `select_lambdas_continuous`'s own
DEFAULT starting point explain the free-`sp` residual on the N=4,
`ti()`-sharing-a-span structure — PLAN slice 5d's cheap first step, extended
with a decisive discriminator found while running it.

WHAT THIS PROBES
----------------
ADR-210 fixed the REML criterion itself (Wood 2011 Appendix B + the
observed-Hessian weight) to float round-trip precision at FIXED sp, both
tiers. Free-sp selection on ADR-208's own N=4 structure still disagreed with
`mgcv` (`max_abs_log10_sp_diff` 0.7560 tier 1 / 1.0996 tier 3) — a residual
slice 5d registered two live hypotheses for: (1) `select_lambdas_continuous`'s
own convergence precision on a weakly-identified `lambda` (the by-term's own
smoothing parameter), or (2) a genuinely multi-modal surface where `mgcv`'s
own Newton-based optimiser reaches a point ours cannot.

THIS SCRIPT DISCRIMINATES THE TWO WITH TWO CHEAP, NO-NEW-MATH CHECKS:

1. **Warm-start test.** Re-run `select_lambdas_continuous` starting AT
   `mgcv`'s own selected `log10(sp)` (read from the R payload — this is why
   the result is DIAGNOSTIC, not INDEPENDENT: the mechanical test in
   `docs/VERIFICATION_STANDARD.md` fails on sight, this function's input
   includes the other side's own selection). If the search stays there (or
   converges to something with an EQUAL OR BETTER score than the blind
   default-start result), `mgcv`'s point is a genuine, REACHABLE optimum of
   OUR OWN criterion — hypothesis (2) (mgcv reaching somewhere ours cannot)
   is refuted, and the gap is squarely hypothesis (1): our own blind start
   just doesn't get there.
2. **BLAS-thread sensitivity.** The blind (default-start) result is compared
   across `OPENBLAS_NUM_THREADS` settings (report only — the caller sets the
   env var; this script does not fork subprocesses). A blind result that
   moves by more than a small fraction of a log10 decade between thread
   counts, on an objective (`penalized_fit_and_score`/`reml_score_general`)
   that is independently verified to agree with `mgcv` to float precision at
   FIXED sp regardless of thread count, localises the sensitivity to the
   SEARCH (the finite-difference-gradient line search on a near-flat
   direction), not the criterion.

Usage:
    Rscript scripts/gam_multiterm_free_sp_probe.R gam_multiterm_free_sp_probe.json
    uv run python scripts/gam_free_sp_warmstart_diagnostic.py gam_multiterm_free_sp_probe.json
"""

import json
import sys

import numpy as np

from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _SEARCH_BOUNDS, _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import select_lambdas_continuous


def main(payload_path: str) -> None:
    with open(payload_path) as fh:
        payload = json.load(fh)

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
    mgcv_log10_sp = np.log10(np.asarray(payload["sp"], dtype=np.float64))

    blind = select_lambdas_continuous(
        y, design["x"], family, blocks, weights=weights, bounds=_SEARCH_BOUNDS
    )
    warm = select_lambdas_continuous(
        y, design["x"], family, blocks, weights=weights, x0=mgcv_log10_sp, bounds=_SEARCH_BOUNDS
    )

    print(f"n={len(y)}  p={design['x'].shape[1]}  blocks={len(blocks)}")
    print(f"mgcv {payload.get('mgcv_version', '?')} / {payload.get('r_version', '?')}")
    print()
    print(
        "DIAGNOSTIC, not parity evidence (docs/VERIFICATION_STANDARD.md): the "
        "warm start below takes mgcv's own selected log10(sp) as an INPUT, so "
        "this can never be part of FREE_SP_MODEL_CLAIM — same status as "
        "scripts/gam_multiterm_sp_delta_probe.R."
    )
    print()
    print(f"mgcv's own log10(sp):        {np.round(mgcv_log10_sp, 6)}")
    print(
        f"blind (default-start) fit:  log10(sp)={np.round(blind.log_lambda, 6)}  "
        f"score={blind.reml_score:.6f}  converged={blind.converged} at_bound={blind.at_bound}"
    )
    print(
        f"warm (start-at-mgcv) fit:   log10(sp)={np.round(warm.log_lambda, 6)}  "
        f"score={warm.reml_score:.6f}  converged={warm.converged} at_bound={warm.at_bound}"
    )
    print()
    score_gap = blind.reml_score - warm.reml_score
    warm_vs_mgcv = float(np.max(np.abs(warm.log_lambda - mgcv_log10_sp)))
    print(f"SCORE GAP (blind - warm):        {score_gap:+.6f}")
    print(f"MAX ABS (warm log10(sp) - mgcv): {warm_vs_mgcv:.6f}")
    print()
    if score_gap > 1e-6 and warm_vs_mgcv < 0.05:
        print(
            "READING: mgcv's own point is a REACHABLE, BETTER-SCORING optimum of "
            "our OWN criterion than the blind default start finds. This is "
            "hypothesis (1) evidence (optimiser convergence on a weakly-identified "
            "lambda), not hypothesis (2) (mgcv reaching somewhere ours cannot)."
        )
    elif warm_vs_mgcv >= 0.05:
        print(
            "READING: even started AT mgcv's own point, our optimiser moves away "
            "from it — mgcv's point is not a local optimum of our own criterion "
            "under this warm start. Re-examine before concluding hypothesis (1)."
        )
    else:
        print(
            "READING: blind and warm starts land at essentially the same score — "
            "the blind start already reaches mgcv's region; the residual is not "
            "explained by this mechanism."
        )


if __name__ == "__main__":
    main(sys.argv[1])
