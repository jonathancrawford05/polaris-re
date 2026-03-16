"""
Experience Study — Actual-to-Expected (A/E) analysis for mortality and lapse.

Compares observed (actual) experience against expected experience derived from
assumed tables, producing credibility-weighted A/E ratios by risk dimension.

The A/E ratio quantifies how actual experience compares to assumption:
    A/E = Actual_Events / Expected_Events

A/E > 1.0 means worse-than-expected experience (higher mortality/lapse than assumed).
A/E < 1.0 means better-than-expected experience.

Credibility-weighting (Limited Fluctuation method):
    Credibility(Z) = min(1, √(n / n_full))
    where n_full = expected observations for full credibility (default 1082 deaths
    for 90% probability of being within 5% of true mean — standard actuarial standard).
    Blended rate = Z * observed_rate + (1 - Z) * table_rate

Use cases:
- Annual assumption review: compare current-year claims against reserved assumptions
- Assumption update: produce calibrated multipliers for MortalityTable
- Deal monitoring: track reinsured block experience against treaty pricing assumptions
"""

from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import polars as pl

__all__ = ["AEResult", "ExperienceStudy"]


@dataclass
class AEResult:
    """
    Results of an Actual-to-Expected analysis.

    Contains A/E ratios, credibility weights, and blended assumption
    adjustments for each combination of grouping dimensions.
    """

    study_type: str
    """'mortality' or 'lapse'."""

    group_by: list[str]
    """Dimension names used for grouping (e.g., ['age_band', 'sex'])."""

    # Core output table (Polars DataFrame)
    summary: pl.DataFrame
    """
    Summary table with columns:
        - All group_by dimensions
        - actual:        total actual events in group
        - expected:      total expected events in group
        - exposure:      total exposure (person-years or policy-months)
        - ae_ratio:      actual / expected
        - actual_rate:   actual / exposure
        - expected_rate: expected / exposure
        - credibility:   Z in [0, 1]
        - blended_rate:  Z * actual_rate + (1-Z) * expected_rate
    """

    # Aggregate (overall) statistics
    total_actual: float = 0.0
    total_expected: float = 0.0
    total_exposure: float = 0.0
    overall_ae: float = 0.0
    """Overall A/E ratio across all groups."""

    overall_credibility: float = 0.0
    """Overall credibility weight for the entire study."""

    # Credibility parameter
    n_full_credibility: float = 1082.0
    """
    Exposure needed for full credibility (90% probability within 5% of true mean).
    Standard limited-fluctuation credibility: n_full = (z_a/2 / e)^2 * p*(1-p) / p^2
    For mortality: n_full ≈ 1082 at 90%/5%. For lapse (higher rate): may be lower.
    """

    def credibility_adjusted_multipliers(self) -> pl.DataFrame:
        """
        Return the A/E summary with credibility-adjusted multipliers.

        The multiplier is the credibility-weighted deviation from 1.0 (expected):
            multiplier = 1 + Z * (A/E - 1) = Z * ae_ratio + (1 - Z)

        Returns:
            DataFrame with all summary columns plus 'multiplier'.
        """
        return self.summary.with_columns(
            (pl.col("credibility") * pl.col("ae_ratio") + (1.0 - pl.col("credibility"))).alias(
                "multiplier"
            )
        )


