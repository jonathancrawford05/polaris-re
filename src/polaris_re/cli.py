"""
Polaris RE — Command Line Interface.

Entry point: `polaris` (registered in pyproject.toml [project.scripts])

Commands:
    polaris price          — run a deal pricing pipeline from YAML/JSON config
    polaris scenario       — run scenario analysis with tabular output
    polaris uq             — run Monte Carlo UQ with summary statistics
    polaris validate       — validate inforce CSV, mortality tables, assumption sets
    polaris rate-schedule  — generate a YRT rate schedule for a target IRR
    polaris ingest         — ingest and normalise raw cedant inforce data
    polaris version        — display package version information

Rich is used for all terminal output: coloured tables, progress bars, panels.
All commands accept --config / --output arguments and write JSON results to disk.
"""

import json
import sys
from dataclasses import dataclass
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
from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    dump_parity_debug,
    iter_cohorts,
    load_inforce,
)
from polaris_re.core.projection import ProjectionConfig

__all__ = ["app"]


@dataclass(frozen=True)
class CohortResult:
    """Typed per-cohort pricing result used by ``price_cmd``.

    Holds the raw ``ProfitTestResult`` objects (for Rich table rendering)
    alongside summary metadata. Replaces an earlier ``dict[str, object]``
    shape so downstream code gets clean types.
    """

    product_type: str
    n_policies: int
    face_amount: float
    cedant_result: ProfitTestResult
    reinsurer_result: ProfitTestResult | None


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


def _parse_config_to_pipeline_inputs(
    raw: dict,  # type: ignore[type-arg]
) -> tuple[PipelineInputs, list[dict[str, object]] | None]:
    """Parse a JSON config dict into PipelineInputs + optional policies list.

    Supports both the new nested schema (mortality/lapse/deal blocks)
    and the legacy flat schema (flat_qx/flat_lapse top-level keys).
    Returns (inputs, policies_dicts_or_None).
    """
    policies_raw: list[dict[str, object]] | None = raw.get("policies")  # type: ignore[assignment]

    # Detect legacy flat schema and translate
    if "flat_qx" in raw or "flat_lapse" in raw:
        console.print(
            "[yellow]Warning:[/yellow] Legacy config schema detected (flat_qx/flat_lapse). "
            "Migrate to the nested mortality/lapse/deal format. "
            "See data/inputs/test_inforce.json for an example."
        )
        flat_qx = float(raw.get("flat_qx", 0.001))
        flat_lapse = float(raw.get("flat_lapse", 0.05))

        mort_cfg = MortalityConfig(source="flat", flat_qx=flat_qx)
        lapse_cfg = LapseConfig(
            duration_table={1: flat_lapse, 2: flat_lapse, 3: flat_lapse, "ultimate": flat_lapse}
        )
        # Parse optional valuation_date (ISO format string)
        legacy_val_date_raw = raw.get("valuation_date")
        legacy_val_date = (
            date.fromisoformat(str(legacy_val_date_raw))
            if legacy_val_date_raw is not None
            else date.today()
        )
        deal_cfg = DealConfig(
            product_type=raw.get("product_type", "TERM"),  # type: ignore[arg-type]
            treaty_type=raw.get("treaty_type", "YRT"),  # type: ignore[arg-type]
            cession_pct=float(raw.get("cession_pct", 0.90)),
            yrt_loading=float(raw.get("yrt_loading", 0.10)),
            yrt_rate_per_1000=raw.get("yrt_rate_per_1000"),  # type: ignore[arg-type]
            modco_rate=float(raw.get("modco_interest_rate", 0.045)),
            discount_rate=float(raw.get("discount_rate", 0.06)),
            projection_years=int(raw.get("projection_horizon_years", 20)),
            acquisition_cost=float(raw.get("acquisition_cost_per_policy", 500.0)),
            maintenance_cost=float(raw.get("maintenance_cost_per_policy_per_year", 75.0)),
            valuation_date=legacy_val_date,
        )
        # Stamp product_type onto each policy dict for load_inforce
        if policies_raw:
            for p in policies_raw:
                p.setdefault("product_type", deal_cfg.product_type)
        return PipelineInputs(mortality=mort_cfg, lapse=lapse_cfg, deal=deal_cfg), policies_raw

    # New nested schema
    mort_raw = raw.get("mortality", {})
    lapse_raw = raw.get("lapse", {})
    deal_raw = raw.get("deal", {})

    mort_cfg = MortalityConfig(
        source=mort_raw.get("source", "SOA_VBT_2015"),
        multiplier=float(mort_raw.get("multiplier", 1.0)),
        flat_qx=mort_raw.get("flat_qx"),
        data_dir=Path(mort_raw["data_dir"]) if "data_dir" in mort_raw else None,
    )

    # Parse lapse duration table — JSON keys are strings, need int conversion
    lapse_duration_raw = lapse_raw.get("duration_table")
    if lapse_duration_raw is not None:
        duration_table: dict[int | str, float] = {}
        for k, v in lapse_duration_raw.items():
            if k == "ultimate":
                duration_table["ultimate"] = float(v)
            else:
                duration_table[int(k)] = float(v)
        lapse_cfg = LapseConfig(
            duration_table=duration_table,
            multiplier=float(lapse_raw.get("multiplier", 1.0)),
        )
    else:
        lapse_cfg = LapseConfig(multiplier=float(lapse_raw.get("multiplier", 1.0)))

    # Parse optional valuation_date (ISO format string) from deal config
    deal_val_date_raw = deal_raw.get("valuation_date")
    deal_val_date = (
        date.fromisoformat(str(deal_val_date_raw))
        if deal_val_date_raw is not None
        else date.today()
    )
    deal_cfg = DealConfig(
        product_type=deal_raw.get("product_type", "TERM"),
        treaty_type=deal_raw.get("treaty_type", "YRT"),
        cession_pct=float(deal_raw.get("cession_pct", 0.90)),
        yrt_loading=float(deal_raw.get("yrt_loading", 0.10)),
        yrt_rate_per_1000=deal_raw.get("yrt_rate_per_1000"),
        yrt_rate_basis=deal_raw.get("yrt_rate_basis", "Mortality-based"),
        modco_rate=float(deal_raw.get("modco_rate", 0.045)),
        discount_rate=float(deal_raw.get("discount_rate", 0.06)),
        hurdle_rate=float(deal_raw.get("hurdle_rate", 0.10)),
        projection_years=int(deal_raw.get("projection_years", 20)),
        acquisition_cost=float(deal_raw.get("acquisition_cost", 500.0)),
        maintenance_cost=float(deal_raw.get("maintenance_cost", 75.0)),
        use_policy_cession=bool(deal_raw.get("use_policy_cession", False)),
        valuation_date=deal_val_date,
    )

    # Stamp product_type onto each policy dict for load_inforce
    if policies_raw:
        for p in policies_raw:
            p.setdefault("product_type", deal_cfg.product_type)

    return PipelineInputs(mortality=mort_cfg, lapse=lapse_cfg, deal=deal_cfg), policies_raw


