"""
ScenarioRunner tests.

Key tests:
  1. BASE scenario matches direct ProfitTester run
  2. Standard stress scenarios all produce valid results
  3. Adverse mortality -> lower IRR; favorable mortality -> higher IRR
  4. ScenarioResult helper methods work correctly
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.analytics.scenario import (
    ScenarioAdjustment,
    ScenarioResult,
    ScenarioRunner,
)
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def test_setup():
    """Build all components needed for scenario testing."""
    policy = Policy(
        policy_id="SCEN001",
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
    treaty = CoinsuranceTreaty(cession_pct=0.5)
    return block, assumptions, config, treaty


class TestScenarioRunnerBasic:
    """Basic functionality tests."""

    def test_standard_scenarios_count(self):
        """Standard stress scenarios should have 6 entries."""
        scenarios = ScenarioRunner.standard_stress_scenarios()
        assert len(scenarios) == 6

    def test_standard_scenarios_include_base(self):
        """Standard scenarios must include a BASE scenario."""
        scenarios = ScenarioRunner.standard_stress_scenarios()
        names = [s.name for s in scenarios]
        assert "BASE" in names

    def test_run_returns_scenario_result(self, test_setup):
        """run() should return a ScenarioResult."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        assert isinstance(result, ScenarioResult)
        assert len(result.scenarios) == 1

    def test_run_all_standard_scenarios(self, test_setup):
        """All 6 standard scenarios should produce results."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run()
        assert len(result.scenarios) == 6


class TestScenarioRunnerConsistency:
    """Verify scenario results are consistent with direct ProfitTester."""

    def test_base_matches_direct_profit_test(self, test_setup):
        """BASE scenario should match a direct ProfitTester run."""
        block, assumptions, config, treaty = test_setup

        # Direct run
        engine = TermLife(block, assumptions, config)
        gross = engine.project()
        net, _ceded = treaty.apply(gross)
        direct_result = ProfitTester(net, hurdle_rate=0.10).run()

        # Scenario runner BASE
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        scenario_result = runner.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        base_result = scenario_result.scenarios[0][1]

        np.testing.assert_allclose(base_result.pv_profits, direct_result.pv_profits, rtol=1e-10)
        np.testing.assert_allclose(base_result.pv_premiums, direct_result.pv_premiums, rtol=1e-10)


class TestScenarioRunnerSensitivity:
    """Sensitivity analysis: direction of impact tests."""

    def test_adverse_mortality_reduces_profit(self, test_setup):
        """Higher mortality (110%) should reduce PV profits vs base."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run(
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ]
        )
        base_pv = result.scenarios[0][1].pv_profits
        mort_110_pv = result.scenarios[1][1].pv_profits
        assert mort_110_pv < base_pv

    def test_favorable_mortality_increases_profit(self, test_setup):
        """Lower mortality (90%) should increase PV profits vs base."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run(
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_90", 0.90, 1.0),
            ]
        )
        base_pv = result.scenarios[0][1].pv_profits
        mort_90_pv = result.scenarios[1][1].pv_profits
        assert mort_90_pv > base_pv


class TestScenarioResultHelpers:
    """Tests for ScenarioResult helper methods."""

    def test_base_case_returns_result(self, test_setup):
        """base_case() should return the BASE scenario result."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run()
        base = result.base_case()
        assert base is not None
        assert base.pv_premiums > 0

    def test_irr_range(self, test_setup):
        """irr_range() should return (min, max) of valid IRRs."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run(
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ]
        )
        irr_min, irr_max = result.irr_range()
        if irr_min is not None and irr_max is not None:
            assert irr_min <= irr_max

    def test_worst_case(self, test_setup):
        """worst_case() should return the scenario with lowest IRR."""
        block, assumptions, config, treaty = test_setup
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner.run(
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ]
        )
        worst = result.worst_case()
        if worst is not None:
            # Worst case should be MORT_110 (adverse mortality)
            assert worst[0] == "MORT_110"

    def test_empty_scenario_result(self):
        """Empty ScenarioResult should return None for helpers."""
        result = ScenarioResult()
        assert result.base_case() is None
        assert result.worst_case() is None
        assert result.irr_range() == (None, None)
