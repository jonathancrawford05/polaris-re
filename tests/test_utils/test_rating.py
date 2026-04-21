"""Tests for block-level substandard-rating composition helper."""

from datetime import date

import pytest

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.utils.rating import rating_composition


def _make_policy(
    policy_id: str,
    face: float,
    multiplier: float = 1.0,
    flat_extra: float = 0.0,
) -> Policy:
    """Build a minimal term-life Policy for rating tests."""
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=45,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=1000.0,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=60,
        mortality_multiplier=multiplier,
        flat_extra_per_1000=flat_extra,
        issue_date=date(2021, 1, 1),
        valuation_date=date(2026, 1, 1),
    )


class TestRatingComposition:
    """Contract tests for rating_composition()."""

    def test_all_standard_block_reports_zero_rated(self):
        """An all-standard block reports 0 rated and a weighted multiplier of 1.0."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face=500_000),
                _make_policy("P2", face=1_000_000),
            ]
        )
        summary = rating_composition(block)
        assert summary["n_policies"] == 2
        assert summary["n_rated"] == 0
        assert summary["pct_rated_by_count"] == pytest.approx(0.0)
        assert summary["pct_rated_by_face"] == pytest.approx(0.0)
        assert summary["face_weighted_mean_multiplier"] == pytest.approx(1.0)
        assert summary["max_multiplier"] == pytest.approx(1.0)
        assert summary["max_flat_extra_per_1000"] == pytest.approx(0.0)

    def test_counts_multiplier_rated_policies(self):
        """Policies with multiplier > 1.0 are counted as rated."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face=500_000),
                _make_policy("P2", face=500_000, multiplier=2.0),
                _make_policy("P3", face=500_000, multiplier=4.0),
            ]
        )
        summary = rating_composition(block)
        assert summary["n_rated"] == 2
        assert summary["pct_rated_by_count"] == pytest.approx(2 / 3)
        # (1.0*500k + 2.0*500k + 4.0*500k) / 1.5M = 7/3 ≈ 2.3333
        assert summary["face_weighted_mean_multiplier"] == pytest.approx(7.0 / 3.0)
        assert summary["max_multiplier"] == pytest.approx(4.0)

    def test_counts_flat_extra_only_policies(self):
        """Policies with flat_extra > 0 (and multiplier=1.0) are still rated."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face=500_000),
                _make_policy("P2", face=500_000, flat_extra=5.0),
            ]
        )
        summary = rating_composition(block)
        assert summary["n_rated"] == 1
        assert summary["pct_rated_by_count"] == pytest.approx(0.5)
        # Multiplier average is still 1.0 because flat-extra policies kept multiplier=1.0
        assert summary["face_weighted_mean_multiplier"] == pytest.approx(1.0)
        assert summary["max_flat_extra_per_1000"] == pytest.approx(5.0)

    def test_face_weighting_is_face_not_count(self):
        """pct_rated_by_face uses face-amount weighting, not policy count."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face=900_000),
                _make_policy("P2", face=100_000, multiplier=2.0),
            ]
        )
        summary = rating_composition(block)
        assert summary["pct_rated_by_count"] == pytest.approx(0.5)
        # Only 100k of 1m face is rated → 10%
        assert summary["pct_rated_by_face"] == pytest.approx(0.1)

    def test_combined_multiplier_and_flat_extra_flagged_once(self):
        """A policy with both a multiplier>1 and flat_extra>0 counts once."""
        block = InforceBlock(
            policies=[
                _make_policy("P1", face=500_000, multiplier=2.0, flat_extra=5.0),
            ]
        )
        summary = rating_composition(block)
        assert summary["n_rated"] == 1
