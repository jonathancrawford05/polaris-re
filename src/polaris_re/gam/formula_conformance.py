"""``polaris_re.gam.gam(<formula string>)`` against ``mgcv::gam(<the same string>)`` —
preview epic Slice P3 (``docs/PLAN_gam_parity_preview.md``, ADR-251).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:func:`polaris_re.gam.gam`) parses the formula string with its own parser, encodes the
DataFrame's factors with its own level-ordering rule, and fits; ``mgcv`` parses the same
string with R's formula machinery, builds factors with ``factor()`` and fits via
``gam(method='REML')``; compared on eta at the training rows, ``edf_total``, the term
structure (smooth labels, ``bs.dim``, coefficients per smooth, ``nsdf``) and the factor
level order."*

**Provenance.** Every column is INDEPENDENT. :func:`fit_formula_case` takes
:class:`FormulaRecipe` — the formula string, the family name and the data columns
(factors as their string labels) — never an ``mgcv`` output; :class:`FormulaPayload`
carries ``mgcv``'s outputs under a different type. Neither side is handed anything the
other produced. The *structure* columns are the second, cheaper column the PLAN asks
for: they check the parse, not the fit, so a mis-parse cannot hide behind a fit that
happens to land close.

**One cell is an expected refusal.** ``gaussian_factor_by_with_bare_smooth`` is
``s(x) + s(x, by=f)``: rank-deficient (ADR-250), so Polaris REFUSES it by name. For that
cell "agrees" means "refused on the structural condition" — the refusal is the
verified behaviour, ``mgcv``'s fit is carried for the record and not compared.
"""

from dataclasses import dataclass, field
from typing import TypedDict

import numpy as np
import polars as pl

from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import GamFit, gam

__all__ = [
    "EXPECTED_REFUSALS",
    "FORMULA_CLAIM",
    "FormulaCaseComparison",
    "FormulaCaseFit",
    "FormulaPayload",
    "FormulaRecipe",
    "compare_formula_case",
    "fit_formula_case",
]

EXPECTED_REFUSALS: frozenset[str] = frozenset({"gaussian_factor_by_with_bare_smooth"})
"""Cells where the verified behaviour is a refusal (ADR-250 rank defect)."""

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, never redeclared."""
_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF


class FormulaRecipe(TypedDict):
    """What Polaris may read: the formula string, family and data. No ``mgcv`` output."""

    name: str
    formula: str
    family: str
    select: bool
    weights_column: str | None
    data: dict[str, float | str | list[float] | list[str]]


class _MgcvFormulaOutputs(TypedDict):
    eta: list[float]
    edf_total: float
    edf_by_smooth: float | list[float]
    labels: str | list[str]
    bs_dim: int | list[int]
    ncoef: int | list[int]
    nsdf: int
    sp: float | list[float]
    scale: float
    levels: dict[str, str | list[str]]


class FormulaPayload(FormulaRecipe):
    """The R probe's full cell: the recipe, plus ``mgcv``'s own outputs."""

    mgcv: _MgcvFormulaOutputs


@dataclass(frozen=True)
class FormulaCaseFit:
    """Polaris's side of one cell."""

    name: str
    fit: GamFit | None
    refusal: str | None = None


def _floats(value: float | list[float]) -> list[float]:
    """``jsonlite`` ``auto_unbox`` turns a length-1 vector into a scalar."""
    return list(value) if isinstance(value, list) else [value]


def _ints(value: int | list[int]) -> list[int]:
    return [int(v) for v in value] if isinstance(value, list) else [int(value)]


def _strs(value: str | list[str]) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _col(value: float | str | list[float] | list[str]) -> list[float] | list[str]:
    if isinstance(value, list):
        return value
    return [value]  # type: ignore[return-value]


def _frame(recipe: FormulaRecipe) -> pl.DataFrame:
    return pl.DataFrame({k: _col(v) for k, v in recipe["data"].items()})


def fit_formula_case(recipe: FormulaRecipe) -> FormulaCaseFit:
    """The independent Python producer. Its signature takes :class:`FormulaRecipe`
    only, so it cannot read ``mgcv``'s eta / edf / labels / levels."""
    try:
        fit = gam(
            recipe["formula"],
            _frame(recipe),
            recipe["family"],
            weights=recipe["weights_column"],
            select=recipe["select"],
        )
    except PolarisValidationError as exc:
        return FormulaCaseFit(name=recipe["name"], fit=None, refusal=str(exc))
    return FormulaCaseFit(name=recipe["name"], fit=fit)


_CLAIM_SENTENCE = (
    "Polaris (polaris_re.gam.gam) parses the formula string with its own parser, encodes "
    "the DataFrame's factors with its own level-ordering rule and fits by REML; mgcv "
    "parses the same string with R's formula machinery, builds factors with factor() and "
    "fits via gam(method='REML'); compared on eta at the training rows, edf_total, the "
    "per-smooth edf, the term structure (smooth labels, bs.dim, coefficients per smooth, "
    "nsdf) and the factor level order."
)

