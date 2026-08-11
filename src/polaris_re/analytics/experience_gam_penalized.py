"""Penalized tensor mortality-improvement surface — P-splines with REML-selected λ.

Slices 1-4 of ``docs/PLAN_penalized_mi_surface.md``. :class:`PenalizedTensorMIModel`
fits at a **caller-supplied λ**; :func:`select_lambdas_reml` chooses one by REML over
a deterministic grid. They are separate entry points because they were built as
separate slices — an optimiser wrapped around an unverified fitter is two hard
things at once — and keeping them separate is what lets the fixed-λ limits stay
testable in isolation (ADR-185, ADR-186).

**Use** :func:`fit_reml` **to get a selected surface.** It is the only entry point
that records where λ came from, and ``unconditional=True`` there is the only way to
get an interval that does not condition on it (ADR-188).

**What this is for.** ``TensorMIModel`` spends the same number of calendar
parameters everywhere regardless of how much information a region carries, which
ADR-184 measured: a 3.13-point swing in fitted MI at age 45 against 0.46 at 85, on a
truth that is exactly flat, because deaths at 45 are ~24x scarcer. A roughness
penalty lets *effective* degrees of freedom fall where the data are thin without
anyone choosing a single global ``df`` that has to suit both ends.

**What it is not for: fixing age 45 on ILEC.** That climb survives removing a whole
polynomial order (ADR-184 amendment 2), so it is not a flexibility artifact and a
better-principled flexibility control is not its remedy. PLAN §1 rules the framing
out; this docstring repeats it because module docstrings are where such things get
quietly re-invented.

## Two bases, and why there have to be two

``TensorMIModel`` builds ``1 + bs(age) + bs(year) + interaction`` — patsy's
main-effects form. A difference penalty is not natural there: it penalises
*marginal* coefficients, which live in the full Kronecker form ``B_age ⊗ B_year``.
So this module builds the Kronecker design. That much the plan anticipated.

What it did not anticipate is that **patsy cannot build a P-spline basis at all**.
A difference penalty's null space is "coefficients linear in index", and that is a
linear *function* only when the Greville abscissae are equally spaced — which needs
uniform knots **and** no boundary clamping. ``patsy.bs`` always clamps, repeating
boundary knots ``degree + 1`` times, and uniform interior knots do not rescue it.
Measured step spread for index-linear coefficients: **5.6e-01** on a patsy basis
against **8.9e-16** on an extended uniform sequence from ``scipy``.

Hence two schemes, and the distinction is load-bearing rather than cosmetic:

- ``knots="uniform"`` (**default**) — the real P-spline. The penalty behaves: at
  large λ_year the calendar margin collapses to a straight line and fitted MI
  becomes constant in time.
- ``knots="clamped"`` — patsy-compatible, and **oracle testing only**. Its column
  space matches ``TensorMIModel``'s exactly, so λ=0 reproduces that model's fitted
  surface, dispersion and ``edf``. The penalty misbehaves in this scheme; never fit
  production surfaces with it.

**Anchor 1 as amended (ADR-185):** λ=0 reproduces ``TensorMIModel`` exactly *in the
clamped scheme*, which is what verifies the fitting machinery — IRLS, dispersion,
``edf``, covariance — against an already-tested oracle. It cannot also hold in the
production scheme, because using a different basis is the entire point of the
rebuild. Asserted on the fitted surface and never on coefficients: the two
parameterisations are not comparable coefficient-wise even when their spans agree.
"""

from dataclasses import dataclass, field, replace
from typing import NamedTuple

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import (
    _CANDIDATE_FACTORS,
    AMOUNT_MEASURES,
    COUNT_MEASURES,
    MISurface,
    _assert_static_base,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "COARSE_STEP",
    "KS_LOG_STEP",
    "LAMBDA_LOG10_BOUNDS",
    "REFINE_STEP",
    "DesignContext",
    "LambdaSelection",
    "PenalizedMIFit",
    "PenalizedTensorMIModel",
    "SmoothingUncertainty",
    "difference_penalty",
    "fit_reml",
    "lambda_is_at_bound",
    "reml_score",
    "select_lambdas_reml",
    "smoothing_uncertainty",
    "tensor_penalties",
]

_DEFAULT_DEGREE = 3
_DEFAULT_PENALTY_ORDER = 2
"""Second differences. The null space is then the linear functions, so an infinite
penalty shrinks the calendar margin to a straight line — which is exactly the
``df == degree == 1`` fit ADR-184 amendment 1 measured, giving the two
implementations a closed form to check each other against."""

_MAX_IRLS_ITER = 100
_IRLS_TOL = 1e-10


def difference_penalty(n_coef: int, order: int = _DEFAULT_PENALTY_ORDER) -> np.ndarray:
    """``DᵀD`` for the ``order``-th difference operator on ``n_coef`` coefficients.

    The Eilers-Marx construction: rather than penalising an integrated squared
    derivative analytically, penalise differences between adjacent B-spline
    coefficients. For a basis on equally-spaced knots the two are close, and the
    difference form is banded, exactly representable and trivial to build.

    Its **null space is what the penalty cannot see**: with ``order=2`` that is the
    linear functions, so no amount of penalty removes a straight-line trend. That
    property is load-bearing — an MI surface shrunk to "no improvement at all" would
    be a modelling artifact, whereas one shrunk to "a constant rate of improvement"
    is a defensible limit.
    """
    if n_coef <= order:
        raise PolarisValidationError(
            f"A difference penalty of order {order} needs more than {order} "
            f"coefficients, got {n_coef}. Either raise the basis dimension or lower "
            f"the penalty order — at n_coef == order the penalty is identically zero."
        )
    d = np.diff(np.eye(n_coef, dtype=np.float64), n=order, axis=0)
    return d.T @ d


def tensor_penalties(
    n_age: int, n_year: int, order: int = _DEFAULT_PENALTY_ORDER
) -> tuple[np.ndarray, np.ndarray]:
    """Marginal penalties lifted to the tensor coefficient vector.

    Coefficients are ordered **age-major** — index ``i * n_year + j`` for age basis
    ``i`` and year basis ``j`` — matching the ``einsum(...).reshape`` in
    :meth:`PenalizedTensorMIModel._tensor_block`. So the age penalty is
    ``Dᵀ D ⊗ I`` and the year penalty ``I ⊗ Dᵀ D``, and swapping them silently
    penalises the wrong margin while still running, which is why the ordering is
    stated here and asserted in the tests.
    """
    s_age = np.kron(difference_penalty(n_age, order), np.eye(n_year, dtype=np.float64))
    s_year = np.kron(np.eye(n_age, dtype=np.float64), difference_penalty(n_year, order))
    return s_age, s_year


