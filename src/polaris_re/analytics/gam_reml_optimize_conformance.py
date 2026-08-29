"""Slice 4 part B's parity claim — does the continuous search land closer to
``mgcv`` than the production grid does (ADR-198's registered prediction)?

``gam_reml_optimize.select_lambdas_continuous`` never reads ``mgcv``'s own
selection, score or coefficients — it minimizes
``gam_reml.reml_score_general`` over the shared ``(X, S_age, S_year)`` design
alone (the mechanical test, ADR-193). ``mgcv`` selects its own
``(lambda_age, lambda_year)`` independently, via its own continuous REML
optimiser (``gam(..., method="REML")`` with free ``sp``,
``scripts/mgcv_conformance.R``). Comparing the two selections is therefore
the same class of INDEPENDENT comparison the ten-cell suite's own level-2
metric already is (``docs/VERIFICATION_STANDARD.md`` §5) — this module reuses
the identical ``DesignExport``/``mgcv_reference.json`` the ten-cell suite
already exports, adding no new R work.
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.experience_mgcv_conformance import DesignExport
from polaris_re.analytics.gam_family import Family, poisson_log
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_optimize import (
    ContinuousLambdaSelection,
    select_lambdas_continuous,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "CONTINUOUS_LAMBDA_CLAIM",
    "FIXED_SP_MULTITERM_REML_CLAIM",
    "ContinuousSelectionComparison",
    "FixedSpMultiTermComparison",
    "FixedSpMultiTermPoint",
    "compare_continuous_selection",
    "compare_fixed_sp_multiterm_case",
]


CONTINUOUS_LAMBDA_CLAIM = VerificationClaim(
    claim=(
        "gam_reml_optimize.select_lambdas_continuous selects (lambda_age, "
        "lambda_year) by minimizing gam_reml.reml_score_general via SciPy "
        "L-BFGS-B, refitting gam_fit.penalized_irls_general at every trial "
        "point over the shared (X, S_age, S_year) design — never reading "
        "mgcv's own selection, score or coefficients; mgcv selects its own "
        "(lambda_age, lambda_year) via its own continuous REML optimiser "
        "(gam(family=poisson(), method='REML') with free sp, "
        "scripts/mgcv_conformance.R); compared on the joint "
        "max_abs_log10_sp_diff and edf_total, per free-sp cell of the "
        "ten-cell conformance fixture."
    ),
    quantities=(
        ComparedQuantity(
            quantity="max_abs_log10_sp_diff (continuous search)",
            left_producer="gam_reml_optimize.select_lambdas_continuous",
            right_producer="mgcv gam(family=poisson(), method='REML') free-sp selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (continuous search)",
            left_producer=(
                "gam_fit.effective_degrees_of_freedom at select_lambdas_continuous's "
                "own selected log_lambda"
            ),
            right_producer="mgcv's edf.total at its own free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""ADR-193's provenance declaration. Both quantities are INDEPENDENT by the
mechanical test: `select_lambdas_continuous`'s signature takes a design and
penalty blocks, never an `mgcv`-payload-shaped argument, and it is never
called with `mgcv`'s own coefficients, score or selection as an input at any
point in the search. `mgcv`'s own selection is read from the ten-cell
suite's already-committed `mgcv_reference.json`, which is `mgcv`'s own
independent free-sp REML fit — the identical source the suite's own,
already-INDEPENDENT `max_abs_log10_sp_diff`/`abs_edf_total_diff_free_sp`
metrics read (`docs/VERIFICATION_STANDARD.md` §5)."""


@dataclass(frozen=True)
class ContinuousSelectionComparison:
    """One free-``sp`` cell's continuous selection against ``mgcv``'s own,
    alongside the already-committed production-grid selection for the same
    cell (read, not recomputed, so this never re-fits the grid)."""

    cell: str
    selection: ContinuousLambdaSelection
    mgcv_log_lambda: np.ndarray
    mgcv_edf_total: float
    grid_log_lambda: np.ndarray
    grid_max_abs_log10_sp_diff: float
    max_abs_log10_sp_diff: float
    """``max(|continuous.log_lambda - mgcv_log_lambda|)`` — the same metric
    shape as the ten-cell suite's ``max_abs_log10_sp_diff``, computed here for
    the continuous search rather than the grid."""
    edf_total_diff: float
    """``selection.edf_total - mgcv_edf_total`` — SIGNED, unlike the ten-cell
    suite's own ``abs_edf_total_diff_free_sp`` (PR #205 review [P2]: no
    ``abs()`` is taken here, so this field is named without the misleading
    ``abs_`` prefix)."""