def _build_pipeline_from_config(
    config_path: Path,
    inforce_path: Path | None = None,
) -> tuple:  # type: ignore[type-arg]
    """Build an inforce pipeline from a JSON config file.

    Supports both the new nested schema (mortality/lapse/deal blocks)
    and the legacy flat schema (flat_qx/flat_lapse) with deprecation warning.

    When inforce_path is provided, policies are loaded from CSV rather than
    the embedded policies list in the config.

    Returns:
        (inforce, assumptions, config, pipeline_inputs) tuple.
    """
    raw = _load_json_config(config_path)
    inputs, policies_raw = _parse_config_to_pipeline_inputs(raw)

    # Load inforce
    if inforce_path is not None:
        if policies_raw:
            console.print(
                "[yellow]Warning:[/yellow] --inforce provided; ignoring 'policies' in config."
            )
        inforce = load_inforce(csv_path=inforce_path)
    elif policies_raw:
        inforce = load_inforce(policies_dict=policies_raw)
    else:
        console.print(
            "[red]Error:[/red] No inforce data: provide --inforce CSV or 'policies' in config."
        )
        raise typer.Exit(code=1)

    inforce, assumptions, config = build_pipeline(inforce, inputs)
    return inforce, assumptions, config, inputs


def _build_treaty_for_pipeline(
    inputs: PipelineInputs,
    gross: CashFlowResult,
    face_amount: float,
    inforce: object | None = None,
) -> tuple[object | None, bool]:
    """Build a treaty and apply it using the pipeline inputs.

    Returns (treaty_object, use_policy_cession).
    """
    deal = inputs.deal
    treaty_type = deal.treaty_type
    if treaty_type is None or str(treaty_type).lower() == "none":
        return None, False

    # Resolve YRT rate
    yrt_rate = deal.yrt_rate_per_1000
    if treaty_type == "YRT" and yrt_rate is None:
        if deal.yrt_rate_basis == "Manual Rate" and deal.yrt_rate_per_1000 is not None:
            yrt_rate = deal.yrt_rate_per_1000
        else:
            yrt_rate = derive_yrt_rate(gross, face_amount, deal.yrt_loading)

    treaty = build_treaty(
        treaty_type=treaty_type,
        cession_pct=deal.cession_pct,
        face_amount=face_amount,
        modco_rate=deal.modco_rate,
        yrt_rate_per_1000=yrt_rate,
    )
    return treaty, deal.use_policy_cession