@dataclass(frozen=True)
class DesignContext:
    """The assembled pieces of a fit, so λ selection need not rebuild them.

    Public because :func:`select_lambdas_reml` consumes it across a module boundary;
    an earlier revision reached into four private attributes instead, three of which
    were never initialised.
    """

    design: np.ndarray
    offset: np.ndarray
    deaths: np.ndarray
    n_tensor: int
    s_age: np.ndarray
    s_year: np.ndarray


@dataclass(frozen=True)
class PenalizedMIFit:
    """A fitted penalized surface.

    ``reml_score`` and ``lambda_grid_step`` are populated by :func:`fit_reml`; a
    fixed-λ fit leaves both ``None``, which is how a reader tells a selected surface
    from a hand-set one.

    **Not** :func:`select_lambdas_reml` — it returns a :class:`LambdaSelection` and
    nothing else, so a caller who follows it with a hand-built model gets the field
    defaults and both come back ``None``. That two-step dance *is* the defect PR #188
    found, and an earlier revision of this docstring named it as the source of the
    metadata (PR #188 review round 2 [P1]). Naming the wrong entry point once a right
    one exists is worse than the original vagueness was.

    (Slice 4 widened that return from a bare 3-tuple to :class:`LambdaSelection`, which
    changes nothing about the point above: the selection object still has to be *given*
    to a fit, and :func:`fit_reml` is still the only thing that does it.)"""

    coef: np.ndarray
    cov: np.ndarray
    """The covariance the bands are formed from.

    Wood's Bayesian ``Vb = (XᵀWX + S)⁻¹ φ`` when :attr:`band_is_unconditional` is
    ``False``, and ``Vb + J V_rho Jᵀ`` — the Kass-Steffey correction — when it is
    ``True``. **Read that flag before quoting a coverage rate**: the two are
    different intervals and slice 3 measured the first at 87.1% against a nominal
    95% on a truth the basis represents exactly."""

    edf_total: float
    """``tr(F)`` for ``F = (XᵀWX + S)⁻¹ XᵀWX``, over every column."""

    edf_tensor: float
    """**The headline.** ``tr(F)`` restricted to the tensor block — the per-term EDF
    ``mgcv`` reports for a smooth. Unlike the shrinkages it **closes**:
    ``edf_tensor + edf_factors == edf_total`` exactly.

    **The mgcv-consistency is VERIFIED** (2026-08-10, ADR-189 amendment 1): on a shared
    design with shared penalties at fixed λ, ``edf_total`` and ``edf_tensor`` agree with
    ``mgcv`` to 7.2e-13 and ``edf_factors`` exactly, over six cells. It was *adopted, not
    verified* from slice 2 until then, on the grounds that nothing in this container could
    compare against mgcv — true of the container, false of the project: CI can, in a
    digest-pinned image."""

    edf_factors: float
    """``tr(F)`` over the unpenalized factor columns. Present so the addition above
    is checkable rather than asserted."""

    shrinkage_age: float
    """Dimensions the age penalty **removed**: ``tr(F | λ_age = 0) - tr(F)``.

    **Removed, not spent** — and the wording is the point. Slice 1 called the
    per-margin quantities ``edf_age`` / ``edf_year``, which reads as "degrees of
    freedom this margin is using" and invites adding them together. They overlap and
    do not sum to anything (PR #187 review). A shrinkage is unaddable on its face."""

    shrinkage_year: float
    """Dimensions the calendar penalty removed. See :attr:`shrinkage_age`."""

    dispersion: float
    lambda_age: float
    lambda_year: float
    n_cells: int
    n_coef: int
    n_tensor: int
    """Columns in the Kronecker tensor block, i.e. where the factor block starts.

    Public because :meth:`improvement_surface` needs it to pad the grid design out
    to ``n_coef``: the MI contrast differences out every calendar-invariant term, so
    the factor columns are supplied as zeros rather than at their reference level.
    Zeros are not a shortcut here — they are what makes the factor block contribute
    nothing to the *variance* either, which is the same cancellation the level
    argument relies on."""

    observed_ages: tuple[int, int]
    observed_years: tuple[int, int]
    factors: tuple[str, ...]
    n_iter: int

    reml_score: float | None = None
    """Laplace-approximate REML at the fitted λ, or ``None`` for a fixed-λ fit."""

    band_is_unconditional: bool = False
    """Does :attr:`cov` carry λ's own sampling variance?

    ``False`` is Wood's ``Vb``, which is **conditional on λ** — it claims a coverage
    rate *given* the smoothing parameters, and ADR-187 finding 2 established that the
    λ it is given is one draw from a wide distribution. ``True`` adds the
    Kass-Steffey term (see :func:`smoothing_uncertainty`).

    Reported rather than inferred because slice 6 must print which interval it drew
    and PLAN Anchor 7 forbids calling either one a 95% band until select-per-replicate
    coverage says so."""

    gamma: float = 1.0
    """Wood's EDF-cost multiplier used during selection; 1.0 for a fixed-λ fit.

    Carried on the fit because a λ selected under gamma != 1 is not comparable with one
    selected under gamma=1, and a report that shows the λ without the gamma invites exactly
    that comparison."""

    n_rejected_points: int | None = None
    """Grid points :func:`select_lambdas_reml` scored ``+inf`` because their own
    penalized IRLS did not converge, or ``None`` for a fixed-λ fit.

    **Present because a search that silently discarded half its grid is a different
    object from one that discarded nothing.** ADR-187 finding 5 is the reason the
    rejection exists at all; this field is the reason the rejection cannot hide."""

    n_evaluated_points: int | None = None
    """Grid points scored in total, rejections included. The denominator for
    :attr:`n_rejected_points` — without it the count is unreadable."""

    lambda_grid_step: float | None = None
    """log10 resolution of the grid the λ came from, or ``None`` if λ was supplied.

    Recorded because it is the exact size of the determinism/accuracy trade Anchor 3
    forced: a grid is reproducible **by construction** — there is no optimiser whose
    last digits can drift — and the price is that λ is known only to this
    resolution."""

    _grid_design: object | None = field(default=None, repr=False)
    """Callable ``(ages, years) -> tensor design``, bound to the fitted knots.

    A closure rather than the raw knot info, because rebuilding the basis needs the
    model's ``k`` and boundary handling as well. Held privately: callers want
    :meth:`improvement_surface`, not a design matrix."""

    def improvement_surface(
        self,
        ages: np.ndarray | None = None,
        years: np.ndarray | None = None,
        confidence_level: float = 0.95,
    ) -> "MISurface":
        """Extract ``MI_x(y)`` with a Bayesian band, **through the shared band layer**.

        The band is :func:`~polaris_re.analytics.experience_gam.mi_surface_from_design`
        — the same function the frequentist tensor surface and the RRGP posterior
        surface call, with ``cov`` here being Wood's ``Vb = (XᵀWX + S)⁻¹φ``. That
        reuse is Design Anchor 2, and it is the anchor's *point*: a band is
        ``√(cᵀVc)`` on a contrast row and does not care how ``V`` was formed.

        **Anchor 2 held for the covariance and could not hold for the design.**
        The extractor's design *rebuild* goes through ``patsy.build_design_matrices``,
        and slice 1 established that patsy cannot express this basis at all — it
        always clamps boundary knots, which destroys the difference penalty's null
        space. So the grid design is rebuilt here from the fitted uniform knots and
        handed to the shared layer. That is a **basis** incompatibility, not a
        covariance one; the anchor's stop-signal ("if this layer needs modifying, the
        covariance swap is wrong") is aimed at the covariance and is not triggered.
        ADR-187 records the distinction rather than letting the anchor read as
        satisfied or as violated, since it is neither.
        """
        from polaris_re.analytics.experience_gam import mi_grid_axes, mi_surface_from_design

        if self._grid_design is None:  # pragma: no cover - fit() always binds it
            raise PolarisComputationError("This fit carries no design builder.")
        ages, years = mi_grid_axes(ages, years, self.observed_ages, self.observed_years)
        tensor = np.asarray(self._grid_design(ages, years), dtype=np.float64)  # type: ignore[operator]
        pad = self.n_coef - self.n_tensor
        design = (
            np.hstack([tensor, np.zeros((tensor.shape[0], pad), dtype=np.float64)])
            if pad
            else tensor
        )
        return mi_surface_from_design(design, self.coef, self.cov, ages, years, confidence_level)


