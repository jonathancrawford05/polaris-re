#!/usr/bin/env python3
"""
convert_lapse_tables.py — Convert lapse data sources to Polaris RE CSV schema.

Converts lapse experience data from external formats (SOA LLAT 2014 Excel
workbooks or generic Excel/CSV) into the canonical Polaris RE lapse CSV
schema: ``policy_year,rate``.

Usage:
    python scripts/convert_lapse_tables.py --source llat --input data/raw/llat_2014.xlsx --output-dir data/lapse_tables
    python scripts/convert_lapse_tables.py --source excel --input data/raw/cedant_lapse.xlsx --output-dir data/lapse_tables --sheet "NS Male"
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import polars as pl
except ImportError:
    print("polars not installed. Run: uv sync")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table as RichTable
except ImportError:
    print("rich not installed. Run: uv sync")
    sys.exit(1)

console = Console()


def _generate_sample_llat(output_dir: Path) -> list[Path]:
    """
    Generate sample LLAT-2014-style lapse tables as CSV files.

    Since the actual SOA LLAT 2014 workbook requires a licence, this
    generates synthetic tables that follow the same structure and
    approximate shape of real lapse experience.

    Returns:
        List of written file paths.
    """
    written: list[Path] = []

    # Typical term life lapse pattern: high in year 1, declining to ultimate
    base_rates = {
        1: 0.0800,
        2: 0.0550,
        3: 0.0420,
        4: 0.0380,
        5: 0.0350,
        6: 0.0330,
        7: 0.0310,
        8: 0.0300,
        9: 0.0290,
        10: 0.0280,
        11: 0.0270,
        12: 0.0260,
        13: 0.0250,
        14: 0.0250,
        15: 0.0250,
        16: 0.0250,
        17: 0.0250,
        18: 0.0250,
        19: 0.0250,
        20: 0.0250,
    }

    # Smoker/non-smoker multipliers (smokers lapse slightly more)
    configs = [
        ("llat_2014_ns.csv", 1.00, "LLAT 2014 Non-Smoker"),
        ("llat_2014_smoker.csv", 1.15, "LLAT 2014 Smoker"),
    ]

    for filename, mult, desc in configs:
        rows = []
        for year, rate in sorted(base_rates.items()):
            adjusted = min(rate * mult, 1.0)
            rows.append({"policy_year": year, "rate": round(adjusted, 6)})
        df = pl.DataFrame(rows)
        path = output_dir / filename
        df.write_csv(path)
        written.append(path)
        console.print(f"  [green]✓[/green] {desc} → {path}")

    return written


def convert_from_excel(
    input_path: Path,
    output_dir: Path,
    sheet_name: str | None = None,
    year_col: str = "policy_year",
    rate_col: str = "rate",
) -> Path:
    """
    Convert a generic Excel or CSV file to Polaris RE lapse schema.

    Args:
        input_path:  Source file (.xlsx, .xls, or .csv).
        output_dir:  Directory for output CSV.
        sheet_name:  Excel sheet name (ignored for CSV).
        year_col:    Column name for policy year in source.
        rate_col:    Column name for lapse rate in source.

    Returns:
        Path to written CSV.
    """
    suffix = input_path.suffix.lower()

    if suffix == ".csv":
        df = pl.read_csv(input_path)
    elif suffix in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError:
            console.print(
                "[red]pandas + openpyxl required for Excel input. Run: uv sync --all-extras[/red]"
            )
            sys.exit(1)
        pdf = pd.read_excel(input_path, sheet_name=sheet_name)
        df = pl.from_pandas(pdf)
    else:
        console.print(f"[red]Unsupported file type: {suffix}[/red]")
        sys.exit(1)

    # Rename columns to canonical schema
    if year_col != "policy_year" and year_col in df.columns:
        df = df.rename({year_col: "policy_year"})
    if rate_col != "rate" and rate_col in df.columns:
        df = df.rename({rate_col: "rate"})

    if "policy_year" not in df.columns or "rate" not in df.columns:
        console.print(
            f"[red]Required columns not found. Got: {df.columns}. "
            f"Need 'policy_year' and 'rate' (or specify --year-col / --rate-col).[/red]"
        )
        sys.exit(1)

    # Keep only the two required columns and sort
    df = df.select(["policy_year", "rate"]).sort("policy_year")

    # Validate
    rates = df["rate"].to_numpy()
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        console.print("[red]Error: rates outside [0, 1] detected.[/red]")
        sys.exit(1)

    output_name = input_path.stem + "_polaris.csv"
    output_path = output_dir / output_name
    df.write_csv(output_path)
    console.print(f"  [green]✓[/green] Converted → {output_path}")

    return output_path


def main() -> None:
    """CLI entry point for lapse table conversion."""
    parser = argparse.ArgumentParser(description="Convert lapse data to Polaris RE CSV schema.")
    parser.add_argument(
        "--source",
        choices=["llat", "excel"],
        required=True,
        help="Source type: 'llat' generates synthetic LLAT-2014 tables, "
        "'excel' converts a generic Excel/CSV file.",
    )
    parser.add_argument("--input", type=Path, help="Input file path (required for --source excel).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/lapse_tables"),
        help="Output directory for converted CSVs.",
    )
    parser.add_argument("--sheet", type=str, default=None, help="Excel sheet name.")
    parser.add_argument(
        "--year-col", type=str, default="policy_year", help="Source year column name."
    )
    parser.add_argument("--rate-col", type=str, default="rate", help="Source rate column name.")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    console.print("[bold]Polaris RE — Lapse Table Converter[/bold]\n")

    if args.source == "llat":
        console.print("Generating synthetic LLAT-2014 lapse tables...")
        paths = _generate_sample_llat(args.output_dir)

        # Summary table
        summary = RichTable(title="Generated Lapse Tables")
        summary.add_column("File")
        summary.add_column("Policy Years")
        summary.add_column("Year 1 Rate")
        summary.add_column("Ultimate Rate")
        for p in paths:
            df = pl.read_csv(p)
            summary.add_row(
                p.name,
                str(len(df)),
                f"{df['rate'][0]:.4f}",
                f"{df['rate'][-1]:.4f}",
            )
        console.print(summary)

    elif args.source == "excel":
        if args.input is None:
            console.print("[red]--input is required for --source excel[/red]")
            sys.exit(1)
        convert_from_excel(
            args.input,
            args.output_dir,
            sheet_name=args.sheet,
            year_col=args.year_col,
            rate_col=args.rate_col,
        )

    console.print("\n[green]Done.[/green]")


if __name__ == "__main__":
    main()
