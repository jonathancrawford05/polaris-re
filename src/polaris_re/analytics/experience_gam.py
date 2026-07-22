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
    "BayesianMISurfaceResult",
    "BayesianTensorMIModel",
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


# --- Bayesian reduced-rank-GP (HSGP) tensor MI surface (Slice 2b) ----------------
#
# The Bayesian analogue of ``TensorMIModel``. Where the frequentist model fits a
# tensor-product B-spline and reports a *delta-method* band, this fits an
# anisotropic Gaussian-process surface ``te(attained_age, calendar_year)`` and
# reports honest **posterior credible intervals** on ``MI_x(y)``.
#
# The GP is represented by its Hilbert-space reduced-rank (HSGP) expansion (Solin
# & Sarkka 2020): on a centred, scaled box ``[-L, L]`` the Laplacian eigenfunctions
# ``phi_j(x) = L**-0.5 sin(pi j (x + L) / (2L))`` with eigenvalues
# ``lambda_j = (pi j / (2L))**2`` form a fixed basis, and a stationary GP prior
# becomes independent coefficients ``beta_j ~ Normal(0, prior_scale**2 * S(sqrt(lambda_j)))``
# where ``S`` is the Matern-5/2 spectral density. This turns the GP into a
# penalised-Poisson GLM that is fit deterministically by Newton/IRLS to its MAP,
# with a closed-form **Laplace** posterior covariance ``(X'WX + P)^-1``. No MCMC,
# no compile-heavy sampler dependency — the whole surface is pure NumPy/SciPy, so
# it ships in the core install and keeps CI lean and the suite deterministic.
#
# (ADR-141 records why this is the tested default backend rather than the
# ``bambi``/``pymc`` HSGP the PLAN anticipated: the ``inference_method="laplace"``
# path of ``bambi`` 0.19 / ``pymc`` 6.1 raises a ``NullTypeGradError`` on an HSGP
# term combined with an ``offset`` term, and full NUTS is non-deterministic and too
# slow for CI. The reduced-rank expansion above is the identical GP math done in
# closed form. A ``pymc``-NUTS audit backend is deferred to the projection slice.)


def _rrgp_eigenbasis_1d(
    xn: np.ndarray, boundary: float, n_basis: int
) -> tuple[np.ndarray, np.ndarray]:
    """Hilbert-space GP eigenbasis on ``[-boundary, boundary]``.

    Returns ``(phi, sqrt_lambda)`` where ``phi`` has shape ``(len(xn), n_basis)``
    and ``sqrt_lambda`` holds the square-rooted eigenvalues (the spectral
    frequencies the density is evaluated at). ``xn`` must be the centred, scaled
    coordinate; ``boundary`` must exceed ``max(|xn|)`` for the expansion to be
    valid (the caller enforces this via ``boundary_factor``).
    """
    j = np.arange(1, n_basis + 1, dtype=np.float64)
    sqrt_lambda = np.pi * j / (2.0 * boundary)
    phi = (1.0 / np.sqrt(boundary)) * np.sin(np.outer(xn + boundary, sqrt_lambda))
    return phi, sqrt_lambda


def _matern52_spectral_density(omega: np.ndarray, length_scale: float) -> np.ndarray:
    """1-D Matern-5/2 spectral density ``S(omega)`` (unit marginal variance).

    ``S(w) = c * (2*nu/l**2 + w**2)**-(nu + d/2)`` with ``nu = 5/2``, ``d = 1``.
    The overall amplitude is carried separately by ``prior_scale``; this returns
    the *shape* that down-weights high-frequency eigenfunctions (larger
    ``length_scale`` => faster decay => smoother surface).
    """
    from scipy.special import gamma

    nu, dim = 2.5, 1
    kappa = 2.0 * nu / length_scale**2
    coef = (2.0**dim * np.pi ** (dim / 2.0) * gamma(nu + dim / 2.0) * (2.0 * nu) ** nu) / (
        gamma(nu) * length_scale ** (2.0 * nu)
    )
    return coef * (kappa + omega**2) ** (-(nu + dim / 2.0))


