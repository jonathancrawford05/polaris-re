"""CLI wiring for block-aware expense-allowance duration mapping — Slice 2.

Slice 1 (ADR-166) decoupled the two roles ``inforce`` plays in
``BaseTreaty.apply``: per-policy cession honoring is gated by the keyword-only
``use_policy_cession`` flag, while block-aware first-year allowance mapping stays
keyed on ``inforce`` *presence*. Slice 2 rewires the CLI so it passes ``inforce``
to ``treaty.apply`` **always** (threading the deal's ``use_policy_cession`` as
the flag) instead of gating whether ``inforce`` is passed on that flag.

Before Slice 2 a renewal (mid-duration) block priced with
``use_policy_cession=False`` and a sliding-scale allowance got the *new-business*
first-year basis — over-charging the high first-year allowance rate on business
years past policy year one. These tests pin the fix at the CLI pricing entry
point (``_price_single_cohort``) and guard that an allowance-free config is
byte-identical to the old ``inforce=None`` path.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from polaris_re.cli import _build_pipeline_from_config, _price_single_cohort
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance

_ALLOWANCE_BLOCK = {"first_year_pct": 0.40, "renewal_pct": 0.10, "months_per_year": 12}


def _write_config(config: dict) -> Path:  # type: ignore[type-arg]
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump(config, tmp)
    return Path(tmp.name)


def _renewal_config(**deal_overrides: object) -> dict:  # type: ignore[type-arg]
    """A single 10-year in-force (mid-duration) TERM policy, no per-policy
    cession override, priced on a flat treaty (``use_policy_cession=False``)."""
    deal: dict = {  # type: ignore[type-arg]
        "product_type": "TERM",
        "treaty_type": "Coinsurance",
        "cession_pct": 0.50,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "projection_years": 10,
        "acquisition_cost": 500.0,
        "maintenance_cost": 75.0,
        "use_policy_cession": False,
    }
    deal.update(deal_overrides)
    return {
        "mortality": {"source": "flat", "flat_qx": 0.003, "multiplier": 1.0},
        "lapse": {"duration_table": {"1": 0.05, "ultimate": 0.03}},
        "deal": deal,
        "policies": [
            {
                "policy_id": "OLD-001",
                "issue_age": 40,
                "attained_age": 50,  # issue_age + 10y in force
                "sex": "M",
                "smoker": False,
                "face_amount": 1_000_000.0,
                "annual_premium": 3000.0,
                "policy_term": 30,
                "duration_inforce": 120,  # 10 policy years in force
                "issue_date": "2015-01-01",
                "valuation_date": "2025-01-01",
            }
        ],
    }


def _price(config: dict):  # type: ignore[type-arg]
    """Run the actual CLI single-cohort pricing path and return its
    ``CohortResult`` (which carries ``ceded_cashflows``)."""
    path = _write_config(config)
    inforce, assumptions, proj, inputs = _build_pipeline_from_config(path)
    return _price_single_cohort(
        cohort_id="TERM",
        cohort_inforce=inforce,
        assumptions=assumptions,
        config=proj,
        inputs=inputs,
        hurdle_rate=0.10,
        parity_label="test",
    )


# --------------------------------------------------------------------------- #
# 1. THE FIX — the CLI charges the RENEWAL rate on a mid-duration block even   #
#    when use_policy_cession is False.                                         #
# --------------------------------------------------------------------------- #


def test_cli_prices_allowance_block_aware_when_cession_flag_false() -> None:
    from polaris_re.products.dispatch import get_product_engine
    from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

    config = _renewal_config(expense_allowance=dict(_ALLOWANCE_BLOCK))
    result = _price(config)
    cli_ceded = result.ceded_cashflows
    assert cli_ceded is not None

    # Independent references: rebuild the same gross + treaty and apply it two
    # ways — block-aware (inforce passed) and new-business (inforce omitted).
    path = _write_config(config)
    inforce, assumptions, proj, _inputs = _build_pipeline_from_config(path)
    gross = get_product_engine(inforce, assumptions, proj).project()
    treaty = CoinsuranceTreaty(
        cession_pct=0.50,
        expense_allowance=ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10),
    )
    _, ceded_blockaware = treaty.apply(gross, inforce=inforce, use_policy_cession=False)
    _, ceded_newbiz = treaty.apply(gross, inforce=None)

    # The CLI matches the block-aware reference (renewal rate throughout for a
    # 10-year in-force policy), NOT the buggy new-business basis.
    np.testing.assert_allclose(cli_ceded.expenses, ceded_blockaware.expenses)
    assert float(cli_ceded.expenses.sum()) < float(ceded_newbiz.expenses.sum())
    # First projection month must be the renewal rate, well below new-business.
    assert cli_ceded.expenses[0] < 0.5 * ceded_newbiz.expenses[0]


def test_cli_cession_stays_flat_when_flag_false() -> None:
    """Passing ``inforce`` for the allowance mapping must NOT silently start
    honoring a per-policy cession override when ``use_policy_cession`` is False.
    A policy overriding cession to 0.90 against a treaty default of 0.50 must
    still be ceded at the flat 0.50."""
    config = _renewal_config(expense_allowance=dict(_ALLOWANCE_BLOCK))
    config["policies"][0]["reinsurance_cession_pct"] = 0.90
    result = _price(config)
    ceded = result.ceded_cashflows
    gross = result.gross_cashflows
    # Flat 0.50 cession on premiums (override ignored because flag is False).
    np.testing.assert_allclose(ceded.gross_premiums, gross.gross_premiums * 0.50)


# --------------------------------------------------------------------------- #
# 2. BYTE-IDENTICAL GUARD — no allowance ⇒ old inforce=None path unchanged.    #
# --------------------------------------------------------------------------- #


def test_cli_no_allowance_byte_identical_to_flat_path() -> None:
    from polaris_re.products.dispatch import get_product_engine
    from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

    config = _renewal_config()  # no allowance
    result = _price(config)
    cli_ceded = result.ceded_cashflows
    cli_net = result.net_cashflows

    path = _write_config(config)
    inforce, assumptions, proj, _inputs = _build_pipeline_from_config(path)
    gross = get_product_engine(inforce, assumptions, proj).project()
    treaty = CoinsuranceTreaty(cession_pct=0.50)
    # The former CLI path for use_policy_cession=False: inforce omitted.
    net_ref, ceded_ref = treaty.apply(gross, inforce=None)

    np.testing.assert_array_equal(cli_ceded.net_cash_flow, ceded_ref.net_cash_flow)
    np.testing.assert_array_equal(cli_net.net_cash_flow, net_ref.net_cash_flow)


@pytest.mark.parametrize("months_in_force", [0, 120])
def test_new_business_block_unaffected_by_wiring(months_in_force: int) -> None:
    """For a *new-business* block (duration 0) the block-aware and new-business
    allowance bases coincide, so the wiring change is a no-op there; for a
    mid-duration block they diverge. This pins both ends of the behaviour."""
    from polaris_re.products.dispatch import get_product_engine
    from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

    config = _renewal_config(expense_allowance=dict(_ALLOWANCE_BLOCK))
    # Age/duration are derived from issue_date → valuation_date (validated for
    # internal consistency), so drive them off the issue date.
    issue_year = 2025 - months_in_force // 12
    config["policies"][0]["duration_inforce"] = months_in_force
    config["policies"][0]["attained_age"] = 40 + months_in_force // 12
    config["policies"][0]["issue_date"] = f"{issue_year}-01-01"

    result = _price(config)
    cli_ceded = result.ceded_cashflows

    path = _write_config(config)
    inforce, assumptions, proj, _inputs = _build_pipeline_from_config(path)
    gross = get_product_engine(inforce, assumptions, proj).project()
    treaty = CoinsuranceTreaty(
        cession_pct=0.50,
        expense_allowance=ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10),
    )
    _, ceded_newbiz = treaty.apply(gross, inforce=None)

    if months_in_force == 0:
        # Block-aware and new-business coincide → CLI == new-business basis.
        np.testing.assert_allclose(cli_ceded.expenses, ceded_newbiz.expenses)
    else:
        # Mid-duration → CLI charges strictly less than the new-business basis.
        assert float(cli_ceded.expenses.sum()) < float(ceded_newbiz.expenses.sum())
