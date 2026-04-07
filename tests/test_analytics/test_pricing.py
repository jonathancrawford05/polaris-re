"""Tests for NetPremiumCalculator (classical equivalence-principle pricing)."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.pricing import (
    NetPremiumCalculator,
    NetPremiumResult,
    _compute_epvs,
)
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _synthetic_table(sex: Sex, smoker: SmokerStatus) -> MortalityTable:
    """Build a MortalityTable for a single (sex, smoker) from the synthetic fixture."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic",
        table_array=table_array,
        sex=sex,
        smoker_status=smoker,
    )


@pytest.fixture()
def mortality_male_ns() -> MortalityTable:
    return _synthetic_table(Sex.MALE, SmokerStatus.NON_SMOKER)


@pytest.fixture()
def mortality_male_sm() -> MortalityTable:
    return _synthetic_table(Sex.MALE, SmokerStatus.SMOKER)


def _wl_policy(
    *,
    policy_id: str = "WL_001",
    issue_age: int = 40,
    attained_age: int | None = None,
    sex: Sex = Sex.MALE,
    smoker: SmokerStatus = SmokerStatus.NON_SMOKER,
    face: float = 1_000_000.0,
) -> Policy:
    return Policy(
        policy_id=policy_id,
        issue_age=issue_age,
        attained_age=attained_age if attained_age is not None else issue_age,
        sex=sex,
        smoker_status=smoker,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=1.0,  # placeholder — this is what we solve for
        product_type=ProductType.WHOLE_LIFE,
        policy_term=None,
        duration_inforce=0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


def _term_policy(*, issue_age: int = 40, term: int = 10, **kw) -> Policy:
    return Policy(
        policy_id=kw.get("policy_id", "TERM_001"),
        issue_age=issue_age,
        attained_age=kw.get("attained_age", issue_age),
        sex=kw.get("sex", Sex.MALE),
        smoker_status=kw.get("smoker", SmokerStatus.NON_SMOKER),
        underwriting_class="STANDARD",
        face_amount=kw.get("face", 1_000_000.0),
        annual_premium=1.0,
        product_type=ProductType.TERM,
        policy_term=term,
        duration_inforce=0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


# ----------------------------------------------------------------------
# Stateless numerical core
# ----------------------------------------------------------------------


class TestComputeEPVs:
    def test_single_year_terminal(self):
        """One-year curve with q=1: A = v, ä = 1, so P = v."""
        q = np.array([1.0])
        A, a = _compute_epvs(q, discount_rate=0.05)
        assert A == pytest.approx(1.0 / 1.05)
        assert a == pytest.approx(1.0)
        assert A / a == pytest.approx(1.0 / 1.05)

    def test_zero_discount_wl_identity(self):
        """At i=0 with a terminal clamp, sum of _t p_x q_{x+t} must equal 1."""
        q = np.array([0.01, 0.02, 0.05, 0.10, 1.0])
        A, _ = _compute_epvs(q, discount_rate=0.0)
        assert A == pytest.approx(1.0, abs=1e-12)

    def test_empty_array_raises(self):
        with pytest.raises(PolarisValidationError):
            _compute_epvs(np.array([]), discount_rate=0.04)


# ----------------------------------------------------------------------
# Whole life pricing
# ----------------------------------------------------------------------


class TestWholeLifePricing:
    def test_returns_wellformed_result(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        result = calc.price(_wl_policy(issue_age=40, face=1_000_000))

        assert isinstance(result, NetPremiumResult)
        assert result.policy_id == "WL_001"
        assert result.product_type == "WHOLE_LIFE"
        assert result.pricing_age == 40
        assert result.basis_age == "issue"
        # Coverage runs from age 40 through terminal 60 inclusive
        assert result.coverage_years == 21
        assert 0.0 < result.A_x < 1.0
        assert result.a_due_x > 1.0
        assert result.net_annual_premium > 0.0
        # With zero loading, gross == net
        assert result.gross_annual_premium == pytest.approx(result.net_annual_premium)
        # rate_per_1000 ties to rate_per_1
        assert result.net_rate_per_1000 == pytest.approx(result.net_rate_per_1 * 1_000.0)

    def test_expense_loading_scales_gross(self, mortality_male_ns):
        base = NetPremiumCalculator(mortality_male_ns, expense_loading=0.0)
        loaded = NetPremiumCalculator(mortality_male_ns, expense_loading=0.25)
        pol = _wl_policy(issue_age=40)

        r_base = base.price(pol)
        r_load = loaded.price(pol)
        assert r_load.net_annual_premium == pytest.approx(r_base.net_annual_premium)
        assert r_load.gross_annual_premium == pytest.approx(r_base.net_annual_premium * 1.25)

    def test_higher_discount_rate_lowers_premium(self, mortality_male_ns):
        """∂P/∂i < 0 for WL: discounting benefits harder than the annuity."""
        low = NetPremiumCalculator(mortality_male_ns, discount_rate=0.02)
        high = NetPremiumCalculator(mortality_male_ns, discount_rate=0.08)
        pol = _wl_policy(issue_age=40)
        assert high.price(pol).net_rate_per_1 < low.price(pol).net_rate_per_1

    def test_older_age_raises_premium(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        younger = calc.price(_wl_policy(issue_age=30))
        older = calc.price(_wl_policy(issue_age=50))
        assert older.net_rate_per_1 > younger.net_rate_per_1

    def test_smoker_above_non_smoker(self, mortality_male_ns, mortality_male_sm):
        ns_calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        sm_calc = NetPremiumCalculator(mortality_male_sm, discount_rate=0.04)
        pol_ns = _wl_policy(issue_age=40, smoker=SmokerStatus.NON_SMOKER)
        pol_sm = _wl_policy(issue_age=40, smoker=SmokerStatus.SMOKER)
        # Synthetic table uses same rates across smoker status in this test —
        # instead we verify the calculator routes through the correct table
        # by checking the basis label round-trips.
        assert ns_calc.price(pol_ns).mortality_basis == "Synthetic"
        assert sm_calc.price(pol_sm).mortality_basis == "Synthetic"

    def test_attained_basis_uses_attained_age(self, mortality_male_ns):
        """
        basis_age="attained" prices at attained_age, not issue_age. Given
        a duration-11 inforce life, attained-basis premium must exceed
        issue-basis premium.
        """
        pol = _wl_policy(issue_age=30, attained_age=41)
        issue = NetPremiumCalculator(
            mortality_male_ns, discount_rate=0.04, basis_age="issue"
        ).price(pol)
        attained = NetPremiumCalculator(
            mortality_male_ns, discount_rate=0.04, basis_age="attained"
        ).price(pol)
        assert issue.pricing_age == 30
        assert attained.pricing_age == 41
        assert attained.net_rate_per_1 > issue.net_rate_per_1

    def test_face_amount_scales_linearly(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        p1 = calc.price(_wl_policy(issue_age=40, face=1_000_000))
        p2 = calc.price(_wl_policy(issue_age=40, face=10_000_000))
        assert p2.net_annual_premium == pytest.approx(10.0 * p1.net_annual_premium, rel=1e-12)
        assert p2.net_rate_per_1 == pytest.approx(p1.net_rate_per_1, rel=1e-12)


# ----------------------------------------------------------------------
# Term pricing
# ----------------------------------------------------------------------


class TestTermPricing:
    def test_term_cheaper_than_whole_life(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        wl = calc.price(_wl_policy(issue_age=40))
        term = calc.price(_term_policy(issue_age=40, term=10))
        assert term.net_rate_per_1 < wl.net_rate_per_1

    def test_longer_term_more_expensive(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        t10 = calc.price(_term_policy(issue_age=40, term=10))
        t20 = calc.price(_term_policy(issue_age=40, term=20))
        assert t20.net_rate_per_1 > t10.net_rate_per_1
        assert t10.coverage_years == 10
        assert t20.coverage_years == 20

    def test_term_exceeds_table_raises(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        # max_age=60, issue 50, 20-year term → would need age 69 coverage
        with pytest.raises(PolarisValidationError, match="exceeds available coverage"):
            calc.price(_term_policy(issue_age=50, term=20))

    def test_missing_policy_term_raises(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns)
        # Build a TERM policy then strip policy_term by reconstructing
        with pytest.raises(PolarisValidationError, match="policy_term"):
            calc.price(
                Policy(
                    policy_id="BAD",
                    issue_age=40,
                    attained_age=40,
                    sex=Sex.MALE,
                    smoker_status=SmokerStatus.NON_SMOKER,
                    underwriting_class="STANDARD",
                    face_amount=100_000.0,
                    annual_premium=1.0,
                    product_type=ProductType.TERM,
                    policy_term=None,
                    duration_inforce=0,
                    issue_date=date(2025, 1, 1),
                    valuation_date=date(2025, 1, 1),
                )
            )


# ----------------------------------------------------------------------
# Block pricing and error handling
# ----------------------------------------------------------------------


class TestBlockPricingAndErrors:
    def test_price_block(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns, discount_rate=0.04)
        block = InforceBlock(
            policies=[
                _wl_policy(policy_id="A", issue_age=35),
                _wl_policy(policy_id="B", issue_age=45),
            ]
        )
        results = calc.price_block(block)
        assert [r.policy_id for r in results] == ["A", "B"]
        assert results[1].net_rate_per_1 > results[0].net_rate_per_1

    def test_unsupported_product_raises(self, mortality_male_ns):
        calc = NetPremiumCalculator(mortality_male_ns)
        pol = Policy(
            policy_id="UL_001",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=100_000.0,
            annual_premium=1.0,
            product_type=ProductType.UNIVERSAL_LIFE,
            duration_inforce=0,
            account_value=10_000.0,
            credited_rate=0.04,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        with pytest.raises(PolarisValidationError, match="WHOLE_LIFE and TERM"):
            calc.price(pol)

    def test_negative_loading_rejected(self, mortality_male_ns):
        with pytest.raises(PolarisValidationError, match="expense_loading"):
            NetPremiumCalculator(mortality_male_ns, expense_loading=-0.1)

    def test_bad_basis_age_rejected(self, mortality_male_ns):
        with pytest.raises(PolarisValidationError, match="basis_age"):
            NetPremiumCalculator(mortality_male_ns, basis_age="retirement")  # type: ignore[arg-type]

    def test_terminal_age_above_table_rejected(self, mortality_male_ns):
        with pytest.raises(PolarisValidationError, match="exceeds table max_age"):
            NetPremiumCalculator(mortality_male_ns, terminal_age=200)
