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

from itertools import pairwise

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

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
    ) -> np.ndarray:
        """
        Period-by-period expense allowance the reinsurer pays the cedant.

        First-year premiums (the first ``months_per_year`` periods) are
        allowed at ``first_year_pct``; later premiums at the renewal rate. When
        a sliding scale is configured, the renewal rate is selected from the
        realized loss ratio (``ceded_claims.sum() / ceded_premiums.sum()``),
        which requires ``ceded_claims``.

        Args:
            ceded_premiums: Ceded premium per period, shape (T,), float64.
            ceded_claims:   Ceded claims per period, shape (T,). Required only
                            when a sliding scale is configured.

        Returns:
            Non-negative allowance array, shape (T,), float64.

        Raises:
            PolarisValidationError: If a sliding scale is set but no claims are
                provided, or array shapes are inconsistent.
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

        rates = np.full(n, renewal_rate, dtype=np.float64)
        fy = min(self.months_per_year, n)
        rates[:fy] = self.first_year_pct

        return premiums * rates
