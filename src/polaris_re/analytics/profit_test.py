"""
ProfitTester — computes deal profitability metrics from a net CashFlowResult.

Implementation Notes for Claude Code:
--------------------------------------
PROFIT VECTOR:
    profit_t = net_cash_flow_t   (already net of claims, expenses, Δreserve)

PRESENT VALUE:
    PV_profits = Σ_t [profit_t * v^t],  v = (1 + hurdle_rate)^(-1/12)

IRR — recommended approach (scipy root-finding, more robust than numpy_financial):
    from scipy.optimize import brentq
    def npv(rate):
        v = (1 + rate) ** (-1/12)
        return float(np.dot(profits, v ** np.arange(1, T+1)))
    try:
        irr = brentq(npv, -0.50, 10.0, xtol=1e-8)
    except ValueError:
        irr = None   # no sign change — profits all same sign

BREAK-EVEN YEAR:
    discounted = profits * discount_factors
    cum_pv = np.cumsum(discounted)
    mask = cum_pv > 0
    breakeven_year = (np.argmax(mask) // 12 + 1) if mask.any() else None

PROFIT MARGIN:
    profit_margin = pv_profits / pv_premiums

ANNUAL PROFIT SUMMARY:
    profit_by_year = profits.reshape(-1, 12).sum(axis=1)   # shape (T//12,)

TODO (Phase 1, Milestone 1.5):
- Implement ProfitTester.run()
- Handle no-convergence case gracefully (irr=None, log Rich warning)
- Tests: tests/test_analytics/test_profit_test.py
  Key test: construct profit vector where PV@10% = 0 → assert IRR ≈ 10%
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["ProfitTestResult", "ProfitTester"]


@dataclass
class ProfitTestResult:
    """
    Profitability metrics for a reinsurance deal.

    Monetary values in dollars. Rates as decimals (0.12 = 12%).
    """

    hurdle_rate: float
    pv_profits: float
    pv_premiums: float
    profit_margin: float  # pv_profits / pv_premiums
    irr: float | None  # None if solver does not converge
    breakeven_year: int | None  # None if never breaks even
    total_undiscounted_profit: float
    profit_by_year: np.ndarray  # shape (projection_years,)


class ProfitTester:
    """
    Computes reinsurance deal profitability metrics from a NET CashFlowResult.

    Args:
        cashflows: NET basis CashFlowResult (after treaty application).
        hurdle_rate: Annual hurdle rate, e.g. 0.10 for 10%.
    """

    def __init__(self, cashflows: CashFlowResult, hurdle_rate: float) -> None:
        if cashflows.basis != "NET":
            raise ValueError(
                f"ProfitTester requires NET basis CashFlowResult, got '{cashflows.basis}'. "
                "Apply a treaty to gross cash flows first."
            )
        self.cashflows = cashflows
        self.hurdle_rate = hurdle_rate

    def run(self) -> ProfitTestResult:
        """
        Compute all profit metrics.

        Returns:
            ProfitTestResult with IRR, PV profits, margin, and break-even year.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "ProfitTester.run() not yet implemented. See module docstring for formulas."
        )
