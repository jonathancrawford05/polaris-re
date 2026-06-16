"""
PremiumSufficiencyTester — gross-premium-adequacy analysis on a CashFlowResult.

Answers the deal-screening question: *does the premium cover expected benefits
plus expenses, with the required profit margin left over?* This is a
gross-premium-valuation view of a block, distinct from `ProfitTester`:

- `ProfitTester` measures economic profit including the reserve movement
  (`net_cash_flow = premiums - benefits - expenses - ΔReserve`) and discounts
  at a hurdle rate to produce PV profits / IRR / break-even.
- `PremiumSufficiencyTester` deliberately EXCLUDES the reserve movement. A
  reserve increase is a balance-sheet timing item that reverses over the life
  of the block; it is not an economic cost of the coverage. Premium adequacy
  therefore compares the PV of premiums against the PV of *benefits + expenses*
  only:

      sufficiency_margin = PV(premiums) - PV(benefits) - PV(expenses)

  where PV(benefits) = PV(death_claims + lapse_surrenders).

The headline ratios are the actuarial loss / expense / combined ratios on a
present-value basis:

      loss_ratio     = PV(benefits) / PV(premiums)
      expense_ratio  = PV(expenses) / PV(premiums)
      combined_ratio = (PV(benefits) + PV(expenses)) / PV(premiums)
      sufficiency_ratio = sufficiency_margin / PV(premiums) = 1 - combined_ratio

A premium is "sufficient" when the margin left after benefits and expenses
meets the required profit target expressed as a fraction of premium:

      is_sufficient ⇔ sufficiency_ratio >= target_margin
                    ⇔ combined_ratio <= 1 - target_margin

`target_margin = 0.0` (the default) tests bare cost coverage.

The tester is basis-agnostic: it operates on whatever basis the supplied
`CashFlowResult` carries. On a GROSS result it answers "is the cedant's
direct premium adequate"; on a reinsurer-view NET result (the basis
`polaris price` reports) it answers "is the reinsurance premium adequate for
the risk assumed". Discounting uses the same monthly convention as
`ProfitTester` and `CashFlowResult.pv_premiums`:
``v = (1 + rate) ** (-1/12)``, factors ``v ** [1 .. T]``.
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["PremiumSufficiencyResult", "PremiumSufficiencyTester"]


@dataclass
class PremiumSufficiencyResult:
    """
    Present-value premium-adequacy metrics for a block of business.

    Monetary values in dollars; ratios as decimals (0.40 = 40%).

    The benefit total is PV(death_claims + lapse_surrenders). The reserve
    movement is intentionally excluded (see module docstring) — premium
    adequacy is an economic-cost comparison, not a balance-sheet one.

    Ratios are None when `pv_premiums <= 0`: a ratio with a non-positive
    premium denominator is not interpretable (this mirrors the
    `ProfitTester.profit_margin` guardrail and can arise on a NET basis where
    ceded premiums exceed gross). When the ratios are None, `is_sufficient`
    is False — sufficiency cannot be established without positive premium.
    """

    discount_rate: float
    target_margin: float  # required profit margin as a fraction of PV premiums
    pv_premiums: float
    pv_claims: float  # PV(death_claims)
    pv_surrenders: float  # PV(lapse_surrenders)
    pv_benefits: float  # PV(death_claims + lapse_surrenders)
    pv_expenses: float
    sufficiency_margin: float  # pv_premiums - pv_benefits - pv_expenses
    sufficiency_ratio: float | None  # sufficiency_margin / pv_premiums
    loss_ratio: float | None  # pv_benefits / pv_premiums
    expense_ratio: float | None  # pv_expenses / pv_premiums
    combined_ratio: float | None  # (pv_benefits + pv_expenses) / pv_premiums
    is_sufficient: bool  # sufficiency_ratio >= target_margin


class PremiumSufficiencyTester:
    """
    Computes premium-adequacy metrics from a `CashFlowResult`.

    Args:
        cashflows: A GROSS, NET, or CEDED `CashFlowResult`. The tester reads
            `gross_premiums`, `death_claims`, `lapse_surrenders`, and
            `expenses`; it does not use the reserve arrays.
        discount_rate: Annual discount rate applied to every cash-flow line,
            e.g. 0.04 for 4%. Typically the valuation interest rate rather
            than a profit hurdle — adequacy asks whether premiums cover costs,
            not whether the deal clears the cost of capital.
        target_margin: Required profit margin as a fraction of PV premiums,
            in [0, 1). The premium is "sufficient" when the post-cost margin
            ratio meets this target. Defaults to 0.0 (bare cost coverage).

    Raises:
        ValueError: if `target_margin` is outside [0, 1).
    """

    def __init__(
        self,
        cashflows: CashFlowResult,
        discount_rate: float,
        *,
        target_margin: float = 0.0,
    ) -> None:
        if not 0.0 <= target_margin < 1.0:
            raise ValueError(
                f"target_margin must be in [0, 1), got {target_margin}. It is a profit "
                "margin expressed as a fraction of premium."
            )
        self.cashflows = cashflows
        self.discount_rate = discount_rate
        self.target_margin = target_margin

    def _pv(self, flows: np.ndarray) -> float:
        """Present value of a monthly cash-flow array at the discount rate."""
        n_periods = len(flows)
        if n_periods == 0:
            return 0.0
        v = (1.0 + self.discount_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, n_periods + 1, dtype=np.float64)
        return float(np.dot(flows, discount_factors))

    def run(self) -> PremiumSufficiencyResult:
        """
        Compute all premium-adequacy metrics.

        Returns:
            PremiumSufficiencyResult with PV components, the sufficiency
            margin, the loss / expense / combined ratios, and the
            `is_sufficient` verdict against `target_margin`.
        """
        cf = self.cashflows
        pv_premiums = self._pv(cf.gross_premiums)
        pv_claims = self._pv(cf.death_claims)
        pv_surrenders = self._pv(cf.lapse_surrenders)
        pv_benefits = pv_claims + pv_surrenders
        pv_expenses = self._pv(cf.expenses)

        sufficiency_margin = pv_premiums - pv_benefits - pv_expenses

        if pv_premiums > 0.0:
            sufficiency_ratio: float | None = sufficiency_margin / pv_premiums
            loss_ratio: float | None = pv_benefits / pv_premiums
            expense_ratio: float | None = pv_expenses / pv_premiums
            combined_ratio: float | None = (pv_benefits + pv_expenses) / pv_premiums
            is_sufficient = sufficiency_ratio >= self.target_margin
        else:
            sufficiency_ratio = None
            loss_ratio = None
            expense_ratio = None
            combined_ratio = None
            is_sufficient = False

        return PremiumSufficiencyResult(
            discount_rate=self.discount_rate,
            target_margin=self.target_margin,
            pv_premiums=pv_premiums,
            pv_claims=pv_claims,
            pv_surrenders=pv_surrenders,
            pv_benefits=pv_benefits,
            pv_expenses=pv_expenses,
            sufficiency_margin=sufficiency_margin,
            sufficiency_ratio=sufficiency_ratio,
            loss_ratio=loss_ratio,
            expense_ratio=expense_ratio,
            combined_ratio=combined_ratio,
            is_sufficient=is_sufficient,
        )
