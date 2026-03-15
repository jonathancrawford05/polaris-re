"""
Tests for UniversalLife cash flow projection engine.

Includes account value roll-forward verification, COI calculation,
lapse-due-to-AV-depletion, and structural invariants.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.universal_life import UniversalLife
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mortality_table() -> MortalityTable:
    """Synthetic mortality table for UL testing."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic UL Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


@pytest.fixture()
def lapse_assumption() -> LapseAssumption:
    return LapseAssumption.from_duration_table({1: 0.03, 2: 0.02, "ultimate": 0.01})


@pytest.fixture()
def assumption_set(
    mortality_table: MortalityTable, lapse_assumption: LapseAssumption
) -> AssumptionSet:
    return AssumptionSet(
        mortality=mortality_table,
        lapse=lapse_assumption,
        version="ul-test-v1",
    )


@pytest.fixture()
def single_ul_policy() -> Policy:
    """Single UL policy: male NS, age 40, face $500k, AV $10k, credited 4%."""
    return Policy(
        policy_id="UL_001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=500_000.0,
        annual_premium=6_000.0,  # target premium = $500/month
        product_type=ProductType.UNIVERSAL_LIFE,
        policy_term=None,
        duration_inforce=0,
        reinsurance_cession_pct=0.50,
        account_value=10_000.0,
        credited_rate=0.04,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


@pytest.fixture()
def single_ul_block(single_ul_policy: Policy) -> InforceBlock:
    return InforceBlock(policies=[single_ul_policy])


@pytest.fixture()
def short_config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=3,
        discount_rate=0.05,
    )


@pytest.fixture()
def long_config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
    )


