"""
ExpenseAllowance model + computation primitive tests (Slice 1).

The allowance is a percentage of ceded premium with a first-year vs renewal
split and an optional sliding scale keyed to loss ratio. These tests verify:
1. Closed-form first-year / renewal allowance amounts.
2. Sliding-scale rate selection from loss-ratio bands.
3. Validation of mis-ordered / non-monotone sliding scales.
4. Edge cases (short horizons, zero premium, custom months_per_year).
"""

import numpy as np
import pytest
from pydantic import ValidationError

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.reinsurance.expense_allowance import (
    ExpenseAllowance,
    ExpenseAllowanceBand,
)

# ----------------------------------------------------------------------
# Flat first-year / renewal allowance — closed form
# ----------------------------------------------------------------------


def test_flat_allowance_first_year_and_renewal_closed_form():
    """$1,000/mo premium, 100% FY + 10% renewal → $12,000 yr1, $1,200/yr after."""
    allowance = ExpenseAllowance(first_year_pct=1.0, renewal_pct=0.10)
    premiums = np.full(36, 1_000.0, dtype=np.float64)  # 3 policy years

    result = allowance.compute_allowance(premiums)

    # Year 1 (months 0-11): 100% of $1,000 = $1,000 each
    np.testing.assert_allclose(result[:12], 1_000.0)
    # Years 2-3 (months 12-35): 10% of $1,000 = $100 each
    np.testing.assert_allclose(result[12:], 100.0)
    # Totals
    np.testing.assert_allclose(result[:12].sum(), 12_000.0)
    np.testing.assert_allclose(result[12:].sum(), 2_400.0)


def test_allowance_scales_linearly_with_premium():
    """Allowance is linear in premium: doubling the premium doubles the allowance."""
    allowance = ExpenseAllowance(first_year_pct=0.5, renewal_pct=0.05)
    p1 = np.full(24, 1_000.0, dtype=np.float64)
    p2 = p1 * 2.0
    np.testing.assert_allclose(
        allowance.compute_allowance(p2),
        allowance.compute_allowance(p1) * 2.0,
    )


@pytest.mark.parametrize(
    ("months_per_year", "n_periods", "expected_fy_count"),
    [(12, 36, 12), (12, 6, 6), (1, 5, 1), (4, 10, 4)],
)
def test_first_year_boundary_respects_months_per_year(
    months_per_year, n_periods, expected_fy_count
):
    """The first ``months_per_year`` periods (capped at horizon) get the FY rate."""
    allowance = ExpenseAllowance(
        first_year_pct=1.0, renewal_pct=0.0, months_per_year=months_per_year
    )
    premiums = np.ones(n_periods, dtype=np.float64)
    result = allowance.compute_allowance(premiums)
    # FY rate=1.0 → value 1.0; renewal rate=0.0 → value 0.0
    assert int(np.isclose(result, 1.0).sum()) == expected_fy_count
    assert int(np.isclose(result, 0.0).sum()) == n_periods - expected_fy_count


def test_zero_premium_yields_zero_allowance():
    allowance = ExpenseAllowance(first_year_pct=1.0, renewal_pct=0.5)
    result = allowance.compute_allowance(np.zeros(24, dtype=np.float64))
    np.testing.assert_allclose(result, 0.0)


def test_output_dtype_is_float64():
    allowance = ExpenseAllowance(first_year_pct=1.0, renewal_pct=0.1)
    result = allowance.compute_allowance(np.ones(12, dtype=np.float64))
    assert result.dtype == np.float64


# ----------------------------------------------------------------------
# Sliding scale — rate selection
# ----------------------------------------------------------------------


@pytest.fixture()
def sliding_allowance():
    """Better experience pays more: <=50% LR → 20%, <=70% → 10%, <=100% → 5%."""
    return ExpenseAllowance(
        first_year_pct=1.0,
        renewal_pct=0.10,  # ignored when sliding_scale present
        sliding_scale=[
            ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.20),
            ExpenseAllowanceBand(max_loss_ratio=0.70, allowance_pct=0.10),
            ExpenseAllowanceBand(max_loss_ratio=1.00, allowance_pct=0.05),
        ],
    )


@pytest.mark.parametrize(
    ("loss_ratio", "expected_rate"),
    [
        (0.0, 0.20),
        (0.50, 0.20),  # boundary inclusive
        (0.51, 0.10),
        (0.70, 0.10),
        (0.90, 0.05),
        (1.00, 0.05),
        (1.50, 0.05),  # above all bands → lowest band
    ],
)
def test_renewal_rate_for_loss_ratio(sliding_allowance, loss_ratio, expected_rate):
    assert sliding_allowance.renewal_rate_for_loss_ratio(loss_ratio) == pytest.approx(expected_rate)


