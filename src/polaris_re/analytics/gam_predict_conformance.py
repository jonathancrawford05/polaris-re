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
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "PREDICT_CASE_NAMES",
    "PREDICT_CLAIM",
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
)

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, never redeclared (Anchor W5)."""
_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
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


class _MgcvOutputs(TypedDict):
    inrange: _MgcvBlock
    outrange: _MgcvBlock
    eta_train: list[float]
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
    return ModelSpec(family=family, link=link, terms=terms, offset_column=offset_column)


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
    return PredictedCase(
        name=recipe["name"],
        fit=fit,
        design_inrange=predict_design(model, fit.term_states, new_in),
        design_outrange=predict_design(model, fit.term_states, new_out),
        link_inrange=fit.predict(new_in, "link"),
        link_outrange=fit.predict(new_out, "link"),
        response_inrange=fit.predict(new_in, "response"),
    )


_CLAIM_SENTENCE = (
    "Polaris (PolarisGAMFit.predict / gam_predict.predict_design) computes the design "
    "and the linear predictor at held-out rows from the training recipe plus the new "
    "covariates; mgcv computes the same via predict.gam(m, newdata, "
    "type=c('lpmatrix','link','response')) from its own fit; compared on the lpmatrix, "
    "eta in range and beyond the training range, the response, and eta at the training "
    "rows (control)."
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


def _max_abs(a: np.ndarray, b: np.ndarray, what: str) -> float:
    if a.shape != b.shape:
        raise PolarisValidationError(
            f"compare_predict_case: {what}: shapes {a.shape} vs {b.shape}."
        )
    return float(np.max(np.abs(a - b)))


def compare_predict_case(python: PredictedCase, payload: PredictPayload) -> PredictCaseComparison:
    """Compare Polaris's predictions with ``mgcv``'s on every declared column.

    ``agrees`` = both lpmatrix blocks within the Stage-A tolerance AND (for a cell
    with a Polaris fit) in-range ``eta`` and ``edf_total`` within ADR-221's gate.
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
        agrees=agrees,
        evidence=PREDICT_CLAIM,
    )
