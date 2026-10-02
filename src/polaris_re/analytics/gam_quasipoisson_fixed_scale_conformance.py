"""``quasipoisson(log)`` at an externally SUPPLIED, FIXED ``scale`` against
``mgcv`` — capability ladder slice **7** (``docs/PLAN_mgcv_capability_ladder.md``).

**What is under test.** ``mgcv``'s ``gam(family = quasipoisson(), scale = phi)``
selects its own smoothing parameters with the dispersion held at ``phi``. The
Polaris producer reaches the same model with NO new criterion code: the
``poisson(log)`` family (``dispersion_fixed=True``) with ``gamma = phi``, because
the known-scale branch of ``gam_reml.reml_score_general`` already substitutes
``gamma`` for a fixed ``phi``. ``mgcv`` itself does NOT accept ``poisson`` for
this: ``poisson(scale = phi)`` silently reports scale 1 (measured, tier 1, and
re-measured on the pinned oracle by the probe's ``poisson_ignores_scale``
tripwire), so quasi-Poisson fixed scale is reachable in ``mgcv`` only through
``quasipoisson()``.

**Claim, before the code (VERIFICATION_STANDARD §3.2)** —
:data:`QUASIPOISSON_FIXED_SCALE_CLAIM_SENTENCE`. ``phi`` is a SUPPLIED INPUT to
both sides (it is in :class:`RQuasiPoissonFixedScaleRecipe`, like the data), not
a compared quantity; ``eta``, ``log10(sp)`` and ``edf`` are each computed by
their own implementation. :func:`fit_quasipoisson_fixed_scale_case` takes the
recipe type, which structurally excludes every ``mgcv``-produced key (the
ADR-193 mechanical test).

The gate is ADR-221's committed criterion, imported and never redeclared
(Anchor W5), applied at EACH supplied ``phi`` — a near one and a far one, so an
agreement at one cannot be vacuous. ``log10(sp)`` and per-term edf are reported,
not gated.

:func:`score_at_both_points` is a DIAGNOSTIC, not a comparison: it scores
``mgcv``'s selected ``sp`` and Polaris's under Polaris's OWN criterion, with the
analytic gradient at each, to say whether a disagreement is a different
criterion or a different stationary point. It reads ``mgcv``'s ``sp`` as an
input to Polaris's scorer, so nothing it returns is parity evidence.
"""

from dataclasses import replace
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_model import (
    PolarisGAMFit,
    assemble_model_design,
    fit_polaris_gam,
    resolve_family,
)
from polaris_re.analytics.gam_quasipoisson_conformance import quasipoisson_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_score_and_gradient
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_term_spec import ModelSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "QUASIPOISSON_FIXED_SCALE_CLAIM",
    "QUASIPOISSON_FIXED_SCALE_CLAIM_SENTENCE",
    "FixedScaleCaseComparison",
    "FixedScaleStationarity",
    "PolarisFixedScaleFits",
    "RQuasiPoissonFixedScalePayload",
    "RQuasiPoissonFixedScaleRFit",
    "RQuasiPoissonFixedScaleRecipe",
    "compare_quasipoisson_fixed_scale_case",
    "fit_quasipoisson_fixed_scale_case",
    "fixed_scale_model_spec",
    "score_at_both_points",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, not redeclared (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's ``edf_total`` gate (``1.0``), imported, not redeclared."""


class RQuasiPoissonFixedScaleRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. ``scales`` is
    the supplied dispersion (an input to both sides); no ``sp`` key."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]
    scales: list[float]


class RQuasiPoissonFixedScaleRFit(TypedDict):
    """One ``mgcv`` fit at one supplied ``scale``."""

    eta: list[float]
    offset_gap: float
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    term_labels: list[str]
    scale: float
    converged: bool


class RQuasiPoissonFixedScalePayload(RQuasiPoissonFixedScaleRecipe):
    """The recipe plus ``scripts/gam_quasipoisson_fixed_scale_probe.R``'s OWN
    fits, one per supplied scale. Read by the compare function only."""

    fits: list[RQuasiPoissonFixedScaleRFit]
    poisson_scale_arg_reported: float
    poisson_ignores_scale: bool


QUASIPOISSON_FIXED_SCALE_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam, family poisson(log) "
    "with gamma=phi) assembles the three-term cr / cr-by / ti design from the "
    "shared recipe (AttdAge, PolYear, StudyYear_C, an overdispersed count y, "
    "the target formula's own knot vectors, and the SUPPLIED dispersion phi), "
    "and selects its own log10(lambda) for all four penalty blocks by "
    "minimizing gam_reml.reml_score_general's known-scale branch with gamma "
    "substituting for the fixed phi (from two starts — the bounds-centre and "
    "the gamma=1 solution — keeping the lower own-criterion score, slice 7b), "
    "then fits with gam_fit.penalized_irls_general — never reading mgcv's own eta, coef, sp "
    "or edf; mgcv computes it via gam(family=quasipoisson(link='log'), "
    "method='REML', scale=phi) with free sp "
    "(scripts/gam_quasipoisson_fixed_scale_probe.R). Compared at each of two "
    "supplied phi on eta at the training design, edf_total and per-term edf, "
    "gated on ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared; log10(sp) per "
    "block and per-term edf are reported, not gated. phi is supplied to both "
    "sides and is not a compared quantity. Coefficients are never compared "
    "(PLAN Anchor 2)."
)


