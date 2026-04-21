"""Tests for cedant inforce data ingestion pipeline."""

from pathlib import Path

import polars as pl
import pytest
import yaml

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.utils.ingestion import (
    IngestConfig,
    RatingCodeEntry,
    RatingCodeMap,
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
                "duration_inforce": 60,
                "issue_date": "2020-01-01",
                "valuation_date": "2025-01-01",
            }
        ]
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
        df = pl.DataFrame(
            {
                "policy_id": ["P1", "P1"],
                "attained_age": [40, 45],
                "face_amount": [100_000, 200_000],
                "sex": ["M", "F"],
                "smoker_status": ["NS", "S"],
            }
        )
        report = validate_inforce_df(df)
        assert any("duplicate" in w.lower() for w in report.warnings)

    def test_negative_age(self):
        """Negative age produces an error."""
        df = pl.DataFrame(
            {
                "policy_id": ["P1"],
                "attained_age": [-5],
                "face_amount": [100_000],
            }
        )
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


def _write_rated_cedant_csv(path: Path) -> None:
    """Write a mock cedant CSV carrying a rating-code column."""
    rows = [
        {
            "policy_id": "R001",
            "issue_age": 30,
            "attained_age": 35,
            "sex": "M",
            "smoker_status": "NS",
            "underwriting_class": "STANDARD",
            "face_amount": 500_000,
            "annual_premium": 500.0,
            "product_type": "TERM",
            "policy_term": 20,
            "duration_inforce": 60,
            "issue_date": "2021-01-01",
            "valuation_date": "2026-01-01",
            "RATE_CLASS": "STD",
        },
        {
            "policy_id": "R002",
            "issue_age": 40,
            "attained_age": 45,
            "sex": "F",
            "smoker_status": "NS",
            "underwriting_class": "SUBSTANDARD",
            "face_amount": 1_000_000,
            "annual_premium": 2000.0,
            "product_type": "TERM",
            "policy_term": 20,
            "duration_inforce": 60,
            "issue_date": "2021-01-01",
            "valuation_date": "2026-01-01",
            "RATE_CLASS": "TBL2",
        },
        {
            "policy_id": "R003",
            "issue_age": 50,
            "attained_age": 55,
            "sex": "M",
            "smoker_status": "S",
            "underwriting_class": "SUBSTANDARD",
            "face_amount": 250_000,
            "annual_premium": 1500.0,
            "product_type": "TERM",
            "policy_term": 10,
            "duration_inforce": 36,
            "issue_date": "2023-01-01",
            "valuation_date": "2026-01-01",
            "RATE_CLASS": "FE5",
        },
        {
            "policy_id": "R004",
            "issue_age": 35,
            "attained_age": 40,
            "sex": "M",
            "smoker_status": "NS",
            "underwriting_class": "STANDARD",
            "face_amount": 750_000,
            "annual_premium": 1200.0,
            "product_type": "TERM",
            "policy_term": 20,
            "duration_inforce": 48,
            "issue_date": "2022-01-01",
            "valuation_date": "2026-01-01",
            "RATE_CLASS": "UNKNOWN_CODE",
        },
    ]
    pl.DataFrame(rows).write_csv(path)


def _rating_config(include_rating_code_map: bool = True) -> IngestConfig:
    """Build an IngestConfig for rated-cedant CSVs."""
    column_mapping = {
        "policy_id": "policy_id",
        "issue_age": "issue_age",
        "attained_age": "attained_age",
        "sex": "sex",
        "smoker_status": "smoker_status",
        "underwriting_class": "underwriting_class",
        "face_amount": "face_amount",
        "annual_premium": "annual_premium",
        "product_type": "product_type",
        "policy_term": "policy_term",
        "duration_inforce": "duration_inforce",
        "issue_date": "issue_date",
        "valuation_date": "valuation_date",
        "rating_code": "RATE_CLASS",
    }
    rating_map = (
        RatingCodeMap(
            source_column="rating_code",
            codes={
                "STD": RatingCodeEntry(mortality_multiplier=1.0, flat_extra_per_1000=0.0),
                "TBL2": RatingCodeEntry(mortality_multiplier=2.0, flat_extra_per_1000=0.0),
                "TBL4": RatingCodeEntry(mortality_multiplier=4.0, flat_extra_per_1000=0.0),
                "FE5": RatingCodeEntry(mortality_multiplier=1.0, flat_extra_per_1000=5.0),
                "TBL2_FE5": RatingCodeEntry(mortality_multiplier=2.0, flat_extra_per_1000=5.0),
            },
        )
        if include_rating_code_map
        else None
    )
    return IngestConfig(
        column_mapping=column_mapping,
        rating_code_map=rating_map,
    )


