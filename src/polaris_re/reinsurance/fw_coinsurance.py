"""
FWCoinsuranceTreaty — Funds-Withheld Coinsurance reinsurance treaty engine.

Funds-withheld (FW) coinsurance is coinsurance in which the reinsurer assumes
the full proportional share of ALL cash flows — premiums, claims, lapses,
expenses AND reserves — exactly like ordinary coinsurance, but the **assets**
backing the ceded reserve are *withheld* by the cedant in a funds-withheld
account rather than transferred to the reinsurer. To compensate the reinsurer
for not holding those assets, the cedant credits funds-withheld interest each
month on the funds-withheld balance:

    funds_withheld_interest_t = fw_balance_t * fw_rate / 12

where the funds-withheld balance equals the ceded reserve balance
(``fw_balance_t = gross_reserve_balance_t * cession_pct``) and ``fw_rate`` is,
by default, the flat ``funds_withheld_rate``. When an ``AssetPortfolio`` is
supplied to ``apply()`` it takes precedence (Option A, identical to
``ModcoTreaty``): the rate becomes the portfolio's gross **book yield** on the
withheld reserve, with the flat rate kept as the fallback whenever the book
yield has no recoverable IRR (``book_yield()`` returns ``None``). Omitting the
portfolio leaves the flat-rate path byte-identical.

Relationship to the other proportional treaties
------------------------------------------------
- **vs Coinsurance:** identical proportional split of every line INCLUDING
  reserves (``net_reserve = gross_reserve * (1 - c)``). The only difference is
  the added funds-withheld interest credit — coinsurance leaves the reinsurer's
  investment income on ceded reserves *implicit* (it holds the assets and earns
  it directly, out of the liability projection); FW coinsurance makes it an
  *explicit* treaty cash flow because the cedant holds the assets.
- **vs Modco:** both retain the backing assets with the cedant and credit
  interest on them. The distinction is the reserve treatment — Modco does NOT
  transfer the reserve (``net_reserve = gross_reserve``; ceded reserve is
  notional), whereas FW coinsurance transfers the reserve proportionally like
  coinsurance. The interest mechanic (rate resolution, Option-A book yield,
  both-sides-equal transfer) is shared.

NCF additivity proof (cession = c, retention r = 1 - c):
    net_ncf   = net_prem - net_claims - net_lapses - net_exp - net_res_inc - fwi
    ceded_ncf = ceded_prem - ceded_claims - ceded_lapses - ceded_exp - ceded_res_inc + fwi
    net_ncf + ceded_ncf
        = gross_prem - gross_claims - gross_lapses - gross_exp - gross_res_inc
        = gross_ncf  ✓   (the funds-withheld interest ``fwi`` cancels)

The funds-withheld interest is stored in ``CashFlowResult.funds_withheld_interest``
on both the net and ceded results for auditability.
"""

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.reinsurance.base_treaty import BaseTreaty

if TYPE_CHECKING:
    from polaris_re.core.asset import AssetPortfolio
    from polaris_re.core.inforce import InforceBlock

__all__ = ["FWCoinsuranceTreaty"]


