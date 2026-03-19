"""Tests for cedant inforce data ingestion pipeline."""

from pathlib import Path

import polars as pl
import pytest
import yaml

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.utils.ingestion import (
    IngestConfig,
    ingest_cedant_data,
    validate_inforce_df,
)


def _write_cedant_csv(path: Path) -> None:
    """Write a mock cedant CSV with non-standard column names."""
    rows = [
        {
            "POLNUM": "C001",
            "AGE_AT_ISSUE": 35,
            "CURRENT_AGE": 40,
            "GENDER": "MALE",
            "TOBACCO": "N",
            "UW_CLASS": "PREFERRED",
            "SUM_ASSURED": 500_000,
            "ANNUAL_PREM": 2000.0,
            "PLAN_CODE": "T20",
            "TERM_YEARS": 20,
            "MONTHS_IF": 60,
            "CESSION": 0.50,
            "ISSUE_DT": "2020-01-01",
            "VAL_DT": "2025-01-01",
        },
        {
            "POLNUM": "C002",
            "AGE_AT_ISSUE": 45,
            "CURRENT_AGE": 50,
            "GENDER": "FEMALE",
            "TOBACCO": "Y",
            "UW_CLASS": "STANDARD",
            "SUM_ASSURED": 300_000,
            "ANNUAL_PREM": 3500.0,
            "PLAN_CODE": "T10",
            "TERM_YEARS": 10,
            "MONTHS_IF": 24,
            "CESSION": 0.75,
            "ISSUE_DT": "2023-01-01",
            "VAL_DT": "2025-01-01",
        },
    ]
    pl.DataFrame(rows).write_csv(path)


def _write_mapping_yaml(path: Path) -> None:
    """Write a mapping config YAML for the mock cedant CSV."""
    config = {
        "source_format": {"delimiter": ",", "date_format": "%Y-%m-%d"},
        "column_mapping": {
            "policy_id": "POLNUM",
            "issue_age": "AGE_AT_ISSUE",
            "attained_age": "CURRENT_AGE",
            "sex": "GENDER",
            "smoker_status": "TOBACCO",
            "underwriting_class": "UW_CLASS",
            "face_amount": "SUM_ASSURED",
            "annual_premium": "ANNUAL_PREM",
            "product_type": "PLAN_CODE",
            "policy_term": "TERM_YEARS",
            "duration_inforce": "MONTHS_IF",
            "reinsurance_cession_pct": "CESSION",
            "issue_date": "ISSUE_DT",
            "valuation_date": "VAL_DT",
        },
        "code_translations": {
            "sex": {"MALE": "M", "FEMALE": "F"},
            "smoker_status": {"Y": "S", "N": "NS"},
            "product_type": {"T10": "TERM", "T20": "TERM"},
        },
        "defaults": {},
    }
    with open(path, "w") as f:
        yaml.safe_dump(config, f)