class TestRatingCodeMap:
    """Tests for the substandard rating-code registry (ADR-044)."""

    def test_derives_multiplier_from_rating_code(self, tmp_path):
        """TBL2 rating code yields mortality_multiplier=2.0 after ingestion."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())

        assert "mortality_multiplier" in df.columns
        rows = {row["policy_id"]: row for row in df.iter_rows(named=True)}
        assert rows["R001"]["mortality_multiplier"] == pytest.approx(1.0)
        assert rows["R002"]["mortality_multiplier"] == pytest.approx(2.0)
        assert rows["R003"]["mortality_multiplier"] == pytest.approx(1.0)
        # Unknown codes fall back to the default entry
        assert rows["R004"]["mortality_multiplier"] == pytest.approx(1.0)

    def test_derives_flat_extra_from_rating_code(self, tmp_path):
        """FE5 rating code yields flat_extra_per_1000=5.0 after ingestion."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())

        assert "flat_extra_per_1000" in df.columns
        rows = {row["policy_id"]: row for row in df.iter_rows(named=True)}
        assert rows["R001"]["flat_extra_per_1000"] == pytest.approx(0.0)
        assert rows["R002"]["flat_extra_per_1000"] == pytest.approx(0.0)
        assert rows["R003"]["flat_extra_per_1000"] == pytest.approx(5.0)
        assert rows["R004"]["flat_extra_per_1000"] == pytest.approx(0.0)

    def test_rating_code_map_absent_leaves_frame_unchanged(self, tmp_path):
        """Without a rating_code_map the derived columns are not added."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config(include_rating_code_map=False))

        # Without the map, ingestion does not create the multiplier columns.
        assert "mortality_multiplier" not in df.columns
        assert "flat_extra_per_1000" not in df.columns

    def test_custom_default_applied_for_unknown_codes(self, tmp_path):
        """Custom ``default`` is returned for codes not present in ``codes``."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)
        cfg = _rating_config()
        cfg_with_default = IngestConfig(
            column_mapping=cfg.column_mapping,
            rating_code_map=RatingCodeMap(
                source_column="rating_code",
                codes=cfg.rating_code_map.codes,  # type: ignore[union-attr]
                default=RatingCodeEntry(mortality_multiplier=1.5, flat_extra_per_1000=0.0),
            ),
        )
        df = ingest_cedant_data(csv_path, cfg_with_default)

        rows = {row["policy_id"]: row for row in df.iter_rows(named=True)}
        # Known code is unaffected
        assert rows["R002"]["mortality_multiplier"] == pytest.approx(2.0)
        # Unknown code now uses the custom default
        assert rows["R004"]["mortality_multiplier"] == pytest.approx(1.5)

    def test_rating_code_round_trips_into_inforce_block(self, tmp_path):
        """Ingested rated CSV loads into InforceBlock with correct rating vecs."""
        from polaris_re.core.inforce import InforceBlock

        csv_path = tmp_path / "rated.csv"
        normalised_path = tmp_path / "normalised.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())
        df.write_csv(normalised_path)

        block = InforceBlock.from_csv(normalised_path)
        assert block.n_policies == 4
        # Policies are created in source order; verify per-policy rating
        by_id = {p.policy_id: p for p in block.policies}
        assert by_id["R001"].mortality_multiplier == pytest.approx(1.0)
        assert by_id["R002"].mortality_multiplier == pytest.approx(2.0)
        assert by_id["R003"].flat_extra_per_1000 == pytest.approx(5.0)
        assert by_id["R004"].mortality_multiplier == pytest.approx(1.0)

    def test_validation_bounds_reject_out_of_range_rating(self):
        """Out-of-range rating values are rejected at the RatingCodeEntry layer."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RatingCodeEntry(mortality_multiplier=25.0)
        with pytest.raises(ValidationError):
            RatingCodeEntry(flat_extra_per_1000=150.0)

    def test_rating_map_loads_from_yaml(self, tmp_path):
        """Rating-code registry is serialisable via YAML like the rest of IngestConfig."""
        yaml_path = tmp_path / "mapping.yaml"
        config_dict = {
            "column_mapping": {"policy_id": "id"},
            "rating_code_map": {
                "source_column": "rate_cls",
                "codes": {
                    "STD": {"mortality_multiplier": 1.0, "flat_extra_per_1000": 0.0},
                    "TBL2": {"mortality_multiplier": 2.0},
                    "FE5": {"flat_extra_per_1000": 5.0},
                },
            },
        }
        with open(yaml_path, "w") as f:
            yaml.safe_dump(config_dict, f)

        cfg = IngestConfig.from_yaml(yaml_path)
        assert cfg.rating_code_map is not None
        assert cfg.rating_code_map.source_column == "rate_cls"
        assert cfg.rating_code_map.codes["TBL2"].mortality_multiplier == pytest.approx(2.0)
        assert cfg.rating_code_map.codes["FE5"].flat_extra_per_1000 == pytest.approx(5.0)


class TestValidateRatingReport:
    """Tests that validate_inforce_df surfaces substandard-rating composition."""

    def test_report_counts_rated_policies(self, tmp_path):
        """report.n_rated reflects policies with multiplier > 1 or flat_extra > 0."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())
        report = validate_inforce_df(df)

        # R002 (TBL2) and R003 (FE5) are rated; R001 and R004 are standard.
        assert report.n_rated == 2
        assert report.pct_rated_by_count == pytest.approx(0.5)

    def test_report_face_weighted_rated_share(self, tmp_path):
        """pct_rated_by_face is weighted by face amount."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())
        report = validate_inforce_df(df)

        # Rated face = 1,000,000 (R002) + 250,000 (R003) = 1,250,000
        # Total face = 500k + 1m + 250k + 750k = 2,500,000 → 50% by face.
        assert report.pct_rated_by_face == pytest.approx(0.5)

    def test_report_mean_multiplier_rated(self, tmp_path):
        """Mean multiplier is averaged only over rated policies."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config())
        report = validate_inforce_df(df)

        # Rated multipliers: R002=2.0, R003=1.0 (flat-extra only) → mean 1.5
        assert report.mean_multiplier_rated == pytest.approx(1.5)

    def test_report_zero_rated_when_no_rating_columns(self, tmp_path):
        """When rating columns are absent, n_rated stays 0 (default dataclass)."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)

        df = ingest_cedant_data(csv_path, _rating_config(include_rating_code_map=False))
        report = validate_inforce_df(df)

        # No rating fields in df → report.n_rated stays 0
        assert report.n_rated == 0
        assert report.pct_rated_by_count == pytest.approx(0.0)