QUASIPOISSON_FIXED_SCALE_CLAIM = VerificationClaim(
    claim=QUASIPOISSON_FIXED_SCALE_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris poisson+gamma=phi vs mgcv quasipoisson scale=phi, free sp)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(quasipoisson, scale=phi, method='REML'), m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block (Polaris vs mgcv, fixed scale, free sp)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its fixed-scale REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris vs mgcv, fixed scale, free sp)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its fixed-scale REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris vs mgcv, fixed scale, free sp)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'], read positionally in formula order"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 7's provenance declaration. Every compared quantity INDEPENDENT; the
supplied ``phi`` is an input to both sides, not a compared quantity."""


def fixed_scale_model_spec(
    age_knots: tuple[float, ...], year_knots: tuple[float, ...]
) -> ModelSpec:
    """The three-term ``ModelSpec`` of ladder L1 under ``poisson(log)`` — the
    family whose known-scale criterion ``gamma`` turns into a fixed dispersion."""
    return replace(quasipoisson_model_spec(age_knots, year_knots), family="poisson")


def _model_and_data(
    r_case: RQuasiPoissonFixedScaleRecipe,
) -> tuple[ModelSpec, dict[str, np.ndarray], np.ndarray]:
    model = fixed_scale_model_spec(
        tuple(float(v) for v in r_case["age_knots"]),
        tuple(float(v) for v in r_case["year_knots"]),
    )
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
    }
    return model, data, np.asarray(r_case["y"], dtype=np.float64)


type PolarisFixedScaleFits = list[PolarisGAMFit]
"""One :class:`PolarisGAMFit` per supplied scale, in ``scales`` order."""


def _fit_best_of_cold_and_unit_gamma_seed(
    model: ModelSpec,
    data: dict[str, np.ndarray],
    y: np.ndarray,
    phi: float,
    unit_fit: PolarisGAMFit,
    multistart: bool,
) -> PolarisGAMFit:
    """Two starts, one criterion: the bounds-centre (cold) search and a search
    seeded at the ``gamma = 1`` solution's ``log10(lambda)``; keep whichever
    reaches the LOWER ``reml_score``.

    **Why (slice 7b, ADR-237).** At a far ``phi`` the cold start settles in a
    different stationary point of the by-term block than ``mgcv`` does (ADR-236:
    both gradients ~0, ``mgcv``'s point scoring lower under OUR criterion).
    ``gamma`` only rescales the known-scale criterion, so the ``gamma = 1``
    minimiser sits in the basin the fixed-``phi`` minimiser continues from.
    Selection between the two candidates uses ONLY Polaris's own criterion —
    nothing ``mgcv`` produced reaches this function (ADR-193 mechanical test:
    the signature carries the recipe-derived inputs only), and no constant here
    is tuned to ``mgcv``: ``gamma = 1`` is the family's natural scale, not a
    fitted value. ``multistart=True`` replaces the cold candidate with the
    best-of-9 search; the seeded candidate is added to it, never substituted.
    """
    cold = fit_polaris_gam(model, data, y, gamma=phi, multistart=multistart)
    if np.isclose(phi, 1.0, rtol=1e-12, atol=0.0):
        return cold
    seeded = fit_polaris_gam(model, data, y, gamma=phi, x0=unit_fit.log_lambda)
    return seeded if seeded.reml_score < cold.reml_score else cold


def fit_quasipoisson_fixed_scale_case(
    r_case: RQuasiPoissonFixedScaleRecipe,
    *,
    multistart: bool = False,
    unit_gamma_seed: bool = True,
) -> PolarisFixedScaleFits:
    """The independent Python producer: for each supplied ``phi``, assemble,
    select own lambda under the known-scale criterion with ``gamma = phi``, fit.
    Never reads ``mgcv``'s ``eta``/``coef``/``sp``/``edf`` (the recipe type has
    none).

    ``unit_gamma_seed=True`` (default, slice 7b) also searches from the
    ``gamma = 1`` solution and keeps the lower-scoring of the two fits — see
    :func:`_fit_best_of_cold_and_unit_gamma_seed`. ``False`` reproduces slice
    7's cold-start-only behaviour (ADR-236's recorded far-``phi`` disagreement).
    """
    model, data, y = _model_and_data(r_case)
    if not unit_gamma_seed:
        return [
            fit_polaris_gam(model, data, y, gamma=float(phi), multistart=multistart)
            for phi in r_case["scales"]
        ]
    unit_fit = fit_polaris_gam(model, data, y, gamma=1.0)
    return [
        _fit_best_of_cold_and_unit_gamma_seed(model, data, y, float(phi), unit_fit, multistart)
        for phi in r_case["scales"]
    ]


class FixedScaleCaseComparison(TypedDict):
    scale: float
    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    r_scale: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_quasipoisson_fixed_scale_case(
    python_fits: PolarisFixedScaleFits, r_case: RQuasiPoissonFixedScalePayload
) -> list[FixedScaleCaseComparison]:
    """One comparison per supplied scale, on every quantity the claim declares.
    ``agrees`` is ADR-221's imported ``eta``/``edf_total`` criterion."""
    if len(python_fits) != len(r_case["fits"]) or len(r_case["scales"]) != len(r_case["fits"]):
        raise PolarisValidationError(
            f"compare_quasipoisson_fixed_scale_case: {len(python_fits)} Python fits, "
            f"{len(r_case['fits'])} R fits, {len(r_case['scales'])} scales."
        )
    out: list[FixedScaleCaseComparison] = []
    for phi, py, rf in zip(r_case["scales"], python_fits, r_case["fits"], strict=True):
        if not np.isclose(float(rf["scale"]), float(phi), rtol=1e-12, atol=0.0):
            raise PolarisValidationError(
                f"compare_quasipoisson_fixed_scale_case: mgcv reports scale "
                f"{rf['scale']} for supplied scale {phi}; mgcv did not hold the scale fixed."
            )
        r_eta = np.asarray(rf["eta"], dtype=np.float64)
        if r_eta.shape != py.eta.shape:
            raise PolarisValidationError(
                f"compare_quasipoisson_fixed_scale_case: R eta has shape {r_eta.shape}, "
                f"Python eta has shape {py.eta.shape}."
            )
        r_log_sp = np.log10(np.atleast_1d(np.asarray(rf["sp"], dtype=np.float64)))
        if r_log_sp.shape != py.log_lambda.shape:
            raise PolarisValidationError(
                f"compare_quasipoisson_fixed_scale_case: R sp has {r_log_sp.size} "
                f"entries, Python log_lambda has {py.log_lambda.size}."
            )
        r_term_edf = np.atleast_1d(np.asarray(rf["term_edf"], dtype=np.float64))
        py_term_edf = np.asarray(list(py.edf_per_term.values()), dtype=np.float64)
        r_labels = tuple(np.atleast_1d(np.asarray(rf["term_labels"], dtype=str)).tolist())
        if r_term_edf.shape != py_term_edf.shape or r_labels != tuple(py.edf_per_term):
            raise PolarisValidationError(
                f"compare_quasipoisson_fixed_scale_case: mgcv's s.table rows {r_labels} "
                f"do not align with Polaris's edf_per_term keys {tuple(py.edf_per_term)}."
            )
        max_abs_eta_diff = float(np.max(np.abs(r_eta - py.eta)))
        edf_total_diff = float(py.edf_total - rf["edf_total"])
        out.append(
            FixedScaleCaseComparison(
                scale=float(phi),
                max_abs_eta_diff=max_abs_eta_diff,
                max_abs_log10_sp_diff=float(np.max(np.abs(py.log_lambda - r_log_sp))),
                edf_total_diff=edf_total_diff,
                max_abs_term_edf_diff=float(np.max(np.abs(py_term_edf - r_term_edf))),
                offset_gap=float(rf["offset_gap"]),
                r_scale=float(rf["scale"]),
                at_bound=py.at_bound,
                converged=py.converged,
                agrees=(
                    py.converged
                    and bool(rf["converged"])
                    and max_abs_eta_diff < _ETA_TOLERANCE
                    and abs(edf_total_diff) < _EDF_TOLERANCE
                ),
                evidence=QUASIPOISSON_FIXED_SCALE_CLAIM,
            )
        )
    return out


