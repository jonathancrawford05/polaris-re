"""
Tests for policy-level cession override (ADR-036).

Verifies the treaty-default-with-policy-override design:
    1. Treaty cession_pct is the default when policy has no override (None).
    2. Policy-level reinsurance_cession_pct overrides treaty default.
    3. Mixed blocks produce face-weighted average cession for aggregate flows.
    4. Additivity invariant (net + ceded == gross) holds under blended cession.
    5. Backward compatibility: existing callers without inforce= still work.
"""

from datetime import date
from pathlib import Path

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.modco import ModcoTreaty
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    policy_id: str,
    face_amount: float = 500_000.0,
    cession_pct: float | None = None,
) -> Policy:
    """Build a standard term policy with optional cession override."""
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face_amount,
        annual_premium=face_amount * 0.003,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=0,
        reinsurance_cession_pct=cession_pct,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


def _make_assumptions() -> AssumptionSet:
    """Build assumption set from synthetic fixtures."""
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
    return AssumptionSet(mortality=mortality, lapse=lapse, version="cession-test-v1")


def _project_gross(block: InforceBlock) -> object:
    """Run a 5-year term life projection and return gross CashFlowResult."""
    assumptions = _make_assumptions()
    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )
    return TermLife(block, assumptions, config).project()


# ---------------------------------------------------------------------------
# InforceBlock cession vector tests
# ---------------------------------------------------------------------------