class FWCoinsuranceTreaty(PolarisBaseModel, BaseTreaty):
    """
    Funds-Withheld Coinsurance reinsurance treaty.

    Proportional share of all cash flows including reserves (like coinsurance),
    with the reserve-backing assets withheld by the cedant and compensated by a
    funds-withheld interest credit to the reinsurer (like modco interest).
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of all cash flows ceded (e.g. 0.75 = 75%).",
    )
    funds_withheld_rate: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Annual interest rate credited by the cedant to the reinsurer on the "
            "funds-withheld balance (the withheld ceded reserve). Typically equals "
            "the cedant's portfolio yield (e.g. 0.045 for 4.5%)."
        ),
    )
    include_expense_allowance: bool = Field(
        default=True,
        description=(
            "If True, the reinsurer takes a proportional share of expenses (paying "
            "the cedant an implicit proportional expense allowance), matching "
            "coinsurance. If False, expenses stay entirely with the cedant."
        ),
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    @model_validator(mode="after")
    def validate_fw_rate_positive(self) -> "FWCoinsuranceTreaty":
        if self.funds_withheld_rate < 0.0:
            raise ValueError(f"funds_withheld_rate must be >= 0.0, got {self.funds_withheld_rate}")
        return self

    def _resolve_fw_rate(self, asset_portfolio: "AssetPortfolio | None") -> float:
        """
        Resolve the effective annual funds-withheld interest rate (Option A).

        When an ``AssetPortfolio`` is supplied, its gross ``book_yield()`` drives
        the funds-withheld interest and takes precedence over the flat
        ``funds_withheld_rate``. The flat rate is the fallback whenever the book
        yield has no recoverable IRR (``book_yield()`` returns ``None``). With no
        portfolio, the flat rate is returned unchanged — the byte-identical
        default path. Mirrors ``ModcoTreaty._resolve_modco_rate``.
        """
        if asset_portfolio is not None:
            book_yield = asset_portfolio.book_yield()
            if book_yield is not None:
                return book_yield
        return self.funds_withheld_rate

    def apply(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock | None" = None,
        asset_portfolio: "AssetPortfolio | None" = None,
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply the funds-withheld coinsurance treaty to gross cash flows.

        Every line is split proportionally by the effective cession rate
        (including reserves, like coinsurance), then a funds-withheld interest
        credit is folded in as a cedant->reinsurer transfer that preserves
        ``net + ceded == gross``.

        Args:
            gross:   GROSS basis CashFlowResult. ``reserve_balance`` must be
                     populated for the funds-withheld interest to be meaningful.
            inforce: Optional InforceBlock for policy-level cession overrides.
            asset_portfolio: Optional ``AssetPortfolio`` backing the withheld
                     reserves. When supplied, its gross ``book_yield()`` drives
                     the funds-withheld interest (Option A precedence) instead of
                     the flat ``funds_withheld_rate``; the flat rate is the
                     fallback when the book yield is unrecoverable. Default
                     ``None`` preserves the flat-rate path byte-identically.

        Returns:
            (net, ceded) CashFlowResult tuple. Both carry the monthly
            funds-withheld interest in ``funds_withheld_interest``.
        """
        if len(gross.reserve_balance) == 0:
            raise PolarisComputationError(
                "FWCoinsuranceTreaty requires reserve_balance in gross CashFlowResult."
            )

        c = self._resolve_cession(self.cession_pct, inforce)
        r = 1.0 - c  # retention proportion

        # All lines split proportionally (identical to coinsurance).
        net_premiums = gross.gross_premiums * r
        ceded_premiums = gross.gross_premiums * c

        net_claims = gross.death_claims * r
        ceded_claims = gross.death_claims * c

        net_lapses = gross.lapse_surrenders * r
        ceded_lapses = gross.lapse_surrenders * c

        if self.include_expense_allowance:
            net_expenses = gross.expenses * r
            ceded_expenses = gross.expenses * c
        else:
            net_expenses = gross.expenses.copy()
            ceded_expenses = np.zeros_like(gross.expenses)

        # Reserves: transferred proportionally (like coinsurance, unlike modco).
        net_reserve_balance = gross.reserve_balance * r
        ceded_reserve_balance = gross.reserve_balance * c
        net_reserve_inc = gross.reserve_increase * r
        ceded_reserve_inc = gross.reserve_increase * c

        # Funds-withheld interest: cedant credits the reinsurer on the withheld
        # ceded reserve balance. fwi_t = ceded_reserve_balance_t * annual_rate / 12.
        # The annual rate is the asset book yield when a portfolio is supplied
        # (Option A precedence), else the flat funds_withheld_rate.
        fw_rate = self._resolve_fw_rate(asset_portfolio)
        funds_withheld_interest = ceded_reserve_balance * fw_rate / 12.0

        # Net pays the interest; ceded receives it — a transfer that nets to zero.
        net_ncf = (
            net_premiums
            - net_claims
            - net_lapses
            - net_expenses
            - net_reserve_inc
            - funds_withheld_interest
        )
        ceded_ncf = (
            ceded_premiums
            - ceded_claims
            - ceded_lapses
            - ceded_expenses
            - ceded_reserve_inc
            + funds_withheld_interest
        )

        net = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="NET",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=net_premiums,
            death_claims=net_claims,
            lapse_surrenders=net_lapses,
            expenses=net_expenses,
            reserve_balance=net_reserve_balance,
            reserve_increase=net_reserve_inc,
            net_cash_flow=net_ncf,
            funds_withheld_interest=funds_withheld_interest,
        )

        ceded = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="CEDED",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=ceded_premiums,
            death_claims=ceded_claims,
            lapse_surrenders=ceded_lapses,
            expenses=ceded_expenses,
            reserve_balance=ceded_reserve_balance,
            reserve_increase=ceded_reserve_inc,
            net_cash_flow=ceded_ncf,
            funds_withheld_interest=funds_withheld_interest,
        )

        return net, ceded