def _price_single_cohort(
    cohort_id: str,
    cohort_inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    inputs: PipelineInputs,
    hurdle_rate: float,
    parity_label: str,
) -> CohortResult:
    """Run the full pricing pipeline on a single-product cohort.

    Extracted from ``price_cmd`` so the same logic can be looped over
    cohorts when the inforce block contains multiple product types.

    Args:
        cohort_id: Human-readable cohort identifier (e.g. "TERM").
        cohort_inforce: InforceBlock containing only one product type.
        assumptions: Shared ``AssumptionSet`` (same for all cohorts in a deal).
        config: Shared ``ProjectionConfig``.
        inputs: PipelineInputs (deal config, treaty type, etc.).
        hurdle_rate: CLI ``--hurdle-rate`` flag (falls back to deal config).
        parity_label: Label for the parity debug dump. When multiple cohorts
            are present we append the cohort id so each dump is distinct.

    Returns:
        Typed ``CohortResult`` carrying the raw ProfitTestResult objects
        plus cohort metadata (product type, policy count, face amount).
    """
    from polaris_re.analytics.profit_test import ProfitTester
    from polaris_re.products.dispatch import get_product_engine

    # 1. Gross projection via product dispatch
    product = get_product_engine(inforce=cohort_inforce, assumptions=assumptions, config=config)
    gross = product.project()

    # 2. Build treaty from pipeline inputs (YRT rate derived per-cohort)
    face_amount = cohort_inforce.total_face_amount()
    treaty, use_policy_cession = _build_treaty_for_pipeline(
        inputs, gross, face_amount, cohort_inforce
    )

    # 3. Apply treaty
    if treaty is not None:
        inforce_arg = cohort_inforce if use_policy_cession else None
        net, ceded = treaty.apply(gross, inforce=inforce_arg)  # type: ignore[attr-defined]
    else:
        net, ceded = gross, None

    # 4. Parity debug dump (label disambiguates cohorts when >1)
    dump_parity_debug(parity_label, gross, net, ceded)

    # 5. Cedant profit test on NET cash flows
    effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
    cedant_result = ProfitTester(cashflows=net, hurdle_rate=effective_hurdle).run()

    # 6. Reinsurer profit test on CEDED re-labelled as NET (ADR-039)
    reinsurer_result: ProfitTestResult | None = None
    if ceded is not None:
        reinsurer_result = ProfitTester(
            cashflows=ceded_to_reinsurer_view(ceded),
            hurdle_rate=effective_hurdle,
        ).run()

    return CohortResult(
        product_type=cohort_id,
        n_policies=cohort_inforce.n_policies,
        face_amount=face_amount,
        cedant_result=cedant_result,
        reinsurer_result=reinsurer_result,
    )


def _profit_test_to_dict(result: ProfitTestResult) -> dict[str, object]:
    """Flatten a ProfitTestResult into a plain dict for JSON serialisation."""
    return {
        "hurdle_rate": result.hurdle_rate,
        "pv_profits": result.pv_profits,
        "pv_premiums": result.pv_premiums,
        "profit_margin": result.profit_margin,
        "irr": result.irr,
        "breakeven_year": result.breakeven_year,
        "total_undiscounted_profit": result.total_undiscounted_profit,
        "profit_by_year": result.profit_by_year.tolist(),
    }