def test_sliding_scale_uses_realized_loss_ratio_closed_form(sliding_allowance):
    """LR = claims/premiums = 60k/100k = 0.60 → renewal rate 10%."""
    # 20 periods. Premiums sum to 100k, claims sum to 60k → LR 0.60 → 10% renewal.
    premiums = np.full(20, 5_000.0, dtype=np.float64)  # sum 100k
    claims = np.full(20, 3_000.0, dtype=np.float64)  # sum 60k
    result = sliding_allowance.compute_allowance(premiums, claims)

    # Year 1 (months 0-11): 100% FY
    np.testing.assert_allclose(result[:12], 5_000.0)
    # Renewal (months 12-19): LR 0.60 selects 10% band → $500
    np.testing.assert_allclose(result[12:], 500.0)


def test_sliding_scale_better_experience_pays_more(sliding_allowance):
    """Lower loss ratio → strictly higher renewal allowance."""
    premiums = np.full(24, 1_000.0, dtype=np.float64)
    good = sliding_allowance.compute_allowance(premiums, np.full(24, 400.0))  # LR 0.40
    poor = sliding_allowance.compute_allowance(premiums, np.full(24, 900.0))  # LR 0.90
    # Renewal periods only (FY identical)
    assert good[12:].sum() > poor[12:].sum()


def test_sliding_scale_zero_premium_loss_ratio_is_zero(sliding_allowance):
    """Zero premium → loss ratio defined as 0 → best band, but premium 0 → allowance 0."""
    result = sliding_allowance.compute_allowance(
        np.zeros(24, dtype=np.float64), np.zeros(24, dtype=np.float64)
    )
    np.testing.assert_allclose(result, 0.0)


def test_sliding_scale_requires_claims(sliding_allowance):
    with pytest.raises(PolarisValidationError, match="requires ceded_claims"):
        sliding_allowance.compute_allowance(np.ones(12, dtype=np.float64))


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


def test_sliding_scale_must_be_ascending_threshold():
    with pytest.raises(PolarisValidationError, match="ascending"):
        ExpenseAllowance(
            first_year_pct=1.0,
            renewal_pct=0.1,
            sliding_scale=[
                ExpenseAllowanceBand(max_loss_ratio=0.70, allowance_pct=0.10),
                ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.20),
            ],
        )


def test_sliding_scale_must_have_distinct_thresholds():
    with pytest.raises(PolarisValidationError, match="distinct"):
        ExpenseAllowance(
            first_year_pct=1.0,
            renewal_pct=0.1,
            sliding_scale=[
                ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.20),
                ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.10),
            ],
        )


def test_sliding_scale_must_be_monotone_non_increasing_rate():
    """Worse experience paying MORE inverts the incentive → rejected."""
    with pytest.raises(PolarisValidationError, match="monotone non-increasing"):
        ExpenseAllowance(
            first_year_pct=1.0,
            renewal_pct=0.1,
            sliding_scale=[
                ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.05),
                ExpenseAllowanceBand(max_loss_ratio=0.70, allowance_pct=0.20),
            ],
        )


def test_equal_rate_bands_are_allowed():
    """Flat (non-increasing) bands are permitted — a degenerate sliding scale."""
    allowance = ExpenseAllowance(
        first_year_pct=1.0,
        renewal_pct=0.1,
        sliding_scale=[
            ExpenseAllowanceBand(max_loss_ratio=0.50, allowance_pct=0.10),
            ExpenseAllowanceBand(max_loss_ratio=0.70, allowance_pct=0.10),
        ],
    )
    assert allowance.renewal_rate_for_loss_ratio(0.60) == pytest.approx(0.10)


def test_premiums_must_be_one_dimensional():
    allowance = ExpenseAllowance(first_year_pct=1.0, renewal_pct=0.1)
    with pytest.raises(PolarisValidationError, match="1-D"):
        allowance.compute_allowance(np.ones((4, 3), dtype=np.float64))


def test_negative_rate_rejected_by_field_constraint():
    with pytest.raises(ValidationError):
        ExpenseAllowance(first_year_pct=-0.1, renewal_pct=0.1)


def test_model_is_frozen():
    allowance = ExpenseAllowance(first_year_pct=1.0, renewal_pct=0.1)
    with pytest.raises(ValidationError):  # frozen-instance error
        allowance.first_year_pct = 0.5
