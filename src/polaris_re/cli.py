"""
Polaris RE — Command Line Interface.

Entry point: `polaris` (registered in pyproject.toml [project.scripts])

Commands:
    polaris price                — run a deal pricing pipeline from YAML/JSON config
    polaris scenario             — run scenario analysis with tabular output
    polaris uq                   — run Monte Carlo UQ with summary statistics
    polaris validate             — validate inforce CSV, mortality tables, assumption sets
    polaris rate-schedule        — generate a YRT rate schedule for a target IRR
    polaris ingest               — ingest and normalise raw cedant inforce data
    polaris portfolio run        — aggregate a multi-deal book of reinsurance treaties
    polaris portfolio scenarios  — run a portfolio under the deal-committee stress set
    polaris portfolio report     — re-render a portfolio result JSON
    polaris version              — display package version information

Rich is used for all terminal output: coloured tables, progress bars, panels.
All commands accept --config / --output arguments and write JSON results to disk.
"""

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import numpy as np
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import polaris_re
from polaris_re.analytics.premium_sufficiency import (
    PremiumSufficiencyResult,
    PremiumSufficiencyTester,
)
from polaris_re.analytics.profit_test import ProfitResultWithCapital, ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock

if TYPE_CHECKING:
    from polaris_re.analytics.scenario import ScenarioAdjustment
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.utils.excel_output import DealPricingExport, IFRS17MovementExport
from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_capital_nar,
    derive_yrt_rate,
    dump_parity_debug,
    iter_cohorts,
    load_inforce,
)
from polaris_re.core.policy import Policy, ProductType
from polaris_re.core.projection import ProjectionConfig

__all__ = ["app"]


@dataclass(frozen=True)
class CohortResult:
    """Typed per-cohort pricing result used by ``price_cmd``.

    Holds the raw ``ProfitTestResult`` objects (for Rich table rendering)
    alongside summary metadata and the live ``CashFlowResult`` instances
    that fed the profit test. The cash flow objects are kept on the
    result so downstream consumers (e.g. the Excel writer wired in by
    Slice 2 of ADR-045) can render annual rollups without re-projecting.

    When ``--capital`` is supplied (``licat`` / ``rbc`` / ``solvency2``),
    ``cedant_result`` and ``reinsurer_result`` are ``ProfitResultWithCapital``
    instances (subclass of ``ProfitTestResult``) carrying RoC and peak capital
    fields. Existing consumers that read base fields keep working.
    """

    product_type: str
    n_policies: int
    face_amount: float
    cedant_result: ProfitTestResult
    reinsurer_result: ProfitTestResult | None
    net_cashflows: CashFlowResult
    gross_cashflows: CashFlowResult
    ceded_cashflows: CashFlowResult | None


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
        # Parse optional valuation_date (ISO format string). None defers to
        # the inforce block's valuation date in build_pipeline (ADR-074).
        legacy_val_date_raw = raw.get("valuation_date")
        legacy_val_date = (
            date.fromisoformat(str(legacy_val_date_raw))
            if legacy_val_date_raw is not None
            else None
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
            reserve_basis=str(raw.get("reserve_basis", "NET_PREMIUM")),
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

    # Parse optional valuation_date (ISO format string) from deal config.
    # None defers to the inforce block's valuation date in build_pipeline
    # (ADR-074) — do not stamp date.today() here.
    deal_val_date_raw = deal_raw.get("valuation_date")
    deal_val_date = (
        date.fromisoformat(str(deal_val_date_raw)) if deal_val_date_raw is not None else None
    )
    # Optional tabular YRT rate table (ADR-075). Path used as-is, mirroring
    # the MortalityConfig.data_dir precedent (no relative-to-config
    # resolution). None leaves the flat-rate path unchanged.
    yrt_table_path_raw = deal_raw.get("yrt_rate_table_path")
    yrt_table_path = Path(str(yrt_table_path_raw)) if yrt_table_path_raw is not None else None
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
        reserve_basis=str(deal_raw.get("reserve_basis", "NET_PREMIUM")),
        valuation_date=deal_val_date,
        yrt_rate_table_path=yrt_table_path,
        yrt_rate_table_select_period=int(deal_raw.get("yrt_rate_table_select_period", 3)),
        yrt_rate_table_label=deal_raw.get("yrt_rate_table_label"),
        yrt_rate_table_smoker_distinct=bool(deal_raw.get("yrt_rate_table_smoker_distinct", True)),
    )

    # Stamp product_type onto each policy dict for load_inforce
    if policies_raw:
        for p in policies_raw:
            p.setdefault("product_type", deal_cfg.product_type)

    return PipelineInputs(mortality=mort_cfg, lapse=lapse_cfg, deal=deal_cfg), policies_raw