FORMULA_CLAIM = VerificationClaim(
    claim=_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta at the training rows (gated, ADR-221)",
            left_producer="gam(formula, DataFrame).eta from the parsed ModelSpec + Newton REML",
            right_producer="mgcv m$linear.predictors from gam(as.formula(formula), method='REML')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (gated, ADR-221)",
            left_producer="GamFit.edf_total at the selected smoothing parameters",
            right_producer="mgcv sum(m$edf)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="term structure: smooth labels, bs.dim, coefficients per smooth, nsdf (exact)",
            left_producer=(
                "polaris_re.gam.formula.parse_formula + the assembled design's term blocks"
            ),
            right_producer=(
                "mgcv m$smooth[[i]]$label / bs.dim / (last.para - first.para + 1), m$nsdf"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="factor level order (exact)",
            left_producer="polaris_re.gam.api.r_factor_levels under ORACLE_COLLATION",
            right_producer="mgcv levels() of the model frame's factors (R's factor() sort)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-smooth edf (reported, not gated)",
            left_producer="GamFit.edf_per_term",
            right_producer="mgcv sum(m$edf) over each smooth's coefficient span",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per penalty (reported, never gated: ADR-221/248)",
            left_producer="GamFit.log_lambda from the Newton search",
            right_producer="mgcv log10(m$sp)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Every column INDEPENDENT; the two sides share only the formula text and the data."""


@dataclass(frozen=True)
class FormulaCaseComparison:
    name: str
    expected_refusal: bool
    refused: bool
    refusal: str | None
    max_abs_eta_diff: float | None
    edf_total_diff: float | None
    max_abs_edf_by_smooth_diff: float | None
    labels_match: bool | None
    bs_dim_match: bool | None
    ncoef_match: bool | None
    nsdf_match: bool | None
    levels_match: bool | None
    max_abs_log10_sp_diff: float | None
    converged: bool | None
    agrees: bool
    evidence: VerificationClaim = field(default=FORMULA_CLAIM)


def compare_formula_case(python: FormulaCaseFit, payload: FormulaPayload) -> FormulaCaseComparison:
    """Compare Polaris with ``mgcv`` on every declared column.

    ``agrees`` for an ordinary cell = eta and ``edf_total`` inside ADR-221's gate AND
    labels, ``bs.dim``, coefficient counts, ``nsdf`` and factor levels all exactly
    equal. For an :data:`EXPECTED_REFUSALS` cell it is "Polaris refused".
    """
    name = python.name
    expected = name in EXPECTED_REFUSALS
    if python.fit is None:
        return FormulaCaseComparison(
            name=name,
            expected_refusal=expected,
            refused=True,
            refusal=python.refusal,
            max_abs_eta_diff=None,
            edf_total_diff=None,
            max_abs_edf_by_smooth_diff=None,
            labels_match=None,
            bs_dim_match=None,
            ncoef_match=None,
            nsdf_match=None,
            levels_match=None,
            max_abs_log10_sp_diff=None,
            converged=None,
            agrees=expected,
        )
    if expected:
        return FormulaCaseComparison(
            name=name,
            expected_refusal=True,
            refused=False,
            refusal=None,
            max_abs_eta_diff=None,
            edf_total_diff=None,
            max_abs_edf_by_smooth_diff=None,
            labels_match=None,
            bs_dim_match=None,
            ncoef_match=None,
            nsdf_match=None,
            levels_match=None,
            max_abs_log10_sp_diff=None,
            converged=python.fit.converged,
            agrees=False,
        )
    fit, mg = python.fit, payload["mgcv"]
    eta_ref = np.asarray(_floats(mg["eta"]), dtype=np.float64)
    if fit.eta.shape != eta_ref.shape:
        raise PolarisValidationError(
            f"compare_formula_case: eta shapes {fit.eta.shape} vs {eta_ref.shape}."
        )
    eta_diff = float(np.max(np.abs(fit.eta - eta_ref)))
    edf_diff = float(fit.edf_total - mg["edf_total"])
    ncoef = tuple(
        b["end"] - b["start"]
        for b in fit.design["term_blocks"]
        if b["label"] in set(fit.smooth_labels)
    )
    labels_match = list(fit.smooth_labels) == _strs(mg["labels"])
    bs_dim_match = list(fit.smooth_bs_dim) == _ints(mg["bs_dim"])
    ncoef_match = list(ncoef) == _ints(mg["ncoef"])
    nsdf_match = fit.n_parametric == int(mg["nsdf"])
    mg_levels = {k: _strs(v) for k, v in mg["levels"].items()}
    levels_match = {k: list(v) for k, v in fit.factor_levels.items()} == mg_levels
    edf_smooth = [fit.edf_per_term[label] for label in fit.smooth_labels]
    ref_smooth = np.asarray(_floats(mg["edf_by_smooth"]), dtype=np.float64)
    edf_smooth_diff = (
        float(np.max(np.abs(np.asarray(edf_smooth) - ref_smooth)))
        if len(edf_smooth) == ref_smooth.size
        else None
    )
    sp_ref = np.log10(np.asarray(_floats(mg["sp"]), dtype=np.float64))
    sp_diff = (
        float(np.max(np.abs(fit.log_lambda - sp_ref)))
        if fit.log_lambda.size == sp_ref.size
        else None
    )
    agrees = (
        eta_diff < _ETA_TOLERANCE
        and abs(edf_diff) < _EDF_TOLERANCE
        and labels_match
        and bs_dim_match
        and ncoef_match
        and nsdf_match
        and levels_match
    )
    return FormulaCaseComparison(
        name=name,
        expected_refusal=False,
        refused=False,
        refusal=None,
        max_abs_eta_diff=eta_diff,
        edf_total_diff=edf_diff,
        max_abs_edf_by_smooth_diff=edf_smooth_diff,
        labels_match=labels_match,
        bs_dim_match=bs_dim_match,
        ncoef_match=ncoef_match,
        nsdf_match=nsdf_match,
        levels_match=levels_match,
        max_abs_log10_sp_diff=sp_diff,
        converged=fit.converged,
        agrees=bool(agrees),
    )
