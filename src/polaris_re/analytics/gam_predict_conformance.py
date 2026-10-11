"""``PolarisGAMFit.predict`` against ``mgcv``'s ``predict.gam`` at held-out rows —
preview epic Slice P1 (``docs/PLAN_gam_parity_preview.md``, ADR-249).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:meth:`~polaris_re.analytics.gam_model.PolarisGAMFit.predict` /
:func:`~polaris_re.analytics.gam_predict.predict_design`) computes the design and
the linear predictor at held-out rows from the training recipe plus the new
covariates; ``mgcv`` computes the same via ``predict.gam(m, newdata,
type=c('lpmatrix','link','response'))`` from its own fit; compared on the
lpmatrix, eta (in range and beyond the training range), the response, and — as a
control — eta at the training rows."*

**Provenance.** Every column is INDEPENDENT. The Polaris producer
(:func:`fit_predict_case`) takes :class:`PredictRecipe` — training columns, ``y``
and the new rows' COVARIATES, never an ``mgcv`` output — and :class:`PredictPayload`
carries ``mgcv``'s outputs separately under a different type. Polaris does not
supply ``mgcv`` any quantity it later reads back.

**Two layers, deliberately separate.** The ``lpmatrix`` column is free of the
smoothing-parameter search: it compares the two bases evaluated at the SAME new
rows, so it isolates the stored-state rebuild (knots, absorbed constraint,
``by``/factor handling, linear extrapolation) at the Stage-A tolerance
(``1e-9``, :data:`~polaris_re.analytics.gam_stage_a._AGREEMENT_TOLERANCE`,
imported). The ``eta`` columns include the fit, so they carry ADR-221's gate
(``2e-2``, imported) — an ``eta`` gap there can be the fit's, not the
predictor's, which is why the training-row control is declared beside them. The
beyond-range ``eta`` is REPORTED, never gated: linear extrapolation amplifies
whatever fit gap exists, so a gate on it would measure the fit twice.

The ``gaussian_sz`` cell compares the ``lpmatrix`` only: free-``sp`` ``sz`` is not a
verified fit (``MGCV_FEATURE_COVERAGE.md``), so no Polaris fit is made for it.
"""

from dataclasses import dataclass
from typing import NotRequired, TypedDict

import numpy as np

from polaris_re.analytics.gam_model import PolarisGAMFit, fit_polaris_gam, resolve_family
from polaris_re.analytics.gam_predict import TermState, fit_term_state, predict_design
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_stage_a import _AGREEMENT_TOLERANCE as _STAGE_A_TOLERANCE
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "PREDICT_CASE_NAMES",
    "PREDICT_CLAIM",
    "SELECT_CASE_NAMES",
    "PredictCaseComparison",
    "PredictPayload",
    "PredictRecipe",
    "PredictedCase",
    "compare_predict_case",
    "fit_predict_case",
    "predict_model_spec",
]

PREDICT_CASE_NAMES: tuple[str, ...] = (
    "gaussian_cr_by_ti",
    "gaussian_factor_by",
    "gaussian_parametric",
    "quasipoisson_cr_re_ti",
    "binomial_cr",
    "poisson_offset",
    "gaussian_sz",
    "poisson_hgam",
    "gaussian_select",
    "gaussian_select_factor_by_main",
    "poisson_select_factor_by_only",
)

