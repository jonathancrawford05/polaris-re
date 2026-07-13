"""Tests for cedant inforce data ingestion pipeline."""

from pathlib import Path

import polars as pl
import pytest
import yaml

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.utils.ingestion import (
    REJECT_REASON_COLUMN,
    CurrencyConfig,
    IngestConfig,
    RatingCodeEntry,
    RatingCodeMap,
    apply_value_coercion,
    ingest_cedant_data,
    partition_inforce_rows,
    validate_inforce_df,
)


def _inforce_rows(**overrides) -> pl.DataFrame:
    """A small, fully-populated, all-clean normalised inforce frame.

    Column values are lists of equal length; pass keyword overrides to inject
    defects for a specific row (e.g. ``face_amount=[500_000.0, 0.0]``).
    """
    base = {
        "policy_id": ["P1", "P2", "P3"],
        "issue_age": [35, 40, 45],
        "attained_age": [37, 42, 47],
        "sex": ["M", "F", "M"],
        "smoker_status": ["NS", "NS", "S"],
        "face_amount": [500_000.0, 250_000.0, 300_000.0],
        "annual_premium": [1_200.0, 950.0, 800.0],
        "product_type": ["TERM", "TERM", "TERM"],
        "duration_inforce": [24, 24, 24],
        "issue_date": ["2022-01-01", "2022-01-01", "2022-01-01"],
        "valuation_date": ["2024-01-01", "2024-01-01", "2024-01-01"],
    }
    base.update(overrides)
    return pl.DataFrame(base)


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
            # 36 months in force from 2023-01-01 → attained 53 (the ADR-074
            # guard rejects stored ages that contradict the dates).
            "attained_age": 53,
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

    def test_strict_default_is_false_preserves_backcompat(self):
        """Default ``strict`` is False so existing configs silently default unknown codes."""
        rmap = RatingCodeMap(source_column="rate", codes={"STD": RatingCodeEntry()})
        assert rmap.strict is False

    def test_strict_mode_raises_on_unknown_code(self, tmp_path):
        """``strict=True`` rejects rows whose rating code is not registered in ``codes``."""
        csv_path = tmp_path / "rated.csv"
        _write_rated_cedant_csv(csv_path)
        cfg = _rating_config()
        strict_cfg = IngestConfig(
            column_mapping=cfg.column_mapping,
            rating_code_map=RatingCodeMap(
                source_column="rating_code",
                codes=cfg.rating_code_map.codes,  # type: ignore[union-attr]
                strict=True,
            ),
        )

        with pytest.raises(PolarisValidationError) as exc_info:
            ingest_cedant_data(csv_path, strict_cfg)

        # R004 carries UNKNOWN_CODE — surface it AND the offending policy_id.
        msg = str(exc_info.value)
        assert "UNKNOWN_CODE" in msg
        assert "R004" in msg

    def test_strict_mode_passes_when_all_codes_known(self, tmp_path):
        """``strict=True`` ingests cleanly when every rating code is registered."""
        csv_path = tmp_path / "all_known.csv"
        rows = [
            {
                "policy_id": "K001",
                "issue_age": 30,
                "attained_age": 35,
                "sex": "M",
                "smoker_status": "NS",
                "underwriting_class": "STANDARD",
                "face_amount": 500_000,
                "annual_premium": 1000.0,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 24,
                "issue_date": "2024-01-01",
                "valuation_date": "2026-01-01",
                "RATE_CLASS": "STD",
            },
            {
                "policy_id": "K002",
                "issue_age": 45,
                "attained_age": 50,
                "sex": "F",
                "smoker_status": "NS",
                "underwriting_class": "RATED",
                "face_amount": 1_000_000,
                "annual_premium": 5000.0,
                "product_type": "TERM",
                "policy_term": 15,
                "duration_inforce": 12,
                "issue_date": "2025-01-01",
                "valuation_date": "2026-01-01",
                "RATE_CLASS": "TBL2",
            },
        ]
        pl.DataFrame(rows).write_csv(csv_path)
        cfg = _rating_config()
        strict_cfg = IngestConfig(
            column_mapping=cfg.column_mapping,
            rating_code_map=RatingCodeMap(
                source_column="rating_code",
                codes=cfg.rating_code_map.codes,  # type: ignore[union-attr]
                strict=True,
            ),
        )

        df = ingest_cedant_data(csv_path, strict_cfg)

        rows_by_id = {row["policy_id"]: row for row in df.iter_rows(named=True)}
        assert rows_by_id["K001"]["mortality_multiplier"] == pytest.approx(1.0)
        assert rows_by_id["K002"]["mortality_multiplier"] == pytest.approx(2.0)

    def test_strict_mode_lists_all_unknown_codes_deduped(self, tmp_path):
        """Error message lists every distinct unknown code, deduped and sorted."""
        csv_path = tmp_path / "many_unknown.csv"
        base = {
            "issue_age": 35,
            "attained_age": 40,
            "sex": "M",
            "smoker_status": "NS",
            "underwriting_class": "STANDARD",
            "face_amount": 500_000,
            "annual_premium": 1000.0,
            "product_type": "TERM",
            "policy_term": 20,
            "duration_inforce": 24,
            "issue_date": "2024-01-01",
            "valuation_date": "2026-01-01",
        }
        rows = [
            {"policy_id": "P1", **base, "RATE_CLASS": "ZZZ"},
            {"policy_id": "P2", **base, "RATE_CLASS": "AAA"},
            {"policy_id": "P3", **base, "RATE_CLASS": "ZZZ"},  # duplicate
            {"policy_id": "P4", **base, "RATE_CLASS": "STD"},  # known
        ]
        pl.DataFrame(rows).write_csv(csv_path)
        cfg = _rating_config()
        strict_cfg = IngestConfig(
            column_mapping=cfg.column_mapping,
            rating_code_map=RatingCodeMap(
                source_column="rating_code",
                codes=cfg.rating_code_map.codes,  # type: ignore[union-attr]
                strict=True,
            ),
        )

        with pytest.raises(PolarisValidationError) as exc_info:
            ingest_cedant_data(csv_path, strict_cfg)

        msg = str(exc_info.value)
        # Both unknown codes listed; "STD" (known) not flagged.
        assert "AAA" in msg
        assert "ZZZ" in msg
        # AAA should appear before ZZZ (sorted) and ZZZ should not be duplicated.
        assert msg.count("ZZZ") == 1
        assert msg.index("AAA") < msg.index("ZZZ")
        assert "STD" not in msg

    def test_strict_mode_yaml_roundtrip(self, tmp_path):
        """``strict`` flag round-trips through YAML config."""
        yaml_path = tmp_path / "strict_mapping.yaml"
        config_dict = {
            "column_mapping": {"policy_id": "id"},
            "rating_code_map": {
                "source_column": "rate_cls",
                "codes": {"STD": {"mortality_multiplier": 1.0}},
                "strict": True,
            },
        }
        with open(yaml_path, "w") as f:
            yaml.safe_dump(config_dict, f)

        cfg = IngestConfig.from_yaml(yaml_path)
        assert cfg.rating_code_map is not None
        assert cfg.rating_code_map.strict is True

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