def _build_pipeline_from_config(
    config_path: Path,
    inforce_path: Path | None = None,
    reserve_basis_override: str | None = None,
) -> tuple:  # type: ignore[type-arg]
    """Build an inforce pipeline from a JSON config file.

    Supports both the new nested schema (mortality/lapse/deal blocks)
    and the legacy flat schema (flat_qx/flat_lapse) with deprecation warning.

    When inforce_path is provided, policies are loaded from CSV rather than
    the embedded policies list in the config.

    When ``reserve_basis_override`` is provided (the ``--reserve-basis`` CLI
    flag), it takes precedence over any ``reserve_basis`` in the config — the
    same flag-over-config precedence the YRT-rate-table surfaces use. An
    unknown value raises ``PolarisValidationError`` via ``build_projection_config``.

    Returns:
        (inforce, assumptions, config, pipeline_inputs) tuple.
    """
    raw = _load_json_config(config_path)
    inputs, policies_raw = _parse_config_to_pipeline_inputs(raw)
    if reserve_basis_override is not None:
        inputs.deal.reserve_basis = reserve_basis_override

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
    yrt_rate_table: object | None = None,
) -> tuple[object | None, bool]:
    """Build a treaty and apply it using the pipeline inputs.

    Args:
        inputs:         Pipeline inputs (deal config, treaty type, etc.).
        gross:          GROSS-basis cash flows for YRT-rate derivation.
        face_amount:    Total in-force face amount.
        inforce:        Reserved for future use (e.g. block-aware loadings).
        yrt_rate_table: Optional pre-loaded ``YRTRateTable`` (ADR-052).
                        When set with ``treaty_type == "YRT"``, the treaty
                        is constructed with the table and the flat rate is
                        suppressed (mutual exclusion enforced by
                        ``YRTTreaty._validate_rate_source_exclusive``).

    Returns:
        (treaty_object, use_policy_cession). When a tabular YRT table is
        supplied, ``use_policy_cession`` is forced to ``True`` so the
        ``inforce`` argument flows through to ``YRTTreaty.apply()``,
        which the tabular path requires.
    """
    deal = inputs.deal
    treaty_type = deal.treaty_type
    if treaty_type is None or str(treaty_type).lower() == "none":
        return None, False

    # Tabular YRT path (ADR-052): construct directly so we can pass the
    # rate table without polluting the generic ``build_treaty`` factory.
    if treaty_type == "YRT" and yrt_rate_table is not None:
        from polaris_re.reinsurance.yrt import YRTTreaty
        from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

        if not isinstance(yrt_rate_table, YRTRateTable):
            raise PolarisValidationError(
                f"yrt_rate_table must be a YRTRateTable, got {type(yrt_rate_table).__name__}."
            )
        treaty = YRTTreaty(
            treaty_name="YRT",
            cession_pct=deal.cession_pct,
            total_face_amount=face_amount,
            yrt_rate_table=yrt_rate_table,
        )
        # Tabular YRT.apply() requires inforce → force the cohort inforce
        # through, regardless of the deal's use_policy_cession flag.
        return treaty, True

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
    capital_model_id: str | None = None,
    yrt_rate_table: object | None = None,
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
        capital_model_id: When ``"licat"`` / ``"rbc"`` / ``"solvency2"``, both
            cedant and reinsurer profit tests are run via
            ``ProfitTester.run_with_capital`` using that jurisdiction's
            per-product factor model (ADR-047/048/098/100, resolved via
            ``capital_model_for``, ADR-101). NAR is derived per-side via
            ``derive_capital_nar`` (ADR-049). When ``None``, the unchanged
            ``run()`` path is used.

    Returns:
        Typed ``CohortResult`` carrying the raw ProfitTestResult objects
        plus cohort metadata (product type, policy count, face amount).
        When ``capital_model_id`` is set, the result fields are
        ``ProfitResultWithCapital`` instances.
    """
    from polaris_re.products.dispatch import get_product_engine

    # 1. Gross projection via product dispatch.
    # Force ``seriatim=True`` when a tabular YRT rate table is in play so
    # ``YRTTreaty.apply()`` can take the per-policy seriatim path
    # (ADR-051 / ADR-052) rather than the face-weighted-average fallback.
    product = get_product_engine(inforce=cohort_inforce, assumptions=assumptions, config=config)
    gross = product.project(seriatim=yrt_rate_table is not None)

    # 2. Build treaty from pipeline inputs (YRT rate derived per-cohort,
    # or tabular when a rate table is supplied).
    face_amount = cohort_inforce.total_face_amount()
    treaty, use_policy_cession = _build_treaty_for_pipeline(
        inputs, gross, face_amount, cohort_inforce, yrt_rate_table=yrt_rate_table
    )

    # 3. Apply treaty
    if treaty is not None:
        inforce_arg = cohort_inforce if use_policy_cession else None
        net, ceded = treaty.apply(gross, inforce=inforce_arg)  # type: ignore[attr-defined]
    else:
        net, ceded = gross, None

    # 4. Parity debug dump (label disambiguates cohorts when >1)
    dump_parity_debug(parity_label, gross, net, ceded)

    # 5. Cedant + reinsurer profit tests
    effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
    cedant_result, reinsurer_result = _run_profit_tests(
        cohort_id=cohort_id,
        gross=gross,
        net=net,
        ceded=ceded,
        face_amount=face_amount,
        cession_pct=inputs.deal.cession_pct if treaty is not None else None,
        hurdle_rate=effective_hurdle,
        capital_model_id=capital_model_id,
    )

    return CohortResult(
        product_type=cohort_id,
        n_policies=cohort_inforce.n_policies,
        face_amount=face_amount,
        cedant_result=cedant_result,
        reinsurer_result=reinsurer_result,
        net_cashflows=net,
        gross_cashflows=gross,
        ceded_cashflows=ceded,
    )


def _run_profit_tests(
    *,
    cohort_id: str,
    gross: CashFlowResult,
    net: CashFlowResult,
    ceded: CashFlowResult | None,
    face_amount: float,
    cession_pct: float | None,
    hurdle_rate: float,
    capital_model_id: str | None,
) -> tuple[ProfitTestResult, ProfitTestResult | None]:
    """Run cedant + reinsurer profit tests, optionally with capital.

    When ``capital_model_id`` is set (``licat`` / ``rbc`` / ``solvency2``), both
    sides go through ``run_with_capital`` with cedant- and reinsurer-derived NAR,
    using the jurisdiction's calculator resolved via ``capital_model_for``
    (ADR-101). When ``None``, the unchanged ``run()`` path is used.
    """
    from polaris_re.analytics.capital_base import capital_model_for
    from polaris_re.analytics.profit_test import ProfitTester

    cedant_tester = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate)
    reinsurer_tester: ProfitTester | None = None
    if ceded is not None:
        reinsurer_tester = ProfitTester(
            cashflows=ceded_to_reinsurer_view(ceded),
            hurdle_rate=hurdle_rate,
        )

    if capital_model_id is None:
        cedant = cedant_tester.run()
        reinsurer: ProfitTestResult | None = (
            reinsurer_tester.run() if reinsurer_tester is not None else None
        )
        return cedant, reinsurer

    try:
        product_type_enum = ProductType(cohort_id)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Cannot map cohort id '{cohort_id}' to a ProductType for capital model."
        ) from exc
    capital_model = capital_model_for(capital_model_id, product_type_enum)

    cedant_nar = derive_capital_nar(
        gross=gross,
        reserve_balance=net.reserve_balance,
        face_amount_total=face_amount,
        cession_pct=cession_pct,
        is_reinsurer=False,
    )
    cedant = cedant_tester.run_with_capital(capital_model, nar=cedant_nar)

    reinsurer_with_capital: ProfitResultWithCapital | None = None
    if reinsurer_tester is not None and ceded is not None and cession_pct is not None:
        reinsurer_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=ceded.reserve_balance,
            face_amount_total=face_amount,
            cession_pct=cession_pct,
            is_reinsurer=True,
        )
        reinsurer_with_capital = reinsurer_tester.run_with_capital(capital_model, nar=reinsurer_nar)
    return cedant, reinsurer_with_capital


def _profit_test_to_dict(result: ProfitTestResult) -> dict[str, object]:
    """Flatten a ProfitTestResult into a plain dict for JSON serialisation.

    When ``result`` is a ``ProfitResultWithCapital``, the capital block
    (``initial_capital``, ``peak_capital``, ``pv_capital``,
    ``pv_capital_strain``, ``return_on_capital``, ``capital_adjusted_irr``)
    is appended. Plain ``ProfitTestResult`` instances produce the original
    schema unchanged so existing JSON consumers keep working.
    """
    out: dict[str, object] = {
        "hurdle_rate": result.hurdle_rate,
        "pv_profits": result.pv_profits,
        "pv_premiums": result.pv_premiums,
        "profit_margin": result.profit_margin,
        "irr": result.irr,
        "breakeven_year": result.breakeven_year,
        "total_undiscounted_profit": result.total_undiscounted_profit,
        "profit_by_year": result.profit_by_year.tolist(),
    }
    if isinstance(result, ProfitResultWithCapital):
        out["initial_capital"] = result.initial_capital
        out["peak_capital"] = result.peak_capital
        out["pv_capital"] = result.pv_capital
        out["pv_capital_strain"] = result.pv_capital_strain
        out["return_on_capital"] = result.return_on_capital
        out["capital_adjusted_irr"] = result.capital_adjusted_irr
    return out


def _compute_cohort_sufficiency(
    cohort: CohortResult,
    discount_rate: float,
    target_margin: float,
) -> tuple[PremiumSufficiencyResult, PremiumSufficiencyResult | None]:
    """Compute cedant + reinsurer premium-sufficiency results for a cohort (ADR-083).

    Mirrors the dual profit-test layout: the cedant view runs on the NET
    cash flows, the reinsurer view on the ceded cash flows re-labelled NET
    (``ceded_to_reinsurer_view``) when a treaty produced a ceded leg. The
    discount rate is the deal's valuation discount rate, NOT the profit
    hurdle — premium adequacy is a valuation comparison of premium against
    benefit + expense outflow, not a cost-of-capital test (ADR-082).
    """
    cedant = PremiumSufficiencyTester(
        cohort.net_cashflows, discount_rate, target_margin=target_margin
    ).run()
    reinsurer: PremiumSufficiencyResult | None = None
    if cohort.ceded_cashflows is not None:
        reinsurer = PremiumSufficiencyTester(
            ceded_to_reinsurer_view(cohort.ceded_cashflows),
            discount_rate,
            target_margin=target_margin,
        ).run()
    return cedant, reinsurer


def _sufficiency_to_dict(result: PremiumSufficiencyResult) -> dict[str, object]:
    """Flatten a PremiumSufficiencyResult into a plain dict for JSON output."""
    return {
        "discount_rate": result.discount_rate,
        "target_margin": result.target_margin,
        "pv_premiums": result.pv_premiums,
        "pv_claims": result.pv_claims,
        "pv_surrenders": result.pv_surrenders,
        "pv_benefits": result.pv_benefits,
        "pv_expenses": result.pv_expenses,
        "sufficiency_margin": result.sufficiency_margin,
        "sufficiency_ratio": result.sufficiency_ratio,
        "loss_ratio": result.loss_ratio,
        "expense_ratio": result.expense_ratio,
        "combined_ratio": result.combined_ratio,
        "is_sufficient": result.is_sufficient,
    }


def _render_sufficiency_table(
    result: PremiumSufficiencyResult,
    title: str,
    border_style: str,
) -> None:
    """Render a Rich table for one premium-sufficiency result (ADR-083)."""
    table = Table(title=title, border_style=border_style)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    def _pct(value: float | None) -> str:
        return f"{value:.2%}" if value is not None else "N/A"

    verdict = "[green]SUFFICIENT[/green]" if result.is_sufficient else "[red]INSUFFICIENT[/red]"
    table.add_row("Discount Rate", f"{result.discount_rate:.2%}")
    table.add_row("Target Margin", f"{result.target_margin:.2%}")
    table.add_row("PV Premiums", f"${result.pv_premiums:,.0f}")
    # PV Claims / PV Surrenders break out PV Benefits into its two line items
    # (ADR-085); they sum to PV Benefits by construction. Matches the Excel
    # Summary panel (ADR-084) and the dashboard pricing tiles.
    table.add_row("PV Claims", f"${result.pv_claims:,.0f}")
    table.add_row("PV Surrenders", f"${result.pv_surrenders:,.0f}")
    table.add_row("PV Benefits", f"${result.pv_benefits:,.0f}")
    table.add_row("PV Expenses", f"${result.pv_expenses:,.0f}")
    table.add_row("Sufficiency Margin", f"${result.sufficiency_margin:,.0f}")
    table.add_row("Loss Ratio", _pct(result.loss_ratio))
    table.add_row("Expense Ratio", _pct(result.expense_ratio))
    table.add_row("Combined Ratio", _pct(result.combined_ratio))
    table.add_row("Verdict", verdict)
    console.print(table)


def _render_cohort_sufficiency_tables(
    cohort: CohortResult,
    sufficiency: tuple[PremiumSufficiencyResult, PremiumSufficiencyResult | None],
) -> None:
    """Render the cedant (and reinsurer) premium-sufficiency tables (ADR-083)."""
    cedant, reinsurer = sufficiency
    _render_sufficiency_table(
        cedant,
        title=f"Premium Sufficiency — Cedant (NET) View · {cohort.product_type}",
        border_style="cyan",
    )
    if reinsurer is not None:
        _render_sufficiency_table(
            reinsurer,
            title=f"Premium Sufficiency — Reinsurer View · {cohort.product_type}",
            border_style="green",
        )


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


def _append_capital_rows(table: Table, result: ProfitTestResult) -> None:
    """Append regulatory-capital rows to a Rich profit-test table when present.

    No-op when ``result`` is a plain ``ProfitTestResult`` (i.e. the user
    did not pass ``--capital``). Keeps single-cohort and mixed-cohort
    visual output identical to pre-Slice-3 when capital is off. The rows are
    jurisdiction-agnostic (RoC / peak capital / strain), so LICAT, RBC, and
    Solvency II all render through the same path.
    """
    if not isinstance(result, ProfitResultWithCapital):
        return
    table.add_row("Peak Capital", f"${result.peak_capital:,.0f}")
    table.add_row("PV Capital (stock)", f"${result.pv_capital:,.0f}")
    table.add_row("PV Capital Strain", f"${result.pv_capital_strain:,.0f}")
    roc_str = f"{result.return_on_capital:.2%}" if result.return_on_capital is not None else "N/A"
    table.add_row("Return on Capital", roc_str)
    capital_irr_str = (
        f"{result.capital_adjusted_irr:.2%}" if result.capital_adjusted_irr is not None else "N/A"
    )
    table.add_row("Capital-Adjusted IRR", capital_irr_str)


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
    _append_capital_rows(cedant_table, cedant_result)
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
        _append_capital_rows(rei_table, reinsurer_result)
        console.print(rei_table)
    else:
        console.print("[dim]No treaty applied — reinsurer view not available.[/dim]")


def _describe_lapse(lapse: "LapseAssumption") -> str:
    """Collapse a LapseAssumption into a one-line human description.

    The committee workbook's Assumptions sheet wants a single readable
    cell, not a numeric vector. For short select periods (≤ 5 years) we
    render every duration; for longer ones we show the first two and the
    ultimate only, so the cell stays readable.
    """
    rates = lapse.select_rates
    ult = lapse.ultimate_rate
    if len(rates) == 0:
        return f"Ultimate {ult:.2%}"
    if len(rates) <= 5:
        parts = [f"Y{i + 1}={r:.2%}" for i, r in enumerate(rates)]
        parts.append(f"ultimate={ult:.2%}")
        return "; ".join(parts)
    head = ", ".join(f"Y{i + 1}={rates[i]:.2%}" for i in range(2))
    return f"{head}, …, Y{len(rates)}={rates[-1]:.2%}, ultimate={ult:.2%}"


def _cohort_to_deal_pricing_export(
    cohort: CohortResult,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    inputs: PipelineInputs,
    effective_hurdle: float,
    sufficiency: tuple[PremiumSufficiencyResult, PremiumSufficiencyResult | None],
    yrt_rate_table: object | None = None,
    rated_block: object | None = None,
    ifrs17_movement: "IFRS17MovementExport | None" = None,
    capital_model_id: str | None = None,
) -> "DealPricingExport":
    """Translate a priced cohort into a DealPricingExport bundle.

    Keeps the CLI as the only translation site between pipeline state
    (``CohortResult`` + ``PipelineInputs``) and the writer's DTO surface.
    When ``yrt_rate_table`` is supplied, it is embedded on the export so
    the writer renders the ``YRT Rate Table`` sheet (ADR-052). When
    ``rated_block`` is supplied, it is embedded on the export so the
    writer appends the rated-block panel to the Assumptions sheet
    (ADR-068). When ``ifrs17_movement`` is supplied, it is embedded on the
    export so the writer appends the ``IFRS 17 Movement`` sheet (ADR-096).
    ``capital_model_id`` (``licat`` / ``rbc`` / ``solvency2``) is recorded on
    the export so the writer names the regulatory standard on the capital-block
    header (ADR-102); ``None`` labels it LICAT for backward compatibility.
    """
    from polaris_re.utils.excel_output import (
        AssumptionsMetaExport,
        DealMetaExport,
        DealPricingExport,
    )

    deal = inputs.deal
    treaty_type = deal.treaty_type
    treaty_type_str = (
        None if treaty_type is None or str(treaty_type).lower() == "none" else str(treaty_type)
    )
    cession_pct = deal.cession_pct if treaty_type_str is not None else None

    deal_meta = DealMetaExport(
        product_type=cohort.product_type,
        n_policies=cohort.n_policies,
        face_amount=cohort.face_amount,
        treaty_type=treaty_type_str,
        cession_pct=cession_pct,
        hurdle_rate=effective_hurdle,
        discount_rate=config.discount_rate,
        projection_years=config.projection_horizon_years,
        valuation_date=config.valuation_date,
        reserve_basis=str(config.reserve_basis),
    )
    assumptions_meta = AssumptionsMetaExport(
        mortality_source=assumptions.mortality.source.value,
        mortality_multiplier=inputs.mortality.multiplier,
        lapse_description=_describe_lapse(assumptions.lapse),
        assumption_set_version=assumptions.version,
    )
    # Premium-sufficiency panel (ADR-083), precomputed once per cohort by
    # the caller at the valuation discount rate.
    suff_cedant, suff_reinsurer = sufficiency
    return DealPricingExport(
        deal_meta=deal_meta,
        assumptions_meta=assumptions_meta,
        cedant_result=cohort.cedant_result,
        reinsurer_result=cohort.reinsurer_result,
        net_cashflows=cohort.net_cashflows,
        gross_cashflows=cohort.gross_cashflows,
        ceded_cashflows=cohort.ceded_cashflows,
        scenario_results=None,
        yrt_rate_table=yrt_rate_table,  # type: ignore[arg-type]
        rated_block=rated_block,  # type: ignore[arg-type]
        premium_sufficiency_cedant=suff_cedant,
        premium_sufficiency_reinsurer=suff_reinsurer,
        ifrs17_movement=ifrs17_movement,  # type: ignore[arg-type]
        capital_model_id=capital_model_id,
    )


def _build_ifrs17_movement_export(
    cohort_inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    *,
    ra_factor: float,
    months_per_period: int,
) -> "IFRS17MovementExport":
    """Build the IFRS 17 analysis-of-change (movement) table for one product cohort.

    Mirrors the reference consumer (``POST /api/v1/ifrs17/movement``, ADR-095):
    the cohort's policies are grouped into annual issue-year cohorts, each
    issue-year group is projected GROSS on the shared calendar grid, and the
    groups are fed to :class:`IFRS17CohortManager`, which measures each cohort
    BBA at its locked-in rate and rolls it forward into an opening → closing
    movement table per component (BEL / RA / CSM).

    The locked-in discount rate is ``config.discount_rate`` for every cohort
    (a per-issue-year locked-in-rate override — already accepted by the REST
    API — is a promoted CLI follow-up). All issue-year sub-blocks of one product
    share the same projection grid, so the cohort aggregate is calendar-consistent
    (the manager raises ``PolarisValidationError`` otherwise).

    Args:
        cohort_inforce: A single-product InforceBlock (one cohort from
            ``iter_cohorts``); its policies span one or more issue years.
        assumptions: Shared AssumptionSet.
        config: Shared ProjectionConfig; ``discount_rate`` is the locked-in rate.
        ra_factor: Risk Adjustment as a fraction of |BEL|.
        months_per_period: Months aggregated into each reporting period.

    Returns:
        An ``IFRS17MovementExport`` bundling the aggregate and per-cohort
        movement tables, ready for the JSON, Rich, and Excel surfaces.
    """
    from polaris_re.analytics.ifrs17 import IFRS17CohortManager, IFRS17ContractInput
    from polaris_re.products.dispatch import get_product_engine
    from polaris_re.utils.excel_output import IFRS17MovementExport

    by_year: dict[int, list[Policy]] = {}
    for policy in cohort_inforce.policies:
        by_year.setdefault(policy.issue_date.year, []).append(policy)

    locked_in_rate = config.discount_rate
    contracts: list[IFRS17ContractInput] = []
    for issue_year in sorted(by_year):
        members = by_year[issue_year]
        sub_block = InforceBlock(policies=members, block_id=cohort_inforce.block_id)
        gross = get_product_engine(
            inforce=sub_block, assumptions=assumptions, config=config
        ).project()
        contracts.append(
            IFRS17ContractInput(
                cashflows=gross,
                issue_date=members[0].issue_date,
                locked_in_rate=locked_in_rate,
                ra_factor=ra_factor,
            )
        )

    manager = IFRS17CohortManager(contracts)
    return IFRS17MovementExport(
        aggregate=manager.aggregate_movement_table(months_per_period=months_per_period),
        cohorts=manager.cohort_movement_tables(months_per_period=months_per_period),
    )


def _ifrs17_movement_max_footing_error(export: "IFRS17MovementExport") -> float:
    """Worst footing residual across the aggregate and every per-cohort table."""
    return max(
        [
            export.aggregate.max_footing_error(),
            *(table.max_footing_error() for table in export.cohorts),
        ]
    )


def _ifrs17_movement_to_dict(
    export: "IFRS17MovementExport", months_per_period: int
) -> dict[str, object]:
    """Serialise an ``IFRS17MovementExport`` for the CLI JSON output.

    Mirrors the REST ``IFRS17MovementResponse`` shape (ADR-095) so the CLI and
    API JSON agree: reporting-period width, cohort count, the worst footing
    residual across the whole bundle, and the aggregate + per-cohort serialised
    movement tables (each table foots by construction).
    """
    return {
        "months_per_period": months_per_period,
        "n_cohorts": len(export.cohorts),
        "max_footing_error": _ifrs17_movement_max_footing_error(export),
        "aggregate": export.aggregate.to_dict(),
        "cohorts": [table.to_dict() for table in export.cohorts],
    }


def _render_ifrs17_movement(export: "IFRS17MovementExport", product_type: str) -> None:
    """Render the IFRS 17 movement table (aggregate) as two compact Rich tables.

    The first reconciles the total insurance liability (opening → closing) per
    reporting period; the second shows the closing balances by component
    (BEL / RA / CSM / total). Full per-component, per-cohort detail is in the
    JSON (``-o``) and Excel (``--excel-out``) surfaces.
    """
    aggregate = export.aggregate

    recon = Table(
        title=f"IFRS 17 Movement — Total Insurance Liability ({product_type})",
        border_style="cyan",
    )
    recon.add_column("Period", justify="right")
    for col in ("Opening", "New Business", "Interest", "Release", "Closing"):
        recon.add_column(col, justify="right")
    for row in aggregate.rows:
        total = row.total
        recon.add_row(
            str(row.period + 1),
            f"${total.opening:,.0f}",
            f"${total.new_business:,.0f}",
            f"${total.interest_accretion:,.0f}",
            f"${total.release:,.0f}",
            f"${total.closing:,.0f}",
        )
    console.print(recon)

    components = Table(
        title=f"IFRS 17 Closing Balances by Component ({product_type})",
        border_style="cyan",
    )
    components.add_column("Period", justify="right")
    for col in ("BEL", "RA", "CSM", "Total"):
        components.add_column(col, justify="right")
    for row in aggregate.rows:
        components.add_row(
            str(row.period + 1),
            f"${row.bel.closing:,.0f}",
            f"${row.ra.closing:,.0f}",
            f"${row.csm.closing:,.0f}",
            f"${row.total.closing:,.0f}",
        )
    console.print(components)

    console.print(
        f"[dim]IFRS 17 cohorts: {len(export.cohorts)} (annual issue-year) · "
        f"reporting period: {aggregate.months_per_period} months · "
        f"max footing error: {_ifrs17_movement_max_footing_error(export):.2e}. "
        f"Per-cohort detail in JSON / Excel.[/dim]"
    )


def _load_yrt_rate_table_from_dir(
    directory: Path,
    select_period: int,
    label: str | None,
    smoker_distinct: bool,
    source_hint: str,
) -> object:
    """Load a tabular ``YRTRateTable`` from a directory, exiting on error.

    Shared by the ``--yrt-rate-table`` CLI flag and the
    ``deal.yrt_rate_table_path`` config field (ADR-075) so both surfaces
    apply identical validation, loading, and console reporting. ``source_hint``
    is interpolated into the "directory not found" message so the user can
    tell which surface supplied the bad path.
    """
    if not directory.exists() or not directory.is_dir():
        console.print(
            f"[red]Error:[/red] YRT rate table directory not found ({source_hint}): {directory}"
        )
        raise typer.Exit(code=1)
    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

    try:
        table = YRTRateTable.load(
            directory=directory,
            select_period=select_period,
            table_name=label or "yrt",
            label=label,
            smoker_distinct=smoker_distinct,
        )
    except (FileNotFoundError, PolarisValidationError) as exc:
        console.print(f"[red]Error loading YRT rate table:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[dim]Loaded tabular YRT rate table from {directory} "
        f"(ages {table.min_age}-{table.max_age}, "  # type: ignore[attr-defined]
        f"{len(table.arrays)} cohorts)[/dim]"  # type: ignore[attr-defined]
    )
    return table


def _resolve_config_yrt_rate_table(inputs: PipelineInputs) -> object | None:
    """Load the tabular YRT table referenced by ``deal.yrt_rate_table_path``.

    Returns ``None`` when the config does not reference a table (the common
    flat-rate path). Shared by the ``scenario`` and ``uq`` commands (ADR-076)
    so a config that carries ``deal.yrt_rate_table_path`` is honoured there,
    not silently dropped. ``price`` keeps its own ``--yrt-rate-table``
    flag-vs-config precedence handling but resolves the config field the same
    way via :func:`_load_yrt_rate_table_from_dir`.
    """
    deal = inputs.deal
    if deal.yrt_rate_table_path is None:
        return None
    return _load_yrt_rate_table_from_dir(
        directory=deal.yrt_rate_table_path,
        select_period=deal.yrt_rate_table_select_period,
        label=deal.yrt_rate_table_label,
        smoker_distinct=deal.yrt_rate_table_smoker_distinct,
        source_hint="deal.yrt_rate_table_path",
    )


def _resolve_yrt_rate_table_flag_over_config(
    flag_table: object | None, inputs: PipelineInputs
) -> object | None:
    """Resolve the tabular YRT table for ``scenario`` / ``uq`` with the
    ``--yrt-rate-table`` flag taking precedence over ``deal.yrt_rate_table_path``.

    Mirrors the precedence ``price`` applies (ADR-075): an explicitly supplied
    flag table wins; otherwise fall back to the config-driven table (ADR-076)
    resolved by :func:`_resolve_config_yrt_rate_table`. When both are present a
    console notice records that the flag overrides the config field, matching
    the message ``price`` prints.
    """
    if flag_table is not None:
        if inputs.deal.yrt_rate_table_path is not None:
            console.print(
                "[dim]--yrt-rate-table flag overrides deal.yrt_rate_table_path from config.[/dim]"
            )
        return flag_table
    return _resolve_config_yrt_rate_table(inputs)


def _resolve_cli_perspective(perspective: str, *, has_treaty: bool) -> str:
    """Validate and resolve the ``--perspective`` flag for scenario / uq (ADR-077).

    Raises ``typer.BadParameter`` on an unknown value. When the deal has no
    real treaty the reinsurer view is undefined, so a requested
    ``"reinsurer"`` perspective is downgraded to ``"cedant"`` with a console
    notice — mirroring ``polaris price`` ("reinsurer view not available").
    The effective perspective is printed so it is always visible in the
    output.
    """
    if perspective not in ("reinsurer", "cedant"):
        raise typer.BadParameter(
            f"Unknown perspective '{perspective}'. Choose 'reinsurer' or 'cedant'."
        )
    effective = perspective
    if perspective == "reinsurer" and not has_treaty:
        console.print(
            "[yellow]No treaty configured — reporting cedant view "
            "(reinsurer view not available).[/yellow]"
        )
        effective = "cedant"
    console.print(f"[dim]Profit-test perspective: {effective}[/dim]")
    return effective


def _resolve_excel_path(base: Path, cohort_id: str, n_cohorts: int) -> Path:
    """Derive the per-cohort Excel path.

    Single-cohort runs write to the supplied path as-is. Mixed-cohort
    runs insert the cohort identifier before the suffix so each workbook
    has a unique filename (e.g. ``deal.xlsx`` → ``deal-TERM.xlsx``).
    """
    if n_cohorts <= 1:
        return base
    suffix = base.suffix or ".xlsx"
    stem = base.stem
    return base.with_name(f"{stem}-{cohort_id}{suffix}")


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
    sufficiency_target_margin: Annotated[
        float,
        typer.Option(
            "--sufficiency-target-margin",
            help=(
                "Premium-sufficiency target profit margin as a fraction of PV "
                "premiums, in [0, 1) (ADR-083). The premium is reported "
                "'sufficient' when its post-cost margin ratio meets this target. "
                "Default 0.0 tests bare cost coverage."
            ),
        ),
    ] = 0.0,
    excel_out: Annotated[
        Path | None,
        typer.Option(
            "--excel-out",
            help=(
                "Path to write a formatted deal-pricing Excel workbook. "
                "For mixed-cohort blocks, one file per cohort is written "
                "with the cohort id appended to the stem."
            ),
        ),
    ] = None,
    capital: Annotated[
        str | None,
        typer.Option(
            "--capital",
            help=(
                "Regulatory capital model: 'licat' (Canada OSFI, ADR-047/048), "
                "'rbc' (US NAIC RBC, ADR-098), or 'solvency2' (EU SCR, ADR-100). "
                "Each cohort's cedant and reinsurer profit tests run with the "
                "selected jurisdiction's per-product factor model and the JSON / "
                "Excel output gain return-on-capital, peak capital, and PV "
                "capital strain (ADR-049/101). Default: not applied."
            ),
        ),
    ] = None,
    yrt_rate_table_dir: Annotated[
        Path | None,
        typer.Option(
            "--yrt-rate-table",
            help=(
                "Directory of tabular YRT rate CSVs (ADR-052). When set, "
                "YRT premiums are billed from the table indexed by (age, "
                "sex, smoker, duration) instead of the flat / "
                "mortality-derived rate. The directory must contain one "
                "CSV per (sex, smoker) cohort using the schema "
                "'{label}_{sex}_{smoker}.csv'. Implies seriatim projection."
            ),
        ),
    ] = None,
    yrt_rate_table_select_period: Annotated[
        int,
        typer.Option(
            "--yrt-rate-table-select-period",
            help=(
                "Number of select-period columns (dur_1..dur_N) in the "
                "tabular YRT rate CSVs. Used only with --yrt-rate-table."
            ),
        ),
    ] = 3,
    yrt_rate_table_label: Annotated[
        str | None,
        typer.Option(
            "--yrt-rate-table-label",
            help=(
                "Filename prefix in the YRT rate table directory. "
                "Defaults to 'yrt' (so files are 'yrt_male_ns.csv' etc.). "
                "Used only with --yrt-rate-table."
            ),
        ),
    ] = None,
    yrt_rate_table_smoker_distinct: Annotated[
        bool,
        typer.Option(
            "--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate",
            help=(
                "When --yrt-rate-table-smoker-distinct (default), expect "
                "separate '_ns' and '_smoker' files per sex. When "
                "--yrt-rate-table-aggregate, expect a single '_unknown' "
                "file per sex."
            ),
        ),
    ] = True,
    reserve_basis: Annotated[
        str | None,
        typer.Option(
            "--reserve-basis",
            help=(
                "Reserve valuation basis: NET_PREMIUM (default), CRVM, VM20, "
                "or GAAP (reserve-basis epic). Lets a reinsurer reproduce the "
                "cedant's reserve method, which drives the YRT NAR, the "
                "coinsurance reserve transfer, and the profit signature. "
                "Overrides any 'reserve_basis' in the config. Selecting a "
                "non-default basis changes the reserve (and therefore the "
                "priced numbers); NET_PREMIUM is byte-identical to prior runs. "
                "An unsupported basis for the product raises an error."
            ),
        ),
    ] = None,
    ifrs17_movement: Annotated[
        bool,
        typer.Option(
            "--ifrs17-movement/--no-ifrs17-movement",
            help=(
                "Emit the IFRS 17 analysis-of-change (movement) table per "
                "product cohort (IFRS 17 epic, ADR-093..096). Policies are "
                "grouped into annual issue-year cohorts, each measured BBA at "
                "the config discount rate (locked-in) and rolled forward "
                "opening → new business → interest accretion → release → "
                "closing for BEL / RA / CSM. Added to the JSON output and, with "
                "--excel-out, the 'IFRS 17 Movement' workbook sheet. Off by "
                "default — runs without it are byte-identical to prior output."
            ),
        ),
    ] = False,
    ifrs17_ra_factor: Annotated[
        float,
        typer.Option(
            "--ifrs17-ra-factor",
            help=(
                "Risk Adjustment as a fraction of |BEL| for the IFRS 17 "
                "movement table (simplified cost-of-capital RA), in [0, 0.50]. "
                "Used only with --ifrs17-movement. Default 0.05."
            ),
        ),
    ] = 0.05,
    ifrs17_months_per_period: Annotated[
        int,
        typer.Option(
            "--ifrs17-months-per-period",
            help=(
                "Months aggregated into each IFRS 17 reporting period "
                "(12 = annual). Used only with --ifrs17-movement. Default 12."
            ),
        ),
    ] = 12,
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

    from polaris_re.analytics.capital_base import SUPPORTED_CAPITAL_MODELS

    capital_model_id: str | None = None
    if capital is not None:
        capital_norm = capital.strip().lower()
        if capital_norm not in SUPPORTED_CAPITAL_MODELS:
            supported = ", ".join(f"'{m}'" for m in SUPPORTED_CAPITAL_MODELS)
            console.print(
                f"[red]Error:[/red] Unknown --capital value '{capital}'. Supported: {supported}."
            )
            raise typer.Exit(code=1)
        capital_model_id = capital_norm

    # Validate the reserve-basis flag eagerly (before any projection work) so a
    # typo fails with a clear message and the list of valid bases, mirroring
    # the --capital validation above. The resolved value (or None to defer to
    # the config) is threaded into the pipeline builder below.
    from polaris_re.core.reserve_basis import ReserveBasis

    if reserve_basis is not None:
        try:
            reserve_basis = ReserveBasis(reserve_basis.strip().upper()).value
        except ValueError:
            valid = ", ".join(b.value for b in ReserveBasis)
            console.print(
                f"[red]Error:[/red] Unknown --reserve-basis value '{reserve_basis}'. "
                f"Valid values: {valid}."
            )
            raise typer.Exit(code=1) from None

    # Tabular YRT rate table (ADR-052) — loaded once and reused across
    # cohorts. The label defaults to "yrt" so the typical filename is
    # ``yrt_male_ns.csv`` etc. unless the user overrides it. The CLI flag is
    # loaded here (eagerly, so bad paths fail before any projection work);
    # the config-driven ``deal.yrt_rate_table_path`` equivalent (ADR-075) is
    # resolved after the config is parsed, below, and the flag takes
    # precedence over it.
    yrt_rate_table_obj: object | None = None
    if yrt_rate_table_dir is not None:
        yrt_rate_table_obj = _load_yrt_rate_table_from_dir(
            directory=yrt_rate_table_dir,
            select_period=yrt_rate_table_select_period,
            label=yrt_rate_table_label,
            smoker_distinct=yrt_rate_table_smoker_distinct,
            source_hint="--yrt-rate-table",
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Building pipeline...", total=None)
        if config_path is not None:
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                config_path, inforce_path, reserve_basis_override=reserve_basis
            )
            console.print(f"[dim]Loaded config from {config_path}[/dim]")
        else:
            # Demo mode: use shipped fixtures
            demo_dir = Path(__file__).parent.parent.parent
            demo_config = demo_dir / "data" / "configs" / "demo.json"
            demo_csv = demo_dir / "data" / "inputs" / "demo.csv"
            inforce, assumptions, config, inputs = _build_pipeline_from_config(
                demo_config,
                demo_csv if demo_csv.exists() else None,
                reserve_basis_override=reserve_basis,
            )
            console.print("[dim]No --config supplied — running demo mode[/dim]")

    # Config-driven tabular YRT table (deal.yrt_rate_table_path, ADR-075).
    # The --yrt-rate-table flag, loaded above, takes precedence; the config
    # field is the YAML/JSON equivalent for configs that want to reference a
    # table directory without a flag. Resolved here (after config parse) so
    # inputs.deal is populated, using the table params from the deal config.
    if inputs.deal.yrt_rate_table_path is not None:
        if yrt_rate_table_obj is not None:
            console.print(
                "[dim]--yrt-rate-table flag overrides deal.yrt_rate_table_path from config.[/dim]"
            )
        else:
            yrt_rate_table_obj = _load_yrt_rate_table_from_dir(
                directory=inputs.deal.yrt_rate_table_path,
                select_period=inputs.deal.yrt_rate_table_select_period,
                label=inputs.deal.yrt_rate_table_label,
                smoker_distinct=inputs.deal.yrt_rate_table_smoker_distinct,
                source_hint="deal.yrt_rate_table_path",
            )

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

    # Fail fast on an out-of-range sufficiency target margin (ADR-083) so the
    # user sees a clean CLI error rather than a traceback mid-projection.
    if not 0.0 <= sufficiency_target_margin < 1.0:
        raise typer.BadParameter(
            f"--sufficiency-target-margin must be in [0, 1), got {sufficiency_target_margin}."
        )

    # Fail fast on out-of-range IFRS 17 movement parameters (ADR-096) before
    # any projection work, mirroring the REST contract (ra_factor in [0, 0.50],
    # months_per_period >= 1).
    if ifrs17_movement:
        if not 0.0 <= ifrs17_ra_factor <= 0.50:
            raise typer.BadParameter(
                f"--ifrs17-ra-factor must be in [0, 0.50], got {ifrs17_ra_factor}."
            )
        if ifrs17_months_per_period < 1:
            raise typer.BadParameter(
                f"--ifrs17-months-per-period must be >= 1, got {ifrs17_months_per_period}."
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
                    capital_model_id=capital_model_id,
                    yrt_rate_table=yrt_rate_table_obj,
                )
            )

        progress.update(task, completed=True)

    # Premium sufficiency is computed once per cohort here (ADR-083) and
    # reused by the Rich tables, the JSON block, and the Excel export — the
    # PV math is cheap but recomputing it per consumer is needless work.
    sufficiency_by_cohort: dict[
        int, tuple[PremiumSufficiencyResult, PremiumSufficiencyResult | None]
    ] = {
        id(c): _compute_cohort_sufficiency(c, config.discount_rate, sufficiency_target_margin)
        for c in cohort_results
    }

    # IFRS 17 movement table per product cohort (ADR-093..096), opt-in via
    # --ifrs17-movement. Each cohort's policies are re-grouped into annual
    # issue-year cohorts and rolled forward; the result feeds the Rich, JSON,
    # and (with --excel-out) Excel surfaces. Keyed by id(cohort) so it joins
    # the cohort_results / sufficiency dicts.
    ifrs17_by_cohort: dict[int, IFRS17MovementExport] = {}
    if ifrs17_movement:
        for (_product_type, cohort_inforce), cohort in zip(
            cohorts_split, cohort_results, strict=True
        ):
            ifrs17_by_cohort[id(cohort)] = _build_ifrs17_movement_export(
                cohort_inforce,
                assumptions,
                config,
                ra_factor=ifrs17_ra_factor,
                months_per_period=ifrs17_months_per_period,
            )

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
        _render_cohort_sufficiency_tables(cohort, sufficiency_by_cohort[id(cohort)])
        if ifrs17_movement:
            _render_ifrs17_movement(ifrs17_by_cohort[id(cohort)], cohort.product_type)

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
        suff_cedant, suff_reinsurer = sufficiency_by_cohort[id(c)]
        cohort_entry: dict[str, object] = {
            "product_type": c.product_type,
            "n_policies": c.n_policies,
            "face_amount": c.face_amount,
            "cedant": cedant_dict,
            "reinsurer": reinsurer_dict,
            "premium_sufficiency": {
                "cedant": _sufficiency_to_dict(suff_cedant),
                "reinsurer": (
                    _sufficiency_to_dict(suff_reinsurer) if suff_reinsurer is not None else None
                ),
            },
        }
        if ifrs17_movement:
            cohort_entry["ifrs17_movement"] = _ifrs17_movement_to_dict(
                ifrs17_by_cohort[id(c)], ifrs17_months_per_period
            )
        cohorts_out.append(cohort_entry)
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
            "reserve_basis": str(config.reserve_basis),
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
        suff_cedant, suff_reinsurer = sufficiency_by_cohort[id(first)]
        output_data["premium_sufficiency"] = {
            "cedant": _sufficiency_to_dict(suff_cedant),
            "reinsurer": (
                _sufficiency_to_dict(suff_reinsurer) if suff_reinsurer is not None else None
            ),
        }
        if ifrs17_movement:
            output_data["ifrs17_movement"] = _ifrs17_movement_to_dict(
                ifrs17_by_cohort[id(first)], ifrs17_months_per_period
            )

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

    if excel_out is not None:
        from polaris_re.utils.excel_output import RatedBlockExport, write_deal_pricing_excel

        effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
        # Block-level rated-block panel, reused across per-cohort workbooks
        # (ADR-068). Matches the once-per-run CLI Rich panel above. When
        # ``n_rated == 0`` the writer suppresses the panel even though we
        # pass the DTO, keeping all-standard workbooks byte-identical to
        # pre-ADR-068 output.
        rated_block_export = RatedBlockExport(
            n_policies=int(rated_summary["n_policies"]),
            n_rated=int(rated_summary["n_rated"]),
            pct_rated_by_count=float(rated_summary["pct_rated_by_count"]),
            pct_rated_by_face=float(rated_summary["pct_rated_by_face"]),
            face_weighted_mean_multiplier=float(rated_summary["face_weighted_mean_multiplier"]),
            max_multiplier=float(rated_summary["max_multiplier"]),
            max_flat_extra_per_1000=float(rated_summary["max_flat_extra_per_1000"]),
        )
        excel_out.parent.mkdir(parents=True, exist_ok=True)
        written_paths: list[Path] = []
        for cohort in cohort_results:
            export = _cohort_to_deal_pricing_export(
                cohort=cohort,
                assumptions=assumptions,
                config=config,
                inputs=inputs,
                effective_hurdle=effective_hurdle,
                sufficiency=sufficiency_by_cohort[id(cohort)],
                yrt_rate_table=yrt_rate_table_obj,
                rated_block=rated_block_export,
                ifrs17_movement=(ifrs17_by_cohort.get(id(cohort)) if ifrs17_movement else None),
                capital_model_id=capital_model_id,
            )
            out_path = _resolve_excel_path(excel_out, cohort.product_type, n_cohorts)
            write_deal_pricing_excel(export, out_path)
            written_paths.append(out_path)
        for p in written_paths:
            console.print(f"[green]Excel workbook written to:[/green] {p}")

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
    perspective: Annotated[
        str,
        typer.Option(
            "--perspective",
            help=(
                "Profit-test perspective: 'reinsurer' (ceded economics, matches "
                "polaris price) or 'cedant' (retained net). Default reinsurer."
            ),
        ),
    ] = "reinsurer",
    yrt_rate_table_dir: Annotated[
        Path | None,
        typer.Option(
            "--yrt-rate-table",
            help=(
                "Directory of tabular YRT rate CSVs (ADR-052). Ad-hoc "
                "equivalent of the config field deal.yrt_rate_table_path (the "
                "flag takes precedence when both are supplied). YRT premiums "
                "are billed from the table indexed by (age, sex, smoker, "
                "duration) instead of the flat / mortality-derived rate; the "
                "directory must contain one CSV per (sex, smoker) cohort using "
                "the schema '{label}_{sex}_{smoker}.csv'. Implies seriatim "
                "projection."
            ),
        ),
    ] = None,
    yrt_rate_table_select_period: Annotated[
        int,
        typer.Option(
            "--yrt-rate-table-select-period",
            help=(
                "Number of select-period columns (dur_1..dur_N) in the "
                "tabular YRT rate CSVs. Used only with --yrt-rate-table."
            ),
        ),
    ] = 3,
    yrt_rate_table_label: Annotated[
        str | None,
        typer.Option(
            "--yrt-rate-table-label",
            help=(
                "Filename prefix in the YRT rate table directory. "
                "Defaults to 'yrt' (so files are 'yrt_male_ns.csv' etc.). "
                "Used only with --yrt-rate-table."
            ),
        ),
    ] = None,
    yrt_rate_table_smoker_distinct: Annotated[
        bool,
        typer.Option(
            "--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate",
            help=(
                "When --yrt-rate-table-smoker-distinct (default), expect "
                "separate '_ns' and '_smoker' files per sex. When "
                "--yrt-rate-table-aggregate, expect a single '_unknown' "
                "file per sex."
            ),
        ),
    ] = True,
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

    # Ad-hoc tabular YRT rate table (--yrt-rate-table), loaded eagerly so a bad
    # path fails before any projection work. Takes precedence over the
    # config-driven deal.yrt_rate_table_path, matching price (ADR-075).
    flag_yrt_rate_table: object | None = None
    if yrt_rate_table_dir is not None:
        flag_yrt_rate_table = _load_yrt_rate_table_from_dir(
            directory=yrt_rate_table_dir,
            select_period=yrt_rate_table_select_period,
            label=yrt_rate_table_label,
            smoker_distinct=yrt_rate_table_smoker_distinct,
            source_hint="--yrt-rate-table",
        )

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

        # Tabular YRT table: the --yrt-rate-table flag (loaded above) takes
        # precedence over the config-driven deal.yrt_rate_table_path (ADR-076),
        # matching price's flag-over-config precedence (ADR-075).
        yrt_rate_table_obj = _resolve_yrt_rate_table_flag_over_config(flag_yrt_rate_table, inputs)

        # Derive YRT rate from base gross projection (ADR-038). The tabular
        # path needs a seriatim projection for the parity dump + treaty apply.
        gross = get_product_engine(inforce=inforce, assumptions=assumptions, config=config).project(
            seriatim=yrt_rate_table_obj is not None
        )
        face_amount = inforce.total_face_amount()

        treaty_obj, use_policy_cession = _build_treaty_for_pipeline(
            inputs, gross, face_amount, inforce, yrt_rate_table=yrt_rate_table_obj
        )
        # Whether the config carries a real treaty (before the gross-only
        # fallback below). Drives the reinsurer-view availability (ADR-077).
        has_real_treaty = treaty_obj is not None

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

        effective_perspective = _resolve_cli_perspective(perspective, has_treaty=has_real_treaty)
        effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
        runner = ScenarioRunner(
            inforce=inforce,
            base_assumptions=assumptions,
            config=config,
            treaty=treaty_obj,
            hurdle_rate=effective_hurdle,
            perspective=effective_perspective,  # type: ignore[arg-type]
        )
        results = runner.run()

    # Display scenario table
    table = Table(title=f"Scenario Analysis ({effective_perspective} view)", border_style="cyan")
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
    _write_output(
        {"perspective": effective_perspective, "scenarios": all_rows},
        output_path,
        "scenario_result",
    )


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
    perspective: Annotated[
        str,
        typer.Option(
            "--perspective",
            help=(
                "Profit-test perspective: 'reinsurer' (ceded economics, matches "
                "polaris price) or 'cedant' (retained net). Default reinsurer."
            ),
        ),
    ] = "reinsurer",
    yrt_rate_table_dir: Annotated[
        Path | None,
        typer.Option(
            "--yrt-rate-table",
            help=(
                "Directory of tabular YRT rate CSVs (ADR-052). Ad-hoc "
                "equivalent of the config field deal.yrt_rate_table_path (the "
                "flag takes precedence when both are supplied). YRT premiums "
                "are billed from the table indexed by (age, sex, smoker, "
                "duration) instead of the flat / mortality-derived rate; the "
                "directory must contain one CSV per (sex, smoker) cohort using "
                "the schema '{label}_{sex}_{smoker}.csv'. Implies seriatim "
                "projection."
            ),
        ),
    ] = None,
    yrt_rate_table_select_period: Annotated[
        int,
        typer.Option(
            "--yrt-rate-table-select-period",
            help=(
                "Number of select-period columns (dur_1..dur_N) in the "
                "tabular YRT rate CSVs. Used only with --yrt-rate-table."
            ),
        ),
    ] = 3,
    yrt_rate_table_label: Annotated[
        str | None,
        typer.Option(
            "--yrt-rate-table-label",
            help=(
                "Filename prefix in the YRT rate table directory. "
                "Defaults to 'yrt' (so files are 'yrt_male_ns.csv' etc.). "
                "Used only with --yrt-rate-table."
            ),
        ),
    ] = None,
    yrt_rate_table_smoker_distinct: Annotated[
        bool,
        typer.Option(
            "--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate",
            help=(
                "When --yrt-rate-table-smoker-distinct (default), expect "
                "separate '_ns' and '_smoker' files per sex. When "
                "--yrt-rate-table-aggregate, expect a single '_unknown' "
                "file per sex."
            ),
        ),
    ] = True,
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

    # Ad-hoc tabular YRT rate table (--yrt-rate-table), loaded eagerly so a bad
    # path fails before any projection work. Takes precedence over the
    # config-driven deal.yrt_rate_table_path, matching price (ADR-075).
    flag_yrt_rate_table: object | None = None
    if yrt_rate_table_dir is not None:
        flag_yrt_rate_table = _load_yrt_rate_table_from_dir(
            directory=yrt_rate_table_dir,
            select_period=yrt_rate_table_select_period,
            label=yrt_rate_table_label,
            smoker_distinct=yrt_rate_table_smoker_distinct,
            source_hint="--yrt-rate-table",
        )

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

        # Tabular YRT table: the --yrt-rate-table flag (loaded above) takes
        # precedence over the config-driven deal.yrt_rate_table_path (ADR-076),
        # matching price's flag-over-config precedence (ADR-075).
        yrt_rate_table_obj = _resolve_yrt_rate_table_flag_over_config(flag_yrt_rate_table, inputs)

        # Derive YRT rate from base gross projection (ADR-038). The tabular
        # path needs a seriatim projection for the parity dump + treaty apply.
        gross = get_product_engine(inforce=inforce, assumptions=assumptions, config=config).project(
            seriatim=yrt_rate_table_obj is not None
        )
        face_amount = inforce.total_face_amount()

        treaty_obj, use_policy_cession = _build_treaty_for_pipeline(
            inputs, gross, face_amount, inforce, yrt_rate_table=yrt_rate_table_obj
        )

        # Whether the config carries a real treaty. Drives the reinsurer-view
        # availability (ADR-077). MonteCarloUQ accepts treaty=None directly.
        has_real_treaty = treaty_obj is not None

        # Parity diagnostic dump (set POLARIS_PARITY_DEBUG=1 to enable)
        if treaty_obj is not None:
            inforce_arg = inforce if use_policy_cession else None
            _net, _ceded = treaty_obj.apply(gross, inforce=inforce_arg)
            dump_parity_debug("cli_uq", gross, _net, _ceded)
        else:
            dump_parity_debug("cli_uq", gross)

        effective_perspective = _resolve_cli_perspective(perspective, has_treaty=has_real_treaty)
        effective_hurdle = hurdle_rate if hurdle_rate != 0.10 else inputs.deal.hurdle_rate
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty_obj,
            hurdle_rate=effective_hurdle,
            n_scenarios=n_scenarios,
            seed=seed,
            perspective=effective_perspective,  # type: ignore[arg-type]
        )
        result = uq.run()

    # Display summary statistics
    table = Table(
        title=f"Monte Carlo UQ Summary (n={n_scenarios}, {effective_perspective} view)",
        border_style="cyan",
    )
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
        "perspective": effective_perspective,
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
    table: Annotated[
        bool,
        typer.Option(
            "--table/--no-table",
            help=(
                "Emit a YRTRateTable (age x sex x smoker x duration grid) "
                "via YRTRateSchedule.generate_table(). When set, --output "
                ".xlsx writes a tabular workbook consumable by "
                "`polaris price --yrt-rate-table` (ADR-053)."
            ),
        ),
    ] = False,
    select_period: Annotated[
        int,
        typer.Option(
            "--select-period",
            help=(
                "Select period (years) for the generated rate table. "
                "Only used with --table. Rates are broadcast across the "
                "select columns in --solve-mode flat; --solve-mode "
                "per_duration solves each column independently (ADR-063)."
            ),
            min=0,
        ),
    ] = 0,
    solve_mode: Annotated[
        Literal["flat", "per_duration"],
        typer.Option(
            "--solve-mode",
            help=(
                "Rate-table solver mode (ADR-063). 'flat' solves one rate per "
                "(age, sex, smoker) row and broadcasts across the select "
                "columns. 'per_duration' solves each (age, duration) cell "
                "independently. Only meaningful with --table."
            ),
        ),
    ] = "flat",
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

    Uses synthetic mortality and lapse tables (demo mode). By default, prints
    one row per (age, sex, smoker) and supports CSV / Excel / JSON export of
    that flat schedule.

    With ``--table`` the command instead emits a full ``YRTRateTable``
    (cohort-keyed 2-D arrays of shape ``(n_ages, select_period + 1)``) that
    can be loaded via ``YRTRateTable.from_arrays`` or fed to
    ``polaris price --yrt-rate-table`` after writing the workbook to disk.
    """
    _header()

    if not table and solve_mode != "flat":
        console.print(
            "[red]✗ --solve-mode is only meaningful with --table "
            "(the flat-schedule path has no per-duration solver).[/red]"
        )
        raise typer.Exit(code=1)

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
        if table:
            # Tabular path — solve the per-(age, sex, smoker) grid and pack
            # it into a YRTRateTable. solve_mode selects between flat
            # (single rate per row, broadcast across select columns) and
            # per_duration (independent solve per (age, duration) cell)
            # — ADR-063. UNKNOWN smoker is used because the demo mortality
            # table is aggregate.
            rate_table = scheduler.generate_table(
                ages=age_list,
                sexes=[Sex.MALE],
                smoker_statuses=[SmokerStatus.UNKNOWN],
                policy_term=term,
                select_period_years=select_period,
                solve_mode=solve_mode,
            )
            result_df = None
        else:
            # Flat schedule — one row per cohort.
            result_df = scheduler.generate(
                ages=age_list,
                sexes=[Sex.MALE],
                smoker_statuses=[SmokerStatus.UNKNOWN],
                policy_term=term,
            )
            rate_table = None

    if table and rate_table is not None:
        _render_yrt_rate_table(rate_table, target_irr)
    elif result_df is not None:
        # Display table
        result_table = Table(title=f"YRT Rate Schedule (Target IRR = {target_irr:.1%})")
        result_table.add_column("Issue Age", justify="center")
        result_table.add_column("Sex")
        result_table.add_column("Smoker")
        result_table.add_column("Term")
        result_table.add_column("Rate/$1000", justify="right")

        for row in result_df.iter_rows(named=True):
            rate_str = (
                f"{row['rate_per_1000']:.4f}" if not np.isnan(row["rate_per_1000"]) else "N/A"
            )
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
        if table and rate_table is not None:
            if output.suffix != ".xlsx":
                console.print(
                    "[red]✗ --table output must be .xlsx (CSV does not preserve "
                    "the cohort-keyed 2-D layout). Re-run with -o NAME.xlsx.[/red]"
                )
                raise typer.Exit(code=1)
            from polaris_re.utils.excel_output import write_yrt_rate_table_excel

            write_yrt_rate_table_excel(rate_table, output)
        elif result_df is not None:
            if output.suffix == ".xlsx":
                from polaris_re.utils.excel_output import write_rate_schedule_excel

                write_rate_schedule_excel(result_df, output)
            else:
                result_df.write_csv(output)
        console.print(f"\nResults written to {output}")

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        if table and rate_table is not None:
            json_data = _yrt_rate_table_to_dict(rate_table)
        else:
            assert result_df is not None
            json_data = result_df.to_dicts()
        output_json.write_text(json.dumps(json_data, indent=2, default=str))
        console.print(f"JSON written to {output_json}")


