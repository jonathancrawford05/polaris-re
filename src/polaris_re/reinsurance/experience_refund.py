"""
ExperienceRefund — profit-sharing (experience refund) for proportional treaties.

Large YRT and coinsurance treaties frequently carry an **experience refund**
(also called profit sharing or an experience-rating refund): when the ceded
business runs better than expected, the reinsurer refunds a share of the
accumulated favourable experience to the cedant. This is the standard
mechanism for aligning both parties to good experience on top of the
sliding-scale expense allowance (see :mod:`expense_allowance`).

The refund is driven by an **experience account** accumulated from the ceded
cash flows:

    contribution_t = ceded_premium_t
                     - ceded_claims_t
                     - allowance_t                       (already paid to cedant)
                     - reinsurer_margin_pct * ceded_premium_t   (reinsurer charge)

A positive balance is favourable to the reinsurer; the cedant is refunded a
``refund_pct`` share of the balance in excess of a ``retention`` the reinsurer
keeps first. The account may be accumulated **at interest** (an experience fund
rolled forward to the settlement point) or as a simple undiscounted sum
(``interest_rate = 0``, the default).

This module provides the data contract and the pure computation primitive.
It is deliberately **not** wired into any treaty engine in this slice; the
treaties consume it in a later slice. When wired, the refund is a terminal
reinsurer→cedant transfer that preserves the ``net + ceded == gross``
additivity invariant (the refund moves money between the two parties; it is
not a new external cash flow), exactly as the expense allowance does.

Sign convention (for the consuming treaty, documented here for context):
    The refund is a cost to the reinsurer and a payment to the cedant.
    ``compute_refund`` returns a non-negative scalar; an unfavourable
    (negative) experience balance refunds nothing — the cedant never pays into
    the fund here (deficit carryforward is out of scope, see the ADR).
"""

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["ExperienceRefund"]


class ExperienceRefund(PolarisBaseModel):
    """
    Experience-refund (profit-sharing) terms for a proportional treaty.

    The refund settles a share of the accumulated favourable experience back to
    the cedant. The experience account is built from the ceded cash flows, net
    of any expense allowance already paid and the reinsurer's retained margin,
    and may be accumulated at interest.

    Attributes:
        refund_pct: Share of the favourable experience balance (above the
                    retention) refunded to the cedant, in [0, 1].
        retention:  Absolute favourable balance the reinsurer keeps before any
                    refund is paid (a profit threshold). Non-negative.
        reinsurer_margin_pct: Reinsurer's risk/expense charge retained before
                    sharing, as a fraction of ceded premium, in [0, 1]. The
                    charge reduces the sharable balance.
        interest_rate: Annual rate at which the experience account is
                    accumulated forward to the settlement point. ``0.0``
                    (default) is a simple undiscounted sum.
        months_per_year: Periods per policy year on the projection grid
                    (default 12), used to convert the annual ``interest_rate``
                    to the per-period accumulation factor.

    The refund is non-negative: an unfavourable (negative) balance refunds
    nothing.
    """

    refund_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Share of the favourable experience balance refunded to the cedant.",
    )
    retention: float = Field(
        default=0.0,
        ge=0.0,
        description="Favourable balance the reinsurer keeps before any refund is paid.",
    )
    reinsurer_margin_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Reinsurer charge retained before sharing, as a fraction of ceded premium.",
    )
    interest_rate: float = Field(
        default=0.0,
        ge=0.0,
        description="Annual accumulation rate for the experience account (0 = simple sum).",
    )
    months_per_year: int = Field(
        default=12,
        ge=1,
        description="Periods per policy year, used to convert the annual interest rate to a per-period factor.",
    )

    # ------------------------------------------------------------------
    # Experience account
    # ------------------------------------------------------------------

    def experience_balance(
        self,
        ceded_premiums: np.ndarray,
        ceded_claims: np.ndarray,
        allowances: np.ndarray | None = None,
    ) -> float:
        """
        Accumulated experience-account balance (favourable to the reinsurer > 0).

        Each period contributes
        ``premium - claims - allowance - reinsurer_margin_pct * premium``.
        With ``interest_rate == 0`` the balance is the simple sum of the
        contributions; otherwise each contribution is accumulated forward to the
        final period at the per-period factor ``(1 + interest_rate)^(1 /
        months_per_year)`` — an experience fund rolled to the settlement point.

        Args:
            ceded_premiums: Ceded premium per period, shape (T,), float64.
            ceded_claims:   Ceded claims per period, shape (T,), float64.
            allowances:     Optional expense allowance already paid to the cedant
                            per period, shape (T,). Defaults to zeros.

        Returns:
            The accumulated experience balance as a float (may be negative).

        Raises:
            PolarisValidationError: On non-1-D inputs or mismatched shapes.
        """
        premiums = np.asarray(ceded_premiums, dtype=np.float64)
        claims = np.asarray(ceded_claims, dtype=np.float64)
        if premiums.ndim != 1:
            raise PolarisValidationError(f"ceded_premiums must be 1-D, got shape {premiums.shape}.")
        if claims.shape != premiums.shape:
            raise PolarisValidationError(
                f"ceded_claims shape {claims.shape} != ceded_premiums shape {premiums.shape}."
            )
        n = premiums.shape[0]

        if allowances is None:
            allowance = np.zeros(n, dtype=np.float64)
        else:
            allowance = np.asarray(allowances, dtype=np.float64)
            if allowance.shape != premiums.shape:
                raise PolarisValidationError(
                    f"allowances shape {allowance.shape} != ceded_premiums shape {premiums.shape}."
                )

        contributions = premiums - claims - allowance - self.reinsurer_margin_pct * premiums

        if n == 0:
            return 0.0
        if self.interest_rate == 0.0:
            return float(contributions.sum())

        period_factor = (1.0 + self.interest_rate) ** (1.0 / self.months_per_year)
        # Accumulate each contribution forward to the final period (index n-1).
        exponents = (n - 1) - np.arange(n, dtype=np.float64)
        factors = period_factor**exponents
        return float((contributions * factors).sum())

    # ------------------------------------------------------------------
    # Refund computation
    # ------------------------------------------------------------------

    def compute_refund(
        self,
        ceded_premiums: np.ndarray,
        ceded_claims: np.ndarray,
        allowances: np.ndarray | None = None,
    ) -> float:
        """
        Experience refund the reinsurer pays the cedant (non-negative scalar).

        Computes the accumulated :meth:`experience_balance`, then refunds
        ``refund_pct`` of the balance in excess of ``retention``. An unfavourable
        (negative) or below-retention balance refunds nothing.

        Args:
            ceded_premiums: Ceded premium per period, shape (T,), float64.
            ceded_claims:   Ceded claims per period, shape (T,), float64.
            allowances:     Optional expense allowance already paid to the cedant
                            per period, shape (T,). Defaults to zeros.

        Returns:
            The refund amount as a non-negative float.
        """
        balance = self.experience_balance(ceded_premiums, ceded_claims, allowances)
        return self.refund_pct * max(0.0, balance - self.retention)