class TestPartitionInforceRows:
    """Row-level quarantine partitioning (A3' Slice 1, ADR-136)."""

    def test_all_clean_passthrough(self):
        """A clean frame yields zero rejects and preserves every row."""
        df = _inforce_rows()
        clean, rejects, report = partition_inforce_rows(df)
        assert report.n_input == 3
        assert report.n_rejected == 0
        assert report.n_policies == 3
        assert not report.has_rejects
        assert report.is_valid
        assert report.reject_reasons == {}
        assert clean.equals(df)
        assert rejects.height == 0
        assert REJECT_REASON_COLUMN in rejects.columns

    def test_clean_frame_is_idempotent(self):
        """Re-partitioning the clean output rejects nothing."""
        df = _inforce_rows()
        clean, _, _ = partition_inforce_rows(df)
        clean2, _, report2 = partition_inforce_rows(clean)
        assert report2.n_rejected == 0
        assert clean2.equals(clean)

    def test_non_positive_face_is_rejected(self):
        """A zero or negative face amount quarantines exactly that row."""
        df = _inforce_rows(face_amount=[500_000.0, 0.0, -1.0])
        clean, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 2
        assert report.reject_reasons["non_positive_face_amount"] == 2
        assert clean["policy_id"].to_list() == ["P1"]
        assert set(rejects["policy_id"].to_list()) == {"P2", "P3"}
        assert all("non_positive_face_amount" in r for r in rejects[REJECT_REASON_COLUMN].to_list())

    def test_non_positive_premium_is_rejected(self):
        df = _inforce_rows(annual_premium=[1_200.0, 0.0, 800.0])
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        assert report.reject_reasons == {"non_positive_premium": 1}
        assert rejects["policy_id"].to_list() == ["P2"]

    def test_negative_age_is_rejected(self):
        df = _inforce_rows(issue_age=[35, -1, 45])
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        assert "negative_issue_age" in report.reject_reasons
        assert rejects["policy_id"].to_list() == ["P2"]

    def test_attained_before_issue_is_rejected(self):
        """Attained age below issue age is an internally inconsistent record."""
        df = _inforce_rows(issue_age=[35, 50, 45], attained_age=[37, 48, 47])
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        assert "attained_before_issue" in report.reject_reasons
        assert rejects["policy_id"].to_list() == ["P2"]

    def test_missing_required_cell_is_rejected(self):
        """A null in a required column quarantines the row."""
        df = _inforce_rows(sex=["M", None, "M"])
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        assert "missing_required_field" in report.reject_reasons
        assert rejects["policy_id"].to_list() == ["P2"]

    def test_multiple_reasons_are_all_recorded(self):
        """A row failing several rules lists every reason and counts each."""
        # P2: zero face AND attained(30) < issue(40) → two blocking rules.
        df = _inforce_rows(
            face_amount=[500_000.0, 0.0, 300_000.0],
            issue_age=[35, 40, 45],
            attained_age=[37, 30, 47],
        )
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        reason = rejects.filter(pl.col("policy_id") == "P2")[REJECT_REASON_COLUMN].item()
        assert "non_positive_face_amount" in reason
        assert "attained_before_issue" in reason
        # Per-rule counts can sum to more than n_rejected (one row, two rules).
        assert report.reject_reasons["non_positive_face_amount"] == 1
        assert report.reject_reasons["attained_before_issue"] == 1

    def test_summary_stats_computed_on_clean_rows(self):
        """The report's summary statistics describe the clean block only."""
        df = _inforce_rows(face_amount=[500_000.0, 0.0, 300_000.0])
        _, _, report = partition_inforce_rows(df)
        # Clean rows are P1 (500k) + P3 (300k); the rejected 0.0 is excluded.
        assert report.total_face_amount == pytest.approx(800_000.0)
        assert report.n_policies == 2

    def test_all_rows_rejected_yields_empty_clean(self):
        df = _inforce_rows(face_amount=[-1.0, 0.0, -5.0])
        clean, _, report = partition_inforce_rows(df)
        assert report.n_rejected == 3
        assert clean.height == 0
        # Empty clean frame → validate flags it (is_valid False), but the
        # partition still succeeded and quarantined every row.
        assert not report.is_valid
        assert report.has_rejects

    def test_empty_input(self):
        clean, rejects, report = partition_inforce_rows(_inforce_rows().clear())
        assert report.n_input == 0
        assert report.n_rejected == 0
        assert clean.height == 0
        assert rejects.height == 0
        assert REJECT_REASON_COLUMN in rejects.columns

    def test_ingest_then_partition_end_to_end(self, tmp_path):
        """The mapped ingestion output flows cleanly through partitioning."""
        csv_path = tmp_path / "cedant.csv"
        yaml_path = tmp_path / "mapping.yaml"
        _write_cedant_csv(csv_path)
        _write_mapping_yaml(yaml_path)
        df = ingest_cedant_data(csv_path, IngestConfig.from_yaml(yaml_path))
        clean, _, report = partition_inforce_rows(df)
        assert report.n_rejected == 0
        assert report.n_policies == 2
        assert clean.equals(df)

    def test_unparseable_date_string_is_rejected(self):
        """A present-but-unparseable date string quarantines the row (A3' Slice 2)."""
        df = _inforce_rows(issue_date=["2022-01-01", "not-a-date", "2022-01-01"])
        _, rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 1
        assert report.reject_reasons.get("unparseable_issue_date") == 1
        assert rejects["policy_id"].to_list() == ["P2"]
        assert "unparseable_issue_date" in rejects[REJECT_REASON_COLUMN].item()

    def test_iso_dates_are_not_flagged_unparseable(self):
        """A clean ISO block adds no unparseable-date rejects (byte-identical path)."""
        df = _inforce_rows()
        clean, _, report = partition_inforce_rows(df)
        assert report.n_rejected == 0
        assert "unparseable_issue_date" not in report.reject_reasons
        assert "unparseable_valuation_date" not in report.reject_reasons
        assert clean.equals(df)


