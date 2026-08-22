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
from polaris_re.analytics.gam_family import poisson_log
from polaris_re.analytics.gam_reml_optimize import (
    ContinuousLambdaSelection,
    select_lambdas_continuous,
)
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "CONTINUOUS_LAMBDA_CLAIM",
    "ContinuousSelectionComparison",
    "compare_continuous_selection",
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
