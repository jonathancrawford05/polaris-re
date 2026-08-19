"""Diagnostic-only check: does the SHIPPED tensor-MI REML score have the same
missing penalized-deviance term ADR-196 found and fixed in
``gam_reml.reml_score_general``?

``docs/WORK_ORDER_reml_penalized_deviance_production_check.md``, run under
``docs/ROUTINE_MGCV_PARITY.md`` ahead of ``docs/PLAN_mgcv_parity_engine.md``
slice 4 part B. Three measurements, in the work order's own order:

* **§3.1** — on the existing ten-cell conformance fixture
  (``experience_mgcv_conformance.py``), do the free-``sp`` cells' scores —
  computed via ``experience_gam_penalized.reml_score`` (the CURRENT,
  production formula) and via the CORRECTED formula — collapse the same way
  against ``mgcv``'s own reported ``m$gcv.ubre`` that ADR-196's own fixture
  did?
* **§3.2** — re-run the SAME 2-D grid ``select_lambdas_reml`` searches, scored
  with the corrected criterion instead, and compare the selected
  ``(λ_age, λ_year)`` against (a) the current shipped selection and (b)
  ``mgcv``'s own free-``sp`` selection (already in the ten-cell suite).
* **§3.3** — does ``smoothing_uncertainty``'s finite-difference Hessian near
  the already-selected ``sp`` change under the corrected score, even when the
  selected grid point itself does not move?

**STRICTLY DIAGNOSTIC — PLAN Anchor 7.** Nothing in this module is imported by
``experience_gam_penalized.reml_score``, ``select_lambdas_reml`` or
``smoothing_uncertainty``, and none of those three is edited here. The grid
search and the Kass-Steffey finite-difference machinery are re-implemented as
parallel, read-only replicas (:func:`select_lambdas_corrected`,
:func:`score_shape_diagnostic`) that call the corrected
scorer in place of the production one — never a patch to the production
functions themselves.

**The "corrected" score is not a new derivation.** ``gam_reml.reml_score_general``
(ADR-196, already Stage-C-verified against ``mgcv`` on its own fixture) reduces
to ``experience_gam_penalized.reml_score``'s EXACT formula plus the missing
``β̂ᵀSβ̂`` term when evaluated with ``poisson_log()`` — the same family this
module's fixture uses (Poisson log-link, offset). That relationship is already
pinned bit-for-bit by
``tests/test_analytics/test_gam_reml.py::TestRelationshipToTheExistingPoissonScore``
(``new == old + 0.5 * coef @ penalty @ coef / gamma``, to 1e-9), so
:func:`corrected_reml_score` below is a one-line call into an
already-independently-verified function, not a fresh formula written for this
work order.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam_penalized import (
    COARSE_STEP,
    KS_LOG_STEP,
    LAMBDA_LOG10_BOUNDS,
    REFINE_STEP,
    PenalizedTensorMIModel,
)
from polaris_re.analytics.experience_gam_penalized import reml_score as production_reml_score
from polaris_re.analytics.experience_mgcv_conformance import DesignExport
from polaris_re.analytics.gam_family import poisson_log
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "PRODUCTION_REML_CHECK_CLAIM",
    "CorrectedLambdaSelection",
    "ProductionScoreGap",
    "ScoreShapeDiagnostic",
    "corrected_reml_score",
    "measure_production_score_gap",
    "score_shape_diagnostic",
    "select_lambdas_corrected",
]


PRODUCTION_REML_CHECK_CLAIM = VerificationClaim(
    claim=(
        "For each free-sp cell of the ten-cell mgcv conformance fixture "
        "(experience_mgcv_conformance.py), polaris_re evaluates the REML score "
        "at its own independently fitted (lambda, coef) — the point "
        "select_lambdas_reml already selected — via two formulas: "
        "experience_gam_penalized.reml_score (current, production) and "
        "gam_reml.reml_score_general(family=poisson_log()) (corrected, ADR-196); "
        "neither reads mgcv's own score or coefficients. mgcv computes the same "
        "criterion at its own independently-selected (lambda, coef) via "
        "gam(family=poisson(), method='REML')$gcv.ubre (scripts/mgcv_conformance.R); "
        "compared, per cell, as mgcv_score minus python_score for each formula."
    ),
    quantities=(
        ComparedQuantity(
            quantity="reml_score (current, production formula)",
            left_producer=(
                "experience_gam_penalized.reml_score, evaluated at the (design, "
                "coef, penalty) select_lambdas_reml already produced"
            ),
            right_producer="mgcv m$gcv.ubre at its own free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="reml_score (corrected, Dp-based)",
            left_producer=(
                "gam_reml.reml_score_general(family=poisson_log()), evaluated at "
                "the SAME (design, coef, penalty) as the row above"
            ),
            right_producer="mgcv m$gcv.ubre at its own free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""§3.1's provenance declaration (ADR-193). Both Python-side quantities are
INDEPENDENT: neither producer's signature accepts mgcv's own score or
coefficients (the mechanical test) — `coef`/`lambda_age`/`lambda_year` are
Python's own, already-fitted answer (from `select_lambdas_reml`'s grid search,
which never reads mgcv's output either), not something read off the R side.
mgcv's score is likewise its own independent free-sp REML fit. This mirrors
how the ten-cell suite's other free-sp metrics (`max_abs_log10_sp_diff`,
`abs_edf_total_diff_free_sp`) are already treated as genuine conformance
levels (`docs/VERIFICATION_STANDARD.md` §5): two independently implemented
fitters/selectors over a shared `(X, S)` recipe, each landing on its own
answer, compared after the fact — not one side reading the other's output."""


