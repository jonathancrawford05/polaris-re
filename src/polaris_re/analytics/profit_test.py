"""
ProfitTester - computes deal profitability metrics from a net CashFlowResult.

Profit vector: profit_t = net_cash_flow_t (already net of claims, expenses, reserve change)
PV profits: sum_t [profit_t * v^t], v = (1 + hurdle_rate)^(-1/12)
IRR: rate at which PV profits = 0, solved via scipy.optimize.brentq
Break-even year: first year where cumulative discounted profit > 0
Profit margin: pv_profits / pv_premiums
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["ProfitTestResult", "ProfitTester"]


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
