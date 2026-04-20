"""Tests for InforceBlock.from_csv() classmethod."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock


def _write_synthetic_csv(path: Path, n: int = 5) -> None:
    """Write a minimal synthetic inforce CSV for testing."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "policy_id": f"TEST_{i:04d}",
                "issue_age": 35 + i,
                "attained_age": 40 + i,
                "sex": "M" if i % 2 == 0 else "F",
                "smoker_status": "NS",
                "underwriting_class": "STANDARD",
                "face_amount": 500_000.0,
                "annual_premium": 2000.0 + i * 100,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 60,
                "reinsurance_cession_pct": 0.50,
                "issue_date": "2020-01-01",
                "valuation_date": "2025-01-01",
            }
        )
    pl.DataFrame(rows).write_csv(path)


class TestInforceBlockFromCSV:
    """Tests for loading InforceBlock from normalised CSV."""

    def test_basic_load(self, tmp_path):
        """Load a basic CSV and verify policy count."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=10)
        block = InforceBlock.from_csv(csv_path)
        assert block.n_policies == 10

    def test_policy_attributes(self, tmp_path):
        """Loaded policies have correct attribute values."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=3)
        block = InforceBlock.from_csv(csv_path)
        assert block.policies[0].policy_id == "TEST_0000"
        assert block.policies[0].issue_age == 35
        assert block.policies[0].attained_age == 40
        np.testing.assert_allclose(block.policies[0].face_amount, 500_000.0)

    def test_vectorized_access(self, tmp_path):
        """Vectorized properties work on loaded block."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=5)
        block = InforceBlock.from_csv(csv_path)
        assert block.face_amount_vec.shape == (5,)
        assert block.attained_age_vec.dtype == np.int32
        np.testing.assert_allclose(block.total_face_amount(), 2_500_000.0)

    def test_block_id(self, tmp_path):
        """Block ID is passed through."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=2)
        block = InforceBlock.from_csv(csv_path, block_id="DEAL-001")
        assert block.block_id == "DEAL-001"

    def test_file_not_found(self):
        """Missing CSV raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            InforceBlock.from_csv(Path("/nonexistent/block.csv"))

    def test_missing_columns_raises(self, tmp_path):
        """Missing required columns raise PolarisValidationError."""
        csv_path = tmp_path / "bad.csv"
        pl.DataFrame({"policy_id": ["A"], "face_amount": [100000]}).write_csv(csv_path)
        with pytest.raises(PolarisValidationError, match="Missing required"):
            InforceBlock.from_csv(csv_path)

    def test_round_trip_large_block(self, tmp_path):
        """Round-trip: write CSV with many policies → load InforceBlock."""
        csv_path = tmp_path / "large.csv"
        _write_synthetic_csv(csv_path, n=50)
        block = InforceBlock.from_csv(csv_path)
        assert block.n_policies == 50
        assert block.total_face_amount() > 0

    def test_sex_enum_mapping(self, tmp_path):
        """Sex values map correctly to Sex enum."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=4)
        block = InforceBlock.from_csv(csv_path)
        from polaris_re.core.policy import Sex

        assert block.policies[0].sex == Sex.MALE
        assert block.policies[1].sex == Sex.FEMALE

    def test_optional_fields_default(self, tmp_path):
        """Optional fields get defaults when not in CSV."""
        csv_path = tmp_path / "minimal.csv"
        rows = [
            {
                "policy_id": "P1",
                "issue_age": 35,
                "attained_age": 40,
                "sex": "M",
                "smoker_status": "NS",
                "face_amount": 500000,
                "annual_premium": 2000,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 60,
                "issue_date": "2020-01-01",
                "valuation_date": "2025-01-01",
            }
        ]
        pl.DataFrame(rows).write_csv(csv_path)
        block = InforceBlock.from_csv(csv_path)
        assert block.policies[0].underwriting_class == "STANDARD"
        assert block.policies[0].reinsurance_cession_pct is None

    def test_substandard_rating_defaults_when_columns_missing(self, tmp_path):
        """CSVs without rating columns load with standard defaults (ADR-042)."""
        csv_path = tmp_path / "block.csv"
        _write_synthetic_csv(csv_path, n=3)
        block = InforceBlock.from_csv(csv_path)
        assert all(p.mortality_multiplier == 1.0 for p in block.policies)
        assert all(p.flat_extra_per_1000 == 0.0 for p in block.policies)

    def test_substandard_rating_read_from_csv(self, tmp_path):
        """CSVs with rating columns load the values through to Policy (ADR-042)."""
        csv_path = tmp_path / "rated.csv"
        rows = [
            {
                "policy_id": "RATED_01",
                "issue_age": 45,
                "attained_age": 45,
                "sex": "M",
                "smoker_status": "NS",
                "underwriting_class": "SUBSTANDARD",
                "face_amount": 1_000_000,
                "annual_premium": 6_000,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 0,
                "reinsurance_cession_pct": 0.5,
                "mortality_multiplier": 2.5,
                "flat_extra_per_1000": 7.5,
                "issue_date": "2025-01-01",
                "valuation_date": "2025-01-01",
            }
        ]
        pl.DataFrame(rows).write_csv(csv_path)
        block = InforceBlock.from_csv(csv_path)
        np.testing.assert_allclose(block.policies[0].mortality_multiplier, 2.5)
        np.testing.assert_allclose(block.policies[0].flat_extra_per_1000, 7.5)
