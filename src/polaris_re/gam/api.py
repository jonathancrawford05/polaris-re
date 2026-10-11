"""``polaris_re.gam.gam`` — the public entry point to the ``mgcv``-parity GAM engine
(preview epic Slice P3, ``docs/PLAN_gam_parity_preview.md``, ADR-251).

A thin typed facade: parse a formula **string** from the verified subset
(:mod:`polaris_re.gam.formula`), encode a Polars DataFrame the way R does, build the
:class:`~polaris_re.analytics.gam_term_spec.ModelSpec` the verified engine takes, and
call :func:`~polaris_re.analytics.gam_model.fit_polaris_gam` with **no solver
options** (its default is the deterministic Newton search, ADR-248). Nothing here is a
new numeric formula.

**Refusal is part of the contract.** Every construct outside the verified subset
raises :class:`~polaris_re.core.exceptions.PolarisValidationError` naming the
construct and the ``MGCV_FEATURE_COVERAGE.md`` row that says why. Two refusals are
not about syntax:

* ``select=True`` is refused only when a bare smooth of a covariate sits beside a
  factor-``by`` smooth of the same covariate (the free-``sp`` search stops at a point
  ``mgcv`` scores lower on that shape, ADR-258); ``cr``, numeric-``by``, factor-``by``
  (``f + s(x, by=f)`` and ``s(x, by=f)``), ``ti``, ``re`` and the parametric block are
  accepted (ADR-217/218, ADR-252, ADR-258);
* a design whose **unpenalised null space is not identified by the data** (the
  structural condition behind ``rank(X) < p``, ADR-250) — most commonly
  ``s(x) + s(x, by=f)`` on one covariate — is **accepted** since parity-engine
  Slice 9: the unidentified coefficient is pivoted out of the fit as ``mgcv`` does
  (:mod:`~polaris_re.analytics.gam_rank_pivot`; :attr:`GamFit.pivoted_columns`).
  A rank loss that depends on the weights is not structural and is not handled.

**Factor coding reproduces R's** (``factor()``, ``contr.treatment``): levels sorted
as R sorts them, the first level the reference. R sorts strings by the session's
``LC_COLLATE``; :data:`ORACLE_COLLATION` pins the rule for the oracle image and
``scripts/gam_formula_probe.R`` reports the image's own ordering so a mismatch is a
measured result. A Polars ``Enum`` column keeps its declared order (``factor(x,
levels=...)``). Only String, Categorical and Enum columns are factors; a numeric
column used as a factor is refused rather than guessed at.
"""

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, overload

import numpy as np
import polars as pl

from polaris_re.analytics.gam_model import PolarisGAMFit, fit_polaris_gam
from polaris_re.analytics.gam_rank_pivot import unidentified_directions
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam.formula import (
    ParametricCall,
    ParsedFormula,
    TensorCall,
    parse_formula,
)
from polaris_re.gam.summary import GamSummary, build_summary

__all__ = [
    "ORACLE_COLLATION",
    "GamFit",
    "gam",
    "r_factor_levels",
    "structural_rank_deficiency",
]

ORACLE_COLLATION: Literal["C", "en_US"] = "en_US"
"""``LC_COLLATE`` rule used to sort string levels. Pinned to what the oracle image
reports (``scripts/gam_formula_probe.R`` -> ``collate``); see ADR-251."""

_COVERAGE = "docs/MGCV_FEATURE_COVERAGE.md"

_DEFAULT_LINK = {
    "gaussian": "identity",
    "poisson": "log",
    "quasipoisson": "log",
    "binomial": "logit",
}


