"""
Asset model — fixed-income instruments and an asset portfolio.

This is the foundation of the Asset / ALM epic (Tier-C C0,
ARCHITECTURE Milestone 5.4). Today the engine is liability-only: Modco prices
its modco interest on a single flat rate and there is no investment-income,
duration, or asset-liability model. This module adds the asset side, starting
with the ability to:

- describe a ``Bond`` (a single fixed-income instrument valued on the monthly
  projection grid),
- project its coupon + principal cash flows as a ``(T,)`` numpy vector, and
- price it (and a whole ``AssetPortfolio``) at a yield.

Investment income, duration / convexity, the Modco integration, and the
asset-liability duration-gap analytics are later slices of the same epic
(see ``docs/PLAN_asset_alm.md``); this slice is purely additive — nothing here
is wired into pricing yet, so all golden baselines are byte-identical.

Discounting convention
----------------------
Bond pricing uses the **same** effective-annual monthly discounting as
``CashFlowResult.pv_*``: a cash flow at month ``t`` (1-indexed, end of month)
is discounted by ``v ** t`` where ``v = (1 + annual_yield) ** (-1 / 12)``. This
keeps a bond PV and a projection PV on a single comparable basis.
"""

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel

__all__ = ["AssetPortfolio", "Bond"]

# Coupon frequencies (payments per year) that divide evenly into 12 months,
# so every coupon lands on an integer month of the projection grid.
_VALID_COUPON_FREQUENCIES: frozenset[int] = frozenset({1, 2, 3, 4, 6, 12})


class Bond(PolarisBaseModel):
    """
    A single fixed-income instrument valued on the monthly projection grid.

    A bond pays a level coupon ``face_value * coupon_rate / coupon_frequency``
    every ``12 / coupon_frequency`` months, and repays ``face_value`` (the
    principal) at ``term_months``. A zero-coupon bond (``coupon_rate = 0``)
    pays only the principal at maturity.

    All monetary values are in dollars (``float64`` semantics).
    """

    face_value: float = Field(
        gt=0.0,
        description="Par / principal repaid at maturity, in dollars.",
    )
    coupon_rate: float = Field(
        ge=0.0,
        description="Annual nominal coupon rate (e.g. 0.04 = 4%). Zero for a zero-coupon bond.",
    )
    coupon_frequency: int = Field(
        default=2,
        description=(
            "Coupon payments per year. Must divide 12 evenly "
            "(one of 1, 2, 3, 4, 6, 12) so coupons land on integer months."
        ),
    )
    term_months: int = Field(
        gt=0,
        description="Months from valuation to maturity (principal repayment).",
    )
    book_value: float | None = Field(
        default=None,
        description=(
            "Amortised book / carrying value, in dollars. Defaults to face_value "
            "(i.e. carried at par) when not supplied."
        ),
    )
    bond_id: str | None = Field(default=None, description="Optional instrument identifier.")

    @model_validator(mode="after")
    def _validate_frequency_and_book(self) -> "Bond":
        if self.coupon_frequency not in _VALID_COUPON_FREQUENCIES:
            raise ValueError(
                f"coupon_frequency must divide 12 (one of "
                f"{sorted(_VALID_COUPON_FREQUENCIES)}), got {self.coupon_frequency}"
            )
        if self.book_value is not None and self.book_value < 0.0:
            raise ValueError(f"book_value must be >= 0.0, got {self.book_value}")
        return self

    @property
    def carrying_value(self) -> float:
        """Book value, defaulting to ``face_value`` when none was supplied."""
        return self.face_value if self.book_value is None else self.book_value

    @property
    def coupon_payment(self) -> float:
        """Dollar coupon paid at each coupon date."""
        return self.face_value * self.coupon_rate / self.coupon_frequency

    @property
    def coupon_interval_months(self) -> int:
        """Months between consecutive coupon payments."""
        return 12 // self.coupon_frequency

    def cash_flow_vector(self, months: int) -> np.ndarray:
        """
        Project coupon + principal cash flows over ``months`` monthly periods.

        Returns a ``(months,)`` float64 array. Index ``i`` carries the cash
        flow paid at month ``i + 1`` (1-indexed, end of month). Coupons fall on
        every ``coupon_interval_months``; the principal is added at
        ``term_months``. Cash flows beyond ``months`` are truncated; months
        after maturity are zero.
        """
        if months <= 0:
            raise ValueError(f"months must be positive, got {months}")

        cf = np.zeros(months, dtype=np.float64)

        # Coupon dates: term-end and every coupon_interval before it, that fall
        # within the requested horizon. 1-indexed month m -> array index m - 1.
        coupon_months = np.arange(
            self.coupon_interval_months,
            self.term_months + 1,
            self.coupon_interval_months,
            dtype=np.int64,
        )
        in_horizon = coupon_months[coupon_months <= months]
        cf[in_horizon - 1] += self.coupon_payment

        # Principal repaid at maturity, if maturity falls within the horizon.
        if self.term_months <= months:
            cf[self.term_months - 1] += self.face_value

        return cf

    def price(self, annual_yield: float) -> float:
        """
        Present value of the bond's cash flows at ``annual_yield``.

        Uses the engine's effective-annual monthly discounting
        (``v = (1 + annual_yield) ** (-1 / 12)``), so the result is directly
        comparable to a ``CashFlowResult`` present value.
        """
        cf = self.cash_flow_vector(self.term_months)
        v = (1.0 + annual_yield) ** (-1.0 / 12.0)
        periods = np.arange(1, self.term_months + 1, dtype=np.float64)
        discount_factors = v**periods
        return float(np.dot(cf, discount_factors))


class AssetPortfolio(PolarisBaseModel):
    """
    A portfolio of fixed-income instruments backing reserves.

    Aggregates its bonds' cash flows and value. The portfolio is the unit a
    later slice hands to ``ModcoTreaty`` to drive modco interest from the asset
    book yield, and the unit ``analytics/alm.py`` measures duration against the
    liability.
    """

    bonds: list[Bond] = Field(
        min_length=1,
        description="Fixed-income instruments held in the portfolio (at least one).",
    )
    portfolio_id: str | None = Field(default=None, description="Optional portfolio identifier.")

    @property
    def max_term_months(self) -> int:
        """Longest instrument term in the portfolio."""
        return max(bond.term_months for bond in self.bonds)

    @property
    def book_value(self) -> float:
        """Total carrying value across all instruments, in dollars."""
        return float(sum(bond.carrying_value for bond in self.bonds))

    @property
    def total_face_value(self) -> float:
        """Total par / principal across all instruments, in dollars."""
        return float(sum(bond.face_value for bond in self.bonds))

    def cash_flow_vector(self, months: int | None = None) -> np.ndarray:
        """
        Aggregate coupon + principal cash flows over the monthly grid.

        ``months`` defaults to the longest instrument term so the whole
        portfolio's cash flows are captured. Returns a ``(months,)`` float64
        array equal to the sum of the constituent bonds' cash-flow vectors.
        """
        horizon = self.max_term_months if months is None else months
        total = np.zeros(horizon, dtype=np.float64)
        for bond in self.bonds:
            total += bond.cash_flow_vector(horizon)
        return total

    def market_value(self, annual_yield: float) -> float:
        """Total present value of the portfolio at ``annual_yield``, in dollars."""
        return float(sum(bond.price(annual_yield) for bond in self.bonds))
