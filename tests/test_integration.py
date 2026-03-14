"""
Full integration test: InforceBlock -> AssumptionSet -> TermLife -> Treaty -> ProfitTester.

Exercises the complete Phase 1 pipeline end-to-end:
1. Build an InforceBlock with multiple policies
2. Load assumptions (mortality + lapse)
3. Run TermLife projection -> gross CashFlowResult
4. Apply YRT and Coinsurance treaties -> (net, ceded)
5. Run ProfitTester on net cash flows
6. Run ScenarioRunner with standard stress scenarios
7. Verify all invariants hold across the full pipeline
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.analytics.scenario import ScenarioRunner
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def multi_policy_block() -> InforceBlock:
    """A block of 3 term life policies with varying characteristics."""
    policies = [
        Policy(
            policy_id="INT001",
            issue_age=35,
            attained_age=35,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=5_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        ),
        Policy(
            policy_id="INT002",
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
        ),
        Policy(
            policy_id="INT003",
            issue_age=45,
            attained_age=45,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=750_000.0,
            annual_premium=9_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        ),
    ]
    return InforceBlock(policies=policies)


@pytest.fixture()
def assumptions() -> AssumptionSet:
    """Full assumption set for integration testing."""
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
    lapse = LapseAssumption.from_duration_table(
        {1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03}
    )
    return AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version="integration-test-v1",
    )


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )


@pytest.fixture()
def gross_result(multi_policy_block, assumptions, config):
    """Gross CashFlowResult from TermLife projection."""
    engine = TermLife(multi_policy_block, assumptions, config)
    return engine.project()


class TestFullPipelineYRT:
    """End-to-end test with YRT treaty."""

    def test_yrt_pipeline(self, gross_result):
        """Full pipeline: Gross -> YRT -> ProfitTester."""
        total_face = 500_000.0 + 1_000_000.0 + 750_000.0
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=total_face,
            flat_yrt_rate_per_1000=2.5,
        )
        net, ceded = treaty.apply(gross_result)

        # Additivity
        treaty.verify_additivity(gross_result, net, ceded)

        # Basis labels
        assert gross_result.basis == "GROSS"
        assert net.basis == "NET"
        assert ceded.basis == "CEDED"

        # Profit test
        tester = ProfitTester(net, hurdle_rate=0.10)
        result = tester.run()
        assert isinstance(result, ProfitTestResult)
        assert result.pv_premiums > 0
        assert len(result.profit_by_year) == 5

    def test_yrt_reserves_not_transferred(self, gross_result):
        """YRT: reserves stay with cedant."""
        total_face = 500_000.0 + 1_000_000.0 + 750_000.0
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=total_face,
            flat_yrt_rate_per_1000=2.5,
        )
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(
            net.reserve_balance, gross_result.reserve_balance, rtol=1e-10
        )
        np.testing.assert_allclose(ceded.reserve_balance, 0.0, atol=1e-10)


class TestFullPipelineCoinsurance:
    """End-to-end test with Coinsurance treaty."""

    def test_coinsurance_pipeline(self, gross_result):
        """Full pipeline: Gross -> Coinsurance -> ProfitTester."""
        treaty = CoinsuranceTreaty(cession_pct=0.5)
        net, ceded = treaty.apply(gross_result)

        # Additivity
        treaty.verify_additivity(gross_result, net, ceded)

        # Reserve transfer
        np.testing.assert_allclose(
            ceded.reserve_balance,
            gross_result.reserve_balance * 0.5,
            rtol=1e-10,
        )

        # Profit test
        tester = ProfitTester(net, hurdle_rate=0.10)
        result = tester.run()
        assert isinstance(result, ProfitTestResult)
        assert result.pv_premiums > 0


class TestFullPipelineScenario:
    """End-to-end test with ScenarioRunner."""

    def test_scenario_runner_full_pipeline(
        self, multi_policy_block, assumptions, config
    ):
        """Full pipeline: ScenarioRunner with standard stress scenarios."""
        treaty = CoinsuranceTreaty(cession_pct=0.5)
        runner = ScenarioRunner(
            multi_policy_block, assumptions, config, treaty, hurdle_rate=0.10
        )
        result = runner.run()

        # All 6 scenarios should produce results
        assert len(result.scenarios) == 6

        # BASE should exist
        base = result.base_case()
        assert base is not None
        assert base.pv_premiums > 0

        # IRR range should be valid
        irr_min, irr_max = result.irr_range()
        if irr_min is not None and irr_max is not None:
            assert irr_min <= irr_max

        # Worst case: may be None if all scenarios have same-sign profits
        worst = result.worst_case()
        if worst is not None:
            assert worst[1].pv_profits <= base.pv_profits


class TestAccountingIdentity:
    """Verify accounting identities hold across the full pipeline."""

    def test_gross_accounting_identity(self, gross_result):
        """Gross: net_cf = premiums - claims - lapses - expenses - reserve_inc."""
        expected = (
            gross_result.gross_premiums
            - gross_result.death_claims
            - gross_result.lapse_surrenders
            - gross_result.expenses
            - gross_result.reserve_increase
        )
        np.testing.assert_allclose(
            gross_result.net_cash_flow, expected, rtol=1e-10
        )

    def test_net_accounting_identity_yrt(self, gross_result):
        """Net (YRT): accounting identity holds."""
        total_face = 500_000.0 + 1_000_000.0 + 750_000.0
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=total_face,
            flat_yrt_rate_per_1000=2.5,
        )
        net, _ceded = treaty.apply(gross_result)
        expected = (
            net.gross_premiums
            - net.death_claims
            - net.lapse_surrenders
            - net.expenses
            - net.reserve_increase
        )
        np.testing.assert_allclose(net.net_cash_flow, expected, rtol=1e-10)

    def test_net_accounting_identity_coinsurance(self, gross_result):
        """Net (Coinsurance): accounting identity holds."""
        treaty = CoinsuranceTreaty(cession_pct=0.5)
        net, _ceded = treaty.apply(gross_result)
        expected = (
            net.gross_premiums
            - net.death_claims
            - net.lapse_surrenders
            - net.expenses
            - net.reserve_increase
        )
        np.testing.assert_allclose(net.net_cash_flow, expected, rtol=1e-10)


class TestMultiPolicyConsistency:
    """Verify multi-policy projections are consistent."""

    def test_seriatim_sums_to_aggregate(
        self, multi_policy_block, assumptions, config
    ):
        """Seriatim premiums summed should match aggregate premiums."""
        engine = TermLife(multi_policy_block, assumptions, config)
        result = engine.project(seriatim=True)
        assert result.seriatim_premiums is not None
        np.testing.assert_allclose(
            result.seriatim_premiums.sum(axis=0),
            result.gross_premiums,
            rtol=1e-10,
        )

    def test_first_month_premium_sum(
        self, multi_policy_block, assumptions, config
    ):
        """
        CLOSED-FORM: First month premium = sum of monthly premiums.
        (5000 + 12000 + 9000) / 12 = 2166.67
        """
        engine = TermLife(multi_policy_block, assumptions, config)
        result = engine.project()
        expected = (5_000.0 + 12_000.0 + 9_000.0) / 12.0
        np.testing.assert_allclose(result.gross_premiums[0], expected, rtol=1e-10)

    def test_three_policies_shape(
        self, multi_policy_block, assumptions, config
    ):
        """Seriatim arrays should have shape (3, 60)."""
        engine = TermLife(multi_policy_block, assumptions, config)
        result = engine.project(seriatim=True)
        assert result.seriatim_premiums is not None
        assert result.seriatim_premiums.shape == (3, 60)
