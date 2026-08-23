#!/usr/bin/env python3
"""
unconditional_coverage_study.py — the Anchor-7 gate for the penalized MI bands.

Slice 4 of `docs/PLAN_penalized_mi_surface.md`. ADR-187 measured penalized band
coverage **conditional on λ** — λ selected once on a held-out replicate, every
replicate then fit at it — and got 87.1% against a nominal 95% on a truth the basis
represents exactly. That is a statement about the formula.

**This script measures the other one: what a user of the shipped procedure actually
gets.** Select λ on every replicate, fit, form the band, count. PLAN Anchor 7 makes
that the only measurement that licenses the label "95% band", which is why this is a
gate rather than a nice-to-have, and why it reports the conditional and unconditional
intervals side by side from the *same* fits — the two differ only in the covariance,
so pairing them removes replicate noise from the comparison.

Cost is the reason this is a script and not a default test: per-replicate selection is
~166-202 penalized fits, so 200 replicates over two truths is ~80,000 fits, about 4-6
minutes. `tests/test_analytics/test_experience_gam_penalized.py` carries a `@slow`
test at a reduced replicate count that pins the *direction*; the decimals come from
here and are committed to `docs/MEASUREMENT_unconditional_coverage.md`.

**If you reduce --replicates, the report says so.** The plan forbids silently
shrinking the study to make it fit, so the replicate count and the resulting
Monte-Carlo SE are printed in the report body rather than left to the reader.

No wall clock anywhere: seeds are pinned, and two runs over the same arguments
produce byte-identical JSON (ADR-074).

Usage:
    uv run python scripts/unconditional_coverage_study.py \
        -o /tmp/unconditional.json --markdown docs/MEASUREMENT_unconditional_coverage.md

    # a quick shape check
    uv run python scripts/unconditional_coverage_study.py --replicates 10 -o /tmp/q.json

Exit status: 0 on a completed run whatever its verdict, 1 on failure.
"""

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.experience_gam import MISurface  # noqa: E402
from polaris_re.analytics.experience_gam_penalized import (  # noqa: E402
    PenalizedMIFit,
    fit_reml,
    smoothing_uncertainty,
)
from polaris_re.analytics.gam_uncertainty_mi import wps_correction  # noqa: E402

type MIFunction = Callable[[float, int], float]
"""MI as a function of (attained age, calendar year) — the shape every truth here
takes. Named because it is this script's own contract with its fixtures, and an
unannotated one was the review's [P2]."""

AGES = np.arange(25, 96)
YEARS = np.arange(2012, 2020)
K_AGE = 7
K_YEAR = 6
NOMINAL = 0.95

DEFAULT_REPLICATES = 200
"""ADR-187's figure, kept so the two studies are comparable replicate-for-replicate.
Monte-Carlo SE on a single cell at p=0.95 is √(0.95·0.05/200) ≈ 1.5pp."""

FIRST_SEED = 1000
"""Replicate seeds are FIRST_SEED .. FIRST_SEED + replicates - 1, matching ADR-187's
evaluation range. Unlike the conditional study there is no held-out selection seed to
keep clear of: every replicate selects its own λ, which is the entire point."""

DELTA_REFERENCE_AGE_FLAT = 0.9586
"""ADR-187's measured coverage for the **unpenalized** delta-method band on the
age-flat truth, over these same 200 seeds.

Quoted rather than re-measured, and reported rather than left out, because it is the
only figure here for the estimator the penalized one would replace — and because the
unpenalized fit selects no λ, so its conditional and unconditional coverage are the
same number by construction. A study that reported only the penalized rows would let
"85%" read as a property of the problem rather than of this estimator."""


