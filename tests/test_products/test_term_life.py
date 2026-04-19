"""
Tests for TermLife cash flow projection engine.

Includes closed-form verification tests against hand calculations
using a single policy with known mortality and lapse rates.
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
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def single_policy_block() -> InforceBlock:
    """A single 40-year-old male NS term life policy."""
    policy = Policy(
        policy_id="TEST001",
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
    return InforceBlock(policies=[policy])


@pytest.fixture()
def mortality_table() -> MortalityTable:
    """Synthetic mortality table for testing."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


@pytest.fixture()
def lapse_assumption() -> LapseAssumption:
    """Simple lapse assumption for testing."""
    return LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})


@pytest.fixture()
def assumption_set(
    mortality_table: MortalityTable, lapse_assumption: LapseAssumption
) -> AssumptionSet:
    return AssumptionSet(
        mortality=mortality_table,
        lapse=lapse_assumption,
        version="test-v1",
    )


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )


@pytest.fixture()
def engine(
    single_policy_block: InforceBlock,
    assumption_set: AssumptionSet,
    config: ProjectionConfig,
) -> TermLife:
    return TermLife(single_policy_block, assumption_set, config)


class TestTermLifeValidation:
    """Tests for input validation."""

    def test_rejects_non_term_policies(
        self, assumption_set: AssumptionSet, config: ProjectionConfig
    ):
        """Non-TERM policies should be rejected."""
        wl_policy = Policy(
            policy_id="WL001",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=8_000.0,
            product_type=ProductType.WHOLE_LIFE,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[wl_policy])
        from polaris_re.core.exceptions import PolarisValidationError

        with pytest.raises(PolarisValidationError, match="non-TERM"):
            TermLife(block, assumption_set, config)


class TestTermLifeProjection:
    """Tests for projection output shape and properties."""

    def test_project_returns_cashflow_result(self, engine: TermLife):
        """project() returns a CashFlowResult."""
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == "TERM"

    def test_projection_months(self, engine: TermLife):
        """Output has correct number of time steps."""
        result = engine.project()
        assert result.projection_months == 60

    def test_premiums_positive(self, engine: TermLife):
        """Premiums should be positive in early months."""
        result = engine.project()
        assert result.gross_premiums[0] > 0

    def test_claims_non_negative(self, engine: TermLife):
        """Death claims should be non-negative."""
        result = engine.project()
        assert np.all(result.death_claims >= 0)

    def test_premiums_decrease_over_time(self, engine: TermLife):
        """Premiums decrease as policies leave the block."""
        result = engine.project()
        assert result.gross_premiums[0] > result.gross_premiums[-1]


class TestTermLifeClosedForm:
    """Closed-form verification tests for single policy."""

    def test_first_month_premium(self, engine: TermLife):
        """
        CLOSED-FORM: First month premium = 12000/12 * 1.0 = 1000.0.
        """
        result = engine.project()
        np.testing.assert_allclose(result.gross_premiums[0], 1000.0, rtol=1e-10)

    def test_first_month_claim(self, engine: TermLife):
        """
        CLOSED-FORM: First month claim = lx[0] * q_monthly * face
        q_annual for age 40, dur_1 (select year 0) = 0.0026
        q_monthly = 1 - (1-0.0026)^(1/12)
        """
        result = engine.project()
        q_annual = 0.0026
        q_monthly = 1.0 - (1.0 - q_annual) ** (1.0 / 12.0)
        expected_claim = q_monthly * 1_000_000.0
        np.testing.assert_allclose(result.death_claims[0], expected_claim, rtol=1e-6)

    def test_inforce_decreasing(self, engine: TermLife):
        """In-force factor should be monotonically decreasing."""
        result = engine.project(seriatim=True)
        assert result.seriatim_lx is not None
        lx = result.seriatim_lx[0, :]
        assert np.all(np.diff(lx) <= 0)

    def test_inforce_starts_at_one(self, engine: TermLife):
        """lx[0] = 1.0 for all policies."""
        result = engine.project(seriatim=True)
        assert result.seriatim_lx is not None
        np.testing.assert_allclose(result.seriatim_lx[0, 0], 1.0)

    def test_net_cash_flow_accounting_identity(self, engine: TermLife):
        """
        ACCOUNTING IDENTITY:
        net_cf = premiums - claims - lapses - expenses - reserve_increase
        Must hold for all t.
        """
        result = engine.project()
        expected_ncf = (
            result.gross_premiums
            - result.death_claims
            - result.lapse_surrenders
            - result.expenses
            - result.reserve_increase
        )
        np.testing.assert_allclose(result.net_cash_flow, expected_ncf, rtol=1e-10)


