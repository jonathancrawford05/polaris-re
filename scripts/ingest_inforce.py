#!/usr/bin/env python3
"""
ingest_inforce.py — Normalise raw cedant inforce data to Polaris RE schema.

Reads a raw CSV/Excel file from a cedant, applies a YAML mapping config
to rename columns, translate codes, and fill defaults, then writes a
normalised Polaris RE inforce CSV.

Usage:
    python scripts/ingest_inforce.py --input data/raw/cedant_block.csv --config mapping.yaml --output data/normalised_block.csv
"""

import argparse
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("rich not installed. Run: uv sync")
    sys.exit(1)

console = Console()


def main() -> None:
    """CLI entry point for cedant inforce data ingestion."""
    parser = argparse.ArgumentParser(
        description="Normalise raw cedant inforce data to Polaris RE schema."
    )
    parser.add_argument("--input", type=Path, required=True, help="Raw cedant data file.")
    parser.add_argument("--config", type=Path, required=True, help="YAML mapping config file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/normalised_block.csv"),
        help="Output normalised CSV path.",
    )
    parser.add_argument("--validate-only", action="store_true", help="Only validate, do not write.")
    args = parser.parse_args()

    console.print("[bold]Polaris RE — Inforce Data Ingestion[/bold]\n")

    # Lazy imports to avoid import errors if polaris_re not installed
    from polaris_re.utils.ingestion import IngestConfig, ingest_cedant_data, validate_inforce_df

    # Load mapping config
    console.print(f"Loading mapping config: {args.config}")
    config = IngestConfig.from_yaml(args.config)

    # Ingest and normalise
    console.print(f"Reading raw data: {args.input}")
    df = ingest_cedant_data(args.input, config)
    console.print(f"  Normalised {len(df)} policies.\n")

    # Validate
    report = validate_inforce_df(df)

    # Summary table
    summary = Table(title="Data Quality Report")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value")
    summary.add_row("Policies", f"{report.n_policies:,}")
    summary.add_row("Total Face Amount", f"${report.total_face_amount:,.0f}")
    summary.add_row("Mean Age", f"{report.mean_age:.1f}")
    summary.add_row("Sex Split", str(report.sex_split))
    summary.add_row("Smoker Split", str(report.smoker_split))
    console.print(summary)

    if report.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in report.warnings:
            console.print(f"  ⚠ {w}")

    if report.errors:
        console.print("\n[red]Errors:[/red]")
        for e in report.errors:
            console.print(f"  ✗ {e}")
        if not args.validate_only:
            console.print("\n[red]Aborting due to validation errors.[/red]")
            sys.exit(1)
    else:
        console.print("\n[green]✓ All validation checks passed.[/green]")

    if not args.validate_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.write_csv(args.output)
        console.print(f"\n[green]Written normalised data to {args.output}[/green]")


if __name__ == "__main__":
    main()
