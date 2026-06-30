"""
ExpenseAllowance — sliding-scale expense allowances for proportional treaties.

In a real YRT or coinsurance treaty the reinsurer pays the cedant an
**expense allowance**: compensation for originating and administering the
ceded business. The allowance is normally quoted as a percentage of the
**ceded premium**, with a high **first-year** rate (reimbursing acquisition
cost) and a lower **renewal** rate. Large deals frequently put the renewal
rate on a **sliding scale** keyed to loss experience — the better the cedant's
experience (lower loss ratio), the higher the allowance the reinsurer pays.

This module provides the data contract and the pure computation primitive.
It is deliberately **not** wired into any treaty engine in this slice; the
treaties consume it in a later slice. Folding the allowance into a treaty's
cash flows is a reinsurer→cedant transfer that preserves the
``net + ceded == gross`` additivity invariant (see ``CoinsuranceTreaty``).

Sign convention (for the consuming treaty, documented here for context):
    The allowance is a cost to the reinsurer and a reimbursement to the cedant.
    ``compute_allowance`` returns a non-negative array; the treaty adds it to
    the ceded ``expenses`` line and subtracts it from the net ``expenses`` line.
"""

from datetime import date as date_type
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

if TYPE_CHECKING:
    from polaris_re.core.inforce import InforceBlock

__all__ = ["ExpenseAllowance", "ExpenseAllowanceBand"]


class ExpenseAllowanceBand(PolarisBaseModel):
    """
    One band of a sliding-scale expense allowance.

    A band pays ``allowance_pct`` (a fraction of renewal ceded premium) when
    the realized loss ratio is at or below ``max_loss_ratio``. Bands are
    evaluated in ascending ``max_loss_ratio`` order; the first band whose
    threshold the loss ratio does not exceed wins.
    """

    max_loss_ratio: float = Field(
        ge=0.0,
        description="Upper loss-ratio bound (inclusive) at which this band's rate applies.",
    )
    allowance_pct: float = Field(
        ge=0.0,
        le=2.0,
        description="Renewal allowance as a fraction of ceded premium when this band applies.",
    )


