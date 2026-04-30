"""
Excel output formatters.

Two workbooks are produced from this module:

* ``write_rate_schedule_excel`` — YRT rate schedule, one sheet per
  sex/smoker combination, used by ``polaris rate-schedule`` (pre-existing).
* ``write_deal_pricing_excel`` — deal-pricing committee packet, covering
  Summary / Cash Flows / Assumptions / Sensitivity. See ADR-045 for the
  workbook schema and the rationale for the four fixed sheets.

The deal-pricing export takes a ``DealPricingExport`` dataclass bundling
the ``ProfitTestResult`` objects, the ``CashFlowResult`` used by the
profit test, and structured metadata (``DealMetaExport`` /
``AssumptionsMetaExport`` / ``ScenarioMetric``). This keeps the writer
signature stable while the CLI wiring (Slice 2) grows above it.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from polaris_re.analytics.profit_test import ProfitResultWithCapital, ProfitTestResult
from polaris_re.core.cashflow import CashFlowResult

if TYPE_CHECKING:
    # openpyxl ships via the `[tables]` extra; type-only imports here keep the
    # module importable without the extra installed.
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

    from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

__all__ = [
    "AssumptionsMetaExport",
    "DealMetaExport",
    "DealPricingExport",
    "ScenarioMetric",
    "write_deal_pricing_excel",
    "write_rate_schedule_excel",
    "write_yrt_rate_table_excel",
]


# ---------------------------------------------------------------------------
# Deal-pricing export DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DealMetaExport:
    """Deal-level metadata rendered on the Assumptions sheet."""

    product_type: str
    n_policies: int
    face_amount: float
    treaty_type: str | None
    cession_pct: float | None
    hurdle_rate: float
    discount_rate: float
    projection_years: int
    valuation_date: date


@dataclass(frozen=True)
class AssumptionsMetaExport:
    """Assumption-set metadata rendered on the Assumptions sheet."""

    mortality_source: str
    mortality_multiplier: float
    lapse_description: str
    assumption_set_version: str


@dataclass(frozen=True)
class ScenarioMetric:
    """One row on the Sensitivity sheet."""

    name: str
    pv_profits: float
    irr: float | None
    profit_margin: float | None


@dataclass(frozen=True)
class DealPricingExport:
    """Bundle of everything a deal-pricing workbook needs.

    ``scenario_results=None`` suppresses the Sensitivity sheet. A
    ``reinsurer_result=None`` suppresses the reinsurer column on the
    Summary sheet — both signal "ceded side does not apply to this deal".
    ``yrt_rate_table=None`` suppresses the ``YRT Rate Table`` sheet
    (only added by ADR-052 when the deal was priced with a tabular
    schedule).
    """

    deal_meta: DealMetaExport
    assumptions_meta: AssumptionsMetaExport
    cedant_result: ProfitTestResult
    reinsurer_result: ProfitTestResult | None
    net_cashflows: CashFlowResult
    gross_cashflows: CashFlowResult | None = None
    ceded_cashflows: CashFlowResult | None = None
    scenario_results: list[ScenarioMetric] | None = None
    yrt_rate_table: "YRTRateTable | None" = None


# ---------------------------------------------------------------------------
# Rate-schedule writer (unchanged)
# ---------------------------------------------------------------------------


def write_rate_schedule_excel(df: pl.DataFrame, path: Path) -> None:
    """
    Write a YRT rate schedule DataFrame to a formatted Excel workbook.

    Creates one sheet per sex/smoker combination. Each sheet has issue_age
    as rows and rate_per_1000 as the value column.

    Args:
        df:   Rate schedule DataFrame from ``YRTRateSchedule.generate()``.
              Expected columns: issue_age, sex, smoker_status, policy_term,
              rate_per_1000, irr.
        path: Output .xlsx file path.

    Raises:
        ImportError: If openpyxl is not installed.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except ImportError as exc:
        raise ImportError(
            "openpyxl required for Excel output. Install via: uv sync --extra tables"
        ) from exc

    wb = Workbook()
    # Remove default sheet
    if wb.active is not None:
        wb.remove(wb.active)

    # Group by sex + smoker_status
    groups = df.group_by(["sex", "smoker_status"]).agg(pl.all())

    for row in groups.iter_rows(named=True):
        sex = row["sex"]
        smoker = row["smoker_status"]
        sheet_name = f"{sex}_{smoker}"

        ws = wb.create_sheet(title=sheet_name)

        # Header row
        headers = ["Issue Age", "Policy Term", "Rate per $1,000", "IRR"]
        header_font = Font(bold=True)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Get the ages and rates for this group
        ages = row["issue_age"]
        terms = row["policy_term"]
        rates = row["rate_per_1000"]
        irrs = row["irr"]

        for i in range(len(ages)):
            row_idx = i + 2
            ws.cell(row=row_idx, column=1, value=ages[i])
            ws.cell(row=row_idx, column=2, value=terms[i])

            rate_cell = ws.cell(row=row_idx, column=3, value=rates[i])
            rate_cell.number_format = "0.0000"

            irr_cell = ws.cell(row=row_idx, column=4, value=irrs[i])
            irr_cell.number_format = "0.00%"

        # Auto-width columns
        for col_idx in range(1, 5):
            ws.column_dimensions[chr(64 + col_idx)].width = 16

    # Add summary sheet
    ws_summary = wb.create_sheet(title="Summary", index=0)
    ws_summary.cell(row=1, column=1, value="YRT Rate Schedule Summary").font = Font(
        bold=True, size=14
    )
    ws_summary.cell(row=3, column=1, value="Generated by Polaris RE")
    ws_summary.cell(row=4, column=1, value=f"Total rate cells: {len(df)}")

    if "policy_term" in df.columns:
        terms = df["policy_term"].unique().to_list()
        ws_summary.cell(row=5, column=1, value=f"Policy terms: {terms}")

    wb.save(path)


