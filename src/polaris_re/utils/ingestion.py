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
from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl
import yaml
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "REJECT_REASON_COLUMN",
    "CurrencyConfig",
    "DataQualityReport",
    "IngestConfig",
    "RatingCodeEntry",
    "RatingCodeMap",
    "apply_value_coercion",
    "ingest_cedant_data",
    "partition_inforce_rows",
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

# --- A3' Slice 2 value-coercion constants (ADR-137) -------------------------
# Monetary columns eligible for unit / currency scaling.
MONEY_COLUMNS = ("face_amount", "annual_premium")

# Calendar-date columns eligible for date coercion and the unparseable-date
# reject rule. These are the required date columns downstream ``InforceBlock``
# parses with ``date.fromisoformat`` — i.e. they must end up as ISO strings.
DATE_COLUMNS = ("issue_date", "valuation_date")

# Canonical output date format: ISO-8601, matching ``date.fromisoformat``.
CANONICAL_DATE_FORMAT = "%Y-%m-%d"

# Candidate source date formats, tried in preference order when a column has no
# explicit format. ISO first so already-clean data is a no-op; US (MM/DD/YYYY)
# before EU (DD/MM/YYYY) is the North-American reinsurance default. Excel serials
# are handled separately (see :func:`_date_parse_expr`).
DATE_CANDIDATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y")

# Excel's day-zero epoch (Excel's 1900 leap-year bug means serial 1 == 1900-01-01,
# so the epoch is 1899-12-30).
EXCEL_EPOCH = date(1899, 12, 30)

# Premium-reporting-frequency → annualisation factor. ``annual_premium`` is
# multiplied by the factor to convert a per-period figure to an annual one.
PREMIUM_ANNUALISATION: dict[str, float] = {
    "annual": 1.0,
    "semiannual": 2.0,
    "quarterly": 4.0,
    "monthly": 12.0,
}


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
            "Defaults to standard (multiplier=1.0, flat_extra=0.0). Ignored "
            "when ``strict`` is True — unknown codes raise instead of falling "
            "back."
        ),
    )
    strict: bool = Field(
        default=False,
        description=(
            "When True, ingestion raises PolarisValidationError if the source "
            "column contains any code not registered in ``codes``. When False "
            "(default), unknown codes silently fall back to ``default``. "
            "Strict mode is the recommended setting for production pipelines "
            "where an unrecognised cedant code is more likely a data error "
            "than a deliberate standard-life signal."
        ),
    )


class CurrencyConfig(PolarisBaseModel):
    """
    Static currency conversion applied to monetary columns during coercion.

    A single fixed multiplicative rate converts source-currency figures to the
    reporting currency (``reporting = source x rate``). This is deliberately a
    static-rate hook — a live FX feed or per-cohort rate is out of scope for
    A3' Slice 2 (ADR-137). Applied to :data:`MONEY_COLUMNS` only.
    """

    code: str = Field(
        description="ISO code of the source currency, e.g. 'CAD'. Recorded for provenance."
    )
    rate: float = Field(
        gt=0.0,
        description=(
            "Multiplicative rate converting source → reporting currency "
            "(reporting = source x rate). Must be positive."
        ),
    )