class TestIngestConfig:
    """Tests for IngestConfig loading."""

    def test_from_yaml(self, tmp_path):
        """Loads config from YAML file."""
        yaml_path = tmp_path / "mapping.yaml"
        _write_mapping_yaml(yaml_path)
        config = IngestConfig.from_yaml(yaml_path)
        assert "policy_id" in config.column_mapping
        assert config.column_mapping["policy_id"] == "POLNUM"

    def test_from_yaml_not_found(self):
        """Missing YAML raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            IngestConfig.from_yaml(Path("/nonexistent/config.yaml"))

    def test_from_dict(self):
        """Constructs config from a plain dict."""
        data = {
            "column_mapping": {"policy_id": "ID", "face_amount": "FA"},
        }
        config = IngestConfig.from_dict(data)
        assert config.column_mapping["policy_id"] == "ID"


class TestIngestCedantData:
    """Tests for the ingestion pipeline."""

    def test_basic_ingestion(self, tmp_path):
        """Ingests and normalises a cedant CSV."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)

        assert len(df) == 2
        assert "policy_id" in df.columns
        assert "face_amount" in df.columns

    def test_column_rename(self, tmp_path):
        """Source columns are renamed to Polaris RE names."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)

        assert "POLNUM" not in df.columns
        assert "policy_id" in df.columns

    def test_code_translation(self, tmp_path):
        """Code translations are applied (MALE→M, Y→S)."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)

        sex_values = df["sex"].to_list()
        assert "M" in sex_values
        assert "F" in sex_values
        assert "MALE" not in sex_values

        smoker_values = df["smoker_status"].to_list()
        assert "NS" in smoker_values
        assert "S" in smoker_values

    def test_product_type_translation(self, tmp_path):
        """Product type codes are translated (T10→TERM, T20→TERM)."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)

        product_types = df["product_type"].to_list()
        assert all(pt == "TERM" for pt in product_types)

    def test_defaults_applied(self, tmp_path):
        """Default values are applied for missing columns."""
        # Write CSV without underwriting_class
        csv_path = tmp_path / "simple.csv"
        rows = [{
            "policy_id": "P1",
            "issue_age": 35,
            "attained_age": 40,
            "sex": "M",
            "smoker_status": "NS",
            "face_amount": 500000,
            "annual_premium": 2000,
            "product_type": "TERM",
            "duration_inforce": 60,
            "issue_date": "2020-01-01",
            "valuation_date": "2025-01-01",
        }]
        pl.DataFrame(rows).write_csv(csv_path)

        config = IngestConfig(
            column_mapping={},  # no renaming needed — already normalised
            defaults={"underwriting_class": "STANDARD", "reinsurance_cession_pct": 0.50},
        )
        df = ingest_cedant_data(csv_path, config)
        assert "underwriting_class" in df.columns

    def test_file_not_found(self, tmp_path):
        """Missing input file raises FileNotFoundError."""
        config = IngestConfig(column_mapping={})
        with pytest.raises(FileNotFoundError):
            ingest_cedant_data(Path("/nonexistent.csv"), config)

    def test_missing_required_columns(self, tmp_path):
        """Missing required columns raise PolarisValidationError."""
        csv_path = tmp_path / "incomplete.csv"
        pl.DataFrame({"col_a": [1], "col_b": [2]}).write_csv(csv_path)
        config = IngestConfig(column_mapping={})
        with pytest.raises(PolarisValidationError, match="Required columns missing"):
            ingest_cedant_data(csv_path, config)

    def test_unsupported_file_type(self, tmp_path):
        """Unsupported file type raises PolarisValidationError."""
        txt_path = tmp_path / "data.txt"
        txt_path.write_text("a,b\n1,2\n")
        config = IngestConfig(column_mapping={})
        with pytest.raises(PolarisValidationError, match="Unsupported"):
            ingest_cedant_data(txt_path, config)


class TestValidateInforceDf:
    """Tests for data quality validation."""

    def test_valid_data(self, tmp_path):
        """Valid data produces no errors."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)
        report = validate_inforce_df(df)

        assert report.is_valid
        assert report.n_policies == 2
        assert report.total_face_amount == 800_000.0

    def test_empty_dataframe(self):
        """Empty DataFrame produces an error."""
        df = pl.DataFrame({"policy_id": [], "face_amount": []})
        report = validate_inforce_df(df)
        assert not report.is_valid
        assert "Empty" in report.errors[0]

    def test_duplicate_policy_ids(self):
        """Duplicate policy IDs produce a warning."""
        df = pl.DataFrame({
            "policy_id": ["P1", "P1"],
            "attained_age": [40, 45],
            "face_amount": [100_000, 200_000],
            "sex": ["M", "F"],
            "smoker_status": ["NS", "S"],
        })
        report = validate_inforce_df(df)
        assert any("duplicate" in w.lower() for w in report.warnings)

    def test_negative_age(self):
        """Negative age produces an error."""
        df = pl.DataFrame({
            "policy_id": ["P1"],
            "attained_age": [-5],
            "face_amount": [100_000],
        })
        report = validate_inforce_df(df)
        assert any("Negative" in e for e in report.errors)

    def test_sex_split(self, tmp_path):
        """Sex split is computed correctly."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)
        report = validate_inforce_df(df)

        assert report.sex_split.get("M", 0) == 1
        assert report.sex_split.get("F", 0) == 1

    def test_mean_age(self, tmp_path):
        """Mean age is computed correctly."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)

        config = IngestConfig.from_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, config)
        report = validate_inforce_df(df)

        assert report.mean_age == pytest.approx(45.0, abs=0.1)