SUPERSEDED_2026_08_09 = {
    "age-flat": (0.8201, 0.8516),
    "age-varying": (0.8200, 0.8581),
}
"""The (conditional, unconditional) figures this report carried from 2026-08-09.

**They no longer reproduce, and the reason is a production change, not a defect
here.** `ce0b9f1` (2026-08-19) added Wood (2011) eq. (4)'s penalized-deviance term to
`experience_gam_penalized.reml_score` — the maintainer-authorized ADR-197 fix, correct
and verified bit-for-bit against `gam_reml.reml_score_general`. A different REML
criterion selects a different λ on every replicate, so coverage moved: measured at
-0.0432 / -0.0410 on the age-flat truth by restoring the pre-fix criterion under
monkeypatch and re-running.

Carried in the report rather than in a changelog because **nothing re-runs this
study** — it is absent from `.github/workflows/` and from the `Makefile`, and the
`@slow` sibling test pins direction rather than decimals. A measurement with no
re-run trigger goes stale silently, and this one did, staying cited as current for
four days in `CONTINUATION_penalized_mi_surface.md`, `RUNBOOK_mgcv_conformance.md`,
`WORK_ORDER_level4_wps2016.md` and ADR-190 decision 4 itself. Printing the
superseded pair beside the current one is what makes the next such drift visible
to a reader instead of only to whoever happens to re-run it."""


def q_base(age: float) -> float:
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def year_quadratic_mi(age: float, year: int) -> float:
    """ADR-187's `_quadratic_mi` — quadratic in year, **flat in age**.

    Outside the second-difference penalty's null space, and exactly representable by
    both bases, so a coverage shortfall here is the band's and not the basis's. Flat
    in age is the property ADR-187 amendment 1 identified as the reason λ_age looked
    unidentifiable on it: the age penalty has nothing to fit.
    """
    return 0.015 + 0.006 * ((year - 2015.5) / 3.5) ** 2


def age_varying_quadratic_mi(age: float, year: int) -> float:
    """The same curve in year, plus a **quadratic** age profile — amendment 1's fixture.

    It exists because ADR-187 amendment 1 showed λ_age's across-replicate spread falls
    sharply once there is age structure to identify it from. A study run only on the
    age-flat truth would measure the estimator in the one regime where its smoothing
    parameters are worst determined.

    **Quadratic in age, not linear, and the distinction is the whole point.** A linear
    age gradient lies *inside* the second-difference penalty's null space along the age
    margin, so λ_age → ∞ costs nothing and the age penalty is exactly as unidentifiable
    as it is on the flat truth. The first version of this fixture was linear and
    measured the same degeneracy under a different name — the identical trap ADR-186
    hit with a truth its basis could not resolve, and ADR-187's coverage design was
    built to avoid. Quadratic is outside the null space and inside both bases, which is
    the pairing the study needs.
    """
    return 0.010 + 0.008 * ((age - 60.0) / 35.0) ** 2 + 0.006 * ((year - 2015.5) / 3.5) ** 2


TRUTHS = {"age-flat": year_quadratic_mi, "age-varying": age_varying_quadratic_mi}


def build_cells(mi_fn: MIFunction, *, seed: int) -> pl.DataFrame:
    """The ILEC-shaped fixture from the diagnostics epic, at a pinned seed."""
    rng = np.random.default_rng(seed)
    rows: list[tuple[int, int, float, float, float]] = []
    for age in AGES:
        q0 = q_base(float(age))
        actual = q0
        for year in YEARS:
            if int(year) > int(YEARS.min()):
                actual *= 1.0 - float(mi_fn(float(age), int(year)))
            rows.append((int(age), int(year), q0, 6.0e4, float(rng.poisson(6.0e4 * actual))))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


def truth_grid(mi_fn: MIFunction) -> np.ndarray:
    """MI on the (age x year-transition) grid the extractor reports."""
    return np.array([[mi_fn(float(a), int(y)) for y in YEARS[1:]] for a in AGES], dtype=np.float64)


@dataclass(frozen=True)
class CoverageRow:
    """One (truth, band) cell of the study."""

    truth: str
    band: str
    overall: float
    young: float
    old: float
    mean_width: float