def _collation_key(value: str, collation: str) -> tuple[object, ...]:
    if collation == "C":
        return (value,)
    if collation == "en_US":
        if not all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in value):
            raise PolarisValidationError(
                f"gam(): level {value!r} has characters outside [A-Za-z0-9_]; its sort "
                "position under en_US collation is not reproduced here. Use a pl.Enum "
                "column to state the level order explicitly."
            )

        # Measured on the oracle image (ADR-251, tier 3): '_' < digits < letters;
        # letters compare case-insensitively, lowercase before uppercase on a tie.
        def weight(ch: str) -> tuple[int, str]:
            if ch == "_":
                return (0, ch)
            return (1, ch) if ch.isdigit() else (2, ch.lower())

        return (
            tuple(weight(ch) for ch in value),
            tuple(ch.isupper() for ch in value),
        )
    raise PolarisValidationError(f"gam(): unknown collation {collation!r}.")


def r_factor_levels(
    values: Sequence[str], collation: Literal["C", "en_US"] | None = None
) -> tuple[str, ...]:
    """The level order R's ``factor(values)`` gives: ``sort(unique(values))`` under
    ``collation`` (default :data:`ORACLE_COLLATION`)."""
    rule = ORACLE_COLLATION if collation is None else collation
    unique = sorted(set(values), key=lambda v: _collation_key(v, rule))
    return tuple(unique)


@dataclass(frozen=True)
class _FactorCoding:
    levels: tuple[str, ...]

    def encode(self, column: pl.Series, name: str) -> np.ndarray:
        if column.null_count():
            raise PolarisValidationError(f"gam(): column {name!r} contains nulls.")
        text = column.cast(pl.String)
        unseen = sorted(set(text.unique().to_list()) - set(self.levels))
        if unseen:
            raise PolarisValidationError(
                f"gam(): column {name!r} has level {unseen[0]!r}, not seen when the model "
                f"was fitted ({list(self.levels)}); mgcv refuses an unseen level too."
            )
        codes = text.replace_strict(
            list(self.levels), list(range(len(self.levels))), return_dtype=pl.Int64
        )
        return np.asarray(codes.to_numpy(), dtype=np.int64)