SELECT_CASE_NAMES: frozenset[str] = frozenset(
    {"gaussian_select", "gaussian_select_factor_by_main", "poisson_select_factor_by_only"}
)
"""Cells fitted with ``select=TRUE`` (the last two are Slice R1, ADR-258)."""

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, never redeclared (Anchor W5)."""
_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
_SE_REL_TOLERANCE = 0.02
"""Relative gate on ``se.fit`` (``Vp`` and ``Vc``), derived BEFORE the first tier-3
run of the P2 comparison (ADR-250). ``Vp`` has no Taylor remainder, so its only
disagreement source is the two engines' smoothing parameters — which ADR-221's
``eta`` gate already bounds at ``2e-2`` — and ``se`` is a smooth functional of
``rho`` of the same order of sensitivity as ``eta``. The ``Vc - Vp`` correction
carries Wood-Pya-Säfken's dropped remainder, whose measured floor is ADR-202's
``0.73%`` over five held-out cases against its committed ``2%`` (Anchor 8). One
number, ``2e-2``, therefore serves both: no wider than the committed uncertainty
tolerance, and applied to a relative ``se`` rather than an absolute ``eta``. An
exceedance is a reported result, never a reason to widen it."""
_LPMATRIX_TOLERANCE = _STAGE_A_TOLERANCE
"""The Stage-A design tolerance (``1e-9``), imported. Derived before the first
tier-3 run of this comparison (ADR-249): the lpmatrix comparison is Stage A
evaluated at new rows, so it inherits Stage A's tolerance rather than a new one."""


class PredictRecipe(TypedDict):
    """What Polaris may read: the shared recipe. No ``mgcv`` output is a key here."""

    name: str
    family: str
    link: str
    offset_column: str | None
    n_levels: dict[str, int]
    train: dict[str, list[float]]
    y: list[float]
    new_inrange: dict[str, list[float]]
    new_outrange: dict[str, list[float]]
    fit_polaris: bool


class _MgcvBlock(TypedDict):
    lpmatrix: list[list[float]]
    link: list[float]
    response: list[float]
    se_link: list[float]
    se_link_unconditional: list[float]
    se_response: list[float]
    cov_proj: list[list[float]]
    cov_proj_unconditional: list[list[float]]


class _MgcvOutputs(TypedDict):
    inrange: _MgcvBlock
    outrange: _MgcvBlock
    eta_train: list[float]
    scale: float
    sp: list[float]
    edf_total: float


class PredictPayload(PredictRecipe):
    """The R probe's full cell: the recipe, plus ``mgcv``'s own outputs."""

    mgcv: _MgcvOutputs
    family_name: NotRequired[str]


def predict_model_spec(name: str, n_levels: dict[str, int], offset_column: str | None) -> ModelSpec:
    """The ``ModelSpec`` for each probe cell — written here by hand against the
    R formula in ``scripts/gam_predict_probe.R`` (the formula front end is Slice
    P3). Term order is ``mgcv``'s column order: parametric blocks first."""
    cr = lambda label, var, k, by=None: TermSpec(  # noqa: E731
        label=label, variables=(var,), basis="cr", k=(k,), by=by
    )
    family, link = {
        "gaussian_cr_by_ti": ("gaussian", "identity"),
        "gaussian_factor_by": ("gaussian", "identity"),
        "gaussian_parametric": ("gaussian", "identity"),
        "quasipoisson_cr_re_ti": ("quasipoisson", "log"),
        "binomial_cr": ("binomial", "logit"),
        "poisson_offset": ("poisson", "log"),
        "poisson_hgam": ("poisson", "log"),
        "gaussian_select": ("gaussian", "identity"),
        "gaussian_select_factor_by_main": ("gaussian", "identity"),
        "poisson_select_factor_by_only": ("poisson", "log"),
        "gaussian_sz": ("gaussian", "identity"),
    }[name]
    terms: tuple[TermSpec, ...]
    if name == "gaussian_cr_by_ti":
        terms = (
            cr("s(x)", "x", 9),
            cr("s(x,by=w)", "x", 9, by="w"),
            TermSpec(label="ti(x,z)", variables=("x", "z"), basis="ti", k=(7, 5)),
        )
    elif name == "gaussian_factor_by":
        terms = (
            cr("s(x)", "x", 8),
            *factor_by_terms(
                base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=n_levels["f"]
            ),
        )
    elif name == "gaussian_parametric":
        terms = (
            TermSpec(label="A", variables=("A",), basis="parametric", levels=(n_levels["A"],)),
            TermSpec(label="B", variables=("B",), basis="parametric", levels=(n_levels["B"],)),
            TermSpec(
                label="A:B",
                variables=("A", "B"),
                basis="parametric",
                levels=(n_levels["A"], n_levels["B"]),
            ),
            cr("s(x)", "x", 8),
        )
    elif name == "quasipoisson_cr_re_ti":
        terms = (
            cr("s(x)", "x", 8),
            TermSpec(label="s(f)", variables=("f",), basis="re", n_levels=n_levels["f"]),
            TermSpec(label="ti(x,z)", variables=("x", "z"), basis="ti", k=(6, 5)),
        )
    elif name == "binomial_cr":
        terms = (cr("s(x)", "x", 8), cr("s(z)", "z", 6))
    elif name == "poisson_offset":
        terms = (cr("s(x)", "x", 8),)
    elif name == "poisson_hgam":
        terms = (
            cr("s(age)", "age", 7),
            cr("s(year)", "year", 5),
            TermSpec(label="ti(age,year)", variables=("age", "year"), basis="ti", k=(7, 5)),
            cr("s(dur)", "dur", 5),
        )
    elif name == "gaussian_select":
        terms = (cr("s(x)", "x", 8), cr("s(z)", "z", 6), cr("s(w)", "w", 6))
    elif name == "gaussian_select_factor_by_main":
        terms = (
            TermSpec(label="f", variables=("f",), basis="parametric", levels=(n_levels["f"],)),
            *factor_by_terms(
                base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=n_levels["f"]
            ),
        )
    elif name == "poisson_select_factor_by_only":
        terms = tuple(
            factor_by_terms(
                base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=n_levels["f"]
            )
        )
    elif name == "gaussian_sz":
        terms = (
            TermSpec(
                label="s(f,x)",
                variables=("f", "x"),
                basis="sz",
                k=(8,),
                n_levels=n_levels["f"],
            ),
        )
    else:
        raise PolarisValidationError(f"predict_model_spec: unknown cell {name!r}.")
    return ModelSpec(
        family=family,
        link=link,
        terms=terms,
        offset_column=offset_column,
        select=name in SELECT_CASE_NAMES,
    )


