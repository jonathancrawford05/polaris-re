"""
ExpenseAllowance treaty wiring tests (Slice 2).

Verifies that an ``ExpenseAllowance`` set on ``CoinsuranceTreaty`` / ``YRTTreaty``:

1. Default (no allowance) leaves every treaty output byte-identical.
2. Preserves ``net + ceded == gross`` on premiums, claims, expenses, and NCF
   (the allowance is a reinsurer->cedant transfer, not a new external flow).
3. Reproduces a hand-computed allowance and the shifted net/ceded NCF.
4. Maps projection month -> policy duration on an inforce block so the
   first-year rate is only charged on policy-year-one business (the Slice-2
   correctness requirement; see CONTINUATION_expense_allowance Slice 2 P2).
5. Composes independently with the proportional ``include_expense_allowance``
   layer on coinsurance.
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


@pytest.fixture()
def inforce_block() -> InforceBlock:
    """Single mid-duration policy (5 years in force at valuation)."""
    return InforceBlock(policies=[_policy("OLD", 2020)])


# ----------------------------------------------------------------------
# 1. Default (no allowance) is byte-identical
# ----------------------------------------------------------------------


def test_coinsurance_default_byte_identical(new_block):
    gross = _gross_from_block(new_block)
    base_net, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross)
    same_net, same_ceded = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=None).apply(gross)
    np.testing.assert_array_equal(base_net.expenses, same_net.expenses)
    np.testing.assert_array_equal(base_ceded.expenses, same_ceded.expenses)
    np.testing.assert_array_equal(base_net.net_cash_flow, same_net.net_cash_flow)
    np.testing.assert_array_equal(base_ceded.net_cash_flow, same_ceded.net_cash_flow)


def test_yrt_default_byte_identical(new_block):
    gross = _gross_from_block(new_block)
    treaty_args = dict(cession_pct=0.5, total_face_amount=1_000_000.0, flat_yrt_rate_per_1000=2.0)
    base_net, base_ceded = YRTTreaty(**treaty_args).apply(gross)
    same_net, same_ceded = YRTTreaty(**treaty_args, expense_allowance=None).apply(gross)
    np.testing.assert_array_equal(base_net.expenses, same_net.expenses)
    np.testing.assert_array_equal(base_ceded.expenses, same_ceded.expenses)
    np.testing.assert_array_equal(base_net.net_cash_flow, same_net.net_cash_flow)
    np.testing.assert_array_equal(base_ceded.net_cash_flow, same_ceded.net_cash_flow)


# ----------------------------------------------------------------------
# 2. Additivity holds with an allowance (transfer nets to zero)
# ----------------------------------------------------------------------


def test_coinsurance_allowance_preserves_additivity(new_block):
    gross = _gross_from_block(new_block)
    treaty = CoinsuranceTreaty(
        cession_pct=0.5,
        expense_allowance=ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10),
    )
    net, ceded = treaty.apply(gross, new_block)
    treaty.verify_additivity(gross, net, ceded)
    # Expense-line additivity is the binding constraint for the transfer.
    np.testing.assert_allclose(net.expenses + ceded.expenses, gross.expenses, rtol=1e-10)


def test_yrt_allowance_preserves_additivity(new_block):
    gross = _gross_from_block(new_block)
    treaty = YRTTreaty(
        cession_pct=0.5,
        total_face_amount=1_000_000.0,
        flat_yrt_rate_per_1000=2.0,
        expense_allowance=ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10),
    )
    net, ceded = treaty.apply(gross, new_block)
    treaty.verify_additivity(gross, net, ceded)
    # In YRT, expenses stay with the cedant except the allowance transfer.
    np.testing.assert_allclose(net.expenses + ceded.expenses, gross.expenses, rtol=1e-10)


# ----------------------------------------------------------------------
# 3. Closed-form allowance + shifted NCF
# ----------------------------------------------------------------------


def test_coinsurance_allowance_closed_form_transfer(new_block):
    """The allowance lands on the ceded expense line and shifts NCF by exactly A."""
    gross = _gross_from_block(new_block)
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    treaty = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=allowance)

    base_net, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, new_block)
    net, ceded = treaty.apply(gross, new_block)

    # Hand-compute the expected allowance from the ceded premium stream and the
    # block's first-year mapping (new business → first 12 periods at 80%).
    fraction = allowance.first_year_fraction_for_block(
        new_block, len(base_ceded.gross_premiums), VAL
    )
    expected_a = allowance.compute_allowance(
        base_ceded.gross_premiums, base_ceded.death_claims, first_year_fraction=fraction
    )

    np.testing.assert_allclose(ceded.expenses - base_ceded.expenses, expected_a, rtol=1e-10)
    np.testing.assert_allclose(base_net.expenses - net.expenses, expected_a, rtol=1e-10)
    # NCF: reinsurer pays the allowance (ceded NCF down by A), cedant receives it.
    np.testing.assert_allclose(
        base_ceded.net_cash_flow - ceded.net_cash_flow, expected_a, rtol=1e-10
    )
    np.testing.assert_allclose(net.net_cash_flow - base_net.net_cash_flow, expected_a, rtol=1e-10)


# ----------------------------------------------------------------------
# 4. Inforce duration mapping — first-year rate only on policy-year-one
# ----------------------------------------------------------------------


def test_coinsurance_inforce_block_charges_renewal_rate_only(inforce_block):
    """A mid-duration block must not be charged the first-year acquisition rate."""
    gross = _gross_from_block(inforce_block)
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    treaty = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=allowance)

    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, inforce_block)
    _, ceded = treaty.apply(gross, inforce_block)

    transfer = ceded.expenses - base_ceded.expenses
    # Entirely renewal: allowance == 10% of ceded premium everywhere.
    np.testing.assert_allclose(transfer, base_ceded.gross_premiums * 0.10, rtol=1e-10)


def test_inforce_mapping_lowers_allowance_vs_new_business():
    """Same premium stream, mid-duration block pays a strictly smaller allowance."""
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    new_block = InforceBlock(policies=[_policy("NEW", 2025)])
    old_block = InforceBlock(policies=[_policy("OLD", 2020)])

    gross_new = _gross_from_block(new_block)
    gross_old = _gross_from_block(old_block)
    treaty = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=allowance)

    _, base_ceded_new = CoinsuranceTreaty(cession_pct=0.5).apply(gross_new, new_block)
    _, ceded_new = treaty.apply(gross_new, new_block)
    _, base_ceded_old = CoinsuranceTreaty(cession_pct=0.5).apply(gross_old, old_block)
    _, ceded_old = treaty.apply(gross_old, old_block)

    a_new = float((ceded_new.expenses - base_ceded_new.expenses).sum())
    a_old = float((ceded_old.expenses - base_ceded_old.expenses).sum())
    assert a_new > a_old


# ----------------------------------------------------------------------
# 5. Composition with the proportional include_expense_allowance layer
# ----------------------------------------------------------------------


def test_allowance_independent_of_proportional_layer(new_block):
    """The sliding-scale allowance is the same delta whether or not the
    proportional expense split is on — they are independent layers."""
    gross = _gross_from_block(new_block)
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)

    on_base = CoinsuranceTreaty(cession_pct=0.5, include_expense_allowance=True)
    on_alw = CoinsuranceTreaty(
        cession_pct=0.5, include_expense_allowance=True, expense_allowance=allowance
    )
    off_base = CoinsuranceTreaty(cession_pct=0.5, include_expense_allowance=False)
    off_alw = CoinsuranceTreaty(
        cession_pct=0.5, include_expense_allowance=False, expense_allowance=allowance
    )

    _, on_base_c = on_base.apply(gross, new_block)
    _, on_alw_c = on_alw.apply(gross, new_block)
    _, off_base_c = off_base.apply(gross, new_block)
    _, off_alw_c = off_alw.apply(gross, new_block)

    np.testing.assert_allclose(
        on_alw_c.expenses - on_base_c.expenses,
        off_alw_c.expenses - off_base_c.expenses,
        rtol=1e-10,
    )


# ----------------------------------------------------------------------
# Sliding scale through the treaty
# ----------------------------------------------------------------------


def test_coinsurance_sliding_scale_selects_renewal_band(inforce_block):
    """The sliding scale keys off the treaty's own realized ceded loss ratio."""
    from polaris_re.reinsurance.expense_allowance import ExpenseAllowanceBand

    gross = _gross_from_block(inforce_block)
    allowance = ExpenseAllowance(
        first_year_pct=0.80,
        renewal_pct=0.10,  # ignored when a scale is present
        sliding_scale=[
            ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.20),
            ExpenseAllowanceBand(max_loss_ratio=2.0, allowance_pct=0.05),
        ],
    )
    treaty = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=allowance)

    _, base_ceded = CoinsuranceTreaty(cession_pct=0.5).apply(gross, inforce_block)
    _, ceded = treaty.apply(gross, inforce_block)

    realized_lr = base_ceded.death_claims.sum() / base_ceded.gross_premiums.sum()
    expected_rate = allowance.renewal_rate_for_loss_ratio(realized_lr)
    transfer = ceded.expenses - base_ceded.expenses
    # Mid-duration block → entirely renewal at the band-selected rate.
    np.testing.assert_allclose(transfer, base_ceded.gross_premiums * expected_rate, rtol=1e-10)