def _render_rated_block_table(summary: dict[str, object]) -> None:
    """Render a small Rich table summarising substandard-rating composition."""
    table = Table(title="Block Substandard Rating", border_style="magenta")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    n_policies = int(summary["n_policies"])  # type: ignore[arg-type]
    n_rated = int(summary["n_rated"])  # type: ignore[arg-type]
    pct_count = float(summary["pct_rated_by_count"])  # type: ignore[arg-type]
    pct_face = float(summary["pct_rated_by_face"])  # type: ignore[arg-type]
    wavg = float(summary["face_weighted_mean_multiplier"])  # type: ignore[arg-type]
    max_mult = float(summary["max_multiplier"])  # type: ignore[arg-type]
    max_fe = float(summary["max_flat_extra_per_1000"])  # type: ignore[arg-type]
    table.add_row("Policies", f"{n_policies:,}")
    table.add_row("Rated (> standard)", f"{n_rated:,}")
    table.add_row("% Rated (by count)", f"{pct_count:.1%}")
    table.add_row("% Rated (by face)", f"{pct_face:.1%}")
    table.add_row("Face-weighted avg multiplier", f"{wavg:.3f}")
    table.add_row("Max multiplier", f"{max_mult:.2f}")
    table.add_row("Max flat-extra / $1,000", f"${max_fe:.2f}")
    console.print(table)


def _render_cohort_pricing_tables(cohort: CohortResult) -> None:
    """Render the Rich tables for a single cohort's pricing results."""
    cedant_result = cohort.cedant_result
    reinsurer_result = cohort.reinsurer_result
    pt_label = cohort.product_type

    # Cedant results table
    cedant_table = Table(
        title=(f"Profit Test — Cedant (NET) View · {pt_label} · {cohort.n_policies:,} policies"),
        border_style="cyan",
    )
    cedant_table.add_column("Metric", style="bold")
    cedant_table.add_column("Value", justify="right")

    irr_str = f"{cedant_result.irr:.2%}" if cedant_result.irr is not None else "N/A"
    be_str = (
        f"Year {cedant_result.breakeven_year}"
        if cedant_result.breakeven_year is not None
        else "Never"
    )
    cedant_margin_str = (
        f"{cedant_result.profit_margin:.2%}" if cedant_result.profit_margin is not None else "N/A"
    )
    cedant_table.add_row("Hurdle Rate", f"{cedant_result.hurdle_rate:.2%}")
    cedant_table.add_row("PV Profits", f"${cedant_result.pv_profits:,.0f}")
    cedant_table.add_row("PV Premiums", f"${cedant_result.pv_premiums:,.0f}")
    cedant_table.add_row("Profit Margin", cedant_margin_str)
    cedant_table.add_row("IRR", irr_str)
    cedant_table.add_row("Break-even", be_str)
    cedant_table.add_row(
        "Total Undiscounted Profit",
        f"${cedant_result.total_undiscounted_profit:,.0f}",
    )
    console.print(cedant_table)

    # Reinsurer results table
    if reinsurer_result is not None:
        rei_table = Table(
            title=f"Profit Test — Reinsurer View · {pt_label}",
            border_style="green",
        )
        rei_table.add_column("Metric", style="bold")
        rei_table.add_column("Value", justify="right")

        rei_irr_str = f"{reinsurer_result.irr:.2%}" if reinsurer_result.irr is not None else "N/A"
        rei_be_str = (
            f"Year {reinsurer_result.breakeven_year}"
            if reinsurer_result.breakeven_year is not None
            else "Never"
        )
        rei_margin_str = (
            f"{reinsurer_result.profit_margin:.2%}"
            if reinsurer_result.profit_margin is not None
            else "N/A"
        )
        rei_table.add_row("Hurdle Rate", f"{reinsurer_result.hurdle_rate:.2%}")
        rei_table.add_row("PV Profits", f"${reinsurer_result.pv_profits:,.0f}")
        rei_table.add_row("PV Premiums", f"${reinsurer_result.pv_premiums:,.0f}")
        rei_table.add_row("Profit Margin", rei_margin_str)
        rei_table.add_row("IRR", rei_irr_str)
        rei_table.add_row("Break-even", rei_be_str)
        rei_table.add_row(
            "Total Undiscounted Profit",
            f"${reinsurer_result.total_undiscounted_profit:,.0f}",
        )
        console.print(rei_table)
    else:
        console.print("[dim]No treaty applied — reinsurer view not available.[/dim]")


