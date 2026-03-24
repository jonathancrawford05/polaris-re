#!/usr/bin/env python3
"""
convert_soa_tables.py — Download and convert SOA/CIA mortality tables to
Polaris RE CSV format.

PRIMARY PATH (recommended): Fetches SOA tables directly from mort.soa.org
via the `pymort` library. No manual download required for VBT 2015 / CSO 2001.

FALLBACK PATH: Converts the CIA2014 Excel workbook (222040T1e.xlsx) downloaded
from cia-ica.ca into the Polaris RE CSV schema.

TARGET CSV SCHEMA
-----------------
Select-and-ultimate (SOA VBT 2015, CIA2014):
    age, dur_1, dur_2, ..., dur_N, ultimate
    - age: issue age (ANB), integers 18-120
    - dur_1..dur_N: select-period annual q_x as decimals (NOT per-mille)
    - ultimate: post-select annual q_x as decimal

Ultimate-only (2001 CSO):
    age, rate
    - age: integers 0-120
    - rate: annual q_x as decimal

USAGE
-----
# Download VBT 2015 + CSO 2001 directly from mort.soa.org:
python scripts/convert_soa_tables.py --source pymort --output-dir data/mortality_tables

# Convert CIA2014 Excel workbook (222040T1e.xlsx):
python scripts/convert_soa_tables.py --source excel \\
    --excel-file ~/Downloads/222040T1e.xlsx \\
    --output-dir data/mortality_tables

# Validate all output CSVs:
python scripts/convert_soa_tables.py --validate-only --output-dir data/mortality_tables

# Inspect an unknown Excel file layout:
python scripts/convert_soa_tables.py --inspect ~/Downloads/someFile.xlsx

SOA TABLE IDs (mort.soa.org)
-----------------------------
VBT 2015 Smoker-Distinct ANB (select period = 25 years):
    3265  Male Non-Smoker   → soa_vbt_2015_male_ns.csv
    3266  Male Smoker       → soa_vbt_2015_male_smoker.csv
    3267  Female Non-Smoker → soa_vbt_2015_female_ns.csv
    3268  Female Smoker     → soa_vbt_2015_female_smoker.csv

2001 CSO ANB (ultimate-only, rates stored per-mille in XML):
    1441  Male              → cso_2001_male.csv
    1442  Female            → cso_2001_female.csv

CIA2014 Excel sheet → output file mapping (222040T1e.xlsx):
    MsmN  Male Smoker       → cia_2014_male_smoker.csv
    MnsN  Male Non-Smoker   → cia_2014_male_ns.csv
    FsmN  Female Smoker     → cia_2014_female_smoker.csv
    FnsN  Female Non-Smoker → cia_2014_female_ns.csv
    (N suffix = Age Nearest Birthday; select period = 20 years; rates per-mille)
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
# SOA table registry (pymort path)
# ---------------------------------------------------------------------------

SOA_TABLE_REGISTRY: dict[str, dict] = {
    "soa_vbt_2015_male_ns": {
        "table_id": 3265,
        "description": "2015 VBT Male Non-Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
    },
    "soa_vbt_2015_male_smoker": {
        "table_id": 3266,
        "description": "2015 VBT Male Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
    },
    "soa_vbt_2015_female_ns": {
        "table_id": 3267,
        "description": "2015 VBT Female Non-Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
    },
    "soa_vbt_2015_female_smoker": {
        "table_id": 3268,
        "description": "2015 VBT Female Smoker ANB",
        "select_period": 25,
        "table_type": "select_ultimate",
        "min_age": 18,
        "max_age": 120,
    },
    "cso_2001_male": {
        "table_id": 1136,
        "description": "2001 CSO Male Composite Select & Ultimate ANB",
        "select_period": 0,
        "table_type": "cso_ultimate",  # extract Tables[1] (ultimate)
        "min_age": 0,
        "max_age": 120,
        "rates_per_mille": False,  # rates already in decimal form
    },
    "cso_2001_female": {
        "table_id": 1139,
        "description": "2001 CSO Female Composite Select & Ultimate ANB",
        "select_period": 0,
        "table_type": "cso_ultimate",
        "min_age": 0,
        "max_age": 120,
        "rates_per_mille": False,
    },
}

# ---------------------------------------------------------------------------
# CIA2014 Excel sheet → output file mapping
#
# Layout in 222040T1e.xlsx (confirmed by inspection):
#   - 2 title/description rows to skip (skiprows=2 gives real headers on row 3)
#   - Real headers: "Issue Age" | 1 | 2 | ... | 20 | "Ult" | "Attd Age"
#   - Select period = 20 years
#   - Rates are per-mille (q_x * 1000); divide by 1000 for Polaris RE
#   - "Attd Age" column is the attained age label — drop it
# ---------------------------------------------------------------------------

CIA_SHEET_MAP: dict[str, dict] = {
    "MnsN": {
        "output_key": "cia_2014_male_ns",
        "description": "CIA2014 Male Non-Smoker ANB",
    },
    "MsmN": {
        "output_key": "cia_2014_male_smoker",
        "description": "CIA2014 Male Smoker ANB",
    },
    "FnsN": {
        "output_key": "cia_2014_female_ns",
        "description": "CIA2014 Female Non-Smoker ANB",
    },
    "FsmN": {
        "output_key": "cia_2014_female_smoker",
        "description": "CIA2014 Female Smoker ANB",
    },
}

CIA_SELECT_PERIOD = 20
CIA_MIN_AGE = 18
CIA_MAX_AGE = 115


# ---------------------------------------------------------------------------
# Primary path: pymort → CSV
# ---------------------------------------------------------------------------


def convert_via_pymort(output_dir: Path, table_keys: list[str] | None = None) -> dict[str, bool]:
    """Download SOA tables via pymort and write Polaris RE CSVs."""
    try:
        from pymort import MortXML  # type: ignore[import]
    except ImportError:
        console.print(
            "[red]pymort not installed.[/red] Run:\n  uv add pymort\n  pip install pymort"
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    keys = table_keys or list(SOA_TABLE_REGISTRY.keys())
    results: dict[str, bool] = {}

    for key in keys:
        if key not in SOA_TABLE_REGISTRY:
            console.print(f"[yellow]Unknown key '{key}' — skipping.[/yellow]")
            continue

        cfg = SOA_TABLE_REGISTRY[key]
        output_path = output_dir / f"{key}.csv"
        console.print(f"  Fetching {cfg['table_id']}: {cfg['description']} ...", end=" ")

        try:
            xml = MortXML.from_id(cfg["table_id"])

            if cfg["table_type"] in ("ultimate_only", "cso_ultimate"):
                df = _pymort_to_ultimate_csv(xml, cfg)
            else:
                df = _pymort_to_select_ultimate_csv(xml, cfg)

            _validate_output_df(df, cfg)
            df.write_csv(output_path)
            console.print(f"[green]✓[/green] → {output_path.name}")
            results[key] = True

        except Exception as exc:
            console.print(f"[red]✗ {exc}[/red]")
            results[key] = False

    return results


def _pymort_to_ultimate_csv(xml: object, cfg: dict) -> pl.DataFrame:
    """
    Convert a pymort ultimate-only or CSO table to Polaris RE schema: age | rate.

    For 'cso_ultimate' tables (e.g. table 1136/1139):
      Tables[0] = select table (Age × Duration MultiIndex)
      Tables[1] = ultimate table starting at age 25
    We use Tables[1] for ages 25+ and fill ages 0-24 from the select table
    at the highest available duration (last column of the select period).

    For 'ultimate_only' tables: Tables[0] is used directly.
    """
    import pandas as pd

    if cfg.get("table_type") == "cso_ultimate":
        # Pull ultimate rates from Tables[1]
        ult_raw: pd.DataFrame = xml.Tables[1].Values  # type: ignore[union-attr]
        ult_raw = ult_raw.reset_index()
        ult_raw.columns = [str(c).strip() for c in ult_raw.columns]
        age_col = ult_raw.columns[0]
        rate_col = ult_raw.columns[1]
        ages_ult = pd.to_numeric(ult_raw[age_col], errors="coerce").values
        rates_ult = pd.to_numeric(ult_raw[rate_col], errors="coerce").values.astype(float)

        # Fill ages 0 to (min_ult_age - 1) from select table at last duration
        # Tables[0] is MultiIndex (Age, Duration); pick the highest duration per age
        sel_raw: pd.DataFrame = xml.Tables[0].Values  # type: ignore[union-attr]
        sel_flat = sel_raw.reset_index()
        sel_flat.columns = [str(c).strip() for c in sel_flat.columns]
        # Last duration row per age = highest select-period rate (closest to ultimate)
        sel_last = (
            sel_flat.sort_values(sel_flat.columns[1])
            .groupby(sel_flat.columns[0])
            .last()
            .reset_index()
        )
        young_ages = pd.to_numeric(sel_last.iloc[:, 0], errors="coerce").values
        young_rates = pd.to_numeric(sel_last.iloc[:, 2], errors="coerce").values.astype(float)

        min_ult_age = int(ages_ult[~np.isnan(ages_ult)].min())
        young_mask = (young_ages < min_ult_age) & (~np.isnan(young_ages)) & (~np.isnan(young_rates))

        all_ages = np.concatenate(
            [young_ages[young_mask].astype(int), ages_ult[~np.isnan(ages_ult)].astype(int)]
        )
        all_rates = np.concatenate([young_rates[young_mask], rates_ult[~np.isnan(ages_ult)]])

        # Sort by age and filter to requested range
        order = np.argsort(all_ages)
        all_ages, all_rates = all_ages[order], all_rates[order]
        min_age, max_age = cfg["min_age"], cfg["max_age"]
        mask = (all_ages >= min_age) & (all_ages <= max_age) & (all_rates > -0.5)
        return pl.DataFrame({"age": all_ages[mask].tolist(), "rate": all_rates[mask].tolist()})

    raw: pd.DataFrame = xml.Tables[0].Values  # type: ignore[union-attr]
    raw = raw.reset_index()
    raw.columns = [str(c).strip() for c in raw.columns]

    age_col = raw.columns[0]
    rate_col = raw.columns[1]

    ages = pd.to_numeric(raw[age_col], errors="coerce").values
    rates = pd.to_numeric(raw[rate_col], errors="coerce").values.astype(float)

    if cfg.get("rates_per_mille", False):
        rates = rates / 1000.0

    min_age, max_age = cfg["min_age"], cfg["max_age"]
    # Drop only rows with NaN ages, NaN rates, or clearly invalid sentinel
    # values (rates < -0.5 catch -1 sentinels without discarding true zero
    # rates at juvenile ages). Do NOT filter on rates >= 0 — q_x = 0.0 is
    # valid at the youngest ages in some tables.
    valid = (
        ~np.isnan(ages.astype(float))
        & ~np.isnan(rates)
        & (rates > -0.5)  # sentinel guard only
        & (ages >= min_age)
        & (ages <= max_age)
    )
    return pl.DataFrame(
        {
            "age": ages[valid].astype(int).tolist(),
            "rate": rates[valid].tolist(),
        }
    )


def _pymort_to_select_ultimate_csv(xml: object, cfg: dict) -> pl.DataFrame:
    """
    Convert a pymort select-and-ultimate table to Polaris RE schema:
        age, dur_1, ..., dur_N, ultimate

    pymort API:
        xml.Tables[0].Values → select table, MultiIndex DataFrame (issue_age, duration)
        xml.Tables[1].Values → ultimate table, DataFrame indexed by attained_age

    VBT 2015 rates are already in q_x decimal form (not per-mille).
    """
    import pandas as pd

    select_period = cfg["select_period"]
    min_age = cfg["min_age"]
    max_age = cfg["max_age"]

    # --- Select table ---
    select_raw: pd.DataFrame = xml.Tables[0].Values  # type: ignore[union-attr]
    select_flat = select_raw.reset_index()
    select_flat.columns = [str(c).strip() for c in select_flat.columns]

    # Identify issue_age and duration columns heuristically
    cols = select_flat.columns.tolist()
    age_col = next(c for c in cols if any(k in str(c).lower() for k in ("issue", "age", "x")))
    dur_col = next(
        c
        for c in cols
        if any(k in str(c).lower() for k in ("dur", "period", "t", "year")) and c != age_col
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

    # Pivot: rows=issue_age, cols=duration 1..select_period
    pivot = select_flat.pivot(index="issue_age", columns="duration", values="qx")
    dur_cols_present = [d for d in range(1, select_period + 1) if d in pivot.columns]
    pivot = pivot[dur_cols_present]
    pivot.columns = pd.Index([f"dur_{d}" for d in dur_cols_present])
    pivot = pivot.reset_index().rename(columns={"issue_age": "age"})

    # --- Ultimate table ---
    ultimate_raw: pd.DataFrame = xml.Tables[1].Values  # type: ignore[union-attr]
    ultimate_raw = ultimate_raw.reset_index()
    ultimate_raw.columns = [str(c).strip() for c in ultimate_raw.columns]
    ult_age_col = ultimate_raw.columns[0]
    ult_rate_col = ultimate_raw.columns[1]
    ultimate_raw[ult_age_col] = ultimate_raw[ult_age_col].astype(int)
    ultimate_raw[ult_rate_col] = ultimate_raw[ult_rate_col].astype(float)
    ult_map: dict[int, float] = dict(
        zip(ultimate_raw[ult_age_col].tolist(), ultimate_raw[ult_rate_col].tolist())
    )

    # Map ultimate rate to each issue_age row:
    # attained_age at end of select = issue_age + select_period
    max_ult_age = max(ult_map.keys())

    def _get_ult(issue_age: int) -> float:
        att = issue_age + select_period
        return ult_map.get(min(att, max_ult_age), float("nan"))

    pivot["ultimate"] = pivot["age"].apply(_get_ult)

    return pl.from_pandas(pivot)


# ---------------------------------------------------------------------------
# CIA2014 Excel path
# ---------------------------------------------------------------------------


def convert_cia_excel(excel_path: Path, output_dir: Path) -> dict[str, bool]:
    """
    Parse CIA2014 Excel workbook (222040T1e.xlsx) and write Polaris RE CSVs.

    Confirmed layout (from --inspect output and screenshot):
      - Sheet names: MnsN, MsmN, FnsN, FsmN  (N = ANB)
      - Row 0: "CIA2014 mortality rates, age nearest birthday"  ← title, skip
      - Row 1: "Male smoker" etc.                               ← description, skip
      - Row 2 (skiprows=2): real headers →
            "Issue Age" | 1 | 2 | ... | 20 | "Ult" | "Attd Age"
      - Rates: per-mille (divide by 1000)
      - "Attd Age" column: attained age label — drop
      - Select period: 20 years
    """
    try:
        import pandas as pd
    except ImportError:
        console.print("[red]pandas not installed.[/red] Run: uv add pandas")
        sys.exit(1)

    if not excel_path.exists():
        console.print(f"[red]File not found: {excel_path}[/red]")
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    xl = pd.ExcelFile(excel_path)
    available_sheets = xl.sheet_names
    console.print(f"  Sheets in workbook: {available_sheets}")

    for sheet_name, meta in CIA_SHEET_MAP.items():
        output_key = meta["output_key"]
        output_path = output_dir / f"{output_key}.csv"
        console.print(f"\n  Processing sheet '{sheet_name}': {meta['description']} ...", end=" ")

        # Try exact sheet name first, then case-insensitive fallback
        matched_sheet = next(
            (s for s in available_sheets if s == sheet_name),
            next(
                (s for s in available_sheets if s.lower() == sheet_name.lower()),
                None,
            ),
        )

        if matched_sheet is None:
            console.print(f"[yellow]✗ Sheet '{sheet_name}' not found — skipping.[/yellow]")
            console.print(f"    Available sheets: {available_sheets}")
            results[output_key] = False
            continue

        try:
            df = _parse_cia2014_sheet(xl, matched_sheet)
            pl_df = pl.from_pandas(df)
            _validate_output_df(
                pl_df,
                {
                    "min_age": CIA_MIN_AGE,
                    "max_age": CIA_MAX_AGE,
                },
            )
            pl_df.write_csv(output_path)
            console.print(
                f"[green]✓[/green] → {output_path.name} "
                f"({len(pl_df)} ages × {len(pl_df.columns) - 1} rate cols)"
            )
            results[output_key] = True

        except Exception as exc:
            console.print(f"[red]✗ {exc}[/red]")
            results[output_key] = False

    return results


def _parse_cia2014_sheet(xl: object, sheet_name: str) -> pd.DataFrame:
    """
    Parse one CIA2014 ANB sheet into a Polaris RE select-and-ultimate DataFrame.

    Confirmed layout (from inspect + screenshot of 222040T1e.xlsx):
      Row 0: title  "CIA2014 mortality rates, age nearest birthday"
      Row 1: blank
      Row 2: sub-header  "Issue" | "Policy year" | ... | "Attd"   ← skip
      Row 3: real headers  NaN/blank | 1 | 2 | ... | 20 | "Ult" | "Attd"  ← use
      Row 4+: data

    So skiprows=3 is correct. The first column header will be blank/NaN;
    we rename it to "age". Duration columns are labelled 1..20 (integers).
    Rates are per-mille — divided by 1000 on output.
    """
    import pandas as pd

    df = xl.parse(sheet_name, skiprows=3, header=0)  # type: ignore[union-attr]

    # Rename columns to clean strings; blank first column → "age"
    new_cols: list[str] = []
    for i, c in enumerate(df.columns):
        s = str(c).strip()
        if s in ("", "nan", "None") or (i == 0 and not s.lstrip("-").replace(".", "").isdigit()):
            new_cols.append("age" if i == 0 else f"_drop_{i}")
        else:
            new_cols.append(s)
    df.columns = pd.Index(new_cols)

    # Drop completely empty rows
    df = df.dropna(how="all")

    # Parse and filter the age (issue age) column
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df = df.dropna(subset=["age"])
    df["age"] = df["age"].astype(int)
    df = df[(df["age"] >= CIA_MIN_AGE) & (df["age"] <= CIA_MAX_AGE)].copy()

    # Identify duration columns (numeric labels 1..20) and "Ult" column.
    # Stop at first non-numeric, non-duration column after the durations.
    duration_cols: list[str] = []
    ult_col: str | None = None

    for col in df.columns:
        if col == "age" or col.startswith("_drop_"):
            continue
        col_lower = col.lower().strip()
        if col_lower in ("ult", "ultimate", "ult."):
            ult_col = col
            break  # everything after Ult (e.g. "Attd") is discarded
        try:
            d = int(float(col))
            if 1 <= d <= CIA_SELECT_PERIOD:
                duration_cols.append(col)
        except ValueError:
            pass  # ignore non-numeric, non-Ult columns

    if ult_col is None:
        raise ValueError(
            f"Could not find 'Ult' column in sheet '{sheet_name}'. "
            f"Columns after parsing: {df.columns.tolist()}"
        )

    if len(duration_cols) != CIA_SELECT_PERIOD:
        raise ValueError(
            f"Expected {CIA_SELECT_PERIOD} duration columns, "
            f"found {len(duration_cols)}: {duration_cols}"
        )

    # Build output DataFrame — divide per-mille rates by 1000
    output = pd.DataFrame()
    output["age"] = df["age"].values

    for i, col in enumerate(duration_cols, start=1):
        vals = pd.to_numeric(df[col], errors="coerce").values.astype(float)
        output[f"dur_{i}"] = vals / 1000.0

    ult_vals = pd.to_numeric(df[ult_col], errors="coerce").values.astype(float)
    output["ultimate"] = ult_vals / 1000.0

    # Sanity check: if max rate is still tiny after dividing by 1000,
    # the source rates were already in decimal form — undo the division.
    all_rate_vals = output[[c for c in output.columns if c != "age"]].values.flatten()
    all_rate_vals = all_rate_vals[~np.isnan(all_rate_vals)]
    if len(all_rate_vals) > 0 and all_rate_vals.max() < 0.001:
        console.print(
            "    [yellow]Warning: max rate after /1000 is "
            f"{all_rate_vals.max():.6f} — source appears already decimal. "
            "Multiplying back by 1000.[/yellow]"
        )
        for col in output.columns:
            if col != "age":
                output[col] = output[col] * 1000.0

    return output.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_output_df(df: pl.DataFrame, cfg: dict) -> None:
    """Sanity check: age coverage, rate bounds."""
    if "age" not in df.columns:
        raise ValueError("Missing 'age' column.")

    rate_cols = [c for c in df.columns if c != "age"]
    for col in rate_cols:
        col_max = df[col].max()
        col_min = df[col].min()
        if col_min is not None and float(col_min) < 0:
            raise ValueError(f"Column '{col}' has negative rates.")
        if col_max is not None and float(col_max) > 1.0:
            raise ValueError(f"Column '{col}' max={float(col_max):.4f} > 1.0 — still per-mille?")


def validate_outputs(output_dir: Path) -> bool:
    """Check all required CSVs exist and pass schema checks."""
    required = list(SOA_TABLE_REGISTRY.keys()) + list(
        m["output_key"] for m in CIA_SHEET_MAP.values()
    )

    tbl = RichTable(title="Polaris RE Mortality Table Validation")
    tbl.add_column("File", style="cyan")
    tbl.add_column("Ages")
    tbl.add_column("Rate cols")
    tbl.add_column("Min q_x")
    tbl.add_column("Max q_x")
    tbl.add_column("Status", style="bold")

    all_ok = True
    for key in required:
        path = output_dir / f"{key}.csv"
        if not path.exists():
            tbl.add_row(f"{key}.csv", "-", "-", "-", "-", "[red]MISSING[/red]")
            all_ok = False
            continue
        try:
            df = pl.read_csv(path)
            rate_cols = [c for c in df.columns if c != "age"]
            all_rates = df.select(rate_cols).to_numpy().flatten().astype(float)
            all_rates = all_rates[~np.isnan(all_rates)]
            tbl.add_row(
                f"{key}.csv",
                str(len(df)),
                str(len(rate_cols)),
                f"{all_rates.min():.6f}",
                f"{all_rates.max():.5f}",
                "[green]OK[/green]",
            )
        except Exception as exc:
            tbl.add_row(f"{key}.csv", "-", "-", "-", "-", f"[red]ERROR: {exc}[/red]")
            all_ok = False

    console.print(tbl)
    return all_ok


def _inspect_excel(path: Path) -> None:
    """Print sheet names and first 5 rows of each sheet for debugging."""
    try:
        import pandas as pd

        xl = pd.ExcelFile(path)
        console.print(f"\n[bold]Inspecting:[/bold] {path.name}")
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, nrows=5)
            console.print(f"\n  Sheet '[cyan]{sheet}[/cyan]':")
            console.print(f"    columns = {df.columns.tolist()}")
            for i, row in df.iterrows():
                console.print(f"    row {i}: {row.tolist()}")
    except Exception as exc:
        console.print(f"  [red]Could not inspect: {exc}[/red]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert SOA/CIA mortality tables to Polaris RE CSV format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["pymort", "excel"],
        default="pymort",
        help="'pymort' = download VBT2015/CSO2001 from mort.soa.org; 'excel' = CIA2014 xlsx.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/mortality_tables"),
        help="Directory for output CSVs (default: data/mortality_tables).",
    )
    parser.add_argument(
        "--excel-file",
        type=Path,
        default=None,
        help="Path to CIA2014 Excel file (222040T1e.xlsx). Required for --source excel.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=None,
        metavar="KEY",
        help=f"Subset of SOA tables to fetch. Available: {', '.join(SOA_TABLE_REGISTRY)}",
    )
    parser.add_argument(
        "--inspect",
        type=Path,
        default=None,
        metavar="EXCEL_FILE",
        help="Print sheet names and first rows of an Excel file for debugging.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip conversion — just validate existing CSVs in --output-dir.",
    )

    args = parser.parse_args()
    console.print("\n[bold]Polaris RE — Mortality Table Converter[/bold]\n")

    if args.inspect:
        _inspect_excel(args.inspect)
        return

    if args.validate_only:
        console.print(f"Validating CSVs in: {args.output_dir}\n")
        ok = validate_outputs(args.output_dir)
        sys.exit(0 if ok else 1)

    if args.source == "pymort":
        console.print(f"Source: [bold]pymort[/bold] → mort.soa.org\nOutput: {args.output_dir}\n")
        results = convert_via_pymort(args.output_dir, args.tables)
    else:
        if not args.excel_file:
            console.print("[red]--excel-file is required with --source excel.[/red]")
            sys.exit(1)
        console.print(
            f"Source: [bold]CIA2014 Excel[/bold] {args.excel_file}\nOutput: {args.output_dir}\n"
        )
        results = convert_cia_excel(args.excel_file, args.output_dir)

    n_ok = sum(v for v in results.values())
    n_total = len(results)
    console.print(f"\nConverted {n_ok}/{n_total} tables.")

    if n_ok > 0:
        console.print("\nValidating outputs...\n")
        validate_outputs(args.output_dir)

    sys.exit(0 if n_ok == n_total else 1)


if __name__ == "__main__":
    main()