# ---------------------------------------------------------------------------
# Deal-pricing writer (ADR-045)
# ---------------------------------------------------------------------------


# Canonical column order for the Cash Flows sheet. Kept as a module-level
# constant so tests and docs reference the same list.
_CASH_FLOW_COLUMNS: tuple[str, ...] = (
    "Year",
    "Gross Premiums",
    "Death Claims",
    "Lapse Surrenders",
    "Expenses",
    "Reserve Increase",
    "Net Cash Flow",
)

_SUMMARY_METRICS: tuple[str, ...] = (
    "Hurdle Rate",
    "PV Profits",
    "PV Premiums",
    "Profit Margin",
    "IRR",
    "Breakeven Year",
    "Total Undiscounted Profit",
)

# LICAT-capital rows appended to the Summary sheet when at least one of
# the rendered profit-test results carries capital metrics (ADR-049).
# Order matches the CLI Rich table for readability.
_CAPITAL_METRICS: tuple[str, ...] = (
    "Peak Capital",
    "PV Capital (stock)",
    "PV Capital Strain",
    "Return on Capital",
    "Capital-Adjusted IRR",
)


def write_deal_pricing_excel(export: DealPricingExport, path: Path) -> None:
    """Write a formatted deal-pricing workbook (see ADR-045 / ADR-052).

    Sheets produced (in order):
        1. Summary        — cedant (and optional reinsurer) profit metrics.
        2. Cash Flows     — annual rollup of the NET CashFlowResult.
        3. Assumptions    — deal + assumption-set metadata.
        4. Sensitivity    — OMITTED when ``export.scenario_results`` is None.
        5. YRT Rate Table — OMITTED when ``export.yrt_rate_table`` is None;
                            otherwise one block per (sex, smoker) cohort
                            (ADR-052).

    Args:
        export: Bundle of all data required for the sheets.
        path:   Output .xlsx file path. Parent directory must exist.

    Raises:
        ImportError: If openpyxl is not installed.
    """
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ImportError(
            "openpyxl required for Excel output. Install via: uv sync --extra tables"
        ) from exc

    wb = Workbook()
    if wb.active is not None:
        wb.remove(wb.active)

    _write_summary_sheet(wb, export)
    _write_cash_flows_sheet(wb, export)
    _write_assumptions_sheet(wb, export)
    if export.scenario_results is not None:
        _write_sensitivity_sheet(wb, export.scenario_results)
    if export.yrt_rate_table is not None:
        _write_yrt_rate_table_sheet(wb, export.yrt_rate_table)

    wb.save(path)


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------


