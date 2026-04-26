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

from polaris_re.analytics.capital import LICATCapital, LICATFactors
from polaris_re.analytics.profit_test import (
    ProfitResultWithCapital,
    ProfitTester,
    ProfitTestResult,
)
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
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

    def test_accepts_gross_basis_input(self):
        """ProfitTester should accept GROSS basis for standalone (no-treaty) pricing."""
        gross_cf = CashFlowResult(
            run_id="test",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="v1",
            product_type="TERM",
        )
        # Must not raise — GROSS is valid for standalone profit testing
        tester = ProfitTester(cashflows=gross_cf, hurdle_rate=0.10)
        assert tester.cashflows.basis == "GROSS"

    def test_raises_on_ceded_basis_input(self):
        """ProfitTester must raise ValueError if given a CEDED basis CashFlowResult."""
        ceded_cf = CashFlowResult(
            run_id="test",
            valuation_date=date(2025, 1, 1),
            basis="CEDED",
            assumption_set_version="v1",
            product_type="TERM",
        )
        with pytest.raises(ValueError, match="CEDED"):
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
        assert result.profit_margin is not None
        assert -1.0 <= result.profit_margin <= 1.0

    def test_profit_margin_positive_for_profitable_deal(self):
        """Positive profits should yield positive margin."""
        profits = np.ones(60, dtype=np.float64) * 50.0
        premiums = np.ones(60, dtype=np.float64) * 1000.0
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()
        assert result.profit_margin is not None
        assert result.profit_margin > 0


class TestProfitTesterReportingGuardrails:
    """Reporting guardrails that suppress misleading IRR and profit_margin values.

    Rationale (see ADR-041):
    - IRRs with |value| > 50% on loss-making deals are numerically valid roots
      of degenerate sign changes but economically meaningless. A pricing actuary
      would never cite "899% IRR on a $14M loss".
    - profit_margin = pv_profits / pv_premiums flips sign when pv_premiums is
      negative (possible on NET cash flows where ceded premiums exceed gross),
      producing "1.5%" margins on large losses.
    """

    def test_irr_suppressed_when_large_magnitude_and_net_loss(self):
        """
        Closed-form: a stream with a small positive in month 0 and losses
        thereafter yields a huge spurious IRR. With total_undiscounted_profit
        < 0 and |irr| > 0.5, irr must be None.
        """
        t = 60
        profits = np.full(t, -100.0, dtype=np.float64)
        profits[0] = 50.0  # tiny early positive → brentq finds a huge root
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        assert result.total_undiscounted_profit < 0
        assert result.irr is None, (
            f"Expected IRR suppressed for loss-making deal with large magnitude "
            f"IRR root, but got irr={result.irr}"
        )

    def test_irr_preserved_when_magnitude_small_even_if_loss(self):
        """
        A loss-making deal with a modest IRR (|irr| <= 0.5) is economically
        interpretable (e.g. a low negative IRR on a mildly unprofitable deal).
        Keep it.
        """
        # Initial outflow of -100, then 59 monthly inflows of +1.60.
        # Undiscounted total = -100 + 59*1.60 = -5.6 < 0.
        # The cash flow yields a modest negative IRR (sign change exists).
        t = 60
        profits = np.zeros(t, dtype=np.float64)
        profits[0] = -100.0
        profits[1:] = 1.60
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        assert result.total_undiscounted_profit < 0
        assert result.irr is not None
        assert abs(result.irr) <= 0.5

    def test_irr_preserved_when_large_magnitude_but_profitable(self):
        """
        A deal with large IRR but NET profitable (total undisc > 0) is a
        legitimate high-return structure — do not suppress.
        """
        # Initial outflow -10, then +2.0 for 59 months. Total = -10 + 118 = 108 > 0.
        # IRR is very large (small strain, large cumulative profit).
        t = 60
        profits = np.full(t, 2.0, dtype=np.float64)
        profits[0] = -10.0
        cf = _make_net_cashflow(profits)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        assert result.total_undiscounted_profit > 0
        # IRR is very large here but should remain because the deal is profitable
        assert result.irr is not None
        assert result.irr > 0.5

    def test_profit_margin_suppressed_when_pv_premiums_negative(self):
        """
        When a NET premium stream has pv_premiums <= 0 (e.g. ceded YRT premiums
        exceed gross premiums in a high-cession deal), profit_margin is the
        ratio of two negative-ish numbers and flips sign misleadingly. Suppress.
        """
        t = 60
        profits = np.full(t, -20.0, dtype=np.float64)
        premiums = np.full(t, -10.0, dtype=np.float64)  # net premiums negative
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        assert result.pv_premiums < 0
        assert result.profit_margin is None

    def test_profit_margin_suppressed_when_pv_premiums_zero(self):
        """Zero pv_premiums => undefined margin => None."""
        t = 60
        profits = np.full(t, -5.0, dtype=np.float64)
        premiums = np.zeros(t, dtype=np.float64)
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        np.testing.assert_allclose(result.pv_premiums, 0.0, atol=1e-10)
        assert result.profit_margin is None

    def test_profit_margin_preserved_when_pv_premiums_positive(self):
        """Positive pv_premiums → margin is meaningful, even if profits are negative."""
        t = 60
        profits = np.full(t, -5.0, dtype=np.float64)
        premiums = np.full(t, 100.0, dtype=np.float64)
        cf = _make_net_cashflow(profits, premiums)
        result = ProfitTester(cf, hurdle_rate=0.10).run()

        assert result.pv_premiums > 0
        assert result.profit_margin is not None
        assert result.profit_margin < 0  # loss-making but well-defined


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