class ExpenseAllowance(PolarisBaseModel):
    """
    Expense-allowance terms for a proportional reinsurance treaty.

    The allowance is a percentage of **ceded premium**, split into a
    first-year rate (duration year 1) and a renewal rate (later durations).
    When ``sliding_scale`` is supplied, the renewal rate is selected from the
    loss-ratio bands instead of the flat ``renewal_pct``.

    Attributes:
        first_year_pct: Allowance on first-year (duration-1) ceded premium.
        renewal_pct:    Flat renewal allowance, used when no sliding scale is set.
        sliding_scale:  Optional ascending-by-threshold loss-ratio bands. When
                        set, the renewal rate slides with the realized loss
                        ratio (better experience pays a higher rate).
        months_per_year: Months per policy year on the projection grid (default 12).

    The sliding scale must be **monotone non-increasing** in loss ratio: a
    lower loss ratio (better experience) must pay an allowance rate at least as
    high as a higher loss ratio. A mis-ordered scale raises
    ``PolarisValidationError`` rather than silently inverting the incentive.
    """

    first_year_pct: float = Field(
        ge=0.0,
        le=2.0,
        description="First-year allowance as a fraction of ceded premium.",
    )
    renewal_pct: float = Field(
        ge=0.0,
        le=2.0,
        description="Flat renewal allowance as a fraction of ceded premium (no sliding scale).",
    )
    sliding_scale: list[ExpenseAllowanceBand] | None = Field(
        default=None,
        description="Optional loss-ratio bands selecting the renewal rate instead of renewal_pct.",
    )
    months_per_year: int = Field(
        default=12,
        ge=1,
        description="Months per policy year (first year = this many periods).",
    )

    @model_validator(mode="after")
    def _validate_sliding_scale(self) -> "ExpenseAllowance":
        """Require an ascending-threshold scale whose rate is monotone non-increasing."""
        scale = self.sliding_scale
        if not scale:
            return self
        thresholds = [b.max_loss_ratio for b in scale]
        if thresholds != sorted(thresholds):
            raise PolarisValidationError(
                "sliding_scale bands must be in ascending max_loss_ratio order; "
                f"got thresholds {thresholds}."
            )
        if len(set(thresholds)) != len(thresholds):
            raise PolarisValidationError(
                "sliding_scale bands must have distinct max_loss_ratio thresholds; "
                f"got {thresholds}."
            )
        rates = [b.allowance_pct for b in scale]
        # Better experience (earlier band, lower threshold) must pay >= worse experience.
        for earlier, later in pairwise(rates):
            if later > earlier:
                raise PolarisValidationError(
                    "sliding_scale allowance_pct must be monotone non-increasing as loss ratio "
                    f"rises (better experience pays more); got rates {rates}."
                )
        return self

    # ------------------------------------------------------------------
    # Rate selection
    # ------------------------------------------------------------------

    def renewal_rate_for_loss_ratio(self, loss_ratio: float) -> float:
        """
        Renewal allowance rate for a realized loss ratio.

        With no sliding scale, returns the flat ``renewal_pct``. With a sliding
        scale, returns the rate of the first band whose ``max_loss_ratio`` is
        not exceeded; a loss ratio above every band falls to the last (lowest)
        band's rate.
        """
        if not self.sliding_scale:
            return self.renewal_pct
        for band in self.sliding_scale:
            if loss_ratio <= band.max_loss_ratio:
                return band.allowance_pct
        return self.sliding_scale[-1].allowance_pct

    # ------------------------------------------------------------------
    # Allowance computation
    # ------------------------------------------------------------------

    def compute_allowance(
        self,
        ceded_premiums: np.ndarray,
        ceded_claims: np.ndarray | None = None,
        *,
        first_year_fraction: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Period-by-period expense allowance the reinsurer pays the cedant.

        First-year premiums are allowed at ``first_year_pct``; later premiums
        at the renewal rate. When a sliding scale is configured, the renewal
        rate is selected from the realized loss ratio
        (``ceded_claims.sum() / ceded_premiums.sum()``), which requires
        ``ceded_claims``.

        **First-year mapping.** Which periods count as "first year" depends on
        ``first_year_fraction``:

        * ``None`` (default): the first ``months_per_year`` *projection*
          periods are treated as first year. This is correct **only for new
          business projected from inception** — every policy is in policy year
          one at projection month 0. Feeding a mid-duration inforce stream here
          wrongly applies the first-year rate (see
          :meth:`first_year_fraction_for_block`).
        * an array of shape (T,) with values in [0, 1]: a per-period blend where
          ``rate[t] = f[t] * first_year_pct + (1 - f[t]) * renewal_rate``. This
          is how a treaty maps each policy's projection month to its actual
          policy duration on an inforce block — ``f[t]`` is the (face-weighted)
          fraction of in-force premium still in policy year one at projection
          month ``t``. A new-business block yields ``f[t] = 1`` for
          ``t < months_per_year`` and ``0`` after, reproducing the default.

        Args:
            ceded_premiums: Ceded premium per period, shape (T,), float64.
            ceded_claims:   Ceded claims per period, shape (T,). Required only
                            when a sliding scale is configured.
            first_year_fraction: Optional per-period first-year weight, shape
                            (T,), values in [0, 1]. See above.

        Returns:
            Non-negative allowance array, shape (T,), float64.

        Raises:
            PolarisValidationError: If a sliding scale is set but no claims are
                provided, or array shapes / fraction values are inconsistent.
        """
        premiums = np.asarray(ceded_premiums, dtype=np.float64)
        if premiums.ndim != 1:
            raise PolarisValidationError(f"ceded_premiums must be 1-D, got shape {premiums.shape}.")
        n = premiums.shape[0]

        if self.sliding_scale:
            if ceded_claims is None:
                raise PolarisValidationError(
                    "compute_allowance requires ceded_claims when a sliding scale is configured."
                )
            claims = np.asarray(ceded_claims, dtype=np.float64)
            if claims.shape != premiums.shape:
                raise PolarisValidationError(
                    f"ceded_claims shape {claims.shape} != ceded_premiums shape {premiums.shape}."
                )
            total_premium = float(premiums.sum())
            loss_ratio = float(claims.sum()) / total_premium if total_premium > 0.0 else 0.0
            renewal_rate = self.renewal_rate_for_loss_ratio(loss_ratio)
        else:
            renewal_rate = self.renewal_pct

        if first_year_fraction is None:
            rates = np.full(n, renewal_rate, dtype=np.float64)
            fy = min(self.months_per_year, n)
            rates[:fy] = self.first_year_pct
        else:
            fraction = np.asarray(first_year_fraction, dtype=np.float64)
            if fraction.shape != premiums.shape:
                raise PolarisValidationError(
                    f"first_year_fraction shape {fraction.shape} != ceded_premiums shape "
                    f"{premiums.shape}."
                )
            if np.any(fraction < 0.0) or np.any(fraction > 1.0):
                raise PolarisValidationError(
                    "first_year_fraction values must lie in [0, 1]; "
                    f"got min {float(fraction.min())}, max {float(fraction.max())}."
                )
            rates = fraction * self.first_year_pct + (1.0 - fraction) * renewal_rate

        return premiums * rates

    # ------------------------------------------------------------------
    # First-year mapping for inforce blocks
    # ------------------------------------------------------------------

    def first_year_fraction_for_block(
        self,
        inforce: "InforceBlock",
        n_periods: int,
        valuation_date: date_type,
    ) -> np.ndarray:
        """
        Per-period face-weighted fraction of the block still in policy year one.

        On an inforce block most policies are mid-duration: their acquisition
        cost is sunk and the renewal allowance — not the first-year rate —
        applies. This maps each policy's projection month to its actual policy
        duration. For projection month ``t``, a policy is in policy year one
        iff ``duration_in_force_months + t < months_per_year``. The returned
        weight ``f[t]`` is the face-weighted fraction of the block meeting that
        test, suitable for the ``first_year_fraction`` argument of
        :meth:`compute_allowance`.

        New business (all durations 0 at valuation) yields ``f[t] = 1`` for
        ``t < months_per_year`` and ``0`` afterwards, recovering the default
        projection-month behaviour. A fully mid-duration block (every policy
        already past policy year one) yields ``f[t] = 0`` everywhere → the whole
        stream is allowed at the renewal rate.

        Note: the fraction is face-weighted, **not** survivorship-weighted —
        it ignores decrements between valuation and projection month ``t``. This
        is a deliberate first-cut approximation; it is exact at the boundaries
        (all-new and all-renewal blocks) and only blends across the year-one
        transition for mixed-duration blocks.

        Args:
            inforce:        The block being reinsured.
            n_periods:      Number of projection periods T.
            valuation_date: Reference date for each policy's duration in force.

        Returns:
            First-year weight per period, shape (T,), float64, values in [0, 1].
        """
        face = inforce.face_amount_vec.astype(np.float64)  # (N,)
        total_face = float(face.sum())
        if total_face <= 0.0 or n_periods <= 0:
            return np.zeros(max(n_periods, 0), dtype=np.float64)

        dur_months = inforce.duration_inforce_vec_at(valuation_date)  # (N,) int32
        months = np.arange(n_periods, dtype=np.int32)  # (T,)
        # Months in force at each projection step, shape (N, T).
        total_months_2d = dur_months[:, np.newaxis] + months[np.newaxis, :]
        in_first_year = total_months_2d < self.months_per_year  # (N, T) bool
        return (face[:, np.newaxis] * in_first_year).sum(axis=0) / total_face