def _fmt_rate(value: float | None) -> object:
    """Return a float (for Excel % formatting) or 'N/A' when suppressed."""
    return "N/A" if value is None else float(value)


def _fmt_int(value: int | None) -> object:
    return "N/A" if value is None else int(value)


def _write_summary_sheet(wb: "Workbook", export: DealPricingExport) -> None:
    from openpyxl.styles import Alignment, Font

    ws = wb.create_sheet(title="Summary")
    header_font = Font(bold=True)
    title_font = Font(bold=True, size=14)
    centre = Alignment(horizontal="center")

    ws.cell(row=1, column=1, value="Deal Pricing Summary").font = title_font

    # Header row at row 3: Metric | Cedant | [Reinsurer]
    ws.cell(row=3, column=1, value="Metric").font = header_font
    ws.cell(row=3, column=2, value="Cedant (NET)").font = header_font
    ws.cell(row=3, column=2).alignment = centre
    if export.reinsurer_result is not None:
        ws.cell(row=3, column=3, value="Reinsurer").font = header_font
        ws.cell(row=3, column=3).alignment = centre

    for i, metric in enumerate(_SUMMARY_METRICS):
        row_idx = 4 + i
        ws.cell(row=row_idx, column=1, value=metric).font = header_font
        _write_metric_cell(ws, row_idx, 2, metric, export.cedant_result)
        if export.reinsurer_result is not None:
            _write_metric_cell(ws, row_idx, 3, metric, export.reinsurer_result)

    # Optional LICAT capital block — appended only when at least one
    # rendered result is a ProfitResultWithCapital (ADR-049). Workbooks
    # produced without --capital remain byte-identical pre-Slice-3.
    capital_present = isinstance(export.cedant_result, ProfitResultWithCapital) or (
        export.reinsurer_result is not None
        and isinstance(export.reinsurer_result, ProfitResultWithCapital)
    )
    if capital_present:
        capital_start = 4 + len(_SUMMARY_METRICS)
        for i, metric in enumerate(_CAPITAL_METRICS):
            row_idx = capital_start + i
            ws.cell(row=row_idx, column=1, value=metric).font = header_font
            _write_capital_cell(ws, row_idx, 2, metric, export.cedant_result)
            if export.reinsurer_result is not None:
                _write_capital_cell(ws, row_idx, 3, metric, export.reinsurer_result)

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 20
    if export.reinsurer_result is not None:
        ws.column_dimensions["C"].width = 20


def _write_metric_cell(
    ws: "Worksheet",
    row: int,
    col: int,
    metric: str,
    result: ProfitTestResult,
) -> None:
    """Write one Summary-sheet metric cell with appropriate number format."""
    cell = ws.cell(row=row, column=col)
    if metric == "Hurdle Rate":
        cell.value = result.hurdle_rate
        cell.number_format = "0.00%"
    elif metric == "PV Profits":
        cell.value = float(result.pv_profits)
        cell.number_format = "$#,##0"
    elif metric == "PV Premiums":
        cell.value = float(result.pv_premiums)
        cell.number_format = "$#,##0"
    elif metric == "Profit Margin":
        cell.value = _fmt_rate(result.profit_margin)
        if isinstance(cell.value, float):
            cell.number_format = "0.00%"
    elif metric == "IRR":
        cell.value = _fmt_rate(result.irr)
        if isinstance(cell.value, float):
            cell.number_format = "0.00%"
    elif metric == "Breakeven Year":
        cell.value = _fmt_int(result.breakeven_year)
    elif metric == "Total Undiscounted Profit":
        cell.value = float(result.total_undiscounted_profit)
        cell.number_format = "$#,##0"


