"""
Tests for IFRS 17 annual issue-year cohort aggregation (analytics/ifrs17.py).

Epic 2 (IFRS 17 movement table), Slice 1 — `IFRS17CohortManager`.

Verification:
1. Grouping: contracts with the same issue year fall into one cohort; distinct
   issue years produce distinct cohorts, ordered by issue year.
2. The locked-in discount rate is preserved per cohort (CSM accretes at the
   cohort's own rate, not a single global rate).
3. A single-contract cohort reproduces a direct `IFRS17Measurement.measure_bba()`.
4. Cohort aggregation is linear: two identical profitable contracts give exactly
   2x the BEL / RA / CSM of one (closed-form additivity anchor).
5. The manager's aggregate schedules equal the sum across cohorts.
6. Validation: empty input, non-GROSS basis, misaligned grids, and inconsistent
   per-cohort locked-in rate / ra_factor all raise PolarisValidationError.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.ifrs17 import (
    IFRS17CohortManager,
    IFRS17ContractInput,
    IFRS17Measurement,
)
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gross_cashflow(
    n_per: int = 24,
    monthly_premium: float = 100.0,
    monthly_claim: float = 10.0,
    monthly_expense: float = 5.0,
    monthly_lapse: float = 2.0,
    valuation_date: date | None = None,
    run_id: str = "ifrs17_cohort_test",
) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult for cohort testing."""
    if valuation_date is None:
        valuation_date = date(2025, 1, 1)
    premiums = np.full(n_per, monthly_premium, dtype=np.float64)
    claims = np.full(n_per, monthly_claim, dtype=np.float64)
    expenses = np.full(n_per, monthly_expense, dtype=np.float64)
    lapses = np.full(n_per, monthly_lapse, dtype=np.float64)
    net_cf = premiums - claims - lapses - expenses
    reserves = np.zeros(n_per, dtype=np.float64)
    return CashFlowResult(
        run_id=run_id,
        valuation_date=valuation_date,
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


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_same_issue_year_groups_into_one_cohort():
    mgr = IFRS17CohortManager([_contract(2020), _contract(2020)])
    assert mgr.n_cohorts == 1
    cohort = mgr.cohorts[0]
    assert cohort.issue_year == 2020
    assert cohort.n_contracts == 2


def test_distinct_issue_years_produce_distinct_cohorts_ordered():
    mgr = IFRS17CohortManager([_contract(2022), _contract(2020), _contract(2021)])
    assert mgr.n_cohorts == 3
    assert [c.issue_year for c in mgr.cohorts] == [2020, 2021, 2022]
    assert all(c.n_contracts == 1 for c in mgr.cohorts)


def test_locked_in_rate_preserved_per_cohort():
    mgr = IFRS17CohortManager(
        [_contract(2020, locked_in_rate=0.03), _contract(2021, locked_in_rate=0.06)]
    )
    by_year = {c.issue_year: c for c in mgr.cohorts}
    assert by_year[2020].locked_in_rate == pytest.approx(0.03)
    assert by_year[2021].locked_in_rate == pytest.approx(0.06)
    # Distinct locked-in rates => distinct CSM accretion => distinct CSM schedules.
    assert not np.allclose(by_year[2020].result.csm, by_year[2021].result.csm)


# ---------------------------------------------------------------------------
# Composition / additivity
# ---------------------------------------------------------------------------


def test_single_contract_cohort_matches_direct_measurement():
    cf = _make_gross_cashflow()
    direct = IFRS17Measurement(cf, discount_rate=0.04, ra_factor=0.05).measure_bba()

    mgr = IFRS17CohortManager(
        [
            IFRS17ContractInput(
                cashflows=cf,
                issue_date=date(2020, 3, 1),
                locked_in_rate=0.04,
                ra_factor=0.05,
            )
        ]
    )
    cohort = mgr.cohorts[0].result
    np.testing.assert_allclose(cohort.bel, direct.bel)
    np.testing.assert_allclose(cohort.risk_adjustment, direct.risk_adjustment)
    np.testing.assert_allclose(cohort.csm, direct.csm)
    assert cohort.initial_csm == pytest.approx(direct.initial_csm)


def test_cohort_of_two_identical_contracts_is_2x():
    one = IFRS17CohortManager([_contract(2020)])
    two = IFRS17CohortManager([_contract(2020), _contract(2020)])
    c1 = one.cohorts[0].result
    c2 = two.cohorts[0].result
    np.testing.assert_allclose(c2.bel, 2.0 * c1.bel)
    np.testing.assert_allclose(c2.risk_adjustment, 2.0 * c1.risk_adjustment)
    np.testing.assert_allclose(c2.csm, 2.0 * c1.csm)
    assert c2.initial_csm == pytest.approx(2.0 * c1.initial_csm)


def test_aggregate_schedules_equal_sum_across_cohorts():
    mgr = IFRS17CohortManager(
        [_contract(2020, locked_in_rate=0.03), _contract(2021, locked_in_rate=0.06)]
    )
    expected_bel = sum(c.result.bel for c in mgr.cohorts)
    expected_ra = sum(c.result.risk_adjustment for c in mgr.cohorts)
    expected_csm = sum(c.result.csm for c in mgr.cohorts)
    expected_liab = sum(c.result.insurance_liability for c in mgr.cohorts)
    np.testing.assert_allclose(mgr.aggregate_bel(), expected_bel)
    np.testing.assert_allclose(mgr.aggregate_ra(), expected_ra)
    np.testing.assert_allclose(mgr.aggregate_csm(), expected_csm)
    np.testing.assert_allclose(mgr.aggregate_insurance_liability(), expected_liab)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_contracts_raises():
    with pytest.raises(PolarisValidationError):
        IFRS17CohortManager([])


def test_non_gross_basis_raises():
    cf = _make_gross_cashflow()
    cf.basis = "NET"  # type: ignore[assignment]
    with pytest.raises(PolarisValidationError):
        IFRS17CohortManager(
            [IFRS17ContractInput(cashflows=cf, issue_date=date(2020, 1, 1), locked_in_rate=0.05)]
        )


def test_misaligned_projection_months_raises():
    short = _contract(2020, n_per=12)
    long = _contract(2020, n_per=24)
    with pytest.raises(PolarisValidationError):
        IFRS17CohortManager([short, long])


def test_inconsistent_locked_in_rate_within_cohort_raises():
    with pytest.raises(PolarisValidationError):
        IFRS17CohortManager(
            [_contract(2020, locked_in_rate=0.03), _contract(2020, locked_in_rate=0.06)]
        )


def test_inconsistent_ra_factor_within_cohort_raises():
    with pytest.raises(PolarisValidationError):
        IFRS17CohortManager([_contract(2020, ra_factor=0.04), _contract(2020, ra_factor=0.07)])
