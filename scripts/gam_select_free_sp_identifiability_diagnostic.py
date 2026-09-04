"""Is `SELECT_FREE_SP_MODEL_CLAIM`'s own `1e-2` gate on raw `log10(sp)`
REACHABLE on the `select=TRUE` 7-block structure -- PLAN slice 7c Part 0.

WHY THIS IS NOT A COMPARISON, AND CARRIES NO `VerificationClaim`
----------------------------------------------------------------
Everything this script measures is a property of **our own** REML criterion
(`gam_reml.reml_score_general`, ADR-196/Appendix B) -- its curvature and its
profile in each of the 7 `log10(lambda)` directions. No Polaris quantity is
compared against an `mgcv` quantity anywhere in it, so it is neither a parity
comparison nor a transport/echo harness check: there is no second producer to
name. `mgcv`'s own selection enters ONLY as the POINT at which our criterion
is examined -- an argument, not an operand. Reporting it under either provenance
label would be a category error, so it carries no `VerificationClaim` at all and
the ledger rows use the third category `MEASUREMENT (own criterion)`
(`docs/VERIFICATION_STANDARD.md` §2.1).

The mechanical test for that category: remove the reference entirely -- is there
still a number? Here yes; `mgcv` only chose the coordinates.

WHAT IT ESTABLISHES (ADR-219)
-----------------------------
ADR-218 (slice 7b) closed the free-`sp` search under `select=TRUE` with a
residual: `multistart=True` brought `eta` to `0.0027` and `edf_total` to
`0.11`, but `max_abs_log10_sp_diff` stayed at `1.48` against a `1e-2` gate,
and a warm-start diagnostic showed `mgcv`'s own point scores `0.0141` BETTER
under our own criterion than best-of-9 blind multistart reaches. ADR-218
attributed that to optimiser convergence on a weakly-identified surface and
named a better optimiser as the next hypothesis.

This script asks the question that must come FIRST: is the gate attainable at
all? It runs three checks:

  (1) EIGENSPECTRUM of the REML score's Hessian w.r.t. `rho` at `mgcv`'s own
      point (`gam_uncertainty_conformance.finite_difference_rho_hessian`,
      itself already checked against `mgcv`'s own `outer_hessian`).
  (2) STEP-STABILITY of each diagonal second difference. A real curvature is
      stable as the step shrinks; a value that scales like `1/h^2` is a
      constant absolute noise floor divided by `h^2` -- i.e. the direction is
      FLAT and the number is numerical, not physical. This is the same
      discipline ADR-212 used to find the finite-difference-step defect.
  (3) PROFILE -- move ONE block's `log10(lambda)` away from `mgcv`'s point,
      others held fixed, and read what it costs. This is the check a reader
      can interpret without any reference to Hessians.

WHAT SLICE 7E ADDS (ADR-219 amendment 1 decision 4, PLAN slice 7e)
--------------------------------------------------------------------
Every H-weighted reading below (4) was, until this slice, weighted by the
Hessian evaluated ONLY at `mgcv`'s own point. That is a real gap the DoD
names explicitly: the weighting curvature could differ at OUR OWN converged
point, and assuming it does not is exactly the kind of unmeasured assumption
this epic does not let stand. Section (5) repeats checks (1)-(2) at each
search's OWN converged point and re-reports the H-weighted distance weighted
by THAT Hessian, so the shift is measured, not assumed negligible. Still
`MEASUREMENT (own criterion)` throughout -- `mgcv`'s point enters only as
where the DISPLACEMENT is measured TO, never as an operand.

Usage:
    Rscript scripts/gam_select_multiterm_free_sp_probe.R probe.json
    uv run python scripts/gam_select_free_sp_identifiability_diagnostic.py probe.json
"""

import json
import sys
from collections.abc import Callable
from dataclasses import replace

import numpy as np

from polaris_re.analytics.gam_model import (
    assemble_model_design,
    resolve_family,
)
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.analytics.gam_select_free_sp_conformance import (
    compare_select_free_sp_case,
    fit_select_free_sp_case,
)
from polaris_re.analytics.gam_sp_identifiability import hessian_weighted_distance
from polaris_re.analytics.gam_uncertainty_conformance import finite_difference_rho_hessian
from polaris_re.core.exceptions import PolarisComputationError

