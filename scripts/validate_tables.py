#!/usr/bin/env python3
"""
validate_tables.py — Validate that all required mortality table CSV files
are present in $POLARIS_DATA_DIR and conform to the expected schema.

Usage:
    python scripts/validate_tables.py
    python scripts/validate_tables.py --data-dir /path/to/data

Run this before any projection to ensure all table files are correctly formatted.
"""

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

REQUIRED_TABLES = [
    # (filename, select_period, description)
    ("soa_vbt_2015_male_ns.csv",       25, "SOA VBT 2015 Male Non-Smoker"),
    ("soa_vbt_2015_male_smoker.csv",   25, "SOA VBT 2015 Male Smoker"),
    ("soa_vbt_2015_female_ns.csv",     25, "SOA VBT 2015 Female Non-Smoker"),
    ("soa_vbt_2015_female_smoker.csv", 25, "SOA VBT 2015 Female Smoker"),
    ("cia_2014_male_ns.csv",           25, "CIA 2014 Male Non-Smoker"),
    ("cia_2014_male_smoker.csv",       25, "CIA 2014 Male Smoker"),
    ("cia_2014_female_ns.csv",         25, "CIA 2014 Female Non-Smoker"),
    ("cia_2014_female_smoker.csv",     25, "CIA 2014 Female Smoker"),
    ("cso_2001_male.csv",               0, "2001 CSO Male (ultimate only)"),
    ("cso_2001_female.csv",             0, "2001 CSO Female (ultimate only)"),
]


def validate_tables(data_dir: Path) -> bool:
    """
    Check all required table files exist and (once load_mortality_csv is implemented)
    validate their contents.

    Returns True if all tables are valid, False otherwise.
    """
    table_dir = data_dir / "mortality_tables"

    results_table = Table(title="Mortality Table Validation", show_header=True)
    results_table.add_column("File", style="cyan")
    results_table.add_column("Description")
    results_table.add_column("Status", style="bold")

    all_ok = True

    for filename, select_period, description in REQUIRED_TABLES:
        path = table_dir / filename
        if not path.exists():
            results_table.add_row(filename, description, "[red]MISSING[/red]")
            all_ok = False
        else:
            # TODO: Call load_mortality_csv(path, select_period) here once implemented
            # and catch PolarisValidationError for invalid tables.
            results_table.add_row(filename, description, "[green]FOUND[/green]")

    console.print(results_table)

    if all_ok:
        console.print("\n[green]✓ All required mortality tables present.[/green]")
    else:
        console.print(
            "\n[red]✗ Some tables are missing.[/red] "
            "Download from SOA/CIA and place in $POLARIS_DATA_DIR/mortality_tables/"
        )

    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Polaris RE mortality table files.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("POLARIS_DATA_DIR", "data")),
        help="Path to the Polaris data directory (default: $POLARIS_DATA_DIR or ./data)",
    )
    args = parser.parse_args()

    console.print(f"[bold]Polaris RE — Table Validation[/bold]")
    console.print(f"Data directory: {args.data_dir}\n")

    ok = validate_tables(args.data_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