class TestTermLifeReserves:
    """Tests for net premium reserves."""

    def test_reserves_non_negative(self, engine: TermLife):
        """Net premium reserves should be non-negative for term life."""
        reserves = engine.compute_reserves()
        assert np.all(reserves >= -1e-10)

    def test_terminal_reserve_zero(self, engine: TermLife):
        """Terminal reserve V_T = 0."""
        reserves = engine.compute_reserves()
        np.testing.assert_allclose(reserves[0, -1], 0.0, atol=1e-10)

    def test_reserve_shape(self, engine: TermLife):
        """Reserves shape should be (N, T)."""
        reserves = engine.compute_reserves()
        assert reserves.shape == (1, 60)


class TestTermLifeSeriatim:
    """Tests for seriatim output."""

    def test_seriatim_populated_when_requested(self, engine: TermLife):
        """seriatim=True populates (N,T) arrays."""
        result = engine.project(seriatim=True)
        assert result.seriatim_premiums is not None
        assert result.seriatim_claims is not None
        assert result.seriatim_reserves is not None
        assert result.seriatim_lx is not None

    def test_seriatim_not_populated_by_default(self, engine: TermLife):
        """seriatim arrays are None by default."""
        result = engine.project(seriatim=False)
        assert result.seriatim_premiums is None

    def test_seriatim_sums_to_aggregate(self, engine: TermLife):
        """Seriatim premiums summed over policies should match aggregate."""
        result = engine.project(seriatim=True)
        assert result.seriatim_premiums is not None
        np.testing.assert_allclose(
            result.seriatim_premiums.sum(axis=0),
            result.gross_premiums,
            rtol=1e-10,
        )

    def test_seriatim_claims_sum_to_aggregate(self, engine: TermLife):
        """Seriatim claims summed over policies should match aggregate."""
        result = engine.project(seriatim=True)
        assert result.seriatim_claims is not None
        np.testing.assert_allclose(
            result.seriatim_claims.sum(axis=0),
            result.death_claims,
            rtol=1e-10,
        )


class TestTermLifeMultiPolicy:
    """Tests with multiple policies."""

    def test_two_policies(self, assumption_set: AssumptionSet, config: ProjectionConfig):
        """Projection works with multiple policies."""
        policies = [
            Policy(
                policy_id=f"P{i}",
                issue_age=35 + i,
                attained_age=35 + i,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=500_000.0 * (i + 1),
                annual_premium=6_000.0 * (i + 1),
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )
            for i in range(2)
        ]
        block = InforceBlock(policies=policies)
        engine = TermLife(block, assumption_set, config)
        result = engine.project(seriatim=True)

        assert result.projection_months == 60
        assert result.seriatim_premiums is not None
        assert result.seriatim_premiums.shape == (2, 60)

        expected_prem = (6_000.0 / 12) + (12_000.0 / 12)
        np.testing.assert_allclose(result.gross_premiums[0], expected_prem, rtol=1e-10)