_STEP_SCAN = (0.2, 0.1, 0.05, 0.025)
"""Natural-log-rho central-difference steps for check (2). Spans a factor of
8, enough to separate a stable curvature from a `1/h^2` noise signature."""

_PROFILE_DELTAS = (-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0)
"""Per-block `log10(lambda)` excursions for check (3), in decades."""

_BLOCK_LABELS = (
    "s(AttdAge) existing",
    "s(AttdAge) null",
    "s(AttdAge,by=StudyYear_C) existing",
    "s(AttdAge,by=StudyYear_C) null",
    "ti(AttdAge,PolYear) existing 1",
    "ti(AttdAge,PolYear) existing 2",
    "ti(AttdAge,PolYear) null",
)
"""Block order `assemble_model_design` produces under `select=True` (ADR-217:
each smooth's own existing block(s) then its null-space block, concatenated in
formula order). Labels only -- nothing here depends on them."""


def _step_stability(
    score_at: Callable[[np.ndarray], float],
    base: float,
    point: np.ndarray,
    n_blocks: int,
) -> tuple[list[int], list[list[float]]]:
    """Check (2)'s scan, factored out so section (5) can run it at a NEW
    point (a search's own converged selection) without duplicating the loop.
    Returns the flat-block indices and the raw per-block, per-step table
    (for printing) -- the same "1/h^2 growth means noise" discipline as the
    original mgcv-point-only version, applied verbatim at whatever `point`
    is passed."""
    ln10 = float(np.log(10.0))
    flat_blocks: list[int] = []
    rows: list[list[float]] = []
    for j in range(n_blocks):
        row = []
        for h in _STEP_SCAN:
            up, dn = point.copy(), point.copy()
            up[j] += h / ln10
            dn[j] -= h / ln10
            row.append((score_at(up) - 2.0 * base + score_at(dn)) / (h * h))
        coarse, fine = abs(row[0]), abs(row[-1])
        unstable = fine > 4.0 * max(coarse, 1e-12)
        if unstable:
            flat_blocks.append(j)
        rows.append(row)
    return flat_blocks, rows


def _derived_floor(hessian: np.ndarray, flat_blocks: list[int]) -> float:
    """Same derivation as the original script body: the floor is the
    smallest RESOLVED eigenvalue, clipping exactly as many as the
    step-stability scan called flat -- never a chosen constant (Anchor 8)."""
    evals = np.linalg.eigvalsh(hessian)
    sorted_evals = np.sort(evals)
    return float(sorted_evals[len(flat_blocks)]) if flat_blocks else 0.0


def _build(payload: dict) -> tuple:
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
    return design, family, y, data["ExposCnt"]


