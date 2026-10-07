"""Predict at new rows for ``PolarisGAMFit`` (preview epic Slice P1,
``docs/PLAN_gam_parity_preview.md``, ADR-249).

``mgcv`` keeps, per smooth, what it needs to rebuild the basis at new rows:
the knots, the identifiability constraint absorbed from the *training* design,
and the ``by``/factor metadata (``m$smooth[[i]]``, used by ``PredictMat``).
:class:`TermState` is that object here. :func:`fit_term_state` records it from
the training data; :func:`predict_term_design` evaluates a term at any rows from
the stored state alone; :func:`predict_design` assembles the full design
(intercept first, then each term in ``ModelSpec.terms`` order — the same layout
:func:`~polaris_re.analytics.gam_model.assemble_model_design` uses).

**Nothing here is a new numeric formula.** Every call is the same basis function
:func:`~polaris_re.analytics.gam_stage_a.build_python_cr_term` (and its ``ti`` /
``sz`` / ``re`` / ``parametric`` / factor-``by`` siblings) already calls, applied
to the new rows with the *stored* knots and constraint instead of ones recomputed
from them. The training design rebuilt this way is bit-identical to
``assemble_model_design`` (pinned by ``tests/test_analytics/test_gam_predict.py``),
which is what makes predicting at the training rows a refactor check and not a
second implementation.

Out-of-range numeric covariates: ``mgcv`` extrapolates a ``cr`` smooth
LINEARLY along the end slope of the natural spline, in the training design and
in ``predict.gam`` alike. :func:`~polaris_re.analytics.gam_basis_cr._cr_basis_raw`
does the same (ADR-249). A factor code outside ``[0, n_levels)`` raises, as
``predict.gam`` raises on an unseen level.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.gam_basis_cr import (
    by_factor_mask_design,
    by_scale_design,
    cr_basis,
    cr_default_knots,
    sum_to_zero_null_space,
    sz_basis,
)
from polaris_re.analytics.gam_basis_parametric import parametric_design
from polaris_re.analytics.gam_basis_re import re_basis
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "TermState",
    "fit_term_state",
    "predict_design",
    "predict_term_design",
]


@dataclass(frozen=True)
class TermState:
    """What a term must remember from its training rows to be evaluated at new
    ones — the analogue of one ``m$smooth[[i]]``.

    ``knots`` and ``constraint`` carry one entry per smoothed margin (one for
    ``cr`` / ``sz``, two for ``ti``, none for ``re`` / ``parametric``).
    ``constraint[i]`` is margin ``i``'s sum-to-zero null-space basis ``Z`` from
    the *training* design, or absent where ``mgcv`` absorbs none (numeric-``by``,
    ``sz``, ``re``, ``parametric``).
    """

    term: TermSpec
    knots: tuple[np.ndarray, ...] = ()
    constraint: tuple[np.ndarray, ...] = ()


def _knots_for(term: TermSpec, variable: str, k: int, x: np.ndarray) -> np.ndarray:
    supplied = term.knots_by_variable().get(variable)
    if supplied is not None:
        return np.asarray(supplied, dtype=np.float64)
    return cr_default_knots(x, k)


def _column(data: Mapping[str, np.ndarray], name: str, term: TermSpec) -> np.ndarray:
    try:
        return np.asarray(data[name])
    except KeyError:
        raise PolarisValidationError(
            f"term {term.label!r} reads column {name!r}, which the data does not carry."
        ) from None


def fit_term_state(term: TermSpec, data: Mapping[str, np.ndarray]) -> TermState:
    """Record ``term``'s knots and absorbed constraint from the training ``data``.

    Uses the same default-knot rule and the same
    :func:`~polaris_re.analytics.gam_basis_cr.sum_to_zero_null_space` the term's
    builder uses, so the stored objects are the ones the training design was
    built from.
    """
    if term.basis == "cr":
        x = np.asarray(_column(data, term.variables[0], term), dtype=np.float64)
        knots = _knots_for(term, term.variables[0], term.k[0], x)
        if term.by is not None:
            return TermState(term=term, knots=(knots,))
        z = sum_to_zero_null_space(cr_basis(x, knots)[0])
        return TermState(term=term, knots=(knots,), constraint=(z,))
    if term.basis == "ti":
        margins = []
        for variable, k in zip(term.variables, term.k, strict=True):
            x = np.asarray(_column(data, variable, term), dtype=np.float64)
            knots = _knots_for(term, variable, k, x)
            margins.append((knots, sum_to_zero_null_space(cr_basis(x, knots)[0])))
        return TermState(
            term=term,
            knots=tuple(m[0] for m in margins),
            constraint=tuple(m[1] for m in margins),
        )
    if term.basis == "sz":
        smoothed = term.variables[1]
        x = np.asarray(_column(data, smoothed, term), dtype=np.float64)
        return TermState(term=term, knots=(_knots_for(term, smoothed, term.k[0], x),))
    if term.basis in ("re", "parametric"):
        return TermState(term=term)
    raise PolarisValidationError(
        f"fit_term_state: TermSpec {term.label!r} has basis={term.basis!r}, which "
        "predict does not support — only 'cr', 'ti', 'sz', 're' and 'parametric'."
    )


def _codes(data: Mapping[str, np.ndarray], name: str, n_levels: int, term: TermSpec) -> np.ndarray:
    codes = np.asarray(_column(data, name, term), dtype=np.int64)
    if codes.size and (codes.min() < 0 or codes.max() >= n_levels):
        raise PolarisValidationError(
            f"predict: factor {name!r} (term {term.label!r}) has codes in "
            f"[{int(codes.min())}, {int(codes.max())}] but the fitted factor has "
            f"{n_levels} level(s) (codes 0..{n_levels - 1}); mgcv refuses an unseen level."
        )
    return codes


def predict_term_design(state: TermState, data: Mapping[str, np.ndarray]) -> np.ndarray:
    """``state.term``'s design block evaluated at ``data``'s rows."""
    term = state.term
    if term.basis == "cr":
        x = np.asarray(_column(data, term.variables[0], term), dtype=np.float64)
        design = cr_basis(x, state.knots[0])[0]
        if term.by_factor is not None:
            assert term.n_levels is not None and term.by_level is not None
            group = _codes(data, term.by_factor, term.n_levels, term)
            return by_factor_mask_design(design @ state.constraint[0], group, term.by_level)
        if term.by is not None:
            return by_scale_design(design, np.asarray(_column(data, term.by, term)))
        return np.asarray(design @ state.constraint[0], dtype=np.float64)
    if term.basis == "ti":
        x1 = np.asarray(_column(data, term.variables[0], term), dtype=np.float64)
        x2 = np.asarray(_column(data, term.variables[1], term), dtype=np.float64)
        d1 = cr_basis(x1, state.knots[0])[0] @ state.constraint[0]
        d2 = cr_basis(x2, state.knots[1])[0] @ state.constraint[1]
        return np.einsum("ij,ik->ijk", d1, d2).reshape(d1.shape[0], d1.shape[1] * d2.shape[1])
    if term.basis == "sz":
        assert term.n_levels is not None
        factor_name, smoothed_name = term.variables
        x = np.asarray(_column(data, smoothed_name, term), dtype=np.float64)
        group = _codes(data, factor_name, term.n_levels, term)
        return sz_basis(x, group, term.n_levels, state.knots[0])[0]
    if term.basis == "re":
        assert term.n_levels is not None
        group = _codes(data, term.variables[0], term.n_levels, term)
        return re_basis(group, term.n_levels)[0]
    if term.basis == "parametric":
        assert term.levels is not None
        groups = tuple(
            _codes(data, v, n, term) for v, n in zip(term.variables, term.levels, strict=True)
        )
        return parametric_design(groups, term.levels)
    raise PolarisValidationError(
        f"predict_term_design: TermSpec {term.label!r} has basis={term.basis!r}, "
        "which predict does not support."
    )


def predict_design(
    model: ModelSpec, states: tuple[TermState, ...], data: Mapping[str, np.ndarray]
) -> np.ndarray:
    """The full design at ``data``'s rows: an intercept column, then each term's
    block in ``model.terms`` order."""
    if len(states) != len(model.terms):
        raise PolarisValidationError(
            f"predict_design: {len(states)} stored term state(s) for {len(model.terms)} term(s)."
        )
    blocks = [predict_term_design(state, data) for state in states]
    n = blocks[0].shape[0]
    return np.hstack([np.ones((n, 1), dtype=np.float64), *blocks])
