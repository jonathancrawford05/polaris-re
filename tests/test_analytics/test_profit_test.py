"""
Profit tester tests.

Key closed-form tests:
  1. Constructed profit vector where PV@10% = 0 -> IRR should equal 10%
  2. Constant positive profit -> PV profits > 0, IRR > hurdle rate
  3. Profit margin between -1 and 1 for reasonable inputs
  4. Integration: TermLife -> CoinsuranceTreaty -> ProfitTester
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_net_cashflow(
    profits: np.ndarray,
    premiums: np.ndarray | None = None,
) -> CashFlowResult:
    """Helper to create a minimal NET CashFlowResult for profit testing."""
    t = len(profits)
    if premiums is None:
        premiums = np.ones(t, dtype=np.float64) * 100.0
    return CashFlowResult(
        run_id="test",
        valuation_date=date(2025, 1, 1),
        basis="NET",
        assumption_set_version="v1",
        product_type="TERM",
        projection_months=t,
        time_index=np.arange(
            np.datetime64("2025-01"), np.datetime64("2025-01") + t, dtype="datetime64[M]"
        ),
        gross_premiums=premiums,
        death_claims=np.zeros(t, dtype=np.float64),
        lapse_surrenders=np.zeros(t, dtype=np.float64),
        expenses=np.zeros(t, dtype=np.float64),
        reserve_balance=np.zeros(t, dtype=np.float64),
        reserve_increase=np.zeros(t, dtype=np.float64),
        net_cash_flow=profits,
    )


class TestProfitTesterValidation:
    """Input validation tests."""

    def test_raises_on_gross_basis_input(self):
        """ProfitTester must raise ValueError if given a GROSS basis CashFlowResult."""
        gross_cf = CashFlowResult(
            run_id="test",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="v1",
            product_type="TERM",
        )
        with pytest.raises(ValueError, match="NET"):
            ProfitTester(cashflows=gross_cf, hurdle_rate=0.10)

    def test_raises_on_ceded_basis_input(self):
        """ProfitTester must raise ValueError if given a CEDED basis CashFlowResult."""
        ceded_cf = CashFlowResult(
            run_id="test",
            valuation_date=date(2025, 1, 1),
            basis="CEDED",
            assumption_set_version="v1",
            product_type="TERM",
        )
        with pytest.raises(ValueError, match="NET"):
            ProfitTester(cashflows=ceded_cf, hurdle_rate=0.10)


class TestProfitTesterIRR:
    """IRR calculation tests."""

    def test_irr_equals_hurdle_when_pv_profits_zero(self):
        """
        CLOSED-FORM: Construct a cash flow vector where PV discounted at 10% = 0.
        The IRR returned must equal 10% (to within 1e-4).

        Construction: initial outflow of -100, then 60 monthly inflows,
        sized so that PV at 10% annual = 0.
        """
        target_rate = 0.10
        t = 60
        v = (1.0 + target_rate) ** (-1.0 / 12.0)

        discount_factors = v ** np.arange(1, t + 1, dtype=np.float64)

        # Set first payment as -100, remaining as level payment such that PV = 0
        # PV = -100*v + level * sum(v^2 to v^60) = 0
        # level = 100*v / sum(v^2..v^60)
        profits = np.zeros(t, dtype=np.float64)
        profits[0] = -100.0
        remaining_pv = discount_factors[1:].sum()
        level_payment = 100.0 * v / remaining_pv
        profits[1:] = level_payment

        # Verify our construction: PV at target_rate should be ~0
        constructed_pv = np.dot(profits, discount_factors)
        np.testing.assert_allclose(constructed_pv, 0.0, atol=1e-6)

        cf = _make_net_cashflow(profits)
        tester = ProfitTester(cf, hurdle_rate=target_rate)
        result = tester.run()

        assert result.irr is not None
        np.testing.assert_allclose(result.irr, target_rate, atol=1e-4)

    def test_irr_none_when_all_positive(self):
        """If all profits positive, no sign change so IRR may not converge."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        tester = ProfitTester(cf, hurdle_rate=0.10)
        result = tester.run()
        # All positive -> no sign change, IRR should be None
        assert result.irr is None

    def test_irr_none_when_all_negative(self):
        """If all profits negative, no sign change so IRR is None."""
        profits = np.ones(60, dtype=np.float64) * -50.0
        cf = _make_net_cashflow(profits)
        tester = ProfitTester(cf, hurdle_rate=0.10)
        result = tester.run()
        assert result.irr is None