def main(payload_path: str) -> None:
    with open(payload_path) as fh:
        payload = json.load(fh)

    design, family, y, weights = _build(payload)
    blocks = tuple(design["penalty_blocks"])
    x = design["x"]
    log10_mgcv = np.log10(np.asarray(payload["sp"], dtype=np.float64))
    rho_mgcv = np.log(np.asarray(payload["sp"], dtype=np.float64))

    def score_at(log10_lambda: np.ndarray) -> float:
        return penalized_fit_and_score(
            y, x, family, blocks, np.asarray(log10_lambda, dtype=np.float64), weights=weights
        )[1]

    base = score_at(log10_mgcv)
    print(f"n={len(y)}  p={x.shape[1]}  blocks={len(blocks)}")
    print(f"mgcv {payload.get('mgcv_version', '?')} / {payload.get('r_version', '?')}")
    print(f"REML score at mgcv's own point: {base:.9f}")
    print()
    print("NOT a comparison: every number below is our OWN criterion's geometry.")
    print("mgcv's selection is the POINT of evaluation, never an operand.")
    print()

    print("(1) HESSIAN EIGENSPECTRUM at mgcv's own point (natural-log rho)")
    hessian = finite_difference_rho_hessian(x, y, blocks, family, weights, rho_mgcv)
    evals, evecs = np.linalg.eigh(hessian)
    for i in range(len(evals)):
        load = np.abs(evecs[:, i])
        top = np.argsort(-load)[:2]
        which = ", ".join(f"b{t + 1}({load[t]:.2f})" for t in top)
        print(f"    eig[{i}] = {evals[i]:12.6f}   loads on {which}")
    print()

    print("(2) STEP-STABILITY of each diagonal second difference")
    print("    stable across h -> real curvature;  ~1/h^2 growth -> flat + noise")
    header = "".join(f"{f'h={h}':>13}" for h in _STEP_SCAN)
    print(f"{'block':>6}{header}   verdict")
    flat_blocks, stability_rows = _step_stability(score_at, base, log10_mgcv, len(blocks))
    for j, row in enumerate(stability_rows):
        verdict = "FLAT (noise)" if j in flat_blocks else "identified"
        print(f"{f'b{j + 1}':>6}" + "".join(f"{v:13.6f}" for v in row) + f"   {verdict}")
    print()

    print("(3) PROFILE -- move ONE block from mgcv's point, others fixed (delta score)")
    print("    '.' = penalized IRLS did not converge at that point")
    header = "".join(f"{f'{d:+.1f}':>11}" for d in _PROFILE_DELTAS)
    print(f"{'block':>6}{'log10 sp':>11}{header}   term")
    for j in range(len(blocks)):
        cells = []
        for d in _PROFILE_DELTAS:
            up = log10_mgcv.copy()
            up[j] += d
            try:
                cells.append(f"{score_at(up) - base:+11.6f}")
            except PolarisComputationError:
                # A non-convergent point is a READING (the profile's own edge),
                # not a crash — recorded as '.' rather than suppressed silently.
                cells.append(f"{'.':>11}")
        print(
            f"{f'b{j + 1}':>6}{log10_mgcv[j]:11.4f}"
            + "".join(cells)
            + f"   {_BLOCK_LABELS[j] if j < len(_BLOCK_LABELS) else ''}"
        )
    print()

    print("(4) CANDIDATE ACCEPTANCE METRICS on this same case (PLAN slice 7c Part 2)")
    print("    REPORTED, NEVER GATED as of THIS script -- slice 7e re-gates eta/edf in")
    print("    production (gam_select_free_sp_conformance.py); this diagnostic stays a")
    print("    MEASUREMENT and gates nothing itself.")
    print("    PROVENANCE DIFFERS BY COLUMN:")
    print("      max|dlog10 sp| : INDEPENDENT -- both sides selected their own sp.")
    print("      H-weighted     : MEASUREMENT (own criterion), VERIFICATION_STANDARD.md")
    print("                       Sec 2.1/ADR-219 amendment 1 decision 2 -- a norm on a")
    print("                       displacement, weighted by OUR OWN criterion's curvature.")
    print("                       Corrected here from an earlier 'INDEPENDENT' label this")
    print("                       script printed before that ratification (slice 7e).")
    print("      score gap      : MEASUREMENT (own criterion) -- our criterion evaluated")
    print("                       AT mgcv's supplied point. Never a parity claim.")
    print()
    # Counted from the STEP-STABILITY verdict, not from eigenvalue signs. The
    # sign count is not stable across environments -- on this same fixture it
    # read 5 of 7 at tier 1 and 7 of 7 at tier 3, purely on which side of zero
    # the noise landed (ADR-219 amendment 2). The step scan called b1/b3 FLAT at
    # both tiers, so it is the reading that survived re-measurement.
    resolved = len(blocks) - len(flat_blocks)
    print(f"    resolved directions (by step-stability): {resolved} of {len(blocks)}")
    # The floor is DERIVED, not chosen: the step-stability scan above already
    # determined HOW MANY directions are unresolved, so clip exactly that many
    # smallest eigenvalues. Reporting H at floor=0 alongside it makes the
    # instability visible rather than hidden -- at floor=0 this metric moved 4.7x
    # across four readings on nothing but the SIGN of noise (ADR-219 amendment 4).
    sorted_evals = np.sort(evals)
    noise_floor = float(sorted_evals[len(flat_blocks)]) if flat_blocks else 0.0
    print(f"    derived floor (smallest resolved eigenvalue): {noise_floor:.6f}")
    header = (
        f"{'search':<22}{'max|dlog10 sp|':>16}{'H (floor=0)':>13}"
        f"{'H (floored)':>13}{'score gap':>13}"
    )
    print(f"    {header}")
    ln10 = float(np.log(10.0))
    searches: dict[str, tuple] = {}
    for label, kwargs in (
        ("single-start", {}),
        ("multistart(9)", {"multistart": True, "n_starts": 9}),
    ):
        fit = fit_select_free_sp_case(payload, **kwargs)
        comparison = compare_select_free_sp_case(fit, payload)
        d_rho = (fit.log_lambda - log10_mgcv) * ln10
        searches[label] = (fit, comparison, d_rho)
        print(
            f"    {label:<22}{comparison.max_abs_log10_sp_diff:16.4f}"
            f"{hessian_weighted_distance(d_rho, hessian, floor=0.0):13.6f}"
            f"{hessian_weighted_distance(d_rho, hessian, floor=noise_floor):13.6f}"
            f"{fit.reml_score - base:13.6f}"
        )
    print()

    print("(5) H-WEIGHTED COMPANION RE-EVALUATED AT EACH SEARCH'S OWN POINT (PLAN slice 7e)")
    print("    Section (4) weighted every displacement by the Hessian at MGCV's point only.")
    print("    Repeating (1)-(2) at OUR OWN converged point measures whether that curvature")
    print("    shift is negligible, rather than assuming it (ADR-219 amendment 1's own DoD).")
    print()
    own_header = (
        f"{'search':<22}{'own log10sp base':>18}{'H(mgcv pt)':>13}"
        f"{'H(own pt)':>13}{'own floor':>12}{'own resolved':>14}"
    )
    print(f"    {own_header}")
    for label, (fit, _comparison, d_rho) in searches.items():
        own_point = fit.log_lambda
        own_base = score_at(own_point)
        own_flat, _own_rows = _step_stability(score_at, own_base, own_point, len(blocks))
        own_hessian = finite_difference_rho_hessian(
            x, y, blocks, family, weights, np.log(np.power(10.0, own_point))
        )
        own_floor = _derived_floor(own_hessian, own_flat)
        h_at_mgcv_pt = hessian_weighted_distance(d_rho, hessian, floor=noise_floor)
        h_at_own_pt = hessian_weighted_distance(d_rho, own_hessian, floor=own_floor)
        own_resolved = len(blocks) - len(own_flat)
        print(
            f"    {label:<22}{own_base:18.6f}{h_at_mgcv_pt:13.6f}{h_at_own_pt:13.6f}"
            f"{own_floor:12.6f}{f'{own_resolved} of {len(blocks)}':>14}"
        )
    print()
    print(
        "    READING: if H(own pt) sits close to H(mgcv pt) for a given search, the\n"
        "    curvature used to weight the displacement is not sensitive to WHICH end it is\n"
        "    evaluated at, and either endpoint is an adequate choice. A large shift would\n"
        "    mean the two points sit in geometrically different regions of the criterion's\n"
        "    curvature and the companion metric needs a stated convention for which point's\n"
        "    Hessian it uses -- this is exactly the possibility the DoD required measuring\n"
        "    rather than assuming away."
    )
    print()

    if flat_blocks:
        names = ", ".join(f"b{j + 1}" for j in flat_blocks)
        print(
            f"READING: {names} carry curvature indistinguishable from ZERO at every step\n"
            "tested -- their apparent second difference grows like 1/h^2, the signature of\n"
            "a constant noise floor on a FLAT direction, not of a real (or negative)\n"
            "curvature. A gate demanding agreement to 1e-2 decades on a block whose lambda\n"
            "the criterion cannot distinguish across DECADES is not a hard target, it is an\n"
            "ILL-POSED one: no optimiser, however exact, can pin a parameter the objective\n"
            "does not resolve. The acceptance metric, not the optimiser, is what slice 7b's\n"
            "residual is really about (PLAN slice 7c Part 2, ADR-219)."
        )
    else:
        print(
            "READING: every direction is identified at mgcv's own point -- the 1e-2 gate is\n"
            "reachable in principle, and slice 7b's residual IS an optimiser defect. Build\n"
            "the analytic gradient (PLAN slice 7c Part 1)."
        )


if __name__ == "__main__":
    main(sys.argv[1])