def compare_continuous_selection(
    cell_name: str,
    export: DesignExport,
    mgcv_sp: tuple[float, float],
    mgcv_edf_total: float,
    grid_log_lambda: np.ndarray,
    *,
    gamma: float = 1.0,
    gtol: float = 1.0e-8,
) -> ContinuousSelectionComparison:
    """Run the continuous search on ``export`` and compare it against
    ``mgcv``'s own free-``sp`` selection for the same cell.

    Args:
        cell_name: the conformance cell's name, carried through for reporting.
        export: the design this cell fits — ``DesignExport.s_age``/``s_year``
            are the two penalty blocks.
        mgcv_sp: ``mgcv``'s own selected ``(lambda_age, lambda_year)``, read
            from ``mgcv_reference.json`` — never computed here.
        mgcv_edf_total: ``mgcv``'s own ``edf.total`` at that selection.
        grid_log_lambda: the production grid's own selected
            ``log10(lambda_age, lambda_year)`` for the same cell, read from
            ``python_reference.json`` — reported alongside for context, not
            recomputed.
        gamma: Wood's smoothness multiplier, passed through unchanged.
        gtol: the continuous search's own convergence tolerance.
    """
    selection = select_lambdas_continuous(
        export.deaths,
        export.design,
        poisson_log(),
        (export.s_age, export.s_year),
        offset=export.offset,
        gamma=gamma,
        gtol=gtol,
    )
    mgcv_log = np.log10(np.asarray(mgcv_sp, dtype=np.float64))
    grid_log = np.asarray(grid_log_lambda, dtype=np.float64)
    return ContinuousSelectionComparison(
        cell=cell_name,
        selection=selection,
        mgcv_log_lambda=mgcv_log,
        mgcv_edf_total=mgcv_edf_total,
        grid_log_lambda=grid_log,
        grid_max_abs_log10_sp_diff=float(np.max(np.abs(grid_log - mgcv_log))),
        max_abs_log10_sp_diff=float(np.max(np.abs(selection.log_lambda - mgcv_log))),
        edf_total_diff=float(selection.edf_total - mgcv_edf_total),
    )