def _coercion_config(**overrides) -> IngestConfig:
    """An IngestConfig carrying only value-coercion settings (no column mapping)."""
    return IngestConfig(column_mapping={}, **overrides)


class TestApplyValueCoercion:
    """Config-gated value coercion — dates + unit/currency (A3' Slice 2, ADR-137)."""

    def test_default_config_is_noop(self):
        """A config with no coercion settings returns the frame unchanged."""
        df = _inforce_rows()
        out, warnings = apply_value_coercion(df, _coercion_config())
        assert out.equals(df)
        assert warnings == []

    def test_new_fields_default_to_noop(self):
        """The new IngestConfig fields default to no-op values."""
        cfg = _coercion_config()
        assert cfg.unit_scale == {}
        assert cfg.premium_mode == "annual"
        assert cfg.currency is None
        assert cfg.date_columns == []
        assert cfg.date_formats == {}

    def test_unit_scale_face_in_thousands(self):
        """Closed-form: face 500 (thousands) x unit_scale 1000 → 500_000."""
        df = _inforce_rows(face_amount=[500.0, 250.0, 300.0])
        out, _ = apply_value_coercion(df, _coercion_config(unit_scale={"face_amount": 1000.0}))
        assert out["face_amount"].to_list() == [500_000.0, 250_000.0, 300_000.0]

    @pytest.mark.parametrize(
        ("mode", "factor"),
        [("annual", 1.0), ("semiannual", 2.0), ("quarterly", 4.0), ("monthly", 12.0)],
    )
    def test_premium_mode_annualisation(self, mode, factor):
        """Closed-form: a per-period premium is annualised by the mode's factor."""
        df = _inforce_rows(annual_premium=[100.0, 100.0, 100.0])
        out, _ = apply_value_coercion(df, _coercion_config(premium_mode=mode))
        assert out["annual_premium"].to_list() == [100.0 * factor] * 3

    def test_currency_conversion_scales_money_columns(self):
        """A currency rate multiplies every monetary column."""
        df = _inforce_rows(
            face_amount=[500_000.0, 250_000.0, 300_000.0],
            annual_premium=[1_000.0, 1_000.0, 1_000.0],
        )
        cfg = _coercion_config(currency=CurrencyConfig(code="CAD", rate=0.5))
        out, warnings = apply_value_coercion(df, cfg)
        assert out["face_amount"].to_list() == [250_000.0, 125_000.0, 150_000.0]
        assert out["annual_premium"].to_list() == [500.0, 500.0, 500.0]
        assert any("CAD" in w for w in warnings)

    def test_scalings_compose_multiplicatively(self):
        """unit_scale and currency compose (500 x 1000 x 2 = 1_000_000)."""
        df = _inforce_rows(face_amount=[500.0, 250.0, 300.0])
        cfg = _coercion_config(
            unit_scale={"face_amount": 1000.0},
            currency=CurrencyConfig(code="EUR", rate=2.0),
        )
        out, _ = apply_value_coercion(df, cfg)
        assert out["face_amount"].to_list() == [1_000_000.0, 500_000.0, 600_000.0]

    def test_currency_rate_must_be_positive(self):
        """CurrencyConfig rejects non-positive rates."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CurrencyConfig(code="CAD", rate=0.0)
        with pytest.raises(ValidationError):
            CurrencyConfig(code="CAD", rate=-1.0)

    @pytest.mark.parametrize(
        ("raw", "fmt"),
        [
            (["2022-03-04", "2021-12-31", "2020-06-15"], None),  # ISO passthrough
            (["03/04/2022", "12/31/2021", "06/15/2020"], None),  # US MM/DD/YYYY
            (["04/03/2022", "31/12/2021", "15/06/2020"], None),  # EU DD/MM/YYYY (decisive)
            (["44624", "44561", "43997"], None),  # Excel serials
            (["04/03/2022", "31/12/2021", "15/06/2020"], "%d/%m/%Y"),  # explicit EU
        ],
    )
    def test_date_formats_coerce_to_iso(self, raw, fmt):
        """Mixed source date formats all coerce to the same canonical ISO dates."""
        df = _inforce_rows(issue_date=raw)
        date_formats = {"issue_date": fmt} if fmt else {}
        cfg = _coercion_config(date_columns=["issue_date"], date_formats=date_formats)
        out, _ = apply_value_coercion(df, cfg)
        assert out["issue_date"].to_list() == ["2022-03-04", "2021-12-31", "2020-06-15"]

    def test_ambiguous_date_column_warns_and_assumes_us(self):
        """All-≤12 slash dates are ambiguous: warn and assume US (MM/DD/YYYY)."""
        df = _inforce_rows(issue_date=["03/04/2022", "05/06/2022", "07/08/2022"])
        out, warnings = apply_value_coercion(df, _coercion_config(date_columns=["issue_date"]))
        # US reading: 03/04 → Mar 4, 05/06 → May 6, 07/08 → Jul 8.
        assert out["issue_date"].to_list() == ["2022-03-04", "2022-05-06", "2022-07-08"]
        assert any("Ambiguous date format" in w and "issue_date" in w for w in warnings)

    def test_explicit_format_suppresses_ambiguity_warning(self):
        """Providing an explicit format resolves ambiguity with no warning."""
        df = _inforce_rows(issue_date=["03/04/2022", "05/06/2022", "07/08/2022"])
        cfg = _coercion_config(date_columns=["issue_date"], date_formats={"issue_date": "%d/%m/%Y"})
        out, warnings = apply_value_coercion(df, cfg)
        # EU reading (%d/%m/%Y): 03/04 → 3 Apr, 05/06 → 5 Jun, 07/08 → 7 Aug.
        assert out["issue_date"].to_list() == ["2022-04-03", "2022-06-05", "2022-08-07"]
        assert not any("Ambiguous" in w for w in warnings)

    def test_unparseable_date_left_for_quarantine(self):
        """An unparseable date is left as-is, warned, and rejected downstream."""
        df = _inforce_rows(issue_date=["03/04/2022", "junk", "07/08/2022"])
        cfg = _coercion_config(date_columns=["issue_date"])
        out, warnings = apply_value_coercion(df, cfg)
        assert out["issue_date"].to_list() == ["2022-03-04", "junk", "2022-07-08"]
        assert any("could not be parsed" in w for w in warnings)
        # The Slice-1 machinery then quarantines the offending row.
        _, rejects, report = partition_inforce_rows(out)
        assert report.reject_reasons.get("unparseable_issue_date") == 1
        assert rejects["policy_id"].to_list() == ["P2"]

    def test_coerced_us_dates_partition_clean(self):
        """Coercing US dates first lets the whole block partition with no rejects."""
        df = _inforce_rows(
            issue_date=["01/02/2022", "03/04/2022", "05/06/2022"],
            valuation_date=["01/02/2024", "03/04/2024", "05/06/2024"],
        )
        cfg = _coercion_config(date_columns=["issue_date", "valuation_date"])
        out, _ = apply_value_coercion(df, cfg)
        clean, _, report = partition_inforce_rows(out)
        assert report.n_rejected == 0
        assert clean.height == 3

    def test_end_to_end_ingest_coerce_partition_roundtrip(self, tmp_path):
        """ingest → coerce (US dates + face in thousands) → partition → InforceBlock."""
        from polaris_re.core.inforce import InforceBlock

        csv_path = tmp_path / "messy.csv"
        rows = [
            {
                "policy_id": "M1",
                "issue_age": 35,
                "attained_age": 40,
                "sex": "M",
                "smoker_status": "NS",
                "face_amount": 500,  # in thousands
                "annual_premium": 100.0,  # monthly basis
                "product_type": "TERM",
                "duration_inforce": 60,
                "issue_date": "01/15/2020",  # US format
                "valuation_date": "01/15/2025",
            },
            {
                "policy_id": "M2",
                "issue_age": 45,
                "attained_age": 49,
                "sex": "F",
                "smoker_status": "S",
                "face_amount": 250,
                "annual_premium": 200.0,
                "product_type": "TERM",
                "duration_inforce": 54,
                "issue_date": "07/15/2020",
                "valuation_date": "01/15/2025",
            },
        ]
        pl.DataFrame(rows).write_csv(csv_path)
        cfg = IngestConfig(
            column_mapping={},
            unit_scale={"face_amount": 1000.0},
            premium_mode="monthly",
            date_columns=["issue_date", "valuation_date"],
        )
        df = ingest_cedant_data(csv_path, cfg)
        df, _warnings = apply_value_coercion(df, cfg)
        clean, _rejects, report = partition_inforce_rows(df)
        assert report.n_rejected == 0
        assert clean["face_amount"].to_list() == [500_000.0, 250_000.0]
        assert clean["annual_premium"].to_list() == [1_200.0, 2_400.0]
        assert clean["issue_date"].to_list() == ["2020-01-15", "2020-07-15"]

        normalised = tmp_path / "normalised.csv"
        clean.write_csv(normalised)
        block = InforceBlock.from_csv(normalised)
        assert block.n_policies == 2
        by_id = {p.policy_id: p for p in block.policies}
        assert by_id["M1"].face_amount == pytest.approx(500_000.0)
        assert by_id["M1"].issue_date.isoformat() == "2020-01-15"
