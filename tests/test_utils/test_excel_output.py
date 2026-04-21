"""
Tests for the deal-pricing Excel export (ADR-045).

The rate-schedule Excel writer is covered separately under
``tests/test_analytics/test_rate_schedule.py``. This module tests the
committee-packet deal-pricing workbook produced by
``write_deal_pricing_excel``.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from openpyxl import load_workbook

from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.utils.excel_output import (
    AssumptionsMetaExport,
    DealMetaExport,
    DealPricingExport,
    ScenarioMetric,
    write_deal_pricing_excel,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


PROJECTION_YEARS: int = 20
PROJECTION_MONTHS: int = PROJECTION_YEARS * 12


def _make_cashflows(basis: str = "NET") -> CashFlowResult:
    """Build a deterministic CashFlowResult with 240 months of cash flows."""
    t = PROJECTION_MONTHS
    # Monthly arrays — small numbers that aggregate to easy-to-check annual sums.
    premiums = np.full(t, 1_000.0, dtype=np.float64)  # $12,000 / yr
    claims = np.full(t, 200.0, dtype=np.float64)  # $2,400 / yr
    surrenders = np.zeros(t, dtype=np.float64)
    expenses = np.full(t, 50.0, dtype=np.float64)  # $600 / yr
    reserve_balance = np.linspace(0.0, 10_000.0, t, dtype=np.float64)
    reserve_increase = np.diff(reserve_balance, prepend=0.0)
    ncf = premiums - claims - surrenders - expenses - reserve_increase

    return CashFlowResult(
        run_id="test-run",
        valuation_date=date(2026, 1, 1),
        basis=basis,  # type: ignore[arg-type]
        assumption_set_version="test-v1",
        product_type="TERM",
        projection_months=t,
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=surrenders,
        expenses=expenses,
        reserve_balance=reserve_balance,
        reserve_increase=reserve_increase,
        net_cash_flow=ncf,
    )


def _make_profit_result(
    *,
    irr: float | None = 0.125,
    profit_margin: float | None = 0.08,
    breakeven_year: int | None = 5,
) -> ProfitTestResult:
    profit_by_year = np.linspace(-1000.0, 5000.0, PROJECTION_YEARS, dtype=np.float64)
    return ProfitTestResult(
        hurdle_rate=0.10,
        pv_profits=25_000.0,
        pv_premiums=250_000.0,
        profit_margin=profit_margin,
        irr=irr,
        breakeven_year=breakeven_year,
        total_undiscounted_profit=float(profit_by_year.sum()),
        profit_by_year=profit_by_year,
    )


def _make_deal_meta() -> DealMetaExport:
    return DealMetaExport(
        product_type="TERM",
        n_policies=500,
        face_amount=50_000_000.0,
        treaty_type="YRT",
        cession_pct=0.90,
        hurdle_rate=0.10,
        discount_rate=0.06,
        projection_years=PROJECTION_YEARS,
        valuation_date=date(2026, 1, 1),
    )


def _make_assumptions_meta() -> AssumptionsMetaExport:
    return AssumptionsMetaExport(
        mortality_source="SOA_VBT_2015",
        mortality_multiplier=1.0,
        lapse_description="Select-ultimate: yr1=10%, yr2=8%, ultimate=3%",
        assumption_set_version="test-v1",
    )


@pytest.fixture
def minimal_export() -> DealPricingExport:
    """Mandatory fields only — cedant + net cash flows, no reinsurer, no scenarios."""
    return DealPricingExport(
        deal_meta=_make_deal_meta(),
        assumptions_meta=_make_assumptions_meta(),
        cedant_result=_make_profit_result(),
        reinsurer_result=None,
        net_cashflows=_make_cashflows("NET"),
    )


@pytest.fixture
def full_export() -> DealPricingExport:
    """Full export: cedant + reinsurer + scenarios."""
    return DealPricingExport(
        deal_meta=_make_deal_meta(),
        assumptions_meta=_make_assumptions_meta(),
        cedant_result=_make_profit_result(irr=0.125, profit_margin=0.08, breakeven_year=5),
        reinsurer_result=_make_profit_result(irr=0.095, profit_margin=0.04, breakeven_year=7),
        net_cashflows=_make_cashflows("NET"),
        scenario_results=[
            ScenarioMetric(name="Base", pv_profits=25_000.0, irr=0.125, profit_margin=0.08),
            ScenarioMetric(
                name="Mortality +25%", pv_profits=-12_000.0, irr=0.045, profit_margin=-0.04
            ),
            ScenarioMetric(name="Lapse +50%", pv_profits=18_000.0, irr=0.108, profit_margin=0.06),
        ],
    )


# ---------------------------------------------------------------------------
# File creation & structure
# ---------------------------------------------------------------------------


class TestDealPricingExcelStructure:
    def test_file_created_and_nonempty(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_expected_sheets_minimal(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        wb = load_workbook(out)
        # Sensitivity omitted when scenario_results is None.
        assert wb.sheetnames == ["Summary", "Cash Flows", "Assumptions"]

    def test_expected_sheets_full(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        wb = load_workbook(out)
        assert wb.sheetnames == ["Summary", "Cash Flows", "Assumptions", "Sensitivity"]

    def test_workbook_roundtrips(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        """Written workbook can be re-opened with openpyxl without errors."""
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        wb = load_workbook(out)
        assert wb["Summary"].max_row >= 2
        assert wb["Cash Flows"].max_row >= PROJECTION_YEARS + 1  # header + rows


# ---------------------------------------------------------------------------
# Summary sheet
# ---------------------------------------------------------------------------


def _find_row_with_label(ws, label: str) -> int:
    """Return the 1-indexed row containing the given label in column A (None if not found)."""
    for row_idx in range(1, ws.max_row + 1):
        cell = ws.cell(row=row_idx, column=1).value
        if cell == label:
            return row_idx
    raise AssertionError(f"Label {label!r} not found in column A of sheet {ws.title!r}")


class TestSummarySheet:
    def test_cedant_irr_matches(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "IRR")
        # Expect the cedant IRR to live in column B (first metric column).
        cedant_irr_cell = ws.cell(row=row, column=2).value
        assert cedant_irr_cell == pytest.approx(full_export.cedant_result.irr)

    def test_cedant_pv_profits_matches(
        self, full_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "PV Profits")
        pv_cell = ws.cell(row=row, column=2).value
        assert pv_cell == pytest.approx(full_export.cedant_result.pv_profits)

    def test_reinsurer_column_present_when_given(
        self, full_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "IRR")
        reinsurer_cell = ws.cell(row=row, column=3).value
        assert reinsurer_cell == pytest.approx(full_export.reinsurer_result.irr)  # type: ignore[union-attr]

    def test_reinsurer_column_absent_when_none(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Summary"]
        # Row 1 is the header; column B is cedant; column C must not be a reinsurer header.
        header_c = ws.cell(row=1, column=3).value
        assert header_c is None or "Reinsurer" not in str(header_c)

    def test_irr_none_renders_as_na(self, tmp_path: Path) -> None:
        """IRR suppressed by the guardrail (None) must render as 'N/A'."""
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_profit_result(irr=None),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "IRR")
        cell = ws.cell(row=row, column=2).value
        assert cell == "N/A"

    def test_profit_margin_none_renders_as_na(self, tmp_path: Path) -> None:
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_profit_result(profit_margin=None),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "Profit Margin")
        cell = ws.cell(row=row, column=2).value
        assert cell == "N/A"


# ---------------------------------------------------------------------------
# Cash Flows sheet
# ---------------------------------------------------------------------------


class TestCashFlowsSheet:
    def test_row_count_equals_projection_years(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Cash Flows"]
        # One header row + projection_years data rows.
        assert ws.max_row == PROJECTION_YEARS + 1

    def test_annual_premium_sum_matches_monthly(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        """Year-1 premium cell = sum of first 12 monthly premiums."""
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Cash Flows"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        prem_col = headers.index("Gross Premiums") + 1
        year1_prem = ws.cell(row=2, column=prem_col).value
        expected = float(minimal_export.net_cashflows.gross_premiums[:12].sum())
        assert year1_prem == pytest.approx(expected)

    def test_all_expected_columns_present(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Cash Flows"]
        headers = {ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)}
        required = {
            "Year",
            "Gross Premiums",
            "Death Claims",
            "Lapse Surrenders",
            "Expenses",
            "Reserve Increase",
            "Net Cash Flow",
        }
        assert required.issubset(headers)

    def test_net_cash_flow_total_matches_profit_sum(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        """Sum of the annual Net Cash Flow column equals sum of monthly NCF."""
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Cash Flows"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        ncf_col = headers.index("Net Cash Flow") + 1
        total = sum(
            ws.cell(row=r, column=ncf_col).value
            for r in range(2, ws.max_row + 1)
            if ws.cell(row=r, column=ncf_col).value is not None
        )
        expected = float(minimal_export.net_cashflows.net_cash_flow.sum())
        assert total == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# Assumptions sheet
# ---------------------------------------------------------------------------


class TestAssumptionsSheet:
    def test_contains_mortality_source(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Assumptions"]
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "Mortality Source" in labels

    def test_contains_treaty_and_cession(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Assumptions"]
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "Treaty Type" in labels
        assert "Cession Percent" in labels

    def test_hurdle_rate_value(self, minimal_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Assumptions"]
        row = _find_row_with_label(ws, "Hurdle Rate")
        assert ws.cell(row=row, column=2).value == pytest.approx(
            minimal_export.deal_meta.hurdle_rate
        )


# ---------------------------------------------------------------------------
# Sensitivity sheet
# ---------------------------------------------------------------------------


class TestSensitivitySheet:
    def test_row_per_scenario(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Sensitivity"]
        assert full_export.scenario_results is not None
        # header + one row per scenario
        assert ws.max_row == len(full_export.scenario_results) + 1

    def test_scenario_names_preserved(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Sensitivity"]
        names_in_sheet = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
        assert full_export.scenario_results is not None
        assert names_in_sheet == [s.name for s in full_export.scenario_results]

    def test_scenario_pv_matches(self, full_export: DealPricingExport, tmp_path: Path) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(full_export, out)
        ws = load_workbook(out)["Sensitivity"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        pv_col = headers.index("PV Profits") + 1
        assert full_export.scenario_results is not None
        for i, scenario in enumerate(full_export.scenario_results):
            pv_cell = ws.cell(row=i + 2, column=pv_col).value
            assert pv_cell == pytest.approx(scenario.pv_profits)
