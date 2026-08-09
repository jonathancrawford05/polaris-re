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
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.experience_gam_penalized import (  # noqa: E402
    fit_reml,
    smoothing_uncertainty,
)

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


def build_cells(mi_fn, *, seed: int) -> pl.DataFrame:
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


def truth_grid(mi_fn) -> np.ndarray:
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
    widths_c: list[float] = []
    widths_u: list[float] = []
    log_age: list[float] = []
    log_year: list[float] = []
    rejected: list[int] = []
    evaluated: list[int] = []
    floored: list[int] = []

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
        # The same fit, twice — only the covariance differs, so the pairing removes
        # replicate noise from the conditional-vs-unconditional comparison.
        surface_c = fit.improvement_surface(ages=AGES, years=YEARS)
        surface_u = _surface_with(fit, fit.cov + extra.correction)

        hits_c += ((surface_c.mi_lower <= truth) & (truth <= surface_c.mi_upper)).astype(float)
        hits_u += ((surface_u.mi_lower <= truth) & (truth <= surface_u.mi_upper)).astype(float)
        widths_c.append(float(np.mean(surface_c.mi_upper - surface_c.mi_lower)))
        widths_u.append(float(np.mean(surface_u.mi_upper - surface_u.mi_lower)))
        log_age.append(float(np.log10(fit.lambda_age)))
        log_year.append(float(np.log10(fit.lambda_year)))
        rejected.append(int(fit.n_rejected_points or 0))
        evaluated.append(int(fit.n_evaluated_points or 0))
        floored.append(extra.n_floored)

    return TruthResult(
        truth=name,
        replicates=replicates,
        conditional=_summarise(name, "conditional", hits_c, widths_c, replicates),
        unconditional=_summarise(name, "unconditional", hits_u, widths_u, replicates),
        log10_lambda_age_spread=round(max(log_age) - min(log_age), 3),
        log10_lambda_year_spread=round(max(log_year) - min(log_year), 3),
        mean_rejected_points=round(float(np.mean(rejected)), 3),
        max_rejected_points=int(max(rejected)),
        mean_evaluated_points=round(float(np.mean(evaluated)), 1),
        replicates_with_rejections=int(sum(1 for x in rejected if x > 0)),
        mean_floored_directions=round(float(np.mean(floored)), 3),
    )


def _surface_with(fit, cov: np.ndarray):
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
    """Does the unconditional band clear Anchor 7's gate?

    Deliberately narrow: the gate is about whether an interval may be *labelled* 95%,
    so the test is whether unconditional coverage reaches nominal minus two
    Monte-Carlo SEs on **every** truth measured. A band that clears on one truth and
    not the other has not cleared.
    """
    lines = []
    passed = True
    for res in results:
        floor = NOMINAL - 2.0 * monte_carlo_se(res.replicates)
        ok = res.unconditional.overall >= floor
        passed = passed and ok
        lines.append(
            f"- **{res.truth}**: unconditional {res.unconditional.overall:.4f} vs floor "
            f"{floor:.4f} — {'PASS' if ok else 'FAIL'} "
            f"(conditional {res.conditional.overall:.4f})"
        )
    head = (
        "**GATE PASSED** — the unconditional band may be labelled a 95% interval."
        if passed
        else "**GATE NOT PASSED** — no interval here may be labelled a 95% band "
        "(PLAN Anchor 7). Report the direction and the measured rate instead."
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
        "procedure a user runs. Both bands below come from the same fits and differ "
        "only in the covariance:",
        "",
        "| band | covariance |",
        "|---|---|",
        "| conditional | `Vb = (XᵀWX + S)⁻¹φ` |",
        "| unconditional | `Vb + J V_rho Jᵀ` (Kass–Steffey) |",
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
        for row in (res.conditional, res.unconditional):
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
        "- Everything about `J V_rho Jᵀ` is **adopted from `mgcv` and unverified** "
        "(PLAN Anchor 8). Slice 5's conformance run against "
        "`vcov(m, unconditional = TRUE)` is what converts it.",
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
