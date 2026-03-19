"""
Polaris RE — Command Line Interface.

Entry point: `polaris` (registered in pyproject.toml [project.scripts])

Commands:
    polaris price     — run a deal pricing pipeline from YAML/JSON config
    polaris scenario  — run scenario analysis with tabular output
    polaris uq        — run Monte Carlo UQ with summary statistics
    polaris validate  — validate inforce CSV, mortality tables, assumption sets
    polaris version   — display package version information

Rich is used for all terminal output: coloured tables, progress bars, panels.
All commands accept --config / --output arguments and write JSON results to disk.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import polaris_re

__all__ = ["app"]

app = typer.Typer(
    name="polaris",
    help="Polaris RE — Life Reinsurance Cash Flow Projection & Pricing Engine",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _header() -> None:
    """Print the Polaris RE header panel."""
    console.print(
        Panel(
            f"[bold cyan]Polaris RE[/bold cyan]  [dim]v{polaris_re.__version__}[/dim]\n"
            "[dim]Life Reinsurance Cash Flow Projection & Pricing Engine[/dim]",
            border_style="cyan",
        )
    )


def _load_json_config(config_path: Path) -> dict:  # type: ignore[type-arg]
    """Load and return a JSON or YAML config file as a plain dict."""
    if not config_path.exists():
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(code=1)
    try:
        text = config_path.read_text()
        return json.loads(text)  # type: ignore[return-value]
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Invalid JSON in {config_path}: {exc}")
        raise typer.Exit(code=1) from exc


def _write_output(data: dict, output_path: Path | None, default_name: str) -> None:  # type: ignore[type-arg]
    """Write result dict to JSON file or print summary to console."""
    if output_path is not None:
        output_path.write_text(json.dumps(data, indent=2, default=str))
        console.print(f"[green]Results written to:[/green] {output_path}")
    else:
        console.print_json(json.dumps(data, indent=2, default=str))


def _build_demo_pipeline() -> tuple:  # type: ignore[type-arg]
    """
    Build a minimal demo pricing pipeline using synthetic data.

    Used when a command is invoked without a real config file (demo mode).
    Returns (inforce, assumptions, config, treaty).
    """

    from pathlib import Path

    import numpy as np

    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
    from polaris_re.core.projection import ProjectionConfig
    from polaris_re.reinsurance.yrt import YRTTreaty
    from polaris_re.utils.table_io import MortalityTableArray

    # Synthetic mortality: 0.001 q_x for all ages (ages 18-120, ultimate-only)
    n_ages = 121 - 18  # 103 ages
    qx = np.full(n_ages, 0.001, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)  # shape (103, 1) — single column = ultimate
    table_array = MortalityTableArray(
        rates=rates_2d,
        min_age=18,
        max_age=120,
        select_period=0,
        source_file=Path("synthetic"),
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.CSO_2001,
        table_name="Synthetic Demo",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.UNKNOWN,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.05, 2: 0.04, 3: 0.03, "ultimate": 0.02})
    assumptions = AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version="demo-v1",
        effective_date=date.today(),
    )

    policy = Policy(
        policy_id="DEMO001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="PREFERRED",
        face_amount=500_000.0,
        annual_premium=1_200.0,
        policy_term=20,
        duration_inforce=0,
        reinsurance_cession_pct=0.0,
        issue_date=date(2010, 1, 1),
        valuation_date=date.today(),
        product_type=ProductType.TERM,
    )
    inforce = InforceBlock(policies=[policy])

    config = ProjectionConfig(
        valuation_date=date.today(),
        projection_horizon_years=20,
        discount_rate=0.06,
    )

    treaty = YRTTreaty(
        cession_pct=0.90,
        total_face_amount=500_000.0,
    )
    return inforce, assumptions, config, treaty


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("version")
def version_cmd() -> None:
    """Display Polaris RE version information."""
    _header()
    console.print(f"Version: [bold]{polaris_re.__version__}[/bold]")
    console.print(f"Python:  [bold]{sys.version.split()[0]}[/bold]")


@app.command("price")
def price_cmd(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to pricing config JSON file."),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write JSON results. Defaults to stdout."),
    ] = None,
    hurdle_rate: Annotated[
        float,
        typer.Option("--hurdle-rate", "-r", help="Annual hurdle rate for profit test (e.g. 0.10)."),
    ] = 0.10,
) -> None:
    """
    [bold]Run a deal pricing pipeline.[/bold]

    Runs the full pipeline: InforceBlock → AssumptionSet → TermLife → YRT Treaty → ProfitTester.

    If no --config is supplied, runs in demo mode with synthetic data.
    """
    _header()

    from polaris_re.analytics.profit_test import ProfitTester
    from polaris_re.products.term_life import TermLife

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Building pipeline...", total=None)
        inforce, assumptions, config, treaty = _build_demo_pipeline()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running projection...", total=None)
        product = TermLife(inforce=inforce, assumptions=assumptions, config=config)
        gross = product.project()
        net, _ = treaty.apply(gross)
        tester = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate)
        result = tester.run()
        progress.update(task, completed=True)

    # Display results table
    table = Table(title="Profit Test Results", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    irr_str = f"{result.irr:.2%}" if result.irr is not None else "N/A"
    be_str = f"Year {result.breakeven_year}" if result.breakeven_year is not None else "Never"

    table.add_row("Hurdle Rate", f"{result.hurdle_rate:.2%}")
    table.add_row("PV Profits", f"${result.pv_profits:,.0f}")
    table.add_row("PV Premiums", f"${result.pv_premiums:,.0f}")
    table.add_row("Profit Margin", f"{result.profit_margin:.2%}")
    table.add_row("IRR", irr_str)
    table.add_row("Break-even", be_str)
    table.add_row("Total Undiscounted Profit", f"${result.total_undiscounted_profit:,.0f}")

    console.print(table)

    output_data = {
        "hurdle_rate": result.hurdle_rate,
        "pv_profits": result.pv_profits,
        "pv_premiums": result.pv_premiums,
        "profit_margin": result.profit_margin,
        "irr": result.irr,
        "breakeven_year": result.breakeven_year,
        "total_undiscounted_profit": result.total_undiscounted_profit,
        "profit_by_year": result.profit_by_year.tolist(),
    }
    _write_output(output_data, output_path, "price_result")


@app.command("scenario")
def scenario_cmd(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to scenario config JSON file."),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write JSON results."),
    ] = None,
    hurdle_rate: Annotated[
        float,
        typer.Option("--hurdle-rate", "-r", help="Annual hurdle rate for profit test."),
    ] = 0.10,
) -> None:
    """
    [bold]Run scenario analysis.[/bold]

    Applies standard stress scenarios (mortality shock, lapse stress, rate shock)
    to the base pricing assumption set and reports PV profit sensitivities.
    """
    _header()

    from polaris_re.analytics.scenario import ScenarioRunner

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running scenarios...", total=None)
        inforce, assumptions, config, treaty = _build_demo_pipeline()
        runner = ScenarioRunner(
            inforce=inforce,
            base_assumptions=assumptions,
            config=config,
            treaty=treaty,
            hurdle_rate=hurdle_rate,
        )
        results = runner.run()

    # Display scenario table
    table = Table(title="Scenario Analysis", border_style="cyan")
    table.add_column("Scenario", style="bold")
    table.add_column("PV Profits", justify="right")
    table.add_column("Profit Margin", justify="right")
    table.add_column("IRR", justify="right")

    all_rows = []
    for name, res in results.scenarios:
        irr_str = f"{res.irr:.2%}" if res.irr is not None else "N/A"
        table.add_row(
            name,
            f"${res.pv_profits:,.0f}",
            f"{res.profit_margin:.2%}",
            irr_str,
        )
        all_rows.append(
            {
                "scenario": name,
                "pv_profits": res.pv_profits,
                "profit_margin": res.profit_margin,
                "irr": res.irr,
            }
        )

    console.print(table)
    _write_output({"scenarios": all_rows}, output_path, "scenario_result")


@app.command("uq")
def uq_cmd(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to UQ config JSON file."),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write JSON results."),
    ] = None,
    n_scenarios: Annotated[
        int,
        typer.Option("--scenarios", "-n", help="Number of Monte Carlo scenarios."),
    ] = 200,
    hurdle_rate: Annotated[
        float,
        typer.Option("--hurdle-rate", "-r", help="Annual hurdle rate for profit test."),
    ] = 0.10,
    seed: Annotated[
        int,
        typer.Option("--seed", "-s", help="Random seed for reproducibility."),
    ] = 42,
) -> None:
    """
    [bold]Run Monte Carlo uncertainty quantification.[/bold]

    Samples from distributions of mortality, lapse, and interest rate assumptions
    and reports the distribution of PV profits, IRR, and profit margin.
    """
    _header()

    from polaris_re.analytics.uq import MonteCarloUQ

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Running {n_scenarios} Monte Carlo scenarios...", total=None)
        inforce, assumptions, config, treaty = _build_demo_pipeline()
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty,
            hurdle_rate=hurdle_rate,
            n_scenarios=n_scenarios,
            seed=seed,
        )
        result = uq.run()

    # Display summary statistics
    table = Table(title=f"Monte Carlo UQ Summary (n={n_scenarios})", border_style="cyan")
    table.add_column("Statistic", style="bold")
    table.add_column("PV Profits", justify="right")
    table.add_column("IRR", justify="right")
    table.add_column("Profit Margin", justify="right")

    p5 = result.percentile(5)
    p50 = result.percentile(50)
    p95 = result.percentile(95)

    table.add_row(
        "Base Case",
        f"${result.base_pv_profit:,.0f}",
        f"{result.base_irr:.2%}" if result.base_irr is not None else "N/A",
        "—",
    )
    table.add_row(
        "5th Percentile",
        f"${p5['pv_profit']:,.0f}",
        f"{p5['irr']:.2%}" if not np.isnan(p5["irr"]) else "N/A",
        f"{p5['profit_margin']:.2%}",
    )
    table.add_row(
        "Median (50th)",
        f"${p50['pv_profit']:,.0f}",
        f"{p50['irr']:.2%}" if not np.isnan(p50["irr"]) else "N/A",
        f"{p50['profit_margin']:.2%}",
    )
    table.add_row(
        "95th Percentile",
        f"${p95['pv_profit']:,.0f}",
        f"{p95['irr']:.2%}" if not np.isnan(p95["irr"]) else "N/A",
        f"{p95['profit_margin']:.2%}",
    )
    table.add_row("VaR 95%", f"${result.var(0.95):,.0f}", "—", "—")
    table.add_row("CVaR 95%", f"${result.cvar(0.95):,.0f}", "—", "—")

    console.print(table)

    output_data = {
        "n_scenarios": result.n_scenarios,
        "seed": result.seed,
        "base_pv_profit": result.base_pv_profit,
        "base_irr": result.base_irr,
        "p5": p5,
        "p50": p50,
        "p95": p95,
        "var_95": result.var(0.95),
        "cvar_95": result.cvar(0.95),
    }
    _write_output(output_data, output_path, "uq_result")


@app.command("validate")
def validate_cmd(
    input_path: Annotated[
        Path,
        typer.Argument(help="Path to inforce CSV or assumption JSON file to validate."),
    ],
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed validation output."),
    ] = False,
) -> None:
    """
    [bold]Validate an inforce file or assumption set.[/bold]

    Checks:
    - CSV column schema for inforce files (policy_id, issue_age, etc.)
    - Required fields and value ranges (ages 18-120, face_amount > 0, etc.)
    - Mortality CSV format (age column, rate columns)
    - Assumption JSON structure

    Exits with code 0 on success, 1 on validation failure.
    """
    _header()

    if not input_path.exists():
        console.print(f"[red]Error:[/red] File not found: {input_path}")
        raise typer.Exit(code=1)

    suffix = input_path.suffix.lower()

    errors: list[str] = []
    warnings: list[str] = []

    if suffix == ".csv":
        # Validate inforce CSV
        try:
            import polars as pl

            df = pl.read_csv(input_path)
        except Exception as exc:
            console.print(f"[red]Error:[/red] Cannot read CSV: {exc}")
            raise typer.Exit(code=1) from exc

        required_cols = {
            "policy_id",
            "issue_age",
            "attained_age",
            "sex",
            "face_amount",
            "annual_premium",
        }
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {sorted(missing_cols)}")

        if "attained_age" in df.columns:
            age_col = df["attained_age"]
            if age_col.min() < 18:  # type: ignore[operator]
                errors.append(f"attained_age below 18 detected (min={age_col.min()})")
            if age_col.max() > 120:  # type: ignore[operator]
                errors.append(f"attained_age above 120 detected (max={age_col.max()})")

        if "face_amount" in df.columns and (df["face_amount"] <= 0).any():
            errors.append("face_amount must be > 0 for all records")

        if verbose:
            console.print(f"[dim]Rows: {len(df)}, Columns: {df.columns}[/dim]")

    elif suffix == ".json":
        # Validate assumption JSON structure
        try:
            config = json.loads(input_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON: {exc}")
            config = {}

        required_keys = {"version", "mortality", "lapse"}
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            errors.append(f"Missing required keys: {sorted(missing_keys)}")

    else:
        warnings.append(f"Unknown file type: {suffix}. No schema validation performed.")

    # Report
    if errors:
        for err in errors:
            console.print(f"[red]✗ Error:[/red] {err}")
        console.print(f"\n[red]Validation FAILED[/red] — {len(errors)} error(s) found.")
        raise typer.Exit(code=1)
    else:
        for warn in warnings:
            console.print(f"[yellow]⚠ Warning:[/yellow] {warn}")
        console.print("[green]✓ Validation PASSED[/green]")


@app.command("rate-schedule")
def rate_schedule_cmd(
    target_irr: Annotated[
        float,
        typer.Option("--target-irr", help="Target annual IRR (e.g. 0.10 for 10%)"),
    ] = 0.10,
    ages: Annotated[
        str,
        typer.Option("--ages", help="Comma-separated issue ages (e.g. 25,30,35,40,45,50)"),
    ] = "25,30,35,40,45,50,55,60,65",
    term: Annotated[
        int,
        typer.Option("--term", help="Policy term in years"),
    ] = 20,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output CSV or Excel file"),
    ] = None,
    output_json: Annotated[
        Path | None,
        typer.Option("--json", help="Export results as JSON"),
    ] = None,
) -> None:
    """
    Generate a YRT rate schedule — rates per $1,000 NAR that achieve a target IRR.

    Uses synthetic mortality and lapse tables (demo mode). Output is a table
    of solved rates by issue age, sex, and smoker status.
    """
    _header()

    from polaris_re.analytics.rate_schedule import YRTRateSchedule
    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.core.projection import ProjectionConfig
    from polaris_re.utils.table_io import load_mortality_csv

    fixtures = Path(__file__).parent.parent.parent / "tests" / "fixtures"

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as prog:
        task = prog.add_task("Loading assumptions...", total=None)

        # Load synthetic mortality table
        table_array = load_mortality_csv(
            fixtures / "synthetic_select_ultimate.csv",
            select_period=3, min_age=18, max_age=60,
        )
        mortality = MortalityTable.from_table_array(
            source=MortalityTableSource.SOA_VBT_2015,
            table_name="Demo Synthetic",
            table_array=table_array,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.UNKNOWN,
        )
        lapse = LapseAssumption.from_duration_table(
            {1: 0.10, 2: 0.08, 3: 0.06, 4: 0.05, 5: 0.04, "ultimate": 0.03}
        )
        assumptions = AssumptionSet(
            mortality=mortality, lapse=lapse, version="demo-rate-schedule"
        )
        config = ProjectionConfig(
            projection_horizon_years=term,
            discount_rate=0.05,
            valuation_date=date(2025, 1, 1),
        )

        prog.update(task, description="Solving rates...")

        scheduler = YRTRateSchedule(
            assumptions=assumptions, config=config, target_irr=target_irr,
        )

        age_list = [int(a.strip()) for a in ages.split(",")]
        # Use only UNKNOWN smoker since we have aggregate tables in demo mode
        result_df = scheduler.generate(
            ages=age_list,
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
            policy_term=term,
        )

    # Display table
    result_table = Table(title=f"YRT Rate Schedule (Target IRR = {target_irr:.1%})")
    result_table.add_column("Issue Age", justify="center")
    result_table.add_column("Sex")
    result_table.add_column("Smoker")
    result_table.add_column("Term")
    result_table.add_column("Rate/$1000", justify="right")

    for row in result_df.iter_rows(named=True):
        rate_str = f"{row['rate_per_1000']:.4f}" if not np.isnan(row["rate_per_1000"]) else "N/A"
        result_table.add_row(
            str(row["issue_age"]),
            str(row["sex"]),
            str(row["smoker_status"]),
            str(row["policy_term"]),
            rate_str,
        )

    console.print(result_table)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix == ".xlsx":
            from polaris_re.utils.excel_output import write_rate_schedule_excel
            write_rate_schedule_excel(result_df, output)
        else:
            result_df.write_csv(output)
        console.print(f"\nResults written to {output}")

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        json_data = result_df.to_dicts()
        output_json.write_text(json.dumps(json_data, indent=2, default=str))
        console.print(f"JSON written to {output_json}")


@app.command()
def ingest(
    input_path: Annotated[
        Path,
        typer.Argument(help="Raw cedant inforce data file (CSV or Excel)"),
    ],
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML mapping configuration file"),
    ] = ...,  # type: ignore[assignment]
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output normalised CSV path"),
    ] = Path("data/normalised_block.csv"),
    validate_only: Annotated[
        bool,
        typer.Option("--validate-only", help="Only validate, do not write"),
    ] = False,
) -> None:
    """
    Ingest raw cedant inforce data and normalise to Polaris RE schema.

    Applies a YAML mapping config to rename columns, translate codes,
    and fill defaults. Reports data quality summary.
    """
    _header()

    from polaris_re.utils.ingestion import IngestConfig, ingest_cedant_data, validate_inforce_df

    if not input_path.exists():
        console.print(f"[red]Error:[/red] Input file not found: {input_path}")
        raise typer.Exit(code=1)

    if not config_path.exists():
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(code=1)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as prog:
        prog.add_task("Loading mapping config...", total=None)
        config = IngestConfig.from_yaml(config_path)

        prog.add_task("Ingesting raw data...", total=None)
        df = ingest_cedant_data(input_path, config)

        prog.add_task("Validating...", total=None)
        report = validate_inforce_df(df)

    # Summary
    summary = Table(title="Ingestion Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value")
    summary.add_row("Policies", f"{report.n_policies:,}")
    summary.add_row("Total Face Amount", f"${report.total_face_amount:,.0f}")
    summary.add_row("Mean Age", f"{report.mean_age:.1f}")
    summary.add_row("Sex Split", str(report.sex_split))
    summary.add_row("Smoker Split", str(report.smoker_split))
    console.print(summary)

    if report.warnings:
        for w in report.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

    if report.errors:
        for e in report.errors:
            console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(code=1)

    console.print("[green]✓ Validation passed[/green]")

    if not validate_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        df.write_csv(output)
        console.print(f"\nNormalised data written to {output}")


if __name__ == "__main__":
    app()