class ExperienceStudy:
    """
    Actual-to-Expected (A/E) experience analysis engine.

    Accepts a Polars DataFrame of observed experience records and expected
    values, then produces grouped A/E ratios with credibility weighting.

    Input DataFrame schema (required columns):
        - actual (float):    Number of actual events (e.g., deaths, lapses)
        - expected (float):  Number of expected events from assumed table
        - exposure (float):  Risk exposure (e.g., policy-years, person-months)

        Optional dimension columns for grouping:
        - age_band, sex, smoker_status, duration_band, calendar_year, product_type, ...
        Any column name is supported as a grouping dimension.

    Args:
        data:                Polars DataFrame with required columns above.
        study_type:          'mortality' or 'lapse'.
        n_full_credibility:  Events needed for full credibility. Default 1082
                             (standard limited-fluctuation for mortality).
    """

    REQUIRED_COLUMNS: ClassVar[set[str]] = {"actual", "expected", "exposure"}

    def __init__(
        self,
        data: pl.DataFrame,
        study_type: str = "mortality",
        n_full_credibility: float = 1082.0,
    ) -> None:
        missing = self.REQUIRED_COLUMNS - set(data.columns)
        if missing:
            raise ValueError(f"Input data missing required columns: {missing}")
        if study_type not in {"mortality", "lapse"}:
            raise ValueError(f"study_type must be 'mortality' or 'lapse', got: {study_type!r}")

        self.data = data
        self.study_type = study_type
        self.n_full_credibility = n_full_credibility

    @staticmethod
    def _credibility(actual: float, n_full: float) -> float:
        """
        Limited-fluctuation credibility weight Z = min(1, sqrt(n / n_full)).

        Args:
            actual:  Actual observed events.
            n_full:  Events required for full credibility.

        Returns:
            Credibility Z in [0, 1].
        """
        return float(min(1.0, np.sqrt(actual / n_full)))

    def run(self, group_by: list[str] | None = None) -> AEResult:
        """
        Run the A/E study, optionally grouped by specified dimensions.

        Args:
            group_by:
                List of column names to group by (e.g., ['age_band', 'sex']).
                If None, produces a single overall A/E ratio (no grouping).

        Returns:
            AEResult with summary table and aggregate statistics.
        """
        group_by = group_by or []

        # Validate group_by columns exist
        unknown = set(group_by) - set(self.data.columns)
        if unknown:
            raise ValueError(f"group_by columns not found in data: {unknown}")

        # --- Aggregate by groups ---
        agg_exprs = [
            pl.col("actual").sum().alias("actual"),
            pl.col("expected").sum().alias("expected"),
            pl.col("exposure").sum().alias("exposure"),
        ]

        if group_by:
            grouped = self.data.group_by(group_by).agg(agg_exprs)
        else:
            grouped = self.data.select(agg_exprs)

        # --- Compute derived metrics ---
        # A/E ratio, actual rate, expected rate, credibility, blended rate
        n_full = self.n_full_credibility

        def _ae(actual: float, expected: float) -> float:
            return actual / expected if expected > 0.0 else float("nan")

        def _rate(events: float, exposure: float) -> float:
            return events / exposure if exposure > 0.0 else float("nan")

        def _cred(actual: float) -> float:
            return float(min(1.0, np.sqrt(actual / n_full)))

        # Apply computations row-wise using map_rows for simplicity
        # Note: using Polars expressions for performance on large datasets
        n_full_lit = pl.lit(n_full)

        summary = grouped.with_columns(
            # A/E ratio
            pl.when(pl.col("expected") > 0)
            .then(pl.col("actual") / pl.col("expected"))
            .otherwise(float("nan"))
            .alias("ae_ratio"),
            # Actual rate
            pl.when(pl.col("exposure") > 0)
            .then(pl.col("actual") / pl.col("exposure"))
            .otherwise(float("nan"))
            .alias("actual_rate"),
            # Expected rate
            pl.when(pl.col("exposure") > 0)
            .then(pl.col("expected") / pl.col("exposure"))
            .otherwise(float("nan"))
            .alias("expected_rate"),
            # Credibility Z = min(1, sqrt(actual / n_full))
            (pl.col("actual") / n_full_lit).sqrt().clip(upper_bound=1.0).alias("credibility"),
        ).with_columns(
            # Blended rate = Z * actual_rate + (1-Z) * expected_rate
            (
                pl.col("credibility") * pl.col("actual_rate")
                + (1.0 - pl.col("credibility")) * pl.col("expected_rate")
            ).alias("blended_rate"),
        )

        # Sort for deterministic output
        if group_by:
            summary = summary.sort(group_by)

        # --- Overall aggregates ---
        total_actual = float(self.data["actual"].sum())
        total_expected = float(self.data["expected"].sum())
        total_exposure = float(self.data["exposure"].sum())
        overall_ae = total_actual / total_expected if total_expected > 0.0 else float("nan")
        overall_cred = float(min(1.0, np.sqrt(total_actual / n_full)))

        return AEResult(
            study_type=self.study_type,
            group_by=group_by,
            summary=summary,
            total_actual=total_actual,
            total_expected=total_expected,
            total_exposure=total_exposure,
            overall_ae=overall_ae,
            overall_credibility=overall_cred,
            n_full_credibility=n_full,
        )

    @classmethod
    def from_projection(
        cls,
        actual_deaths: np.ndarray,
        expected_deaths: np.ndarray,
        exposure: np.ndarray,
        study_type: str = "mortality",
        n_full_credibility: float = 1082.0,
    ) -> "ExperienceStudy":
        """
        Convenience constructor from projection arrays.

        Converts numpy arrays (e.g., from a CashFlowResult) into a Polars
        DataFrame suitable for A/E analysis. No grouping dimensions — produces
        a single overall A/E ratio across the full projection horizon.

        Args:
            actual_deaths:   Shape (T,) actual events per projection period.
            expected_deaths: Shape (T,) expected events per projection period.
            exposure:        Shape (T,) exposure per projection period.
            study_type:      'mortality' or 'lapse'.
            n_full_credibility: Events for full credibility. Default 1082.

        Returns:
            ExperienceStudy instance ready for .run().
        """
        n = len(actual_deaths)
        if len(expected_deaths) != n or len(exposure) != n:
            raise ValueError("actual_deaths, expected_deaths, and exposure must have equal length")

        data = pl.DataFrame(
            {
                "actual": actual_deaths.astype(np.float64),
                "expected": expected_deaths.astype(np.float64),
                "exposure": exposure.astype(np.float64),
            }
        )
        return cls(data=data, study_type=study_type, n_full_credibility=n_full_credibility)

    @classmethod
    def add_age_bands(
        cls,
        data: pl.DataFrame,
        age_col: str = "age",
        band_width: int = 5,
    ) -> pl.DataFrame:
        """
        Add an 'age_band' column to a DataFrame by bucketing ages.

        Args:
            data:       DataFrame with an age column.
            age_col:    Name of the column containing attained ages.
            band_width: Width of each age band. Default 5.

        Returns:
            DataFrame with new 'age_band' column (e.g., '35-39', '40-44').
        """
        return data.with_columns(
            (
                (pl.col(age_col) // band_width * band_width).cast(pl.Utf8)
                + pl.lit("-")
                + ((pl.col(age_col) // band_width * band_width + band_width - 1).cast(pl.Utf8))
            ).alias("age_band")
        )