# ----------------------------------------------------------------------
# ProfitTester.run_with_capital — Slice 2 of LICAT capital feature (ADR-048)
# ----------------------------------------------------------------------


def _make_cashflow_with_nar(
    profits: np.ndarray,
    nar: np.ndarray,
    premiums: np.ndarray | None = None,
) -> CashFlowResult:
    """Helper for capital tests — NET cashflow with explicit NAR populated."""
    t = len(profits)
    if premiums is None:
        premiums = np.full(t, 100.0, dtype=np.float64)
    return CashFlowResult(
        run_id="test-capital",
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
        nar=nar,
    )


class TestProfitTesterWithCapital:
    """Slice 2 — ProfitTester.run_with_capital + RoC."""

    def test_returns_profit_result_with_capital(self) -> None:
        t = 12
        profits = np.full(t, 50.0, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital.for_product(ProductType.TERM)

        result = ProfitTester(cf, hurdle_rate=0.10).run_with_capital(cap)

        assert isinstance(result, ProfitResultWithCapital)
        assert isinstance(result, ProfitTestResult)
        assert result.peak_capital > 0.0
        assert result.pv_capital > 0.0
        assert result.return_on_capital is not None

    def test_base_profit_fields_preserved(self) -> None:
        """run_with_capital preserves every ProfitTestResult field unchanged."""
        t = 24
        profits = np.full(t, 50.0, dtype=np.float64)
        profits[0] = -200.0  # add a sign change so IRR exists
        premiums = np.full(t, 1_000.0, dtype=np.float64)
        nar = np.full(t, 500_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar, premiums)
        cap = LICATCapital.for_product(ProductType.TERM)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        base = tester.run()
        joint = tester.run_with_capital(cap)

        assert joint.hurdle_rate == base.hurdle_rate
        assert joint.pv_profits == pytest.approx(base.pv_profits)
        assert joint.pv_premiums == pytest.approx(base.pv_premiums)
        assert joint.profit_margin == base.profit_margin
        assert joint.irr == base.irr
        assert joint.breakeven_year == base.breakeven_year
        assert joint.total_undiscounted_profit == pytest.approx(base.total_undiscounted_profit)
        np.testing.assert_array_equal(joint.profit_by_year, base.profit_by_year)

    def test_roc_closed_form_pv_profits_over_pv_capital(self) -> None:
        """
        CLOSED-FORM: For a flat profit + flat capital schedule, RoC equals
        pv_profits / pv_capital (stock denominator at the hurdle rate).
        """
        t = 36
        profits = np.full(t, 100.0, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap)
        capital_schedule = cap.required_capital(cf)

        expected_pv_capital = capital_schedule.pv_capital(0.10)
        expected_roc = result.pv_profits / expected_pv_capital

        assert result.pv_capital == pytest.approx(expected_pv_capital)
        assert result.return_on_capital == pytest.approx(expected_roc)

    def test_doubling_capital_factor_halves_roc(self) -> None:
        """Sensitivity: 2x C-2 factor -> 2x pv_capital -> RoC halved."""
        t = 24
        profits = np.full(t, 100.0, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        cap_low = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.05))
        cap_high = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))

        r_low = tester.run_with_capital(cap_low)
        r_high = tester.run_with_capital(cap_high)

        assert r_low.return_on_capital is not None
        assert r_high.return_on_capital is not None
        # Doubling capital factor halves RoC (within float tolerance)
        assert r_high.return_on_capital == pytest.approx(r_low.return_on_capital / 2.0)

    def test_explicit_nar_plumbed_through_to_calculator(self) -> None:
        """
        Slice 2 acceptance: nar= override forwards to LICATCapital and
        produces the expected closed-form C-2 component.
        """
        t = 12
        profits = np.full(t, 0.0, dtype=np.float64)
        # CashFlowResult has TINY nar; explicit override should win
        cf = _make_cashflow_with_nar(profits, np.full(t, 1.0, dtype=np.float64))
        explicit_nar = np.full(t, 2_000_000.0, dtype=np.float64)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap, nar=explicit_nar)

        # Peak capital should reflect explicit NAR, not the cashflow stub
        expected_peak = 0.10 * 2_000_000.0
        assert result.peak_capital == pytest.approx(expected_peak)
        # Initial = same in this constant-NAR case
        assert result.initial_capital == pytest.approx(expected_peak)

    def test_no_nar_raises(self) -> None:
        """If neither cashflows.nar nor nar= override is supplied, raise."""
        t = 12
        profits = np.full(t, 50.0, dtype=np.float64)
        # Build a cashflow without nar
        cf = CashFlowResult(
            run_id="test-no-nar",
            valuation_date=date(2025, 1, 1),
            basis="NET",
            assumption_set_version="v1",
            product_type="TERM",
            projection_months=t,
            time_index=np.arange(
                np.datetime64("2025-01"), np.datetime64("2025-01") + t, dtype="datetime64[M]"
            ),
            gross_premiums=np.full(t, 100.0, dtype=np.float64),
            death_claims=np.zeros(t, dtype=np.float64),
            lapse_surrenders=np.zeros(t, dtype=np.float64),
            expenses=np.zeros(t, dtype=np.float64),
            reserve_balance=np.zeros(t, dtype=np.float64),
            reserve_increase=np.zeros(t, dtype=np.float64),
            net_cash_flow=profits,
        )
        cap = LICATCapital.for_product(ProductType.TERM)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        with pytest.raises(PolarisComputationError, match="NAR"):
            tester.run_with_capital(cap)

    def test_zero_capital_factor_yields_none_roc(self) -> None:
        """A zero-factor capital model produces pv_capital = 0 -> RoC None."""
        t = 12
        profits = np.full(t, 50.0, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.0))
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap)

        assert result.pv_capital == 0.0
        assert result.return_on_capital is None

    def test_capital_by_period_shape_and_values(self) -> None:
        """capital_by_period mirrors the LICATCapital schedule shape and values."""
        t = 18
        profits = np.full(t, 25.0, dtype=np.float64)
        nar = np.linspace(1_000_000.0, 500_000.0, t, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital.for_product(ProductType.TERM)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap)

        assert result.capital_by_period.shape == (t,)
        np.testing.assert_allclose(result.capital_by_period, 0.15 * nar)

    def test_pv_capital_strain_for_flat_capital(self) -> None:
        """
        For a constant capital schedule, strain is K at t=0 and zero after,
        so pv_capital_strain = K * v.
        """
        t = 12
        profits = np.zeros(t, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap)

        v = (1.0 + 0.10) ** (-1.0 / 12.0)
        expected = 0.10 * 1_000_000.0 * v
        assert result.pv_capital_strain == pytest.approx(expected)

    def test_capital_adjusted_irr_falls_below_vanilla_when_capital_strained(self) -> None:
        """
        Sensitivity: a profitable deal with significant capital lock-up
        produces a capital-adjusted IRR strictly below the vanilla IRR.
        Capital is a frictional cost on the shareholder; shareholder IRR
        must be no higher than the gross IRR.
        """
        t = 60
        # Initial strain followed by steady positive profits to give a
        # well-defined IRR with a sign change.
        profits = np.full(t, 100.0, dtype=np.float64)
        profits[0] = -500.0
        nar = np.full(t, 2_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital.for_product(ProductType.TERM)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        result = tester.run_with_capital(cap)

        assert result.irr is not None
        assert result.capital_adjusted_irr is not None
        # Adjusting for capital injects a negative period 0 strain and a
        # terminal release; the net effect lowers the shareholder IRR.
        assert result.capital_adjusted_irr < result.irr

    def test_run_unaffected_by_run_with_capital(self) -> None:
        """Backward compat: existing run() callers see no change."""
        t = 12
        profits = np.full(t, 50.0, dtype=np.float64)
        nar = np.full(t, 1_000_000.0, dtype=np.float64)
        cf = _make_cashflow_with_nar(profits, nar)
        cap = LICATCapital.for_product(ProductType.TERM)
        tester = ProfitTester(cf, hurdle_rate=0.10)

        before = tester.run()
        _ = tester.run_with_capital(cap)
        after = tester.run()

        assert before.pv_profits == after.pv_profits
        assert before.irr == after.irr
        assert before.profit_margin == after.profit_margin

    def test_module_exports_profit_result_with_capital(self) -> None:
        """ProfitResultWithCapital is exposed via polaris_re.analytics."""
        from polaris_re.analytics import ProfitResultWithCapital as Exported

        assert Exported is ProfitResultWithCapital


# ----------------------------------------------------------------------
# CapitalResult.pv_capital_strain — closed-form (Slice 2 method)
# ----------------------------------------------------------------------


class TestPvCapitalStrainClosedForm:
    def test_strain_zero_rate_equals_telescoped_capital(self) -> None:
        """At rate=0, sum of strain equals capital[T-1] (telescope)."""
        from polaris_re.analytics.capital import CapitalResult

        capital = np.array([100.0, 150.0, 120.0, 90.0], dtype=np.float64)
        result = CapitalResult(
            projection_months=4,
            c1_component=np.zeros(4, dtype=np.float64),
            c2_component=capital.copy(),
            c3_component=np.zeros(4, dtype=np.float64),
            capital_by_period=capital.copy(),
            initial_capital=100.0,
            peak_capital=150.0,
        )

        # At rate=0 the sum of strain components = capital[-1] (telescope)
        pv_strain_zero = result.pv_capital_strain(discount_rate=0.0)
        assert pv_strain_zero == pytest.approx(float(capital[-1]))

    def test_strain_for_constant_capital_equals_initial_times_v(self) -> None:
        from polaris_re.analytics.capital import CapitalResult

        n = 24
        capital = np.full(n, 250_000.0, dtype=np.float64)
        result = CapitalResult(
            projection_months=n,
            c1_component=np.zeros(n, dtype=np.float64),
            c2_component=capital.copy(),
            c3_component=np.zeros(n, dtype=np.float64),
            capital_by_period=capital.copy(),
            initial_capital=250_000.0,
            peak_capital=250_000.0,
        )

        rate = 0.08
        v = (1.0 + rate) ** (-1.0 / 12.0)
        expected = 250_000.0 * v  # only initial injection has weight
        assert result.pv_capital_strain(rate) == pytest.approx(expected)