@dataclass(frozen=True)
class _RRGPSpec:
    """Fixed design specification for the reduced-rank-GP MI surface.

    Captured at fit time so the identical basis (same centring, boundary,
    length-scales, eigenfunction count, and factor level maps) can be rebuilt on
    an arbitrary prediction grid. All GP coordinates are standardised to unit
    standard deviation; ``boundary`` is in those standardised units.
    """

    age_center: float
    age_scale: float
    age_boundary: float
    age_basis: int
    age_length_scale: float
    year_center: float
    year_scale: float
    year_boundary: float
    year_basis: int
    year_length_scale: float
    prior_scale: float
    age_varying: bool
    duration_center: float | None
    duration_scale: float | None
    duration_boundary: float | None
    duration_basis: int
    duration_length_scale: float
    factor_levels: dict[str, list[object]]

    def _gp_block_1d(
        self,
        values: np.ndarray,
        center: float,
        scale: float,
        boundary: float,
        n_basis: int,
        ls: float,
    ) -> np.ndarray:
        xn = (np.asarray(values, dtype=np.float64) - center) / scale
        phi, sqrt_lambda = _rrgp_eigenbasis_1d(xn, boundary, n_basis)
        sd = np.sqrt(_matern52_spectral_density(sqrt_lambda, ls))
        return phi * sd[None, :]

    def design(self, cols: dict[str, np.ndarray]) -> np.ndarray:
        """Assemble the model matrix for the given columns.

        Column order (fixed): intercept, age main effect, year main effect,
        [age x year interaction if ``age_varying``], [duration smooth if active],
        then one dummy per non-baseline level of each factor. Every GP block is
        pre-scaled by the square-root spectral density so its coefficients carry
        the shared ``Normal(0, prior_scale**2)`` prior.
        """
        n = len(cols["attained_age"])
        blocks = [np.ones((n, 1), dtype=np.float64)]
        age_b = self._gp_block_1d(
            cols["attained_age"],
            self.age_center,
            self.age_scale,
            self.age_boundary,
            self.age_basis,
            self.age_length_scale,
        )
        year_b = self._gp_block_1d(
            cols["calendar_year"],
            self.year_center,
            self.year_scale,
            self.year_boundary,
            self.year_basis,
            self.year_length_scale,
        )
        blocks.append(age_b)
        blocks.append(year_b)
        if self.age_varying:
            # Separable Matern tensor: the (i, j) product basis carries prior sd
            # sqrt(S_age_i * S_year_j) = (scaled age col i) * (scaled year col j).
            inter = np.einsum("ni,nj->nij", age_b, year_b).reshape(n, -1)
            blocks.append(inter)
        if self.duration_center is not None and "duration_years" in cols:
            blocks.append(
                self._gp_block_1d(
                    cols["duration_years"],
                    self.duration_center,
                    self.duration_scale,
                    self.duration_boundary,
                    self.duration_basis,
                    self.duration_length_scale,
                )
            )
        for factor, levels in self.factor_levels.items():
            col = np.asarray(cols[factor])
            for lvl in levels[1:]:  # drop-first dummy encoding
                blocks.append((col == lvl).astype(np.float64)[:, None])
        return np.concatenate(blocks, axis=1)

    def precision(self) -> np.ndarray:
        """Prior precision (ridge) for every design column.

        GP coefficients (age, year, interaction, duration) share
        ``1 / prior_scale**2``; the intercept and factor dummies get a near-flat
        ``1e-6`` so they are effectively unpenalised.
        """
        gp_prec = 1.0 / self.prior_scale**2
        parts = [np.array([1e-6])]  # intercept
        parts.append(np.full(self.age_basis, gp_prec))
        parts.append(np.full(self.year_basis, gp_prec))
        if self.age_varying:
            parts.append(np.full(self.age_basis * self.year_basis, gp_prec))
        if self.duration_center is not None:
            parts.append(np.full(self.duration_basis, gp_prec))
        n_dummies = sum(len(levels) - 1 for levels in self.factor_levels.values())
        parts.append(np.full(n_dummies, 1e-6))
        return np.concatenate(parts)