@dataclass(frozen=True)
class TruthResult:
    truth: str
    replicates: int
    conditional: CoverageRow
    unconditional: CoverageRow
    ks_analytic: CoverageRow
    """Kass-Steffey with ``J`` taken analytically instead of by central differences.

    Present to **separate the two mechanisms** re-pointing production would change at
    once: this row differs from ``unconditional`` only in how ``J`` is obtained, and
    from ``wps2016`` only in the missing ``V''`` term. Without it a coverage movement
    could not be attributed to the formula rather than to the derivative method."""

    wps2016: CoverageRow
    """Wood, Pya and Saefken (2016) eq. (7) in full — the band ADR-202 verified
    against ``mgcv`` and ADR-190 decision 4 predicted would move coverage."""

    mean_inflation_unconditional: float
    mean_inflation_ks_analytic: float
    mean_inflation_wps2016: float
    """Mean coefficient-variance inflation each correction applies, averaged over
    replicates. Reported beside the coverage because ADR-190 measured the *size* of
    the gap (3.2-4.1x on the correction term) and this is the same quantity on the
    production path — a coverage change with no inflation change would mean the two
    studies are not looking at the same object."""

    mean_floored_wps_directions: float
    log10_lambda_age_spread: float
    log10_lambda_year_spread: float
    mean_rejected_points: float
    max_rejected_points: int
    mean_evaluated_points: float
    replicates_with_rejections: int
    mean_floored_directions: float


def _summarise(truth: str, band: str, hits: np.ndarray, widths: list[float], n: int) -> CoverageRow:
    cov = hits / n
    return CoverageRow(
        truth=truth,
        band=band,
        overall=round(float(cov.mean()), 4),
        young=round(float(cov[AGES <= 50].mean()), 4),
        old=round(float(cov[AGES >= 80].mean()), 4),
        mean_width=round(float(np.mean(widths)), 6),
    )


