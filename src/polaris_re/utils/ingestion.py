"""
Cedant inforce data ingestion pipeline.

Reinsurers receive inforce data in inconsistent layouts: different column
names, date formats, code mappings, and missing fields. This module provides
a configurable YAML-driven mapping pipeline so any cedant layout can be
ingested without code changes.

Pipeline:
    Raw cedant CSV/Excel → IngestConfig (YAML) → normalised Polaris RE DataFrame
    → DataQualityReport → InforceBlock.from_csv()
"""

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "DataQualityReport",
    "IngestConfig",
    "RatingCodeEntry",
    "RatingCodeMap",
    "ingest_cedant_data",
    "validate_inforce_df",
]

# Polaris RE normalised column names (must match generate_synthetic_block.py output)
POLARIS_COLUMNS = [
    "policy_id",
    "issue_age",
    "attained_age",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount",
    "annual_premium",
    "product_type",
    "policy_term",
    "duration_inforce",
    "reinsurance_cession_pct",
    "mortality_multiplier",
    "flat_extra_per_1000",
    "issue_date",
    "valuation_date",
]

REQUIRED_COLUMNS = [
    "policy_id",
    "issue_age",
    "attained_age",
    "sex",
    "smoker_status",
    "face_amount",
    "annual_premium",
    "product_type",
    "duration_inforce",
    "issue_date",
    "valuation_date",
]


class SourceFormat(PolarisBaseModel):
    """Source file format settings."""

    delimiter: str = Field(default=",", description="CSV delimiter character.")
    date_format: str = Field(default="%Y-%m-%d", description="Date format string.")


class RatingCodeEntry(PolarisBaseModel):
    """
    Target substandard-rating values derived from a single cedant rating code.

    Bounds mirror the ``Policy`` fields to keep the Pydantic validation at
    the ingestion boundary identical to the projection-layer validation.
    """

    mortality_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=20.0,
        description=(
            "Mortality multiplier applied to base q_x. 1.0 = standard; 2.0 = Table 2; "
            "5.0 = Table 8. Must match the bounds on Policy.mortality_multiplier."
        ),
    )
    flat_extra_per_1000: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "Annual flat extra in $ per $1,000 face amount. Must match the "
            "bounds on Policy.flat_extra_per_1000."
        ),
    )


class RatingCodeMap(PolarisBaseModel):
    """
    Cedant rating-code registry.

    Cedants commonly record substandard rating as a single string code
    (e.g. ``STD``, ``TBL2``, ``TBL4``, ``FE5``) rather than as the two
    numeric Polaris fields (``mortality_multiplier``,
    ``flat_extra_per_1000``). This registry derives the two Polaris
    fields from one source column.

    Applied AFTER column renaming and code translations. If a row's
    rating code is not found in ``codes``, ``default`` values are used —
    equivalent to treating the life as standard.
    """

    source_column: str = Field(
        description=(
            "Source column name (post-rename) containing cedant rating codes. "
            "Typically 'rating_code' or similar after column_mapping is applied."
        ),
    )
    codes: dict[str, RatingCodeEntry] = Field(
        description=(
            "Mapping from cedant rating code → target Polaris rating values. "
            "Codes not present in the source file are silently skipped."
        ),
    )
    default: RatingCodeEntry = Field(
        default_factory=RatingCodeEntry,
        description=(
            "Fallback rating for codes not present in the 'codes' dict. "
            "Defaults to standard (multiplier=1.0, flat_extra=0.0)."
        ),
    )


