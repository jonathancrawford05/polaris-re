"""
PremiumDeficiencyTester — loss-recognition / premium-deficiency-reserve floor.

Turns the gross-premium-adequacy view of `PremiumSufficiencyTester` into a
*reserve floor* via the FAS 60 / ASC 944 loss-recognition test. Where the
sufficiency analyzer answers "does the premium cover future benefits plus
expenses?" and reports a signed margin, this tester answers the balance-sheet
consequence: "*if it does not, how large a reserve must be held today to cover
the shortfall?*"

The prospective gross premium reserve (GPV) at the valuation date is the present
value of future benefits and expenses in excess of future gross premiums:

    GPV = PV(death_claims + lapse_surrenders) + PV(expenses) - PV(gross_premiums)

which is exactly the negative of `PremiumSufficiencyResult.sufficiency_margin`
(the reserve movement is excluded on both — premium adequacy is an economic-cost
comparison, not a balance-sheet timing one). A premium deficiency exists when
this gross premium reserve exceeds the reserve already held for the block; the
premium-deficiency reserve (PDR) is the amount needed to bring the held reserve
up to the gross premium reserve, floored at zero (a premium *surplus* never
creates a negative reserve):

    PDR          = max(0, GPV - existing_reserve)
    reserve_floor = max(existing_reserve, GPV) = existing_reserve + PDR

With the default `existing_reserve = 0.0` this is the bare test — do the premiums
alone cover future benefits and expenses? — and the PDR is simply the sufficiency
shortfall floored at zero. Pass the reserve held at the valuation date to run the
full FAS 60 net loss-recognition test (the PDR is then established only to the
extent the held reserve is insufficient).

Like `PremiumSufficiencyTester`, the tester is basis-agnostic: on a GROSS result
it tests the cedant's direct premium, on a reinsurer-view NET result the ceded
premium against the risk assumed. Discounting reuses `PremiumSufficiencyTester`
verbatim (``v = (1 + rate) ** (-1/12)``, factors ``v ** [1 .. T]``), so the
gross premium reserve agrees with the sufficiency margin to floating-point.

Scope: this is the point-in-time loss-recognition test at the valuation date. A
per-period roll-forward of the reserve floor across the projection (comparing the
prospective GPV to the held reserve at every future duration) is a follow-up.
"""

from dataclasses import dataclass

from polaris_re.analytics.premium_sufficiency import PremiumSufficiencyTester
from polaris_re.core.cashflow import CashFlowResult

__all__ = ["PremiumDeficiencyResult", "PremiumDeficiencyTester"]


@dataclass
class PremiumDeficiencyResult:
    """
    Loss-recognition metrics for a block of business, in dollars.

    The gross premium reserve is the prospective PV of future benefits and
    expenses net of future gross premiums (the reserve movement is excluded —
    see the module docstring). The premium-deficiency reserve is that value in
    excess of the reserve already held, floored at zero; the reserve floor is
    the resulting minimum reserve the block must carry.
    """

    discount_rate: float
    existing_reserve: float  # reserve already held at the valuation date
    pv_premiums: float
    pv_claims: float  # PV(death_claims)
    pv_surrenders: float  # PV(lapse_surrenders)
    pv_benefits: float  # PV(death_claims + lapse_surrenders)
    pv_expenses: float
    gross_premium_reserve: float  # PV(benefits + expenses) - PV(premiums)
    premium_deficiency_reserve: float  # max(0, gross_premium_reserve - existing_reserve)
    reserve_floor: float  # max(existing_reserve, gross_premium_reserve)
    is_deficient: bool  # premium_deficiency_reserve > 0


class PremiumDeficiencyTester:
    """
    Computes the premium-deficiency reserve floor from a `CashFlowResult`.

    Args:
        cashflows: A GROSS, NET, or CEDED `CashFlowResult`. The tester reads
            `gross_premiums`, `death_claims`, `lapse_surrenders`, and
            `expenses`; it does not use the reserve arrays (the reserve already
            held is supplied explicitly via `existing_reserve`).
        discount_rate: Annual discount rate applied to every cash-flow line,
            e.g. 0.04 for 4%. Typically the valuation interest rate — the test
            asks whether premiums cover future costs on the valuation basis.
        existing_reserve: Reserve already held for the block at the valuation
            date, netted against the gross premium reserve per FAS 60. Must be
            non-negative. Defaults to 0.0 (the bare test — premiums alone
            against future benefits + expenses).

    Raises:
        ValueError: if `existing_reserve` is negative.
    """

    def __init__(
        self,
        cashflows: CashFlowResult,
        discount_rate: float,
        *,
        existing_reserve: float = 0.0,
    ) -> None:
        if existing_reserve < 0.0:
            raise ValueError(
                f"existing_reserve must be non-negative, got {existing_reserve}. It is "
                "the reserve already held for the block at the valuation date."
            )
        self.cashflows = cashflows
        self.discount_rate = discount_rate
        self.existing_reserve = existing_reserve

    def run(self) -> PremiumDeficiencyResult:
        """
        Compute the loss-recognition metrics.

        Returns:
            PremiumDeficiencyResult with the PV components, the prospective
            gross premium reserve, the premium-deficiency reserve, the resulting
            reserve floor, and the `is_deficient` verdict.
        """
        # Reuse the sufficiency analyzer's PV components and discounting verbatim
        # so the gross premium reserve is exactly the negative of its margin.
        suff = PremiumSufficiencyTester(self.cashflows, self.discount_rate).run()
        gross_premium_reserve = -suff.sufficiency_margin

        premium_deficiency_reserve = max(0.0, gross_premium_reserve - self.existing_reserve)
        reserve_floor = self.existing_reserve + premium_deficiency_reserve

        return PremiumDeficiencyResult(
            discount_rate=self.discount_rate,
            existing_reserve=self.existing_reserve,
            pv_premiums=suff.pv_premiums,
            pv_claims=suff.pv_claims,
            pv_surrenders=suff.pv_surrenders,
            pv_benefits=suff.pv_benefits,
            pv_expenses=suff.pv_expenses,
            gross_premium_reserve=gross_premium_reserve,
            premium_deficiency_reserve=premium_deficiency_reserve,
            reserve_floor=reserve_floor,
            is_deficient=premium_deficiency_reserve > 0.0,
        )