def run_truth(name: str, *, replicates: int, gamma: float = 1.0) -> TruthResult:
    """Select-per-replicate coverage for one truth, both bands, from the same fits."""
    mi_fn = TRUTHS[name]
    truth = truth_grid(mi_fn)

    hits_c = np.zeros_like(truth)
    hits_u = np.zeros_like(truth)
    hits_k = np.zeros_like(truth)
    hits_w = np.zeros_like(truth)
    widths_c: list[float] = []
    widths_u: list[float] = []
    widths_k: list[float] = []
    widths_w: list[float] = []
    inflation_u: list[float] = []
    inflation_k: list[float] = []
    inflation_w: list[float] = []
    log_age: list[float] = []
    log_year: list[float] = []
    rejected: list[int] = []
    evaluated: list[int] = []
    floored: list[int] = []
    floored_wps: list[int] = []

    for r in range(replicates):
        cells = build_cells(mi_fn, seed=FIRST_SEED + r)
        fit = fit_reml(cells, k_age=K_AGE, k_year=K_YEAR, gamma=gamma)
        extra = smoothing_uncertainty(
            cells,
            lambda_age=fit.lambda_age,
            lambda_year=fit.lambda_year,
            gamma=gamma,
            k_age=K_AGE,
            k_year=K_YEAR,
        )
        wps = wps_correction(cells, fit, extra, k_age=K_AGE, k_year=K_YEAR)

        # The same fit, four times — only the covariance differs, so the pairing
        # removes replicate noise from every comparison below.
        surface_c = fit.improvement_surface(ages=AGES, years=YEARS)
        surface_u = _surface_with(fit, fit.cov + extra.correction)
        surface_k = _surface_with(fit, fit.cov + wps.first_order)
        surface_w = _surface_with(fit, fit.cov + wps.correction)

        hits_c += ((surface_c.mi_lower <= truth) & (truth <= surface_c.mi_upper)).astype(float)
        hits_u += ((surface_u.mi_lower <= truth) & (truth <= surface_u.mi_upper)).astype(float)
        hits_k += ((surface_k.mi_lower <= truth) & (truth <= surface_k.mi_upper)).astype(float)
        hits_w += ((surface_w.mi_lower <= truth) & (truth <= surface_w.mi_upper)).astype(float)
        widths_c.append(float(np.mean(surface_c.mi_upper - surface_c.mi_lower)))
        widths_u.append(float(np.mean(surface_u.mi_upper - surface_u.mi_lower)))
        widths_k.append(float(np.mean(surface_k.mi_upper - surface_k.mi_lower)))
        widths_w.append(float(np.mean(surface_w.mi_upper - surface_w.mi_lower)))
        base_variance = float(np.mean(np.diag(fit.cov)))
        inflation_u.append(float(np.mean(np.diag(fit.cov + extra.correction))) / base_variance)
        inflation_k.append(float(np.mean(np.diag(fit.cov + wps.first_order))) / base_variance)
        inflation_w.append(float(np.mean(np.diag(fit.cov + wps.correction))) / base_variance)
        log_age.append(float(np.log10(fit.lambda_age)))
        log_year.append(float(np.log10(fit.lambda_year)))
        rejected.append(int(fit.n_rejected_points or 0))
        evaluated.append(int(fit.n_evaluated_points or 0))
        floored.append(extra.n_floored)
        floored_wps.append(wps.n_floored)

    return TruthResult(
        truth=name,
        replicates=replicates,
        conditional=_summarise(name, "conditional", hits_c, widths_c, replicates),
        unconditional=_summarise(name, "unconditional", hits_u, widths_u, replicates),
        ks_analytic=_summarise(name, "ks-analytic", hits_k, widths_k, replicates),
        wps2016=_summarise(name, "wps2016", hits_w, widths_w, replicates),
        mean_inflation_unconditional=round(float(np.mean(inflation_u)), 4),
        mean_inflation_ks_analytic=round(float(np.mean(inflation_k)), 4),
        mean_inflation_wps2016=round(float(np.mean(inflation_w)), 4),
        mean_floored_wps_directions=round(float(np.mean(floored_wps)), 3),
        log10_lambda_age_spread=round(max(log_age) - min(log_age), 3),
        log10_lambda_year_spread=round(max(log_year) - min(log_year), 3),
        mean_rejected_points=round(float(np.mean(rejected)), 3),
        max_rejected_points=int(max(rejected)),
        mean_evaluated_points=round(float(np.mean(evaluated)), 1),
        replicates_with_rejections=int(sum(1 for x in rejected if x > 0)),
        mean_floored_directions=round(float(np.mean(floored)), 3),
    )


def _surface_with(fit: PenalizedMIFit, cov: np.ndarray) -> MISurface:
    """The fit's surface under a substituted covariance, through the shared band layer.

    Rebuilding the design here rather than re-fitting is what makes the two bands a
    *paired* comparison. It goes through `mi_surface_from_design`, the same function
    `improvement_surface` calls (ADR-187 decision 2), so the arithmetic is not a
    fourth copy of the band formula living in a script.
    """
    from polaris_re.analytics.experience_gam import mi_surface_from_design

    tensor = np.asarray(fit._grid_design(AGES, YEARS), dtype=np.float64)
    pad = fit.n_coef - fit.n_tensor
    design = (
        np.hstack([tensor, np.zeros((tensor.shape[0], pad), dtype=np.float64)]) if pad else tensor
    )
    return mi_surface_from_design(design, fit.coef, cov, AGES, YEARS, NOMINAL)


def monte_carlo_se(replicates: int) -> float:
    return float(np.sqrt(NOMINAL * (1.0 - NOMINAL) / replicates))


