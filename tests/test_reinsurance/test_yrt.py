"""
YRT treaty tests.

KEY INVARIANT TO VERIFY FOR ALL TESTS:
    net_cashflow + ceded_cashflow == gross_cashflow (for premiums and claims)

All monetary assertions use np.testing.assert_allclose(rtol=1e-5).
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
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def gross_result():
    """Produce a gross CashFlowResult from a single-policy TermLife projection."""
    policy = Policy(
        policy_id="YRT001",
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
    lapse = LapseAssumption.from_duration_table(
        {1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03}
    )
    assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="test-v1")
    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )
    engine = TermLife(block, assumptions, config)
    return engine.project()


@pytest.fixture()
def yrt_treaty():
    """Standard YRT treaty with 50% cession and flat rate."""
    return YRTTreaty(
        cession_pct=0.5,
        total_face_amount=1_000_000.0,
        flat_yrt_rate_per_1000=2.5,
    )


@pytest.fixture()
def yrt_result(yrt_treaty, gross_result):
    """Apply YRT treaty and return (net, ceded) tuple."""
    return yrt_treaty.apply(gross_result)


class TestYRTAdditivity:
    """Verify net + ceded == gross for all cash flow lines."""

    def test_additivity_premiums(self, gross_result, yrt_result):
        """net premiums + ceded premiums must equal gross premiums."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross_result.gross_premiums,
            rtol=1e-10,
        )

    def test_additivity_claims(self, gross_result, yrt_result):
        """net claims + ceded claims must equal gross claims."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.death_claims + ceded.death_claims,
            gross_result.death_claims,
            rtol=1e-10,
        )

    def test_additivity_reserves(self, gross_result, yrt_result):
        """net reserves + ceded reserves must equal gross reserves."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.reserve_balance + ceded.reserve_balance,
            gross_result.reserve_balance,
            rtol=1e-10,
        )

    def test_additivity_net_cash_flow(self, gross_result, yrt_result):
        """net NCF + ceded NCF must equal gross NCF."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross_result.net_cash_flow,
            rtol=1e-10,
        )

    def test_verify_additivity_method(self, yrt_treaty, gross_result, yrt_result):
        """BaseTreaty.verify_additivity() should pass without error."""
        net, ceded = yrt_result
        yrt_treaty.verify_additivity(gross_result, net, ceded)


class TestYRTReserves:
    """YRT reserves stay with cedant."""

    def test_reserves_not_transferred(self, gross_result, yrt_result):
        """Net reserves == gross reserves (no transfer in YRT)."""
        net, _ceded = yrt_result
        np.testing.assert_allclose(
            net.reserve_balance, gross_result.reserve_balance, rtol=1e-10
        )

    def test_ceded_reserves_zero(self, yrt_result):
        """Ceded reserves should be zero in YRT."""
        _, ceded = yrt_result
        np.testing.assert_allclose(ceded.reserve_balance, 0.0, atol=1e-10)

    def test_ceded_reserve_increase_zero(self, yrt_result):
        """Ceded reserve increase should be zero in YRT."""
        _, ceded = yrt_result
        np.testing.assert_allclose(ceded.reserve_increase, 0.0, atol=1e-10)


class TestYRTClaims:
    """Claims are split proportionally by cession_pct."""

    def test_ceded_claims_proportional(self, gross_result, yrt_result):
        """Ceded claims = gross claims * cession_pct."""
        _, ceded = yrt_result
        np.testing.assert_allclose(
            ceded.death_claims, gross_result.death_claims * 0.5, rtol=1e-10
        )

    def test_net_claims_proportional(self, gross_result, yrt_result):
        """Net claims = gross claims * (1 - cession_pct)."""
        net, _ = yrt_result
        np.testing.assert_allclose(
            net.death_claims, gross_result.death_claims * 0.5, rtol=1e-10
        )


class TestYRTNAR:
    """NAR and YRT premium calculations."""

    def test_nar_populated(self, yrt_result):
        """NAR should be populated in the ceded result."""
        _, ceded = yrt_result
        assert ceded.nar is not None
        assert len(ceded.nar) == ceded.projection_months

    def test_nar_non_negative(self, yrt_result):
        """NAR must be non-negative at all time steps."""
        _, ceded = yrt_result
        assert ceded.nar is not None
        assert np.all(ceded.nar >= 0)

    def test_nar_first_month(self, gross_result, yrt_treaty):
        """
        CLOSED-FORM: At t=0, inforce_ratio=1, so NAR = face - reserve[0].
        """
        _net, ceded = yrt_treaty.apply(gross_result)
        assert ceded.nar is not None
        expected_nar = 1_000_000.0 - gross_result.reserve_balance[0]
        np.testing.assert_allclose(ceded.nar[0], expected_nar, rtol=1e-6)

    def test_yrt_premium_first_month(self, gross_result, yrt_treaty):
        """
        CLOSED-FORM: ceded_prem[0] = NAR[0] * (2.5/12/1000) * 0.5.
        """
        _net, ceded = yrt_treaty.apply(gross_result)
        assert ceded.nar is not None
        expected_nar = 1_000_000.0 - gross_result.reserve_balance[0]
        expected_prem = expected_nar * (2.5 / 12.0 / 1000.0) * 0.5
        np.testing.assert_allclose(ceded.gross_premiums[0], expected_prem, rtol=1e-6)

    def test_yrt_premiums_populated(self, yrt_result):
        """YRT premiums should be populated in the ceded result."""
        _, ceded = yrt_result
        assert ceded.yrt_premiums is not None
        assert np.all(ceded.yrt_premiums >= 0)


class TestYRTBasis:
    """Verify basis labels and metadata."""

    def test_net_basis(self, yrt_result):
        """Net result should have basis='NET'."""
        net, _ = yrt_result
        assert net.basis == "NET"

    def test_ceded_basis(self, yrt_result):
        """Ceded result should have basis='CEDED'."""
        _, ceded = yrt_result
        assert ceded.basis == "CEDED"


class TestYRTEdgeCases:
    """Edge cases for YRT treaty."""

    def test_zero_cession_no_ceded(self, gross_result):
        """With cession_pct=0, ceded claims and premiums should be zero."""
        treaty = YRTTreaty(
            cession_pct=0.0,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.5,
        )
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(ceded.death_claims, 0.0, atol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(
            net.gross_premiums, gross_result.gross_premiums, rtol=1e-10
        )

    def test_full_cession(self, gross_result):
        """With cession_pct=1.0, all claims are ceded."""
        treaty = YRTTreaty(
            cession_pct=1.0,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.5,
        )
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(
            ceded.death_claims, gross_result.death_claims, rtol=1e-10
        )
        np.testing.assert_allclose(net.death_claims, 0.0, atol=1e-10)

    def test_no_yrt_rate_zero_premiums(self, gross_result):
        """Without flat_yrt_rate_per_1000, ceded premiums should be zero."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
        )
        net, ceded = treaty.apply(gross_result)
        np.testing.assert_allclose(ceded.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(
            net.gross_premiums, gross_result.gross_premiums, rtol=1e-10
        )

    def test_expenses_stay_with_cedant(self, gross_result, yrt_result):
        """Expenses should remain fully with the cedant in YRT."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.expenses, gross_result.expenses, rtol=1e-10
        )
        np.testing.assert_allclose(ceded.expenses, 0.0, atol=1e-10)

    def test_lapses_stay_with_cedant(self, gross_result, yrt_result):
        """Lapse surrenders should remain fully with the cedant in YRT."""
        net, ceded = yrt_result
        np.testing.assert_allclose(
            net.lapse_surrenders, gross_result.lapse_surrenders, rtol=1e-10
        )
        np.testing.assert_allclose(ceded.lapse_surrenders, 0.0, atol=1e-10)