class TestTermLifePremiumExpiry:
    """Verify premiums and expenses stop after the policy term expires."""

    def test_premiums_zero_after_term(
        self, single_policy_block: InforceBlock, assumption_set: AssumptionSet
    ):
        """A 20yr term projected over 30yr must have zero premiums after month 240."""
        long_config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=30,
            discount_rate=0.05,
        )
        engine = TermLife(single_policy_block, assumption_set, long_config)
        result = engine.project()

        term_months = 20 * 12  # 240
        assert result.gross_premiums[:term_months].sum() > 0.0
        np.testing.assert_allclose(
            result.gross_premiums[term_months:],
            0.0,
            atol=1e-15,
            err_msg="Premiums must be zero after the policy term expires",
        )

    def test_expenses_zero_after_term(
        self, single_policy_block: InforceBlock, assumption_set: AssumptionSet
    ):
        """Ongoing maintenance expenses must stop after term expiry."""
        long_config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=30,
            discount_rate=0.05,
            maintenance_cost_per_policy_per_year=120.0,
        )
        engine = TermLife(single_policy_block, assumption_set, long_config)
        result = engine.project()

        term_months = 20 * 12
        assert result.expenses[:term_months].sum() > 0.0
        np.testing.assert_allclose(
            result.expenses[term_months:],
            0.0,
            atol=1e-15,
            err_msg="Expenses must be zero after the policy term expires",
        )


class TestTermLifeAcquisitionCostGating:
    """Acquisition cost applies only to new-business policies (duration_inforce == 0)."""

    def test_seasoned_policy_no_acquisition_cost(
        self, assumption_set: AssumptionSet
    ) -> None:
        """
        A seasoned inforce policy (duration_inforce > 0) must NOT receive
        acquisition cost — it was already paid at original issue.
        """
        seasoned_policy = Policy(
            policy_id="TERM_SEASONED",
            issue_age=35,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=12_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=60,  # 5 years seasoned
            reinsurance_cession_pct=0.5,
            issue_date=date(2020, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=10,
            discount_rate=0.05,
            acquisition_cost_per_policy=500.0,
            maintenance_cost_per_policy_per_year=0.0,
        )
        block = InforceBlock(policies=[seasoned_policy])
        engine = TermLife(block, assumption_set, config)
        result = engine.project()
        # Zero acquisition for seasoned policy, zero maintenance → all expenses zero
        np.testing.assert_allclose(result.expenses, 0.0, atol=1e-15)

    def test_mixed_block_acquisition_only_new_business(
        self, assumption_set: AssumptionSet
    ) -> None:
        """
        A block with 1 new-business and 1 seasoned policy: acquisition cost
        applies only to the new-business policy.
        """
        new_policy = Policy(
            policy_id="TERM_NEW",
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
        seasoned_policy = Policy(
            policy_id="TERM_SEASONED",
            issue_age=35,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=12_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=60,  # 5 years seasoned
            reinsurance_cession_pct=0.5,
            issue_date=date(2020, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=10,
            discount_rate=0.05,
            acquisition_cost_per_policy=500.0,
            maintenance_cost_per_policy_per_year=0.0,
        )
        block = InforceBlock(policies=[new_policy, seasoned_policy])
        engine = TermLife(block, assumption_set, config)
        result = engine.project()
        # Only 1 of 2 policies is new business → month-0 expense = 1 × $500
        np.testing.assert_allclose(result.expenses[0], 500.0, rtol=1e-10)
        # No maintenance → remaining months are zero
        np.testing.assert_allclose(result.expenses[1:], 0.0, atol=1e-15)

    def test_new_business_still_receives_acquisition(
        self, single_policy_block: InforceBlock, assumption_set: AssumptionSet
    ) -> None:
        """A new-business policy (duration_inforce == 0) still gets acquisition cost."""
        config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=5,
            discount_rate=0.05,
            acquisition_cost_per_policy=750.0,
            maintenance_cost_per_policy_per_year=0.0,
        )
        engine = TermLife(single_policy_block, assumption_set, config)
        result = engine.project()
        np.testing.assert_allclose(result.expenses[0], 750.0, rtol=1e-10)