def corrected_reml_score(
    deaths: np.ndarray,
    design: np.ndarray,
    offset: np.ndarray,
    coef: np.ndarray,
    penalty: np.ndarray,
    gamma: float = 1.0,
) -> float:
    """The Dₚ-based corrected score for a Poisson/log/offset fit — diagnostic only.

    A one-line call into :func:`gam_reml.reml_score_general` with
    ``family=poisson_log()`` — see the module docstring for why that already
    IS the corrected version of ``experience_gam_penalized.reml_score`` for
    this family, a relationship pinned by an existing test rather than
    asserted fresh here.
    """
    weights = np.ones(deaths.shape[0], dtype=np.float64)
    return reml_score_general(
        deaths, design, poisson_log(), coef, penalty, offset=offset, weights=weights, gamma=gamma
    )


def _padded_penalty(export: DesignExport, lambda_age: float, lambda_year: float) -> np.ndarray:
    """``export.s_age``/``s_year`` are already padded to the full design width
    (``experience_mgcv_conformance._pad``, applied when the exchange was
    built), matching how ``PythonCellResult``'s own ``penalty`` is assembled
    in ``_cell_result`` — no re-derivation of the padding convention here."""
    return lambda_age * export.s_age + lambda_year * export.s_year


@dataclass(frozen=True)
class ProductionScoreGap:
    """§3.1: one free-``sp`` cell's score under both formulas, against ``mgcv``."""

    cell: str
    lambda_age: float
    lambda_year: float
    gamma: float
    mgcv_score: float
    current_python_score: float
    corrected_python_score: float
    gap_current: float
    """``mgcv_score - current_python_score``."""
    gap_corrected: float
    """``mgcv_score - corrected_python_score``."""


def measure_production_score_gap(
    cell_name: str,
    export: DesignExport,
    coef: np.ndarray,
    lambda_age: float,
    lambda_year: float,
    gamma: float,
    mgcv_score: float,
) -> ProductionScoreGap:
    """§3.1's per-cell measurement: score the SAME already-fitted ``(design,
    coef, penalty)`` two ways, and compare each against ``mgcv``'s own
    reported score for that cell (``m$gcv.ubre``, already exported by
    ``scripts/mgcv_conformance.R`` — no new R work, per the work order §3.1
    point 4)."""
    penalty = _padded_penalty(export, lambda_age, lambda_year)
    current = production_reml_score(
        export.deaths, export.design, export.offset, coef, penalty, gamma
    )
    corrected = corrected_reml_score(
        export.deaths, export.design, export.offset, coef, penalty, gamma
    )
    return ProductionScoreGap(
        cell=cell_name,
        lambda_age=lambda_age,
        lambda_year=lambda_year,
        gamma=gamma,
        mgcv_score=mgcv_score,
        current_python_score=current,
        corrected_python_score=corrected,
        gap_current=mgcv_score - current,
        gap_corrected=mgcv_score - corrected,
    )