def _render_yrt_rate_table(rate_table: object, target_irr: float) -> None:
    """Print one Rich table per cohort for a generated ``YRTRateTable``.

    Cells whose rate was forward/back-filled (rather than directly solved
    by brentq) are marked with a trailing ``*`` so reviewers can
    distinguish authoritative cells from interpolated fill-in (ADR-054).
    A footer caption is printed once per cohort whenever any cell in
    that cohort is filled.
    """
    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

    if not isinstance(rate_table, YRTRateTable):
        raise PolarisValidationError(f"Expected YRTRateTable, got {type(rate_table).__name__}.")
    select_period = rate_table.select_period_years
    headers = ["Age"] + [f"dur_{i}" for i in range(1, select_period + 1)] + ["ultimate"]
    for cohort_key in sorted(rate_table.arrays.keys()):
        arr = rate_table.arrays[cohort_key]
        title = (
            f"YRT Rate Table — cohort {cohort_key} (Target IRR = {target_irr:.1%}, $/$1,000 NAR)"
        )
        rich_tbl = Table(title=title)
        for h in headers:
            rich_tbl.add_column(h, justify="right" if h != "Age" else "center")
        mask = arr.solved_mask
        for age_offset in range(arr.rates.shape[0]):
            age_val = arr.min_age + age_offset
            row_cells: list[str] = [str(age_val)]
            for col_offset in range(arr.rates.shape[1]):
                rate = float(arr.rates[age_offset, col_offset])
                is_solved = True if mask is None else bool(mask[age_offset, col_offset])
                suffix = "" if is_solved else "*"
                row_cells.append(f"{rate:.4f}{suffix}")
            rich_tbl.add_row(*row_cells)
        console.print(rich_tbl)
        if not arr.is_fully_solved:
            console.print(
                "[dim italic]"
                "* = forward/back-filled from a solved row "
                "(age was not directly solved; ADR-054)."
                "[/dim italic]"
            )


