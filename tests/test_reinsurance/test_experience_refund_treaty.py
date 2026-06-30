"""
ExperienceRefund treaty wiring tests (Slice 3b-1).

Verifies that an ``ExperienceRefund`` set on ``CoinsuranceTreaty`` / ``YRTTreaty``:

1. Default (no refund) leaves every treaty output byte-identical.
2. Preserves ``net + ceded == gross`` on premiums, claims, expenses, and NCF
   (the refund is a reinsurer->cedant transfer, not a new external flow).
3. Reproduces the hand-computed refund and lands it on the FINAL projection
   period only, shifting net/ceded NCF by exactly the refund there.
4. Composes additively with the expense allowance when both are active, and the
   refund is computed net of the allowance already paid.
5. Refunds nothing on unfavourable / below-retention experience (byte-identical).
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
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
from polaris_re.reinsurance.experience_refund import ExperienceRefund
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"
VAL = date(2025, 1, 1)


def _mortality() -> MortalityTable:
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


def _gross_from_block(block: InforceBlock):
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    assumptions = AssumptionSet(mortality=_mortality(), lapse=lapse, version="test-v1")
    config = ProjectionConfig(
        valuation_date=VAL,
        projection_horizon_years=5,
        discount_rate=0.05,
    )
    return TermLife(block, assumptions, config).project()


def _policy(policy_id: str, issue_year: int) -> Policy:
    months = (VAL.year - issue_year) * 12
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=40 + months // 12,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=1_000_000.0,
        annual_premium=12_000.0,
        product_type=ProductType.TERM,
        policy_term=30,
        duration_inforce=months,
        reinsurance_cession_pct=0.5,
        issue_date=date(issue_year, 1, 1),
        valuation_date=VAL,
    )


@pytest.fixture()
def new_block() -> InforceBlock:
    """Single new-business policy (duration 0)."""
    return InforceBlock(policies=[_policy("NEW", 2025)])


# ----------------------------------------------------------------------
# 1. Default (no refund) is byte-identical
# ----------------------------------------------------------------------


def test_coinsurance_default_byte_identical(new_block):
    gross = _gross_from_block(new_block)
    base_net, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross)
    same_net, same_ceded = CoinsuranceTreaty(cession_pct=0.5, experience_refund=None).apply(gross)
    np.testing.assert_array_equal(base_net.expenses, same_net.expenses)
    np.testing.assert_array_equal(base_ceded.expenses, same_ceded.expenses)
    np.testing.assert_array_equal(base_net.net_cash_flow, same_net.net_cash_flow)
    np.testing.assert_array_equal(base_ceded.net_cash_flow, same_ceded.net_cash_flow)


def test_yrt_default_byte_identical(new_block):
    gross = _gross_from_block(new_block)
    treaty_args = dict(cession_pct=0.5, total_face_amount=1_000_000.0, flat_yrt_rate_per_1000=2.0)
    base_net, base_ceded = YRTTreaty(**treaty_args).apply(gross)
    same_net, same_ceded = YRTTreaty(**treaty_args, experience_refund=None).apply(gross)
    np.testing.assert_array_equal(base_net.expenses, same_net.expenses)
    np.testing.assert_array_equal(base_ceded.expenses, same_ceded.expenses)
    np.testing.assert_array_equal(base_net.net_cash_flow, same_net.net_cash_flow)
    np.testing.assert_array_equal(base_ceded.net_cash_flow, same_ceded.net_cash_flow)


# ----------------------------------------------------------------------
# 2. Additivity holds with a refund (transfer nets to zero)
# ----------------------------------------------------------------------


def test_coinsurance_refund_preserves_additivity(new_block):
    gross = _gross_from_block(new_block)
    treaty = CoinsuranceTreaty(
        cession_pct=0.5,
        experience_refund=ExperienceRefund(refund_pct=0.50),
    )
    net, ceded = treaty.apply(gross, new_block)
    treaty.verify_additivity(gross, net, ceded)
    np.testing.assert_allclose(net.expenses + ceded.expenses, gross.expenses, rtol=1e-10)


def test_yrt_refund_preserves_additivity(new_block):
    gross = _gross_from_block(new_block)
    treaty = YRTTreaty(
        cession_pct=0.5,
        total_face_amount=1_000_000.0,
        flat_yrt_rate_per_1000=2.0,
        experience_refund=ExperienceRefund(refund_pct=0.50),
    )
    net, ceded = treaty.apply(gross, new_block)
    treaty.verify_additivity(gross, net, ceded)
    np.testing.assert_allclose(net.expenses + ceded.expenses, gross.expenses, rtol=1e-10)


# ----------------------------------------------------------------------
# 3. Closed-form refund, landed on the FINAL period only
# ----------------------------------------------------------------------


def test_coinsurance_refund_closed_form_terminal(new_block):
    """The refund lands solely on the final expense period and shifts NCF by R."""
    gross = _gross_from_block(new_block)
    refund_terms = ExperienceRefund(refund_pct=0.50)
    treaty = CoinsuranceTreaty(cession_pct=0.5, experience_refund=refund_terms)

    base_net, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    net, ceded = treaty.apply(gross, new_block)

    expected_r = refund_terms.compute_refund(base_ceded.gross_premiums, base_ceded.death_claims)
    assert expected_r > 0.0  # favourable term experience -> a real refund

    transfer = ceded.expenses - base_ceded.expenses
    # All zero except the final period == the scalar refund.
    np.testing.assert_allclose(transfer[:-1], 0.0, atol=1e-9)
    np.testing.assert_allclose(transfer[-1], expected_r, rtol=1e-10)
    # Mirror on the net side.
    np.testing.assert_allclose(base_net.expenses - net.expenses, transfer, rtol=1e-10)
    # NCF: reinsurer pays the refund at the terminal period; cedant receives it.
    np.testing.assert_allclose(
        base_ceded.net_cash_flow[-1] - ceded.net_cash_flow[-1], expected_r, rtol=1e-10
    )
    np.testing.assert_allclose(
        net.net_cash_flow[-1] - base_net.net_cash_flow[-1], expected_r, rtol=1e-10
    )


@pytest.mark.parametrize("refund_pct", [0.0, 0.25, 0.5, 1.0])
def test_coinsurance_refund_linear_in_pct(new_block, refund_pct):
    """The terminal transfer scales linearly with refund_pct."""
    gross = _gross_from_block(new_block)
    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    treaty = CoinsuranceTreaty(
        cession_pct=0.5, experience_refund=ExperienceRefund(refund_pct=refund_pct)
    )
    _, ceded = treaty.apply(gross, new_block)
    balance = base_ceded.gross_premiums.sum() - base_ceded.death_claims.sum()
    expected = refund_pct * max(0.0, balance)
    np.testing.assert_allclose(ceded.expenses[-1] - base_ceded.expenses[-1], expected, rtol=1e-10)


# ----------------------------------------------------------------------
# 4. Composition: allowance + refund active simultaneously
# ----------------------------------------------------------------------


def test_allowance_and_refund_compose_additively(new_block):
    """With both transfers active, additivity holds and the refund is net of
    the allowance already paid."""
    gross = _gross_from_block(new_block)
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    refund_terms = ExperienceRefund(refund_pct=0.50)

    treaty = CoinsuranceTreaty(
        cession_pct=0.5, expense_allowance=allowance, experience_refund=refund_terms
    )
    net, ceded = treaty.apply(gross, new_block)
    treaty.verify_additivity(gross, net, ceded)
    np.testing.assert_allclose(net.expenses + ceded.expenses, gross.expenses, rtol=1e-10)

    # Reconstruct the expected refund: net of the allowance array the treaty paid.
    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    fraction = allowance.first_year_fraction_for_block(
        new_block, len(base_ceded.gross_premiums), VAL
    )
    allowance_arr = allowance.compute_allowance(
        base_ceded.gross_premiums, base_ceded.death_claims, first_year_fraction=fraction
    )
    expected_r = refund_terms.compute_refund(
        base_ceded.gross_premiums, base_ceded.death_claims, allowances=allowance_arr
    )
    # The terminal expense carries BOTH the period allowance and the refund.
    terminal_transfer = ceded.expenses[-1] - base_ceded.expenses[-1]
    np.testing.assert_allclose(terminal_transfer, allowance_arr[-1] + expected_r, rtol=1e-10)


def test_refund_net_of_allowance_is_smaller(new_block):
    """A treaty that also pays an allowance refunds strictly less (the allowance
    reduces the sharable experience balance)."""
    gross = _gross_from_block(new_block)
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    refund_terms = ExperienceRefund(refund_pct=0.50)

    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)

    refund_only = CoinsuranceTreaty(cession_pct=0.5, experience_refund=refund_terms)
    _, ceded_refund_only = refund_only.apply(gross, new_block)

    fraction = allowance.first_year_fraction_for_block(
        new_block, len(base_ceded.gross_premiums), VAL
    )
    allowance_arr = allowance.compute_allowance(
        base_ceded.gross_premiums, base_ceded.death_claims, first_year_fraction=fraction
    )

    r_only = ceded_refund_only.expenses[-1] - base_ceded.expenses[-1]
    r_with_allowance = refund_terms.compute_refund(
        base_ceded.gross_premiums, base_ceded.death_claims, allowances=allowance_arr
    )
    assert r_with_allowance < r_only


# ----------------------------------------------------------------------
# 5. Unfavourable / below-retention experience refunds nothing
# ----------------------------------------------------------------------


def test_below_retention_refunds_nothing_byte_identical(new_block):
    """A retention above the favourable balance refunds nothing -> byte-identical."""
    gross = _gross_from_block(new_block)
    base_net, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    treaty = CoinsuranceTreaty(
        cession_pct=0.5,
        experience_refund=ExperienceRefund(refund_pct=1.0, retention=1.0e12),
    )
    net, ceded = treaty.apply(gross, new_block)
    np.testing.assert_array_equal(ceded.expenses, base_ceded.expenses)
    np.testing.assert_array_equal(net.expenses, base_net.expenses)
    np.testing.assert_array_equal(ceded.net_cash_flow, base_ceded.net_cash_flow)
    np.testing.assert_array_equal(net.net_cash_flow, base_net.net_cash_flow)


def test_unfavourable_experience_refunds_nothing(new_block):
    """A large reinsurer margin drives the balance negative -> zero refund."""
    gross = _gross_from_block(new_block)
    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    treaty = CoinsuranceTreaty(
        cession_pct=0.5,
        experience_refund=ExperienceRefund(refund_pct=0.50, reinsurer_margin_pct=1.0),
    )
    _, ceded = treaty.apply(gross, new_block)
    np.testing.assert_array_equal(ceded.expenses, base_ceded.expenses)