class IngestConfig(PolarisBaseModel):
    """
    YAML-driven mapping configuration for cedant inforce ingestion.

    Maps arbitrary source column names to Polaris RE field names, defines
    code translations (e.g. ``M → MALE``), optionally derives the
    per-policy substandard rating fields from a cedant rating-code column,
    and provides default values for missing optional fields.
    """

    source_format: SourceFormat = Field(default_factory=SourceFormat)
    column_mapping: dict[str, str] = Field(
        description="Maps Polaris RE field name → source column name."
    )
    code_translations: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Per-field code translation dicts (source_value → polaris_value).",
    )
    rating_code_map: RatingCodeMap | None = Field(
        default=None,
        description=(
            "Optional registry that derives mortality_multiplier and "
            "flat_extra_per_1000 from a single cedant rating-code column. "
            "When None, rating is not derived (defaults of 1.0 / 0.0 apply "
            "downstream via Policy validation)."
        ),
    )
    defaults: dict[str, str | float | int] = Field(
        default_factory=dict,
        description="Default values for optional fields not present in source.",
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "IngestConfig":
        """Load an IngestConfig from a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Mapping config not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IngestConfig":
        """Construct from a plain dictionary (e.g. from JSON API request)."""
        return cls(**data)  # type: ignore[arg-type]


@dataclass
class DataQualityReport:
    """Summary of data quality checks on an ingested inforce DataFrame."""

    n_policies: int = 0
    total_face_amount: float = 0.0
    mean_age: float = 0.0
    sex_split: dict[str, int] = field(default_factory=dict)
    smoker_split: dict[str, int] = field(default_factory=dict)
    n_rated: int = 0
    pct_rated_by_count: float = 0.0
    pct_rated_by_face: float = 0.0
    mean_multiplier_rated: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if no blocking errors were found."""
        return len(self.errors) == 0


def _apply_rating_code_map(df: pl.DataFrame, mapping: RatingCodeMap) -> pl.DataFrame:
    """Derive mortality_multiplier and flat_extra_per_1000 from a rating code column.

    Applied after column renaming so ``mapping.source_column`` refers to the
    post-rename column name. Silently leaves the frame unchanged if the
    source column is absent — callers that require the column should set
    it as required in ``column_mapping``.

    Existing mortality_multiplier / flat_extra_per_1000 columns are
    overwritten. This is intentional: when a cedant supplies both a rating
    code and pre-computed multipliers, the rating code is authoritative.
    """
    if mapping.source_column not in df.columns:
        return df

    mult_lookup = {code: entry.mortality_multiplier for code, entry in mapping.codes.items()}
    extra_lookup = {code: entry.flat_extra_per_1000 for code, entry in mapping.codes.items()}

    code_col = pl.col(mapping.source_column).cast(pl.Utf8)
    multiplier_expr = (
        code_col.replace_strict(
            mult_lookup, default=mapping.default.mortality_multiplier, return_dtype=pl.Float64
        )
        .cast(pl.Float64)
        .alias("mortality_multiplier")
    )
    flat_extra_expr = (
        code_col.replace_strict(
            extra_lookup, default=mapping.default.flat_extra_per_1000, return_dtype=pl.Float64
        )
        .cast(pl.Float64)
        .alias("flat_extra_per_1000")
    )

    drop_cols = [c for c in ("mortality_multiplier", "flat_extra_per_1000") if c in df.columns]
    if drop_cols:
        df = df.drop(drop_cols)

    return df.with_columns([multiplier_expr, flat_extra_expr])


def ingest_cedant_data(
    raw_path: Path,
    config: IngestConfig,
) -> pl.DataFrame:
    """
    Apply a mapping config to a raw cedant CSV/Excel file.

    Renames columns, translates codes, fills defaults, and returns
    a normalised Polaris RE DataFrame.

    Args:
        raw_path: Path to the raw cedant data file (.csv or .xlsx).
        config:   Mapping configuration.

    Returns:
        Normalised Polars DataFrame with Polaris RE column names.

    Raises:
        FileNotFoundError: Raw file not found.
        PolarisValidationError: Required columns missing after mapping.
    """
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw inforce file not found: {raw_path}")

    suffix = raw_path.suffix.lower()
    if suffix == ".csv":
        df = pl.read_csv(raw_path, separator=config.source_format.delimiter)
    elif suffix in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("pandas + openpyxl required for Excel input.") from exc
        pdf = pd.read_excel(raw_path)
        df = pl.from_pandas(pdf)
    else:
        raise PolarisValidationError(f"Unsupported file type: {suffix}")

    # Build reverse mapping: source_column → polaris_field
    rename_map: dict[str, str] = {}
    for polaris_field, source_col in config.column_mapping.items():
        if source_col in df.columns:
            rename_map[source_col] = polaris_field

    df = df.rename(rename_map)

    # Apply code translations
    for field_name, translation in config.code_translations.items():
        if field_name in df.columns:
            df = df.with_columns(
                pl.col(field_name).cast(pl.Utf8).replace(translation).alias(field_name)
            )

    # Derive substandard-rating fields from cedant rating codes
    if config.rating_code_map is not None:
        df = _apply_rating_code_map(df, config.rating_code_map)

    # Apply defaults for missing columns
    for field_name, default_value in config.defaults.items():
        if field_name not in df.columns:
            df = df.with_columns(pl.lit(default_value).alias(field_name))

    # Check required columns are present
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise PolarisValidationError(
            f"Required columns missing after mapping: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    # Select only Polaris columns that exist (preserves order)
    available_cols = [c for c in POLARIS_COLUMNS if c in df.columns]
    df = df.select(available_cols)

    return df


def validate_inforce_df(df: pl.DataFrame) -> DataQualityReport:
    """
    Run data quality checks on a normalised inforce DataFrame.

    Args:
        df: Normalised Polaris RE DataFrame.

    Returns:
        DataQualityReport with summary statistics and error/warning lists.
    """
    report = DataQualityReport()
    report.n_policies = len(df)

    if report.n_policies == 0:
        report.errors.append("Empty DataFrame — no policies found.")
        return report

    # Summary statistics
    if "face_amount" in df.columns:
        face_col = df["face_amount"].cast(pl.Float64, strict=False)
        report.total_face_amount = float(face_col.sum())  # type: ignore[arg-type]

    if "attained_age" in df.columns:
        age_col = df["attained_age"].cast(pl.Float64, strict=False)
        report.mean_age = float(age_col.mean())  # type: ignore[arg-type]

    if "sex" in df.columns:
        counts = df["sex"].value_counts()
        report.sex_split = {
            str(row["sex"]): int(row["count"]) for row in counts.iter_rows(named=True)
        }

    if "smoker_status" in df.columns:
        counts = df["smoker_status"].value_counts()
        report.smoker_split = {
            str(row["smoker_status"]): int(row["count"]) for row in counts.iter_rows(named=True)
        }

    # Substandard rating composition (only meaningful when the fields exist)
    if "mortality_multiplier" in df.columns or "flat_extra_per_1000" in df.columns:
        mult_col = (
            df["mortality_multiplier"].cast(pl.Float64, strict=False)
            if "mortality_multiplier" in df.columns
            else pl.Series("mortality_multiplier", [1.0] * report.n_policies, dtype=pl.Float64)
        )
        extra_col = (
            df["flat_extra_per_1000"].cast(pl.Float64, strict=False)
            if "flat_extra_per_1000" in df.columns
            else pl.Series("flat_extra_per_1000", [0.0] * report.n_policies, dtype=pl.Float64)
        )
        is_rated_mask = (mult_col > 1.0) | (extra_col > 0.0)
        report.n_rated = int(is_rated_mask.sum())
        report.pct_rated_by_count = report.n_rated / report.n_policies if report.n_policies else 0.0
        if "face_amount" in df.columns and report.total_face_amount > 0.0:
            face_col = df["face_amount"].cast(pl.Float64, strict=False)
            rated_face = float((face_col * is_rated_mask.cast(pl.Float64)).sum())
            report.pct_rated_by_face = rated_face / report.total_face_amount
        if report.n_rated > 0:
            rated_mult = mult_col.filter(is_rated_mask)
            report.mean_multiplier_rated = float(rated_mult.mean())  # type: ignore[arg-type]

    # Duplicate policy IDs
    if "policy_id" in df.columns:
        n_unique = df["policy_id"].n_unique()
        if n_unique < report.n_policies:
            n_dups = report.n_policies - n_unique
            report.warnings.append(f"{n_dups} duplicate policy_id values found.")

    # Age range checks
    if "attained_age" in df.columns:
        ages = df["attained_age"].cast(pl.Int32, strict=False)
        min_age = int(ages.min())  # type: ignore[arg-type]
        max_age = int(ages.max())  # type: ignore[arg-type]
        if min_age < 0:
            report.errors.append(f"Negative attained_age found (min={min_age}).")
        if max_age > 120:
            report.warnings.append(f"Attained age > 120 found (max={max_age}).")

    # Face amount checks
    if "face_amount" in df.columns:
        face = df["face_amount"].cast(pl.Float64, strict=False)
        if float(face.min()) <= 0:  # type: ignore[arg-type]
            report.errors.append("Non-positive face_amount found.")

    # Required field null checks
    for col in REQUIRED_COLUMNS:
        if col in df.columns:
            n_null = df[col].null_count()
            if n_null > 0:
                report.errors.append(f"Column '{col}' has {n_null} null values.")

    return report