def _write_capital_cell(
    ws: "Worksheet",
    row: int,
    col: int,
    metric: str,
    result: ProfitTestResult,
) -> None:
    """Write one Summary-sheet LICAT capital cell.

    Renders ``"N/A"`` when the result is not a
    ``ProfitResultWithCapital`` (e.g. mixed runs where one side has no
    treaty and therefore no reinsurer capital).
    """
    cell = ws.cell(row=row, column=col)
    if not isinstance(result, ProfitResultWithCapital):
        cell.value = "N/A"
        return
    if metric == "Peak Capital":
        cell.value = float(result.peak_capital)
        cell.number_format = "$#,##0"
    elif metric == "PV Capital (stock)":
        cell.value = float(result.pv_capital)
        cell.number_format = "$#,##0"
    elif metric == "PV Capital Strain":
        cell.value = float(result.pv_capital_strain)
        cell.number_format = "$#,##0"
    elif metric == "Return on Capital":
        cell.value = _fmt_rate(result.return_on_capital)
        if isinstance(cell.value, float):
            cell.number_format = "0.00%"
    elif metric == "Capital-Adjusted IRR":
        cell.value = _fmt_rate(result.capital_adjusted_irr)
        if isinstance(cell.value, float):
            cell.number_format = "0.00%"


