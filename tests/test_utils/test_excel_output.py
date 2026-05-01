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

from polaris_re.analytics.profit_test import ProfitResultWithCapital, ProfitTestResult
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.utils.excel_output import (
    AssumptionsMetaExport,
    DealMetaExport,
    DealPricingExport,
    ScenarioMetric,
    write_deal_pricing_excel,
    write_yrt_rate_table_excel,
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


# ---------------------------------------------------------------------------
# LICAT capital block on the Summary sheet (ADR-049)
# ---------------------------------------------------------------------------


def _make_capital_result(
    *,
    pv_capital: float = 100_000.0,
    pv_capital_strain: float = 25_000.0,
    return_on_capital: float | None = 0.18,
    capital_adjusted_irr: float | None = 0.115,
    peak_capital: float = 150_000.0,
) -> ProfitResultWithCapital:
    profit_by_year = np.linspace(-1000.0, 5000.0, PROJECTION_YEARS, dtype=np.float64)
    return ProfitResultWithCapital(
        hurdle_rate=0.10,
        pv_profits=25_000.0,
        pv_premiums=250_000.0,
        profit_margin=0.10,
        irr=0.125,
        breakeven_year=5,
        total_undiscounted_profit=float(profit_by_year.sum()),
        profit_by_year=profit_by_year,
        initial_capital=80_000.0,
        peak_capital=peak_capital,
        pv_capital=pv_capital,
        pv_capital_strain=pv_capital_strain,
        return_on_capital=return_on_capital,
        capital_adjusted_irr=capital_adjusted_irr,
        capital_by_period=np.linspace(80_000.0, peak_capital, PROJECTION_MONTHS, dtype=np.float64),
    )


@pytest.fixture
def capital_export() -> DealPricingExport:
    """Export with a ProfitResultWithCapital cedant + reinsurer."""
    return DealPricingExport(
        deal_meta=_make_deal_meta(),
        assumptions_meta=_make_assumptions_meta(),
        cedant_result=_make_capital_result(),
        reinsurer_result=_make_capital_result(
            pv_capital=60_000.0,
            return_on_capital=0.22,
            capital_adjusted_irr=0.142,
            peak_capital=90_000.0,
        ),
        net_cashflows=_make_cashflows("NET"),
    )


class TestSummarySheetCapitalBlock:
    """ADR-049: capital rows are appended only when results carry capital."""

    def test_capital_rows_absent_when_off(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        ws = load_workbook(out)["Summary"]
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "Return on Capital" not in labels
        assert "Peak Capital" not in labels
        assert "PV Capital (stock)" not in labels
        assert "PV Capital Strain" not in labels
        assert "Capital-Adjusted IRR" not in labels

    def test_capital_rows_present_when_capital_result(
        self, capital_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(capital_export, out)
        ws = load_workbook(out)["Summary"]
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        for required in (
            "Peak Capital",
            "PV Capital (stock)",
            "PV Capital Strain",
            "Return on Capital",
            "Capital-Adjusted IRR",
        ):
            assert required in labels, f"missing {required!r} on Summary sheet"

    def test_cedant_return_on_capital_value_matches(
        self, capital_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(capital_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "Return on Capital")
        cell = ws.cell(row=row, column=2).value
        assert cell == pytest.approx(0.18)

    def test_reinsurer_pv_capital_value_matches(
        self, capital_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(capital_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "PV Capital (stock)")
        cedant_cell = ws.cell(row=row, column=2).value
        reinsurer_cell = ws.cell(row=row, column=3).value
        assert cedant_cell == pytest.approx(100_000.0)
        assert reinsurer_cell == pytest.approx(60_000.0)

    def test_advisory_strain_metric_present(
        self, capital_export: DealPricingExport, tmp_path: Path
    ) -> None:
        """PR-#34 reviewer requirement: surface PV Capital Strain on Excel."""
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(capital_export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "PV Capital Strain")
        cedant_cell = ws.cell(row=row, column=2).value
        assert cedant_cell == pytest.approx(25_000.0)

    def test_return_on_capital_none_renders_as_na(self, tmp_path: Path) -> None:
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_capital_result(return_on_capital=None),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "Return on Capital")
        assert ws.cell(row=row, column=2).value == "N/A"

    def test_reinsurer_capital_na_when_only_cedant_has_capital(self, tmp_path: Path) -> None:
        """Mixed run: cedant has capital, reinsurer is plain — reinsurer cells = N/A."""
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_capital_result(),
            reinsurer_result=_make_profit_result(),  # plain ProfitTestResult
            net_cashflows=_make_cashflows("NET"),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["Summary"]
        row = _find_row_with_label(ws, "Return on Capital")
        assert ws.cell(row=row, column=3).value == "N/A"


# ---------------------------------------------------------------------------
# YRT Rate Table sheet (ADR-052)
# ---------------------------------------------------------------------------


def _make_yrt_rate_table():  # type: ignore[no-untyped-def]
    """Build a small synthetic ``YRTRateTable`` for sheet-rendering tests."""
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

    rates_male_ns = np.array(
        [
            [0.50, 0.55, 0.60, 1.00],
            [0.55, 0.60, 0.65, 1.10],
            [0.60, 0.65, 0.70, 1.20],
        ],
        dtype=np.float64,
    )
    rates_male_smoker = rates_male_ns * 1.6
    arr_ns = YRTRateTableArray(rates=rates_male_ns, min_age=30, max_age=32, select_period=3)
    arr_smoker = YRTRateTableArray(rates=rates_male_smoker, min_age=30, max_age=32, select_period=3)
    return YRTRateTable.from_arrays(
        table_name="synthetic-test",
        arrays={
            (Sex.MALE, SmokerStatus.NON_SMOKER): arr_ns,
            (Sex.MALE, SmokerStatus.SMOKER): arr_smoker,
        },
    )


class TestYRTRateTableSheet:
    """`write_deal_pricing_excel` adds a ``YRT Rate Table`` sheet when set."""

    def test_omitted_when_yrt_rate_table_is_none(
        self, minimal_export: DealPricingExport, tmp_path: Path
    ) -> None:
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(minimal_export, out)
        wb = load_workbook(out)
        assert "YRT Rate Table" not in wb.sheetnames

    def test_added_when_yrt_rate_table_set(self, tmp_path: Path) -> None:
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_profit_result(),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
            yrt_rate_table=_make_yrt_rate_table(),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        wb = load_workbook(out)
        assert "YRT Rate Table" in wb.sheetnames

    def test_sheet_contains_table_name_and_cohorts(self, tmp_path: Path) -> None:
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_profit_result(),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
            yrt_rate_table=_make_yrt_rate_table(),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["YRT Rate Table"]
        # Title (row 1) names the table.
        assert "synthetic-test" in str(ws.cell(row=1, column=1).value)
        # Find both cohort labels in column A.
        labels = [str(ws.cell(row=r, column=1).value) for r in range(1, ws.max_row + 1)]
        assert any("M_NS" in lbl for lbl in labels)
        assert any("M_S" in lbl for lbl in labels)

    def test_sheet_renders_known_rate_value(self, tmp_path: Path) -> None:
        """Smoke check: at least one cell holds the expected rate value."""
        export = DealPricingExport(
            deal_meta=_make_deal_meta(),
            assumptions_meta=_make_assumptions_meta(),
            cedant_result=_make_profit_result(),
            reinsurer_result=None,
            net_cashflows=_make_cashflows("NET"),
            yrt_rate_table=_make_yrt_rate_table(),
        )
        out = tmp_path / "deal.xlsx"
        write_deal_pricing_excel(export, out)
        ws = load_workbook(out)["YRT Rate Table"]
        # Walk every cell — at least one should equal one of our rates.
        target = 0.50  # M_NS, age 30, dur_1
        found = False
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, (int, float)) and abs(cell.value - target) < 1e-9:
                    found = True
                    break
            if found:
                break
        assert found


# ---------------------------------------------------------------------------
# write_yrt_rate_table_excel — standalone workbook (ADR-053)
# ---------------------------------------------------------------------------


class TestWriteYrtRateTableExcel:
    """``write_yrt_rate_table_excel`` produces a standalone workbook."""

    def test_workbook_created(self, tmp_path: Path) -> None:
        """Workbook file is written and non-empty."""
        table = _make_yrt_rate_table()
        out = tmp_path / "schedule.xlsx"
        write_yrt_rate_table_excel(table, out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_has_summary_and_rate_table_sheets(self, tmp_path: Path) -> None:
        """Workbook carries both ``Summary`` and ``YRT Rate Table`` sheets."""
        table = _make_yrt_rate_table()
        out = tmp_path / "schedule.xlsx"
        write_yrt_rate_table_excel(table, out)
        wb = load_workbook(out)
        assert "Summary" in wb.sheetnames
        assert "YRT Rate Table" in wb.sheetnames

    def test_summary_carries_table_metadata(self, tmp_path: Path) -> None:
        """``Summary`` sheet shows the table name and cohort count."""
        table = _make_yrt_rate_table()
        out = tmp_path / "schedule.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["Summary"]
        cells = [str(ws.cell(row=r, column=1).value) for r in range(1, 10)]
        assert any("synthetic-test" in c for c in cells)
        # Two cohorts in the fixture.
        assert any("Cohorts: 2" in c for c in cells)
        # Total rate cells: 2 cohorts x 3 ages x 4 cols = 24.
        assert any("Total rate cells: 24" in c for c in cells)

    def test_rate_table_sheet_renders_known_value(self, tmp_path: Path) -> None:
        """At least one cell carries the expected M_NS / age 30 / dur_1 rate."""
        table = _make_yrt_rate_table()
        out = tmp_path / "schedule.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["YRT Rate Table"]
        target = 0.50  # M_NS, age 30, dur_1
        found = False
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, (int, float)) and abs(cell.value - target) < 1e-9:
                    found = True
                    break
            if found:
                break
        assert found

    def test_workbook_omits_empty_default_sheet(self, tmp_path: Path) -> None:
        """openpyxl's default ``Sheet`` is removed before adding the named sheets."""
        table = _make_yrt_rate_table()
        out = tmp_path / "schedule.xlsx"
        write_yrt_rate_table_excel(table, out)
        wb = load_workbook(out)
        assert "Sheet" not in wb.sheetnames
        # Only the two intentional sheets.
        assert set(wb.sheetnames) == {"Summary", "YRT Rate Table"}

    def test_wide_select_period_column_widths(self, tmp_path: Path) -> None:
        """`select_period >= 25` does not crash or corrupt column widths.

        Regression for PR #39 P1: ``chr(ord("B") + col_offset)`` produced
        invalid Excel column keys (`'['`, `'\\\\'`, ...) for select periods
        past 24, even though `YRTRateTable.select_period_years` allows up
        to 50. The fix uses ``openpyxl.utils.get_column_letter`` which
        wraps to two-letter columns (`AA`, `AB`, ...) past Z.
        """
        from polaris_re.core.policy import Sex, SmokerStatus
        from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

        # select_period=30 → 31 duration columns (dur_1 .. ultimate),
        # data columns B .. AF (need two-letter columns past Z).
        select_period = 30
        rates = np.full((2, select_period + 1), 0.5, dtype=np.float64)
        arr = YRTRateTableArray(rates=rates, min_age=30, max_age=31, select_period=select_period)
        table = YRTRateTable.from_arrays(
            table_name="wide-select",
            arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): arr},
        )
        out = tmp_path / "wide.xlsx"
        write_yrt_rate_table_excel(table, out)
        wb = load_workbook(out)
        ws = wb["YRT Rate Table"]
        # Column B holds dur_1; column AF (= index 32) holds the ultimate.
        # Both must have the explicit width set (14.0) by the loop.
        assert ws.column_dimensions["B"].width == 14
        assert ws.column_dimensions["AF"].width == 14
        # And no corrupt non-letter keys (e.g. '[') made it in.
        for key in ws.column_dimensions:
            assert key.isalpha(), f"corrupt column key {key!r}"


# ---------------------------------------------------------------------------
# Filled-cell disclosure (ADR-054) — visual styling + Summary count
# ---------------------------------------------------------------------------


def _make_partially_solved_table():
    """Two-row cohort table with the second row marked as filled."""
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

    rates = np.array([[1.0], [2.0]], dtype=np.float64)
    mask = np.array([[True], [False]], dtype=np.bool_)
    arr = YRTRateTableArray(
        rates=rates,
        min_age=40,
        max_age=41,
        select_period=0,
        solved_mask=mask,
    )
    return YRTRateTable.from_arrays(
        table_name="partial",
        arrays={(Sex.MALE, SmokerStatus.UNKNOWN): arr},
    )


class TestSolvedMaskDisclosureExcel:
    """ADR-054 — Excel surfaces disclose forward/back-filled cells."""

    def test_filled_cell_is_italic(self, tmp_path: Path) -> None:
        """Cells with mask False render in italic font."""
        table = _make_partially_solved_table()
        out = tmp_path / "partial.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["YRT Rate Table"]
        # Find the two data cells. Layout per ``_write_yrt_rate_table_sheet``:
        # title row 1, age-range row 2, NOTE row 3 (because mask present),
        # blank row 4, cohort label row 5, header row 6, data rows 7 & 8.
        solved_cell = ws["B7"]
        filled_cell = ws["B8"]
        assert solved_cell.value == 1.0
        assert filled_cell.value == 2.0
        assert solved_cell.font.italic is False
        assert filled_cell.font.italic is True

    def test_filled_cell_has_grey_fill(self, tmp_path: Path) -> None:
        """Cells with mask False render with a light-grey ``PatternFill``."""
        table = _make_partially_solved_table()
        out = tmp_path / "partial.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["YRT Rate Table"]
        filled_cell = ws["B8"]
        # ``EEEEEE`` (defined in `_write_yrt_rate_table_sheet`) is the disclosure colour.
        # openpyxl serialises it as ``00EEEEEE`` (alpha-prefixed), so check the suffix.
        fg = filled_cell.fill.fgColor.rgb if filled_cell.fill.fgColor is not None else ""
        assert "EEEEEE" in (fg or "").upper()

    def test_disclosure_note_row_present(self, tmp_path: Path) -> None:
        """Row 3 carries the human-readable note when any cohort has filled cells."""
        table = _make_partially_solved_table()
        out = tmp_path / "partial.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["YRT Rate Table"]
        note = str(ws.cell(row=3, column=1).value or "")
        assert "forward/back-filled" in note
        assert "ADR-054" in note

    def test_summary_carries_solved_filled_counts(self, tmp_path: Path) -> None:
        """The Summary sheet records solved- and filled-cell counts when masked."""
        table = _make_partially_solved_table()
        out = tmp_path / "partial.xlsx"
        write_yrt_rate_table_excel(table, out)
        ws = load_workbook(out)["Summary"]
        cells = [str(ws.cell(row=r, column=1).value or "") for r in range(1, 12)]
        assert any("Solved cells: 1" in c for c in cells)
        assert any("Filled cells: 1" in c for c in cells)

    def test_no_mask_renders_unchanged(self, tmp_path: Path) -> None:
        """CSV-loaded tables (mask None) keep the pre-ADR-054 layout.

        - Title at row 1
        - Age-range row at row 2
        - NO note row at row 3
        - Cohort label at row 4
        - No italic / no light-grey fill on data cells
        - Summary lacks the Solved / Filled count rows
        """
        from polaris_re.core.policy import Sex, SmokerStatus
        from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

        rates = np.array([[1.0], [2.0]], dtype=np.float64)
        arr = YRTRateTableArray(rates=rates, min_age=40, max_age=41, select_period=0)
        table = YRTRateTable.from_arrays(
            table_name="loaded",
            arrays={(Sex.MALE, SmokerStatus.UNKNOWN): arr},
        )
        out = tmp_path / "loaded.xlsx"
        write_yrt_rate_table_excel(table, out)

        wb = load_workbook(out)
        ws = wb["YRT Rate Table"]
        # Cohort label sits at the original row 4 (no NOTE row inserted).
        assert "Cohort:" in str(ws.cell(row=4, column=1).value)
        # Data rows at 6 & 7 (header at 5).
        c1 = ws["B6"]
        c2 = ws["B7"]
        assert c1.font.italic is False
        assert c2.font.italic is False
        # No grey fill applied.
        for cell in (c1, c2):
            fg = cell.fill.fgColor.rgb if cell.fill.fgColor is not None else None
            assert (fg is None) or ("EEEEEE" not in (fg or "").upper())

        ws_summary = wb["Summary"]
        cells = [str(ws_summary.cell(row=r, column=1).value or "") for r in range(1, 12)]
        # The Solved / Filled disclosure is gated on mask presence — must NOT appear.
        assert not any("Solved cells:" in c for c in cells)
        assert not any("Filled cells:" in c for c in cells)
