"""
Smoke test: load the dummy test inforce CSV and exercise the end-to-end
pipeline that the Streamlit upload path uses.

Validates:
    1. InforceBlock.from_csv() parses data/inputs/test_inforce.csv
    2. Vectorized attribute access (face_amount_vec, attained_age_vec, ...)
    3. NetPremiumCalculator re-prices the policies and ties back to the
       annual_premium stored in the CSV (which was calibrated to VBT 2015 NS)
    4. WholeLife projection engine runs to completion and produces non-empty
       gross cash flows

This is the script you run to answer "does the CSV actually work with the
code I just shipped" without standing up the Streamlit dashboard.

Usage:
    uv run python scripts/smoke_test_inforce.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from polaris_re.analytics.pricing import NetPremiumCalculator
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.whole_life import WholeLife

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "inputs" / "test_inforce.csv"
MORTALITY_DIR = REPO_ROOT / "data" / "mortality_tables"

console = Console()


def step(title: str) -> None:
    console.print(Panel(title, border_style="cyan"))


def main() -> int:
    console.print(f"[dim]Repo root:[/dim] {REPO_ROOT}")
    console.print(f"[dim]Inforce CSV:[/dim] {CSV_PATH}\n")

    # ------------------------------------------------------------------
    # 1. Load the CSV via the same entry point the Streamlit app uses
    # ------------------------------------------------------------------
    step("1. InforceBlock.from_csv")
    block = InforceBlock.from_csv(CSV_PATH, block_id="smoke-test")
    console.print(f"  n_policies          = {block.n_policies}")
    console.print(f"  product_types       = {block.product_types}")
    console.print(f"  total_face_amount   = ${block.total_face_amount():,.0f}")
    console.print(f"  total_annual_prem   = ${block.total_annual_premium():,.0f}")
    console.print(f"  attained_age_vec    = {block.attained_age_vec.tolist()}")
    console.print(f"  duration_inforce_vec= {block.duration_inforce_vec.tolist()} (months)")
    console.print(f"  is_male_vec         = {block.is_male_vec.tolist()}")
    console.print(f"  is_smoker_vec       = {block.is_smoker_vec.tolist()}")
    console.print(f"  cession_pct_vec     = {block.cession_pct_vec.tolist()}\n")

    # ------------------------------------------------------------------
    # 2. Re-price via NetPremiumCalculator and tie back to the CSV
    # ------------------------------------------------------------------
    step("2. NetPremiumCalculator re-price (SOA VBT 2015 NS, i=4%, loading=25%)")
    mortality = MortalityTable.load(MortalityTableSource.SOA_VBT_2015, data_dir=MORTALITY_DIR)
    calc = NetPremiumCalculator(
        mortality=mortality,
        discount_rate=0.04,
        expense_loading=0.25,
        basis_age="issue",
    )
    results = calc.price_block(block)

    tbl = Table(title="Calibration check", border_style="green")
    tbl.add_column("policy_id")
    tbl.add_column("CSV premium", justify="right")
    tbl.add_column("Recomputed gross", justify="right")
    tbl.add_column("Δ", justify="right")
    tbl.add_column("rate/$1k", justify="right")

    ok = True
    for policy, res in zip(block.policies, results, strict=True):
        csv_prem = policy.annual_premium
        recomputed = res.gross_annual_premium
        delta = recomputed - csv_prem
        # CSV is stored to the cent; tolerate only float-rounding drift.
        if abs(delta) > 0.01:
            ok = False
        tbl.add_row(
            policy.policy_id,
            f"${csv_prem:,.2f}",
            f"${recomputed:,.2f}",
            f"${delta:+,.2f}",
            f"{res.net_rate_per_1000:.3f}",
        )
    console.print(tbl)
    if ok:
        console.print("[green]✓ CSV premiums tie to NetPremiumCalculator output[/green]\n")
    else:
        console.print(
            "[red]✗ CSV premiums differ from recomputed by more than 1c. "
            "Regenerate the CSV from NetPremiumCalculator.[/red]\n"
        )
        return 1

    # ------------------------------------------------------------------
    # 3. Run the WholeLife projection engine end-to-end
    # ------------------------------------------------------------------
    step("3. WholeLife projection")
    # Lapse: simple select-and-ultimate structure
    lapse = LapseAssumption.from_duration_table(
        {1: 0.06, 2: 0.05, 3: 0.04, 4: 0.03, 5: 0.03, "ultimate": 0.02}
    )
    assumptions = AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version="smoke-test-v1",
        effective_date=date(2026, 4, 6),
    )
    config = ProjectionConfig(
        valuation_date=date(2026, 4, 6),
        projection_horizon_years=30,
        discount_rate=0.04,
        acquisition_cost_per_policy=500.0,
        maintenance_cost_per_policy_per_year=75.0,
    )
    engine = WholeLife(inforce=block, assumptions=assumptions, config=config)
    gross = engine.project()

    console.print(f"  basis               = {gross.basis}")
    console.print(f"  projection_months   = {gross.projection_months}")
    console.print(f"  gross_premiums sum  = ${float(gross.gross_premiums.sum()):,.0f}")
    console.print(f"  death_claims sum    = ${float(gross.death_claims.sum()):,.0f}")
    console.print(f"  lapse_surrenders    = ${float(gross.lapse_surrenders.sum()):,.0f}")
    console.print(f"  expenses sum        = ${float(gross.expenses.sum()):,.0f}")
    console.print(f"  reserve_balance[0]  = ${float(gross.reserve_balance[0]):,.0f}")
    console.print(f"  reserve_balance[-1] = ${float(gross.reserve_balance[-1]):,.0f}")

    if gross.gross_premiums.sum() <= 0:
        console.print("[red]✗ zero gross premiums — projection failed silently[/red]")
        return 1

    console.print("\n[green bold]✓ Smoke test complete[/green bold]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