def _write_cash_flows_sheet(wb: "Workbook", export: DealPricingExport) -> None:
    from openpyxl.styles import Alignment, Font

    ws = wb.create_sheet(title="Cash Flows")
    header_font = Font(bold=True)
    centre = Alignment(horizontal="center")

    for col_idx, header in enumerate(_CASH_FLOW_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.alignment = centre

    annual = _aggregate_monthly_to_annual(export.net_cashflows)
    for row_idx, row in enumerate(annual, start=2):
        ws.cell(row=row_idx, column=1, value=row["Year"])
        ws.cell(row=row_idx, column=2, value=row["Gross Premiums"]).number_format = "$#,##0"
        ws.cell(row=row_idx, column=3, value=row["Death Claims"]).number_format = "$#,##0"
        ws.cell(row=row_idx, column=4, value=row["Lapse Surrenders"]).number_format = "$#,##0"
        ws.cell(row=row_idx, column=5, value=row["Expenses"]).number_format = "$#,##0"
        ws.cell(row=row_idx, column=6, value=row["Reserve Increase"]).number_format = "$#,##0"
        ws.cell(row=row_idx, column=7, value=row["Net Cash Flow"]).number_format = "$#,##0"

    ws.column_dimensions["A"].width = 8
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 18


def _aggregate_monthly_to_annual(cf: CashFlowResult) -> list[dict[str, float]]:
    """Collapse a monthly CashFlowResult to an annual table.

    Treats any partial trailing year as an additional row, mirroring
    ``ProfitTester.profit_by_year``. The Year label for the partial row
    is the next integer (so a 241-month projection produces 20 full
    years plus a Year 21 row).
    """
    t = cf.projection_months or len(cf.net_cash_flow)
    if t == 0:
        return []

    def _sum_by_year(arr: np.ndarray) -> np.ndarray:
        n_full = t // 12
        remainder = t % 12
        full = (
            arr[: n_full * 12].reshape(-1, 12).sum(axis=1)
            if n_full > 0
            else np.array([], dtype=np.float64)
        )
        if remainder > 0:
            partial = arr[n_full * 12 :].sum()
            return np.append(full, partial)
        return full

    prem = _sum_by_year(cf.gross_premiums)
    claims = _sum_by_year(cf.death_claims)
    lapses = _sum_by_year(cf.lapse_surrenders)
    expenses = _sum_by_year(cf.expenses)
    reserve = _sum_by_year(cf.reserve_increase)
    ncf = _sum_by_year(cf.net_cash_flow)

    rows: list[dict[str, float]] = []
    for y in range(len(ncf)):
        rows.append(
            {
                "Year": y + 1,
                "Gross Premiums": float(prem[y]),
                "Death Claims": float(claims[y]),
                "Lapse Surrenders": float(lapses[y]),
                "Expenses": float(expenses[y]),
                "Reserve Increase": float(reserve[y]),
                "Net Cash Flow": float(ncf[y]),
            }
        )
    return rows


def _write_assumptions_sheet(wb: "Workbook", export: DealPricingExport) -> None:
    from openpyxl.styles import Font

    ws = wb.create_sheet(title="Assumptions")
    header_font = Font(bold=True)
    title_font = Font(bold=True, size=14)

    ws.cell(row=1, column=1, value="Deal & Assumption Metadata").font = title_font

    deal = export.deal_meta
    asm = export.assumptions_meta

    # Ordered list of (label, value, number_format). None format → default.
    rows: list[tuple[str, object, str | None]] = [
        ("Product Type", deal.product_type, None),
        ("Policies", deal.n_policies, "#,##0"),
        ("Face Amount", deal.face_amount, "$#,##0"),
        ("Treaty Type", deal.treaty_type if deal.treaty_type is not None else "None", None),
        (
            "Cession Percent",
            deal.cession_pct if deal.cession_pct is not None else "N/A",
            "0.00%" if deal.cession_pct is not None else None,
        ),
        ("Hurdle Rate", deal.hurdle_rate, "0.00%"),
        ("Discount Rate", deal.discount_rate, "0.00%"),
        ("Projection Years", deal.projection_years, "#,##0"),
        ("Valuation Date", deal.valuation_date.isoformat(), None),
        ("Mortality Source", asm.mortality_source, None),
        ("Mortality Multiplier", asm.mortality_multiplier, "0.000"),
        ("Lapse Description", asm.lapse_description, None),
        ("Assumption Set Version", asm.assumption_set_version, None),
    ]

    for i, (label, value, fmt) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=label).font = header_font
        cell = ws.cell(row=i, column=2, value=value)
        if fmt is not None:
            cell.number_format = fmt

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 32


def _write_sensitivity_sheet(wb: "Workbook", scenarios: list[ScenarioMetric]) -> None:
    from openpyxl.styles import Alignment, Font

    ws = wb.create_sheet(title="Sensitivity")
    header_font = Font(bold=True)
    centre = Alignment(horizontal="center")

    headers = ("Scenario", "PV Profits", "IRR", "Profit Margin")
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.alignment = centre

    for i, s in enumerate(scenarios, start=2):
        ws.cell(row=i, column=1, value=s.name)
        pv_cell = ws.cell(row=i, column=2, value=float(s.pv_profits))
        pv_cell.number_format = "$#,##0"
        irr_cell = ws.cell(row=i, column=3, value=_fmt_rate(s.irr))
        if isinstance(irr_cell.value, float):
            irr_cell.number_format = "0.00%"
        margin_cell = ws.cell(row=i, column=4, value=_fmt_rate(s.profit_margin))
        if isinstance(margin_cell.value, float):
            margin_cell.number_format = "0.00%"

    ws.column_dimensions["A"].width = 28
    for col in "BCD":
        ws.column_dimensions[col].width = 16