def _arrays(cols: dict[str, list[float]]) -> dict[str, np.ndarray]:
    return {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}


def _as_data(cols: dict[str, list[float]], factors: set[str]) -> dict[str, np.ndarray]:
    return {
        k: (np.asarray(v, dtype=np.int64) if k in factors else np.asarray(v, dtype=np.float64))
        for k, v in cols.items()
    }


@dataclass(frozen=True)
class PredictedCase:
    """Polaris's side of one cell: everything :func:`compare_predict_case` reads."""

    name: str
    fit: PolarisGAMFit | None
    design_inrange: np.ndarray
    design_outrange: np.ndarray
    link_inrange: np.ndarray | None
    link_outrange: np.ndarray | None
    response_inrange: np.ndarray | None
    se_link: np.ndarray | None = None
    se_link_unconditional: np.ndarray | None = None
    se_response: np.ndarray | None = None
    cov_proj: np.ndarray | None = None
    cov_proj_unconditional: np.ndarray | None = None
    vcov_refusal: str | None = None
    """``PolarisComputationError`` text when the covariance is refused (a
    numerically singular ``XᵀWX + S_lambda``); ``None`` when it was computed."""
    unconditional_refusal: str | None = None
    scale: float | None = None


def fit_predict_case(recipe: PredictRecipe) -> PredictedCase:
    """The independent Python producer. Its signature takes :class:`PredictRecipe`
    only — training columns, ``y`` and the new rows' covariates — so it cannot
    read ``mgcv``'s ``lpmatrix`` / ``link`` / ``response`` / ``sp`` / ``edf``."""
    factors = set(recipe["n_levels"])
    model = predict_model_spec(recipe["name"], recipe["n_levels"], recipe["offset_column"])
    train = _as_data(recipe["train"], factors)
    new_in = _as_data(recipe["new_inrange"], factors)
    new_out = _as_data(recipe["new_outrange"], factors)
    if not recipe["fit_polaris"]:
        states: tuple[TermState, ...] = tuple(fit_term_state(t, train) for t in model.terms)
        return PredictedCase(
            name=recipe["name"],
            fit=None,
            design_inrange=predict_design(model, states, new_in),
            design_outrange=predict_design(model, states, new_out),
            link_inrange=None,
            link_outrange=None,
            response_inrange=None,
        )
    fit = fit_polaris_gam(model, train, np.asarray(recipe["y"], dtype=np.float64), outer="newton")
    x_in = predict_design(model, fit.term_states, new_in)
    se_link = se_resp = cov_proj = None
    se_unc = cov_unc = None
    refusal = unc_refusal = None
    try:
        _, se_link = fit.predict(new_in, "link", se_fit=True)
        _, se_resp = fit.predict(new_in, "response", se_fit=True)
        cov_proj = x_in @ fit.vcov() @ x_in.T
    except PolarisComputationError as exc:
        refusal = str(exc)
    if refusal is None:
        try:
            _, se_unc = fit.predict(new_in, "link", se_fit=True, unconditional=True)
            cov_unc = x_in @ fit.vcov(unconditional=True) @ x_in.T
        except PolarisComputationError as exc:
            unc_refusal = str(exc)
    family = resolve_family(recipe["family"], recipe["link"])
    return PredictedCase(
        name=recipe["name"],
        fit=fit,
        design_inrange=x_in,
        design_outrange=predict_design(model, fit.term_states, new_out),
        link_inrange=fit.predict(new_in, "link"),
        link_outrange=fit.predict(new_out, "link"),
        response_inrange=fit.predict(new_in, "response"),
        se_link=se_link,
        se_link_unconditional=se_unc,
        se_response=se_resp,
        cov_proj=cov_proj,
        cov_proj_unconditional=cov_unc,
        vcov_refusal=refusal,
        unconditional_refusal=unc_refusal,
        scale=1.0 if family.dispersion_fixed else float(fit.dispersion.fletcher),
    )