FIXED_SP_MULTITERM_REML_CLAIM = VerificationClaim(
    claim=(
        "gam_reml_optimize.penalized_fit_and_score fits the target formula's "
        "own four-block structure (a reference-age cr smooth, its numeric-by "
        "scaling, and ti()'s two margins) via gam_fit.penalized_irls_general "
        "and scores it with gam_reml.reml_score_general, at a caller-supplied "
        "fixed log10(lambda) per block -- never reading mgcv's own eta, coef, "
        "score or deviance; mgcv computes the identical model via "
        "gam(family=binomial(link='cloglog'), weights=ExposCnt, sp=10**log10_sp) "
        "at the SAME fixed sp point (scripts/gam_fixed_sp_score_probe.R); "
        "compared, per point, on the REML score (read as the SPREAD of "
        "`ours - mgcv` across all 8 points, since a constant additive offset "
        "between the two criteria is expected and only variation is "
        "diagnostic -- see REML_SCORE_CLAIM's own module docstring for why "
        "the absolute value is not compared) and on deviance directly, which "
        "rules out the most plausible harness artifact (mgcv rescaling the "
        "supplied penalty via gam.control()$scalePenalty) the same way "
        "REML_SCORE_CLAIM's own deviance companion does."
    ),
    quantities=(
        ComparedQuantity(
            quantity="reml_score (spread of ours - mgcv across 8 fixed-sp points)",
            left_producer=(
                "gam_reml_optimize.penalized_fit_and_score at a caller-supplied "
                "fixed log10(lambda), on the four-block design"
            ),
            right_producer=(
                "mgcv gam(family=binomial(link='cloglog'), sp=10**log10_sp)$gcv.ubre "
                "at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="deviance",
            left_producer=(
                "gam_family.Family.deviance on the SAME independently-converged "
                "penalized_irls_general fit compare_fixed_sp_multiterm_case uses"
            ),
            right_producer="mgcv m$deviance at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""ADR-193's provenance declaration for the fixed-`sp` measurement PLAN slice
5c registered (PR #215 review [P1-1]). Distinct from `REML_SCORE_CLAIM`
(gam_reml_conformance.py), which covers a DIFFERENT fixture — 2 blocks,
binomial-LOGIT, `paraPen`-supplied via `score_reml_point` — not the 4-block,
binomial-CLOGLOG, formula-built structure this claim covers via
`gam_reml_optimize.penalized_fit_and_score`. Both are INDEPENDENT by the same
mechanical test: neither producer's signature accepts any `mgcv`-shaped
payload (`penalized_fit_and_score` takes `y, x, family, penalty_blocks,
log_lambda, weights` — no `mgcv_score`/`eta`/`coef` field exists to read even
by accident), and `mgcv_score`/`mgcv_deviance` enter `compare_fixed_sp_multiterm_case`
only as the right-hand side of a comparison, never as an input to the left."""


@dataclass(frozen=True)
class FixedSpMultiTermPoint:
    """One fixed-``sp`` point's score and deviance, both sides."""

    name: str
    log10_sp: np.ndarray
    ours_score: float
    mgcv_score: float
    ours_deviance: float
    mgcv_deviance: float

    @property
    def score_diff(self) -> float:
        return self.ours_score - self.mgcv_score

    @property
    def deviance_diff(self) -> float:
        return self.ours_deviance - self.mgcv_deviance


@dataclass(frozen=True)
class FixedSpMultiTermComparison:
    """The whole 8-point fixed-``sp`` comparison PLAN slice 5c measures."""

    points: tuple[FixedSpMultiTermPoint, ...]
    score_diff_spread: float
    """``max(score_diff) - min(score_diff)`` — the headline metric: NOT ~0
    means the criterion itself moves with `sp` relative to `mgcv`'s; ~0 means
    the two criteria agree up to an additive constant at every tested point."""
    max_abs_deviance_diff: float
    evidence: VerificationClaim = FIXED_SP_MULTITERM_REML_CLAIM


def compare_fixed_sp_multiterm_case(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    weights: np.ndarray,
    points: tuple[dict[str, object], ...],
) -> FixedSpMultiTermComparison:
    """Fit and score the shared design at each of ``points``' fixed
    ``log10(sp)``, and compare against the SAME point's ``mgcv_score``/
    ``mgcv_deviance`` (read from ``scripts/gam_fixed_sp_score_probe.R``'s
    payload, never as an input to the fit or score computed here).

    Args:
        y: response, ``(n,)``.
        x: the assembled design, ``(n, p)``.
        family: the shared family/link (target formula: binomial/cloglog).
        penalty_blocks: one ``(p, p)`` block per smoothing parameter.
        weights: prior weights (``ExposCnt``).
        points: each entry has ``log10_sp`` (one value per block),
            ``mgcv_score`` and ``mgcv_deviance`` — the R probe's own payload
            rows, read as plain dicts so this function's signature carries
            no `mgcv`-shaped type a caller could feed back to it.

    Raises:
        PolarisValidationError: if any point's ``log10_sp`` length does not
            match ``penalty_blocks``.
    """
    rows = []
    for point in points:
        log10_sp = np.asarray(point["log10_sp"], dtype=np.float64)
        if log10_sp.shape != (len(penalty_blocks),):
            raise PolarisValidationError(
                f"compare_fixed_sp_multiterm_case: point {point['name']!r} has "
                f"{log10_sp.shape[0]} log10_sp entries, expected "
                f"{len(penalty_blocks)} (one per penalty block)."
            )
        lambdas = 10.0**log10_sp
        penalty = np.zeros_like(penalty_blocks[0])
        for lam, block in zip(lambdas, penalty_blocks, strict=True):
            penalty = penalty + lam * block
        fit = penalized_irls_general(x, y, family=family, penalty=penalty, weights=weights)
        eta = x @ fit.coef
        mu = family.link.linkinv(eta)
        ours_deviance = family.deviance(y, mu, weights)
        ours_score = reml_score_general(
            y, x, family, fit.coef, penalty_blocks, lambdas, weights=weights
        )
        rows.append(
            FixedSpMultiTermPoint(
                name=str(point["name"]),
                log10_sp=log10_sp,
                ours_score=ours_score,
                mgcv_score=float(point["mgcv_score"]),  # type: ignore[arg-type]
                ours_deviance=ours_deviance,
                mgcv_deviance=float(point["mgcv_deviance"]),  # type: ignore[arg-type]
            )
        )
    score_diffs = np.array([r.score_diff for r in rows])
    deviance_diffs = np.array([abs(r.deviance_diff) for r in rows])
    return FixedSpMultiTermComparison(
        points=tuple(rows),
        score_diff_spread=float(score_diffs.max() - score_diffs.min()),
        max_abs_deviance_diff=float(deviance_diffs.max()),
    )