def _write_yrt_rate_table_sheet(wb: "Workbook", table: "YRTRateTable") -> None:
    """Render the loaded YRT rate table on a single ``YRT Rate Table`` sheet.

    Layout: one block per (sex, smoker) cohort, stacked vertically with a
    blank row between blocks. Each block's header row labels the cohort
    and each rate row is ``[age, dur_1, dur_2, ..., dur_N, ultimate]``
    so the sheet is human-readable next to the source CSV (ADR-052).
    """
    from openpyxl.styles import Alignment, Font

    ws = wb.create_sheet(title="YRT Rate Table")
    title_font = Font(bold=True, size=14)
    header_font = Font(bold=True)
    cohort_font = Font(bold=True, italic=True)
    centre = Alignment(horizontal="center")

    ws.cell(row=1, column=1, value=f"YRT Rate Table — {table.table_name}").font = title_font
    ws.cell(
        row=2,
        column=1,
        value=(
            f"Ages {table.min_age}-{table.max_age}, "
            f"select period {table.select_period_years} years. "
            f"Rates are annual $/$1,000 NAR."
        ),
    )

    select_period = table.select_period_years
    headers = ["Age"] + [f"dur_{i}" for i in range(1, select_period + 1)] + ["ultimate"]

    row_idx = 4
    for key in sorted(table.arrays.keys()):
        arr = table.arrays[key]
        # Cohort label.
        ws.cell(row=row_idx, column=1, value=f"Cohort: {key}").font = cohort_font
        row_idx += 1
        # Header row.
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = centre
        row_idx += 1
        # Data rows: one per attained age in the cohort.
        for age_offset in range(arr.rates.shape[0]):
            age = arr.min_age + age_offset
            ws.cell(row=row_idx, column=1, value=age)
            for col_offset in range(arr.rates.shape[1]):
                rate_cell = ws.cell(
                    row=row_idx,
                    column=2 + col_offset,
                    value=float(arr.rates[age_offset, col_offset]),
                )
                rate_cell.number_format = "0.0000"
            row_idx += 1
        # Blank row between cohorts.
        row_idx += 1

    ws.column_dimensions["A"].width = 12
    for col_offset in range(select_period + 1):
        ws.column_dimensions[chr(ord("B") + col_offset)].width = 14


def write_yrt_rate_table_excel(table: "YRTRateTable", path: Path) -> None:
    """Write a standalone Excel workbook for a generated ``YRTRateTable``.

    Used by ``polaris rate-schedule --table`` to emit the solved tabular
    schedule as a deliverable workbook (ADR-053). Layout:

    * ``Summary`` sheet — table name, age range, select period, cohort
      list, and a count of solved cells.
    * ``YRT Rate Table`` sheet — one block per (sex, smoker) cohort
      stacked vertically (delegates to ``_write_yrt_rate_table_sheet``
      so the layout matches the deal-pricing workbook's appended sheet
      verbatim).

    Args:
        table: The populated ``YRTRateTable`` to render.
        path:  Output ``.xlsx`` file path.

    Raises:
        ImportError: If openpyxl is not installed (install via
            ``uv sync --extra tables``).
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:
        raise ImportError(
            "openpyxl required for Excel output. Install via: uv sync --extra tables"
        ) from exc

    wb = Workbook()
    if wb.active is not None:
        wb.remove(wb.active)

    # Summary sheet first so it opens by default.
    ws_summary = wb.create_sheet(title="Summary")
    ws_summary.cell(row=1, column=1, value=f"YRT Rate Table — {table.table_name}").font = Font(
        bold=True, size=14
    )
    ws_summary.cell(row=3, column=1, value="Generated by Polaris RE")
    ws_summary.cell(row=4, column=1, value=f"Age range: {table.min_age}-{table.max_age}")
    ws_summary.cell(row=5, column=1, value=f"Select period (years): {table.select_period_years}")
    ws_summary.cell(row=6, column=1, value=f"Cohorts: {len(table.arrays)}")
    n_cells = sum(int(arr.rates.size) for arr in table.arrays.values())
    ws_summary.cell(row=7, column=1, value=f"Total rate cells: {n_cells}")
    ws_summary.column_dimensions["A"].width = 40

    _write_yrt_rate_table_sheet(wb, table)

    wb.save(path)