class FixedScaleStationarity(TypedDict):
    """DIAGNOSTIC (not parity evidence): Polaris's own criterion at both points."""

    scale: float
    python_score: float
    mgcv_score: float
    python_max_abs_grad: float
    mgcv_max_abs_grad: float


def score_at_both_points(
    python_fits: PolarisFixedScaleFits, r_case: RQuasiPoissonFixedScalePayload
) -> list[FixedScaleStationarity]:
    """Score ``mgcv``'s selected ``sp`` and Polaris's under Polaris's own
    criterion, with the analytic gradient at each. Two near-zero gradients with
    different scores mean two stationary points of ONE criterion (a landscape
    finding), not two criteria. Reads ``mgcv``'s ``sp`` as a scorer INPUT, so it
    is a diagnostic and never evidence of agreement."""
    model, data, y = _model_and_data(r_case)
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    out: list[FixedScaleStationarity] = []
    for phi, py, rf in zip(r_case["scales"], python_fits, r_case["fits"], strict=True):
        pts: dict[str, tuple[float, float]] = {}
        for name, ll in (
            ("python", py.log_lambda),
            ("mgcv", np.log10(np.atleast_1d(np.asarray(rf["sp"], dtype=np.float64)))),
        ):
            _, score, grad = penalized_fit_score_and_gradient(
                y,
                design["x"],
                family,
                design["penalty_blocks"],
                np.asarray(ll, dtype=np.float64),
                gamma=float(phi),
            )
            pts[name] = (float(score), float(np.max(np.abs(grad))))
        out.append(
            FixedScaleStationarity(
                scale=float(phi),
                python_score=pts["python"][0],
                mgcv_score=pts["mgcv"][0],
                python_max_abs_grad=pts["python"][1],
                mgcv_max_abs_grad=pts["mgcv"][1],
            )
        )
    return out