@dataclass
class BayesianMISurfaceResult:
    """
    Result of fitting a :class:`BayesianTensorMIModel`.

    Carries the MAP coefficients and their Laplace posterior covariance, and
    extracts the ``MI_x(y)`` improvement surface with honest **posterior credible
    intervals** (the Bayesian analogue of :class:`MISurfaceResult`'s delta-method
    band). Because the year-to-year contrast is linear in the coefficients, the
    credible interval propagates the Laplace covariance through the contrast and
    the ``1 - exp(.)`` link exactly.
    """

    basis: str
    """``'count'`` or ``'amount'`` — which exposure/deaths pair was fit."""

    factors: list[str]
    """Categorical factors that entered the additive model."""

    age_varying: bool
    """Whether the age x calendar interaction was included (age-varying MI) vs a
    separable age + calendar model (improvement constant across age)."""

    overall_ae: float
    """Total actual deaths / total expected deaths (exposure * q_base)."""

    dispersion: float
    """Pearson dispersion phi = Pearson chi-squared / effective residual df."""

    overdispersion_applied: bool
    """Whether the posterior covariance was scaled by phi (quasi-Poisson)."""

    effective_df: float
    """Effective degrees of freedom trace(H0 @ H^-1) — the penalised model size."""

    n_cells: int
    """Number of grouped cells in the fit."""

    observed_ages: tuple[int, int]
    """(min, max) attained age observed in the fit."""

    observed_years: tuple[int, int]
    """(min, max) calendar year observed in the fit."""

    prior_scale: float
    """GP amplitude / coefficient prior standard deviation used."""

    length_scales: dict[str, float]
    """Standardised-coordinate length-scales per GP dimension."""

    reference: dict[str, object]
    """Reference covariate values (median duration, modal factor level)."""

    _spec: _RRGPSpec = field(default=None, repr=False)  # type: ignore[assignment]
    _theta: np.ndarray = field(default=None, repr=False)  # type: ignore[assignment]
    _cov: np.ndarray = field(default=None, repr=False)  # type: ignore[assignment]

    def _grid_cols(self, ages: np.ndarray, years: np.ndarray) -> dict[str, np.ndarray]:
        """Build the covariate columns for an (age x year) grid with every
        non-surface covariate held at its reference (they cancel in the
        year-to-year contrast, so the choice does not affect the surface)."""
        n_age, n_year = len(ages), len(years)
        cols: dict[str, np.ndarray] = {
            "attained_age": np.repeat(ages, n_year).astype(np.float64),
            "calendar_year": np.tile(years, n_age).astype(np.float64),
        }
        for k, v in self.reference.items():
            if k in ("attained_age", "calendar_year"):
                continue
            cols[k] = np.repeat(np.asarray([v]), n_age * n_year)
        return cols

    def improvement_surface(
        self,
        ages: np.ndarray | None = None,
        years: np.ndarray | None = None,
        credible_level: float = 0.95,
    ) -> MISurface:
        """
        Extract the annual improvement grid ``MI_x(y)`` with a posterior credible
        band.

        For each attained age and annual step ``y-1 -> y`` the improvement is
        ``1 - exp(d)`` with ``d = eta(x, y) - eta(x, y-1)``. ``d`` is a linear
        contrast of the coefficients, so its posterior (under the Laplace
        approximation) is Gaussian with variance ``c' Cov c``; the band is the
        equal-tailed ``credible_level`` interval mapped through ``1 - exp(.)``.
        Every calendar-invariant term (intercept, age main effect, factors,
        duration) cancels in ``d``, so the surface is exactly the fitted
        calendar/tensor trend regardless of the reference covariates.

        Args:
            ages:           Contiguous integer ages; defaults to the observed range.
            years:          Contiguous integer calendar years; defaults to the
                            observed range. Improvement is reported for interior
                            steps, so the surface spans ``years[1:]``.
            credible_level: Two-sided posterior credible level for the band.

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
        design = self._spec.design(self._grid_cols(ages, years))
        p = design.shape[1]
        design = design.reshape(n_age, n_year, p)
        eta = (design @ self._theta).reshape(n_age, n_year)

        d = eta[:, 1:] - eta[:, :-1]
        contrast = design[:, 1:, :] - design[:, :-1, :]
        var = np.einsum("ayp,pq,ayq->ay", contrast, self._cov, contrast)
        se = np.sqrt(np.clip(var, 0.0, None))

        z = float(norm.ppf(0.5 + credible_level / 2.0))
        mi = 1.0 - np.exp(d)
        mi_lower = 1.0 - np.exp(d + z * se)
        mi_upper = 1.0 - np.exp(d - z * se)
        return MISurface(
            ages=ages,
            years=years[1:],
            mi_grid=mi.astype(np.float64),
            mi_lower=mi_lower.astype(np.float64),
            mi_upper=mi_upper.astype(np.float64),
            confidence_level=credible_level,
        )


class BayesianTensorMIModel:
    """
    Bayesian anisotropic-GP mortality-improvement surface over grouped cells.

    The Bayesian counterpart to :class:`TensorMIModel`. Fits
    ``deaths ~ offset(log[exposure * q_base]) + te(attained_age, calendar_year)
    + s(duration_years) + Sigma factors`` where ``te`` is an **anisotropic
    reduced-rank Gaussian process** (Hilbert-space HSGP expansion, Matern-5/2
    covariance with per-axis length-scales), fit to its MAP by penalised-Poisson
    IRLS with a closed-form **Laplace** posterior covariance. The calendar
    gradient of the surface is the fitted improvement;
    :meth:`BayesianMISurfaceResult.improvement_surface` turns it into the
    ``MI_x(y)`` grid with honest **posterior credible intervals**.

    The whole model is pure NumPy/SciPy (no MCMC, no ``pymc``/``bambi``), so it is
    deterministic and ships in the core install. See ADR-141 for why this
    reduced-rank backend is preferred over the ``bambi``/``pymc`` HSGP the PLAN
    anticipated.

    Identifiability (Design Anchor 3) is inherited from the frequentist model:
    no issue-year term, so the calendar gradient is attributed to improvement;
    an optional ``underwriting_era`` factor exposes the alternative. The
    Anchor-1 static-base guard rejects a generational offset.

    Args:
        cells:            Grouped cells in the canonical contract (see
                          :class:`TensorMIModel`).
        basis:            ``'count'`` or ``'amount'``.
        age_basis:        Number of HSGP eigenfunctions on the attained-age axis.
        year_basis:       Number of HSGP eigenfunctions on the calendar-year axis.
        duration_basis:   Eigenfunctions for the residual duration smooth.
        boundary_factor:  Domain half-width as a multiple of the standardised data
                          range (must exceed 1; the eigenfunctions are only valid
                          inside ``[-L, L]``).
        age_length_scale / year_length_scale / duration_length_scale:
                          Standardised-coordinate GP length-scales (larger =>
                          smoother). These are fixed smoothness dials, the direct
                          analogue of the frequentist model's spline df.
        prior_scale:      GP amplitude (coefficient prior standard deviation).
        age_varying:      Include the age x calendar interaction (age-varying
                          improvement). ``False`` fits a separable model.
        overdispersion:   Scale the posterior covariance by the Pearson dispersion
                          phi (quasi-Poisson). ``None`` enables it for by-amount.
        allow_generational_base: Skip the static-base guard (Anchor 1).

    Raises:
        PolarisValidationError: On a missing/invalid contract or a non-static base.
    """

    REQUIRED_ALWAYS: ClassVar[set[str]] = {"attained_age", "calendar_year", "q_base"}

    def __init__(
        self,
        cells: pl.DataFrame,
        *,
        basis: str = "count",
        age_basis: int = 8,
        year_basis: int = 8,
        duration_basis: int = 6,
        boundary_factor: float = 1.6,
        age_length_scale: float = 1.2,
        year_length_scale: float = 1.5,
        duration_length_scale: float = 1.5,
        prior_scale: float = 5.0,
        age_varying: bool = True,
        overdispersion: bool | None = None,
        allow_generational_base: bool = False,
    ) -> None:
        if basis not in {"count", "amount"}:
            raise PolarisValidationError(f"basis must be 'count' or 'amount', got {basis!r}.")
        if boundary_factor <= 1.0:
            raise PolarisValidationError("boundary_factor must exceed 1.0 for a valid HSGP basis.")
        if min(age_basis, year_basis) < 2:
            raise PolarisValidationError("age_basis and year_basis must each be >= 2.")
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
                "BayesianTensorMIModel needs >1 distinct calendar_year to identify a trend."
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
        self.age_basis = age_basis
        self.year_basis = year_basis
        self.duration_basis = duration_basis
        self.boundary_factor = boundary_factor
        self.age_length_scale = age_length_scale
        self.year_length_scale = year_length_scale
        self.duration_length_scale = duration_length_scale
        self.prior_scale = prior_scale
        self.age_varying = age_varying
        self.overdispersion = (basis == "amount") if overdispersion is None else overdispersion
        self.allow_generational_base = allow_generational_base

    def _build_frame(self) -> tuple[pl.DataFrame, list[str]]:
        frame = self.cells
        if "duration_months" in frame.columns:
            frame = frame.with_columns((pl.col("duration_months") / 12.0).alias("duration_years"))
        factors = [f for f in _CANDIDATE_FACTORS if f in frame.columns and frame[f].n_unique() > 1]
        return frame, factors

    def _build_spec(self, frame: pl.DataFrame, factors: list[str]) -> _RRGPSpec:
        def stats(name: str) -> tuple[float, float, float]:
            v = frame[name].to_numpy().astype(np.float64)
            center = float(v.mean())
            scale = float(v.std())
            scale = scale if scale > 0.0 else 1.0
            xn = (v - center) / scale
            boundary = float(self.boundary_factor * np.max(np.abs(xn)))
            boundary = boundary if boundary > 0.0 else 1.0
            return center, scale, boundary

        age_c, age_s, age_bnd = stats("attained_age")
        yr_c, yr_s, yr_bnd = stats("calendar_year")
        dur_active = "duration_years" in frame.columns and frame["duration_years"].n_unique() > 1
        if dur_active:
            dur_c, dur_s, dur_bnd = stats("duration_years")
        else:
            dur_c = dur_s = dur_bnd = None
        levels = {
            f: sorted(frame[f].unique().to_list(), key=lambda x: (x is None, x)) for f in factors
        }
        return _RRGPSpec(
            age_center=age_c,
            age_scale=age_s,
            age_boundary=age_bnd,
            age_basis=self.age_basis,
            age_length_scale=self.age_length_scale,
            year_center=yr_c,
            year_scale=yr_s,
            year_boundary=yr_bnd,
            year_basis=self.year_basis,
            year_length_scale=self.year_length_scale,
            prior_scale=self.prior_scale,
            age_varying=self.age_varying,
            duration_center=dur_c,
            duration_scale=dur_s,
            duration_boundary=dur_bnd,
            duration_basis=self.duration_basis,
            duration_length_scale=self.duration_length_scale,
            factor_levels=levels,
        )

    def _reference(self, frame: pl.DataFrame, factors: list[str]) -> dict[str, object]:
        ref: dict[str, object] = {
            "attained_age": float(np.median(frame["attained_age"].to_numpy())),
            "calendar_year": float(np.median(frame["calendar_year"].to_numpy())),
        }
        if "duration_years" in frame.columns:
            ref["duration_years"] = float(np.median(frame["duration_years"].to_numpy()))
        for f in factors:
            vc = frame.group_by(f).len().sort("len", descending=True)
            ref[f] = vc[f][0]
        return ref

    def fit(self, max_iter: int = 100, tol: float = 1e-9) -> BayesianMISurfaceResult:
        """
        Fit the surface to its MAP and return a :class:`BayesianMISurfaceResult`.

        The penalised Poisson log-posterior is maximised by Newton/IRLS; the
        Laplace posterior covariance is the inverse Hessian at the mode. Both
        steps are deterministic — the result is identical on every run.

        Raises:
            PolarisComputationError: If the Newton iteration fails to converge.
        """
        frame, factors = self._build_frame()
        spec = self._build_spec(frame, factors)

        cols = {c: frame[c].to_numpy() for c in frame.columns}
        design = spec.design(cols)
        prec = spec.precision()

        exposure = frame[self.exposure_col].to_numpy().astype(np.float64)
        deaths = frame[self.deaths_col].to_numpy().astype(np.float64)
        q_base = frame["q_base"].to_numpy().astype(np.float64)
        expected = exposure * q_base
        if np.any(expected <= 0.0):
            raise PolarisValidationError(
                "Every cell must have positive exposure * q_base to form the offset."
            )
        offset = np.log(expected)

        n, p = design.shape
        theta = np.zeros(p, dtype=np.float64)
        prec_mat = np.diag(prec)
        converged = False
        for _ in range(max_iter):
            eta = design @ theta + offset
            mu = np.exp(np.clip(eta, -50.0, 50.0))
            grad = design.T @ (deaths - mu) - prec * theta
            hess = (design.T * mu) @ design + prec_mat  # positive-definite (= -Hessian of logpost)
            step = np.linalg.solve(hess, grad)
            theta = theta + step
            # Scale-robust criterion: the coefficient step is negligible relative to
            # the coefficient magnitude. An absolute tol is unreachable when the
            # by-amount deaths run to 1e8 and floating-point noise floors the step.
            if np.max(np.abs(step)) < tol * (1.0 + np.max(np.abs(theta))):
                converged = True
                break
        if not converged:
            raise PolarisComputationError("Bayesian MI surface Newton iteration did not converge.")

        cov = np.linalg.inv(hess)
        mu = np.exp(np.clip(design @ theta + offset, -50.0, 50.0))
        unpenalised_hess = (design.T * mu) @ design
        effective_df = float(np.trace(cov @ unpenalised_hess))
        resid_df = max(n - effective_df, 1.0)
        pearson_chi2 = float(np.sum((deaths - mu) ** 2 / np.clip(mu, 1e-12, None)))
        dispersion = pearson_chi2 / resid_df
        if self.overdispersion:
            cov = cov * dispersion

        overall_ae = float(deaths.sum() / expected.sum())
        cal = self.cells["calendar_year"].to_numpy()
        age = self.cells["attained_age"].to_numpy()
        return BayesianMISurfaceResult(
            basis=self.basis,
            factors=factors,
            age_varying=self.age_varying,
            overall_ae=overall_ae,
            dispersion=dispersion,
            overdispersion_applied=self.overdispersion,
            effective_df=effective_df,
            n_cells=frame.height,
            observed_ages=(int(age.min()), int(age.max())),
            observed_years=(int(cal.min()), int(cal.max())),
            prior_scale=self.prior_scale,
            length_scales={
                "attained_age": self.age_length_scale,
                "calendar_year": self.year_length_scale,
                "duration_years": self.duration_length_scale,
            },
            reference=self._reference(frame, factors),
            _spec=spec,
            _theta=theta,
            _cov=cov,
        )