@dataclass(frozen=True)
class GamFit(PolarisGAMFit):
    """A :class:`~polaris_re.analytics.gam_model.PolarisGAMFit` that also remembers
    the formula and the factor coding, so :meth:`predict` takes a Polars DataFrame."""

    formula: str = ""
    response: str = ""
    factor_levels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    numeric_columns: tuple[str, ...] = ()
    smooth_labels: tuple[str, ...] = ()
    """``mgcv``-style labels of the smooth terms (``s(x)``, ``s(x):w``, ``s(x):fa``,
    ``ti(x,z)``, ``s(f)``), in coefficient order after the parametric block."""
    smooth_bs_dim: tuple[int, ...] = ()
    """``mgcv``'s ``smooth$bs.dim`` per smooth: ``k`` for ``cr``, ``prod(k)`` for
    ``ti``, the level count for ``re``."""
    n_parametric: int = 0
    """``mgcv``'s ``m$nsdf``: the intercept plus the parametric block's columns."""

    def summary(self) -> GamSummary:
        """The fit report (``summary.gam``'s counterpart, no p-values): per-smooth edf and
        ``log10(sp)``, scale, REML score, deviance explained, ``n`` and the Newton
        search's convergence report. ``print(fit.summary())`` renders it."""
        return build_summary(self, self.formula, self.smooth_labels, self.n_parametric)

    def encode(self, newdata: pl.DataFrame) -> dict[str, np.ndarray]:
        """``newdata`` as the arrays :meth:`PolarisGAMFit.predict` reads."""
        out: dict[str, np.ndarray] = {}
        for name in self.numeric_columns:
            out[name] = _numeric(newdata, name)
        for name, levels in self.factor_levels.items():
            out[name] = _FactorCoding(levels).encode(_column(newdata, name), name)
        return out

    @overload
    def predict(
        self,
        newdata: pl.DataFrame,
        type: Literal["link", "response"] = "link",
        *,
        se_fit: Literal[False] = False,
        unconditional: bool = False,
    ) -> np.ndarray: ...

    @overload
    def predict(
        self,
        newdata: pl.DataFrame,
        type: Literal["link", "response"] = "link",
        *,
        se_fit: Literal[True],
        unconditional: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    @overload
    def predict(
        self,
        newdata: Mapping[str, np.ndarray],
        type: Literal["link", "response"] = "link",
        *,
        se_fit: Literal[False] = False,
        unconditional: bool = False,
    ) -> np.ndarray: ...

    @overload
    def predict(
        self,
        newdata: Mapping[str, np.ndarray],
        type: Literal["link", "response"] = "link",
        *,
        se_fit: Literal[True],
        unconditional: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def predict(
        self,
        newdata: pl.DataFrame | Mapping[str, np.ndarray],
        type: Literal["link", "response"] = "link",
        *,
        se_fit: bool = False,
        unconditional: bool = False,
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
        """``predict.gam``. A DataFrame is encoded with the fitted factor coding
        (string levels in, offset column included); a mapping of arrays is passed
        through as codes, exactly as :meth:`PolarisGAMFit.predict` takes it."""
        data = self.encode(newdata) if isinstance(newdata, pl.DataFrame) else newdata
        if se_fit:
            return super().predict(data, type, se_fit=True, unconditional=unconditional)
        return super().predict(data, type, se_fit=False, unconditional=unconditional)


def _column(df: pl.DataFrame, name: str) -> pl.Series:
    if name not in df.columns:
        raise PolarisValidationError(
            f"gam(): the data has no column {name!r} (columns: {df.columns})."
        )
    return df.get_column(name)


def _numeric(df: pl.DataFrame, name: str) -> np.ndarray:
    col = _column(df, name)
    if col.null_count():
        raise PolarisValidationError(f"gam(): column {name!r} contains nulls.")
    if not (col.dtype.is_numeric()):
        raise PolarisValidationError(
            f"gam(): column {name!r} has dtype {col.dtype}, but the formula uses it as a number."
        )
    values = col.cast(pl.Float64).to_numpy()
    if not np.all(np.isfinite(values)):
        raise PolarisValidationError(f"gam(): column {name!r} contains non-finite values.")
    return np.asarray(values, dtype=np.float64)


def _is_factor_dtype(dtype: pl.DataType) -> bool:
    return dtype in (pl.String, pl.Categorical) or isinstance(dtype, pl.Enum)


def _factor_coding(df: pl.DataFrame, name: str) -> _FactorCoding:
    col = _column(df, name)
    if not _is_factor_dtype(col.dtype):
        raise PolarisValidationError(
            f"gam(): column {name!r} has dtype {col.dtype}; factors must be String, "
            "Categorical or Enum columns (a numeric or Boolean column is never silently "
            "treated as a factor — cast it to String, or to an Enum to fix the level order)."
        )
    if col.null_count():
        raise PolarisValidationError(f"gam(): column {name!r} contains nulls.")
    if isinstance(col.dtype, pl.Enum):
        levels = tuple(col.dtype.categories.to_list())
    else:
        levels = r_factor_levels(col.cast(pl.String).unique().to_list())
    if len(levels) < 2:
        raise PolarisValidationError(
            f"gam(): factor {name!r} has {len(levels)} level(s); mgcv needs at least 2."
        )
    return _FactorCoding(levels)


def _family(family: str) -> tuple[str, str]:
    text = family.strip()
    link = None
    if "(" in text:
        name, _, rest = text.partition("(")
        inner = rest.rstrip(")").strip()
        text = name.strip()
        if inner:
            key, _, value = inner.partition("=")
            if key.strip() != "link":
                raise PolarisValidationError(
                    f"gam(): family argument {inner!r} is not supported; "
                    "only link=... is (e.g. 'binomial(link=\"cloglog\")')."
                )
            link = value.strip().strip("'\"")
    if text not in _DEFAULT_LINK:
        raise PolarisValidationError(
            f"gam(): family {text!r} is not supported — verified families are "
            f"{sorted(_DEFAULT_LINK)} ({_COVERAGE} §2.2; Gamma, nb, tw and the extended "
            "families are not verified)."
        )
    return text, link or _DEFAULT_LINK[text]


def structural_rank_deficiency(x: np.ndarray, penalty_blocks: Sequence[np.ndarray]) -> int:
    """Number of unpenalised directions the data do not identify.

    Takes the null space ``N`` of ``S = sum_j S_j`` (the directions no penalty
    touches) and counts the rank deficiency of ``X N``. A coefficient direction in
    that null space that ``X`` cannot see is not estimable at *any* smoothing
    parameter — the structural form of ``rank(X) < p`` (ADR-250). It does not depend
    on ``y`` or on the fitted smoothing parameters.
    """
    return int(unidentified_directions(x, penalty_blocks).shape[1])


def _refuse_select_with_bare_and_factor_by(smooth: Sequence[TermSpec]) -> None:
    """Allow ``select=TRUE`` with a factor-``by`` smooth only when it is the ONLY smooth of its
    covariate (Slice R1, ADR-258, pre-registered handling R1-d; an allowlist, review P1).

    Measured and agreeing with ``mgcv``: ``f + s(x, by=f)`` and ``s(x, by=f)`` (120 of 120
    draws over two independent sets). A bare smooth beside the ``by`` smooth disagreed in 17 of
    120 draws, and a second ``by`` smooth (poisson) in 11 of 120. ``select=TRUE`` penalises the
    null space of every smooth, the null spaces overlap in one direction, and the data separate
    the four-or-more penalties that share it only weakly, so the Newton search stops, converged
    by its own test, at a point ``mgcv``'s REML scores lower (a plateau, mechanism class iii).
    A ``ti`` involving the covariate beside a factor ``by`` agreed in 59 of 60 draws but the one
    miss (a flat ridge, ``eta`` 3.5e-02) is a recorded disagreement, so it is refused to the same
    standard (zero misses in the accepted forms). A numeric ``by`` beside a factor ``by`` agreed
    in 60 of 60 draws and is accepted. A recorded limitation, not something to tune around.
    """
    groups: dict[str, set[str]] = {}
    for t in smooth:
        if t.basis == "ti":
            # a tensor interaction involving the covariate counts as another smooth of it
            for v in t.variables:
                groups.setdefault(v, set()).add(f"smooth:{t.label}")
            continue
        if len(t.variables) != 1 or t.basis != "cr":
            continue
        if t.by is not None and t.by_factor is None:
            continue  # a numeric by smooth beside a factor by: 60 of 60 draws agree (ADR-258)
        key = f"by={t.by_factor}" if t.by_factor is not None else f"smooth:{t.label}"
        groups.setdefault(t.variables[0], set()).add(key)
    for var, keys in sorted(groups.items()):
        has_factor_by = any(k.startswith("by=") for k in keys)
        if has_factor_by and len(keys) > 1:
            raise PolarisValidationError(
                f"gam(): select=True with a factor-by smooth of {var!r} and another smooth of "
                f"{var!r} (a bare smooth, a second by-smooth or a ti term) "
                "is not "
                "supported — measured against mgcv, the free-sp search stops at a point its REML "
                "scores lower in about 1 draw in 7 with a bare smooth and 1 in 11 with a second "
                "by-smooth (poisson), and for a ti term an equal-score ridge with a different "
                "eta (ADR-258, R1-d). Use one smooth of "
                f'{var!r}: f + s({var}, by=f, bs="cr"), or fit without select=True '
                f"({_COVERAGE} §2.3 select row)."
            )


def _build_model(
    parsed: ParsedFormula,
    df: pl.DataFrame,
    family: str,
    link: str,
    weights: str | None,
    offset: str | None,
    select: bool,
) -> tuple[ModelSpec, dict[str, np.ndarray], dict[str, _FactorCoding], list[tuple[str, int]]]:
    data: dict[str, np.ndarray] = {}
    codings: dict[str, _FactorCoding] = {}

    def need_numeric(name: str, where: str) -> None:
        col = _column(df, name)
        if _is_factor_dtype(col.dtype):
            raise PolarisValidationError(
                f"gam(): {where} uses {name!r} as a number, but it is a factor column."
            )
        data[name] = _numeric(df, name)

    def need_factor(name: str) -> _FactorCoding:
        if name not in codings:
            codings[name] = _factor_coding(df, name)
            data[name] = codings[name].encode(_column(df, name), name)
        return codings[name]

    parametric: list[TermSpec] = []
    smooth: list[TermSpec] = []
    smooth_meta: list[tuple[str, int]] = []
    parametric_vars = [t for t in parsed.terms if isinstance(t, ParametricCall)]
    mains = {t.variables[0] for t in parametric_vars if len(t.variables) == 1}
    for pt in parametric_vars:
        for v in pt.variables:
            if not _is_factor_dtype(_column(df, v).dtype):
                raise PolarisValidationError(
                    f"gam(): the bare term {pt.text!r} is a numeric column ({v!r}, dtype "
                    f"{_column(df, v).dtype}); parametric numeric terms are not in the verified "
                    f"subset — only factor main effects and a:b ({_COVERAGE} §2.1 parametric "
                    'row). Model it with s(x, bs="cr") or cast it to String if it is a factor.'
                )
        coding = [need_factor(v) for v in pt.variables]
        if len(pt.variables) == 2 and not set(pt.variables) <= mains:
            raise PolarisValidationError(
                f"gam(): the interaction {pt.text} needs both main effects "
                f"({pt.variables[0]} and {pt.variables[1]}) in the formula; R's default "
                "coding of an interaction without them is not reproduced "
                f"({_COVERAGE} §2.1 parametric row)."
            )
        parametric.append(
            TermSpec(
                label=pt.text,
                variables=pt.variables,
                basis="parametric",
                levels=tuple(len(c.levels) for c in coding),
            )
        )

    for call in parsed.terms:
        if isinstance(call, ParametricCall):
            continue
        if isinstance(call, TensorCall):
            for v in call.variables:
                need_numeric(v, call.text)
            smooth.append(TermSpec(label=call.text, variables=call.variables, basis="ti", k=call.k))
            smooth_meta.append((call.text, int(np.prod(call.k))))
        elif call.basis == "re":
            levels = need_factor(call.variable).levels
            smooth.append(
                TermSpec(
                    label=call.text, variables=(call.variable,), basis="re", n_levels=len(levels)
                )
            )
            smooth_meta.append((call.text, len(levels)))
        else:
            assert call.k is not None
            need_numeric(call.variable, call.text)
            if call.by is None:
                smooth.append(
                    TermSpec(label=call.text, variables=(call.variable,), basis="cr", k=(call.k,))
                )
                smooth_meta.append((call.text, call.k))
            elif _is_factor_dtype(_column(df, call.by).dtype):
                levels = need_factor(call.by).levels
                for spec in factor_by_terms(
                    base_label=call.text,
                    variable=call.variable,
                    k=call.k,
                    by_factor=call.by,
                    n_levels=len(levels),
                    level_labels=tuple(f"{call.by}{lv}" for lv in levels),
                ):
                    smooth.append(spec)
                    smooth_meta.append((spec.label, call.k))
            else:
                need_numeric(call.by, call.text)
                label = f"{call.text}:{call.by}"
                smooth.append(
                    TermSpec(
                        label=label,
                        variables=(call.variable,),
                        basis="cr",
                        k=(call.k,),
                        by=call.by,
                    )
                )
                smooth_meta.append((label, call.k))

    if select:
        _refuse_select_with_bare_and_factor_by(smooth)
    if weights is not None:
        need_numeric(weights, "weights=")
    if offset is not None:
        need_numeric(offset, "offset")
    model = ModelSpec(
        family=family,
        link=link,
        terms=(*parametric, *smooth),
        weights_column=weights,
        offset_column=offset,
        select=select,
    )
    return model, data, codings, smooth_meta


def gam(
    formula: str,
    data: pl.DataFrame,
    family: str,
    *,
    weights: str | None = None,
    offset: str | None = None,
    select: bool = False,
    scale: float | None = None,
) -> GamFit:
    """Fit an ``mgcv`` GAM formula from the verified subset by REML.

    Args:
        formula: e.g. ``'y ~ g + s(x, bs="cr", k=8) + ti(x, z, bs="cr", k=c(6, 5))'``.
            Supported: ``s(x, bs="cr", k=, by=)`` (numeric or factor ``by``),
            ``s(f, bs="re")``, ``ti(x, z, bs="cr", k=)``, factors ``a``, ``a:b``
            (with both main effects), ``offset(col)``. Anything else is refused by
            name (:class:`~polaris_re.core.exceptions.PolarisValidationError`).
        data: a Polars DataFrame. String/Categorical/Enum columns are factors; no
            nulls.
        family: ``"gaussian"``, ``"poisson"``, ``"quasipoisson"``, ``"binomial"``,
            optionally with ``link=`` (``'binomial(link="cloglog")'``).
        weights: name of a prior-weights column.
        offset: name of an offset column (alternative to ``offset(col)`` in the
            formula; not both).
        select: ``mgcv``'s ``select=TRUE``. Refused only when a bare smooth of the same covariate
            sits beside a factor-``by`` smooth (ADR-258).
        scale: a fixed dispersion. **Refused:** it is verified only inside the
            conformance module (ADR-236/237), not through the production fitter.

    Returns:
        a :class:`GamFit` (a :class:`~polaris_re.analytics.gam_model.PolarisGAMFit`
        whose ``predict`` also accepts a DataFrame). The smoothing parameters come
        from the deterministic Newton REML search; there are no solver options.
    """
    if scale is not None:
        raise PolarisValidationError(
            "gam(): scale= (a fixed dispersion) is not supported — it is verified only in "
            f"the conformance module, not through fit_polaris_gam ({_COVERAGE} §2.3, "
            "ADR-236/237; production wiring is ladder slice 7c)."
        )
    if not isinstance(data, pl.DataFrame):
        raise PolarisValidationError("gam(): data must be a polars DataFrame.")
    parsed = parse_formula(formula)
    if offset is not None and parsed.offset is not None:
        raise PolarisValidationError(
            "gam(): both offset= and offset(.) in the formula were given; use one."
        )
    family_name, link = _family(family)
    model, arrays, codings, smooth_meta = _build_model(
        parsed, data, family_name, link, weights, offset or parsed.offset, select
    )
    y = _numeric(data, parsed.response)
    fit = fit_polaris_gam(model, arrays, y, warn_stacklevel=3)
    if not fit.converged:
        warnings.warn(
            "gam(): the REML search did not meet its convergence criterion; treat the fit "
            "with caution (fit.converged is False).",
            stacklevel=2,
        )
    nsdf = 1 + sum(
        b["end"] - b["start"]
        for b in fit.design["term_blocks"]
        if any(t.label == b["label"] and t.basis == "parametric" for t in model.terms)
    )
    used = {v for t in model.terms for v in (*t.variables, t.by) if v is not None}
    if model.offset_column is not None:
        used.add(model.offset_column)
    numeric_columns = tuple(sorted(used - set(codings)))
    return GamFit(
        **{f: getattr(fit, f) for f in PolarisGAMFit.__dataclass_fields__},
        formula=formula,
        response=parsed.response,
        factor_levels={name: c.levels for name, c in codings.items()},
        numeric_columns=numeric_columns,
        smooth_labels=tuple(label for label, _ in smooth_meta),
        smooth_bs_dim=tuple(dim for _, dim in smooth_meta),
        n_parametric=nsdf,
    )