def verdict(results: list[TruthResult]) -> str:
    """Does the **WPS-2016** band clear Anchor 7's gate?

    Deliberately narrow: the gate is about whether an interval may be *labelled* 95%,
    so the test is whether coverage reaches nominal minus two Monte-Carlo SEs on
    **every** truth measured. A band that clears on one truth and not the other has
    not cleared.

    The band under test is now ``wps2016`` rather than ``unconditional``. ADR-188 ran
    this gate against the shipped Kass-Steffey band and it failed; ADR-190 decision 4
    registered, in advance, that eq. (7)'s larger correction should move coverage
    toward or past the floor. The shipped band's own verdict is still printed beside
    it, because "the new one passes" and "the old one failed" are the two halves of
    that prediction and reporting only the first would hide the comparison.
    """
    lines = []
    passed = True
    for res in results:
        floor = NOMINAL - 2.0 * monte_carlo_se(res.replicates)
        ok = res.wps2016.overall >= floor
        passed = passed and ok
        lines.append(
            f"- **{res.truth}**: wps2016 {res.wps2016.overall:.4f} vs floor "
            f"{floor:.4f} — {'PASS' if ok else 'FAIL'} "
            f"(shipped Kass-Steffey {res.unconditional.overall:.4f}, "
            f"conditional {res.conditional.overall:.4f})"
        )
    head = (
        "**GATE PASSED** — the eq. (7) band reaches nominal coverage on every truth "
        "measured. Labelling it a 95% interval remains a maintainer decision "
        "(PLAN Anchor 7 of `PLAN_penalized_mi_surface.md` closes on a *measurement*, "
        "and this is it; the label itself is reserved)."
        if passed
        else "**GATE NOT PASSED** — no interval here may be labelled a 95% band "
        "(PLAN Anchor 7). Report the direction and the measured rate instead."
    )
    return head + "\n\n" + "\n".join(lines)


def prediction_verdict(results: list[TruthResult]) -> str:
    """ADR-190 decision 4's registered prediction, resolved.

    The prediction was directional and written before the answer was available:
    a larger correction should move coverage **toward or past** the 0.9192 floor. It
    is resolved here rather than in prose so that the falsifying case — coverage that
    does not move — produces the words "REFUTED" from the same code path that would
    produce "CONFIRMED", instead of being described away.

    **Three outcomes, not two.** "Moved toward the floor" and "reached the floor" are
    different results and collapsing them would be this report's own version of the
    error the epic keeps finding in itself: an early draft of this function printed
    "the formula was the gap stands" whenever coverage rose by any amount, which
    would have described a 3-point move onto a 10-point shortfall as a diagnosis
    confirmed. A movement that leaves the gate failing confirms the *direction* and
    refutes the *sufficiency*, and the report has to say both.
    """
    lines = []
    all_moved = True
    all_cleared = True
    worst_shortfall = 0.0
    for res in results:
        delta = res.wps2016.overall - res.unconditional.overall
        floor = NOMINAL - 2.0 * monte_carlo_se(res.replicates)
        all_moved = all_moved and delta > 0.0
        all_cleared = all_cleared and res.wps2016.overall >= floor
        worst_shortfall = max(worst_shortfall, floor - res.wps2016.overall)
        lines.append(
            f"- **{res.truth}**: {res.unconditional.overall:.4f} -> "
            f"{res.wps2016.overall:.4f} ({delta:+.4f}), floor {floor:.4f}; "
            f"correction inflation {res.mean_inflation_unconditional:.4f}x -> "
            f"{res.mean_inflation_wps2016:.4f}x"
        )
    if not all_moved:
        head = (
            "**REFUTED** — coverage did not move upward on every truth. Per ADR-190 "
            "decision 4's own terms the coverage gap has a second cause and decision 1 "
            "needs re-examining. Do not re-point production on this evidence."
        )
    elif all_cleared:
        head = (
            "**CONFIRMED IN FULL** — eq. (7) moves coverage upward on every truth and "
            "past the floor. ADR-190 decision 1's diagnosis accounts for the gate "
            "failure."
        )
    else:
        head = (
            "**CONFIRMED IN DIRECTION, REFUTED IN SUFFICIENCY** — eq. (7) moves "
            "coverage upward on every truth, which is what ADR-190 decision 4 "
            "registered, so decision 1's diagnosis was pointing at something real. "
            "But the gate still fails by up to "
            f"{worst_shortfall:.4f}, so the formula was **a** gap and not **the** gap. "
            "ADR-190 decision 4's contingency therefore applies in substance even "
            "though its literal trigger did not fire: a second cause remains, and "
            "closing it is not a covariance problem eq. (7) can reach. **Coverage is "
            "not a reason to re-point production** — mgcv parity (ADR-202) is the "
            "case for that, and it is a different case."
        )
    return head + "\n\n" + "\n".join(lines)


