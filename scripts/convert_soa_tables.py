#!/usr/bin/env python3
"""
convert_soa_tables.py — Download and convert SOA/CIA mortality tables to
Polaris RE CSV format.

PRIMARY PATH (recommended): Fetches tables directly from mort.soa.org via
the `pymort` library. No manual download required.

FALLBACK PATH: Converts manually downloaded SOA Excel files (.xlsx) into
the Polaris RE CSV schema.

TARGET CSV SCHEMA
-----------------
Select-and-ultimate (SOA VBT 2015, CIA 2014):
    age, dur_1, dur_2, ..., dur_25, ultimate
    - Rates expressed as decimals (e.g. 0.00045, NOT per-mille 0.45)
    - age column: attained age (ANB), integers 18-120 inclusive
    - dur_1..dur_25: select-period annual q_x rates
    - ultimate: post-select-period annual q_x rate

Ultimate-only (2001 CSO):
    age, rate
    - age column: integers 0-120 inclusive
    - rate: annual q_x as decimal

USAGE
-----
# Primary: download directly from mort.soa.org (requires: pip install pymort)
python scripts/convert_soa_tables.py --source pymort --output-dir data/mortality_tables

# Fallback: convert locally downloaded SOA Excel files
python scripts/convert_soa_tables.py --source excel --excel-dir ~/Downloads/soa_tables --output-dir data/mortality_tables

# Validate outputs only
python scripts/convert_soa_tables.py --validate-only --output-dir data/mortality_tables

SOA TABLE IDs (mort.soa.org)
-----------------------------
VBT 2015 Smoker-Distinct ANB (select period = 25 years):
    3265  Male Non-Smoker   → soa_vbt_2015_male_ns.csv
    3266  Male Smoker       → soa_vbt_2015_male_smoker.csv
    3267  Female Non-Smoker → soa_vbt_2015_female_ns.csv
    3268  Female Smoker     → soa_vbt_2015_female_smoker.csv

2001 CSO (ultimate-only ANB, rates per 1000 in source):
    1441  Male              → cso_2001_male.csv
    1442  Female            → cso_2001_female.csv

CIA 2014 tables are not available via mort.soa.org (Canadian tables).
Download from cia-ica.ca and use --source excel for those.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl
from rich.console import Console
from rich.table import Table as RichTable

console = Console()

# ---------------------------------------------------------------------------
# SOA table ID registry
# ---------------------------------------------------------------------------

SOA_TABLE_REGISTRY: dict[str, dict] = {
    "soa_vbt_2015_male_ns": {
        "table_id": 3265,
        "description": "2015 VBT Male Non-Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
        "rates_per_mille": False,  # pymort returns rates already as q_x (0-1)
    },
    "soa_vbt_2015_male_smoker": {
        "table_id": 3266,
        "description": "2015 VBT Male Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
        "rates_per_mille": False,
    },
    "soa_vbt_2015_female_ns": {
        "table_id": 3267,
        "description": "2015 VBT Female Non-Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
        "rates_per_mille": False,
    },
    "soa_vbt_2015_female_smoker": {
        "table_id": 3268,
        "description": "2015 VBT Female Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
        "rates_per_mille": False,
    },
    "cso_2001_male": {
        "table_id": 1441,
        "description": "2001 CSO Male Ultimate ANB",
        "select_period": 0,
        "table_type": "ultimate_only",
        "min_age": 0,
        "max_age": 120,
        "rates_per_mille": True,  # SOA stores CSO as q_x * 1000
    },
    "cso_2001_female": {
        "table_id": 1442,
        "description": "2001 CSO Female Ultimate ANB",
        "select_period": 0,
        "table_type": "ultimate_only",
        "min_age": 0,
        "max_age": 120,
        "rates_per_mille": True,
    },
}

# CIA 2014 Excel file patterns (used with --source excel)
# These map the expected filename pattern to target output name.
# CIA distributes their tables as Excel workbooks with separate sheets
# for select (issue_age × duration) and ultimate (attained_age × rate).
CIA_EXCEL_REGISTRY: dict[str, dict] = {
    "cia_2014_male_ns": {
        "filename_pattern": "*male*non*smok*",
        "alt_pattern": "*MNS*",
        "description": "CIA 2014 Male Non-Smoker",
        "select_period": 25,
        "select_sheet": "Select",       # adjust if your file differs
        "ultimate_sheet": "Ultimate",
        "issue_age_col": "Issue Age",   # adjust to match actual column header
        "min_age": 18,
        "max_age": 120,
    },
    "cia_2014_male_smoker": {
        "filename_pattern": "*male*smok*",
        "alt_pattern": "*MS*",
        "description": "CIA 2014 Male Smoker",
        "select_period": 25,
        "select_sheet": "Select",
        "ultimate_sheet": "Ultimate",
        "issue_age_col": "Issue Age",
        "min_age": 18,
        "max_age": 120,
    },
    "cia_2014_female_ns": {
        "filename_pattern": "*female*non*smok*",
        "alt_pattern": "*FNS*",
        "description": "CIA 2014 Female Non-Smoker",
        "select_period": 25,
        "select_sheet": "Select",
        "ultimate_sheet": "Ultimate",
        "issue_age_col": "Issue Age",
        "min_age": 18,
        "max_age": 120,
    },
    "cia_2014_female_smoker": {
        "filename_pattern": "*female*smok*",
        "alt_pattern": "*FS*",
        "description": "CIA 2014 Female Smoker",
        "select_period": 25,
        "select_sheet": "Select",
        "ultimate_sheet": "Ultimate",
        "issue_age_col": "Issue Age",
        "min_age": 18,
        "max_age": 120,
    },
}


# ---------------------------------------------------------------------------
# Primary path: pymort → CSV
# ---------------------------------------------------------------------------


def convert_via_pymort(output_dir: Path, table_keys: list[str] | None = None) -> dict[str, bool]:
    """
    Download SOA tables via pymort and write to Polaris RE CSV format.

    Returns a dict of {output_filename: success_bool}.
    """
    try:
        from pymort import MortXML  # type: ignore[import]
    except ImportError:
        console.print(
            "[red]pymort not installed.[/red] Run:\n"
            "  uv add pymort   (inside the project)\n"
            "  pip install pymort   (standalone)"
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    keys = table_keys or list(SOA_TABLE_REGISTRY.keys())
    results: dict[str, bool] = {}

    for key in keys:
        if key not in SOA_TABLE_REGISTRY:
            console.print(f"[yellow]Unknown table key '{key}' — skipping.[/yellow]")
            continue

        cfg = SOA_TABLE_REGISTRY[key]
        table_id = cfg["table_id"]
        output_path = output_dir / f"{key}.csv"

        console.print(f"  Fetching table {table_id}: {cfg['description']} ...", end=" ")

        try:
            xml = MortXML.from_id(table_id)

            if cfg["table_type"] == "ultimate_only":
                df = _pymort_ultimate_to_csv(xml, cfg)
            else:
                df = _pymort_select_ultimate_to_csv(xml, cfg)

            _validate_output(df, cfg)
            df.write_csv(output_path)
            console.print(f"[green]✓[/green] → {output_path.name}")
            results[key] = True

        except Exception as exc:
            console.print(f"[red]✗ {exc}[/red]")
            results[key] = False

    return results


def _pymort_ultimate_to_csv(xml: object, cfg: dict) -> pl.DataFrame:
    """
    Convert a pymort ultimate-only table to Polars DataFrame in Polaris CSV schema.

    pymort returns a MultiIndex pandas DataFrame for ultimate tables.
    Schema: age | rate
    """
    import pandas as pd  # pymort depends on pandas

    # pymort exposes .values which is a pandas DataFrame for ultimate tables
    # The index is age, the single column is the rate
    ultimate_df: pd.DataFrame = xml.values  # type: ignore[union-attr]

    # Flatten: some tables have multi-level columns or index — normalise
    if isinstance(ultimate_df.index, pd.MultiIndex):
        ultimate_df = ultimate_df.reset_index()
        age_col = [c for c in ultimate_df.columns if "age" in str(c).lower()][0]
        rate_col = [c for c in ultimate_df.columns if c != age_col][0]
    else:
        ultimate_df = ultimate_df.reset_index()
        age_col = ultimate_df.columns[0]
        rate_col = ultimate_df.columns[1]

    ages = ultimate_df[age_col].astype(int).values
    rates = ultimate_df[rate_col].astype(float).values

    # CSO tables are stored per-mille (q_x * 1000) in the SOA XML
    if cfg.get("rates_per_mille", False):
        rates = rates / 1000.0

    # Filter to requested age range
    min_age, max_age = cfg["min_age"], cfg["max_age"]
    mask = (ages >= min_age) & (ages <= max_age)
    ages, rates = ages[mask], rates[mask]

    return pl.DataFrame({"age": ages.tolist(), "rate": rates.tolist()})


def _pymort_select_ultimate_to_csv(xml: object, cfg: dict) -> pl.DataFrame:
    """
    Convert a pymort select-and-ultimate table to Polaris RE CSV schema.

    pymort returns:
        xml.values  → select table as MultiIndex DataFrame (issue_age, duration)
        xml.ultimate → ultimate table as Series indexed by attained_age

    Target schema:
        age, dur_1, dur_2, ..., dur_25, ultimate
    where age = issue age (ANB), dur_i = q_x in select year i,
    ultimate = q_x for attained age beyond select period.
    """
    import pandas as pd

    select_period = cfg["select_period"]
    min_age = cfg["min_age"]
    max_age = cfg["max_age"]

    # --- Select table ---
    select_raw: pd.DataFrame = xml.values  # type: ignore[union-attr]

    # Reset MultiIndex → columns: IssueAge (or Age), Duration (or Dur), value
    select_flat = select_raw.reset_index()
    cols = select_flat.columns.tolist()

    # Heuristic column identification — pymort column names vary slightly
    age_col = next(
        c for c in cols if any(k in str(c).lower() for k in ("issue", "age", "x"))
    )
    dur_col = next(
        c for c in cols if any(k in str(c).lower() for k in ("dur", "period", "t"))
        and c != age_col
    )
    rate_col = next(c for c in cols if c not in (age_col, dur_col))

    select_flat = select_flat.rename(
        columns={age_col: "issue_age", dur_col: "duration", rate_col: "qx"}
    )
    select_flat["issue_age"] = select_flat["issue_age"].astype(int)
    select_flat["duration"] = select_flat["duration"].astype(int)
    select_flat["qx"] = select_flat["qx"].astype(float)

    # Filter to target age range
    select_flat = select_flat[
        (select_flat["issue_age"] >= min_age) & (select_flat["issue_age"] <= max_age)
    ]

    # Pivot: rows = issue_age, columns = duration (1..select_period)
    pivot = select_flat.pivot(index="issue_age", columns="duration", values="qx")
    # Keep only durations 1..select_period
    dur_cols = [d for d in range(1, select_period + 1) if d in pivot.columns]
    pivot = pivot[dur_cols]
    pivot.columns = [f"dur_{d}" for d in dur_cols]
    pivot = pivot.reset_index().rename(columns={"issue_age": "age"})

    # --- Ultimate table ---
    # xml.ultimate is a pandas Series indexed by attained_age
    ultimate_series: pd.Series = xml.ultimate  # type: ignore[union-attr]
    ultimate_series.index = ultimate_series.index.astype(int)
    ultimate_series = ultimate_series.astype(float)

    # Map ultimate rates to issue_age:
    # Attained age at end of select period = issue_age + select_period
    # We use issue_age as the row key, consistent with SOA table layout.
    def get_ultimate(issue_age: int) -> float:
        attained = issue_age + select_period
        if attained in ultimate_series.index:
            return float(ultimate_series[attained])
        # Clamp to max available attained age
        return float(ultimate_series[min(attained, ultimate_series.index.max())])

    ages = pivot["age"].tolist()
    pivot["ultimate"] = [get_ultimate(a) for a in ages]

    return pl.from_pandas(pivot)


# ---------------------------------------------------------------------------
# Fallback path: Excel → CSV
# ---------------------------------------------------------------------------


def convert_via_excel(
    excel_dir: Path,
    output_dir: Path,
    table_type: str = "all",
) -> dict[str, bool]:
    """
    Convert manually downloaded SOA/CIA Excel files to Polaris RE CSV format.

    SOA VBT 2015 Excel layout (per file, one sex/smoker combination):
        Sheet "Select":
            Row 1: header — col 0 = "Issue Age", cols 1-25 = dur labels, col 26 = "Ult" or "Ultimate"
            Rows 2+: data — rates expressed as q_x * 1000 (per-mille)
        Sheet "Ultimate":
            Row 1: header — "Attained Age", "qx" (or similar)
            Rows 2+: data — rates per-mille

    CIA 2014 Excel layout is similar but sheet names and headers may differ.
    The --inspect flag can be used to print the actual headers before converting.
    """
    try:
        import openpyxl  # type: ignore[import]
    except ImportError:
        console.print(
            "[red]openpyxl not installed.[/red] Run:\n"
            "  uv add openpyxl\n  pip install openpyxl"
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    excel_files = sorted(excel_dir.glob("*.xlsx")) + sorted(excel_dir.glob("*.xls"))
    if not excel_files:
        console.print(f"[red]No Excel files found in {excel_dir}[/red]")
        return results

    console.print(f"\nFound {len(excel_files)} Excel file(s) in {excel_dir}")

    for xlsx_path in excel_files:
        console.print(f"\n  Processing: [cyan]{xlsx_path.name}[/cyan]")
        try:
            result = _convert_soa_excel_file(xlsx_path, output_dir)
            results.update(result)
        except Exception as exc:
            console.print(f"    [red]✗ Failed: {exc}[/red]")

    return results


def _inspect_excel(path: Path) -> None:
    """Print sheet names and first 3 rows of each sheet — useful for debugging."""
    try:
        import pandas as pd
        xl = pd.ExcelFile(path)
        console.print(f"\n[bold]Inspecting:[/bold] {path.name}")
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, nrows=3)
            console.print(f"  Sheet '{sheet}': columns = {df.columns.tolist()}")
            console.print(f"  First row: {df.iloc[0].tolist() if len(df) > 0 else '(empty)'}")
    except Exception as exc:
        console.print(f"  [red]Could not inspect: {exc}[/red]")


def _convert_soa_excel_file(
    path: Path,
    output_dir: Path,
) -> dict[str, bool]:
    """
    Convert a single SOA/CIA Excel file to one or more Polaris RE CSVs.

    Attempts to auto-detect:
    - Table type (select/ultimate or ultimate-only) from sheet names
    - Sex and smoker status from filename
    - Whether rates are per-mille or decimal
    """
    import pandas as pd

    results: dict[str, bool] = {}
    stem = path.stem.lower()

    # --- Detect sex ---
    if "male" in stem or "_m_" in stem or stem.endswith("_m"):
        sex = "male"
    elif "female" in stem or "_f_" in stem or stem.endswith("_f"):
        sex = "female"
    else:
        console.print(
            f"    [yellow]Cannot determine sex from filename '{path.name}'.[/yellow]\n"
            f"    Rename to include 'male' or 'female', or pass --sex explicitly."
        )
        return results

    # --- Detect smoker status ---
    if "nonsmoker" in stem or "non_smoker" in stem or "ns" in stem or "nons" in stem:
        smoker = "ns"
    elif "smoker" in stem:
        smoker = "smoker"
    elif "aggregate" in stem or "agg" in stem or "composite" in stem:
        smoker = "aggregate"
    else:
        console.print(
            f"    [yellow]Cannot determine smoker status from '{path.name}'.[/yellow]\n"
            f"    Rename to include 'smoker', 'nonsmoker'/'ns', or 'aggregate'."
        )
        return results

    # --- Detect source (SOA vs CIA) ---
    if "cia" in stem or "canadian" in stem:
        source_prefix = "cia_2014"
    elif "vbt" in stem or "soa" in stem:
        source_prefix = "soa_vbt_2015"
    elif "cso" in stem:
        source_prefix = "cso_2001"
    else:
        # Default to SOA VBT
        source_prefix = "soa_vbt_2015"
        console.print(
            f"    [yellow]Source not detected from filename — assuming soa_vbt_2015.[/yellow]"
        )

    output_key = f"{source_prefix}_{sex}_{smoker}"
    output_path = output_dir / f"{output_key}.csv"

    xl = pd.ExcelFile(path)
    sheet_names_lower = {s.lower(): s for s in xl.sheet_names}

    # --- Ultimate-only (CSO) ---
    if source_prefix == "cso_2001" or len(xl.sheet_names) == 1:
        df = _parse_ultimate_sheet(xl, sheet_names_lower, stem)
        pl_df = pl.from_pandas(df)
        pl_df.write_csv(output_path)
        console.print(f"    [green]✓[/green] {output_key}.csv  ({len(pl_df)} ages)")
        results[output_key] = True
        return results

    # --- Select-and-ultimate ---
    select_sheet = next(
        (sheet_names_lower[k] for k in sheet_names_lower
         if "select" in k or "s&u" in k or "su" in k),
        xl.sheet_names[0],
    )
    ultimate_sheet = next(
        (sheet_names_lower[k] for k in sheet_names_lower
         if "ultimate" in k or "ult" in k),
        xl.sheet_names[-1] if len(xl.sheet_names) > 1 else xl.sheet_names[0],
    )

    df_select = xl.parse(select_sheet, header=0)
    df_ultimate = xl.parse(ultimate_sheet, header=0)

    polaris_df = _reshape_select_ultimate(df_select, df_ultimate, source_prefix)
    pl_df = pl.from_pandas(polaris_df)
    pl_df.write_csv(output_path)
    console.print(
        f"    [green]✓[/green] {output_key}.csv  "
        f"({len(pl_df)} ages × {len(pl_df.columns) - 1} rate columns)"
    )
    results[output_key] = True
    return results


def _parse_ultimate_sheet(
    xl: object,
    sheet_names_lower: dict[str, str],
    stem: str,
) -> "pd.DataFrame":
    """Parse an ultimate-only sheet and return a clean age|rate DataFrame."""
    import pandas as pd

    sheet = list(sheet_names_lower.values())[0]
    df = xl.parse(sheet, header=0)  # type: ignore[union-attr]
    df.columns = [str(c).strip().lower() for c in df.columns]

    age_col = next((c for c in df.columns if "age" in c), df.columns[0])
    rate_col = next((c for c in df.columns if c != age_col), df.columns[1])

    df = df[[age_col, rate_col]].dropna()
    df[age_col] = df[age_col].astype(int)
    df[rate_col] = df[rate_col].astype(float)

    # Detect per-mille (rates > 1.0 are clearly per-mille)
    if df[rate_col].max() > 1.0:
        df[rate_col] = df[rate_col] / 1000.0

    return df.rename(columns={age_col: "age", rate_col: "rate"}).reset_index(drop=True)


def _reshape_select_ultimate(
    df_select: "pd.DataFrame",
    df_ultimate: "pd.DataFrame",
    source_prefix: str,
) -> "pd.DataFrame":
    """
    Reshape SOA/CIA select table (issue_age × duration) + ultimate column
    into Polaris RE schema: age, dur_1..dur_N, ultimate.

    SOA Excel select sheet layout:
        Row 0 (header): "Issue Age" | 1 | 2 | ... | 25 | "Ult" or "Ultimate"
        Subsequent rows: age | q_x values (per-mille)

    CIA Excel select sheet layout is similar but column labels may differ.
    """
    import pandas as pd

    df_select.columns = [str(c).strip() for c in df_select.columns]

    # Identify age column (first column)
    age_col = df_select.columns[0]
    df_select = df_select.dropna(subset=[age_col])
    df_select[age_col] = pd.to_numeric(df_select[age_col], errors="coerce")
    df_select = df_select.dropna(subset=[age_col])
    df_select[age_col] = df_select[age_col].astype(int)

    # Identify duration columns: numeric headers 1..25 or "1".."25"
    # and the ultimate column (labelled "Ult", "Ultimate", "26", etc.)
    rate_cols = [c for c in df_select.columns if c != age_col]
    duration_cols: list[str] = []
    ult_col: str | None = None

    for col in rate_cols:
        try:
            d = int(float(str(col)))
            if 1 <= d <= 30:
                duration_cols.append(col)
        except ValueError:
            if str(col).lower() in ("ult", "ultimate", "ult.", "u"):
                ult_col = col

    # If ultimate column not found separately, it may be embedded in duration cols
    # (some SOA files label it "26" for a 25-year select period)
    if ult_col is None and len(duration_cols) > 25:
        ult_col = duration_cols[-1]
        duration_cols = duration_cols[:-1]

    # Detect per-mille
    sample_rates = df_select[duration_cols[:3]].values.flatten()
    sample_rates = sample_rates[~np.isnan(sample_rates.astype(float))]
    is_per_mille = float(sample_rates.max()) > 1.0

    # Build output DataFrame
    output = pd.DataFrame()
    output["age"] = df_select[age_col].values

    for i, col in enumerate(duration_cols, start=1):
        vals = pd.to_numeric(df_select[col], errors="coerce").values.astype(float)
        if is_per_mille:
            vals = vals / 1000.0
        output[f"dur_{i}"] = vals

    # Ultimate column — from select sheet or ultimate sheet
    if ult_col is not None:
        ult_vals = pd.to_numeric(df_select[ult_col], errors="coerce").values.astype(float)
        if is_per_mille:
            ult_vals = ult_vals / 1000.0
        output["ultimate"] = ult_vals
    else:
        # Try to merge from separate ultimate sheet
        df_ultimate.columns = [str(c).strip().lower() for c in df_ultimate.columns]
        ult_age_col = next((c for c in df_ultimate.columns if "age" in c), df_ultimate.columns[0])
        ult_rate_col = next((c for c in df_ultimate.columns if c != ult_age_col), df_ultimate.columns[1])
        df_ultimate[ult_age_col] = pd.to_numeric(df_ultimate[ult_age_col], errors="coerce")
        df_ultimate[ult_rate_col] = pd.to_numeric(df_ultimate[ult_rate_col], errors="coerce")
        df_ultimate = df_ultimate.dropna()

        ult_rates = pd.to_numeric(df_ultimate[ult_rate_col], errors="coerce").values.astype(float)
        if float(ult_rates.max()) > 1.0:
            ult_rates = ult_rates / 1000.0

        ult_map = dict(zip(
            df_ultimate[ult_age_col].astype(int).tolist(),
            ult_rates.tolist(),
        ))
        # Map to issue_age (ultimate attained_age = issue_age + select_period)
        select_period = len(duration_cols)
        output["ultimate"] = output["age"].apply(
            lambda a: ult_map.get(a + select_period, ult_map.get(max(ult_map.keys()), np.nan))
        )

    return output.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_output(df: pl.DataFrame, cfg: dict) -> None:
    """Basic sanity checks on a converted Polaris RE mortality table."""
    min_age, max_age = cfg["min_age"], cfg["max_age"]
    n_expected = max_age - min_age + 1

    if "age" not in df.columns:
        raise ValueError("Output DataFrame missing 'age' column.")

    n_actual = len(df)
    if n_actual < n_expected:
        raise ValueError(
            f"Expected {n_expected} age rows ({min_age}-{max_age}), got {n_actual}."
        )

    rate_cols = [c for c in df.columns if c != "age"]
    for col in rate_cols:
        col_max = df[col].max()
        col_min = df[col].min()
        if col_min is not None and col_min < 0:
            raise ValueError(f"Column '{col}' contains negative rates.")
        if col_max is not None and col_max > 1.0:
            raise ValueError(
                f"Column '{col}' max={col_max:.4f} > 1.0 — likely still per-mille."
            )


def validate_outputs(output_dir: Path) -> bool:
    """Check all 10 required output CSVs exist and pass basic schema checks."""
    required_files = list(SOA_TABLE_REGISTRY.keys()) + list(CIA_EXCEL_REGISTRY.keys())

    results_table = RichTable(title="Polaris RE Mortality Table Validation")
    results_table.add_column("File", style="cyan")
    results_table.add_column("Ages")
    results_table.add_column("Rate cols")
    results_table.add_column("Min q_x")
    results_table.add_column("Max q_x")
    results_table.add_column("Status", style="bold")

    all_ok = True

    for key in required_files:
        path = output_dir / f"{key}.csv"
        if not path.exists():
            results_table.add_row(f"{key}.csv", "-", "-", "-", "-", "[red]MISSING[/red]")
            all_ok = False
            continue

        try:
            df = pl.read_csv(path)
            rate_cols = [c for c in df.columns if c != "age"]
            all_rates = df.select(rate_cols).to_numpy().flatten()
            all_rates = all_rates[~np.isnan(all_rates)]
            results_table.add_row(
                f"{key}.csv",
                str(len(df)),
                str(len(rate_cols)),
                f"{all_rates.min():.5f}",
                f"{all_rates.max():.5f}",
                "[green]OK[/green]",
            )
        except Exception as exc:
            results_table.add_row(f"{key}.csv", "-", "-", "-", "-", f"[red]ERROR: {exc}[/red]")
            all_ok = False

    console.print(results_table)
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert SOA/CIA mortality tables to Polaris RE CSV format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["pymort", "excel"],
        default="pymort",
        help="Conversion source: 'pymort' (download from mort.soa.org) or 'excel' (local files).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/mortality_tables"),
        help="Directory to write output CSVs (default: data/mortality_tables).",
    )
    parser.add_argument(
        "--excel-dir",
        type=Path,
        default=None,
        help="Directory containing downloaded SOA/CIA Excel files (required for --source excel).",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=None,
        metavar="TABLE_KEY",
        help=(
            "Subset of tables to convert (default: all). "
            f"Available: {', '.join(SOA_TABLE_REGISTRY.keys())}"
        ),
    )
    parser.add_argument(
        "--inspect",
        type=Path,
        default=None,
        metavar="EXCEL_FILE",
        help="Print sheet names and headers for a single Excel file (for debugging CIA files).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip conversion and only validate existing CSVs in --output-dir.",
    )

    args = parser.parse_args()

    console.print("\n[bold]Polaris RE — Mortality Table Converter[/bold]\n")

    # --inspect mode
    if args.inspect:
        _inspect_excel(args.inspect)
        return

    # --validate-only mode
    if args.validate_only:
        console.print(f"Validating CSVs in: {args.output_dir}\n")
        ok = validate_outputs(args.output_dir)
        sys.exit(0 if ok else 1)

    # Conversion
    if args.source == "pymort":
        console.print(
            "Source: [bold]pymort[/bold] (fetching from mort.soa.org)\n"
            f"Output: {args.output_dir}\n"
        )
        results = convert_via_pymort(args.output_dir, args.tables)

    else:  # excel
        if not args.excel_dir:
            console.print("[red]--excel-dir is required when --source excel is used.[/red]")
            sys.exit(1)
        console.print(
            f"Source: [bold]Excel files[/bold] in {args.excel_dir}\n"
            f"Output: {args.output_dir}\n"
        )
        results = convert_via_excel(args.excel_dir, args.output_dir)

    # Summary
    n_ok = sum(v for v in results.values())
    n_total = len(results)
    console.print(f"\nConverted {n_ok}/{n_total} tables.")

    # Validate outputs
    if n_ok > 0:
        console.print("\nValidating outputs...\n")
        validate_outputs(args.output_dir)

    sys.exit(0 if n_ok == n_total else 1)


if __name__ == "__main__":
    main()