class IngestConfig(PolarisBaseModel):
    """
    YAML-driven mapping configuration for cedant inforce ingestion.

    Maps arbitrary source column names to Polaris RE field names, defines
    code translations (e.g. ``M → MALE``), optionally derives the
    per-policy substandard rating fields from a cedant rating-code column,
    and provides default values for missing optional fields.

    The value-coercion fields (``unit_scale`` / ``premium_mode`` / ``currency``
    / ``date_columns`` / ``date_formats``, A3' Slice 2, ADR-137) drive
    :func:`apply_value_coercion`. They all default to a no-op, so a config that
    does not set them leaves the ingested frame byte-identical to today's
    behaviour.
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
    unit_scale: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-column multiplicative scale applied during value coercion, e.g. "
            "{'face_amount': 1000.0} to convert a face reported in thousands to "
            "dollars. Empty (default) leaves values unchanged."
        ),
    )
    premium_mode: Literal["annual", "semiannual", "quarterly", "monthly"] = Field(
        default="annual",
        description=(
            "Reporting frequency of ``annual_premium`` in the source. Non-annual "
            "values are annualised (monthly → x12, quarterly → x4, semiannual → "
            "x2). Default 'annual' is a no-op."
        ),
    )
    currency: CurrencyConfig | None = Field(
        default=None,
        description=(
            "Optional static currency conversion applied to monetary columns "
            "during coercion. None (default) leaves values unchanged."
        ),
    )
    date_columns: list[str] = Field(
        default_factory=list,
        description=(
            "Columns to coerce to canonical ISO dates during value coercion. "
            "Empty (default) means no date coercion — source strings pass through "
            "unchanged, preserving current behaviour."
        ),
    )
    date_formats: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Explicit source strftime format per date column (e.g. "
            "{'issue_date': '%d/%m/%Y'}). Overrides auto-inference and suppresses "
            "the ambiguous-format warning for that column."
        ),
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
    """Summary of data quality checks on an ingested inforce DataFrame.

    Summary statistics (``n_policies`` and below) describe the rows that
    passed validation — i.e. the *clean* block that will actually be priced.
    The row-level quarantine fields (``n_input`` / ``n_rejected`` /
    ``reject_reasons``) are populated by :func:`partition_inforce_rows`, which
    separates unusable rows instead of failing the whole block; they stay at
    their defaults for the frame-level :func:`validate_inforce_df` path so that
    function's behaviour is unchanged (A3' Slice 1, ADR-136).
    """

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
    # Row-level quarantine diagnostics (A3' Slice 1). ``n_input`` is the total
    # rows examined; ``n_rejected`` the rows quarantined; ``reject_reasons`` maps
    # each blocking rule name → how many rows failed it (a row failing two rules
    # increments both, so the values can sum to more than ``n_rejected``).
    n_input: int = 0
    n_rejected: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """True if no blocking errors were found on the clean block.

        Note this reflects the *clean* rows only. A partitioned block can have
        ``is_valid`` True while ``n_rejected > 0`` — that is the intended
        outcome: unusable rows were quarantined so the rest can be priced. Use
        :attr:`has_rejects` to test whether any rows were dropped.
        """
        return len(self.errors) == 0

    @property
    def has_rejects(self) -> bool:
        """True if any rows were quarantined by row-level validation."""
        return self.n_rejected > 0


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

    if mapping.strict:
        present = df[mapping.source_column].cast(pl.Utf8)
        unknown_mask = ~present.is_in(list(mapping.codes.keys()))
        if bool(unknown_mask.any()):
            unknown_codes = sorted(
                {str(c) for c in present.filter(unknown_mask).unique().to_list()}
            )
            example_ids: list[str] = []
            if "policy_id" in df.columns:
                example_ids = [
                    str(pid) for pid in df.filter(unknown_mask)["policy_id"].head(5).to_list()
                ]
            id_hint = f" (e.g. policy_id={example_ids})" if example_ids else ""
            raise PolarisValidationError(
                f"Unknown rating code(s) in column '{mapping.source_column}' "
                f"with strict=True: {unknown_codes}{id_hint}. Add them to "
                f"rating_code_map.codes or set strict=False to fall back to "
                f"the default rating."
            )

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


def _date_parse_expr(col: str, formats: list[str]) -> pl.Expr:
    """Build a Date expression parsing ``col`` under any of ``formats``.

    Attempts each strftime format in order and coalesces the results, so a
    column that mixes a few formats still parses row-by-row. All-digit strings
    are additionally parsed as Excel serials (days since :data:`EXCEL_EPOCH`).
    Cells matching no format resolve to null.
    """
    s = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
    attempts = [s.str.to_date(fmt, strict=False) for fmt in formats]
    serial = (
        pl.when(s.str.contains(r"^\d+$"))
        .then(
            (pl.lit(EXCEL_EPOCH) + pl.duration(days=s.cast(pl.Int64, strict=False))).cast(pl.Date)
        )
        .otherwise(None)
    )
    attempts.append(serial)
    return pl.coalesce(attempts)


def _infer_date_order(series: pl.Series, explicit: str | None) -> tuple[list[str], bool]:
    """Infer the format-preference order for a date column.

    Returns ``(ordered_formats, ambiguous)``. When ``explicit`` is given it is
    used verbatim and ``ambiguous`` is False. Otherwise the slash-delimited
    values are inspected: a first component > 12 forces EU (DD/MM/YYYY), a second
    component > 12 forces US (MM/DD/YYYY). When neither is decisive but some value
    has both components ≤ 12 and unequal, the column is genuinely ambiguous —
    US order is chosen (the North-American default) and ``ambiguous`` is True so a
    warning is raised.
    """
    if explicit:
        return [explicit], False

    s = series.cast(pl.Utf8, strict=False).str.strip_chars()
    first = s.str.extract(r"^(\d{1,2})/\d{1,2}/\d{2,4}$", 1).cast(pl.Int64, strict=False)
    second = s.str.extract(r"^\d{1,2}/(\d{1,2})/\d{2,4}$", 1).cast(pl.Int64, strict=False)
    stats = (
        series.to_frame()
        .select(
            saw_slash=first.is_not_null().any(),
            must_eu=(first > 12).any(),
            must_us=(second > 12).any(),
            both_le_12=((first <= 12) & (second <= 12) & (first != second)).any(),
        )
        .row(0, named=True)
    )

    us, eu = "%m/%d/%Y", "%d/%m/%Y"
    base = ["%Y-%m-%d", "%Y/%m/%d"]
    ambiguous = False
    if stats["must_eu"] and not stats["must_us"]:
        order = [*base, eu, us]
    elif stats["must_us"] and not stats["must_eu"]:
        order = [*base, us, eu]
    else:
        order = [*base, us, eu]
        ambiguous = bool(stats["saw_slash"] and stats["both_le_12"] and not stats["must_us"])
    return order, ambiguous


def _scale_value_columns(
    df: pl.DataFrame, config: IngestConfig, warnings: list[str]
) -> pl.DataFrame:
    """Apply unit / premium-annualisation / currency scaling to monetary columns.

    All three are multiplicative, so per-column factors are composed and applied
    in a single pass. A column enters ``factors`` only when a config source
    actually touches it — an explicit ``unit_scale`` entry, a non-``annual``
    ``premium_mode`` (for ``annual_premium``), or a configured ``currency`` (for
    the monetary columns). Membership in ``factors`` is therefore the "was
    scaling configured for this column?" signal: with a default config nothing is
    added, ``factors`` is empty, and the frame is returned byte-identical — the
    no-op guarantee the golden suite relies on is a property of the control flow,
    not of a float-equality check on the composed factor.

    A column that a config source *does* touch is always processed (cast to
    ``Float64`` and multiplied), even when its net factor works out to exactly
    ``1.0`` (e.g. an explicit ``unit_scale`` of ``1.0``, or a coincidental
    product). This is deliberate: the user asked us to scale that column, so we
    normalise its dtype to the canonical monetary ``float64`` rather than
    silently short-circuiting on an arithmetic identity.
    """
    factors: dict[str, float] = {}

    # Unit scale — every column the user explicitly listed is configured.
    for col, scale in config.unit_scale.items():
        if col in df.columns:
            factors[col] = factors.get(col, 1.0) * float(scale)

    # Premium annualisation — gate on the mode, not the factor. 'annual' is the
    # only mode with a unit factor, so a non-'annual' mode always means "scale".
    if config.premium_mode != "annual" and "annual_premium" in df.columns:
        premium_factor = PREMIUM_ANNUALISATION[config.premium_mode]
        factors["annual_premium"] = factors.get("annual_premium", 1.0) * premium_factor
        warnings.append(
            f"Annualised 'annual_premium' from {config.premium_mode} basis (x{premium_factor:g})."
        )

    # Currency — gate on a rate being configured.
    if config.currency is not None:
        for col in MONEY_COLUMNS:
            if col in df.columns:
                factors[col] = factors.get(col, 1.0) * config.currency.rate
        warnings.append(
            f"Converted monetary columns from {config.currency.code} at rate "
            f"{config.currency.rate:g} to the reporting currency."
        )

    if not factors:
        return df
    exprs = [
        (pl.col(col).cast(pl.Float64, strict=False) * factor).alias(col)
        for col, factor in factors.items()
    ]
    return df.with_columns(exprs)


def _coerce_date_columns(
    df: pl.DataFrame, config: IngestConfig, warnings: list[str]
) -> pl.DataFrame:
    """Coerce the configured date columns to canonical ISO strings.

    Parseable cells become ``YYYY-MM-DD`` strings (what downstream
    ``InforceBlock.from_csv`` expects); unparseable non-empty cells are left as
    their original string so :func:`partition_inforce_rows` can quarantine them
    with an ``unparseable_<col>`` reason. Genuinely ambiguous columns raise a
    warning naming the assumed order and how to disambiguate.
    """
    for col in config.date_columns:
        if col not in df.columns or df.schema[col] not in (pl.Utf8, pl.String):
            continue
        explicit = config.date_formats.get(col)
        order, ambiguous = _infer_date_order(df[col], explicit)
        if ambiguous:
            warnings.append(
                f"Ambiguous date format in column '{col}': values fit both US "
                f"(MM/DD/YYYY) and EU (DD/MM/YYYY). Assumed US. Set "
                f"date_formats['{col}'] to disambiguate."
            )
        parsed = _date_parse_expr(col, order)
        original = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
        n_unparseable = int(
            df.select(
                (original.is_not_null() & (original.str.len_chars() > 0) & parsed.is_null()).sum()
            ).item()
        )
        if n_unparseable:
            warnings.append(
                f"Column '{col}': {n_unparseable} value(s) could not be parsed as a "
                f"date; affected rows will be quarantined."
            )
        iso = parsed.dt.strftime(CANONICAL_DATE_FORMAT)
        df = df.with_columns(pl.coalesce([iso, pl.col(col).cast(pl.Utf8, strict=False)]).alias(col))
    return df


def apply_value_coercion(df: pl.DataFrame, config: IngestConfig) -> tuple[pl.DataFrame, list[str]]:
    """Apply config-gated value coercion to a normalised inforce frame.

    Two independent, default-off transformations (A3' Slice 2, ADR-137):

    * **Unit / premium / currency scaling** of monetary columns
      (``unit_scale`` x ``premium_mode`` x ``currency``).
    * **Date coercion** of ``date_columns`` to canonical ISO strings, with
      per-column format inference, Excel-serial support, and ambiguity flagging.

    Intended to run between :func:`ingest_cedant_data` and
    :func:`partition_inforce_rows`: scaling and canonicalisation happen first so
    that a value which fails coercion becomes a null (caught by
    ``missing_<col>``) or an ``unparseable_<col>`` reject — either way
    it lands in the rejects frame with a clear reason instead of crashing
    downstream.

    Args:
        df:     Normalised Polaris RE DataFrame (post-``ingest_cedant_data``).
        config: Mapping/coercion configuration.

    Returns:
        ``(coerced_df, warnings)``. With a default config the frame is returned
        byte-identical and ``warnings`` is empty — the pricing/golden path is
        never affected.
    """
    warnings: list[str] = []
    df = _scale_value_columns(df, config, warnings)
    df = _coerce_date_columns(df, config, warnings)
    return df, warnings


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


# Row-level blocking rules. Each maps a rule name → a callable building a Polars
# boolean expression that is True when the row is INVALID for that rule. A rule
# is only applied when the columns it needs are present. Non-blocking issues
# (duplicate ids, age > 120) stay warnings on the report and never reject a row.
REJECT_REASON_COLUMN = "_reject_reason"


def _row_rules(columns: list[str]) -> list[tuple[str, pl.Expr]]:
    """Blocking row-rule expressions applicable to the given column set."""
    cols = set(columns)
    rules: list[tuple[str, pl.Expr]] = []

    # 1. Any required cell is null → the row cannot be built into a Policy. One
    #    rule per required column so the reason names the offending field
    #    (``missing_issue_age``), consistent with the per-column ``negative_<col>``
    #    and ``unparseable_<col>`` rules — a row missing two fields lists both.
    for col in (c for c in REQUIRED_COLUMNS if c in cols):
        rules.append((f"missing_{col}", pl.col(col).is_null()))

    # 2. Non-positive money fields (nulls are covered by rule 1).
    if "face_amount" in cols:
        rules.append(
            (
                "non_positive_face_amount",
                (pl.col("face_amount").cast(pl.Float64, strict=False) <= 0.0).fill_null(False),
            )
        )
    if "annual_premium" in cols:
        rules.append(
            (
                "non_positive_premium",
                (pl.col("annual_premium").cast(pl.Float64, strict=False) <= 0.0).fill_null(False),
            )
        )

    # 3. Negative ages.
    for age_col in ("issue_age", "attained_age"):
        if age_col in cols:
            rules.append(
                (
                    f"negative_{age_col}",
                    (pl.col(age_col).cast(pl.Float64, strict=False) < 0.0).fill_null(False),
                )
            )

    # 4. Attained age before issue age — an internally inconsistent record.
    if {"issue_age", "attained_age"} <= cols:
        rules.append(
            (
                "attained_before_issue",
                (
                    pl.col("attained_age").cast(pl.Float64, strict=False)
                    < pl.col("issue_age").cast(pl.Float64, strict=False)
                ).fill_null(False),
            )
        )

    return rules


def _date_reject_rules(df: pl.DataFrame) -> list[tuple[str, pl.Expr]]:
    """Blocking rules for string date columns that fail to parse (A3' Slice 2).

    A cell is rejected (``unparseable_<col>``) when it is a non-empty string that
    matches none of :data:`DATE_CANDIDATE_FORMATS` (nor an Excel serial). Empty /
    null cells are left to the ``missing_<col>`` rules. Only string-typed
    :data:`DATE_COLUMNS` are checked — already-temporal columns are skipped — so
    a clean ISO block (the common case, and every existing caller) is unaffected.
    """
    rules: list[tuple[str, pl.Expr]] = []
    for col in DATE_COLUMNS:
        if col in df.columns and df.schema[col] in (pl.Utf8, pl.String):
            original = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
            parseable = _date_parse_expr(col, list(DATE_CANDIDATE_FORMATS))
            rules.append(
                (
                    f"unparseable_{col}",
                    original.is_not_null() & (original.str.len_chars() > 0) & parseable.is_null(),
                )
            )
    return rules


def partition_inforce_rows(
    df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, DataQualityReport]:
    """Split a normalised inforce frame into clean and rejected rows.

    Unlike :func:`validate_inforce_df` (which flags the whole frame as invalid
    when any blocking problem is present), this partitions the block so a
    reinsurer can price the usable rows and quarantine the rest — the common
    reality with real cedant extracts (A3' Slice 1, ADR-136).

    A row is **rejected** when it violates any blocking rule in
    :func:`_row_rules` (missing required cell, non-positive face/premium,
    negative age, attained-before-issue) or :func:`_date_reject_rules` (a
    present-but-unparseable date string, A3' Slice 2). Rejected rows are returned in a second
    frame carrying a ``_reject_reason`` column that lists every rule they failed
    (``"; "``-joined). The returned :class:`DataQualityReport` describes the
    **clean** rows (its summary stats are computed on them, reusing
    :func:`validate_inforce_df`) and additionally records ``n_input``,
    ``n_rejected``, and a per-rule ``reject_reasons`` breakdown.

    Args:
        df: Normalised Polaris RE DataFrame (post-``ingest_cedant_data``).

    Returns:
        ``(clean_df, rejects_df, report)``. ``clean_df`` has the input columns;
        ``rejects_df`` has the input columns plus ``_reject_reason`` (and is
        empty with just the reason column appended when nothing is rejected).
    """
    n_input = len(df)
    rules = _row_rules(df.columns) + _date_reject_rules(df)

    if not rules or n_input == 0:
        clean = df
        rejects = df.clear().with_columns(pl.lit(None, dtype=pl.Utf8).alias(REJECT_REASON_COLUMN))
        report = validate_inforce_df(clean)
        report.n_input = n_input
        report.n_rejected = 0
        return clean, rejects, report

    invalid_expr = pl.any_horizontal([expr for _, expr in rules]).alias("__invalid")
    reason_expr = pl.concat_str(
        [pl.when(expr).then(pl.lit(name)).otherwise(None) for name, expr in rules],
        separator="; ",
        ignore_nulls=True,
    ).alias(REJECT_REASON_COLUMN)

    annotated = df.with_columns([invalid_expr, reason_expr])
    clean = annotated.filter(~pl.col("__invalid")).drop("__invalid", REJECT_REASON_COLUMN)
    rejects = annotated.filter(pl.col("__invalid")).drop("__invalid")

    # Per-rule counts over the whole input (a row can count toward several rules).
    rule_counts = df.select([expr.cast(pl.Int64).sum().alias(name) for name, expr in rules]).row(
        0, named=True
    )
    reject_reasons = {name: int(count) for name, count in rule_counts.items() if count}

    report = validate_inforce_df(clean)
    report.n_input = n_input
    report.n_rejected = len(rejects)
    report.reject_reasons = reject_reasons
    return clean, rejects, report