# --------------------------------------------------------------------------- #
# §3.2 — the same grid search, scored with the corrected criterion
# --------------------------------------------------------------------------- #


def _fit_and_score_both(
    cells: pl.DataFrame,
    log_age: float,
    log_year: float,
    gamma: float,
    model_kwargs: dict[str, object],
) -> tuple[np.ndarray, float, float]:
    """One fit, both scores, at one grid point.

    Fitting once and scoring the single resulting ``coef`` two ways (rather
    than fitting separately per scorer) guarantees the current-vs-corrected
    comparison isolates the SCORE FORMULA alone — both scores are built from
    bit-identical coefficients, with no risk of the two branches drifting
    apart in *which* fit produced them. Mirrors
    ``experience_gam_penalized._fit_and_score``'s structure exactly (same
    model construction, same penalty assembly); that function is not called,
    imported, or modified.
    """
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=10.0**log_age,
        lambda_year=10.0**log_year,
        **model_kwargs,  # type: ignore[arg-type]
    )
    fit = model.fit()
    context = model.design_context
    if context is None:  # pragma: no cover - fit() always sets it
        raise PolarisComputationError("fit() did not record its design context.")
    design = context.design
    penalty = np.zeros((design.shape[1], design.shape[1]), dtype=np.float64)
    penalty[: context.n_tensor, : context.n_tensor] = (
        10.0**log_age * context.s_age + 10.0**log_year * context.s_year
    )
    current = production_reml_score(
        context.deaths, design, context.offset, fit.coef, penalty, gamma
    )
    corrected = corrected_reml_score(
        context.deaths, design, context.offset, fit.coef, penalty, gamma
    )
    return fit.coef, current, corrected


@dataclass(frozen=True)
class CorrectedLambdaSelection:
    """What :func:`select_lambdas_corrected` returns — mirrors
    ``experience_gam_penalized.LambdaSelection``'s shape (not imported, since
    that type is a `NamedTuple` this module has no need to subclass), plus
    the fit's ``edf_total``/``edf_tensor``/``edf_factors`` at the SELECTED
    point (work order §3.2 point 2 — EDF, not only lambda, must be
    comparable against the current shipped selection and mgcv's own)."""

    lambda_age: float
    lambda_year: float
    reml_score: float
    n_rejected: int
    n_evaluated: int
    edf_total: float
    edf_tensor: float
    edf_factors: float


