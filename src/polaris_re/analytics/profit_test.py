"""
ProfitTester - computes deal profitability metrics from a net CashFlowResult.

Profit vector: profit_t = net_cash_flow_t (already net of claims, expenses, reserve change)
PV profits: sum_t [profit_t * v^t], v = (1 + hurdle_rate)^(-1/12)
IRR: rate at which PV profits = 0, solved via scipy.optimize.brentq
Break-even year: first year where cumulative discounted profit > 0
Profit margin: pv_profits / pv_premiums

Capital-aware extension (ADR-048, Slice 2 of LICAT capital feature):
`run_with_capital(capital_model, *, nar=None)` joins the profit test with a
`LICATCapital` calculator and returns `ProfitResultWithCapital` carrying
peak/initial capital, PV capital (stock), PV capital strain (incremental),
return-on-capital, and capital-adjusted IRR.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from polaris_re.analytics.capital import CapitalResult, LICATCapital
from polaris_re.core.cashflow import CashFlowResult

__all__ = ["ProfitResultWithCapital", "ProfitTestResult", "ProfitTester"]


@dataclass
class ProfitTestResult:
    """
    Profitability metrics for a reinsurance deal.

    Monetary values in dollars. Rates as decimals (0.12 = 12%).

    Reporting guardrails (see ADR-041):
    - `irr` is None when the brentq solver does not converge OR when
      |irr| > IRR_SUPPRESS_MAGNITUDE and total_undiscounted_profit < 0.
      The latter case catches mathematically valid but economically
      meaningless roots on loss-making deals.
    - `profit_margin` is None when pv_premiums <= 0. A ratio with a
      non-positive denominator flips sign misleadingly on NET cash flows
      where ceded premiums can exceed gross.
    """

    hurdle_rate: float
    pv_profits: float
    pv_premiums: float
    profit_margin: float | None  # pv_profits / pv_premiums; None if pv_premiums <= 0
    irr: float | None  # None if solver does not converge or deal is degenerate
    breakeven_year: int | None  # None if never breaks even
    total_undiscounted_profit: float
    profit_by_year: np.ndarray  # shape (projection_years,)


@dataclass
class ProfitResultWithCapital(ProfitTestResult):
    """
    `ProfitTestResult` augmented with capital metrics (ADR-048, Slice 2).

    All `ProfitTestResult` fields are preserved unchanged. Additional fields:

    - `initial_capital`: required capital at projection month 0.
    - `peak_capital`: maximum required capital across the projection.
    - `pv_capital`: PV of the capital STOCK at the hurdle rate (default
      RoC denominator per ADR-048).
    - `pv_capital_strain`: PV of the capital STRAIN (period-over-period
      increases) at the hurdle rate (alternative RoC denominator).
    - `return_on_capital`: `pv_profits / pv_capital`. None when
      `pv_capital <= 0` (e.g. zero-factor capital model).
    - `capital_adjusted_irr`: IRR of `net_cash_flow_t - strain_t`, with
      a terminal release of the residual capital at month T-1. None when
      the distributable cash flow has no sign change.
    - `capital_by_period`: full `(T,)` capital schedule for downstream
      reporting.
    """

    initial_capital: float = 0.0
    peak_capital: float = 0.0
    pv_capital: float = 0.0
    pv_capital_strain: float = 0.0
    return_on_capital: float | None = None
    capital_adjusted_irr: float | None = None
    capital_by_period: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))


class ProfitTester:
    """
    Computes reinsurance deal profitability metrics from a NET or GROSS CashFlowResult.

    Accepts NET basis (post-treaty) or GROSS basis (standalone / no-treaty pricing).
    Rejects CEDED basis — it is meaningless to profit-test the ceded portion alone.

    Args:
        cashflows: NET or GROSS basis CashFlowResult.
        hurdle_rate: Annual hurdle rate, e.g. 0.10 for 10%.
    """

    # IRR values above this magnitude on loss-making deals are typically
    # artefacts of a degenerate sign change (brief early positive then all
    # negative) and are not economically interpretable. See ADR-041.
    IRR_SUPPRESS_MAGNITUDE: float = 0.5

    def __init__(self, cashflows: CashFlowResult, hurdle_rate: float) -> None:
        if cashflows.basis == "CEDED":
            raise ValueError(
                "ProfitTester does not accept CEDED basis CashFlowResult. "
                "Pass NET (post-treaty) or GROSS (standalone) cash flows."
            )
        self.cashflows = cashflows
        self.hurdle_rate = hurdle_rate

    def _npv(self, rate: float, profits: np.ndarray) -> float:
        """Net present value of profits at the given annual rate."""
        t = len(profits)
        v = (1.0 + rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, t + 1, dtype=np.float64)
        return float(np.dot(profits, discount_factors))

    def _solve_irr(self, profits: np.ndarray) -> float | None:
        """
        Solve IRR for an arbitrary cash-flow stream using brentq.

        Mirrors the IRR reporting guardrail used by `run()`:
        - Returns None if brentq cannot find a sign change.
        - Returns None on a loss-making stream when |irr| exceeds
          IRR_SUPPRESS_MAGNITUDE (degenerate sign-change root).
        """
        try:
            irr: float | None = brentq(
                lambda r: self._npv(r, profits),
                -0.99,
                100.0,
                xtol=1e-8,
                maxiter=500,
            )
        except ValueError:
            return None

        total = float(profits.sum())
        if irr is not None and abs(irr) > self.IRR_SUPPRESS_MAGNITUDE and total < 0:
            return None
        return irr

    def run(self) -> ProfitTestResult:
        """
        Compute all profit metrics.

        Returns:
            ProfitTestResult with IRR, PV profits, margin, and break-even year.
        """
        profits = self.cashflows.net_cash_flow
        t = len(profits)

        # PV profits at hurdle rate
        pv_profits = self._npv(self.hurdle_rate, profits)

        # PV premiums at hurdle rate
        pv_premiums = self._npv(self.hurdle_rate, self.cashflows.gross_premiums)

        # Profit margin — suppressed when pv_premiums <= 0, because the ratio
        # of two non-positive numbers flips sign misleadingly. This occurs on
        # NET cash flows where ceded YRT premiums can exceed gross premiums.
        profit_margin: float | None = pv_profits / pv_premiums if pv_premiums > 0.0 else None

        # IRR via Brent's method
        # Widen the search interval to [-0.99, 100.0] to handle edge cases.
        # If all profits are the same sign (no sign change), brentq cannot
        # find a root — this typically means the deal has no meaningful IRR
        # (e.g., no initial strain from expenses or commissions).
        irr: float | None = None
        try:
            irr = brentq(
                lambda r: self._npv(r, profits),
                -0.99,
                100.0,
                xtol=1e-8,
                maxiter=500,
            )
        except ValueError:
            # No sign change - profits all same sign
            irr = None

        # IRR reporting guardrail: on a loss-making deal (negative total
        # undiscounted profit), a root whose magnitude exceeds
        # IRR_SUPPRESS_MAGNITUDE is almost always an artefact of a
        # degenerate sign change (e.g. one small early positive followed by
        # monotonic losses) and should not be reported.
        total_undiscounted_profit = float(profits.sum())
        if (
            irr is not None
            and abs(irr) > self.IRR_SUPPRESS_MAGNITUDE
            and total_undiscounted_profit < 0
        ):
            irr = None

        # Break-even year: first year where cumulative discounted profit turns
        # positive and remains positive for the rest of the projection.
        # Previous logic used np.argmax which found the *first* month with
        # cum_pv > 0, which could be month 1 (premium received before claims
        # accumulate) even when cumulative profit later goes deeply negative.
        v = (1.0 + self.hurdle_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, t + 1, dtype=np.float64)
        discounted = profits * discount_factors
        cum_pv = np.cumsum(discounted)
        breakeven_year: int | None = None
        # Find the last month where cum_pv transitions from <= 0 to > 0.
        # After this crossing, cum_pv must stay positive through the end.
        for m in range(t - 1, -1, -1):
            if cum_pv[m] <= 0:
                # The crossover is at m+1 (if it exists and stays positive)
                if m + 1 < t and cum_pv[m + 1] > 0:
                    breakeven_year = int((m + 1) // 12 + 1)
                break
        else:
            # cum_pv is positive from month 0 onward (entire projection profitable)
            if cum_pv[0] > 0:
                breakeven_year = 1

        # Annual profit summary
        # Pad to full years if needed
        n_full_years = t // 12
        remainder = t % 12
        if n_full_years > 0:
            profit_by_year = profits[: n_full_years * 12].reshape(-1, 12).sum(axis=1)
        else:
            profit_by_year = np.array([], dtype=np.float64)
        if remainder > 0:
            partial_year = profits[n_full_years * 12 :].sum()
            profit_by_year = np.append(profit_by_year, partial_year)

        return ProfitTestResult(
            hurdle_rate=self.hurdle_rate,
            pv_profits=pv_profits,
            pv_premiums=pv_premiums,
            profit_margin=profit_margin,
            irr=irr,
            breakeven_year=breakeven_year,
            total_undiscounted_profit=total_undiscounted_profit,
            profit_by_year=profit_by_year,
        )

    def run_with_capital(
        self,
        capital_model: LICATCapital,
        *,
        nar: np.ndarray | None = None,
    ) -> ProfitResultWithCapital:
        """
        Compute profit metrics jointly with required capital and RoC.

        Wraps `run()` and joins the result with a `LICATCapital`
        calculator. The returned `ProfitResultWithCapital` contains every
        field on `ProfitTestResult` (so callers that only inspect base
        fields keep working) plus capital metrics.

        Args:
            capital_model: An instantiated `LICATCapital` (typically built
                via `LICATCapital.for_product(product_type)`).
            nar: Optional NAR vector of shape `(T,)`. Forwarded to
                `LICATCapital.required_capital`. If neither this nor
                `cashflows.nar` is set, the underlying calculator raises
                `PolarisComputationError`.

        Returns:
            ProfitResultWithCapital with `pv_capital`, `return_on_capital`,
            `capital_adjusted_irr`, etc. populated. RoC denominator is
            PV(capital stock) at the hurdle rate (ADR-048).
        """
        base = self.run()
        capital: CapitalResult = capital_model.required_capital(self.cashflows, nar=nar)

        pv_capital = capital.pv_capital(self.hurdle_rate)
        pv_capital_strain = capital.pv_capital_strain(self.hurdle_rate)

        # RoC denominator = pv_capital (stock) per ADR-048. Suppress when
        # the stock is non-positive — the ratio is not meaningful for
        # zero-capital models or anomalous negative balances.
        return_on_capital: float | None = base.pv_profits / pv_capital if pv_capital > 0.0 else None

        # Capital-adjusted IRR: IRR of distributable cash flow, defined as
        # net_cash_flow_t - strain_t with a terminal release of the
        # residual capital balance at month T-1. Sum of strain over the
        # adjusted projection is therefore zero (full capital recycle).
        profits = self.cashflows.net_cash_flow
        strain = capital.capital_strain()
        n = len(profits)
        if n == 0 or len(strain) != n:
            distributable = profits.copy()
        else:
            distributable = profits - strain
            # Terminal release of residual capital
            distributable[-1] += float(capital.capital_by_period[-1])

        capital_adjusted_irr = self._solve_irr(distributable) if n > 0 else None

        return ProfitResultWithCapital(
            hurdle_rate=base.hurdle_rate,
            pv_profits=base.pv_profits,
            pv_premiums=base.pv_premiums,
            profit_margin=base.profit_margin,
            irr=base.irr,
            breakeven_year=base.breakeven_year,
            total_undiscounted_profit=base.total_undiscounted_profit,
            profit_by_year=base.profit_by_year,
            initial_capital=capital.initial_capital,
            peak_capital=capital.peak_capital,
            pv_capital=pv_capital,
            pv_capital_strain=pv_capital_strain,
            return_on_capital=return_on_capital,
            capital_adjusted_irr=capital_adjusted_irr,
            capital_by_period=capital.capital_by_period.copy(),
        )
