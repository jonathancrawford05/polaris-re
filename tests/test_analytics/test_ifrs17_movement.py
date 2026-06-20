"""
Tests for the IFRS 17 analysis-of-change (movement) table (analytics/ifrs17.py).

Epic 2 (IFRS 17 movement table), Slice 2 — `IFRS17MovementTable` and
`build_movement_table`.

Verification:
1. **Additivity (headline):** for every reporting period and every component
   (BEL / RA / CSM / total), ``opening + Σ movements == closing`` to
   ``assert_allclose``. This is the defining property of the disclosure.
2. New business is recognised only in the cohort's first reporting period and
   equals the initial-recognition balance; opening of period 0 is 0.
3. Reporting periods chain: each period's opening equals the prior period's
   closing.
4. The CSM (and every component) exhausts to 0 at full run-off.
5. CSM accretes at the cohort's **locked-in** rate (two cohorts at distinct
   rates accrete differently); the per-cohort table preserves that rate.
6. The aggregate movement table equals the per-period, per-component sum of the
   cohort tables.
7. Closed-form: with a constant fulfilment cash flow the BEL release equals
   ``-Σ FCF`` and new business equals the initial BEL.
"""

import math
from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.ifrs17 import (
    IFRS17CohortManager,
    IFRS17ContractInput,
    IFRS17Measurement,
    IFRS17MovementTable,
    build_movement_table,
)
from polaris_re.core.cashflow import CashFlowResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gross_cashflow(
    n_per: int = 36,
    monthly_premium: float = 100.0,
    monthly_claim: float = 10.0,
    monthly_expense: float = 5.0,
    monthly_lapse: float = 2.0,
    run_id: str = "ifrs17_movement_test",
) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult aligned on a common grid."""
    premiums = np.full(n_per, monthly_premium, dtype=np.float64)
    claims = np.full(n_per, monthly_claim, dtype=np.float64)
    expenses = np.full(n_per, monthly_expense, dtype=np.float64)
    lapses = np.full(n_per, monthly_lapse, dtype=np.float64)
    net_cf = premiums - claims - lapses - expenses
    reserves = np.zeros(n_per, dtype=np.float64)
    return CashFlowResult(
        run_id=run_id,
        valuation_date=date(2025, 1, 1),
        basis="GROSS",
        assumption_set_version="v1",
        product_type="TERM",
        projection_months=n_per,
        time_index=np.arange(
            np.datetime64("2025-01"),
            np.datetime64("2025-01") + n_per,
            dtype="datetime64[M]",
        ),
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=lapses,
        expenses=expenses,
        reserve_balance=reserves,
        reserve_increase=reserves.copy(),
        net_cash_flow=net_cf,
    )


def _contract(
    issue_year: int,
    locked_in_rate: float = 0.05,
    ra_factor: float = 0.05,
    **cf_kwargs,
) -> IFRS17ContractInput:
    return IFRS17ContractInput(
        cashflows=_make_gross_cashflow(**cf_kwargs),
        issue_date=date(issue_year, 6, 1),
        locked_in_rate=locked_in_rate,
        ra_factor=ra_factor,
    )


def _multi_cohort_manager() -> IFRS17CohortManager:
    """Two distinct issue-year cohorts at distinct locked-in rates."""
    return IFRS17CohortManager(
        [
            _contract(2022, locked_in_rate=0.04),
            _contract(2022, locked_in_rate=0.04, monthly_premium=120.0),
            _contract(2024, locked_in_rate=0.06),
        ]
    )


# ---------------------------------------------------------------------------
# 1. Additivity — the headline acceptance test
# ---------------------------------------------------------------------------


def test_every_component_foots_per_cohort_and_aggregate():
    manager = _multi_cohort_manager()
    for table in manager.cohort_movement_tables():
        np.testing.assert_allclose(table.max_footing_error(), 0.0, atol=1e-9)
    aggregate = manager.aggregate_movement_table()
    np.testing.assert_allclose(aggregate.max_footing_error(), 0.0, atol=1e-9)


def test_footing_holds_for_monthly_reporting_periods():
    manager = _multi_cohort_manager()
    for table in manager.cohort_movement_tables(months_per_period=1):
        assert table.n_periods == manager.n_periods
        np.testing.assert_allclose(table.max_footing_error(), 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# 2. New business / opening conventions
# ---------------------------------------------------------------------------


def test_new_business_only_in_first_period_equals_initial_recognition():
    cohort = _multi_cohort_manager().cohorts[0]
    table = build_movement_table(cohort.result, cohort.locked_in_rate)
    row0 = table.rows[0]

    # Period 0 opens pre-recognition at zero, new business carries recognition.
    np.testing.assert_allclose(row0.bel.opening, 0.0, atol=1e-12)
    np.testing.assert_allclose(row0.ra.opening, 0.0, atol=1e-12)
    np.testing.assert_allclose(row0.csm.opening, 0.0, atol=1e-12)
    np.testing.assert_allclose(row0.bel.new_business, cohort.result.bel[0])
    np.testing.assert_allclose(row0.ra.new_business, cohort.result.risk_adjustment[0])
    np.testing.assert_allclose(row0.csm.new_business, cohort.result.csm[0])

    # No new business after the first reporting period (exact 0.0 sentinel —
    # atol=0 keeps the file consistent with the "never bare == for floats" rule).
    for row in table.rows[1:]:
        np.testing.assert_allclose(row.bel.new_business, 0.0, atol=0.0)
        np.testing.assert_allclose(row.ra.new_business, 0.0, atol=0.0)
        np.testing.assert_allclose(row.csm.new_business, 0.0, atol=0.0)


def test_opening_chains_to_prior_closing():
    cohort = _multi_cohort_manager().cohorts[0]
    table = build_movement_table(cohort.result, cohort.locked_in_rate)
    for prev, curr in zip(table.rows[:-1], table.rows[1:], strict=True):
        np.testing.assert_allclose(curr.bel.opening, prev.bel.closing)
        np.testing.assert_allclose(curr.ra.opening, prev.ra.closing)
        np.testing.assert_allclose(curr.csm.opening, prev.csm.closing)


# ---------------------------------------------------------------------------
# 3. Run-off: everything exhausts to zero at expiry
# ---------------------------------------------------------------------------


def test_all_components_exhaust_at_expiry():
    cohort = _multi_cohort_manager().cohorts[0]
    table = build_movement_table(cohort.result, cohort.locked_in_rate)
    last = table.rows[-1]
    assert last.end_month == cohort.result.n_periods
    np.testing.assert_allclose(last.bel.closing, 0.0, atol=1e-9)
    np.testing.assert_allclose(last.ra.closing, 0.0, atol=1e-9)
    np.testing.assert_allclose(last.csm.closing, 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# 4. Total column
# ---------------------------------------------------------------------------


def test_total_column_is_sum_of_components():
    table = _multi_cohort_manager().aggregate_movement_table()
    for row in table.rows:
        total = row.total
        np.testing.assert_allclose(
            total.opening, row.bel.opening + row.ra.opening + row.csm.opening
        )
        np.testing.assert_allclose(
            total.closing, row.bel.closing + row.ra.closing + row.csm.closing
        )
        np.testing.assert_allclose(
            total.interest_accretion,
            row.bel.interest_accretion + row.ra.interest_accretion + row.csm.interest_accretion,
        )
        np.testing.assert_allclose(total.footing_error(), 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# 5. Locked-in rate drives CSM accretion
# ---------------------------------------------------------------------------


def test_csm_accretes_at_locked_in_rate():
    # Identical cash flows, different locked-in rates → different CSM accretion.
    low = build_movement_table(
        IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.03).measure_bba(), 0.03
    )
    high = build_movement_table(
        IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.08).measure_bba(), 0.08
    )
    low_accretion = sum(r.csm.interest_accretion for r in low.rows)
    high_accretion = sum(r.csm.interest_accretion for r in high.rows)
    assert high_accretion > low_accretion > 0.0


def test_csm_interest_matches_engine_roll_forward():
    # The movement table's CSM accretion is exactly the engine's monthly
    # accretion, re-bucketed into reporting periods (closed-form tie-out).
    result = IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.05).measure_bba()
    table = build_movement_table(result, 0.05)
    for row in table.rows:
        expected = result.csm_interest_accretion[row.start_month : row.end_month].sum()
        np.testing.assert_allclose(row.csm.interest_accretion, expected)
        expected_release = -result.csm_release[row.start_month : row.end_month].sum()
        np.testing.assert_allclose(row.csm.release, expected_release)


def test_per_cohort_table_preserves_locked_in_rate():
    manager = _multi_cohort_manager()
    tables = manager.cohort_movement_tables()
    for cohort, table in zip(manager.cohorts, tables, strict=True):
        assert table.issue_year == cohort.issue_year
        assert table.locked_in_rate == cohort.locked_in_rate
    aggregate = manager.aggregate_movement_table()
    assert aggregate.issue_year is None
    assert aggregate.locked_in_rate is None


# ---------------------------------------------------------------------------
# 6. Aggregate == Σ cohorts
# ---------------------------------------------------------------------------


def test_aggregate_equals_sum_of_cohort_movements():
    manager = _multi_cohort_manager()
    cohort_tables = manager.cohort_movement_tables()
    aggregate = manager.aggregate_movement_table()
    assert aggregate.n_periods == cohort_tables[0].n_periods
    for period in range(aggregate.n_periods):
        for field in ("opening", "new_business", "interest_accretion", "release", "closing"):
            for component in ("bel", "ra", "csm"):
                agg_val = getattr(getattr(aggregate.rows[period], component), field)
                cohort_sum = sum(
                    getattr(getattr(t.rows[period], component), field) for t in cohort_tables
                )
                np.testing.assert_allclose(agg_val, cohort_sum, atol=1e-9)


# ---------------------------------------------------------------------------
# 7. Reporting-period structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_per", "months_per_period", "expected_rows"),
    [(36, 12, 3), (30, 12, 3), (24, 12, 2), (13, 12, 2), (12, 12, 1), (24, 6, 4)],
)
def test_reporting_period_count(n_per, months_per_period, expected_rows):
    result = IFRS17Measurement(_make_gross_cashflow(n_per=n_per), discount_rate=0.05).measure_bba()
    table = build_movement_table(result, 0.05, months_per_period=months_per_period)
    assert table.n_periods == expected_rows
    assert table.rows[-1].end_month == n_per


# ---------------------------------------------------------------------------
# 8. Closed-form BEL movement
# ---------------------------------------------------------------------------


def test_closed_form_bel_release_equals_negative_total_fcf():
    # Constant net outflow c per month (onerous: claims only, no premium) over a
    # single reporting period. By the BEL recursion the per-month release equals
    # -FCF[t] = -c, so the period release is -c * T and new business is BEL[0].
    n_per = 6
    claim = 50.0
    cf = _make_gross_cashflow(
        n_per=n_per,
        monthly_premium=0.0,
        monthly_claim=claim,
        monthly_expense=0.0,
        monthly_lapse=0.0,
    )
    rate = 0.05
    result = IFRS17Measurement(cf, discount_rate=rate).measure_bba()
    table = build_movement_table(result, rate, months_per_period=n_per)
    assert table.n_periods == 1
    row = table.rows[0]

    # Release = -Σ FCF = -(claims) = -c * T (single reporting period).
    np.testing.assert_allclose(row.bel.release, -claim * n_per)
    # New business = initial BEL.
    np.testing.assert_allclose(row.bel.new_business, result.bel[0])
    # Interest = Σ BEL[t] * monthly accretion factor.
    m = (1.0 + rate) ** (1.0 / 12.0) - 1.0
    np.testing.assert_allclose(row.bel.interest_accretion, float((result.bel * m).sum()))
    # Closing = 0 (full run-off).
    np.testing.assert_allclose(row.bel.closing, 0.0, atol=1e-9)
    # And it foots.
    np.testing.assert_allclose(row.bel.footing_error(), 0.0, atol=1e-9)


def test_build_movement_table_is_returned_type():
    result = IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.05).measure_bba()
    table = build_movement_table(result, 0.05)
    assert isinstance(table, IFRS17MovementTable)
    assert table.n_periods == math.ceil(result.n_periods / 12)


# ---------------------------------------------------------------------------
# 8. Serialisation — to_dict() (Slice 3a: surfacing foundation)
# ---------------------------------------------------------------------------


def test_component_movement_to_dict_round_trips_fields():
    result = IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.05).measure_bba()
    table = build_movement_table(result, 0.05)
    comp = table.rows[0].bel
    d = comp.to_dict()
    assert set(d) == {
        "opening",
        "new_business",
        "interest_accretion",
        "release",
        "closing",
        "footing_error",
    }
    # Round-trip: the serialiser stores the identical floats (assert_allclose
    # rather than bare == per the repo's float-comparison rule).
    np.testing.assert_allclose(d["opening"], comp.opening)
    np.testing.assert_allclose(d["closing"], comp.closing)
    np.testing.assert_allclose(d["footing_error"], comp.footing_error())
    # Every value is a plain float (JSON-serialisable, no numpy scalars).
    for value in d.values():
        assert isinstance(value, float)


def test_movement_row_to_dict_has_four_columns_and_total_foots():
    result = IFRS17Measurement(_make_gross_cashflow(), discount_rate=0.05).measure_bba()
    row = build_movement_table(result, 0.05).rows[0]
    d = row.to_dict()
    assert d["period"] == row.period
    assert d["start_month"] == row.start_month
    assert d["end_month"] == row.end_month
    assert set(d) == {"period", "start_month", "end_month", "bel", "ra", "csm", "total"}
    # total == BEL + RA + CSM, field by field.
    for fld in ("opening", "new_business", "interest_accretion", "release", "closing"):
        np.testing.assert_allclose(d["total"][fld], d["bel"][fld] + d["ra"][fld] + d["csm"][fld])


def test_movement_table_to_dict_metadata_and_rows():
    manager = _multi_cohort_manager()
    cohort_table = manager.cohort_movement_tables()[0]
    d = cohort_table.to_dict()
    assert set(d) == {
        "months_per_period",
        "issue_year",
        "locked_in_rate",
        "n_periods",
        "max_footing_error",
        "rows",
    }
    assert d["months_per_period"] == cohort_table.months_per_period
    assert d["issue_year"] == cohort_table.issue_year
    np.testing.assert_allclose(d["locked_in_rate"], cohort_table.locked_in_rate)
    assert d["n_periods"] == cohort_table.n_periods
    assert len(d["rows"]) == cohort_table.n_periods
    # The serialised table foots (max footing residual ~ 0).
    np.testing.assert_allclose(d["max_footing_error"], 0.0, atol=1e-9)


def test_aggregate_table_to_dict_has_null_cohort_metadata():
    manager = _multi_cohort_manager()
    d = manager.aggregate_movement_table().to_dict()
    # The aggregate spans mixed cohorts: no single issue year / locked-in rate.
    assert d["issue_year"] is None
    assert d["locked_in_rate"] is None
    assert len(d["rows"]) > 0


def test_movement_table_to_dict_is_json_serialisable():
    import json

    manager = _multi_cohort_manager()
    payload = {
        "aggregate": manager.aggregate_movement_table().to_dict(),
        "cohorts": [t.to_dict() for t in manager.cohort_movement_tables()],
    }
    # Round-trips through JSON without a custom encoder.
    restored = json.loads(json.dumps(payload))
    np.testing.assert_allclose(restored["cohorts"][0]["rows"][0]["bel"]["opening"], 0.0)
