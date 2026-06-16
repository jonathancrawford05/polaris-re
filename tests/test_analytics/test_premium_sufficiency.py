"""
PremiumSufficiencyTester tests.

Key closed-form tests:
  1. Flat deterministic block at rate 0 -> ratios are exact arithmetic.
  2. Single payment at month 12 -> PV equals v**12 exactly.
  3. combined_ratio == loss_ratio + expense_ratio; sufficiency_ratio == 1 - combined_ratio.
  4. is_sufficient verdict against a parametrized target_margin.
  5. Insufficient block (costs exceed premium) -> negative margin, not sufficient.
  6. Zero / non-positive premium -> ratios None, not sufficient.
  7. Integration: TermLife GROSS projection -> tester produces a coherent verdict.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.premium_sufficiency import (
    PremiumSufficiencyResult,
    PremiumSufficiencyTester,
)
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_cashflow(
    *,
    premiums: np.ndarray,
    claims: np.ndarray | None = None,
    surrenders: np.ndarray | None = None,
    expenses: np.ndarray | None = None,
    basis: str = "GROSS",
) -> CashFlowResult:
    """Build a minimal CashFlowResult for premium-sufficiency testing."""
    t = len(premiums)
    zeros = np.zeros(t, dtype=np.float64)
    claims = zeros if claims is None else claims
    surrenders = zeros if surrenders is None else surrenders
    expenses = zeros if expenses is None else expenses
    net = premiums - claims - surrenders - expenses
    return CashFlowResult(
        run_id="test",
        valuation_date=date(2025, 1, 1),
        basis=basis,  # type: ignore[arg-type]
        assumption_set_version="v1",
        product_type="TERM",
        projection_months=t,
        time_index=np.arange(
            np.datetime64("2025-01"), np.datetime64("2025-01") + t, dtype="datetime64[M]"
        ),
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=surrenders,
        expenses=expenses,
        net_cash_flow=net,
    )


class TestClosedFormFlatBlock:
    """Rate 0 makes every PV an exact undiscounted sum."""

    def _result(self, target_margin: float = 0.0) -> PremiumSufficiencyResult:
        t = 24
        cf = _make_cashflow(
            premiums=np.full(t, 100.0, dtype=np.float64),
            claims=np.full(t, 40.0, dtype=np.float64),
            surrenders=np.full(t, 5.0, dtype=np.float64),
            expenses=np.full(t, 10.0, dtype=np.float64),
        )
        return PremiumSufficiencyTester(cf, discount_rate=0.0, target_margin=target_margin).run()

    def test_pv_components_are_undiscounted_sums(self) -> None:
        r = self._result()
        np.testing.assert_allclose(r.pv_premiums, 2400.0)
        np.testing.assert_allclose(r.pv_claims, 960.0)
        np.testing.assert_allclose(r.pv_surrenders, 120.0)
        np.testing.assert_allclose(r.pv_benefits, 1080.0)
        np.testing.assert_allclose(r.pv_expenses, 240.0)

    def test_sufficiency_margin_and_ratios(self) -> None:
        r = self._result()
        # margin = 2400 - 1080 - 240 = 1080
        np.testing.assert_allclose(r.sufficiency_margin, 1080.0)
        np.testing.assert_allclose(r.sufficiency_ratio, 0.45)
        np.testing.assert_allclose(r.loss_ratio, 0.45)
        np.testing.assert_allclose(r.expense_ratio, 0.10)
        np.testing.assert_allclose(r.combined_ratio, 0.55)

    def test_ratio_identities(self) -> None:
        r = self._result()
        assert r.combined_ratio is not None
        assert r.loss_ratio is not None
        assert r.expense_ratio is not None
        assert r.sufficiency_ratio is not None
        np.testing.assert_allclose(r.combined_ratio, r.loss_ratio + r.expense_ratio)
        np.testing.assert_allclose(r.sufficiency_ratio, 1.0 - r.combined_ratio)


class TestDiscounting:
    def test_single_payment_at_month_12(self) -> None:
        t = 12
        premiums = np.zeros(t, dtype=np.float64)
        premiums[-1] = 1000.0  # paid at month 12
        cf = _make_cashflow(premiums=premiums)
        rate = 0.06
        r = PremiumSufficiencyTester(cf, discount_rate=rate).run()
        v = (1.0 + rate) ** (-1.0 / 12.0)
        np.testing.assert_allclose(r.pv_premiums, 1000.0 * v**12)
        # Equivalently, discounting one year at the annual rate.
        np.testing.assert_allclose(r.pv_premiums, 1000.0 / (1.0 + rate))


class TestSufficiencyVerdict:
    @pytest.mark.parametrize(
        ("target_margin", "expected"),
        [
            (0.0, True),  # margin ratio 0.45 >= 0.0
            (0.40, True),  # 0.45 >= 0.40
            (0.45, True),  # boundary: 0.45 >= 0.45
            (0.50, False),  # 0.45 < 0.50
            (0.60, False),
        ],
    )
    def test_target_margin_sensitivity(self, target_margin: float, expected: bool) -> None:
        t = 12
        cf = _make_cashflow(
            premiums=np.full(t, 100.0, dtype=np.float64),
            claims=np.full(t, 45.0, dtype=np.float64),
            expenses=np.full(t, 10.0, dtype=np.float64),
        )
        # loss 0.45, expense 0.10, combined 0.55, sufficiency ratio 0.45
        r = PremiumSufficiencyTester(cf, discount_rate=0.0, target_margin=target_margin).run()
        np.testing.assert_allclose(r.sufficiency_ratio, 0.45)
        assert r.is_sufficient is expected

    def test_insufficient_block_negative_margin(self) -> None:
        t = 12
        cf = _make_cashflow(
            premiums=np.full(t, 100.0, dtype=np.float64),
            claims=np.full(t, 95.0, dtype=np.float64),
            expenses=np.full(t, 20.0, dtype=np.float64),  # benefits + expenses = 115 > 100
        )
        r = PremiumSufficiencyTester(cf, discount_rate=0.0).run()
        assert r.sufficiency_margin < 0.0
        assert r.combined_ratio is not None and r.combined_ratio > 1.0
        assert r.is_sufficient is False


class TestEdgeCases:
    def test_zero_premium_ratios_none_and_insufficient(self) -> None:
        t = 6
        cf = _make_cashflow(
            premiums=np.zeros(t, dtype=np.float64),
            claims=np.full(t, 10.0, dtype=np.float64),
        )
        r = PremiumSufficiencyTester(cf, discount_rate=0.05).run()
        # Exact-zero check (not an approximate value comparison): premiums are
        # all zeros so the PV is identically 0.0 — `== 0.0` is the intended test.
        assert r.pv_premiums == 0.0
        assert r.sufficiency_ratio is None
        assert r.loss_ratio is None
        assert r.expense_ratio is None
        assert r.combined_ratio is None
        assert r.is_sufficient is False
        # Margin is still well-defined (negative cost).
        np.testing.assert_allclose(r.sufficiency_margin, -r.pv_benefits)

    @pytest.mark.parametrize("bad", [-0.01, 1.0, 1.5])
    def test_invalid_target_margin_rejected(self, bad: float) -> None:
        cf = _make_cashflow(premiums=np.full(12, 100.0, dtype=np.float64))
        with pytest.raises(ValueError, match="target_margin"):
            PremiumSufficiencyTester(cf, discount_rate=0.0, target_margin=bad)

    def test_basis_agnostic_net_input_accepted(self) -> None:
        # Unlike ProfitTester, sufficiency accepts any basis (incl. CEDED).
        cf = _make_cashflow(
            premiums=np.full(12, 50.0, dtype=np.float64),
            claims=np.full(12, 20.0, dtype=np.float64),
            basis="CEDED",
        )
        r = PremiumSufficiencyTester(cf, discount_rate=0.0).run()
        np.testing.assert_allclose(r.loss_ratio, 0.4)
        assert r.is_sufficient is True


class TestReserveExcluded:
    """Premium adequacy must ignore the reserve movement entirely."""

    def test_reserve_increase_does_not_change_result(self) -> None:
        t = 12
        premiums = np.full(t, 100.0, dtype=np.float64)
        claims = np.full(t, 40.0, dtype=np.float64)
        expenses = np.full(t, 10.0, dtype=np.float64)
        cf_no_reserve = _make_cashflow(premiums=premiums, claims=claims, expenses=expenses)
        cf_with_reserve = _make_cashflow(premiums=premiums, claims=claims, expenses=expenses)
        # Inject a large reserve movement; net_cash_flow would change for a
        # profit test, but premium sufficiency must be identical.
        cf_with_reserve.reserve_increase = np.full(t, 25.0, dtype=np.float64)
        cf_with_reserve.net_cash_flow = cf_with_reserve.net_cash_flow - 25.0

        r1 = PremiumSufficiencyTester(cf_no_reserve, discount_rate=0.03).run()
        r2 = PremiumSufficiencyTester(cf_with_reserve, discount_rate=0.03).run()
        np.testing.assert_allclose(r1.sufficiency_margin, r2.sufficiency_margin)
        # Bit-identical equality (not approximate): the analyzer never reads the
        # reserve arrays, so the two results are computed from identical inputs.
        assert r1.combined_ratio == r2.combined_ratio


class TestTermLifeIntegration:
    def test_gross_projection_produces_coherent_verdict(self) -> None:
        policy = Policy(
            policy_id="P1",
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
            reinsurance_cession_pct=0.0,
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
            projection_horizon_years=20,
            discount_rate=0.04,
        )
        gross = TermLife(block, assumptions, config).project()
        assert gross.basis == "GROSS"

        r = PremiumSufficiencyTester(gross, discount_rate=0.04, target_margin=0.05).run()

        # Coherence: the PV identity holds and ratios are populated on a
        # positive-premium GROSS block.
        np.testing.assert_allclose(
            r.sufficiency_margin,
            r.pv_premiums - r.pv_benefits - r.pv_expenses,
        )
        assert r.loss_ratio is not None
        assert r.combined_ratio is not None
        np.testing.assert_allclose(r.combined_ratio, r.loss_ratio + r.expense_ratio)
        # Verdict is consistent with the computed ratio.
        assert r.is_sufficient == (r.sufficiency_ratio >= 0.05)
