"""
Decouple the two roles ``inforce`` plays in ``BaseTreaty.apply`` — Slice 1.

Before this slice a caller had a single lever (pass ``inforce`` or not) that
controlled *two* independent concerns at once:

1. **Cession resolution** — whether per-policy ``reinsurance_cession_pct``
   overrides are honored (face-weighted) or the flat treaty ``cession_pct`` is
   used.
2. **Block-aware first-year allowance mapping** — whether the sliding-scale
   ``ExpenseAllowance`` first-year rate is charged on genuine policy-year-one
   business (``first_year_fraction_for_block``) or on the new-business
   projection-month basis (first ``months_per_year`` periods).

The CLI / API / dashboard gate passing ``inforce`` on ``use_policy_cession``.
So a renewal (mid-duration) block priced with ``use_policy_cession=False`` and
a sliding-scale allowance got the *new-business* mapping — over-charging the
first-year rate on business that is years past policy year one (measured
+65% / +$1,767 ceded allowance on a single 10-year in-force policy).

This slice adds a keyword-only ``use_policy_cession: bool = True`` to
``apply``: cession honoring is keyed on the **flag**, block-aware allowance
mapping stays keyed on **``inforce`` presence**. A caller can now pass
``inforce`` for the allowance mapping while keeping the flat cession.

Slice 1 is engine-only — no CLI/API/dashboard caller is rewired yet, so every
golden stays byte-identical (default ``True`` + the existing ``inforce=None``
call sites are unchanged). Slice 2 wires the callers.
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
from polaris_re.reinsurance.fw_coinsurance import FWCoinsuranceTreaty
from polaris_re.reinsurance.modco import ModcoTreaty
from polaris_re.reinsurance.yrt import YRTTreaty

FIXTURES = Path(__file__).parent.parent / "fixtures"
VAL = date(2025, 1, 1)


def _mortality() -> MortalityTable:
    from polaris_re.utils.table_io import load_mortality_csv

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


def _gross(block: InforceBlock):
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    assumptions = AssumptionSet(mortality=_mortality(), lapse=lapse, version="test-v1")
    config = ProjectionConfig(valuation_date=VAL, projection_horizon_years=5, discount_rate=0.05)
    return TermLife(block, assumptions, config).project()


def _policy(policy_id: str, issue_year: int, cession: float | None) -> Policy:
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
        reinsurance_cession_pct=cession,
        issue_date=date(issue_year, 1, 1),
        valuation_date=VAL,
    )


@pytest.fixture()
def renewal_block_no_override() -> InforceBlock:
    """One 10-year in-force policy, no per-policy cession override."""
    return InforceBlock(policies=[_policy("OLD", 2015, cession=None)])


# ----------------------------------------------------------------------
# 1. THE FIX — flag False keeps the block-aware allowance mapping.
# ----------------------------------------------------------------------


def test_coinsurance_flag_false_keeps_block_aware_allowance(renewal_block_no_override):
    """With use_policy_cession=False + an allowance, the renewal block must
    still be charged the *renewal* rate (block-aware), NOT the new-business
    first-year rate — while cession stays flat."""
    gross = _gross(renewal_block_no_override)
    allow = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
    treaty = CoinsuranceTreaty(cession_pct=0.5, expense_allowance=allow)

    # New-business (buggy) basis: inforce omitted entirely.
    _, ceded_newbiz = treaty.apply(gross, inforce=None)
    # Block-aware reference: inforce passed, overrides honored (default).
    _, ceded_blockaware = treaty.apply(gross, inforce=renewal_block_no_override)
    # The fix: inforce passed for the allowance, but flat cession.
    _, ceded_fixed = treaty.apply(
        gross, inforce=renewal_block_no_override, use_policy_cession=False
    )

    # The fixed path matches the block-aware path (renewal rate throughout),
    # NOT the new-business path.
    np.testing.assert_allclose(ceded_fixed.expenses, ceded_blockaware.expenses)
    assert float(ceded_fixed.expenses.sum()) < float(ceded_newbiz.expenses.sum())
    # First projection month: renewal rate (~$50), not first-year rate (~$200).
    assert ceded_fixed.expenses[0] < 0.5 * ceded_newbiz.expenses[0]


def test_yrt_flag_false_keeps_block_aware_allowance(renewal_block_no_override):
    gross = _gross(renewal_block_no_override)
    allow = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
    treaty = YRTTreaty(
        cession_pct=0.5,
        total_face_amount=1_000_000.0,
        flat_yrt_rate_per_1000=2.0,
        expense_allowance=allow,
    )
    _, ceded_newbiz = treaty.apply(gross, inforce=None)
    _, ceded_blockaware = treaty.apply(gross, inforce=renewal_block_no_override)
    _, ceded_fixed = treaty.apply(
        gross, inforce=renewal_block_no_override, use_policy_cession=False
    )
    np.testing.assert_allclose(ceded_fixed.expenses, ceded_blockaware.expenses)
    assert float(ceded_fixed.expenses.sum()) < float(ceded_newbiz.expenses.sum())


# ----------------------------------------------------------------------
# 2. Cession honoring is keyed on the flag, not on inforce presence.
# ----------------------------------------------------------------------


def test_flag_gates_per_policy_cession_override():
    """A block whose policy overrides cession to 0.5 against a treaty default of
    0.9: flag True honors the 0.5 override, flag False uses the flat 0.9."""
    block = InforceBlock(policies=[_policy("OVR", 2015, cession=0.5)])
    gross = _gross(block)
    treaty = CoinsuranceTreaty(cession_pct=0.9)

    _, ceded_honored = treaty.apply(gross, inforce=block, use_policy_cession=True)
    _, ceded_flat = treaty.apply(gross, inforce=block, use_policy_cession=False)

    # Honored → 0.5 of gross premiums ceded; flat → 0.9 of gross premiums.
    np.testing.assert_allclose(ceded_honored.gross_premiums, gross.gross_premiums * 0.5)
    np.testing.assert_allclose(ceded_flat.gross_premiums, gross.gross_premiums * 0.9)


# ----------------------------------------------------------------------
# 2b. The flag gates cession on ALL four proportional treaties.
# ----------------------------------------------------------------------


def _proportional_treaty(kind: str):
    """One treaty of each proportional kind, all with a 0.9 flat cession.

    Every proportional treaty cedes ``death_claims * c``; the constructors
    differ only in their extra required fields (YRT rate, modco/FW rate).
    """
    if kind == "coinsurance":
        return CoinsuranceTreaty(cession_pct=0.9)
    if kind == "yrt":
        return YRTTreaty(cession_pct=0.9, total_face_amount=1_000_000.0, flat_yrt_rate_per_1000=2.0)
    if kind == "modco":
        return ModcoTreaty(cession_pct=0.9, modco_interest_rate=0.045)
    if kind == "fw_coinsurance":
        return FWCoinsuranceTreaty(cession_pct=0.9, funds_withheld_rate=0.045)
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["coinsurance", "yrt", "modco", "fw_coinsurance"])
def test_flag_gates_cession_all_proportional_treaties(kind):
    """Explicit coverage that ``use_policy_cession`` threads through every
    proportional treaty's ``apply`` → ``_resolve_cession``: a 0.5 per-policy
    override is honored only when the flag is True; otherwise the flat 0.9
    treaty cession is used. Asserted on ``ceded.death_claims`` (= gross * c for
    all four)."""
    block = InforceBlock(policies=[_policy("OVR", 2015, cession=0.5)])
    gross = _gross(block)
    treaty = _proportional_treaty(kind)

    _, ceded_honored = treaty.apply(gross, inforce=block, use_policy_cession=True)
    _, ceded_flat = treaty.apply(gross, inforce=block, use_policy_cession=False)

    np.testing.assert_allclose(ceded_honored.death_claims, gross.death_claims * 0.5)
    np.testing.assert_allclose(ceded_flat.death_claims, gross.death_claims * 0.9)


# ----------------------------------------------------------------------
# 3. Backward compatibility — default True is byte-identical.
# ----------------------------------------------------------------------


def test_default_true_matches_explicit_true():
    block = InforceBlock(policies=[_policy("OVR", 2015, cession=0.5)])
    gross = _gross(block)
    treaty = CoinsuranceTreaty(cession_pct=0.9)
    net_default, ceded_default = treaty.apply(gross, inforce=block)
    net_true, ceded_true = treaty.apply(gross, inforce=block, use_policy_cession=True)
    np.testing.assert_array_equal(ceded_default.gross_premiums, ceded_true.gross_premiums)
    np.testing.assert_array_equal(net_default.net_cash_flow, net_true.net_cash_flow)


def test_no_override_block_flag_true_matches_flat():
    """A block with no per-policy override: passing inforce with the default
    flag is byte-identical to the flat inforce=None path (face_weighted_cession
    returns the treaty default when nothing overrides)."""
    block = InforceBlock(policies=[_policy("OLD", 2015, cession=None)])
    gross = _gross(block)
    treaty = CoinsuranceTreaty(cession_pct=0.5)  # no allowance
    _, ceded_flat = treaty.apply(gross, inforce=None)
    _, ceded_inforce = treaty.apply(gross, inforce=block, use_policy_cession=True)
    np.testing.assert_array_equal(ceded_flat.gross_premiums, ceded_inforce.gross_premiums)
    np.testing.assert_array_equal(ceded_flat.death_claims, ceded_inforce.death_claims)