_CLAIM_SENTENCE = (
    "Polaris (PolarisGAMFit.predict / gam_predict.predict_design) computes the design "
    "and the linear predictor at held-out rows from the training recipe plus the new "
    "covariates; mgcv computes the same via predict.gam(m, newdata, "
    "type=c('lpmatrix','link','response'), se.fit=TRUE, unconditional=c(FALSE,TRUE)) from "
    "its own fit; compared on the lpmatrix, eta in range and beyond the training range, "
    "the response, the link-scale se.fit under Vp and Vc, the response-scale se.fit, the "
    "projected covariances, the scale, and eta at the training rows (control)."
)

PREDICT_CLAIM = VerificationClaim(
    claim=_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="design at held-out rows, lpmatrix (in range and beyond range)",
            left_producer=(
                "gam_predict.predict_design from TermState (knots and constraint stored "
                "from the training rows)"
            ),
            right_producer="mgcv predict.gam(m, newdata, type='lpmatrix') (PredictMat)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta at held-out rows, in range",
            left_producer="PolarisGAMFit.predict(newdata, 'link') after fit_polaris_gam",
            right_producer="mgcv predict.gam(m, newdata, type='link') after gam(method='REML')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta at held-out rows, beyond the training range (reported, not gated)",
            left_producer="PolarisGAMFit.predict(newdata, 'link') with linear cr extrapolation",
            right_producer="mgcv predict.gam(m, newdata, type='link') beyond the end knots",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="response at held-out rows, in range (reported, not gated)",
            left_producer="PolarisGAMFit.predict(newdata, 'response') (family inverse link)",
            right_producer="mgcv predict.gam(m, newdata, type='response')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="se.fit on the link scale, Vp (gated, relative)",
            left_producer=(
                "PolarisGAMFit.predict(se_fit=True): sqrt(diag(X_new Vp X_new')), "
                "Vp = phi (X'WX + S)^-1 from the Polaris fit"
            ),
            right_producer="mgcv predict.gam(m, newdata, se.fit=TRUE)$se.fit from its own fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="se.fit on the link scale, Vc unconditional (gated, relative)",
            left_producer=(
                "PolarisGAMFit.predict(se_fit=True, unconditional=True): Vp + J Vrho J' + "
                "phi V'' (eq. 7) with Polaris's own exact REML Hessian"
            ),
            right_producer=("mgcv predict.gam(m, newdata, se.fit=TRUE, unconditional=TRUE)$se.fit"),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="se.fit on the response scale, Vp (reported, not gated)",
            left_producer="PolarisGAMFit.predict('response', se_fit=True): delta method",
            right_producer="mgcv predict.gam(m, newdata, type='response', se.fit=TRUE)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="X_new Vp X_new' and X_new Vc X_new' (reported, not gated)",
            left_producer="PolarisGAMFit.vcov() and vcov(unconditional=True), projected",
            right_producer="mgcv m$Vp and m$Vc, projected through predict.gam's lpmatrix",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="scale phi (reported, not gated)",
            left_producer="PolarisGAMFit.dispersion.fletcher (1 for a fixed-dispersion family)",
            right_producer="mgcv m$scale from gam(method='REML')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta at the training rows (control)",
            left_producer="PolarisGAMFit.eta from fit_polaris_gam",
            right_producer="mgcv m$linear.predictors from gam(method='REML')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (control)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Every column INDEPENDENT. The two sides differ in what they SHARE: the lpmatrix
shares only the recipe and the new covariates (no sp, no fit); the eta columns
also depend on each engine's own smoothing-parameter selection."""


@dataclass(frozen=True)
class PredictCaseComparison:
    name: str
    max_abs_lpmatrix_diff_inrange: float
    max_abs_lpmatrix_diff_outrange: float
    max_abs_eta_diff_inrange: float | None
    max_abs_eta_diff_outrange: float | None
    max_rel_response_diff_inrange: float | None
    max_abs_eta_diff_train: float | None
    edf_total_diff: float | None
    converged: bool | None
    agrees: bool
    evidence: VerificationClaim
    max_rel_se_link: float | None = None
    max_rel_se_link_unconditional: float | None = None
    max_rel_se_response: float | None = None
    max_rel_cov_proj: float | None = None
    max_rel_cov_proj_unconditional: float | None = None
    rel_scale_diff: float | None = None
    se_agrees: bool | None = None
    """Both gated ``se.fit`` columns inside :data:`_SE_REL_TOLERANCE`; ``None``
    when Polaris refused the covariance (``vcov_refusal``)."""
    vcov_refusal: str | None = None
    unconditional_refusal: str | None = None


def _max_abs(a: np.ndarray, b: np.ndarray, what: str) -> float:
    if a.shape != b.shape:
        raise PolarisValidationError(
            f"compare_predict_case: {what}: shapes {a.shape} vs {b.shape}."
        )
    return float(np.max(np.abs(a - b)))


def compare_predict_case(python: PredictedCase, payload: PredictPayload) -> PredictCaseComparison:
    """Compare Polaris's predictions with ``mgcv``'s on every declared column.

    ``agrees`` = both lpmatrix blocks within the Stage-A tolerance AND (for a cell
    with a Polaris fit) in-range ``eta`` and ``edf_total`` within ADR-221's gate AND
    ``se_agrees`` is not ``False`` (a refused covariance, ``None``, is not a miss).
    The beyond-range ``eta``, the response and the training-row control are
    reported, never gated."""
    mg = payload["mgcv"]
    lp_in = _max_abs(
        python.design_inrange,
        np.asarray(mg["inrange"]["lpmatrix"], dtype=np.float64),
        "lpmatrix in",
    )
    lp_out = _max_abs(
        python.design_outrange,
        np.asarray(mg["outrange"]["lpmatrix"], dtype=np.float64),
        "lpmatrix out",
    )
    agrees = lp_in < _LPMATRIX_TOLERANCE and lp_out < _LPMATRIX_TOLERANCE
    if python.fit is None:
        return PredictCaseComparison(
            name=python.name,
            max_abs_lpmatrix_diff_inrange=lp_in,
            max_abs_lpmatrix_diff_outrange=lp_out,
            max_abs_eta_diff_inrange=None,
            max_abs_eta_diff_outrange=None,
            max_rel_response_diff_inrange=None,
            max_abs_eta_diff_train=None,
            edf_total_diff=None,
            converged=None,
            agrees=agrees,
            evidence=PREDICT_CLAIM,
        )
    assert python.link_inrange is not None and python.link_outrange is not None
    assert python.response_inrange is not None
    eta_in = _max_abs(python.link_inrange, np.asarray(mg["inrange"]["link"]), "eta in")
    eta_out = _max_abs(python.link_outrange, np.asarray(mg["outrange"]["link"]), "eta out")
    mu_ref = np.asarray(mg["inrange"]["response"], dtype=np.float64)
    resp_rel = float(
        np.max(np.abs(python.response_inrange - mu_ref) / np.maximum(np.abs(mu_ref), 1e-12))
    )
    eta_train = _max_abs(python.fit.eta, np.asarray(mg["eta_train"]), "eta train")
    edf_diff = float(python.fit.edf_total - mg["edf_total"])
    agrees = agrees and eta_in < _ETA_TOLERANCE and abs(edf_diff) < _EDF_TOLERANCE

    def _rel(ours: np.ndarray | None, theirs: list[float] | list[list[float]]) -> float | None:
        if ours is None:
            return None
        ref = np.asarray(theirs, dtype=np.float64)
        return float(np.max(np.abs(ours - ref)) / np.max(np.abs(ref)))

    def _rel_rows(ours: np.ndarray | None, theirs: list[float]) -> float | None:
        if ours is None:
            return None
        ref = np.asarray(theirs, dtype=np.float64)
        return float(np.max(np.abs(ours - ref) / ref))

    blk = mg["inrange"]
    rel_se = _rel_rows(python.se_link, blk["se_link"])
    rel_se_unc = _rel_rows(python.se_link_unconditional, blk["se_link_unconditional"])
    se_agrees = (
        None
        if python.vcov_refusal is not None
        else (
            rel_se is not None
            and rel_se < _SE_REL_TOLERANCE
            # a Vc refusal is a stated limitation ONLY for a pivoted fit (Slice 9, ADR-255
            # Decision 3): the Vp column is still gated and Vc is reported as refused.
            # A Vc failure on an un-pivoted fit (any other cause) stays a miss.
            and (
                (python.unconditional_refusal is not None and python.fit.pivoted_columns != ())
                or (rel_se_unc is not None and rel_se_unc < _SE_REL_TOLERANCE)
            )
        )
    )
    rel_scale = None if python.scale is None else abs(python.scale - mg["scale"]) / abs(mg["scale"])
    # the family must resolve (a wrong family would fail here, not downstream)
    resolve_family(payload["family"], payload["link"])
    return PredictCaseComparison(
        name=python.name,
        max_abs_lpmatrix_diff_inrange=lp_in,
        max_abs_lpmatrix_diff_outrange=lp_out,
        max_abs_eta_diff_inrange=eta_in,
        max_abs_eta_diff_outrange=eta_out,
        max_rel_response_diff_inrange=resp_rel,
        max_abs_eta_diff_train=eta_train,
        edf_total_diff=edf_diff,
        converged=python.fit.converged,
        agrees=agrees and se_agrees is not False,
        evidence=PREDICT_CLAIM,
        max_rel_se_link=rel_se,
        max_rel_se_link_unconditional=rel_se_unc,
        max_rel_se_response=_rel_rows(python.se_response, blk["se_response"]),
        max_rel_cov_proj=_rel(python.cov_proj, blk["cov_proj"]),
        max_rel_cov_proj_unconditional=_rel(
            python.cov_proj_unconditional, blk["cov_proj_unconditional"]
        ),
        rel_scale_diff=rel_scale,
        se_agrees=se_agrees,
        vcov_refusal=python.vcov_refusal,
        unconditional_refusal=python.unconditional_refusal,
    )