def _fail_on_mixed_cohorts(
    inforce: InforceBlock,
    command_name: str,
) -> None:
    """Exit the CLI with a clear message if the block has multiple product types.

    Scenario analysis and Monte Carlo UQ operate on a single CashFlowResult
    per run and cannot coherently combine cash flows across product types.
    For mixed blocks, users should run ``polaris price`` (which is cohort
    aware) or filter the input CSV to a single product type first.
    """
    if len(inforce.product_types) <= 1:
        return
    detected = ", ".join(sorted(pt.value for pt in inforce.product_types))
    console.print(
        f"[red]Error:[/red] `polaris {command_name}` does not support mixed "
        f"product-type blocks (found: {detected}).\n"
        f"[dim]Run [bold]polaris price[/bold] to see per-cohort results, or "
        f"filter your inforce CSV to a single product type first.[/dim]"
    )
    raise typer.Exit(code=1)


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
    inforce_path: Annotated[
        Path | None,
        typer.Option("--inforce", "-i", help="Path to inforce CSV file."),
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

    Runs the full pipeline: InforceBlock → AssumptionSet → Product → Treaty → ProfitTester.
    Supports TERM, WHOLE_LIFE, and UL product types via the product dispatcher.

    [bold]Mixed product blocks[/bold] are supported: each distinct
    [cyan]product_type[/cyan] in the inforce CSV is priced as its own
    independent cohort (separate gross projection, treaty, and profit test).
    Results are reported per-cohort — there is no cross-product aggregation.

    If no --config is supplied, runs in demo mode using
    [cyan]data/configs/demo.json[/cyan] and [cyan]data/inputs/demo.csv[/cyan].

    [bold]Debugging:[/bold] set [cyan]POLARIS_PARITY_DEBUG=1[/cyan] to dump
    year-by-year cash flow CSVs (gross / net / ceded). Files are written to
    [cyan]data/outputs/parity/[/cyan] by default; override with
    [cyan]POLARIS_PARITY_OUTPUT=<path>[/cyan]. The resolved absolute path is
    printed on stderr.
    """
    _header()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Building pipeline...", total=None)
        if config_path is not None:
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                config_path, inforce_path
            )
            console.print(f"[dim]Loaded config from {config_path}[/dim]")
        else:
            # Demo mode: use shipped fixtures
            demo_dir = Path(__file__).parent.parent.parent
            demo_config = demo_dir / "data" / "configs" / "demo.json"
            demo_csv = demo_dir / "data" / "inputs" / "demo.csv"
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                demo_config, demo_csv if demo_csv.exists() else None
            )
            console.print("[dim]No --config supplied — running demo mode[/dim]")

    # Partition the block into per-product cohorts. Homogeneous blocks
    # pass through as a single-element list (zero overhead).
    cohorts_split = iter_cohorts(inforce)
    n_cohorts = len(cohorts_split)
    if n_cohorts > 1:
        detected = ", ".join(pt.value for pt, _ in cohorts_split)
        console.print(
            f"[yellow]Mixed product block detected[/yellow] "
            f"({n_cohorts} cohorts: {detected}). Pricing each cohort independently."
        )

    cohort_results: list[CohortResult] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running projection...", total=None)

        for product_type, cohort_inforce in cohorts_split:
            parity_label = f"cli_{product_type.value.lower()}" if n_cohorts > 1 else "cli"
            cohort_results.append(
                _price_single_cohort(
                    cohort_id=product_type.value,
                    cohort_inforce=cohort_inforce,
                    assumptions=assumptions,
                    config=config,
                    inputs=inputs,
                    hurdle_rate=hurdle_rate,
                    parity_label=parity_label,
                )
            )

        progress.update(task, completed=True)

    # Render per-cohort tables
    for cohort in cohort_results:
        if n_cohorts > 1:
            console.print()
            console.print(
                Panel(
                    f"[bold]Cohort: {cohort.product_type}[/bold] "
                    f"· {cohort.n_policies:,} policies "
                    f"· ${cohort.face_amount:,.0f} face",
                    border_style="yellow",
                )
            )
        _render_cohort_pricing_tables(cohort)

    # Build JSON output. Always includes a "cohorts" list; for the common
    # single-cohort case, mirror the cohort's cedant/reinsurer dicts at the
    # top level so existing consumers of the CLI JSON output keep working.
    cohorts_out: list[dict[str, object]] = []
    total_cedant_pv = 0.0
    total_reinsurer_pv = 0.0
    for c in cohort_results:
        cedant_dict = _profit_test_to_dict(c.cedant_result)
        reinsurer_dict = (
            _profit_test_to_dict(c.reinsurer_result) if c.reinsurer_result is not None else None
        )
        cohorts_out.append(
            {
                "product_type": c.product_type,
                "n_policies": c.n_policies,
                "face_amount": c.face_amount,
                "cedant": cedant_dict,
                "reinsurer": reinsurer_dict,
            }
        )
        total_cedant_pv += c.cedant_result.pv_profits
        if c.reinsurer_result is not None:
            total_reinsurer_pv += c.reinsurer_result.pv_profits

    from polaris_re.utils.rating import rating_composition

    rated_summary = rating_composition(inforce)

    output_data: dict[str, object] = {
        "cohorts": cohorts_out,
        "summary": {
            "n_cohorts": n_cohorts,
            "total_pv_profits_cedant": total_cedant_pv,
            "total_pv_profits_reinsurer": total_reinsurer_pv,
        },
        "rated_block": rated_summary,
    }
    # Back-compat: expose the first cohort's cedant/reinsurer at the top
    # level so downstream consumers that only know the old schema still
    # work for the (overwhelmingly common) single-cohort case.
    if n_cohorts == 1:
        first = cohort_results[0]
        output_data["cedant"] = _profit_test_to_dict(first.cedant_result)
        if first.reinsurer_result is not None:
            output_data["reinsurer"] = _profit_test_to_dict(first.reinsurer_result)

    if n_cohorts > 1:
        summary_table = Table(title="Mixed-Cohort Summary", border_style="magenta")
        summary_table.add_column("Metric", style="bold")
        summary_table.add_column("Value", justify="right")
        summary_table.add_row("Cohorts", str(n_cohorts))
        summary_table.add_row("Total PV Profits (Cedant)", f"${total_cedant_pv:,.0f}")
        summary_table.add_row("Total PV Profits (Reinsurer)", f"${total_reinsurer_pv:,.0f}")
        console.print(summary_table)
        console.print(
            "[dim]Note: per-cohort IRRs are not summed. Each cohort is an "
            "independent deal — cross-product aggregation (single blended IRR) "
            "is a separate feature.[/dim]"
        )

    # Only render the rated-block panel when the block actually contains
    # substandard lives — all-standard blocks stay visually identical to
    # pre-Slice-3 output.
    if int(rated_summary["n_rated"]) > 0:  # type: ignore[arg-type]
        _render_rated_block_table(rated_summary)

    _write_output(output_data, output_path, "price_result")


@app.command("scenario")
def scenario_cmd(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to scenario config JSON file."),
    ] = None,
    inforce_path: Annotated[
        Path | None,
        typer.Option("--inforce", "-i", help="Path to inforce CSV file."),
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
    Supports TERM, WHOLE_LIFE, and UL product types via the product dispatcher.

    [bold]Mixed product blocks are not supported[/bold] — scenario analysis
    operates on a single aggregated CashFlowResult and cannot coherently
    combine cash flows across product types. For mixed blocks, run
    [bold]polaris price[/bold] (which is cohort-aware) or filter your
    inforce CSV to a single [cyan]product_type[/cyan] first.

    If no --config is supplied, runs in demo mode using
    [cyan]data/configs/demo.json[/cyan] and [cyan]data/inputs/demo.csv[/cyan].

    [bold]Debugging:[/bold] set [cyan]POLARIS_PARITY_DEBUG=1[/cyan] to dump
    year-by-year cash flow CSVs. Files are written to
    [cyan]data/outputs/parity/[/cyan] by default; override with
    [cyan]POLARIS_PARITY_OUTPUT=<path>[/cyan].
    """
    _header()

    from polaris_re.analytics.scenario import ScenarioRunner
    from polaris_re.products.dispatch import get_product_engine
    from polaris_re.reinsurance.yrt import YRTTreaty

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running scenarios...", total=None)
        if config_path is not None:
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                config_path, inforce_path
            )
            console.print(f"[dim]Loaded config from {config_path}[/dim]")
        else:
            demo_dir = Path(__file__).parent.parent.parent
            demo_config = demo_dir / "data" / "configs" / "demo.json"
            demo_csv = demo_dir / "data" / "inputs" / "demo.csv"
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                demo_config, demo_csv if demo_csv.exists() else None
            )
            console.print("[dim]No --config supplied — running demo mode[/dim]")

        _fail_on_mixed_cohorts(inforce, "scenario")

        # Derive YRT rate from base gross projection (ADR-038)
        gross = get_product_engine(
            inforce=inforce, assumptions=assumptions, config=config
        ).project()
        face_amount = inforce.total_face_amount()

        treaty_obj, use_policy_cession = _build_treaty_for_pipeline(
            inputs, gross, face_amount, inforce
        )

        # Parity diagnostic dump (set POLARIS_PARITY_DEBUG=1 to enable)
        if treaty_obj is not None:
            inforce_arg = inforce if use_policy_cession else None
            _net, _ceded = treaty_obj.apply(gross, inforce=inforce_arg)
            dump_parity_debug("cli_scenario", gross, _net, _ceded)
        else:
            dump_parity_debug("cli_scenario", gross)

        # ScenarioRunner requires a treaty; fall back to gross-only YRT if None
        if treaty_obj is None:
            yrt_rate = derive_yrt_rate(gross, face_amount)
            treaty_obj = YRTTreaty(
                cession_pct=0.0,
                total_face_amount=face_amount,
                flat_yrt_rate_per_1000=yrt_rate,
            )

        effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
        runner = ScenarioRunner(
            inforce=inforce,
            base_assumptions=assumptions,
            config=config,
            treaty=treaty_obj,
            hurdle_rate=effective_hurdle,
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
        margin_str = f"{res.profit_margin:.2%}" if res.profit_margin is not None else "N/A"
        table.add_row(
            name,
            f"${res.pv_profits:,.0f}",
            margin_str,
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
    inforce_path: Annotated[
        Path | None,
        typer.Option("--inforce", "-i", help="Path to inforce CSV file."),
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
    Supports TERM, WHOLE_LIFE, and UL product types via the product dispatcher.

    [bold]Mixed product blocks are not supported[/bold] — Monte Carlo UQ
    samples against a single base projection and cannot coherently combine
    cash flows across product types. For mixed blocks, run
    [bold]polaris price[/bold] (which is cohort-aware) or filter your
    inforce CSV to a single [cyan]product_type[/cyan] first.

    If no --config is supplied, runs in demo mode using
    [cyan]data/configs/demo.json[/cyan] and [cyan]data/inputs/demo.csv[/cyan].

    [bold]Debugging:[/bold] set [cyan]POLARIS_PARITY_DEBUG=1[/cyan] to dump
    year-by-year cash flow CSVs. Files are written to
    [cyan]data/outputs/parity/[/cyan] by default; override with
    [cyan]POLARIS_PARITY_OUTPUT=<path>[/cyan].
    """
    _header()

    from polaris_re.analytics.uq import MonteCarloUQ
    from polaris_re.products.dispatch import get_product_engine

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Running {n_scenarios} Monte Carlo scenarios...", total=None)
        if config_path is not None:
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                config_path, inforce_path
            )
            console.print(f"[dim]Loaded config from {config_path}[/dim]")
        else:
            demo_dir = Path(__file__).parent.parent.parent
            demo_config = demo_dir / "data" / "configs" / "demo.json"
            demo_csv = demo_dir / "data" / "inputs" / "demo.csv"
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                demo_config, demo_csv if demo_csv.exists() else None
            )
            console.print("[dim]No --config supplied — running demo mode[/dim]")

        _fail_on_mixed_cohorts(inforce, "uq")

        # Derive YRT rate from base gross projection (ADR-038)
        gross = get_product_engine(
            inforce=inforce, assumptions=assumptions, config=config
        ).project()
        face_amount = inforce.total_face_amount()

        treaty_obj, use_policy_cession = _build_treaty_for_pipeline(
            inputs, gross, face_amount, inforce
        )

        # Parity diagnostic dump (set POLARIS_PARITY_DEBUG=1 to enable)
        if treaty_obj is not None:
            inforce_arg = inforce if use_policy_cession else None
            _net, _ceded = treaty_obj.apply(gross, inforce=inforce_arg)
            dump_parity_debug("cli_uq", gross, _net, _ceded)
        else:
            dump_parity_debug("cli_uq", gross)

        effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty_obj,
            hurdle_rate=effective_hurdle,
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
            select_period=3,
            min_age=18,
            max_age=60,
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
        assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="demo-rate-schedule")
        config = ProjectionConfig(
            projection_horizon_years=term,
            discount_rate=0.05,
            valuation_date=date.today(),
        )

        prog.update(task, description="Solving rates...")

        scheduler = YRTRateSchedule(
            assumptions=assumptions,
            config=config,
            target_irr=target_irr,
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