def _yrt_rate_table_to_dict(rate_table: object) -> dict[str, object]:
    """Serialise a ``YRTRateTable`` to a JSON-friendly dict.

    Each cohort dict carries a ``solved_mask`` (``list[list[bool]]``)
    when the table was generated with per-cell solver provenance
    (ADR-054). CSV-loaded tables omit the field (mask is ``None``)
    because every loaded cell is authoritative.
    """
    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

    if not isinstance(rate_table, YRTRateTable):
        raise PolarisValidationError(f"Expected YRTRateTable, got {type(rate_table).__name__}.")
    cohorts: dict[str, dict[str, object]] = {}
    for key in sorted(rate_table.arrays.keys()):
        arr = rate_table.arrays[key]
        entry: dict[str, object] = {
            "min_age": int(arr.min_age),
            "max_age": int(arr.max_age),
            "select_period": int(arr.select_period),
            "rates": arr.rates.tolist(),
        }
        if arr.solved_mask is not None:
            entry["solved_mask"] = arr.solved_mask.tolist()
        cohorts[key] = entry
    return {
        "table_name": rate_table.table_name,
        "min_age": int(rate_table.min_age),
        "max_age": int(rate_table.max_age),
        "select_period_years": int(rate_table.select_period_years),
        "cohorts": cohorts,
    }