def select_lambdas_corrected(
    cells: pl.DataFrame,
    *,
    coarse_step: float = COARSE_STEP,
    refine_step: float = REFINE_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    gamma: float = 1.0,
    use_corrected_score: bool = True,
    **model_kwargs: object,
) -> CorrectedLambdaSelection:
    """§3.2: a diagnostic REPLICA of ``select_lambdas_reml``'s exact grid-search
    structure (same coarse-then-refine sweep, same bounds, same rejection
    rule), scoring each point with :func:`corrected_reml_score` instead of the
    production ``reml_score``. ``select_lambdas_reml`` itself is not called,
    imported for its scorer, or modified anywhere in this module — this is a
    parallel implementation built to answer one question (does the corrected
    criterion select a different grid point?), not a patch.

    ``use_corrected_score=False`` is the §3.2 NULL CONTROL (PR #204 review
    [P2]): it runs the identical replica sweep but scores each point with the
    CURRENT (production) criterion instead, via the same
    :func:`_fit_and_score_both` call that already computes both scores at
    every grid point. If this replica is faithful to
    ``select_lambdas_reml``, scoring it with the current criterion must
    reproduce the shipped ``python_reference.json`` selection exactly — the
    control that rules out "the corrected criterion selects closer to mgcv"
    being an artifact of a replica that already diverged from production for
    some OTHER reason (a different bound, a different rejection rule, a
    different tie-break). Default ``True`` keeps every existing call site
    (§3.2's own corrected-selection measurement) unchanged.
    """
    lo, hi = bounds
    tally = {"rejected": 0, "evaluated": 0}

    def score_at(log_age: float, log_year: float) -> float:
        tally["evaluated"] += 1
        try:
            _, current, corrected = _fit_and_score_both(
                cells, log_age, log_year, gamma, model_kwargs
            )
        except PolarisComputationError:
            tally["rejected"] += 1
            return np.inf
        value = corrected if use_corrected_score else current
        if not np.isfinite(value):
            tally["rejected"] += 1
            return np.inf
        return value

    def sweep(centre: tuple[float, float], step: float, span: float) -> tuple[float, float, float]:
        axis = np.arange(max(lo, centre[0] - span), min(hi, centre[0] + span) + step / 2.0, step)
        years = np.arange(max(lo, centre[1] - span), min(hi, centre[1] + span) + step / 2.0, step)
        best = (np.inf, centre[0], centre[1])
        for la in axis:
            for ly in years:
                value = score_at(float(la), float(ly))
                if value < best[0]:
                    best = (value, float(la), float(ly))
        return best

    coarse = sweep(((lo + hi) / 2.0, (lo + hi) / 2.0), coarse_step, (hi - lo) / 2.0)
    fine = sweep((coarse[1], coarse[2]), refine_step, coarse_step)
    if not np.isfinite(fine[0]):
        raise PolarisComputationError(
            f"Corrected-score REML selection rejected every one of {tally['evaluated']} "
            f"grid points — no penalized fit converged anywhere in log10 lambda {bounds}."
        )
    # One additional fit AT the selected point, to read off edf_total/edf_tensor/
    # edf_factors — the sweep above only tracks the SCORE at each grid point, not
    # the fit's other diagnostics, so this is a single extra fit, not part of the
    # sweep's O(grid) cost. Mirrors how fit_reml re-fits at the selected point
    # after select_lambdas_reml's own sweep (experience_gam_penalized.py).
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=10.0 ** fine[1],
        lambda_year=10.0 ** fine[2],
        **model_kwargs,  # type: ignore[arg-type]
    )
    fit = model.fit()
    return CorrectedLambdaSelection(
        10.0 ** fine[1],
        10.0 ** fine[2],
        fine[0],
        tally["rejected"],
        tally["evaluated"],
        edf_total=float(fit.edf_total),
        edf_tensor=float(fit.edf_tensor),
        edf_factors=float(fit.edf_factors),
    )


# --------------------------------------------------------------------------- #
# §3.3 — does the score's SHAPE near the optimum change under the correction?
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ScoreShapeDiagnostic:
    """§3.3: ``smoothing_uncertainty``'s finite-difference inputs, current vs
    corrected score, evaluated at the SAME already-selected ``(lambda_age,
    lambda_year)`` — not a re-selection. The fit (and therefore the Jacobian
    ``∂β̂/∂log λ``) never depends on which score formula is used
    (:func:`_fit_and_score_both` fits once per grid point and scores it both
    ways), so a difference here isolates to the Hessian/eigenvalues/
    correction magnitude alone.
    """

    hessian_current: np.ndarray
    hessian_corrected: np.ndarray
    eigenvalues_current: np.ndarray
    eigenvalues_corrected: np.ndarray
    n_floored_current: int
    n_floored_corrected: int
    correction_current: np.ndarray
    """``J V_rho Jᵀ`` built from the CURRENT score's Hessian — same construction
    as ``SmoothingUncertainty.correction``, reproduced here rather than
    called (that function fits its own 9 points; this reuses the ones this
    diagnostic already fit, so the two branches share bit-identical
    coefficients)."""
    correction_corrected: np.ndarray
    """Same, from the CORRECTED score's Hessian."""
    jacobian: np.ndarray
    """Identical either way (score-formula-independent) — carried once."""