def to_markdown(results: list[TruthResult], *, gamma: float) -> str:
    replicates = results[0].replicates
    se = monte_carlo_se(replicates)
    reduced = replicates != DEFAULT_REPLICATES
    out = [
        "# Measurement — unconditional coverage of the penalized MI band",
        "",
        "**Produced by:** `scripts/unconditional_coverage_study.py` "
        "(slice 4, `docs/PLAN_penalized_mi_surface.md`).",
        "**Companion to:** ADR-187's conditional study, and the gate PLAN Anchor 7 sets.",
        "",
        "## What this measures, and how it differs from ADR-187",
        "",
        "ADR-187 selected λ **once** on a held-out replicate and fit every replicate at "
        "it, which is what `Vb` claims — a coverage rate *given* the smoothing "
        "parameters. This study selects λ on **every replicate**, because that is the "
        "procedure a user runs. All four bands below come from the same fits and "
        "differ only in the covariance:",
        "",
        "| band | covariance | `J` from |",
        "|---|---|---|",
        "| conditional | `Vb = (XᵀWX + S)⁻¹φ` | — |",
        "| unconditional | `Vb + J V_rho J\u1d40` (Kass-Steffey) — **the shipped band** "
        "| central differences |",
        "| ks-analytic | `Vb + J V_rho J\u1d40`, same formula | Wood (2011) 3.4, analytic |",
        "| wps2016 | `Vb + V' + V''` — Wood, Pya & Saefken (2016) eq. (7) "
        "| Wood (2011) 3.4, analytic |",
        "",
        "**The last two rows separate the two mechanisms** that re-pointing "
        "production would change at once. `ks-analytic` differs from "
        "`unconditional` only in how `J` is obtained, and from `wps2016` only in "
        "the missing `V''`. Without it a coverage movement could not be "
        "attributed to the formula rather than to the derivative method — and "
        "only the formula is what ADR-202 verified against `mgcv`.",
        "",
        "**No production path changed to produce this** (PLAN Anchor 7). "
        "`experience_gam_penalized` is untouched; the two new bands come from "
        "`polaris_re.analytics.gam_uncertainty_mi.wps_correction`, which reads a "
        "fit that module produced and returns a covariance beside it.",
        "",
        f"**Replicates:** {replicates}"
        + (
            f" — **reduced from the planned {DEFAULT_REPLICATES}**, stated here because "
            "the plan forbids shrinking the study silently."
            if reduced
            else f" (the planned figure). Monte-Carlo SE on a single cell ≈ {se * 100:.2f}pp."
        ),
        f"**Nominal level:** {NOMINAL}.  **gamma:** {gamma}.  "
        f"**Basis:** `k_age={K_AGE}`, `k_year={K_YEAR}`.",
        "",
        "## Results",
        "",
        "| truth | band | overall | young ≤50 | old ≥80 | mean width |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for res in results:
        for row in (res.conditional, res.unconditional, res.ks_analytic, res.wps2016):
            out.append(
                f"| {row.truth} | {row.band} | {row.overall:.4f} | {row.young:.4f} | "
                f"{row.old:.4f} | {row.mean_width:.5f} |"
            )
    if any(r.truth == "age-flat" for r in results):
        out += [
            f"| age-flat | *unpenalized delta-method (ADR-187)* | *{DELTA_REFERENCE_AGE_FLAT:.4f}* "
            "| *0.9574* | *0.9533* | *0.03044* |",
            "",
            "The last row is **not** re-measured here — it is quoted from ADR-187, which "
            "ran the unpenalized `TensorMIModel(age_df=6, year_df=3)` over the identical "
            f"truth and the identical replicate seeds ({FIRST_SEED}..{FIRST_SEED + 199}). "
            "It belongs beside these numbers because it is the estimator the penalized "
            "one is proposed to replace, and because it needs no unconditional variant: "
            "having no λ, it has no smoothing-parameter uncertainty to leave out.",
        ]
    out += [
        "",
        "## This supersedes the 2026-08-09 edition, and not because the study changed",
        "",
        "| truth | conditional, then -> now | unconditional, then -> now |",
        "|---|---|---|",
    ]
    for res in results:
        was = SUPERSEDED_2026_08_09.get(res.truth)
        if was is not None:
            out.append(
                f"| {res.truth} | {was[0]:.4f} -> {res.conditional.overall:.4f} "
                f"| {was[1]:.4f} -> {res.unconditional.overall:.4f} |"
            )
    out += [
        "",
        "`ce0b9f1` (2026-08-19) added Wood (2011) eq. (4)'s penalized-deviance term to "
        "`experience_gam_penalized.reml_score` — the maintainer-authorized ADR-197 fix. "
        "It is **correct**: ADR-197's resolution verified the criterion bit-for-bit "
        "against `gam_reml.reml_score_general` and moved conformance level 5 from "
        "DISAGREES to AGREES. But a different REML criterion selects a different λ on "
        "every replicate, so coverage moved with it — measured at -0.0432 / -0.0410 on "
        "the age-flat truth by restoring the pre-fix criterion under monkeypatch and "
        "re-running the identical seeds.",
        "",
        "**The shipped band's real baseline was therefore ~0.78, not ~0.85, for four "
        "days before this run.** Every document that cited 0.8516 / 0.8581 as the "
        "current state of the gate — including ADR-190 decision 4, whose registered "
        "prediction is resolved below — was quoting a superseded number. Nothing "
        "re-runs this study in CI or the `Makefile`, which is why the drift was "
        "silent and why this section now ships with the report.",
        "",
        "## How much each correction inflates the variance",
        "",
        "Mean coefficient-variance inflation over replicates, `mean(diag(Vb + C)) / "
        "mean(diag(Vb))`. ADR-190 measured the *size* of the gap against `mgcv` "
        "(3.2-4.1x on the correction term) on the conformance fixtures; this is the "
        "same quantity on the production path, so a coverage change with no inflation "
        "change would mean the two studies are not looking at the same object.",
        "",
        "| truth | unconditional | ks-analytic | wps2016 | eq. (7) correction vs "
        "Kass-Steffey | floored Hessian directions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for res in results:
        ratio = (res.mean_inflation_wps2016 - 1.0) / max(
            res.mean_inflation_ks_analytic - 1.0, 1e-12
        )
        out.append(
            f"| {res.truth} | {res.mean_inflation_unconditional:.4f}x | "
            f"{res.mean_inflation_ks_analytic:.4f}x | {res.mean_inflation_wps2016:.4f}x | "
            f"{ratio:.2f}x | {res.mean_floored_wps_directions:.3f} |"
        )
    out += [
        "",
        "The `unconditional` and `ks-analytic` columns are the **same formula** taken "
        "two different ways, so the gap between them is the entire cost of the "
        "derivative-method change — mechanism 2. The gap between `ks-analytic` and "
        "`wps2016` is mechanism 1, the `V''` term.",
        "",
        "## ADR-190 decision 4's registered prediction",
        "",
        prediction_verdict(results),
        "",
        "## Selection behaviour across replicates",
        "",
        "| truth | log10 λ_age spread | log10 λ_year spread | replicates with a rejected "
        "grid point | mean rejected | max rejected | mean grid points scored | mean floored "
        "Hessian directions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for res in results:
        out.append(
            f"| {res.truth} | {res.log10_lambda_age_spread:.2f} | "
            f"{res.log10_lambda_year_spread:.2f} | "
            f"{res.replicates_with_rejections}/{res.replicates} | "
            f"{res.mean_rejected_points:.3f} | {res.max_rejected_points} | "
            f"{res.mean_evaluated_points:.1f} | {res.mean_floored_directions:.3f} |"
        )
    out += [
        "",
        "The rejected-grid-point columns are the direct evidence for slice 4's first "
        "piece: before the fix, **any** replicate in that column would have aborted the "
        "whole study (ADR-187 finding 5).",
        "",
        "## Anchor 7 verdict",
        "",
        verdict(results),
        "",
        "## Reading this honestly",
        "",
        "- A band that reaches nominal by being **very wide** has not become a good "
        "band. Read the width column beside the coverage column; the penalized band's "
        "claim was always precision, and paying all of it back for calibration is a "
        "result, not a success.",
        "- The λ spreads here are measured under **selection per replicate**, so they "
        "are the honest version of ADR-187 finding 2 rather than the conditional "
        "study's single draw.",
        "- **The shipped `unconditional` band was REFUTED against `mgcv`, and still "
        "is.** Level 4 measured it inflating the mean variance 1.11-1.21x where "
        "`mgcv` inflates 1.49-1.87x, in the same direction on every cell (ADR-189 "
        "amendment 1, ADR-190). It is tabulated above because it is what production "
        "ships, not because it is verified — and the ten-cell suite still reads "
        "`level 4: DISAGREES` on it, correctly. This sentence was missing between "
        "2026-08-23's first and second editions of this report, which left the "
        "document's only verification status attached to a band production does not "
        "use (PR #207 review [P1]).",
        "- The `wps2016` covariance is **verified against `mgcv`**, not adopted from "
        "it: ADR-202 measured `unconditional_covariance` against "
        "`vcov(m, unconditional = TRUE)` on the tier-3 pinned oracle at 0.023-0.904% "
        "element-wise. That is what PLAN Anchor 8 asked for, and it is why the "
        "adopted-and-unverified caveat that stood here until 2026-08-23 is gone.",
        "- **`mgcv` parity and coverage are different claims.** The row above says "
        "this band is the same object `mgcv` computes. It does not say that object "
        "is well-calibrated — that is what the coverage column measures, and the two "
        "could in principle disagree. Read them as two facts, not one.",
    ]
    return "\n".join(out) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unconditional_coverage_study.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="JSON results path")
    parser.add_argument("--markdown", type=Path, default=None, help="Markdown report path")
    parser.add_argument(
        "--replicates",
        type=int,
        default=DEFAULT_REPLICATES,
        help=f"replicates per truth (default {DEFAULT_REPLICATES}); a reduction is "
        "recorded in the report",
    )
    parser.add_argument(
        "--truth",
        action="append",
        choices=sorted(TRUTHS),
        default=None,
        help="restrict to one truth (repeatable); default is all",
    )
    parser.add_argument("--gamma", type=float, default=1.0, help="Wood's EDF-cost multiplier")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.replicates < 1:
        print("--replicates must be >= 1", file=sys.stderr)
        return 1
    names = args.truth or sorted(TRUTHS)

    results = []
    for name in names:
        print(f"[{name}] {args.replicates} replicates, selecting lambda on each...", flush=True)
        results.append(run_truth(name, replicates=args.replicates, gamma=args.gamma))
        latest = results[-1]
        print(
            f"[{name}] conditional {latest.conditional.overall:.4f} "
            f"unconditional {latest.unconditional.overall:.4f}",
            flush=True,
        )

    payload = {
        "nominal": NOMINAL,
        "replicates": args.replicates,
        "planned_replicates": DEFAULT_REPLICATES,
        "gamma": args.gamma,
        "k_age": K_AGE,
        "k_year": K_YEAR,
        "first_seed": FIRST_SEED,
        "monte_carlo_se": round(monte_carlo_se(args.replicates), 5),
        "truths": [asdict(r) for r in results],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")
    if args.markdown:
        args.markdown.write_text(to_markdown(results, gamma=args.gamma))
        print(f"wrote {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