portfolio_app = typer.Typer(
    name="portfolio",
    help="Multi-deal portfolio aggregation — reinsurer-level book metrics (ADR-057).",
    rich_markup_mode="rich",
)
app.add_typer(portfolio_app, name="portfolio")


def _load_portfolio_config(config_path: Path) -> dict:  # type: ignore[type-arg]
    """Load a portfolio config from YAML or JSON.

    The format is inferred from the file suffix (``.yaml`` / ``.yml`` →
    YAML; otherwise JSON). YAML is a superset of JSON so either format
    parses identically through ``yaml.safe_load``, but JSON files are
    routed through ``json.loads`` so error messages match the rest of the
    CLI.
    """
    if not config_path.exists():
        console.print(f"[red]Error:[/red] Portfolio config not found: {config_path}")
        raise typer.Exit(code=1)
    text = config_path.read_text()
    suffix = config_path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            import yaml

            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
    except Exception as exc:  # broad — catches yaml.YAMLError and json.JSONDecodeError
        console.print(f"[red]Error parsing portfolio config:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if not isinstance(data, dict):
        console.print(
            f"[red]Error:[/red] Portfolio config must be a mapping, got {type(data).__name__}."
        )
        raise typer.Exit(code=1)
    return data


def _build_portfolio_from_config(
    config_path: Path,
) -> tuple[object, float]:
    """Build a ``Portfolio`` from a YAML / JSON portfolio config.

    Returns ``(portfolio, hurdle_rate)``. Each entry in ``deals`` is parsed
    through the same ``_parse_config_to_pipeline_inputs`` helper used by
    ``polaris price`` so per-deal config keys (mortality, lapse, deal)
    behave identically across single-deal and portfolio commands.
    """
    from polaris_re.analytics.portfolio import Portfolio

    raw = _load_portfolio_config(config_path)

    hurdle_rate = float(raw.get("hurdle_rate", 0.10))
    deals_raw = raw.get("deals")
    if not isinstance(deals_raw, list) or len(deals_raw) == 0:
        console.print("[red]Error:[/red] Portfolio config must contain a non-empty 'deals' list.")
        raise typer.Exit(code=1)

    portfolio = Portfolio(name=str(raw.get("name", "portfolio")))
    for idx, deal_raw in enumerate(deals_raw):
        if not isinstance(deal_raw, dict):
            console.print(
                f"[red]Error:[/red] Deal #{idx} must be a mapping, got {type(deal_raw).__name__}."
            )
            raise typer.Exit(code=1)
        deal_id = deal_raw.get("deal_id")
        cedant = deal_raw.get("cedant")
        if not deal_id or not cedant:
            console.print(f"[red]Error:[/red] Deal #{idx} must specify 'deal_id' and 'cedant'.")
            raise typer.Exit(code=1)

        inputs, policies_raw = _parse_config_to_pipeline_inputs(deal_raw)

        # Inforce: either an external CSV reference, or inline policies.
        inforce_csv = deal_raw.get("inforce_csv")
        if inforce_csv is not None:
            inforce_path = Path(str(inforce_csv))
            if not inforce_path.exists():
                console.print(
                    f"[red]Error:[/red] Deal {deal_id!r} inforce_csv not found: {inforce_path}"
                )
                raise typer.Exit(code=1)
            inforce = load_inforce(csv_path=inforce_path)
        elif policies_raw:
            inforce = load_inforce(policies_dict=policies_raw)
        else:
            console.print(
                f"[red]Error:[/red] Deal {deal_id!r} must specify 'inforce_csv' or 'policies'."
            )
            raise typer.Exit(code=1)

        inforce, assumptions, config = build_pipeline(inforce, inputs)
        face = inforce.total_face_amount()

        # YRT rate derivation mirrors `polaris price`: when treaty_type is YRT
        # and no flat rate is supplied, derive a mortality-based rate from a
        # one-off gross projection so ceded premiums are calibrated to the
        # block's actual claims, not zero (which would happen with a None
        # rate and yield a claims-only cession).
        yrt_rate = inputs.deal.yrt_rate_per_1000
        if inputs.deal.treaty_type == "YRT" and yrt_rate is None:
            from polaris_re.products.dispatch import get_product_engine

            gross_for_rate = get_product_engine(
                inforce=inforce, assumptions=assumptions, config=config
            ).project()
            yrt_rate = derive_yrt_rate(gross_for_rate, face, inputs.deal.yrt_loading)

        treaty = build_treaty(
            treaty_type=inputs.deal.treaty_type,
            cession_pct=inputs.deal.cession_pct,
            face_amount=face,
            modco_rate=inputs.deal.modco_rate,
            yrt_rate_per_1000=yrt_rate,
            treaty_name=f"{deal_id}-{inputs.deal.treaty_type}",
        )
        if treaty is None:
            console.print(
                f"[red]Error:[/red] Deal {deal_id!r}: portfolio requires a proportional "
                f"treaty (YRT / Coinsurance / Modco); got {inputs.deal.treaty_type!r}."
            )
            raise typer.Exit(code=1)
        try:
            portfolio.add_deal(
                deal_id=str(deal_id),
                cedant=str(cedant),
                inforce=inforce,
                assumptions=assumptions,
                config=config,
                treaty=treaty,
            )
        except PolarisValidationError as exc:
            console.print(f"[red]Error adding deal {deal_id!r}:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    return portfolio, hurdle_rate


_PORTFOLIO_CONCENTRATION_BASES: tuple[str, ...] = (
    "ceded_face",
    "ceded_nar_peak",
    "pv_premium",
)

_PORTFOLIO_CONCENTRATION_BASIS_LABELS: dict[str, str] = {
    "ceded_face": "Ceded Face",
    "ceded_nar_peak": "Peak Ceded NAR",
    "pv_premium": "PV Premium",
}


def _render_concentration_tables_for_basis(
    result_dict: dict[str, object],  # type: ignore[type-arg]
    basis: str,
) -> None:
    """Render the cedant / product / treaty concentration tables for one weight basis.

    ADR-069 surfaces a three-basis nested view at
    ``result_dict["concentration_by_basis"][basis][dimension][label]``.
    For legacy result JSON files written before ADR-069 the nested key is
    absent; the ``ceded_face`` basis falls back to the flat
    ``concentration`` / ``hhi`` keys so ``polaris portfolio report`` still
    renders pre-ADR-069 JSON correctly. Any non-face basis on a legacy file
    emits a one-line warning and skips rendering for that basis.
    """
    nested = result_dict.get("concentration_by_basis")
    nested_hhi = result_dict.get("hhi_by_basis")
    if isinstance(nested, dict) and basis in nested:
        concentration = nested[basis]
        hhi = nested_hhi[basis] if isinstance(nested_hhi, dict) else {}
    elif basis == "ceded_face":
        concentration = result_dict["concentration"]
        hhi = result_dict["hhi"]
    else:
        console.print(
            f"[yellow]Warning:[/yellow] Result JSON does not include "
            f"weight basis {basis!r} (only 'ceded_face' is available on "
            "pre-ADR-069 outputs); skipping this section."
        )
        return

    basis_label = _PORTFOLIO_CONCENTRATION_BASIS_LABELS[basis]
    for dimension in ("cedant", "product", "treaty"):
        shares = concentration[dimension]  # type: ignore[index]
        if not shares:
            continue
        tbl = Table(
            title=(
                f"Concentration by {dimension.title()} — weighted by "
                f"{basis_label} (HHI = {float(hhi[dimension]):.3f})"  # type: ignore[index]
            ),
            border_style="magenta",
        )
        tbl.add_column(dimension.title(), style="bold")
        tbl.add_column(f"Share of {basis_label}", justify="right")
        for label, share in sorted(shares.items(), key=lambda kv: -float(kv[1])):
            tbl.add_row(str(label), f"{float(share):.2%}")
        console.print(tbl)


def _render_portfolio_summary(
    result_dict: dict[str, object],  # type: ignore[type-arg]
    concentration_basis: Literal["ceded_face", "ceded_nar_peak", "pv_premium", "all"] = (
        "ceded_face"
    ),
) -> None:
    """Render Rich tables for a portfolio result dict.

    Accepts either a fresh ``PortfolioResult.to_dict()`` output or a result
    JSON re-loaded from disk — both share the same shape.

    ``concentration_basis`` selects which weight basis is rendered for the
    concentration / HHI tables (ADR-069). Defaults to ``"ceded_face"`` to
    preserve the historical face-weighted view. Pass ``"all"`` to render
    all three bases stacked.
    """
    n_deals = int(result_dict["n_deals"])  # type: ignore[arg-type]
    total_pv = float(result_dict["total_pv_profits"])  # type: ignore[arg-type]
    total_irr = result_dict.get("total_irr")
    total_face = float(result_dict["total_face_amount"])  # type: ignore[arg-type]
    total_ceded_face = float(result_dict["total_ceded_face"])  # type: ignore[arg-type]
    peak_nar = float(result_dict["peak_ceded_nar"])  # type: ignore[arg-type]

    overview = Table(title="Portfolio Overview", border_style="cyan")
    overview.add_column("Metric", style="bold")
    overview.add_column("Value", justify="right")
    overview.add_row("Deals", str(n_deals))
    overview.add_row("Hurdle Rate", f"{float(result_dict['hurdle_rate']):.2%}")  # type: ignore[arg-type]
    grid_origin = result_dict.get("grid_origin")
    if grid_origin is not None:
        overview.add_row("Grid Origin", str(grid_origin))
    overview.add_row("Total PV Profits", f"${total_pv:,.0f}")
    overview.add_row(
        "Total IRR",
        f"{float(total_irr):.2%}" if isinstance(total_irr, (int, float)) else "N/A",
    )
    overview.add_row("Total Face", f"${total_face:,.0f}")
    overview.add_row("Total Ceded Face", f"${total_ceded_face:,.0f}")
    overview.add_row("Peak Ceded NAR", f"${peak_nar:,.0f}")
    console.print(overview)

    # Per-deal breakdown
    deals = Table(title="Per-Deal Breakdown", border_style="green")
    deals.add_column("Deal ID", style="bold")
    deals.add_column("Cedant")
    deals.add_column("Product")
    deals.add_column("Treaty")
    deals.add_column("Policies", justify="right")
    deals.add_column("Face", justify="right")
    deals.add_column("Ceded Face", justify="right")
    deals.add_column("PV Profits", justify="right")
    deals.add_column("IRR", justify="right")
    deals.add_column("Offset (mo)", justify="right")
    for deal in result_dict["deals"]:  # type: ignore[union-attr]
        pt = deal["profit_test"]
        irr_str = f"{float(pt['irr']):.2%}" if pt.get("irr") is not None else "N/A"
        deals.add_row(
            str(deal["deal_id"]),
            str(deal["cedant"]),
            str(deal["product_type"]),
            str(deal["treaty_type"]),
            f"{int(deal['n_policies']):,}",
            f"${float(deal['face_amount']):,.0f}",
            f"${float(deal['ceded_face']):,.0f}",
            f"${float(pt['pv_profits']):,.0f}",
            irr_str,
            str(int(deal.get("grid_offset", 0))),
        )
    console.print(deals)

    bases_to_render: tuple[str, ...] = (
        _PORTFOLIO_CONCENTRATION_BASES if concentration_basis == "all" else (concentration_basis,)
    )
    for basis in bases_to_render:
        _render_concentration_tables_for_basis(result_dict, basis)


@portfolio_app.command("run")
def portfolio_run_cmd(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Portfolio config file (YAML or JSON)."),
    ],
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to write the portfolio result as JSON. Default: stdout JSON.",
        ),
    ] = None,
    hurdle_rate: Annotated[
        float | None,
        typer.Option(
            "--hurdle-rate",
            "-r",
            help=(
                "Override the portfolio-level hurdle rate from the config. "
                "Applied uniformly to every deal and to the aggregate profit test."
            ),
        ),
    ] = None,
    align: Annotated[
        str,
        typer.Option(
            "--align",
            help=(
                "Time-alignment mode (ADR-061). 'strict' (default) sums cash flows "
                "by month index and requires every deal to share a valuation date. "
                "'calendar' places each deal on a common monthly grid keyed off the "
                "earliest valuation date so deals with different inception dates "
                "aggregate correctly; total_pv_profits then reports the portfolio "
                "NPV as of the common origin."
            ),
        ),
    ] = "strict",
    concentration_basis: Annotated[
        Literal["ceded_face", "ceded_nar_peak", "pv_premium", "all"],
        typer.Option(
            "--concentration-basis",
            help=(
                "Weight basis for the rendered concentration / HHI tables (ADR-069). "
                "'ceded_face' (default) — share of total ceded face. "
                "'ceded_nar_peak' — share weighted by each deal's peak ceded NAR, "
                "the production view for YRT-heavy books. "
                "'pv_premium' — share weighted by ceded PV-premium revenue. "
                "'all' — render all three bases stacked. The JSON output always "
                "carries all three under 'concentration_by_basis'; this flag "
                "only controls the rendered Rich tables."
            ),
        ),
    ] = "ceded_face",
) -> None:
    """
    [bold]Run a multi-deal portfolio and aggregate reinsurer-level metrics.[/bold]

    Loads a YAML or JSON portfolio config (a list of deals, each with its own
    mortality / lapse / deal config plus inline policies or an inforce CSV
    reference), projects every deal, applies its proportional treaty (YRT /
    Coinsurance / Modco), and aggregates the reinsurer-side cash flows into
    total PV profits, total IRR, and concentration metrics by cedant,
    product type, and treaty type.
    """
    _header()

    if align not in ("strict", "calendar"):
        console.print(f"[red]Error:[/red] --align must be 'strict' or 'calendar'; got {align!r}.")
        raise typer.Exit(code=1)

    portfolio, configured_hurdle = _build_portfolio_from_config(config_path)
    effective_hurdle = hurdle_rate if hurdle_rate is not None else configured_hurdle

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Running portfolio ({portfolio.n_deals} deals)...", total=None)
        try:
            result = portfolio.run(effective_hurdle, align=align)
        except PolarisValidationError as exc:
            console.print(f"[red]Error running portfolio:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    result_dict = result.to_dict()
    _render_portfolio_summary(result_dict, concentration_basis=concentration_basis)

    _write_output(result_dict, output_path, default_name="portfolio.json")


_STANDARD_SCENARIO_KEYWORD = "standard"


def _resolve_scenarios_argument(scenarios_arg: str | None) -> "list[ScenarioAdjustment]":
    """Resolve the ``--scenarios`` CLI argument to a list of ``ScenarioAdjustment``.

    Accepts either ``"standard"`` / ``None`` (the default deal-committee six-
    scenario set from :meth:`ScenarioRunner.standard_stress_scenarios`) or a
    comma-separated list of names drawn from that set (e.g. ``"BASE,MORT_110"``).
    The returned list preserves the order the caller supplied so downstream
    consumers can index scenarios positionally.

    Raises :class:`typer.Exit` with a Rich error message when the argument is
    empty, contains duplicates, or references an unknown scenario name.
    """
    from polaris_re.analytics.scenario import ScenarioRunner

    standard = ScenarioRunner.standard_stress_scenarios()
    if scenarios_arg is None or scenarios_arg == _STANDARD_SCENARIO_KEYWORD:
        return list(standard)

    raw = scenarios_arg.strip()
    if not raw:
        console.print(
            "[red]Error:[/red] --scenarios value is empty. Pass 'standard' for the "
            "default six-scenario set, or a comma-separated list of names "
            "(e.g. 'BASE,MORT_110')."
        )
        raise typer.Exit(code=1)

    names = [tok.strip() for tok in raw.split(",") if tok.strip()]
    if not names:
        console.print(
            "[red]Error:[/red] --scenarios value parsed to an empty list. "
            "Pass 'standard' or a comma-separated list of scenario names."
        )
        raise typer.Exit(code=1)

    if len(names) != len(set(names)):
        counts: dict[str, int] = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
        duplicates = sorted(n for n, c in counts.items() if c > 1)
        console.print(
            f"[red]Error:[/red] duplicate scenario names in --scenarios: {duplicates}. "
            "Each scenario should appear at most once."
        )
        raise typer.Exit(code=1)

    by_name = {sc.name: sc for sc in standard}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        valid = ", ".join(sc.name for sc in standard)
        console.print(
            f"[red]Error:[/red] unknown scenario name(s): {unknown}. Valid names: {valid}."
        )
        raise typer.Exit(code=1)

    return [by_name[n] for n in names]


def _render_portfolio_scenarios_summary(
    result_dict: dict[str, object],
) -> None:
    """Render a Rich table summarising the per-scenario aggregate result.

    Consumes the flat ``PortfolioScenarioResult.to_dict()`` shape — a
    ``{"scenarios": [{"name", "result"}, ...]}`` mapping where each ``result``
    is itself a ``PortfolioResult.to_dict()`` output.
    """
    scenarios = result_dict.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return

    table = Table(title="Portfolio Scenario Analysis", border_style="cyan")
    table.add_column("Scenario", style="bold")
    table.add_column("Total PV Profits", justify="right")
    table.add_column("Total IRR", justify="right")
    table.add_column("Total Face", justify="right")
    table.add_column("Peak Ceded NAR", justify="right")

    for entry in scenarios:
        name = str(entry["name"])  # type: ignore[index]
        res = entry["result"]  # type: ignore[index]
        pv = float(res["total_pv_profits"])  # type: ignore[arg-type, index]
        irr = res.get("total_irr")  # type: ignore[union-attr]
        face = float(res["total_face_amount"])  # type: ignore[arg-type, index]
        nar = float(res["peak_ceded_nar"])  # type: ignore[arg-type, index]
        irr_str = f"{float(irr):.2%}" if isinstance(irr, (int, float)) else "N/A"
        table.add_row(
            name,
            f"${pv:,.0f}",
            irr_str,
            f"${face:,.0f}",
            f"${nar:,.0f}",
        )
    console.print(table)


@portfolio_app.command("scenarios")
def portfolio_scenarios_cmd(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Portfolio config file (YAML or JSON)."),
    ],
    scenarios_arg: Annotated[
        str | None,
        typer.Option(
            "--scenarios",
            "-s",
            help=(
                "Scenario set to run. 'standard' (default) is the deal-committee "
                "six-scenario stress set (BASE, MORT_110, MORT_90, LAPSE_80, "
                "LAPSE_120, MORT_110_LAPSE_80). Pass a comma-separated list "
                "(e.g. 'BASE,MORT_110') to filter to a named subset; "
                "names must come from the standard set."
            ),
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=("Path to write the PortfolioScenarioResult JSON. Default: stdout JSON."),
        ),
    ] = None,
    hurdle_rate: Annotated[
        float | None,
        typer.Option(
            "--hurdle-rate",
            "-r",
            help=(
                "Override the portfolio-level hurdle rate from the config. "
                "Applied uniformly to every scenario's aggregate profit test."
            ),
        ),
    ] = None,
    align: Annotated[
        str,
        typer.Option(
            "--align",
            help=(
                "Time-alignment mode (ADR-061). 'strict' (default) requires every "
                "deal to share a valuation date. 'calendar' places each deal on a "
                "common monthly grid keyed off the earliest valuation date. The "
                "mode is forwarded unchanged to every scenario's aggregate run."
            ),
        ),
    ] = "strict",
) -> None:
    """
    [bold]Run a multi-deal portfolio under a stress-scenario set (ADR-064).[/bold]

    Wires :meth:`polaris_re.analytics.portfolio.Portfolio.run_scenarios`
    through to the CLI. Each scenario applies its multiplicative mortality
    and lapse stresses uniformly to every deal in the book (the "correlated"
    reinsurer-conservative view from ADR-064) and the full per-scenario
    aggregate result is returned in a flat
    ``{"scenarios": [{"name", "result"}, ...]}`` JSON shape — the same
    ``PortfolioResult.to_dict()`` payload ``polaris portfolio run`` writes,
    nested under each scenario's name.
    """
    _header()

    if align not in ("strict", "calendar"):
        console.print(f"[red]Error:[/red] --align must be 'strict' or 'calendar'; got {align!r}.")
        raise typer.Exit(code=1)

    scenarios = _resolve_scenarios_argument(scenarios_arg)

    portfolio, configured_hurdle = _build_portfolio_from_config(config_path)
    effective_hurdle = hurdle_rate if hurdle_rate is not None else configured_hurdle

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(
            f"Running {len(scenarios)} scenario(s) on portfolio ({portfolio.n_deals} deals)...",
            total=None,
        )
        try:
            result = portfolio.run_scenarios(  # type: ignore[attr-defined]
                effective_hurdle,
                scenarios=scenarios,
                align=align,
            )
        except PolarisValidationError as exc:
            console.print(f"[red]Error running portfolio scenarios:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    result_dict = result.to_dict()
    _render_portfolio_scenarios_summary(result_dict)

    _write_output(result_dict, output_path, default_name="portfolio_scenarios.json")


@portfolio_app.command("report")
def portfolio_report_cmd(
    result_path: Annotated[
        Path,
        typer.Option(
            "--result",
            "-r",
            help="Path to a portfolio result JSON file written by 'polaris portfolio run'.",
        ),
    ],
    concentration_basis: Annotated[
        Literal["ceded_face", "ceded_nar_peak", "pv_premium", "all"],
        typer.Option(
            "--concentration-basis",
            help=(
                "Weight basis for the rendered concentration / HHI tables "
                "(ADR-069). 'ceded_face' (default), 'ceded_nar_peak', "
                "'pv_premium', or 'all'. Pre-ADR-069 result JSON only carries "
                "the face-weighted view; non-face bases warn and skip when "
                "the input is a legacy file."
            ),
        ),
    ] = "ceded_face",
) -> None:
    """
    [bold]Re-render a portfolio result JSON without re-running the projection.[/bold]

    Reads a result JSON produced by ``polaris portfolio run --output`` and
    prints the per-deal breakdown plus the cedant / product / treaty
    concentration tables.
    """
    _header()
    if not result_path.exists():
        console.print(f"[red]Error:[/red] Result file not found: {result_path}")
        raise typer.Exit(code=1)
    try:
        result_dict = json.loads(result_path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error parsing result JSON:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if not isinstance(result_dict, dict) or "deals" not in result_dict:
        console.print(
            "[red]Error:[/red] Result file does not look like a portfolio result "
            "(missing 'deals' key)."
        )
        raise typer.Exit(code=1)
    _render_portfolio_summary(result_dict, concentration_basis=concentration_basis)


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
