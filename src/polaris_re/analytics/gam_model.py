"""``PolarisGAM`` — the production path from a ``ModelSpec`` (mgcv-parity engine,
``docs/PLAN_mgcv_parity_engine.md`` slice 5b,
``docs/WORK_ORDER_multi_term_assembly.md``).

ADR-207 amended Anchor 7 to permit a production path built from the epic's
already tier-3-verified components. This module is that path, for the scope
the work order names: a model built from any mix of ``"cr"`` (with or without
a numeric ``by``) and ``"ti"`` terms, fitting itself and choosing its own
smoothing parameters.

**Nothing here is a new numeric formula.** :func:`assemble_model_design` is
the ``ModelSpec``-driven generalisation of
:func:`~polaris_re.analytics.gam_multiterm_conformance.assemble_multiterm_design`'s
column/penalty-padding logic (that module now calls this one — the work
order's step 1, "extract the shared assembly so the harness and the engine
cannot drift"). :func:`fit_polaris_gam` composes three already-independently-
verified pieces unchanged: the basis producers
(:func:`~polaris_re.analytics.gam_stage_a.build_python_cr_term` /
:func:`~polaris_re.analytics.gam_stage_a.build_python_ti_term` — ADR-194,
ADR-200, ADR-205), the continuous smoothing-parameter search
(:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous` —
ADR-199), and the general penalized fitter it already calls internally
(:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` — ADR-195).

**What this module does NOT do.** ``select = TRUE`` (slice 7) is not built
— :func:`assemble_model_design` raises on any basis it does not recognise
rather than silently skipping a term. ``"sz"`` terms (slice 6b,
``docs/PLAN_mgcv_parity_engine.md``) ARE built by :func:`assemble_model_design`
via :func:`~polaris_re.analytics.gam_stage_a.build_python_sz_term` (ADR-215),
but :func:`fit_polaris_gam`'s own outer search
(:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`)
has never been exercised on an ``sz``-shaped block structure (one smoothing
parameter per factor level) — slice 6b's own scope is the fixed-``sp``
assembly and fit, not extending the free-``sp`` search to this shape. It
does not touch ``experience_gam_penalized`` or ``experience_gam``
(PLAN Anchor 7) — those stay the production tensor-MI surface until a caller
is explicitly moved, which this module does not do on its own. It does not
compute an unconditional (Kass-Steffey / Wood-Pya-Saefken) covariance — the
work order's own §3 scope is ``eta``, selected ``log10(sp)``, and edf, not
uncertainty.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import (
    Family,
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_reml_optimize import select_lambdas_continuous
from polaris_re.analytics.gam_stage_a import (
    TermExtract,
    build_python_cr_term,
    build_python_sz_term,
    build_python_ti_term,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "ModelDesign",
    "PolarisGAMFit",
    "TermBlock",
    "assemble_model_design",
    "fit_polaris_gam",
    "resolve_family",
]

_FAMILY_LINKS: dict[tuple[str, str], Callable[[], Family]] = {
    ("poisson", "log"): poisson_log,
    ("quasipoisson", "log"): quasipoisson_log,
    ("binomial", "logit"): binomial_logit,
    ("binomial", "cloglog"): binomial_cloglog,
}
"""Every ``(family, link)`` combination slice 3 (ADR-195) built and verified
against ``mgcv``. ``ModelSpec.family``/``.link`` are free-text strings (Anchor
3), but this module only ever resolves them to one of these — deliberately no
"unknown but assume Poisson-shaped" fallback, since a silently-wrong family
would fail nowhere near where the mistake was made."""


PRODUCTION_LOG10_BOUNDS = (-2.0, 12.0)
""":func:`fit_polaris_gam`'s own default search domain for
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous` —
deliberately wider than that module's own
``DEFAULT_LOG10_BOUNDS = (-2.0, 8.0)``.

**Measured, not guessed (PR #212 review [P1]):** on the target formula's own
three-term `cr`+`by`+`ti` structure, `mgcv`'s own free-sp REML selection
reaches `log10(sp) ~ 9.87` on the by-term's block —
outside `DEFAULT_LOG10_BOUNDS` entirely. A caller fitting this exact model
shape with the module default would have its search silently clamped at 8,
short of where the criterion's own minimum lies (or at least short of where
`mgcv`'s optimiser lands — see ADR-208 for what that comparison does and
does not establish). `gam_model_conformance._SEARCH_BOUNDS = (-2, 11)`
already widened the comparator's own search to reach this region;
this constant gives `fit_polaris_gam` itself the same headroom (plus a
margin) by default, rather than leaving every caller to discover the clamp
independently. `select_lambdas_continuous`'s own default is untouched
(PLAN Anchor 7 — that module and its constant are ADR-199's tier-3-verified
artifact)."""


def resolve_family(family: str, link: str) -> Family:
    """The ``(family, link)`` -> :class:`Family` lookup every ``ModelSpec``-driven
    fit needs. Raises rather than guessing on an unrecognised pair."""
    try:
        return _FAMILY_LINKS[(family, link)]()
    except KeyError:
        raise PolarisValidationError(
            f"resolve_family: no Family/Link constructor for family={family!r}, "
            f"link={link!r}. Supported combinations: "
            f"{sorted(_FAMILY_LINKS)}."
        ) from None


class TermBlock(TypedDict):
    """One term's column span in the assembled design, and how many
    independently-scaled penalty blocks it contributed (1 for ``cr``, 2 for
    ``ti`` — ADR-205 decision 2)."""

    label: str
    start: int
    end: int
    n_penalties: int


class ModelDesign(TypedDict):
    """The assembled design and every independently-scaled penalty block, in
    ``ModelSpec.terms`` order — the same convention
    :class:`~polaris_re.analytics.gam_multiterm_conformance.MultiTermDesign`
    already used, generalised from exactly three fixed terms to any
    ``ModelSpec`` built from ``"cr"``/``"ti"`` terms."""

    x: np.ndarray
    penalty_blocks: tuple[np.ndarray, ...]
    term_blocks: tuple[TermBlock, ...]


def _build_term_extract(term: TermSpec, data: Mapping[str, np.ndarray]) -> TermExtract:
    if term.basis == "cr":
        x = np.asarray(data[term.variables[0]], dtype=np.float64)
        by = None if term.by is None else np.asarray(data[term.by], dtype=np.float64)
        return build_python_cr_term(x, term, by=by)
    if term.basis == "ti":
        x1 = np.asarray(data[term.variables[0]], dtype=np.float64)
        x2 = np.asarray(data[term.variables[1]], dtype=np.float64)
        return build_python_ti_term(x1, x2, term)
    if term.basis == "sz":
        # TermSpec's own documented order for basis="sz": (factor_name, smoothed_name).
        factor_name, smoothed_name = term.variables
        x = np.asarray(data[smoothed_name], dtype=np.float64)
        group = np.asarray(data[factor_name], dtype=np.int64)
        if term.n_levels is None:
            raise PolarisValidationError(
                f"assemble_model_design: TermSpec {term.label!r} is basis='sz' "
                "with n_levels=None — the factor-level count is an input "
                "(Anchor 4), not derived from a sample's own observed group "
                "codes. Set TermSpec.n_levels explicitly."
            )
        return build_python_sz_term(x, group, term.n_levels, term)
    raise PolarisValidationError(
        f"assemble_model_design: TermSpec {term.label!r} has basis={term.basis!r}, "
        "which PolarisGAM does not build yet — only 'cr', 'ti' and 'sz' are "
        "wired. 'raw' supplies its own design/penalty directly and has no "
        "recipe for this function to build from."
    )


def assemble_model_design(model: ModelSpec, data: Mapping[str, np.ndarray]) -> ModelDesign:
    """Build the full design and every penalty block from a ``ModelSpec`` and
    the covariate data it names — never from ``mgcv``'s own ``X``/``coef``
    (there is none in ``data`` to read).

    An unpenalized intercept column comes first (``mgcv``'s own convention
    for a formula with no explicit parametric terms), then each term's own
    columns in ``model.terms`` order. Each penalty block is padded with zeros
    outside its own term's columns — the same convention
    :class:`~polaris_re.analytics.experience_mgcv_conformance.DesignExport`
    and
    :func:`~polaris_re.analytics.gam_multiterm_conformance.assemble_multiterm_design`
    (now built on this function) already use.

    Args:
        model: every term must be ``basis="cr"``, ``basis="ti"`` or
            ``basis="sz"`` — see :func:`_build_term_extract`.
        data: covariate arrays keyed by name, e.g. ``{"AttdAge": ..., "PolYear":
            ..., "StudyYear_C": ...}`` — a numeric-``by`` term reads its scaling
            variable from here via ``term.by``, a ``ti`` term reads both of
            ``term.variables`` from here, and an ``sz`` term reads its factor's
            0-indexed level codes (``term.variables[0]``) and its smoothed
            margin's values (``term.variables[1]``) from here.

    Raises:
        PolarisValidationError: if a term names a basis this function does not
            build, or if ``data`` is missing a variable a term names.
    """
    extracts = [(term, _build_term_extract(term, data)) for term in model.terms]
    n = extracts[0][1].design.shape[0]

    intercept = np.ones((n, 1), dtype=np.float64)
    columns = [intercept]
    term_blocks: list[TermBlock] = []
    raw_blocks: list[tuple[int, np.ndarray]] = []
    col = 1
    for term, extract in extracts:
        width = extract.design.shape[1]
        columns.append(extract.design)
        term_blocks.append(
            TermBlock(label=term.label, start=col, end=col + width, n_penalties=len(extract.s))
        )
        raw_blocks.extend((col, block) for block in extract.s)
        col += width

    x = np.hstack(columns)
    p_total = x.shape[1]

    def _pad(start: int, block: np.ndarray) -> np.ndarray:
        width = block.shape[0]
        padded = np.zeros((p_total, p_total), dtype=np.float64)
        padded[start : start + width, start : start + width] = block
        return padded

    penalty_blocks = tuple(_pad(start, block) for start, block in raw_blocks)
    return ModelDesign(x=x, penalty_blocks=penalty_blocks, term_blocks=tuple(term_blocks))


def _per_term_edf(
    design: ModelDesign,
    family: Family,
    eta: np.ndarray,
    mu: np.ndarray,
    penalty: np.ndarray,
    weights: np.ndarray | None,
) -> dict[str, float]:
    """``tr(F)`` restricted to each term's own columns, at the final IRLS
    working weights — the same identity
    ``experience_gam_penalized.PenalizedTensorMIModel.fit``'s ``edf_tensor``/
    ``edf_factors`` split uses (``f_diag[:n_tensor].sum()`` etc.), generalised
    from two fixed blocks to any number of named terms.

    Deliberately excludes the intercept column, matching ``mgcv``'s own
    ``summary.gam``'s per-smooth-term ``edf`` column — a reader summing this
    dict's values gets the *smooth* terms' total, not
    :attr:`PolarisGAMFit.edf_total` (which also counts the intercept and would
    be off by approximately 1).
    """
    x = design["x"]
    n = mu.shape[0]
    w = np.ones(n, dtype=np.float64) if weights is None else weights
    deta_dmu = family.link.mu_eta(eta)
    irls_weights = w * deta_dmu**2 / family.variance(mu)
    xtwx = x.T @ (irls_weights[:, None] * x)
    hat = np.linalg.solve(xtwx + penalty, xtwx)
    diag = np.diag(hat)
    return {tb["label"]: float(diag[tb["start"] : tb["end"]].sum()) for tb in design["term_blocks"]}


@dataclass(frozen=True)
class PolarisGAMFit:
    """A ``ModelSpec`` fitted to data, with its own selected smoothing
    parameters. No coefficient is ever the object of a parity comparison
    (Anchor 2) — this dataclass carries ``coef`` because a caller needs it to
    predict, not because it is meant to be compared against ``mgcv``'s."""

    model: ModelSpec
    design: ModelDesign
    coef: np.ndarray
    eta: np.ndarray
    log_lambda: np.ndarray
    """``log10(lambda)``, one entry per penalty block, in
    ``design["penalty_blocks"]`` order (:class:`TermBlock` order, and within a
    term, its penalties in the order its basis producer returned them)."""
    lambda_: np.ndarray
    edf_total: float
    """``tr(F)`` over the WHOLE design, intercept included — Anchor 4's EDF
    definition, unchanged from
    :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`."""
    edf_per_term: dict[str, float]
    """See :func:`_per_term_edf` — excludes the intercept, matching ``mgcv``'s
    own per-smooth-term convention."""
    reml_score: float
    converged: bool
    n_function_evals: int
    n_rejected: int
    at_bound: bool


def fit_polaris_gam(
    model: ModelSpec,
    data: Mapping[str, np.ndarray],
    y: np.ndarray,
    *,
    gamma: float = 1.0,
    x0: np.ndarray | None = None,
    bounds: tuple[float, float] = PRODUCTION_LOG10_BOUNDS,
    gtol: float = 1.0e-8,
    maxiter: int = 200,
) -> PolarisGAMFit:
    """Fit ``model`` to ``data``/``y``, selecting every smoothing parameter by
    continuous REML (:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`).

    Args:
        model: family/link/terms/weights/offset (Anchor 5 — both may be set
            at once, and neither is inferred from the other).
        data: covariate arrays keyed by name, read by
            :func:`assemble_model_design`, plus (if named on ``model``) the
            weights and/or offset columns.
        y: the response, ``(n,)`` — not part of ``ModelSpec`` (which
            describes the model, not one particular fit's data), so it is a
            required argument here rather than another ``data`` lookup by
            convention.
        gamma, x0, bounds, gtol, maxiter: passed through to
            :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
            unchanged, except ``bounds`` defaults to
            :data:`PRODUCTION_LOG10_BOUNDS` rather than that module's own
            (narrower) default — see its docstring.

    Raises:
        PolarisValidationError: propagated from :func:`assemble_model_design`
            or :func:`resolve_family`.
        PolarisComputationError: propagated from
            :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
            if every trial smoothing-parameter point is rejected; or raised
            here if the search's own selection sits AT a bound of ``bounds``
            (PR #212 review [P1]) — a clamped smoothing parameter is not the
            criterion's minimum, and returning it silently as though it were
            would misreport `edf`/`eta` downstream without any signal that
            the search domain, not the criterion, was the limiting factor.
            Widen ``bounds`` and refit rather than reading the clamped value.
    """
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    weights = (
        None
        if model.weights_column is None
        else np.asarray(data[model.weights_column], dtype=np.float64)
    )
    offset = (
        None
        if model.offset_column is None
        else np.asarray(data[model.offset_column], dtype=np.float64)
    )
    y = np.asarray(y, dtype=np.float64)

    selection = select_lambdas_continuous(
        y,
        design["x"],
        family,
        design["penalty_blocks"],
        offset=offset,
        weights=weights,
        gamma=gamma,
        x0=x0,
        bounds=bounds,
        gtol=gtol,
        maxiter=maxiter,
    )
    if selection.at_bound:
        # One log_lambda entry per penalty BLOCK; a term with more than one
        # penalty (ti carries two, ADR-205) owns a run of consecutive entries.
        block_labels = [
            tb["label"] for tb in design["term_blocks"] for _ in range(tb["n_penalties"])
        ]
        at_bound_blocks = [
            (label, float(log_lam))
            for label, log_lam in zip(block_labels, selection.log_lambda, strict=True)
            if np.isclose(log_lam, bounds[0]) or np.isclose(log_lam, bounds[1])
        ]
        raise PolarisComputationError(
            f"fit_polaris_gam: the smoothing-parameter search selected log10(lambda) "
            f"at a bound of {bounds} for {at_bound_blocks or 'at least one penalty block'} "
            "-- this is the search domain's edge, not necessarily the REML criterion's "
            "minimum. Widen `bounds` and refit rather than reading this selection."
        )

    eta = (np.zeros_like(y) if offset is None else offset) + design["x"] @ selection.coef
    mu = family.link.linkinv(eta)
    penalty = np.zeros_like(design["penalty_blocks"][0])
    for log_lam, block in zip(selection.log_lambda, design["penalty_blocks"], strict=True):
        penalty = penalty + (10.0**log_lam) * block
    edf_per_term = _per_term_edf(design, family, eta, mu, penalty, weights)

    return PolarisGAMFit(
        model=model,
        design=design,
        coef=selection.coef,
        eta=eta,
        log_lambda=selection.log_lambda,
        lambda_=selection.lambda_,
        edf_total=selection.edf_total,
        edf_per_term=edf_per_term,
        reml_score=selection.reml_score,
        converged=selection.converged,
        n_function_evals=selection.n_function_evals,
        n_rejected=selection.n_rejected,
        at_bound=selection.at_bound,
    )