class TestUniversalLifeValidation:
    """Input validation tests."""

    def test_rejects_term_policies(
        self, assumption_set: AssumptionSet, short_config: ProjectionConfig
    ) -> None:
        term_policy = Policy(
            policy_id="TERM_001",
            issue_age=40,
            attained_age=40,
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
        )
        block = InforceBlock(policies=[term_policy])
        with pytest.raises(PolarisValidationError, match="non-UL"):
            UniversalLife(inforce=block, assumptions=assumption_set, config=short_config)

    def test_rejects_missing_account_value(
        self, assumption_set: AssumptionSet, short_config: ProjectionConfig
    ) -> None:
        policy = Policy(
            policy_id="UL_NO_AV",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=6_000.0,
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            account_value=None,  # missing
            credited_rate=0.04,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        with pytest.raises(PolarisValidationError, match="account_value"):
            UniversalLife(inforce=block, assumptions=assumption_set, config=short_config)

    def test_rejects_missing_credited_rate(
        self, assumption_set: AssumptionSet, short_config: ProjectionConfig
    ) -> None:
        policy = Policy(
            policy_id="UL_NO_RATE",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=6_000.0,
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            account_value=10_000.0,
            credited_rate=None,  # missing
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        with pytest.raises(PolarisValidationError, match="credited_rate"):
            UniversalLife(inforce=block, assumptions=assumption_set, config=short_config)


class TestUniversalLifeAccountValue:
    """Tests for account value roll-forward correctness."""

    def test_av_positive_for_well_funded_policy(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """A well-funded policy should maintain positive AV throughout."""
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        av = engine.compute_reserves()
        assert np.all(av >= 0.0), "Account values went negative"

    def test_av_initial_value(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """AV at t=0 should equal the policy's initial account_value."""
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        av = engine.compute_reserves()
        assert av[0, 0] == pytest.approx(10_000.0, rel=1e-6)

    def test_av_grows_with_credited_interest(
        self,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Over-funded policy (high AV, low COI) should see AV grow with credited interest."""
        # Policy with very high AV relative to face (COI will be near 0)
        policy = Policy(
            policy_id="UL_OVERFUNDED",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=100_000.0,  # small face
            annual_premium=12_000.0,  # high premium
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            account_value=200_000.0,  # AV > face (NAR=0, no COI)
            credited_rate=0.05,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        engine = UniversalLife(inforce=block, assumptions=assumption_set, config=short_config)
        av = engine.compute_reserves()
        # AV should grow (credited > 0, no COI)
        assert av[0, -1] > av[0, 0]

    def test_av_depletes_zero_premium(
        self,
        assumption_set: AssumptionSet,
        long_config: ProjectionConfig,
    ) -> None:
        """A policy with zero premium and small AV should eventually deplete."""
        policy = Policy(
            policy_id="UL_LAPSE",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=0.0,  # zero premium
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            account_value=1_000.0,  # small initial AV
            credited_rate=0.04,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        engine = UniversalLife(
            inforce=block,
            assumptions=assumption_set,
            config=long_config,
        )
        av = engine.compute_reserves()
        # At some point the AV reaches zero (lapse occurs)
        assert av[0, -1] == pytest.approx(0.0, abs=1e-6)

    def test_coi_zero_when_av_exceeds_face(
        self,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """COI should be negligible when AV >= face (NAR = 0)."""
        policy = Policy(
            policy_id="UL_OVERFUNDED2",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=50_000.0,
            annual_premium=0.0,
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            account_value=100_000.0,  # AV >> face
            credited_rate=0.05,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        engine = UniversalLife(
            inforce=block, assumptions=assumption_set, config=short_config
        )
        q = engine._build_mortality_arrays()
        w = engine._build_lapse_arrays()
        _av, coi, _lx, _lapse = engine._roll_forward_account_values(q, w)
        # COI in first month should be ~0 since AV > face (NAR = 0)
        np.testing.assert_allclose(coi[0, 0], 0.0, atol=1e-10)


class TestUniversalLifeProjection:
    """Tests for the project() output."""

    def test_project_basis_and_product_type(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == "UNIVERSAL_LIFE"

    def test_array_lengths(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        result = engine.project()
        t = short_config.projection_months
        assert len(result.gross_premiums) == t
        assert len(result.death_claims) == t
        assert len(result.net_cash_flow) == t

    def test_net_cash_flow_accounting_identity(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """NCF = premiums - claims - lapses - expenses - reserve_increase."""
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
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

    def test_premiums_at_target(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """First-month premiums = annual_premium / 12."""
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        result = engine.project()
        expected_monthly = 6_000.0 / 12.0
        assert result.gross_premiums[0] == pytest.approx(expected_monthly, rel=1e-6)

    def test_seriatim_output(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        result = engine.project(seriatim=True)
        t = short_config.projection_months
        assert result.seriatim_lx is not None
        assert result.seriatim_lx.shape == (1, t)
        assert result.seriatim_lx[0, 0] == pytest.approx(1.0, rel=1e-10)

    def test_reserve_equals_av(
        self,
        single_ul_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """compute_reserves() returns the AV array."""
        engine = UniversalLife(
            inforce=single_ul_block, assumptions=assumption_set, config=short_config
        )
        av = engine.compute_reserves()
        result = engine.project(seriatim=True)
        np.testing.assert_allclose(result.seriatim_reserves, av, rtol=1e-10)

    def test_surrender_charge_reduces_lapse_cv(
        self,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Surrender charges should reduce lapse surrender values."""
        policy = Policy(
            policy_id="UL_SC",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=6_000.0,
            product_type=ProductType.UNIVERSAL_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            account_value=10_000.0,
            credited_rate=0.04,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        charge = np.array([5_000.0])  # $5k surrender charge

        no_charge = UniversalLife(inforce=block, assumptions=assumption_set, config=short_config)
        with_charge = UniversalLife(
            inforce=block,
            assumptions=assumption_set,
            config=short_config,
            surrender_charge_vec=charge,
        )
        res_no = no_charge.project()
        res_with = with_charge.project()
        # Lapse surrenders should be lower with charge
        assert res_with.lapse_surrenders.sum() <= res_no.lapse_surrenders.sum()
