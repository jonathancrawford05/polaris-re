"""Penalized tensor mortality-improvement surface — P-splines with REML-selected λ.

Slices 1-2 of ``docs/PLAN_penalized_mi_surface.md``. :class:`PenalizedTensorMIModel`
fits at a **caller-supplied λ**; :func:`select_lambdas_reml` chooses one by REML over
a deterministic grid. They are separate entry points because they were built as
separate slices — an optimiser wrapped around an unverified fitter is two hard
things at once — and keeping them separate is what lets the fixed-λ limits stay
testable in isolation (ADR-185, ADR-186).

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

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import (
    _CANDIDATE_FACTORS,
    AMOUNT_MEASURES,
    COUNT_MEASURES,
    _assert_static_base,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "COARSE_STEP",
    "LAMBDA_LOG10_BOUNDS",
    "REFINE_STEP",
    "DesignContext",
    "PenalizedMIFit",
    "PenalizedTensorMIModel",
    "difference_penalty",
    "fit_reml",
    "lambda_is_at_bound",
    "reml_score",
    "select_lambdas_reml",
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

    ``reml_score`` and ``lambda_grid_step`` are populated only when λ came from
    :func:`select_lambdas_reml`; a fixed-λ fit leaves both ``None``, which is how a
    reader tells a selected surface from a hand-set one."""

    coef: np.ndarray
    cov: np.ndarray
    """Bayesian covariance ``(XᵀWX + S)⁻¹ φ`` — Wood's, not the delta-method
    sandwich. Slice 3 measures whether its bands cover at nominal rate; slice 1
    only has to produce it."""

    edf_total: float
    """``tr(F)`` for ``F = (XᵀWX + S)⁻¹ XᵀWX``, over every column."""

    edf_tensor: float
    """**The headline.** ``tr(F)`` restricted to the tensor block — the per-term EDF
    ``mgcv`` reports for a smooth. Unlike the shrinkages it **closes**:
    ``edf_tensor + edf_factors == edf_total`` exactly.

    The mgcv-consistency is *adopted, not verified* — nothing in this container can
    compare against mgcv, and PLAN §7 carries that as the oracle's second job."""

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
    observed_ages: tuple[int, int]
    observed_years: tuple[int, int]
    factors: tuple[str, ...]
    n_iter: int

    reml_score: float | None = None
    """Laplace-approximate REML at the fitted λ, or ``None`` for a fixed-λ fit."""

    lambda_grid_step: float | None = None
    """log10 resolution of the grid the λ came from, or ``None`` if λ was supplied.

    Recorded because it is the exact size of the determinism/accuracy trade Anchor 3
    forced: a grid is reproducible **by construction** — there is no optimiser whose
    last digits can drift — and the price is that λ is known only to this
    resolution."""

    _design_builder: object | None = field(default=None, repr=False)


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
        reml_score_value: float | None = None,
        lambda_grid_step: float | None = None,
    ) -> PenalizedMIFit:
        """Penalized IRLS at the fixed λ supplied to the constructor."""
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
            observed_ages=(int(ages.min()), int(ages.max())),
            observed_years=(int(years.min()), int(years.max())),
            factors=factors,
            n_iter=n_iter,
            reml_score=reml_score_value,
            lambda_grid_step=lambda_grid_step,
            _design_builder=info,
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
price is resolution, which is recorded on every fit as ``lambda_grid_step`` rather
than left implicit."""


def reml_score(
    deaths: np.ndarray,
    design: np.ndarray,
    offset: np.ndarray,
    coef: np.ndarray,
    penalty: np.ndarray,
) -> float:
    """Laplace-approximate REML for a penalized Poisson GLM (lower is better).

    ``V = D/2 + log|XᵀWX + S|/2 - log|S|₊/2``, where ``|S|₊`` is the generalized
    determinant — the product of the *positive* eigenvalues, since a difference
    penalty is rank-deficient by design and its null space is what makes a linear
    trend unpenalisable.

    **REML rather than GCV**, per the plan: GCV undersmooths and admits multiple
    minima, which on an eight-year calendar window is a practical concern rather
    than a textbook one.
    """
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

    return 0.5 * deviance + 0.5 * float(logdet_h) - 0.5 * logdet_s


def select_lambdas_reml(
    cells: pl.DataFrame,
    *,
    coarse_step: float = COARSE_STEP,
    refine_step: float = REFINE_STEP,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    **model_kwargs: object,
) -> tuple[float, float, float]:
    """Choose (λ_age, λ_year) by REML over a deterministic grid.

    Returns ``(lambda_age, lambda_year, reml_score)``.

    Coarse sweep over the full range, then one refinement pass at ``refine_step``
    around the coarse winner. Both passes are **grids**, so the result is a function
    of the inputs alone — no optimiser state, no convergence path, no last-digit
    drift across platforms (Anchor 3).

    Cost is **202 penalized fits** for an interior winner (coarse 11x11 = 121, then
    refine 9x9 = 81), or 166 when the winner clips at a bound — about 1.0-1.5 s on
    the ILEC-shaped fixture. An earlier revision said ~150, which was 11-35% low.
    On the real 125k-cell book the fit is the expensive part and
    slice 4 carries the budget.
    """
    lo, hi = bounds

    def score_at(log_age: float, log_year: float) -> float:
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
        return reml_score(context.deaths, design, context.offset, fit.coef, penalty)

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
    return 10.0 ** fine[1], 10.0 ** fine[2], fine[0]


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


def fit_reml(cells: pl.DataFrame, **model_kwargs: object) -> PenalizedMIFit:
    """Select λ by REML, then fit at it — with the selection metadata recorded.

    **This function exists because the fields it populates were inert.** Slice 2
    shipped `reml_score` and `lambda_grid_step` on :class:`PenalizedMIFit`, with
    docstrings in five places saying they distinguish a selected surface from a
    hand-set one. Nothing wrote them: `select_lambdas_reml` returns a bare tuple and
    a caller rebuilding the model got the defaults, so both were always ``None`` and
    the two cases were indistinguishable (PR #188 review [P1]).

    Callers who want a selected surface should use this rather than the two-step
    dance, because the two-step dance is exactly what dropped the metadata.
    """
    lambda_age, lambda_year, score = select_lambdas_reml(cells, **model_kwargs)
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=lambda_age,
        lambda_year=lambda_year,
        **model_kwargs,  # type: ignore[arg-type]
    )
    return model.fit(reml_score_value=score, lambda_grid_step=REFINE_STEP)
