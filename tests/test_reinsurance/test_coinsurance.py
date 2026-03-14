"""
Coinsurance treaty tests.

KEY INVARIANTS:
1. net + ceded == gross for all cash flow lines (premiums, claims, expenses, reserves)
2. Reserve transfer: ceded_reserve == gross_reserve * cession_pct at every time step
3. Net reserve == gross_reserve * (1 - cession_pct) at every time step
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

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
def gross_result():
    """Produce a gross CashFlowResult from a single-policy TermLife projection."""
    policy = Policy(
        policy_id="COINS001",
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
    return engine.project()


@pytest.fixture()
def coins_treaty():
    """Standard 50% coinsurance treaty."""
    return CoinsuranceTreaty(cession_pct=0.5)


@pytest.fixture()
def coins_result(coins_treaty, gross_result):
    """Apply coinsurance treaty and return (net, ceded) tuple."""
    return coins_treaty.apply(gross_result)


class TestCoinsuranceAdditivity:
    """Verify net + ceded == gross for all cash flow lines."""

    def test_additivity_premiums(self, gross_result, coins_result):
        """net premiums + ceded premiums must equal gross premiums."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross_result.gross_premiums,
            rtol=1e-10,
        )

    def test_additivity_claims(self, gross_result, coins_result):
        """net claims + ceded claims must equal gross claims."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.death_claims + ceded.death_claims,
            gross_result.death_claims,
            rtol=1e-10,
        )

    def test_additivity_reserves(self, gross_result, coins_result):
        """net reserves + ceded reserves must equal gross reserves."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.reserve_balance + ceded.reserve_balance,
            gross_result.reserve_balance,
            rtol=1e-10,
        )

    def test_additivity_reserve_increase(self, gross_result, coins_result):
        """net reserve increase + ceded reserve increase must equal gross."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.reserve_increase + ceded.reserve_increase,
            gross_result.reserve_increase,
            rtol=1e-10,
        )

    def test_additivity_expenses(self, gross_result, coins_result):
        """net expenses + ceded expenses must equal gross expenses."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.expenses + ceded.expenses,
            gross_result.expenses,
            rtol=1e-10,
        )

    def test_additivity_net_cash_flow(self, gross_result, coins_result):
        """net NCF + ceded NCF must equal gross NCF."""
        net, ceded = coins_result
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross_result.net_cash_flow,
            rtol=1e-10,
        )

    def test_verify_additivity_method(self, coins_treaty, gross_result, coins_result):
        """BaseTreaty.verify_additivity() should pass without error."""
        net, ceded = coins_result
        coins_treaty.verify_additivity(gross_result, net, ceded)


class TestCoinsuranceReserves:
    """Reserves are transferred proportionally in coinsurance."""

    def test_ceded_reserves_proportional(self, gross_result, coins_result):
        """
        CLOSED-FORM: ceded_reserve = gross_reserve * 0.5 at every time step.
        """
        _, ceded = coins_result
        np.testing.assert_allclose(
            ceded.reserve_balance,
            gross_result.reserve_balance * 0.5,
            rtol=1e-10,
        )

    def test_net_reserves_proportional(self, gross_result, coins_result):
        """
        CLOSED-FORM: net_reserve = gross_reserve * 0.5 at every time step.
        """
        net, _ = coins_result
        np.testing.assert_allclose(
            net.reserve_balance,
            gross_result.reserve_balance * 0.5,
            rtol=1e-10,
        )

    def test_ceded_reserve_increase_proportional(self, gross_result, coins_result):
        """Ceded reserve increase = gross reserve increase * cession_pct."""
        _, ceded = coins_result
        np.testing.assert_allclose(
            ceded.reserve_increase,
            gross_result.reserve_increase * 0.5,
            rtol=1e-10,
        )


class TestCoinsuranceClaims:
    """Claims are split proportionally."""

    def test_ceded_claims_proportional(self, gross_result, coins_result):
        """Ceded claims = gross claims * cession_pct."""
        _, ceded = coins_result
        np.testing.assert_allclose(
            ceded.death_claims,
            gross_result.death_claims * 0.5,
            rtol=1e-10,
        )

    def test_net_claims_proportional(self, gross_result, coins_result):
        """Net claims = gross claims * (1 - cession_pct)."""
        net, _ = coins_result
        np.testing.assert_allclose(
            net.death_claims,
            gross_result.death_claims * 0.5,
            rtol=1e-10,
        )


class TestCoinsuranceBasis:
    """Verify basis labels and metadata."""

    def test_net_basis(self, coins_result):
        """Net result should have basis='NET'."""
        net, _ = coins_result
        assert net.basis == "NET"

    def test_ceded_basis(self, coins_result):
        """Ceded result should have basis='CEDED'."""
        _, ceded = coins_result
        assert ceded.basis == "CEDED"

    def test_projection_months_match(self, gross_result, coins_result):
        """Net and ceded should have same projection_months as gross."""
        net, ceded = coins_result
        assert net.projection_months == gross_result.projection_months
        assert ceded.projection_months == gross_result.projection_months


class TestCoinsuranceEdgeCases:
    """Edge cases for coinsurance treaty."""

    def test_zero_cession_net_equals_gross(self, gross_result):
        """With cession_pct=0, net == gross and ceded == 0."""
        treaty = CoinsuranceTreaty(cession_pct=0.0)
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(net.gross_premiums, gross_result.gross_premiums, rtol=1e-10)
        np.testing.assert_allclose(net.death_claims, gross_result.death_claims, rtol=1e-10)
        np.testing.assert_allclose(net.reserve_balance, gross_result.reserve_balance, rtol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(ceded.death_claims, 0.0, atol=1e-10)
        np.testing.assert_allclose(ceded.reserve_balance, 0.0, atol=1e-10)

    def test_full_cession_ceded_equals_gross(self, gross_result):
        """With cession_pct=1.0, ceded == gross and net == 0."""
        treaty = CoinsuranceTreaty(cession_pct=1.0)
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(ceded.gross_premiums, gross_result.gross_premiums, rtol=1e-10)
        np.testing.assert_allclose(ceded.death_claims, gross_result.death_claims, rtol=1e-10)
        np.testing.assert_allclose(ceded.reserve_balance, gross_result.reserve_balance, rtol=1e-10)
        np.testing.assert_allclose(net.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(net.death_claims, 0.0, atol=1e-10)
        np.testing.assert_allclose(net.reserve_balance, 0.0, atol=1e-10)

    def test_no_expense_allowance(self, gross_result):
        """Without expense allowance, expenses stay fully with cedant."""
        treaty = CoinsuranceTreaty(cession_pct=0.5, include_expense_allowance=False)
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(net.expenses, gross_result.expenses, rtol=1e-10)
        np.testing.assert_allclose(ceded.expenses, 0.0, atol=1e-10)

    def test_net_cash_flow_accounting_identity(self, coins_result):
        """net_cash_flow = premiums - claims - lapses - expenses - reserve_increase."""
        net, ceded = coins_result
        for result in [net, ceded]:
            expected = (
                result.gross_premiums
                - result.death_claims
                - result.lapse_surrenders
                - result.expenses
                - result.reserve_increase
            )
            np.testing.assert_allclose(result.net_cash_flow, expected, rtol=1e-10)
