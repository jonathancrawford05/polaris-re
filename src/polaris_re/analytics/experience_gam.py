"""
Experience GAM — interpretable additive model for mortality experience analysis.

This module is the auditable middle layer between the grouped limited-fluctuation
credibility in :mod:`polaris_re.analytics.experience_study` and the black-box
XGBoost path in :mod:`polaris_re.assumptions.ml_mortality`. It isolates *standard*
feature effects (attained age, select duration, and categorical risk factors) from
experience and expresses them as a smooth, uncertainty-quantified **A/E multiplier
surface** on top of a static select-and-ultimate base table.

Design anchors (see docs/PLAN_experience_gam.md — Slice 1 subset):

1. **Model on the log-mortality scale, offset by the static select base.**
   ``log μ = log[exposure * q_base(x, d)] + η``, Poisson / quasi-Poisson.
   ``q_base(x, d)`` is the existing VBT/CIA select-and-ultimate annual rate — it
   pins the dominant agexduration structure so the GAM estimates only the company
   A/E level and small residual shape. The base MUST be a single-reference-year
   static table (never generational) — anchor 1.

2. **A/E parameterization, not direct-qx.** ``exp(η)`` is the fitted multiplicative
   deviation from the base table. It plugs straight into a blended basexmultiplier
   export that round-trips through :func:`polaris_re.utils.table_io.load_mortality_csv`.

7. **Grouped Lexis cells are the canonical input.** One row per covariate
   combination; the grouped Poisson likelihood equals the seriatim likelihood up
   to a constant, so grouping is sufficiency, not compromise. An optional
   :func:`aggregate_seriatim` folds a row-level extract into the same contract.
   Both by-count and by-amount exposure/deaths are carried; the by-amount basis
   is overdispersed → a dispersion parameter (quasi-Poisson scale) is mandatory
   there, optional for by-count.

Slice-2a adds the **tensor mortality-improvement (MI) surface** — the epic
headline. :class:`TensorMIModel` fits an age-varying calendar-improvement term
``te(attained_age, calendar_year)`` on top of the same static-base offset and
extracts the annual improvement grid ``MI_x(y) = 1 - exp[te(x, y) - te(x, y-1)]``
with pointwise (delta-method) confidence bands. It encodes Design-Anchor-3
identifiability by construction (no issue-year term → the calendar gradient is
attributed to improvement; an optional ``underwriting_era`` factor exposes the
alternative), and guards against a *generational* base offset (which would make
the fitted trend residual-vs-assumed improvement, not MI). Slice 2a is the
frequentist, CI-lean de-risking of the surface (statsmodels tensor-product
B-splines, no new dependency); the Bayesian HSGP backend (honest posterior
credible intervals + posterior-predictive projection) and the
``MortalityImprovement``-compatible custom-scale emission are Slices 2b-2c.

Still out of scope here: hierarchical partial pooling (Slice 3) and the CLI /
assumption-versioning / validation surfaces (Slice 4).

Backend: ``statsmodels`` (penalized/regression splines via ``patsy`` B-splines).
Both are guarded behind the ``[ml]`` optional extra — this module imports them
lazily so ``import polaris_re.analytics`` still succeeds when ``[ml]`` is absent;
the first fit then raises an actionable error.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import numpy as np
import polars as pl

from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus

__all__ = [
    "AMOUNT_MEASURES",
    "CANONICAL_KEY_COLUMNS",
    "COUNT_MEASURES",
    "ExperienceGAM",
    "GAMFitResult",
    "MISurface",
    "MISurfaceResult",
    "SmoothEffect",
    "TensorMIModel",
    "aggregate_seriatim",
    "attach_base_rate",
]


# --- Canonical grouped-cell contract (anchor 7) ---------------------------------

CANONICAL_KEY_COLUMNS: tuple[str, ...] = (
    "issue_age",
    "duration_months",
    "attained_age",
    "calendar_year",
    "sex",
    "smoker",
    "band",
    "product",
    "uw_class",
    "channel",
    "segment",
    "underwriting_era",
)
"""Covariate keys of the canonical grouped-cell contract. Only a subset is
required for a given study (see :class:`ExperienceGAM`); the rest are optional
dimensions that become GAM factors when present and varying."""

COUNT_MEASURES: tuple[str, str] = ("central_exposure", "death_count")
"""By-count exposure/deaths pair — the policy-count experience basis."""

AMOUNT_MEASURES: tuple[str, str] = ("amount_exposed", "death_amount")
"""By-amount exposure/deaths pair — the face-amount-weighted experience basis
(overdispersed → dispersion parameter mandatory)."""

# Factors that may enter the additive model when present with >1 level.
# ``underwriting_era`` is the Design-Anchor-3 escape hatch: a cedant with a known
# underwriting change in the experience window can expose it to attribute part of
# the calendar gradient to a secular underwriting shift rather than improvement.
_CANDIDATE_FACTORS: tuple[str, ...] = (
    "sex",
    "smoker",
    "band",
    "product",
    "uw_class",
    "channel",
    "segment",
    "underwriting_era",
)


def aggregate_seriatim(
    seriatim: pl.DataFrame,
    key_columns: list[str] | None = None,
) -> pl.DataFrame:
    """
    Fold a seriatim (row-level) experience extract into the canonical grouped
    contract by summing the exposure/death measures over the covariate keys.

    Because covariates are constant within a grouped cell, the grouped
    Poisson/quasi-Poisson likelihood equals the seriatim likelihood up to a
    constant — so aggregating first yields *identical* fitted coefficients
    (anchor 7). This function is that aggregator.

    Args:
        seriatim:    Row-level DataFrame carrying at least ``attained_age`` and
                     one exposure/deaths measure pair. Measure columns present
                     from ``COUNT_MEASURES``/``AMOUNT_MEASURES`` are summed; every
                     other recognised key column is used as a grouping dimension.
        key_columns: Explicit grouping keys. If None, all present canonical key
                     columns are used.

    Returns:
        Grouped DataFrame: one row per covariate combination, with the measure
        columns summed. Sorted by the grouping keys for deterministic output.

    Raises:
        PolarisValidationError: If no measure columns are present.
    """
    present_measures = [c for c in (*COUNT_MEASURES, *AMOUNT_MEASURES) if c in seriatim.columns]
    if not present_measures:
        raise PolarisValidationError(
            "Seriatim extract has no recognised measure columns; expected at "
            f"least one of {(*COUNT_MEASURES, *AMOUNT_MEASURES)}."
        )

    if key_columns is None:
        key_columns = [c for c in CANONICAL_KEY_COLUMNS if c in seriatim.columns]
    else:
        unknown = set(key_columns) - set(seriatim.columns)
        if unknown:
            raise PolarisValidationError(f"key_columns not found in data: {unknown}")

    if not key_columns:
        raise PolarisValidationError("No grouping key columns present in seriatim extract.")

    grouped = seriatim.group_by(key_columns).agg(
        [pl.col(m).sum().alias(m) for m in present_measures]
    )
    return grouped.sort(key_columns)


def _annual_base_rate(
    table: MortalityTable,
    attained_ages: np.ndarray,
    sex: Sex,
    smoker: SmokerStatus,
    duration_months: np.ndarray,
) -> np.ndarray:
    """
    Annual static-base q_base(x, d) for a block of cells sharing (sex, smoker).

    ``MortalityTable.get_qx_vector`` returns *monthly* rates under a constant-force
    assumption; ``q_annual = 1 - (1 - q_monthly)**12`` inverts that exactly, so the
    result is the table's annual select-and-ultimate rate with no interpolation
    loss.
    """
    q_monthly = table.get_qx_vector(
        ages=attained_ages.astype(np.int32),
        sex=sex,
        smoker_status=smoker,
        durations=duration_months.astype(np.int32),
    )
    q_annual = 1.0 - np.power(1.0 - q_monthly, 12.0)
    return q_annual.astype(np.float64)


def attach_base_rate(
    cells: pl.DataFrame,
    table: MortalityTable,
    *,
    default_smoker: SmokerStatus = SmokerStatus.UNKNOWN,
    column: str = "q_base",
) -> pl.DataFrame:
    """
    Attach the static select-and-ultimate annual base rate ``q_base`` to each
    grouped cell using ``table.get_qx_vector`` (anchor 1).

    The lookup requires a single (sex, smoker) per call, so this loops over the
    distinct (sex, smoker) combinations present in the cells — a handful of
    categories, never a per-policy loop.

    Args:
        cells:          Grouped cells with ``attained_age`` and, if the table is
                        select, ``duration_months`` (defaults to ultimate/0 when
                        absent). Optional ``sex``/``smoker`` columns select the
                        table; missing sex defaults to male, missing smoker to
                        ``default_smoker``.
        table:          A static (single-reference-year) mortality table.
        default_smoker: Smoker status used when the cells carry no ``smoker`` col.
        column:         Output column name for the base rate.

    Returns:
        The cells with an added ``q_base`` float64 column in (0, 1].

    Raises:
        PolarisValidationError: If ``attained_age`` is missing.
    """
    if "attained_age" not in cells.columns:
        raise PolarisValidationError("attach_base_rate requires an 'attained_age' column.")

    n = cells.height
    ages = cells["attained_age"].to_numpy().astype(np.int32)
    if "duration_months" in cells.columns:
        dur = cells["duration_months"].to_numpy().astype(np.int32)
    else:
        dur = np.zeros(n, dtype=np.int32)

    if "sex" in cells.columns:
        sex_raw = cells["sex"].to_numpy()
    else:
        sex_raw = np.full(n, Sex.MALE.value, dtype=object)
    if "smoker" in cells.columns:
        smk_raw = cells["smoker"].to_numpy()
    else:
        smk_raw = np.full(n, default_smoker.value, dtype=object)

    q_base = np.zeros(n, dtype=np.float64)
    # Iterate over the distinct (sex, smoker) label pairs — small cardinality.
    combos = {(str(s), str(k)) for s, k in zip(sex_raw, smk_raw, strict=True)}
    for sex_label, smk_label in combos:
        mask = np.array(
            [
                str(s) == sex_label and str(k) == smk_label
                for s, k in zip(sex_raw, smk_raw, strict=True)
            ],
            dtype=bool,
        )
        sex_enum = Sex(sex_label)
        smoker_enum = SmokerStatus(smk_label)
        q_base[mask] = _annual_base_rate(table, ages[mask], sex_enum, smoker_enum, dur[mask])

    return cells.with_columns(pl.Series(column, q_base, dtype=pl.Float64))


@dataclass(frozen=True)
class SmoothEffect:
    """
    A fitted smooth (spline) effect over a covariate grid, on the A/E multiplier
    scale, with a pointwise confidence band.

    The multiplier is ``exp(η)`` evaluated over the grid with every *other*
    covariate held at its reference level — i.e. the marginal shape of this
    feature's effect on top of the static base table.
    """

    feature: str
    """Name of the covariate (e.g. ``'attained_age'`` or ``'duration_years'``)."""

    grid: np.ndarray
    """Covariate values at which the effect is evaluated, shape (G,)."""

    multiplier: np.ndarray
    """Fitted A/E multiplier ``exp(η)`` at each grid point, shape (G,)."""

    lower: np.ndarray
    """Lower confidence bound on the multiplier, shape (G,)."""

    upper: np.ndarray
    """Upper confidence bound on the multiplier, shape (G,)."""

    confidence_level: float
    """Two-sided confidence level of the band (e.g. 0.95)."""


@dataclass
class GAMFitResult:
    """
    Result of fitting an :class:`ExperienceGAM`.

    Carries the fitted A/E level, the estimated dispersion, and prediction
    helpers for per-feature smooth/factor effects and blended-table export.
    """

    basis: str
    """``'count'`` or ``'amount'`` — which exposure/deaths pair was fit."""

    factors: list[str]
    """Categorical factors that entered the additive model."""

    overall_ae: float
    """Total actual deaths / total expected deaths (exposure * q_base)."""

    dispersion: float
    """Pearson dispersion φ = Pearson χ² / residual df. > 1 signals
    overdispersion; on the by-amount basis the fit is scaled by φ
    (quasi-Poisson) so standard errors and bands widen accordingly."""

    overdispersion_applied: bool
    """Whether the covariance was scaled by φ (quasi-Poisson)."""

    n_cells: int
    """Number of grouped cells in the fit."""

    reference: dict[str, object]
    """Reference covariate values (median smooth, modal factor level) used when
    marginalising a single feature's effect."""

    # Internal fit state (excluded from any serialisation / repr noise).
    _result: object = field(default=None, repr=False)
    _design_info: object = field(default=None, repr=False)
    _smooth_specs: dict[str, str] = field(default_factory=dict, repr=False)

    def _predict_eta(self, frame: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """
        Predict the linear predictor η (offset excluded) and its standard error
        over ``frame``, which must supply every model covariate.

        Returns:
            (eta, se_eta) arrays of shape (len(frame),).
        """
        x = self._design_matrix(frame)
        params = np.asarray(self._result.params, dtype=np.float64)
        cov = np.asarray(self._result.cov_params(), dtype=np.float64)
        eta = x @ params
        se = np.sqrt(np.einsum("ij,jk,ik->i", x, cov, x))
        return eta, se

    def _design_matrix(self, frame: pl.DataFrame) -> np.ndarray:
        """Rebuild the fitted design matrix for ``frame`` (offset excluded)."""
        from patsy import build_design_matrices

        data = {c: frame[c].to_numpy() for c in frame.columns}
        (design,) = build_design_matrices([self._design_info], data)
        return np.asarray(design, dtype=np.float64)

    def _reference_frame(self, n: int) -> dict[str, np.ndarray]:
        """
        Build a length-n covariate frame with every field at its reference.

        The ``__levels__<factor>`` entries in ``self.reference`` are bookkeeping
        lists (the distinct levels of each factor), not covariate values — they
        must be excluded or they produce ragged columns.
        """
        return {
            k: np.repeat(np.asarray([v]), n)
            for k, v in self.reference.items()
            if not k.startswith("__levels__")
        }

    def smooth_effect(
        self,
        feature: str,
        grid: np.ndarray,
        confidence_level: float = 0.95,
    ) -> SmoothEffect:
        """
        Marginal smooth effect of ``feature`` over ``grid`` on the A/E multiplier
        scale, with a pointwise confidence band.

        All other covariates are held at their reference level, so the returned
        multiplier is this feature's contribution to the A/E surface on top of
        the static base table.

        Args:
            feature:          ``'attained_age'`` or ``'duration_years'`` (any
                              smooth term present in the fit).
            grid:             Grid of feature values, shape (G,).
            confidence_level: Two-sided confidence level for the band.

        Returns:
            A :class:`SmoothEffect`.

        Raises:
            PolarisValidationError: If ``feature`` is not a fitted smooth term.
        """
        from scipy.stats import norm

        if feature not in self._smooth_specs:
            raise PolarisValidationError(
                f"'{feature}' is not a fitted smooth term. Available: {sorted(self._smooth_specs)}"
            )
        grid = np.asarray(grid, dtype=np.float64)
        ref = self._reference_frame(len(grid))
        ref[feature] = grid
        frame = pl.DataFrame(ref)
        eta, se = self._predict_eta(frame)
        z = float(norm.ppf(0.5 + confidence_level / 2.0))
        return SmoothEffect(
            feature=feature,
            grid=grid,
            multiplier=np.exp(eta),
            lower=np.exp(eta - z * se),
            upper=np.exp(eta + z * se),
            confidence_level=confidence_level,
        )

    def factor_effect(self, factor: str, confidence_level: float = 0.95) -> pl.DataFrame:
        """
        A/E multiplier per level of a categorical ``factor``, relative to the
        reference level, with a confidence band.

        The multiplier and its band are formed from the **contrast** against the
        reference level, ``eta(level) - eta(ref)``, with all other covariates held at
        their reference. The band is the SE of that contrast (not of the level's
        absolute prediction), so the reference level lands at exactly multiplier
        1.0 with a zero-width band.

        Returns:
            DataFrame with columns ``[factor, multiplier, lower, upper]``; the
            reference level has multiplier 1.0.

        Raises:
            PolarisValidationError: If ``factor`` did not enter the model.
        """
        from scipy.stats import norm

        if factor not in self.factors:
            raise PolarisValidationError(
                f"'{factor}' is not a fitted factor. Available: {self.factors}"
            )
        levels = list(self.reference[f"__levels__{factor}"])  # type: ignore[call-overload]
        n = len(levels)
        base = self._reference_frame(n)
        base[factor] = np.asarray(levels)
        x_levels = self._design_matrix(pl.DataFrame(base))
        x_ref = self._design_matrix(pl.DataFrame(self._reference_frame(1)))

        # Contrast design rows: level prediction minus the reference prediction.
        contrast = x_levels - x_ref
        params = np.asarray(self._result.params, dtype=np.float64)
        cov = np.asarray(self._result.cov_params(), dtype=np.float64)
        rel = contrast @ params
        se = np.sqrt(np.einsum("ij,jk,ik->i", contrast, cov, contrast))
        z = float(norm.ppf(0.5 + confidence_level / 2.0))
        return pl.DataFrame(
            {
                factor: np.asarray(levels),
                "multiplier": np.exp(rel),
                "lower": np.exp(rel - z * se),
                "upper": np.exp(rel + z * se),
            }
        )

    def predict_multiplier(self, cells: pl.DataFrame) -> np.ndarray:
        """A/E multiplier ``exp(η)`` for each supplied cell (offset excluded)."""
        eta, _ = self._predict_eta(cells)
        return np.asarray(np.exp(eta), dtype=np.float64)

    def export_to_mortality_csv(
        self,
        path: str | Path,
        ages: np.ndarray,
        q_base_by_age: np.ndarray,
    ) -> Path:
        """
        Write a blended basexmultiplier annual mortality table in the Polaris
        ultimate-only CSV schema (``age,rate``), evaluating the fitted A/E
        multiplier at the reference covariates for each age.

        The resulting file round-trips through
        :func:`polaris_re.utils.table_io.load_mortality_csv` (select_period=0).

        Args:
            path:          Output CSV path.
            ages:          Contiguous integer ages, shape (A,).
            q_base_by_age: Static annual base rate q_base(age), shape (A,) — the
                           same table used to build the fit offset.

        Returns:
            The written path.

        Raises:
            PolarisValidationError: If ages/rates lengths differ, ages are not
                contiguous, or any blended rate falls outside [0, 1].
        """
        ages = np.asarray(ages)
        q_base_by_age = np.asarray(q_base_by_age, dtype=np.float64)
        if len(ages) != len(q_base_by_age):
            raise PolarisValidationError("ages and q_base_by_age must have equal length.")
        expected_ages = np.arange(int(ages.min()), int(ages.max()) + 1)
        if len(ages) != len(expected_ages) or not np.array_equal(ages.astype(int), expected_ages):
            raise PolarisValidationError("ages must be contiguous integers with no gaps.")

        ref = self._reference_frame(len(ages))
        ref["attained_age"] = ages.astype(np.float64)
        frame = pl.DataFrame(ref)
        mult = self.predict_multiplier(frame)
        blended = q_base_by_age * mult
        if np.any(blended < 0.0) or np.any(blended > 1.0):
            raise PolarisValidationError(
                "Blended basexmultiplier rates fell outside [0, 1]; check the base "
                "table and fitted multiplier."
            )

        path = Path(path)
        pl.DataFrame({"age": ages.astype(np.int64), "rate": blended.astype(np.float64)}).write_csv(
            path
        )
        return path


class ExperienceGAM:
    """
    Interpretable additive A/E model over grouped experience cells.

    Fits ``deaths ~ offset(log[exposure * q_base]) + s(attained_age)
    + s(duration_years) + Σ factors`` with a Poisson (by-count) or quasi-Poisson
    (by-amount) family, isolating each standard feature's smooth/categorical
    contribution to the A/E multiplier surface.

    Args:
        cells:          Grouped-cell DataFrame in the canonical contract. Must
                        carry ``attained_age``, a ``q_base`` annual base rate (see
                        :func:`attach_base_rate`), and the exposure/deaths pair for
                        ``basis``. ``duration_months`` and any of the candidate
                        factors are used when present and varying.
        basis:          ``'count'`` (policy count) or ``'amount'`` (face-weighted).
        age_df:         Spline degrees of freedom for the attained-age smooth.
        duration_df:    Spline degrees of freedom for the duration smooth.
        overdispersion: Scale the covariance by the Pearson dispersion φ
                        (quasi-Poisson). ``None`` (default) enables it for the
                        by-amount basis and disables it for by-count.

    Raises:
        PolarisValidationError: On a missing/invalid contract.
    """

    REQUIRED_ALWAYS: ClassVar[set[str]] = {"attained_age", "q_base"}

    def __init__(
        self,
        cells: pl.DataFrame,
        *,
        basis: str = "count",
        age_df: int = 6,
        duration_df: int = 4,
        overdispersion: bool | None = None,
    ) -> None:
        if basis not in {"count", "amount"}:
            raise PolarisValidationError(f"basis must be 'count' or 'amount', got {basis!r}.")
        exposure_col, deaths_col = COUNT_MEASURES if basis == "count" else AMOUNT_MEASURES
        required = self.REQUIRED_ALWAYS | {exposure_col, deaths_col}
        missing = required - set(cells.columns)
        if missing:
            raise PolarisValidationError(
                f"Grouped cells missing required columns for basis={basis!r}: {missing}"
            )
        if cells.height == 0:
            raise PolarisValidationError("Grouped cells DataFrame is empty.")

        q_base = cells["q_base"].to_numpy().astype(np.float64)
        if np.any(q_base <= 0.0) or np.any(q_base > 1.0):
            raise PolarisValidationError("q_base must lie in (0, 1] for every cell.")

        self.cells = cells
        self.basis = basis
        self.exposure_col = exposure_col
        self.deaths_col = deaths_col
        self.age_df = age_df
        self.duration_df = duration_df
        self.overdispersion = (basis == "amount") if overdispersion is None else overdispersion

    @staticmethod
    def _require_backend() -> object:
        """Lazily import statsmodels, raising an actionable error when [ml] absent."""
        try:
            import statsmodels.api as sm
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
            raise PolarisComputationError(
                "ExperienceGAM requires 'statsmodels' (the [ml] optional extra). "
                "Install it with: uv sync --extra ml"
            ) from exc
        return sm

    def _build_frame(self) -> tuple[pl.DataFrame, list[str]]:
        """Assemble the modelling frame and the list of active factors."""
        frame = self.cells
        # duration in years for the smooth (primary duration effect is in q_base).
        if "duration_months" in frame.columns:
            frame = frame.with_columns((pl.col("duration_months") / 12.0).alias("duration_years"))
        # Active factors: present, categorical, with >1 distinct level.
        factors = [f for f in _CANDIDATE_FACTORS if f in frame.columns and frame[f].n_unique() > 1]
        return frame, factors

    def _formula_terms(self, frame: pl.DataFrame, factors: list[str]) -> tuple[str, dict[str, str]]:
        """Return (rhs formula string, smooth-spec map)."""
        smooth_specs: dict[str, str] = {}
        terms: list[str] = []
        # Attained-age smooth is always present.
        age_spec = f"bs(attained_age, df={self.age_df})"
        terms.append(age_spec)
        smooth_specs["attained_age"] = age_spec
        # Duration smooth only if duration varies.
        if "duration_years" in frame.columns and frame["duration_years"].n_unique() > 1:
            dur_spec = f"bs(duration_years, df={self.duration_df})"
            terms.append(dur_spec)
            smooth_specs["duration_years"] = dur_spec
        for f in factors:
            terms.append(f"C({f})")
        rhs = " + ".join(terms)
        return rhs, smooth_specs

    def _reference(self, frame: pl.DataFrame, factors: list[str]) -> dict[str, object]:
        """Reference covariates: median smooth values, modal factor level."""
        ref: dict[str, object] = {}
        ref["attained_age"] = float(np.median(frame["attained_age"].to_numpy()))
        if "duration_years" in frame.columns:
            ref["duration_years"] = float(np.median(frame["duration_years"].to_numpy()))
        for f in factors:
            # Modal level (exposure-weighted would be nicer; count mode is fine
            # and deterministic).
            vc = frame.group_by(f).len().sort("len", descending=True)
            modal = vc[f][0]
            ref[f] = modal
            ref[f"__levels__{f}"] = sorted(frame[f].unique().to_list())
        return ref

    def fit(self) -> GAMFitResult:
        """
        Fit the additive A/E GAM and return a :class:`GAMFitResult`.

        Raises:
            PolarisComputationError: If ``statsmodels`` is unavailable or the fit
                fails to converge.
        """
        sm = self._require_backend()
        from patsy import dmatrix

        frame, factors = self._build_frame()
        rhs, smooth_specs = self._formula_terms(frame, factors)

        data = {c: frame[c].to_numpy() for c in frame.columns}
        design = dmatrix(rhs, data, return_type="dataframe")
        design_info = design.design_info
        x = np.asarray(design, dtype=np.float64)

        exposure = frame[self.exposure_col].to_numpy().astype(np.float64)
        deaths = frame[self.deaths_col].to_numpy().astype(np.float64)
        q_base = frame["q_base"].to_numpy().astype(np.float64)
        expected = exposure * q_base
        if np.any(expected <= 0.0):
            raise PolarisValidationError(
                "Every cell must have positive exposure * q_base to form the offset."
            )
        offset = np.log(expected)

        model = sm.GLM(deaths, x, family=sm.families.Poisson(), offset=offset)
        # scale="X2" is the quasi-Poisson dispersion (Pearson phi): widens SEs
        # under overdispersion. Plain Poisson otherwise.
        result = model.fit(scale="X2") if self.overdispersion else model.fit()
        if not getattr(result, "converged", True):
            raise PolarisComputationError("Experience GAM fit did not converge.")

        dispersion = float(result.pearson_chi2 / result.df_resid)
        overall_ae = float(deaths.sum() / expected.sum())
        reference = self._reference(frame, factors)

        return GAMFitResult(
            basis=self.basis,
            factors=factors,
            overall_ae=overall_ae,
            dispersion=dispersion,
            overdispersion_applied=self.overdispersion,
            n_cells=frame.height,
            reference=reference,
            _result=result,
            _design_info=design_info,
            _smooth_specs=smooth_specs,
        )


# --- Slice 2a: tensor mortality-improvement (MI) surface -------------------------

# Columns that determine the *static* select-and-ultimate base rate q_base(x, d).
# The generational-base guard groups by these: within an otherwise-identical cell,
# a static base is constant across calendar years, a generational one is not.
_QBASE_DETERMINANTS: tuple[str, ...] = ("attained_age", "duration_months", "sex", "smoker")


def _predict_eta_se(
    result: object,
    design_info: object,
    frame: pl.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rebuild the fitted design matrix for ``frame`` (offset excluded) and return
    ``(design, eta, se_eta)``.

    The stateful ``patsy`` transforms captured in ``design_info`` reuse the
    *fitted* spline knots, so predictions on a fresh grid are consistent with the
    fit. ``se_eta`` is the linear-predictor standard error from the parameter
    covariance — the frequentist analogue of a posterior SE.
    """
    from patsy import build_design_matrices

    data = {c: frame[c].to_numpy() for c in frame.columns}
    (design_obj,) = build_design_matrices([design_info], data)
    design = np.asarray(design_obj, dtype=np.float64)
    params = np.asarray(result.params, dtype=np.float64)  # type: ignore[attr-defined]
    cov = np.asarray(result.cov_params(), dtype=np.float64)  # type: ignore[attr-defined]
    eta = design @ params
    se = np.sqrt(np.einsum("ij,jk,ik->i", design, cov, design))
    return design, eta, se


def _assert_static_base(cells: pl.DataFrame, tol: float = 1e-9) -> None:
    """
    Guard: verify the ``q_base`` offset is a *static* single-reference-year table,
    not a generational/projected one (Design Anchor 1).

    Groups cells by the base-rate determinants (attained age, duration, sex,
    smoker) and checks that ``q_base`` is constant across calendar years within
    each group. A generational base varies with calendar year for a fixed
    (age, duration, sex, smoker), which would make the fitted calendar gradient
    *residual-vs-assumed* improvement rather than the improvement itself.

    Raises:
        PolarisValidationError: If any group's ``q_base`` spread exceeds ``tol``,
            or if there is no calendar variation to test the guard against.
    """
    determinants = [c for c in _QBASE_DETERMINANTS if c in cells.columns]
    if "calendar_year" not in cells.columns:
        raise PolarisValidationError("TensorMIModel requires a 'calendar_year' column.")
    if not determinants:
        # Nothing to group on — cannot verify staticness; treat as a contract error.
        raise PolarisValidationError(
            "Cannot verify a static base offset without at least an 'attained_age' column."
        )
    spread = (
        cells.group_by(determinants)
        .agg(
            (pl.col("q_base").max() - pl.col("q_base").min()).alias("_spread"),
            pl.col("calendar_year").n_unique().alias("_n_years"),
        )
        .filter(pl.col("_n_years") > 1)
    )
    if spread.height == 0:
        raise PolarisValidationError(
            "No (age, duration, sex, smoker) cell spans multiple calendar years, so the "
            "static-base guard cannot run and the calendar/improvement trend is not "
            "identifiable. Supply experience covering >1 calendar year per covariate cell."
        )
    max_spread = float(spread["_spread"].max())
    if max_spread > tol:
        raise PolarisValidationError(
            f"q_base varies by up to {max_spread:.3g} across calendar years within a fixed "
            "(age, duration, sex, smoker) cell — the base offset looks generational, not "
            "static. Fit the MI surface against a single-reference-year base table (Anchor 1), "
            "or pass allow_generational_base=True to override (the fitted trend will then be "
            "residual-vs-assumed improvement, not improvement)."
        )


@dataclass(frozen=True)
class MISurface:
    """
    A fitted mortality-improvement surface: the annual improvement rate
    ``MI_x(y)`` over an age x calendar-year grid, with a pointwise confidence band.

    ``MI_x(y) = 1 - exp[te(x, y) - te(x, y-1)]`` is the fraction by which the
    A/E-implied mortality at attained age ``x`` falls going from calendar year
    ``y-1`` to ``y`` (positive = improving/declining mortality). Each ``years[j]``
    is the *end* year of an annual step, so ``mi_grid`` has one fewer column than
    the calendar range spanned. This plugs into
    ``MortalityImprovement.apply_improvement`` as ``q(Y) = q(base) * Π (1 - MI)``
    (the ``MortalityImprovement``-compatible export lands in Slice 2b/2c).
    """

    ages: np.ndarray
    """Attained ages of the surface rows, shape (A,), int."""

    years: np.ndarray
    """End year of each annual improvement step, shape (Y,), int."""

    mi_grid: np.ndarray
    """Annual improvement rate ``MI_x(y)``, shape (A, Y), float64."""

    mi_lower: np.ndarray
    """Lower confidence bound on ``MI_x(y)``, shape (A, Y), float64."""

    mi_upper: np.ndarray
    """Upper confidence bound on ``MI_x(y)``, shape (A, Y), float64."""

    confidence_level: float
    """Two-sided confidence level of the band (e.g. 0.95)."""

    def to_frame(self) -> pl.DataFrame:
        """Long-format DataFrame with columns ``[attained_age, calendar_year,
        mi, mi_lower, mi_upper]`` — one row per (age, step-end-year)."""
        a = np.repeat(self.ages, len(self.years))
        y = np.tile(self.years, len(self.ages))
        return pl.DataFrame(
            {
                "attained_age": a.astype(np.int64),
                "calendar_year": y.astype(np.int64),
                "mi": self.mi_grid.reshape(-1).astype(np.float64),
                "mi_lower": self.mi_lower.reshape(-1).astype(np.float64),
                "mi_upper": self.mi_upper.reshape(-1).astype(np.float64),
            }
        )


@dataclass
class MISurfaceResult:
    """
    Result of fitting a :class:`TensorMIModel`.

    Carries the fitted overall A/E level and prediction helpers to extract the
    ``MI_x(y)`` improvement surface with confidence bands.
    """

    basis: str
    """``'count'`` or ``'amount'`` — which exposure/deaths pair was fit."""

    factors: list[str]
    """Categorical factors that entered the additive model."""

    age_varying: bool
    """Whether the age x calendar tensor interaction was included (age-varying MI)
    vs a separable age + calendar model (improvement constant across age)."""

    overall_ae: float
    """Total actual deaths / total expected deaths (exposure * q_base)."""

    dispersion: float
    """Pearson dispersion φ = Pearson χ² / residual df."""

    overdispersion_applied: bool
    """Whether the covariance was scaled by φ (quasi-Poisson)."""

    n_cells: int
    """Number of grouped cells in the fit."""

    observed_ages: tuple[int, int]
    """(min, max) attained age observed in the fit."""

    observed_years: tuple[int, int]
    """(min, max) calendar year observed in the fit."""

    reference: dict[str, object]
    """Reference covariate values (median smooth, modal factor level) used when
    marginalising the surface over duration and factors."""

    _result: object = field(default=None, repr=False)
    _design_info: object = field(default=None, repr=False)

    def _reference_frame(self, n: int) -> dict[str, np.ndarray]:
        """Length-n covariate frame with every field at its reference (excluding
        the ``__levels__`` bookkeeping entries)."""
        return {
            k: np.repeat(np.asarray([v]), n)
            for k, v in self.reference.items()
            if not k.startswith("__levels__")
        }

    def improvement_surface(
        self,
        ages: np.ndarray | None = None,
        years: np.ndarray | None = None,
        confidence_level: float = 0.95,
    ) -> MISurface:
        """
        Extract the annual improvement grid ``MI_x(y)`` with a pointwise band.

        For each attained age and each annual step ``y-1 -> y``, the improvement is
        ``1 - exp(d)`` where ``d = η(x, y) - η(x, y-1)`` is the year-to-year change
        in the linear predictor with every non-calendar covariate held at its
        reference. Because those non-calendar terms and the base offset are
        calendar-invariant, they cancel in ``d`` — so the grid is exactly the
        fitted calendar/tensor trend regardless of the reference choice. The band
        is the delta-method interval from the covariance of the linear contrast.

        Args:
            ages:             Contiguous integer ages; defaults to the observed
                              attained-age range.
            years:            Contiguous integer calendar years; defaults to the
                              observed calendar-year range. Improvement is reported
                              for the interior steps, so the returned surface spans
                              ``years[1:]``.
            confidence_level: Two-sided confidence level for the band.

        Returns:
            An :class:`MISurface` of shape (len(ages), len(years) - 1).

        Raises:
            PolarisValidationError: If fewer than two calendar years are supplied.
        """
        from scipy.stats import norm

        if ages is None:
            ages = np.arange(self.observed_ages[0], self.observed_ages[1] + 1)
        if years is None:
            years = np.arange(self.observed_years[0], self.observed_years[1] + 1)
        ages = np.asarray(ages).astype(np.int64)
        years = np.asarray(years).astype(np.int64)
        if len(years) < 2:
            raise PolarisValidationError(
                "improvement_surface needs at least two calendar years to form an "
                "annual improvement step."
            )

        n_age, n_year = len(ages), len(years)
        grid_age = np.repeat(ages, n_year).astype(np.float64)
        grid_year = np.tile(years, n_age).astype(np.float64)
        ref = self._reference_frame(n_age * n_year)
        ref["attained_age"] = grid_age
        ref["calendar_year"] = grid_year
        frame = pl.DataFrame(ref)

        design, eta, _ = _predict_eta_se(self._result, self._design_info, frame)
        p = design.shape[1]
        design = design.reshape(n_age, n_year, p)
        eta = eta.reshape(n_age, n_year)

        # Annual step contrasts: d[a, j] = η(a, year_j) - η(a, year_{j-1}).
        d = eta[:, 1:] - eta[:, :-1]  # (A, Y-1)
        contrast = design[:, 1:, :] - design[:, :-1, :]  # (A, Y-1, p)
        cov = np.asarray(self._result.cov_params(), dtype=np.float64)  # type: ignore[attr-defined]
        var = np.einsum("ayp,pq,ayq->ay", contrast, cov, contrast)
        se = np.sqrt(np.clip(var, 0.0, None))

        z = float(norm.ppf(0.5 + confidence_level / 2.0))
        mi = 1.0 - np.exp(d)
        # d larger => smaller MI, so the +z*se side is the lower MI bound.
        mi_lower = 1.0 - np.exp(d + z * se)
        mi_upper = 1.0 - np.exp(d - z * se)
        return MISurface(
            ages=ages,
            years=years[1:],
            mi_grid=mi.astype(np.float64),
            mi_lower=mi_lower.astype(np.float64),
            mi_upper=mi_upper.astype(np.float64),
            confidence_level=confidence_level,
        )


class TensorMIModel:
    """
    Age-varying mortality-improvement surface over grouped experience cells.

    Fits ``deaths ~ offset(log[exposure * q_base]) + te(attained_age, calendar_year)
    + s(duration_years) + Σ factors`` with a Poisson (by-count) or quasi-Poisson
    (by-amount) family, where ``te(attained_age, calendar_year)`` is a
    tensor-product B-spline surface. The calendar gradient of that surface is the
    fitted mortality improvement; :meth:`MISurfaceResult.improvement_surface`
    turns it into the ``MI_x(y)`` grid.

    Identifiability (Design Anchor 3): the model carries **no issue-year term**, so
    the calendar gradient is attributed to improvement by construction (issue-year
    term constrained to zero). A cedant with a known underwriting change can add an
    ``underwriting_era`` column, which enters as an ordinary factor.

    Args:
        cells:            Grouped cells in the canonical contract. Must carry
                          ``attained_age``, ``calendar_year`` (>1 distinct value),
                          a static ``q_base`` (see :func:`attach_base_rate`), and
                          the exposure/deaths pair for ``basis``.
        basis:            ``'count'`` or ``'amount'``.
        age_df:           Spline df for the attained-age margin.
        year_df:          Spline df for the calendar-year margin (the trend).
        duration_df:      Spline df for the residual duration smooth (when it varies).
        age_varying:      Include the age x calendar tensor interaction (age-varying
                          improvement). ``False`` fits a separable age + calendar
                          model (improvement constant across age).
        overdispersion:   Scale the covariance by the Pearson dispersion φ
                          (quasi-Poisson). ``None`` enables it for the by-amount
                          basis and disables it for by-count.
        allow_generational_base: Skip the static-base guard (Anchor 1). The fitted
                          trend then measures residual-vs-assumed improvement.

    Raises:
        PolarisValidationError: On a missing/invalid contract or a non-static base.
    """

    REQUIRED_ALWAYS: ClassVar[set[str]] = {"attained_age", "calendar_year", "q_base"}

    def __init__(
        self,
        cells: pl.DataFrame,
        *,
        basis: str = "count",
        age_df: int = 6,
        year_df: int = 4,
        duration_df: int = 4,
        age_varying: bool = True,
        overdispersion: bool | None = None,
        allow_generational_base: bool = False,
    ) -> None:
        if basis not in {"count", "amount"}:
            raise PolarisValidationError(f"basis must be 'count' or 'amount', got {basis!r}.")
        exposure_col, deaths_col = COUNT_MEASURES if basis == "count" else AMOUNT_MEASURES
        required = self.REQUIRED_ALWAYS | {exposure_col, deaths_col}
        missing = required - set(cells.columns)
        if missing:
            raise PolarisValidationError(
                f"Grouped cells missing required columns for basis={basis!r}: {missing}"
            )
        if cells.height == 0:
            raise PolarisValidationError("Grouped cells DataFrame is empty.")
        if cells["calendar_year"].n_unique() < 2:
            raise PolarisValidationError(
                "TensorMIModel needs >1 distinct calendar_year to identify an improvement trend."
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
        self.age_df = age_df
        self.year_df = year_df
        self.duration_df = duration_df
        self.age_varying = age_varying
        self.overdispersion = (basis == "amount") if overdispersion is None else overdispersion
        self.allow_generational_base = allow_generational_base

    def _build_frame(self) -> tuple[pl.DataFrame, list[str]]:
        """Assemble the modelling frame (adds ``duration_years``) and active factors."""
        frame = self.cells
        if "duration_months" in frame.columns:
            frame = frame.with_columns((pl.col("duration_months") / 12.0).alias("duration_years"))
        factors = [f for f in _CANDIDATE_FACTORS if f in frame.columns and frame[f].n_unique() > 1]
        return frame, factors

    def _formula(self, frame: pl.DataFrame, factors: list[str]) -> str:
        """Right-hand-side patsy formula for the tensor-MI model."""
        age_term = f"bs(attained_age, df={self.age_df})"
        year_term = f"bs(calendar_year, df={self.year_df})"
        terms = [age_term, year_term]
        if self.age_varying:
            # Tensor-product interaction => age-varying improvement surface.
            terms.append(f"{age_term}:{year_term}")
        if "duration_years" in frame.columns and frame["duration_years"].n_unique() > 1:
            terms.append(f"bs(duration_years, df={self.duration_df})")
        terms.extend(f"C({f})" for f in factors)
        return " + ".join(terms)

    def _reference(self, frame: pl.DataFrame, factors: list[str]) -> dict[str, object]:
        """Reference covariates: median duration, modal factor level. Attained age
        and calendar year are supplied per-grid-point by the surface extractor.

        Unlike ``GAMFitResult`` (which keeps ``__levels__<factor>`` lists for its
        per-level ``factor_effect`` contrasts), the MI surface never marginalises a
        single factor's levels — the year-to-year contrast cancels every
        calendar-invariant term — so only the modal reference level is stored."""
        ref: dict[str, object] = {}
        ref["attained_age"] = float(np.median(frame["attained_age"].to_numpy()))
        ref["calendar_year"] = float(np.median(frame["calendar_year"].to_numpy()))
        if "duration_years" in frame.columns:
            ref["duration_years"] = float(np.median(frame["duration_years"].to_numpy()))
        for f in factors:
            vc = frame.group_by(f).len().sort("len", descending=True)
            ref[f] = vc[f][0]
        return ref

    def fit(self) -> MISurfaceResult:
        """
        Fit the tensor-MI model and return a :class:`MISurfaceResult`.

        Raises:
            PolarisComputationError: If ``statsmodels`` is unavailable or the fit
                fails to converge.
        """
        sm = ExperienceGAM._require_backend()
        from patsy import dmatrix

        frame, factors = self._build_frame()
        rhs = self._formula(frame, factors)

        data = {c: frame[c].to_numpy() for c in frame.columns}
        design = dmatrix(rhs, data, return_type="dataframe")
        design_info = design.design_info
        x = np.asarray(design, dtype=np.float64)

        exposure = frame[self.exposure_col].to_numpy().astype(np.float64)
        deaths = frame[self.deaths_col].to_numpy().astype(np.float64)
        q_base = frame["q_base"].to_numpy().astype(np.float64)
        expected = exposure * q_base
        if np.any(expected <= 0.0):
            raise PolarisValidationError(
                "Every cell must have positive exposure * q_base to form the offset."
            )
        offset = np.log(expected)

        model = sm.GLM(deaths, x, family=sm.families.Poisson(), offset=offset)
        result = model.fit(scale="X2") if self.overdispersion else model.fit()
        if not getattr(result, "converged", True):
            raise PolarisComputationError("Tensor MI model fit did not converge.")

        dispersion = float(result.pearson_chi2 / result.df_resid)
        overall_ae = float(deaths.sum() / expected.sum())
        cal = self.cells["calendar_year"].to_numpy()
        age = self.cells["attained_age"].to_numpy()

        return MISurfaceResult(
            basis=self.basis,
            factors=factors,
            age_varying=self.age_varying,
            overall_ae=overall_ae,
            dispersion=dispersion,
            overdispersion_applied=self.overdispersion,
            n_cells=frame.height,
            observed_ages=(int(age.min()), int(age.max())),
            observed_years=(int(cal.min()), int(cal.max())),
            reference=self._reference(frame, factors),
            _result=result,
            _design_info=design_info,
        )
