"""
Profit tester tests.

Key closed-form tests:
  1. Zero profit vector → IRR undefined (or scipy raises)
  2. Constant positive profit → IRR deterministic from formula
  3. Constructed profit vector where PV@10% = 0 → IRR should equal 10%
"""

import pytest

pytestmark = pytest.mark.xfail(
    reason="ProfitTester.run() not yet implemented.",
    strict=False,
)


class TestProfitTester:
    def test_irr_equals_hurdle_when_pv_profits_zero(self):
        """
        CLOSED-FORM: Construct a cash flow vector where PV discounted at 10% = 0.
        The IRR returned must equal 10% (to within 1e-4).
        """
        pytest.skip("ProfitTester not yet implemented")

    def test_positive_pv_profits_at_hurdle(self):
        """If all profits positive, PV profits > 0 and IRR > hurdle rate."""
        pytest.skip("ProfitTester not yet implemented")

    def test_profit_margin_bounds(self):
        """Profit margin must be between -1 and 1 for reasonable inputs."""
        pytest.skip("ProfitTester not yet implemented")

    def test_raises_on_gross_basis_input(self):
        """ProfitTester must raise ValueError if given a GROSS basis CashFlowResult."""
        from datetime import date

        from polaris_re.analytics.profit_test import ProfitTester
        from polaris_re.core.cashflow import CashFlowResult

        gross_cf = CashFlowResult(
            run_id="test",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="v1",
            product_type="TERM",
        )
        with pytest.raises(ValueError, match="NET"):
            ProfitTester(cashflows=gross_cf, hurdle_rate=0.10)
