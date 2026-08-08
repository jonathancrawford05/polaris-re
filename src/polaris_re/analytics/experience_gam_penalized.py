"""Penalized tensor mortality-improvement surface — P-splines at fixed λ.

Slice 1 of ``docs/PLAN_penalized_mi_surface.md``. **Fixed, caller-supplied λ only**;
REML selection is slice 2, and separating the two is deliberate — an optimiser
wrapped around an unverified fitter is two hard things at once.

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

## The parameterisation, and why Anchor 1 can hold exactly

``TensorMIModel`` builds ``1 + bs(age, df=ka) + bs(year, df=ky) + interaction`` —
patsy's main-effects form. A difference penalty is not natural in that basis: it
penalises *marginal* coefficients, which live in the full Kronecker form
``B_age ⊗ B_year``.

So this module builds the clean Kronecker design instead, from **full** marginal
bases (``df + 1`` with an intercept, which carries the same interior knots). The two
designs are different bases for the **same column space** — verified: rank of the
concatenation equals the rank of either, and fitted values agree to ~4e-15 on a
random response. Since least-squares projection is basis-independent, **at λ=0 the
two models fit identical values** (Anchor 1) even though their coefficients differ
and are not comparable.

That is why Anchor 1 is asserted on the fitted surface and never on coefficients.
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
    "PenalizedMIFit",
    "PenalizedTensorMIModel",
    "difference_penalty",
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
class PenalizedMIFit:
    """A fitted penalized surface at fixed λ."""

    coef: np.ndarray
    cov: np.ndarray
    """Bayesian covariance ``(XᵀWX + S)⁻¹ φ`` — Wood's, not the delta-method
    sandwich. Slice 3 measures whether its bands cover at nominal rate; slice 1
    only has to produce it."""

    edf_total: float
    """``tr(H)`` for ``H = X (XᵀWX + S)⁻¹ XᵀW``. Bounded above by the column count
    and below by the penalty null-space dimension."""

    edf_age: float
    edf_year: float
    dispersion: float
    lambda_age: float
    lambda_year: float
    n_cells: int
    n_coef: int
    observed_ages: tuple[int, int]
    observed_years: tuple[int, int]
    factors: tuple[str, ...]
    n_iter: int
    _design_builder: object = field(default=None, repr=False)


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
        self.lambda_age = float(lambda_age)
        self.lambda_year = float(lambda_year)

    # -- design ------------------------------------------------------------------

    def _basis(
        self, x: np.ndarray, k: int, bounds: tuple[float, float]
    ) -> tuple[np.ndarray, np.ndarray]:
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
            from patsy import dmatrix

            spec = f"bs(v, df={k}, degree={self.degree}, include_intercept=True) - 1"
            design = dmatrix(spec, {"v": np.asarray(x, dtype=np.float64)}, return_type="dataframe")
            return np.asarray(design, dtype=np.float64), np.asarray([], dtype=np.float64)

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
        age_bounds, year_bounds, _, _ = info  # type: ignore[misc]
        grid_age = np.repeat(np.asarray(ages, dtype=np.float64), len(years))
        grid_year = np.tile(np.asarray(years, dtype=np.float64), len(ages))
        b_age, _ = self._basis(grid_age, self.k_age, age_bounds)
        b_year, _ = self._basis(grid_year, self.k_year, year_bounds)
        return self._tensor_block(b_age, b_year)

    # -- fit ---------------------------------------------------------------------

    def fit(self) -> PenalizedMIFit:
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

        coef, n_iter, weights = _penalized_irls(x, deaths, offset, penalty)

        xtwx = x.T @ (weights[:, None] * x)
        try:
            inv = np.linalg.inv(xtwx + penalty)
        except np.linalg.LinAlgError as exc:  # pragma: no cover - singular design
            raise PolarisComputationError("Penalized normal equations are singular.") from exc

        mu = np.exp(offset + x @ coef)
        resid_p = (deaths - mu) / np.sqrt(np.clip(mu, 1e-300, None))
        hat = inv @ xtwx
        edf_total = float(np.trace(hat))
        dof_resid = max(len(deaths) - edf_total, 1.0)
        dispersion = float((resid_p**2).sum() / dof_resid)

        ages = frame["attained_age"].to_numpy()
        years = frame["calendar_year"].to_numpy()
        return PenalizedMIFit(
            coef=coef,
            cov=inv * dispersion,
            edf_total=edf_total,
            edf_age=_margin_edf(hat, self.k_age, self.k_year, axis=0),
            edf_year=_margin_edf(hat, self.k_age, self.k_year, axis=1),
            dispersion=dispersion,
            lambda_age=self.lambda_age,
            lambda_year=self.lambda_year,
            n_cells=int(frame.height),
            n_coef=int(x.shape[1]),
            observed_ages=(int(ages.min()), int(ages.max())),
            observed_years=(int(years.min()), int(years.max())),
            factors=factors,
            n_iter=n_iter,
            _design_builder=info,
        )


def _margin_edf(hat: np.ndarray, k_age: int, k_year: int, *, axis: int) -> float:
    """Effective df attributable to one margin.

    The tensor block's diagonal reshaped to (k_age, k_year) and summed over the
    other axis. This is a **descriptive split, not an orthogonal decomposition** —
    the margins are not independent and the two do not sum to ``edf_total``. It is
    reported because Anchor 4 requires complexity to be visible, and the honest
    caveat travels with it rather than being discovered later.
    """
    n_tensor = k_age * k_year
    diag = np.diag(hat)[:n_tensor].reshape(k_age, k_year)
    return float(diag.sum(axis=1 - axis).sum())


def _penalized_irls(
    x: np.ndarray, y: np.ndarray, offset: np.ndarray, penalty: np.ndarray
) -> tuple[np.ndarray, int, np.ndarray]:
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
    weights = np.ones_like(y)
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
            return coef, iteration, weights
        previous_deviance = deviance
    raise PolarisComputationError(
        f"Penalized IRLS did not converge in {_MAX_IRLS_ITER} iterations "
        f"(deviance {previous_deviance:.6g})."
    )
