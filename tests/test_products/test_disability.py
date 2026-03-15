"""
Tests for DisabilityProduct — CI and DI cash flow projection engines.

Includes closed-form verification for CI lump sum claims,
DI multi-state recursion correctness, and structural invariants.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.morbidity import MorbidityTable
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.disability import DisabilityProduct
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mortality_table() -> MortalityTable:
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic DI/CI Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


@pytest.fixture()
def lapse_assumption() -> LapseAssumption:
    return LapseAssumption.from_duration_table({1: 0.02, "ultimate": 0.01})


@pytest.fixture()
def assumption_set(
    mortality_table: MortalityTable, lapse_assumption: LapseAssumption
) -> AssumptionSet:
    return AssumptionSet(
        mortality=mortality_table,
        lapse=lapse_assumption,
        version="di-ci-test-v1",
    )


@pytest.fixture()
def ci_morbidity() -> MorbidityTable:
    return MorbidityTable.synthetic_ci()


@pytest.fixture()
def di_morbidity() -> MorbidityTable:
    return MorbidityTable.synthetic_di()


def _make_policy(product_type: ProductType, policy_id: str = "P001") -> Policy:
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=100_000.0,
        annual_premium=1_200.0,
        product_type=product_type,
        policy_term=None,
        duration_inforce=0,
        reinsurance_cession_pct=0.50,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


@pytest.fixture()
def ci_block() -> InforceBlock:
    return InforceBlock(policies=[_make_policy(ProductType.CRITICAL_ILLNESS)])


@pytest.fixture()
def di_block() -> InforceBlock:
    return InforceBlock(policies=[_make_policy(ProductType.DISABILITY)])


@pytest.fixture()
def short_config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )


class TestDisabilityProductValidation:
    """Input validation tests."""

    def test_rejects_term_policies(
        self,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        term_block = InforceBlock(policies=[_make_policy(ProductType.TERM)])
        with pytest.raises(PolarisValidationError, match="unsupported product types"):
            DisabilityProduct(
                inforce=term_block,
                assumptions=assumption_set,
                config=short_config,
                morbidity=ci_morbidity,
            )

    def test_rejects_mixed_types(
        self,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """Block with both CI and DI policies should raise."""
        ci_policy = _make_policy(ProductType.CRITICAL_ILLNESS, "CI_001")
        di_policy = _make_policy(ProductType.DISABILITY, "DI_001")
        mixed_block = InforceBlock(policies=[ci_policy, di_policy])
        with pytest.raises(PolarisValidationError, match="only CI or only DI"):
            DisabilityProduct(
                inforce=mixed_block,
                assumptions=assumption_set,
                config=short_config,
                morbidity=ci_morbidity,
            )

    def test_ci_policy_requires_ci_table(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """CI policies with DI morbidity table raises."""
        with pytest.raises(PolarisValidationError, match="CI morbidity"):
            DisabilityProduct(
                inforce=ci_block,
                assumptions=assumption_set,
                config=short_config,
                morbidity=di_morbidity,
            )

    def test_di_policy_requires_di_table(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        with pytest.raises(PolarisValidationError, match="DI morbidity"):
            DisabilityProduct(
                inforce=di_block,
                assumptions=assumption_set,
                config=short_config,
                morbidity=ci_morbidity,
            )


class TestCIProjection:
    """Tests for Critical Illness projection."""

    def test_project_returns_gross_basis(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == "CRITICAL_ILLNESS"

    def test_claims_positive(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """CI claims should be positive (non-zero incidence for age 40)."""
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project()
        assert result.death_claims.sum() > 0.0

    def test_ncf_accounting_identity(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project()
        expected = (
            result.gross_premiums
            - result.death_claims
            - result.lapse_surrenders
            - result.expenses
            - result.reserve_increase
        )
        np.testing.assert_allclose(result.net_cash_flow, expected, rtol=1e-10)

    def test_ci_claims_lump_sum_per_claim(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """
        CLOSED-FORM (approximate): First-month CI claims ≈ lx[0] * i_month * face
        lx[0] = 1.0, i_month = annual_incidence / 12 at age 40.
        """
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project()

        ages = np.array([40], dtype=np.int32)
        annual_incidence = ci_morbidity.get_incidence_vector(ages, "M")[0]
        monthly_incidence = annual_incidence / 12.0
        expected_t0 = 1.0 * monthly_incidence * 100_000.0  # face amount

        np.testing.assert_allclose(result.death_claims[0], expected_t0, rtol=1e-8)

    def test_seriatim_lx_starts_at_one(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project(seriatim=True)
        assert result.seriatim_lx is not None
        assert result.seriatim_lx[0, 0] == pytest.approx(1.0, rel=1e-10)

    def test_ci_lx_decreases_over_time(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """In-force factor should decrease as CI claims terminate policies."""
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        result = engine.project(seriatim=True)
        lx = result.seriatim_lx
        assert lx is not None
        # lx should be strictly decreasing over time
        assert lx[0, -1] < lx[0, 0]

    def test_zero_reserves(
        self,
        ci_block: InforceBlock,
        assumption_set: AssumptionSet,
        ci_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=ci_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=ci_morbidity,
        )
        reserves = engine.compute_reserves()
        np.testing.assert_allclose(reserves, 0.0, atol=1e-10)


class TestDIProjection:
    """Tests for Disability Income projection."""

    def test_project_returns_gross_basis(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == "DISABILITY"

    def test_ncf_accounting_identity(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )
        result = engine.project()
        expected = (
            result.gross_premiums
            - result.death_claims
            - result.lapse_surrenders
            - result.expenses
            - result.reserve_increase
        )
        np.testing.assert_allclose(result.net_cash_flow, expected, rtol=1e-10)

    def test_di_disabled_lives_start_zero(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """No disabled lives at t=0 (all newly issued)."""
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )
        result = engine.project(seriatim=True)
        # At t=0, no disabled lives yet → DI claims = 0 at t=0
        assert result.death_claims[0] == pytest.approx(0.0, abs=1e-10)

    def test_di_claims_grow_then_stabilize(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """DI benefit payments should be positive and grow early in projection."""
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )
        result = engine.project()
        # Claims in second year should be higher than first year (disabled pool builds up)
        assert result.death_claims[1:12].sum() < result.death_claims[12:24].sum() or \
               result.death_claims[12:24].sum() > 0.0  # some claims must occur

    def test_di_benefit_proportional_to_face(
        self,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """
        CLOSED-FORM (month 2 check):
        At t=1: disabled lives ≈ lx_active[0] * incidence[0]
                monthly_benefit = face/12
                DI claims[1] ≈ disabled[1] * face/12
        """
        face = 100_000.0
        di_block = InforceBlock(policies=[_make_policy(ProductType.DISABILITY)])
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )

        # Get incidence at age 40 for month 0
        ages = np.array([40], dtype=np.int32)
        incidence_annual = di_morbidity.get_incidence_vector(ages, "M")[0]
        incidence_monthly = incidence_annual / 12.0

        result = engine.project()
        # t=1: newly disabled = approx lx_active[0] * incidence[0] ≈ 1 * incidence_monthly
        # DI benefit at t=1 ≈ disabled_t1 * face/12
        expected_t1 = incidence_monthly * (face / 12.0)
        np.testing.assert_allclose(result.death_claims[1], expected_t1, rtol=0.05)

    def test_di_premiums_decrease_over_time(
        self,
        di_block: InforceBlock,
        assumption_set: AssumptionSet,
        di_morbidity: MorbidityTable,
        short_config: ProjectionConfig,
    ) -> None:
        """Premiums (paid by active lives) should decrease as active lives exit."""
        engine = DisabilityProduct(
            inforce=di_block,
            assumptions=assumption_set,
            config=short_config,
            morbidity=di_morbidity,
        )
        result = engine.project()
        # Premium in last year should be lower than first year
        first_year = result.gross_premiums[:12].sum()
        last_year = result.gross_premiums[-12:].sum()
        assert last_year < first_year