class TestEffectiveCessionVec:
    """Test InforceBlock.effective_cession_vec() and face_weighted_cession()."""

    def test_all_none_defaults_to_treaty(self) -> None:
        """When all policies have cession=None, effective vec = treaty default."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", cession_pct=None),
                _make_policy("P2", cession_pct=None),
            ]
        )
        result = block.effective_cession_vec(treaty_default=0.90)
        np.testing.assert_allclose(result, [0.90, 0.90])

    def test_all_explicit_ignores_treaty(self) -> None:
        """When all policies have explicit cession, treaty default is ignored."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", cession_pct=0.70),
                _make_policy("P2", cession_pct=0.30),
            ]
        )
        result = block.effective_cession_vec(treaty_default=0.90)
        np.testing.assert_allclose(result, [0.70, 0.30])

    def test_mixed_override_and_default(self) -> None:
        """Mix of None and explicit: None → treaty default, explicit → override."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", cession_pct=0.80),
                _make_policy("P2", cession_pct=None),
                _make_policy("P3", cession_pct=0.40),
            ]
        )
        result = block.effective_cession_vec(treaty_default=0.50)
        np.testing.assert_allclose(result, [0.80, 0.50, 0.40])

    def test_face_weighted_cession_uniform(self) -> None:
        """Equal face amounts → simple average of effective cession rates."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face_amount=500_000, cession_pct=0.80),
                _make_policy("P2", face_amount=500_000, cession_pct=0.40),
            ]
        )
        result = block.face_weighted_cession(treaty_default=0.50)
        np.testing.assert_allclose(result, 0.60)  # (0.80 + 0.40) / 2

    def test_face_weighted_cession_nonuniform(self) -> None:
        """Larger face gets more weight in blended cession."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face_amount=1_000_000, cession_pct=0.90),
                _make_policy("P2", face_amount=500_000, cession_pct=None),
            ]
        )
        # Effective: P1=0.90, P2=0.50 (treaty default)
        # Face-weighted: (1M * 0.90 + 0.5M * 0.50) / 1.5M = 1.15M / 1.5M
        result = block.face_weighted_cession(treaty_default=0.50)
        expected = (1_000_000 * 0.90 + 500_000 * 0.50) / 1_500_000
        np.testing.assert_allclose(result, expected)

    def test_face_weighted_all_none(self) -> None:
        """All None → face_weighted_cession equals treaty default."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face_amount=500_000, cession_pct=None),
                _make_policy("P2", face_amount=1_000_000, cession_pct=None),
            ]
        )
        result = block.face_weighted_cession(treaty_default=0.75)
        np.testing.assert_allclose(result, 0.75)

    def test_cession_pct_vec_returns_nan_for_none(self) -> None:
        """cession_pct_vec uses NaN as sentinel for None (use treaty default)."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", cession_pct=0.50),
                _make_policy("P2", cession_pct=None),
            ]
        )
        raw = block.cession_pct_vec
        np.testing.assert_allclose(raw[0], 0.50)
        assert np.isnan(raw[1])


# ---------------------------------------------------------------------------
# YRT treaty with policy-level override
# ---------------------------------------------------------------------------


class TestYRTCessionOverride:
    """YRT treaty respects policy-level cession overrides."""

    def test_no_inforce_uses_treaty_default(self) -> None:
        """Backward compat: .apply(gross) without inforce uses treaty cession_pct."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.30)])
        gross = _project_gross(block)
        treaty = YRTTreaty(cession_pct=0.50, total_face_amount=500_000)
        _net, ceded = treaty.apply(gross)
        # ceded claims = gross * 0.50 (treaty default, policy ignored)
        np.testing.assert_allclose(ceded.death_claims, gross.death_claims * 0.50, rtol=1e-10)

    def test_inforce_with_overrides_changes_cession(self) -> None:
        """Passing inforce with explicit policy cession changes the split."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.30)])
        gross = _project_gross(block)
        treaty = YRTTreaty(cession_pct=0.90, total_face_amount=500_000)

        # Without inforce — uses treaty 90%
        _, ceded_default = treaty.apply(gross)
        # With inforce — uses policy 30%
        _, ceded_override = treaty.apply(gross, inforce=block)

        # Ceded claims should be lower with 30% override than 90% treaty
        assert ceded_override.death_claims.sum() < ceded_default.death_claims.sum()
        np.testing.assert_allclose(
            ceded_override.death_claims, gross.death_claims * 0.30, rtol=1e-10
        )

    def test_inforce_none_cession_falls_back(self) -> None:
        """Policy with None cession falls back to treaty cession_pct."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=None)])
        gross = _project_gross(block)
        treaty = YRTTreaty(cession_pct=0.60, total_face_amount=500_000)

        _, ceded = treaty.apply(gross, inforce=block)
        np.testing.assert_allclose(ceded.death_claims, gross.death_claims * 0.60, rtol=1e-10)

    def test_additivity_with_override(self) -> None:
        """net + ceded == gross even with policy-level override."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.70)])
        gross = _project_gross(block)
        treaty = YRTTreaty(
            cession_pct=0.50,
            total_face_amount=500_000,
            flat_yrt_rate_per_1000=2.5,
        )
        net, ceded = treaty.apply(gross, inforce=block)
        treaty.verify_additivity(gross, net, ceded)


# ---------------------------------------------------------------------------
# Coinsurance treaty with policy-level override
# ---------------------------------------------------------------------------


class TestCoinsuranceCessionOverride:
    """Coinsurance treaty respects policy-level cession overrides."""

    def test_override_changes_proportional_split(self) -> None:
        """Policy override of 30% vs treaty 90% produces different net reserves."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.30)])
        gross = _project_gross(block)
        treaty = CoinsuranceTreaty(cession_pct=0.90)

        net_default, _ = treaty.apply(gross)
        net_override, _ = treaty.apply(gross, inforce=block)

        # 30% cession → 70% net reserves vs 10% net reserves
        np.testing.assert_allclose(
            net_override.reserve_balance,
            gross.reserve_balance * 0.70,
            rtol=1e-10,
        )
        assert net_override.reserve_balance.sum() > net_default.reserve_balance.sum()

    def test_additivity_with_override(self) -> None:
        """net + ceded == gross even with policy-level override."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.65)])
        gross = _project_gross(block)
        treaty = CoinsuranceTreaty(cession_pct=0.90)
        net, ceded = treaty.apply(gross, inforce=block)
        treaty.verify_additivity(gross, net, ceded)


# ---------------------------------------------------------------------------
# Modco treaty with policy-level override
# ---------------------------------------------------------------------------


class TestModcoCessionOverride:
    """Modco treaty respects policy-level cession overrides."""

    def test_override_changes_modco_interest(self) -> None:
        """Policy cession override changes the modco interest amount."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.30)])
        gross = _project_gross(block)
        treaty = ModcoTreaty(cession_pct=0.90, modco_interest_rate=0.045)

        net_default, _ = treaty.apply(gross)
        net_override, _ = treaty.apply(gross, inforce=block)

        # 30% cession → lower modco interest than 90%
        assert net_override.modco_interest is not None
        assert net_default.modco_interest is not None
        assert net_override.modco_interest.sum() < net_default.modco_interest.sum()

    def test_additivity_with_override(self) -> None:
        """NCF additivity holds with override."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=0.55)])
        gross = _project_gross(block)
        treaty = ModcoTreaty(cession_pct=0.90, modco_interest_rate=0.04)
        net, ceded = treaty.apply(gross, inforce=block)
        treaty.verify_additivity(gross, net, ceded)


# ---------------------------------------------------------------------------
# Mixed block (face-weighted blending)
# ---------------------------------------------------------------------------


class TestMixedBlockCession:
    """Test face-weighted cession blending on mixed blocks."""

    def test_mixed_block_blended_cession(self) -> None:
        """
        Two-policy block: P1 ($1M face, 90% cession) + P2 ($500k face, None).
        Treaty default = 50%.
        Face-weighted = (1M*0.90 + 0.5M*0.50) / 1.5M ≈ 0.7667.
        """
        block = InforceBlock(
            policies=[
                _make_policy("P1", face_amount=1_000_000, cession_pct=0.90),
                _make_policy("P2", face_amount=500_000, cession_pct=None),
            ]
        )
        gross = _project_gross(block)
        treaty = CoinsuranceTreaty(cession_pct=0.50)

        _, ceded_blended = treaty.apply(gross, inforce=block)
        _, ceded_default = treaty.apply(gross)

        expected_blend = (1_000_000 * 0.90 + 500_000 * 0.50) / 1_500_000

        # Ceded premiums should be gross * blended_cession
        np.testing.assert_allclose(
            ceded_blended.gross_premiums,
            gross.gross_premiums * expected_blend,
            rtol=1e-10,
        )
        # And different from the treaty default (50%)
        assert not np.allclose(ceded_blended.gross_premiums, ceded_default.gross_premiums)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing code without inforce= continues to work unchanged."""

    def test_policy_none_cession_default(self) -> None:
        """Policy with cession_pct=None is valid and creates cleanly."""
        p = _make_policy("P1", cession_pct=None)
        assert p.reinsurance_cession_pct is None

    def test_policy_explicit_cession_still_works(self) -> None:
        """Policy with explicit cession_pct still validates and stores."""
        p = _make_policy("P1", cession_pct=0.75)
        assert p.reinsurance_cession_pct == 0.75

    def test_treaty_apply_without_inforce(self) -> None:
        """treaty.apply(gross) without inforce= uses treaty cession_pct."""
        block = InforceBlock(policies=[_make_policy("P1", cession_pct=None)])
        gross = _project_gross(block)
        treaty = YRTTreaty(cession_pct=0.50, total_face_amount=500_000)
        _net, ceded = treaty.apply(gross)
        np.testing.assert_allclose(ceded.death_claims, gross.death_claims * 0.50, rtol=1e-10)