class PenalizedTensorMIModel:
    """Tensor MI surface with Eilers-Marx difference penalties, at fixed λ.

    Args:
        cells:       Grouped cells in the canonical contract, as ``TensorMIModel``.
        basis:       ``'count'`` or ``'amount'``.
        k_age:       Age basis dimension. **An upper bound, not a tuning knob**
                     (Anchor 5): choose it generously, then confirm ``edf_age`` sits
                     well below it. HMD's 30 years support 10-15; ILEC's **eight
                     distinct calendar years do not support 10** on the year margin.
        k_year:      Calendar basis dimension, same rule and the one that bites.
        penalty_order: Difference order. 2 leaves linear trends unpenalised.
        lambda_age / lambda_year: Fixed smoothing parameters. ``0.0`` reproduces
                     ``TensorMIModel`` exactly (Anchor 1).
    """

    def __init__(
        self,
        cells: pl.DataFrame,
        *,
        basis: str = "count",
        k_age: int = 10,
        k_year: int = 8,
        degree: int = _DEFAULT_DEGREE,
        penalty_order: int = _DEFAULT_PENALTY_ORDER,
        knots: str = "uniform",
        lambda_age: float = 0.0,
        lambda_year: float = 0.0,
        allow_generational_base: bool = False,
    ) -> None:
        if basis not in {"count", "amount"}:
            raise PolarisValidationError(f"basis must be 'count' or 'amount', got {basis!r}.")
        if lambda_age < 0.0 or lambda_year < 0.0:
            raise PolarisValidationError("Smoothing parameters must be non-negative.")
        if knots not in {"uniform", "clamped"}:
            raise PolarisValidationError(
                f"knots must be 'uniform' (P-spline) or 'clamped' (patsy-compatible, "
                f"oracle-testing only), got {knots!r}."
            )
        # The Kronecker form uses FULL marginal bases (intercept included), so the
        # floor is degree + 1 rather than TensorMIModel's degree — one higher, and
        # worth its own message because reusing validate_spline_margin here would
        # report the wrong parameter name and the wrong number.
        for name, k in (("k_age", k_age), ("k_year", k_year)):
            if k < degree + 1:
                raise PolarisValidationError(
                    f"{name}={k} is below the full-basis minimum of {degree + 1} for "
                    f"degree={degree}. This model uses full marginal bases (intercept "
                    f"included), so its floor is one higher than TensorMIModel's df "
                    f"floor — {name}={degree + 1} is the patsy df={degree} basis plus "
                    f"its intercept, spanning the same space."
                )

        exposure_col, deaths_col = COUNT_MEASURES if basis == "count" else AMOUNT_MEASURES
        required = {"attained_age", "calendar_year", "q_base", exposure_col, deaths_col}
        missing = required - set(cells.columns)
        if missing:
            raise PolarisValidationError(
                f"Grouped cells missing columns for basis={basis!r}: {missing}"
            )
        if cells.height == 0:
            raise PolarisValidationError("Grouped cells DataFrame is empty.")
        if cells["calendar_year"].n_unique() < 2:
            raise PolarisValidationError(
                "PenalizedTensorMIModel needs >1 distinct calendar_year to identify a trend."
            )
        q_base = cells["q_base"].to_numpy().astype(np.float64)
        if np.any(q_base <= 0.0) or np.any(q_base > 1.0):
            raise PolarisValidationError("q_base must lie in (0, 1] for every cell.")
        if not allow_generational_base:
            _assert_static_base(cells)

        self.cells = cells
        self.basis = basis
        self.exposure_col = exposure_col
        self.deaths_col = deaths_col
        self.k_age = k_age
        self.k_year = k_year
        self.degree = degree
        self.penalty_order = penalty_order
        self.knots = knots
        self.design_context: DesignContext | None = None
        self.lambda_age = float(lambda_age)
        self.lambda_year = float(lambda_year)

    # -- design ------------------------------------------------------------------

    def _basis(
        self,
        x: np.ndarray,
        k: int,
        bounds: tuple[float, float],
        fitted_info: object = None,
    ) -> tuple[np.ndarray, object]:
        """Marginal B-spline basis, in one of two knot schemes.

        ``"uniform"`` — the **P-spline** basis (Eilers-Marx): B-splines on a knot
        sequence extended uniformly *past* both boundaries. This is not a stylistic
        choice. A difference penalty's null space is "coefficients linear in index",
        and that corresponds to a linear *function* only when the Greville abscissae
        are equally spaced — which requires uniform knots **and** no boundary
        clamping. ``patsy.bs`` always clamps (repeating boundary knots
        ``degree + 1`` times), so a difference penalty over a patsy basis does not
        annihilate linear trends: measured residual 5.6e-01 against 8.9e-16 here.
        **patsy cannot build a P-spline basis**, which is why this reaches for scipy.

        ``"clamped"`` — patsy-compatible: quantile interior knots, clamped
        boundaries. The penalty misbehaves in this scheme and it exists **only** so
        the λ=0 oracle test can match ``TensorMIModel``'s column space exactly
        (Anchor 1, as amended). Not for production fitting.
        """
        from scipy.interpolate import BSpline

        lo, hi = bounds
        if self.knots == "clamped":
            from patsy import build_design_matrices, dmatrix

            if fitted_info is not None:
                # Reuse the FITTED knots. Without this, patsy recomputes quantile
                # knots from whatever vector it is handed — so a prediction grid
                # would silently get a DIFFERENT basis than the fit. Invisible on a
                # complete rectangle (grid quantiles == data quantiles) and wrong by
                # 3.2e-2 in eta the moment coverage is ragged, which is what real
                # ILEC is (PR #187 review [P1]).
                (design,) = build_design_matrices(
                    [fitted_info], {"v": np.asarray(x, dtype=np.float64)}
                )
                return np.asarray(design, dtype=np.float64), fitted_info
            spec = f"bs(v, df={k}, degree={self.degree}, include_intercept=True) - 1"
            design = dmatrix(spec, {"v": np.asarray(x, dtype=np.float64)}, return_type="dataframe")
            return np.asarray(design, dtype=np.float64), design.design_info

        n_interval = k - self.degree
        step = (hi - lo) / n_interval
        knots = lo + step * np.arange(-self.degree, n_interval + self.degree + 1, dtype=np.float64)
        basis = BSpline.design_matrix(
            np.asarray(x, dtype=np.float64), knots, self.degree, extrapolate=True
        ).toarray()
        return np.asarray(basis, dtype=np.float64), knots

    def _bounds(self, frame: pl.DataFrame) -> tuple[tuple[float, float], tuple[float, float]]:
        age = frame["attained_age"].to_numpy().astype(np.float64)
        year = frame["calendar_year"].to_numpy().astype(np.float64)
        return (float(age.min()), float(age.max())), (float(year.min()), float(year.max()))

    def _build(self, frame: pl.DataFrame) -> tuple[np.ndarray, object]:
        """Return the tensor design and a builder that reproduces it on a fresh grid."""
        age_bounds, year_bounds = self._bounds(frame)
        b_age, knots_age = self._basis(
            frame["attained_age"].to_numpy().astype(np.float64), self.k_age, age_bounds
        )
        b_year, knots_year = self._basis(
            frame["calendar_year"].to_numpy().astype(np.float64), self.k_year, year_bounds
        )
        return self._tensor_block(b_age, b_year), (age_bounds, year_bounds, knots_age, knots_year)

    @staticmethod
    def _tensor_block(b_age: np.ndarray, b_year: np.ndarray) -> np.ndarray:
        """Row-wise Kronecker product, **age-major** — see :func:`tensor_penalties`."""
        n, ka = b_age.shape
        ky = b_year.shape[1]
        return np.einsum("ni,nj->nij", b_age, b_year).reshape(n, ka * ky)

    def design_on_grid(self, info: object, ages: np.ndarray, years: np.ndarray) -> np.ndarray:
        """Rebuild the tensor design on an (age x year) grid using the fitted knots."""
        age_bounds, year_bounds, fitted_age, fitted_year = info  # type: ignore[misc]
        grid_age = np.repeat(np.asarray(ages, dtype=np.float64), len(years))
        grid_year = np.tile(np.asarray(years, dtype=np.float64), len(ages))
        b_age, _ = self._basis(grid_age, self.k_age, age_bounds, fitted_age)
        b_year, _ = self._basis(grid_year, self.k_year, year_bounds, fitted_year)
        return self._tensor_block(b_age, b_year)

    # -- fit ---------------------------------------------------------------------

    def fit(
        self,
        *,
        selection: "LambdaSelection | None" = None,
        lambda_grid_step: float | None = None,
        gamma: float = 1.0,
    ) -> PenalizedMIFit:
        """Penalized IRLS at the fixed λ supplied to the constructor.

        ``selection`` carries the provenance of a λ that came from
        :func:`select_lambdas_reml` — its REML score and how much of the grid it had
        to reject. Left ``None`` by a hand-set fit, which is how a reader tells the
        two apart (see :class:`PenalizedMIFit`).
        """
        frame = self.cells
        factors = tuple(
            f for f in _CANDIDATE_FACTORS if f in frame.columns and frame[f].n_unique() > 1
        )

        x_tensor, info = self._build(frame)
        blocks = [x_tensor]
        if factors:
            from patsy import dmatrix

            # The Kronecker block already spans the constant (both marginal bases
            # carry an intercept), so the factor block must drop its own intercept
            # or the design is rank-deficient. Building WITH patsy's intercept and
            # slicing it off leaves exactly one dummy per non-reference level.
            data = {c: frame[c].to_numpy() for c in frame.columns}
            rhs = " + ".join(f"C({f})" for f in factors)
            factor_block = np.asarray(dmatrix(rhs, data, return_type="dataframe"), dtype=np.float64)
            blocks.append(factor_block[:, 1:])
        x = np.hstack(blocks) if len(blocks) > 1 else x_tensor

        n_tensor = x_tensor.shape[1]
        s_age, s_year = tensor_penalties(self.k_age, self.k_year, self.penalty_order)
        penalty = np.zeros((x.shape[1], x.shape[1]), dtype=np.float64)
        penalty[:n_tensor, :n_tensor] = self.lambda_age * s_age + self.lambda_year * s_year

        exposure = frame[self.exposure_col].to_numpy().astype(np.float64)
        deaths = frame[self.deaths_col].to_numpy().astype(np.float64)
        expected = exposure * frame["q_base"].to_numpy().astype(np.float64)
        if np.any(expected <= 0.0):
            raise PolarisValidationError(
                "Every cell must have positive exposure * q_base to form the offset."
            )
        offset = np.log(expected)

        coef, n_iter = _penalized_irls(x, deaths, offset, penalty)
        # Design context, exposed deliberately rather than as a private back
        # channel: select_lambdas_reml needs the assembled design, offset, response
        # and penalty blocks to score REML without rebuilding them. Three of the
        # four were previously uninitialised attributes, so touching them on an
        # unfitted model raised AttributeError instead of anything readable
        # (PR #188 review [P2]).
        self.design_context = DesignContext(
            design=x, offset=offset, deaths=deaths, n_tensor=n_tensor, s_age=s_age, s_year=s_year
        )
        # W at the FINAL coefficient, not the previous iterate. At tolerance the
        # difference is negligible, but cov / edf / dispersion should be the
        # quantities their docstrings claim rather than one step stale.
        weights = np.clip(np.exp(np.clip(offset + x @ coef, -700.0, 700.0)), 1e-300, None)
        xtwx = x.T @ (weights[:, None] * x)
        try:
            inv = np.linalg.inv(xtwx + penalty)
        except np.linalg.LinAlgError as exc:  # pragma: no cover - singular design
            raise PolarisComputationError("Penalized normal equations are singular.") from exc

        mu = np.exp(offset + x @ coef)
        resid_p = (deaths - mu) / np.sqrt(np.clip(mu, 1e-300, None))
        hat = inv @ xtwx
        edf_total = float(np.trace(hat))

        # Headline per-term EDF: tr(F) split by block. This CLOSES — the two sum to
        # edf_total exactly — which is why it replaced slice 1's overlapping split.
        f_diag = np.diag(hat)
        edf_tensor = float(f_diag[:n_tensor].sum())
        edf_factors = float(f_diag[n_tensor:].sum())

        # Margin diagnostic: dimensions each penalty REMOVED, relative to leaving
        # that margin unpenalized. Zero at lambda_j = 0 by construction.
        free_age = penalty.copy()
        free_age[:n_tensor, :n_tensor] = self.lambda_year * s_year
        free_year = penalty.copy()
        free_year[:n_tensor, :n_tensor] = self.lambda_age * s_age
        shrinkage_age = _edf_removed(xtwx, free_age, penalty)
        shrinkage_year = _edf_removed(xtwx, free_year, penalty)
        dof_resid = max(len(deaths) - edf_total, 1.0)
        dispersion = float((resid_p**2).sum() / dof_resid)

        ages = frame["attained_age"].to_numpy()
        years = frame["calendar_year"].to_numpy()
        return PenalizedMIFit(
            coef=coef,
            cov=inv * dispersion,
            edf_total=edf_total,
            edf_tensor=edf_tensor,
            edf_factors=edf_factors,
            shrinkage_age=shrinkage_age,
            shrinkage_year=shrinkage_year,
            dispersion=dispersion,
            lambda_age=self.lambda_age,
            lambda_year=self.lambda_year,
            n_cells=int(frame.height),
            n_coef=int(x.shape[1]),
            n_tensor=n_tensor,
            observed_ages=(int(ages.min()), int(ages.max())),
            observed_years=(int(years.min()), int(years.max())),
            factors=factors,
            n_iter=n_iter,
            reml_score=None if selection is None else selection.reml_score,
            gamma=gamma,
            n_rejected_points=None if selection is None else selection.n_rejected,
            n_evaluated_points=None if selection is None else selection.n_evaluated,
            lambda_grid_step=lambda_grid_step,
            _grid_design=lambda a, y: self.design_on_grid(info, a, y),
        )