def score_shape_diagnostic(
    cells: pl.DataFrame,
    *,
    lambda_age: float,
    lambda_year: float,
    gamma: float = 1.0,
    log_step: float = KS_LOG_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    **model_kwargs: object,
) -> ScoreShapeDiagnostic:
    """§3.3: a diagnostic REPLICA of ``smoothing_uncertainty``'s own
    central-difference Hessian construction (same 9-point stencil, same
    ``KS_LOG_STEP``, same eigenvalue-floor convention), computing it TWICE —
    once from the current score, once from the corrected one — at each of the
    9 points from a single fit each (:func:`_fit_and_score_both`).
    ``smoothing_uncertainty`` itself is not called or modified.
    """
    if log_step <= 0.0:
        raise PolarisValidationError(f"log_step must be positive, got {log_step}.")
    if lambda_age <= 0.0 or lambda_year <= 0.0:
        raise PolarisValidationError(
            "Both smoothing parameters must be strictly positive; got "
            f"({lambda_age}, {lambda_year})."
        )
    centre = np.array([np.log10(lambda_age), np.log10(lambda_year)], dtype=np.float64)
    step10 = log_step / float(np.log(10.0))

    def at(d_age: float, d_year: float) -> tuple[np.ndarray, float, float]:
        try:
            return _fit_and_score_both(
                cells, centre[0] + d_age, centre[1] + d_year, gamma, model_kwargs
            )
        except PolarisComputationError as exc:
            raise PolarisComputationError(
                "score_shape_diagnostic needs the fit at log10 lambda offset "
                f"({d_age:+.3f}, {d_year:+.3f}) from ({centre[0]:.3f}, "
                f"{centre[1]:.3f}), and it did not converge."
            ) from exc

    beta_0, cur_0, cor_0 = at(0.0, 0.0)
    beta_ap, cur_ap, cor_ap = at(+step10, 0.0)
    beta_am, cur_am, cor_am = at(-step10, 0.0)
    beta_yp, cur_yp, cor_yp = at(0.0, +step10)
    beta_ym, cur_ym, cor_ym = at(0.0, -step10)
    _, cur_pp, cor_pp = at(+step10, +step10)
    _, cur_pm, cor_pm = at(+step10, -step10)
    _, cur_mp, cor_mp = at(-step10, +step10)
    _, cur_mm, cor_mm = at(-step10, -step10)
    del beta_0  # only the four axis points feed the Jacobian, per smoothing_uncertainty

    h_sq = log_step * log_step

    def hessian_of(
        v0: float,
        ap: float,
        am: float,
        yp: float,
        ym: float,
        pp: float,
        pm: float,
        mp: float,
        mm: float,
    ) -> np.ndarray:
        return np.array(
            [
                [(ap - 2.0 * v0 + am) / h_sq, (pp - pm - mp + mm) / (4.0 * h_sq)],
                [(pp - pm - mp + mm) / (4.0 * h_sq), (yp - 2.0 * v0 + ym) / h_sq],
            ],
            dtype=np.float64,
        )

    hessian_current = hessian_of(
        cur_0, cur_ap, cur_am, cur_yp, cur_ym, cur_pp, cur_pm, cur_mp, cur_mm
    )
    hessian_corrected = hessian_of(
        cor_0, cor_ap, cor_am, cor_yp, cor_ym, cor_pp, cor_pm, cor_mp, cor_mm
    )

    jacobian = np.column_stack(
        [(beta_ap - beta_am) / (2.0 * log_step), (beta_yp - beta_ym) / (2.0 * log_step)]
    ).astype(np.float64)

    half_width = float(np.log(10.0) * (bounds[1] - bounds[0])) / 2.0
    eigenvalue_floor = 1.0 / (half_width * half_width)

    def v_rho_and_correction(hessian: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # Exactly smoothing_uncertainty's own construction (experience_gam_penalized.py),
        # reproduced rather than called — see the class docstring for why.
        eigenvalues, vectors = np.linalg.eigh(0.5 * (hessian + hessian.T))
        variances = 1.0 / np.maximum(eigenvalues, eigenvalue_floor)
        v_rho = (vectors * variances) @ vectors.T
        return eigenvalues, jacobian @ v_rho @ jacobian.T

    eig_current, correction_current = v_rho_and_correction(hessian_current)
    eig_corrected, correction_corrected = v_rho_and_correction(hessian_corrected)

    return ScoreShapeDiagnostic(
        hessian_current=hessian_current,
        hessian_corrected=hessian_corrected,
        eigenvalues_current=eig_current,
        eigenvalues_corrected=eig_corrected,
        n_floored_current=int(np.sum(eig_current <= eigenvalue_floor)),
        n_floored_corrected=int(np.sum(eig_corrected <= eigenvalue_floor)),
        correction_current=correction_current,
        correction_corrected=correction_corrected,
        jacobian=jacobian,
    )
