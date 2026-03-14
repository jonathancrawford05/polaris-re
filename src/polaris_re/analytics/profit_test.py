"""
ProfitTester — computes deal profitability metrics from a CashFlowResult.

Takes a net CashFlowResult (after treaty application) and a hurdle rate,
and returns IRR, PV of profits, profit margin, and break-even duration.

Implementation Notes for Claude Code:
--------------------------------------
PROFIT VECTOR:
    The profit at each time step is the net cash flow surplus:
        profit_t = net_premium_t - net_claim_t - expense_t - Δreserve_t
    This should already equal CashFlowResult.net_cash_flow for the NET basis.

PRESENT VALUE OF PROFITS:
    PV_profits = Σ_t [profit_t * v^t]
    where v = (1 + hurdle_rate)^(-1/12) for monthly time steps.

IRR (Internal Rate of Return):
    The IRR is the discount rate i* such that:
        Σ_t [profit_t * (1 + i*)^(-t/12)] = 0
    Use numpy_financial.irr(profit_vector) — NOTE: numpy_financial.irr expects
    an annual cash flow vector. Convert monthly profits to annual by summing
    12 months at a time before calling irr(), or use a root-finding approach
    (scipy.optimize.brentq) directly on the PV function.

    Recommended approach:
        from scipy.optimize import brentq
        def npv(rate): return sum(profit_t / (1+rate)**(t/12) for t, profit_t in enumerate(profits))
        irr = brentq(npv, -0.5, 5.0)   # search between -50% and 500%

BREAK-EVEN YEAR:
    First year where cumulative PV profits > 0.
    breakeven_month = np.argmax(np.cumsum(discounted_profits) > 0)
    breakeven_year = breakeven_month // 12 + 1

PROFIT MARGIN:
    profit_margin = PV_profits / PV_gross_premiums

TODO (Phase 1, Milestone 1.5):
- Implement ProfitTestResult dataclass
- Implement ProfitTester.run() following formulas above
- Handle edge case where IRR solver does not converge (return None, log warning)
- Add tests verifying: if profit_t = 0 for all t, IRR = undefined; if constructed
  such that PV profits = 0 at 10%, IRR should equal 10%.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["ProfitTester", "ProfitTestResult"]


@dataclass
class ProfitTestResult:
    """
    Output of a profit test run.

    All monetary values are in dollars (same currency as CashFlowResult inputs).
    Rates are expressed as decimals (e.g., 0.12 = 12%).
    """

    hurdle_rate: float
    pv_profits: float
    pv_premiums: float
    profit_margin: float          # pv_profits / pv_premiums
    irr: float | None             # None if solver does not converge
    breakeven_year: int | None    # None if never breaks even in projection horizon
    total_undiscounted_profit: float
    profit_by_year: np.ndarray    # shape (projection_years,) — annual sum of monthly profits


class ProfitTester:
    """
    Computes reinsurance deal profitability metrics.

    Args:
        cashflows: NET basis CashFlowResult (after treaty application).
        hurdle_rate: Annual hurdle rate for discounting (e.g. 0.10 for 10%).
    """

    def __init__(self, cashflows: CashFlowResult, hurdle_rate: float) -> None:
        if cashflows.basis != "NET":
            raise ValueError(
                f"ProfitTester requires NET basis CashFlowResult, got {cashflows.basis}. "
                "Apply a treaty to the gross cash flows first."
            )
        self.cashflows = cashflows
        self.hurdle_rate = hurdle_rate

    def run(self) -> ProfitTestResult:
        """
        Compute all profit metrics and return a ProfitTestResult.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "ProfitTester.run() not yet implemented. "
            "See module docstring for IRR, PV, and break-even formulas."
        )
