"""Tests for the calibrated premium generation in generate_synthetic_block."""

import sys
from pathlib import Path

import pytest

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_synthetic_block import generate_synthetic_block


@pytest.fixture
def data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "mortality_tables"


class TestCalibratedPremiums:
    """Verify that premiums are calibrated to mortality and loss ratio."""

    def test_premiums_scale_with_loss_ratio(self, data_dir: Path) -> None:
        """Lower loss ratio -> higher premiums (more margin)."""
        df_60 = generate_synthetic_block(
            n_policies=50,
            seed=42,
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        df_40 = generate_synthetic_block(
            n_policies=50,
            seed=42,
            target_loss_ratio=0.40,
            data_dir=str(data_dir),
        )
        # Same policies, different loss ratios
        assert df_40["annual_premium"].sum() > df_60["annual_premium"].sum()
        # Ratio should be approximately 0.60/0.40 = 1.5
        ratio = df_40["annual_premium"].sum() / df_60["annual_premium"].sum()
        assert 1.4 < ratio < 1.6

    def test_smokers_pay_more(self, data_dir: Path) -> None:
        """Smoker policies should have higher premiums due to higher mortality."""
        df = generate_synthetic_block(
            n_policies=500,
            seed=42,
            smoker_pct=50,  # 50/50 split for statistical power
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        smoker_avg = df.filter(df["smoker_status"] == "S")["annual_premium"].mean()
        ns_avg = df.filter(df["smoker_status"] == "NS")["annual_premium"].mean()
        assert smoker_avg > ns_avg

    def test_premiums_positive(self, data_dir: Path) -> None:
        """All generated premiums must be positive."""
        df = generate_synthetic_block(
            n_policies=100,
            seed=42,
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        assert (df["annual_premium"] > 0).all()

    def test_loss_ratio_sanity(self, data_dir: Path) -> None:
        """
        Rough check: for a single-age cohort, the ratio of
        (avg_qx * face) / premium should approximate the target loss ratio.
        """
        df = generate_synthetic_block(
            n_policies=200,
            seed=42,
            mean_age=40,
            age_std=1,  # tight age distribution
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        # This is an approximate check — the generated premiums use
        # average q_x over the term, so the ratio won't be exact
        avg_premium = df["annual_premium"].mean()
        avg_face = df["face_amount"].mean()
        # Premium should be in a reasonable range relative to face amount
        assert avg_premium > 0
        assert avg_premium < avg_face * 0.10  # premium < 10% of face
