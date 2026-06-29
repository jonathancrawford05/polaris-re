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


# ----------------------------------------------------------------------
# Slice 2 — first-year mapping for inforce blocks (duration-aware)
# ----------------------------------------------------------------------

from datetime import date  # noqa: E402

from polaris_re.core.inforce import InforceBlock  # noqa: E402
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus  # noqa: E402


def _policy(policy_id: str, issue_year: int, face: float = 1_000_000.0) -> Policy:
    """Term policy issued on 1 Jan of ``issue_year``, valued 2025-01-01."""
    val = date(2025, 1, 1)
    months = (val.year - issue_year) * 12
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=40 + months // 12,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=12_000.0,
        product_type=ProductType.TERM,
        policy_term=30,
        duration_inforce=months,
        issue_date=date(issue_year, 1, 1),
        valuation_date=val,
    )


def test_first_year_fraction_explicit_blend_matches_closed_form():
    """rate[t] = f[t]*fy + (1-f[t])*renewal, applied to premium."""
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    premiums = np.full(6, 1_000.0, dtype=np.float64)
    fraction = np.array([1.0, 1.0, 0.5, 0.5, 0.0, 0.0], dtype=np.float64)

    result = allowance.compute_allowance(premiums, first_year_fraction=fraction)

    expected_rates = np.array([0.80, 0.80, 0.45, 0.45, 0.10, 0.10])
    np.testing.assert_allclose(result, premiums * expected_rates)


def test_first_year_fraction_all_ones_then_zeros_recovers_default():
    """A new-business-shaped fraction reproduces the default projection split."""
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    premiums = np.full(24, 1_000.0, dtype=np.float64)
    fraction = np.concatenate([np.ones(12), np.zeros(12)])

    blended = allowance.compute_allowance(premiums, first_year_fraction=fraction)
    default = allowance.compute_allowance(premiums)
    np.testing.assert_allclose(blended, default)


def test_first_year_fraction_shape_mismatch_rejected():
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    with pytest.raises(PolarisValidationError, match="first_year_fraction shape"):
        allowance.compute_allowance(
            np.ones(6, dtype=np.float64), first_year_fraction=np.ones(5, dtype=np.float64)
        )


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_first_year_fraction_out_of_range_rejected(bad):
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    fraction = np.full(6, bad, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match=r"\[0, 1\]"):
        allowance.compute_allowance(np.ones(6, dtype=np.float64), first_year_fraction=fraction)


def test_block_fraction_new_business_is_one_then_zero():
    """A brand-new block: f[t]=1 for the first policy year, 0 after."""
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    block = InforceBlock(policies=[_policy("N", 2025)])  # duration 0
    fraction = allowance.first_year_fraction_for_block(block, 24, date(2025, 1, 1))
    np.testing.assert_allclose(fraction[:12], 1.0)
    np.testing.assert_allclose(fraction[12:], 0.0)


def test_block_fraction_mid_duration_is_all_zero():
    """A 5-years-inforce block is entirely past policy year one → renewal only."""
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    block = InforceBlock(policies=[_policy("O", 2020)])  # duration 60 months
    fraction = allowance.first_year_fraction_for_block(block, 24, date(2025, 1, 1))
    np.testing.assert_allclose(fraction, 0.0)


def test_block_fraction_is_face_weighted_for_mixed_block():
    """Equal-face new + mid-duration → f[t]=0.5 in year one, 0 after."""
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    block = InforceBlock(policies=[_policy("N", 2025), _policy("O", 2020)])
    fraction = allowance.first_year_fraction_for_block(block, 24, date(2025, 1, 1))
    np.testing.assert_allclose(fraction[:12], 0.5)
    np.testing.assert_allclose(fraction[12:], 0.0)


def test_block_fraction_face_weighting_is_not_equal_weighting():
    """A larger new-business face pulls the year-one fraction above 0.5."""
    allowance = ExpenseAllowance(first_year_pct=0.8, renewal_pct=0.1)
    block = InforceBlock(
        policies=[_policy("N", 2025, face=3_000_000.0), _policy("O", 2020, face=1_000_000.0)]
    )
    fraction = allowance.first_year_fraction_for_block(block, 6, date(2025, 1, 1))
    np.testing.assert_allclose(fraction, 0.75)


def test_block_fraction_inforce_mapping_fixes_overstatement():
    """The Slice-2 mapping recovers renewal-only allowance on a mid-duration block.

    Reproduces the premise the routine verified: the Slice-1 primitive applied
    naively to an inforce stream overstates the allowance by charging the
    first-year rate; the duration-aware fraction removes it.
    """
    allowance = ExpenseAllowance(first_year_pct=0.80, renewal_pct=0.10)
    premiums = np.full(24, 1_000.0, dtype=np.float64)
    block = InforceBlock(policies=[_policy("O", 2020)])  # mid-duration

    naive = allowance.compute_allowance(premiums)
    fraction = allowance.first_year_fraction_for_block(block, 24, date(2025, 1, 1))
    mapped = allowance.compute_allowance(premiums, first_year_fraction=fraction)

    np.testing.assert_allclose(mapped, premiums * 0.10)  # all renewal
    assert naive.sum() > mapped.sum()  # naive overstates
