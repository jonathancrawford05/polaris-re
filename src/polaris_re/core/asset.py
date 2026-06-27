"""
Asset model — fixed-income instruments and an asset portfolio.

This is the foundation of the Asset / ALM epic (Tier-C C0,
ARCHITECTURE Milestone 5.4). Today the engine is liability-only: Modco prices
its modco interest on a single flat rate and there is no investment-income,
duration, or asset-liability model. This module adds the asset side, starting
with the ability to:

- describe a ``Bond`` (a single fixed-income instrument valued on the monthly
  projection grid),
- project its coupon + principal cash flows as a ``(T,)`` numpy vector,
- price it (and a whole ``AssetPortfolio``) at a yield, and
- measure an ``AssetPortfolio``'s gross book yield, the investment income it
  earns on a reserve balance, and its Macaulay / modified duration and
  convexity (Slice 2).

The Modco integration (driving modco interest from the asset book yield) and
the asset-liability duration-gap analytics are later slices of the same epic
(see ``docs/PLAN_asset_alm.md``); the work here is purely additive — nothing is
wired into pricing yet, so all golden baselines are byte-identical.

Discounting convention
----------------------
Bond pricing uses the **same** effective-annual monthly discounting as
``CashFlowResult.pv_*``: a cash flow at month ``t`` (1-indexed, end of month)
is discounted by ``v ** t`` where ``v = (1 + annual_yield) ** (-1 / 12)``. This
keeps a bond PV and a projection PV on a single comparable basis.
"""

import numpy as np
from pydantic import Field, model_validator
from scipy.optimize import brentq

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisComputationError

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

    # ------------------------------------------------------------------
    # Slice 2 — book yield, investment income, duration / convexity
    # ------------------------------------------------------------------
    #
    # All measures below discount the aggregate cash-flow vector on the
    # engine's effective-annual monthly convention (``v = (1 + y) ** (-1/12)``,
    # cash flow at month ``t`` discounted by ``v ** t``). Time is expressed in
    # **years** (``t / 12``) so the duration / convexity formulas take their
    # textbook continuous-time-in-years shape against the effective-annual
    # yield ``y``:
    #
    #   price(y)          = Σ cf_t · (1 + y) ** (-τ_t)              , τ_t = t/12
    #   Macaulay duration = Σ τ_t · cf_t · (1+y)^(-τ_t) / price     (years)
    #   modified duration = Macaulay / (1 + y)                      (years)
    #   convexity         = Σ τ_t (τ_t+1) cf_t (1+y)^(-τ_t)
    #                          / (price · (1 + y) ** 2)             (years²)

    def _pv_components(self, annual_yield: float) -> tuple[np.ndarray, np.ndarray]:
        """
        Per-month present value of the aggregate cash flow and the matching
        time-in-years vector, on the engine discounting convention.

        Returns ``(pv, years)`` where ``pv[i]`` is the discounted cash flow at
        month ``i + 1`` and ``years[i] = (i + 1) / 12``. Shared by the duration
        and convexity measures.
        """
        cf = self.cash_flow_vector()
        periods = np.arange(1, cf.shape[0] + 1, dtype=np.float64)
        v = (1.0 + annual_yield) ** (-1.0 / 12.0)
        pv = cf * v**periods
        years = periods / 12.0
        return pv, years

    def book_yield(self) -> float | None:
        """
        Gross book yield — the effective-annual IRR of carrying value vs the
        portfolio's projected cash flows.

        Solves for the yield ``y`` at which the discounted cash flows equal the
        total carrying (book) value, on the engine's effective-annual monthly
        discounting. Uses ``scipy.optimize.brentq`` over ``[-0.99, 100.0]`` —
        the same solver and bracket as ``ProfitTester.irr`` — and returns
        ``None`` when the bracket contains no sign change (no recoverable IRR),
        mirroring the profit tester's None-on-no-sign-change guard.

        This is the **flat scalar** earned rate that Slice 3 hands to the Modco
        treaty; it is held constant over the horizon (no amortising / term
        structure — see ``docs/PLAN_asset_alm.md`` §5).
        """
        carrying = self.book_value
        cf = self.cash_flow_vector()
        periods = np.arange(1, cf.shape[0] + 1, dtype=np.float64)

        def excess_pv(annual_yield: float) -> float:
            v = (1.0 + annual_yield) ** (-1.0 / 12.0)
            return float(np.dot(cf, v**periods)) - carrying

        try:
            return float(brentq(excess_pv, -0.99, 100.0, xtol=1e-10, maxiter=500))
        except ValueError:
            # No sign change in the bracket — no recoverable book yield.
            return None

    def investment_income(
        self, reserve_vector: np.ndarray, annual_yield: float | None = None
    ) -> np.ndarray:
        """
        Monthly investment income earned on a reserve balance at the book yield.

        ``investment_income[t] = reserve_vector[t] · y / 12`` where ``y`` is the
        flat earned rate — ``annual_yield`` when supplied, else ``book_yield()``.
        This is the number the Modco treaty needs in Slice 3: the income thrown
        off by the assets backing the (notional) ceded reserve each month.

        Returns a ``(T,)`` float64 array the same length as ``reserve_vector``.
        Raises ``PolarisComputationError`` when no yield is supplied and
        ``book_yield()`` has no recoverable IRR.
        """
        if annual_yield is None:
            annual_yield = self.book_yield()
            if annual_yield is None:
                raise PolarisComputationError(
                    "investment_income: portfolio has no recoverable book_yield(); "
                    "pass an explicit annual_yield."
                )
        reserves = np.asarray(reserve_vector, dtype=np.float64)
        return reserves * annual_yield / 12.0

    def macaulay_duration(self, annual_yield: float) -> float:
        """
        Macaulay duration in **years** — the PV-weighted average time to the
        portfolio's cash flows at ``annual_yield``.

        Raises ``PolarisComputationError`` if the portfolio price is non-positive
        (no meaningful duration).
        """
        pv, years = self._pv_components(annual_yield)
        price = float(pv.sum())
        if price <= 0.0:
            raise PolarisComputationError(
                f"macaulay_duration: non-positive portfolio price ({price}) at "
                f"yield {annual_yield}; duration is undefined."
            )
        return float((years * pv).sum() / price)

    def modified_duration(self, annual_yield: float) -> float:
        """
        Modified duration in years — ``macaulay_duration / (1 + annual_yield)``.

        The price sensitivity ``-(1/P) dP/dy`` under the effective-annual yield
        convention, so the ``(1 + y)`` divisor (not a periodic-rate variant).
        """
        return self.macaulay_duration(annual_yield) / (1.0 + annual_yield)

    def convexity(self, annual_yield: float) -> float:
        """
        Convexity in **years²** — ``(1/P) d²P/dy²`` at ``annual_yield``.

        For a zero-coupon position maturing in ``N`` years this reduces to the
        textbook ``N (N + 1) / (1 + y) ** 2``.

        Raises ``PolarisComputationError`` if the portfolio price is non-positive.
        """
        pv, years = self._pv_components(annual_yield)
        price = float(pv.sum())
        if price <= 0.0:
            raise PolarisComputationError(
                f"convexity: non-positive portfolio price ({price}) at yield "
                f"{annual_yield}; convexity is undefined."
            )
        weighted = float((years * (years + 1.0) * pv).sum())
        return weighted / (price * (1.0 + annual_yield) ** 2)