class TestProfitTesterPV:
    """Present value calculation tests."""

    def test_positive_pv_profits(self):
        """If all profits positive, PV profits > 0."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        tester = ProfitTester(cf, hurdle_rate=0.10)
        result = tester.run()
        assert result.pv_profits > 0

    def test_pv_decreases_with_higher_hurdle(self):
        """PV profits should decrease when hurdle rate increases."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        result_low = ProfitTester(cf, hurdle_rate=0.05).run()
        result_high = ProfitTester(cf, hurdle_rate=0.15).run()
        assert result_low.pv_profits > result_high.pv_profits

    def test_pv_premiums_positive(self):
        """PV premiums should be positive for positive premium stream."""
        profits = np.ones(60, dtype=np.float64) * 50.0
        premiums = np.ones(60, dtype=np.float64) * 1000.0
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.pv_premiums > 0


class TestProfitTesterMargin:
    """Profit margin tests."""

    def test_profit_margin_bounds(self):
        """Profit margin should be reasonable for typical inputs."""
        profits = np.ones(60, dtype=np.float64) * 50.0
        premiums = np.ones(60, dtype=np.float64) * 1000.0
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert -1.0 <= result.profit_margin <= 1.0

    def test_profit_margin_positive_for_profitable_deal(self):
        """Positive profits should yield positive margin."""
        profits = np.ones(60, dtype=np.float64) * 50.0
        premiums = np.ones(60, dtype=np.float64) * 1000.0
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.profit_margin > 0


class TestProfitTesterBreakeven:
    """Break-even year tests."""

    def test_breakeven_year_one_for_immediate_profit(self):
        """Immediate positive profits should break even in year 1."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.breakeven_year == 1

    def test_breakeven_none_when_never_positive(self):
        """All negative profits should never break even."""
        profits = np.ones(60, dtype=np.float64) * -50.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.breakeven_year is None

    def test_breakeven_after_initial_loss(self):
        """Initial loss followed by profits should break even after year 1."""
        profits = np.zeros(60, dtype=np.float64)
        profits[:12] = -200.0  # loss in year 1
        profits[12:] = 100.0  # profit from year 2
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.breakeven_year is not None
        assert result.breakeven_year >= 2


class TestProfitTesterAnnualSummary:
    """Annual profit summary tests."""

    def test_profit_by_year_shape(self):
        """profit_by_year should have one entry per year."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert len(result.profit_by_year) == 5  # 60 months = 5 years

    def test_profit_by_year_sums_correctly(self):
        """Annual profits should sum to total undiscounted profit."""
        profits = np.ones(60, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        np.testing.assert_allclose(
            result.profit_by_year.sum(),
            result.total_undiscounted_profit,
            rtol=1e-10,
        )

    def test_profit_by_year_partial_year(self):
        """Non-multiple-of-12 months should include partial year."""
        profits = np.ones(50, dtype=np.float64) * 100.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        # 50 months = 4 full years + 2 months
        assert len(result.profit_by_year) == 5


class TestProfitTesterIntegration:
    """Integration test with TermLife -> Treaty -> ProfitTester."""

    def test_full_pipeline(self):
        """End-to-end: TermLife -> CoinsuranceTreaty -> ProfitTester."""
        policy = Policy(
            policy_id="PROFIT001",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=12_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        table_array = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        mortality = MortalityTable.from_table_array(
            source=MortalityTableSource.SOA_VBT_2015,
            table_name="Synthetic Test",
            table_array=table_array,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
        )
        lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
        assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="test-v1")
        config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=5,
            discount_rate=0.05,
        )

        engine = TermLife(block, assumptions, config)
        gross = engine.project()

        treaty = CoinsuranceTreaty(cession_pct=0.5)
        net, _ceded = treaty.apply(gross)

        tester = ProfitTester(net, hurdle_rate=0.10)
        result = tester.run()

        assert isinstance(result, ProfitTestResult)
        assert result.pv_premiums > 0
        assert len(result.profit_by_year) == 5
        assert result.total_undiscounted_profit != 0.0