def _edf_removed(xtwx: np.ndarray, unpenalized: np.ndarray, penalized: np.ndarray) -> float:
    """Dimensions a penalty removed: ``tr(F | λⱼ = 0) - tr(F)``.

    Zero when that margin carries no penalty, growing as the penalty bites. Reported
    as a **shrinkage** rather than an edf because the two margins overlap and cannot
    be added — a point slice 1 made in a docstring while naming the fields in a way
    that invited adding them anyway (PR #187 review).
    """
    free = float(np.trace(np.linalg.solve(xtwx + unpenalized, xtwx)))
    bound = float(np.trace(np.linalg.solve(xtwx + penalized, xtwx)))
    # Clipped: at equality these are two large traces cancelling, landing at ~-1e-9.
    return max(free - bound, 0.0)


def _penalized_irls(
    x: np.ndarray, y: np.ndarray, offset: np.ndarray, penalty: np.ndarray
) -> tuple[np.ndarray, int]:
    """Poisson log-link penalized IRLS: solve ``(XᵀWX + S)β = XᵀWz`` to convergence.

    **Convergence is on the deviance, not on the coefficient shift.** At a large λ
    the normal equations are penalty-dominated and badly conditioned, so the
    coefficients rattle in the penalised directions at round-off level indefinitely
    while the *fit* has long since settled. A coefficient-shift criterion never
    trips there — measured: no convergence in 100 iterations at λ=1e12, where the
    deviance had stabilised within 8. The deviance is also the quantity the fit is
    actually optimising, so this is the correct criterion rather than a workaround.

    The solve is Cholesky (the matrix is positive definite by construction), falling
    back to least squares if the penalty has driven it numerically singular.
    """
    from scipy.linalg import LinAlgError as SciPyLinAlgError
    from scipy.linalg import cho_factor, cho_solve

    coef = np.zeros(x.shape[1], dtype=np.float64)
    previous_deviance = np.inf
    for iteration in range(1, _MAX_IRLS_ITER + 1):
        eta = offset + x @ coef
        mu = np.exp(np.clip(eta, -700.0, 700.0))
        weights = np.clip(mu, 1e-300, None)
        z = eta - offset + (y - mu) / weights
        lhs = x.T @ (weights[:, None] * x) + penalty
        rhs = x.T @ (weights * z)
        try:
            coef = cho_solve(cho_factor(lhs, lower=True), rhs)
        except (SciPyLinAlgError, np.linalg.LinAlgError):
            coef, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)

        mu = np.exp(np.clip(offset + x @ coef, -700.0, 700.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            terms = np.where(y > 0.0, y * np.log(np.where(y > 0.0, y / mu, 1.0)), 0.0)
        deviance = float(2.0 * np.sum(terms - (y - mu)))
        if abs(deviance - previous_deviance) < _IRLS_TOL * (abs(deviance) + 0.1):
            return coef, iteration
        previous_deviance = deviance
    raise PolarisComputationError(
        f"Penalized IRLS did not converge in {_MAX_IRLS_ITER} iterations "
        f"(deviance {previous_deviance:.6g})."
    )


# --------------------------------------------------------------------------- #
# Slice 2 — REML selection
# --------------------------------------------------------------------------- #

LAMBDA_LOG10_BOUNDS = (-2.0, 8.0)
"""Search range for log10 λ. Wide on purpose: the bounds are a statement about
what is *representable*, not a prior about what is likely, and a selected λ sitting
on a bound is a caveat the caller must be told about rather than a silent clamp."""

COARSE_STEP = 1.0
REFINE_STEP = 0.25
"""Grid resolutions. **A grid rather than a continuous optimiser, deliberately.**
Anchor 3 makes determinism a requirement, and PLAN §5 risk 1 anticipated that a
converged λ could drift in its last digits across runs or platforms — the same class
of problem that already falsified this project's byte-for-byte reproducibility claim
(ADR-184 amendment 2). A grid removes the failure mode outright: the selected λ is a
grid point, so it is reproducible **by construction** with nothing to quantise. The
price is resolution, which is recorded on every **selected** fit as
``lambda_grid_step`` rather than left implicit — a plain ``fit()`` at hand-set λ
leaves it ``None`` by design, since there was no grid to have a resolution."""


def reml_score(
    deaths: np.ndarray,
    design: np.ndarray,
    offset: np.ndarray,
    coef: np.ndarray,
    penalty: np.ndarray,
    gamma: float = 1.0,
) -> float:
    """Laplace-approximate REML for a penalized Poisson GLM (lower is better).

    ``V = D/(2gamma) + log|XᵀWX + S|/2 - log|S|₊/2 - (p - r)·log(gamma)/2``, where ``|S|₊``
    is the generalized determinant — the product of the *positive* eigenvalues, since
    a difference penalty is rank-deficient by design and its null space is what makes
    a linear trend unpenalisable — ``p`` is the column count and ``r = rank(S)``.

    **REML rather than GCV**, per the plan: GCV undersmooths and admits multiple
    minima, which on an eight-year calendar window is a practical concern rather
    than a textbook one.

    ## ``gamma``, and exactly what it is doing here

    Wood's smoothness multiplier. ``mgcv`` documents it as multiplying "the effective
    degrees of freedom in the GCV or UBRE/AIC score (**or the scale parameter in the
    RE/ML criteria**)", and this is a RE/ML criterion, so gamma enters as the scale: set
    ``φ = gamma`` in the known-scale REML criterion and every gamma-dependent term above
    follows. The fit itself does **not** move — the scale cancels out of
    ``(XᵀWX/φ + S/φ)β = XᵀWz/φ`` — so gamma changes only which λ gets selected, by
    down-weighting the deviance against the complexity terms. Larger gamma, smoother fit.

    The ``-(p - r)·log(gamma)/2`` term is **constant in λ** and therefore cannot change a
    selection. It is carried anyway so that scores are comparable *across* gamma rather
    than only within one, since a criterion whose values silently shift by a constant
    is the kind of thing a later slice compares by accident.

    **gamma is adopted from mgcv and UNSETTLED — measured, not verified, not refuted**
    (PLAN Anchor 8; ADR-189 amendment 1). Slice 5's conformance run put level 5's two metrics
    narrowly outside their PROVISIONAL tolerances (``max_abs_log10_sp_diff_gamma`` 0.672
    against 0.5; ``abs_edf_total_diff_gamma`` 1.127 against 1.0) while the cross-cell sign
    check **passed** — ``gamma`` moves EDF the same way on both sides, it is the destination
    that differs. Note the same two metrics at ``gamma = 1.0`` pass narrowly, so the
    tolerances themselves are the unsettled part as much as ``gamma`` is. It is here for
    parity,
    **not** as a remedy for a bias this project has demonstrated: ADR-187 amendment 2
    measured the "REML undersmooths" direction on an age-flat fixture and found it
    does *not* reproduce on an age-varying one. It defaults to 1.0, where every term
    above collapses to the pre-gamma criterion exactly.
    """
    if gamma <= 0.0:
        raise PolarisValidationError(f"gamma must be positive, got {gamma}.")
    eta = offset + design @ coef
    mu = np.exp(np.clip(eta, -700.0, 700.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(
            deaths > 0.0, deaths * np.log(np.where(deaths > 0.0, deaths / mu, 1.0)), 0.0
        )
    deviance = float(2.0 * np.sum(terms - (deaths - mu)))

    weights = np.clip(mu, 1e-300, None)
    _, logdet_h = np.linalg.slogdet(design.T @ (weights[:, None] * design) + penalty)

    eigenvalues = np.linalg.eigvalsh(penalty)
    largest = float(eigenvalues.max()) if eigenvalues.size else 0.0
    positive = eigenvalues[eigenvalues > max(largest, 1e-300) * 1e-10]
    logdet_s = float(np.sum(np.log(positive))) if positive.size else 0.0

    # No `gamma == 1.0` short-circuit: np.log(1.0) is exactly 0.0 and `deviance / 1.0`
    # is exact, so the criterion is bit-identical at the default without a float
    # equality test guarding it (PR #190 review [P2]). The bit-identity is asserted by
    # test_gamma_of_one_leaves_the_criterion_bit_identical, not by this line's shape.
    scale = (design.shape[1] - positive.size) * float(np.log(gamma))
    return 0.5 * deviance / gamma + 0.5 * float(logdet_h) - 0.5 * logdet_s - 0.5 * scale


def _fit_and_score(
    cells: pl.DataFrame,
    log_age: float,
    log_year: float,
    gamma: float,
    model_kwargs: dict[str, object],
) -> tuple[np.ndarray, float]:
    """Penalized fit at ``log10 λ = (log_age, log_year)``, with its REML score.

    The one place that assembles a penalty block to match a fitted design, so the
    selector and the Kass-Steffey Hessian cannot drift apart in how they score a λ —
    which they would, since they differ only in *where* they evaluate. Propagates
    :class:`PolarisComputationError` from a non-converging IRLS; the selector catches
    it and scores the point ``+inf``, :func:`smoothing_uncertainty` does not.
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
    return fit.coef, reml_score(context.deaths, design, context.offset, fit.coef, penalty, gamma)


class LambdaSelection(NamedTuple):
    """What the grid search returns, including what it had to throw away.

    Replaces the bare ``(λ_age, λ_year, score)`` tuple slice 2 returned. The two new
    fields are not decoration: ADR-187 finding 5 is a grid point that *fails*, and a
    search that quietly drops failures while returning the same three numbers as
    before would make the failure invisible at exactly the scale it starts to matter
    (slice 6 runs this on a 125k-cell book).
    """

    lambda_age: float
    lambda_year: float
    reml_score: float
    n_rejected: int
    """Grid points whose own penalized IRLS did not converge, scored ``+inf``."""
    n_evaluated: int
    """Grid points visited in total, across both sweeps, rejections included."""


def select_lambdas_reml(
    cells: pl.DataFrame,
    *,
    coarse_step: float = COARSE_STEP,
    refine_step: float = REFINE_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    gamma: float = 1.0,
    **model_kwargs: object,
) -> LambdaSelection:
    """Choose (λ_age, λ_year) by REML over a deterministic grid.

    Coarse sweep over the full range, then one refinement pass at ``refine_step``
    around the coarse winner. Both passes are **grids**, so the result is a function
    of the inputs alone — no optimiser state, no convergence path, no last-digit
    drift across platforms (Anchor 3).

    Cost is **202 penalized fits** for an interior winner (coarse 11x11 = 121, then
    refine 9x9 = 81), or 166 when the winner clips at a bound — about 0.6-1.5 s on
    the ILEC-shaped fixture. An earlier revision said ~150, which was 11-35% low.
    On the real 125k-cell book the fit is the expensive part and slice 6 carries the
    budget.

    ## A grid point that does not converge is rejected, not raised

    Slice 2 let :class:`PolarisComputationError` out of ``score_at``, so a single
    non-converging corner took the whole search down: measured at ``log10 λ = (-1, 8)``
    — essentially unpenalized in age, saturated in year — on roughly one replicate in
    a hundred, and the coarse sweep visits that corner on *every* call (ADR-187
    finding 5). On a 125k-cell book that is a failed production run.

    **A λ whose own fit does not converge is not a λ to select**, so scoring it
    ``+inf`` is the answer rather than a workaround. The alternatives considered —
    damping the IRLS step, or raising the iteration cap — both make the search slower
    in order to keep evaluating a point it should be rejecting. Non-finite scores are
    rejected on the same grounds and by the same branch.

    The count comes back on :attr:`LambdaSelection.n_rejected` because a search that
    discarded half its grid is a different object from one that discarded nothing, and
    :func:`fit_reml` forwards it onto the fit. If *every* point is rejected there is no
    selection to report and that raises — returning the untouched grid centre would be
    a fabricated answer wearing the same type as a real one.
    """
    lo, hi = bounds
    tally = {"rejected": 0, "evaluated": 0}

    def score_at(log_age: float, log_year: float) -> float:
        tally["evaluated"] += 1
        try:
            _, value = _fit_and_score(cells, log_age, log_year, gamma, model_kwargs)
        except PolarisComputationError:
            tally["rejected"] += 1
            return np.inf
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
            f"REML selection rejected every one of {tally['evaluated']} grid points — "
            f"no penalized fit converged anywhere in log10 lambda {bounds}. The grid "
            f"centre is not an answer, so this raises rather than returning one. Check "
            f"the cells for zero-exposure or zero-death rows before widening the grid."
        )
    return LambdaSelection(
        10.0 ** fine[1], 10.0 ** fine[2], fine[0], tally["rejected"], tally["evaluated"]
    )


KS_LOG_STEP = float(np.log(10.0) * REFINE_STEP)
"""Finite-difference step for the Kass-Steffey Hessian, in **natural** log λ.

One refinement-grid step (0.25 decade), and the choice is not arbitrary. λ is known
only to the grid's resolution, so differencing on a finer scale would be measuring
structure the selector cannot resolve; and ADR-187 amendment 2 measured the REML
profile as **very shallow** — 3.85 REML units across 5.5 decades — where a small step
differences round-off rather than curvature. A grid step is the natural scale at both
ends of that trade."""


@dataclass(frozen=True)
class SmoothingUncertainty:
    """λ's own sampling variance, propagated into the coefficient covariance."""

    correction: np.ndarray
    """``J V_rho Jᵀ``, positive semi-definite by construction, to be **added** to
    ``Vb``. PSD is what makes the unconditional band provably no narrower than the
    conditional one, which is the direction check a sign error would break."""

    v_rho: np.ndarray
    """2x2 covariance of ``(log λ_age, log λ_year)``, i.e. the floored inverse of
    :attr:`hessian`. In natural log units, so a diagonal entry of 1.0 is one e-fold."""

    hessian: np.ndarray
    """2x2 second derivative of the REML criterion in natural log λ, by central
    differences. Not necessarily positive definite: λ came from a *grid*, so it is
    near a minimum rather than at a stationary point."""

    jacobian: np.ndarray
    """``∂β̂/∂log λ``, ``n_coef x 2``, by central differences."""

    n_floored: int
    """Hessian eigenvalues raised to the variance cap — see :func:`smoothing_uncertainty`.
    Non-zero means the criterion is flat (or locally non-convex) in that many
    directions and λ's variance there is capped rather than believed."""

    log_step: float


def smoothing_uncertainty(
    cells: pl.DataFrame,
    *,
    lambda_age: float,
    lambda_year: float,
    gamma: float = 1.0,
    log_step: float = KS_LOG_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    **model_kwargs: object,
) -> SmoothingUncertainty:
    """The Kass-Steffey correction: what ``Vb`` leaves out because it conditions on λ.

    ``Vb = (XᵀWX + S)⁻¹φ`` is a covariance **given** the smoothing parameters, and
    ADR-187 finding 2 established that the λ it is given is one draw from a wide
    distribution. Slice 3 measured the consequence: **87.1% coverage against a
    nominal 95%** on a truth the basis represents exactly. This function computes the
    missing term.

    Kass-Steffey (1989), as ``mgcv`` exposes it through
    ``vcov(..., unconditional = TRUE)``:

        ``Vβ' = Vβ + J V_rho Jᵀ``, with ``rho = log lambda``,
        ``J = d(beta-hat)/d(rho)`` and ``V_rho = H⁻¹``

    where ``H`` is the Hessian of the REML criterion in ``rho``. Both derivatives are
    taken by **central differences** — nine penalized fits, against the selector's 202
    — because the criterion and the fit are already available as functions of rho and an
    analytic derivative would be a second implementation of the fit to keep in step.

    ## The variance cap, and why a cap rather than a pseudo-inverse

    ``H`` is evaluated at a **grid point**, not at a stationary point, so it can carry
    a near-zero or negative eigenvalue — and ADR-187 amendment 2 says to expect
    near-zero, because the profile is shallow. Inverting that directly sends λ's
    variance to infinity (or negative), and neither is an interval.

    The cap comes from the selector's own contract: :func:`select_lambdas_reml`
    **cannot** return a λ outside ``bounds``, so ``log lambda``'s standard deviation cannot
    exceed half the bound width. Eigenvalues below ``1/(half-width)²`` are raised to
    it, which caps the variance a flat direction contributes at exactly the range the
    search could have produced. That is a statement about the search rather than a
    numerical fudge factor, and :attr:`SmoothingUncertainty.n_floored` reports how
    often it bound.

    **REFUTED — this correction systematically UNDER-INFLATES** (2026-08-10, ADR-189
    amendment 1). Slice 5's conformance run compared it against
    ``vcov(m, unconditional = TRUE)``: ours inflates the mean variance 1.11-1.21x where
    ``mgcv`` inflates it 1.49-1.87x, in the **same direction on every cell**, two of three
    past the 0.25 tolerance. PLAN Anchor 8 said a refutation would be a successful run, and
    this is it — an under-inflated covariance under-covers, which localises ADR-188's failing
    Anchor-7 gate (0.8516 / 0.8581 against a 0.9192 floor) to **this arithmetic** rather than
    to shrinkage bias no covariance could reach.

    Three places to look, in order, before anything is tuned: the central-difference Jacobian
    ``d(beta-hat)/d(rho)`` and ``log_step``; the **eigenvalue floor** below, which caps the
    variance a flat direction contributes and would produce exactly this under-inflation if it
    binds too often
    (:attr:`SmoothingUncertainty.n_floored` was measured at 0.46 / 0.15 directions per fit in
    ADR-188); and the natural-log-versus-decade conversion, the one place a factor of
    ``ln(10)²`` could hide. **Do not tune the floor until it matches mgcv — derive it.**

    Raises:
        PolarisComputationError: if a perturbed λ fails to converge. Unlike the
            selector this does **not** reject and continue: a missing corner is a
            missing derivative, and a Hessian assembled from whatever converged would
            be a different quantity reported under the same name.
    """
    if log_step <= 0.0:
        raise PolarisValidationError(f"log_step must be positive, got {log_step}.")
    if lambda_age <= 0.0 or lambda_year <= 0.0:
        raise PolarisValidationError(
            "The Kass-Steffey correction differentiates in log lambda, so both "
            f"smoothing parameters must be strictly positive; got ({lambda_age}, "
            f"{lambda_year})."
        )
    centre = np.array([np.log10(lambda_age), np.log10(lambda_year)], dtype=np.float64)
    # Derivatives are in NATURAL log lambda per Kass-Steffey; the fitter is addressed
    # in decades, so the step is converted once here and the two are never mixed.
    step10 = log_step / float(np.log(10.0))

    def at(d_age: float, d_year: float) -> tuple[np.ndarray, float]:
        try:
            return _fit_and_score(cells, centre[0] + d_age, centre[1] + d_year, gamma, model_kwargs)
        except PolarisComputationError as exc:
            raise PolarisComputationError(
                f"The unconditional covariance needs the REML criterion at "
                f"log10 lambda offset ({d_age:+.3f}, {d_year:+.3f}) from the selected "
                f"({centre[0]:.3f}, {centre[1]:.3f}), and the penalized fit there did "
                f"not converge. A Hessian built from the corners that happened to "
                f"converge is not the Hessian, so this raises rather than degrading "
                f"silently. Try a smaller log_step."
            ) from exc

    _, v0 = at(0.0, 0.0)
    beta_ap, v_ap = at(+step10, 0.0)
    beta_am, v_am = at(-step10, 0.0)
    beta_yp, v_yp = at(0.0, +step10)
    beta_ym, v_ym = at(0.0, -step10)
    _, v_pp = at(+step10, +step10)
    _, v_pm = at(+step10, -step10)
    _, v_mp = at(-step10, +step10)
    _, v_mm = at(-step10, -step10)

    h_sq = log_step * log_step
    hessian = np.array(
        [
            [(v_ap - 2.0 * v0 + v_am) / h_sq, (v_pp - v_pm - v_mp + v_mm) / (4.0 * h_sq)],
            [(v_pp - v_pm - v_mp + v_mm) / (4.0 * h_sq), (v_yp - 2.0 * v0 + v_ym) / h_sq],
        ],
        dtype=np.float64,
    )
    jacobian = np.column_stack(
        [(beta_ap - beta_am) / (2.0 * log_step), (beta_yp - beta_ym) / (2.0 * log_step)]
    ).astype(np.float64)

    half_width = float(np.log(10.0) * (bounds[1] - bounds[0])) / 2.0
    variance_cap = half_width * half_width
    eigenvalue_floor = 1.0 / variance_cap
    eigenvalues, vectors = np.linalg.eigh(0.5 * (hessian + hessian.T))
    # Reciprocal of the CLIPPED eigenvalue, not a select between two branches: an
    # exactly-zero (or negative) eigenvalue is the case this floor exists for, and
    # computing 1/eigenvalue first would emit a divide-by-zero warning for a value
    # that is then discarded (PR #190 review [P2]).
    variances = 1.0 / np.maximum(eigenvalues, eigenvalue_floor)
    n_floored = int(np.sum(eigenvalues <= eigenvalue_floor))
    v_rho = (vectors * variances) @ vectors.T

    return SmoothingUncertainty(
        correction=jacobian @ v_rho @ jacobian.T,
        v_rho=v_rho,
        hessian=hessian,
        jacobian=jacobian,
        n_floored=n_floored,
        log_step=log_step,
    )


def lambda_is_at_bound(
    lambda_value: float,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    tol: float = 1e-9,
) -> bool:
    """Is a selected λ pinned to the edge of the search range?

    It happens routinely and legitimately — a genuinely linear calendar trend wants
    a λ the grid cannot express, and the constant-MI fixture selects exactly
    ``1e8``, the upper bound. But it means the reported number is *"at least this"*
    rather than *"this"*, and Anchor 5's discipline of checking a fitted quantity
    against its ceiling applies to λ as much as to ``k``.

    Flagged rather than silently clamped, because :func:`select_lambdas_reml`'s
    docstring promises the caller is told and an unkept promise in a docstring is
    the defect class this epic keeps finding in its own work.
    """
    log_value = float(np.log10(lambda_value)) if lambda_value > 0.0 else bounds[0]
    return abs(log_value - bounds[0]) < tol or abs(log_value - bounds[1]) < tol


def fit_reml(
    cells: pl.DataFrame,
    *,
    coarse_step: float = COARSE_STEP,
    refine_step: float = REFINE_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    gamma: float = 1.0,
    unconditional: bool = False,
    log_step: float = KS_LOG_STEP,
    **model_kwargs: object,
) -> PenalizedMIFit:
    """Select λ by REML, then fit at it — with the selection metadata recorded.

    ``unconditional=True`` adds the Kass-Steffey term to the covariance, so the bands
    stop conditioning on a λ that ADR-187 finding 2 showed is one draw from a wide
    distribution. It costs nine extra penalized fits on top of the selector's 202 and
    it is **off by default**, because PLAN Anchor 7 forbids anyone calling either
    interval a 95% band until select-per-replicate coverage has been measured — the
    default should not quietly pick a side of a question the project has open.
    Whichever is used is recorded on :attr:`PenalizedMIFit.band_is_unconditional`.

    **This function exists because the fields it populates were inert.** Slice 2
    shipped `reml_score` and `lambda_grid_step` on :class:`PenalizedMIFit`, with
    docstrings in five places saying they distinguish a selected surface from a
    hand-set one. Nothing wrote them: `select_lambdas_reml` returned a bare tuple that
    a caller had to re-assemble into a model by hand, so both were always ``None`` and
    the two cases were indistinguishable (PR #188 review [P1]). Slice 4 replaced that
    tuple with :class:`LambdaSelection` and added two more fields to carry — which
    makes this function's job larger, not smaller.

    Callers who want a selected surface should use this rather than the two-step
    dance, because the two-step dance is exactly what dropped the metadata.

    The grid parameters are **named here rather than swept up in** ``model_kwargs``,
    which is forwarded to the model constructor as well as the selector. An earlier
    revision took them only implicitly, so ``refine_step=0.5`` raised ``TypeError``
    from ``PenalizedTensorMIModel.__init__`` before it could reach the selector, and
    the reported ``lambda_grid_step`` was the module constant rather than the
    resolution actually used. The two halves were the same gap and are closed
    together: the step reported is the step swept (PR #188 review round 2 [P2]).
    Slice 4 needs the override — a coarser sweep is the obvious lever when 202 fits
    meet the 125k-cell book.
    """
    selection = select_lambdas_reml(
        cells,
        coarse_step=coarse_step,
        refine_step=refine_step,
        bounds=bounds,
        gamma=gamma,
        **model_kwargs,
    )
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=selection.lambda_age,
        lambda_year=selection.lambda_year,
        **model_kwargs,  # type: ignore[arg-type]
    )
    fit = model.fit(selection=selection, lambda_grid_step=refine_step, gamma=gamma)
    if not unconditional:
        return fit
    extra = smoothing_uncertainty(
        cells,
        lambda_age=selection.lambda_age,
        lambda_year=selection.lambda_year,
        gamma=gamma,
        log_step=log_step,
        bounds=bounds,
        **model_kwargs,
    )
    return replace(fit, cov=fit.cov + extra.correction, band_is_unconditional=True)
