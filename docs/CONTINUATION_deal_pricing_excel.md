# Continuation: Deal-Pricing Excel Export

**Source:** PRODUCT_DIRECTION_2026-04-19.md — BLOCKER (item #4 in
Recommended Next Sprint)
**Status:** IN PROGRESS
**Total slices:** 2
**Estimated total scope:** ~2 dev-days

## Overall Goal

Give Polaris RE a committee-packet Excel deliverable for deal pricing.
Today, `polaris price` emits JSON; a pricing actuary cannot circulate
JSON to a deal committee. The feature adds a formatted workbook with
Summary (IRR/NPV/margin/breakeven), Cash Flows (annual rollup),
Assumptions (mortality/lapse/treaty/hurdle), and Sensitivity (scenario
results) sheets, plus a `polaris price --excel-out path.xlsx` CLI flag
that writes the workbook alongside the existing JSON output.

## Decomposition

### Slice 1: Library writer + DTOs (this session)
- **Status:** DONE
- **Branch:** `claude/blissful-volta-e6Cb6`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `write_deal_pricing_excel(export, path)` to
    `src/polaris_re/utils/excel_output.py`, alongside the pre-existing
    `write_rate_schedule_excel`.
  - Added four frozen dataclasses as the public API:
    `DealMetaExport`, `AssumptionsMetaExport`, `ScenarioMetric`, and
    `DealPricingExport` (the bundle accepted by the writer).
  - Workbook structure: Summary → Cash Flows → Assumptions →
    Sensitivity (the last one is omitted when
    `export.scenario_results is None`).
  - Summary sheet: one metric column for Cedant (NET), one optional
    metric column for Reinsurer (omitted when
    `reinsurer_result=None`).
  - Cash Flows sheet: annual rollup of the NET `CashFlowResult` with
    seven canonical columns (Year, Gross Premiums, Death Claims,
    Lapse Surrenders, Expenses, Reserve Increase, Net Cash Flow).
  - Assumptions sheet: flat label/value table sourced from
    `DealMetaExport` + `AssumptionsMetaExport`.
  - Guardrail handling: `ProfitTestResult.irr` or `profit_margin`
    equal to `None` (ADR-041 guardrails) render as the string `"N/A"`
    in the affected cell; float cells carry a `"0.00%"` or `"$#,##0"`
    number format.
  - ADR-045 added to `docs/DECISIONS.md`.
- **Files modified / added:**
  - `src/polaris_re/utils/excel_output.py` (modified — added four DTOs,
    one new public writer, and four private sheet builders).
  - `tests/test_utils/test_excel_output.py` (new).
  - `docs/DECISIONS.md` (ADR-045 appended).
- **Tests added (20):** five test classes covering file
  creation/roundtrip, Summary values and conditional reinsurer
  column, Cash Flows aggregation and row count, Assumptions key
  presence, and Sensitivity row-per-scenario. Full suite: 722
  non-slow (up from 702), QA suite 29/29.
- **Acceptance criteria:**
  - `write_deal_pricing_excel` produces a valid `.xlsx` file. ✅
  - Required sheets (Summary, Cash Flows, Assumptions) always
    present. ✅
  - Sensitivity sheet present iff `scenario_results is not None`. ✅
  - Summary IRR cell equals `ProfitTestResult.irr`. ✅
  - Cash Flows sheet has `projection_years` data rows. ✅
  - Annual premium column sums match monthly aggregation exactly. ✅
  - Guardrail-suppressed values (`irr=None`, `profit_margin=None`)
    render as `"N/A"`. ✅
  - Golden regression unchanged. ✅
  - ADR-045 written. ✅
- **Key decisions that affect the next slice:**
  - **NET cash flows only, for now.** `DealPricingExport` accepts
    `gross_cashflows` and `ceded_cashflows` as optional fields, but
    Slice 1 does not render them — the presentation for gross/ceded
    (separate sheets? merged columns?) is deferred to Slice 2 once
    the CLI wiring confirms what downstream consumers need.
  - **Annual, not monthly, cash flows.** Committee packets never
    work at monthly granularity. The aggregation mirrors
    `ProfitTester.profit_by_year` exactly, so a 241-month projection
    produces 20 full years plus a partial Year 21 row — both outputs
    agree on the year numbering.
  - **Structured DTOs, not `dict[str, Any]`.** Per the project
    typing rules (no `Any`), the metadata is split into two frozen
    dataclasses (`DealMetaExport`, `AssumptionsMetaExport`). This
    makes Slice 2 a mechanical translation from `CohortResult` +
    `PipelineInputs` → export bundle.
  - **Reinsurer column appears only when relevant.** For a
    standalone gross run (no treaty), the Summary sheet has one
    metric column, not two. This keeps single-sided projections
    visually clean.

### Slice 2: CLI wiring + mixed-cohort behaviour
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Branch (planned):** `feat/auto-deal-excel-export-s2-2026-XX-XX`
- **Files to create/modify:**
  - `src/polaris_re/cli.py` — add `--excel-out PATH` option to
    `polaris price`. When provided, translate each `CohortResult`
    into a `DealPricingExport` and call `write_deal_pricing_excel`.
    For a single-cohort deal, write one workbook at the provided
    path. For mixed cohorts, write either a single workbook with
    one sheet set per cohort (preferred) OR one file per cohort
    (alternative — see open question below).
  - `tests/qa/test_cli_golden.py` — add one CLI integration test
    using the golden YRT config: run `polaris price --excel-out`,
    verify the workbook exists, verify sheet names, verify Summary
    IRR cell equals the JSON `cedant.irr` field.
  - (Optional) `tests/test_utils/test_excel_output.py` — if the
    translation helper lives in `excel_output.py`, add unit tests
    for it.
- **Tests to add (estimated 3-4):**
  - CLI integration: `polaris price --excel-out` produces a valid
    workbook whose cell values match the JSON output.
  - CLI integration: `polaris price` without `--excel-out` does not
    write any .xlsx (no regression of existing JSON-only path).
  - (If mixed-cohort aggregation is implemented) cohort sheet
    naming test.
- **Acceptance criteria:**
  - `polaris price --inforce ... --config ... --excel-out deal.xlsx`
    writes a valid workbook.
  - Summary IRR cell equals the JSON `cedant.irr` value.
  - Cash flow row count equals `projection_years`.
  - Existing CLI JSON output unchanged when `--excel-out` is not
    provided (no regression).
  - Golden regression unchanged.

## Context for Next Session

- The writer does not call back into the CLI or pipeline — it only
  imports `ProfitTestResult` and `CashFlowResult`. This is
  intentional: Slice 2 will add the *translation* from CLI
  `CohortResult` → `DealPricingExport` inside `cli.py`. Keeping the
  writer free of CLI imports means future non-CLI consumers (e.g.
  the FastAPI service or the Streamlit dashboard) can use the same
  writer without pulling in CLI machinery.
- The pipeline currently does not persist the `CashFlowResult` used
  by the profit test back to the CLI JSON output — only
  `profit_by_year` survives. The Excel writer therefore needs the
  *live* `CashFlowResult` object, which means the translation must
  happen during `_price_single_cohort` or immediately after, before
  the CashFlowResult goes out of scope. One clean option: extend
  `CohortResult` (in `cli.py`) to carry the `net_cashflows` (and
  optionally `gross_cashflows` / `ceded_cashflows`) as attributes.
- The `AssumptionsMetaExport.lapse_description` is a free-text
  string on purpose — the lapse table is either a small
  duration-keyed dict or a select-ultimate loaded from a CSV, and
  both cases collapse cleanly to a human-readable one-liner. Slice
  2 should build this string from `AssumptionSet.lapse` using a
  small helper; don't pass the full numeric lapse vector into the
  workbook.
- Default `DealMetaExport` values are not provided. If Slice 2
  needs to handle the case where a field isn't known (e.g.
  `treaty_type=None` when there is no treaty), the DTO already
  supports it (`treaty_type: str | None`, `cession_pct: float |
  None`). Use `None`; the writer renders missing cession as `"N/A"`
  and treaty type as `"None"`.
- For the rate-schedule Excel writer (pre-existing), the sheet
  name for "Summary" is hardcoded. The new deal-pricing writer
  uses the same sheet name. If both writers ever produce to the
  same workbook (not currently planned), this will collide —
  today it doesn't, but flagging it for Slice 2's design review.

## Open Questions (for human)

1. **Mixed-cohort behaviour for `--excel-out`.** Two options:
   a. Single workbook, one sheet set per cohort (sheet names
      prefixed by cohort id, e.g. `Summary-TERM`, `Summary-WL`).
   b. One workbook per cohort, filename derived from the target
      path (e.g. `deal-TERM.xlsx`, `deal-WL.xlsx`).
   Slice 2 will default to option (b) unless directed otherwise —
   it is simpler to implement, preserves the Slice 1 workbook
   schema exactly, and committee packets normally cover one
   product at a time anyway. Flag in the Slice 2 PR for human
   confirmation.
2. **Gross/ceded cash flow sheets.** Slice 1 deliberately omits
   gross and ceded cash flow sheets even though the DTO fields
   exist. If the deal committee needs them (three-sheet cash-flow
   section: Gross / Ceded / Net), Slice 2 will add them as three
   additional sheets. If only Net is needed, leave as-is and drop
   the unused `gross_cashflows` / `ceded_cashflows` fields from
   `DealPricingExport` before Slice 1 is merged in a follow-up.
3. **Per-policy substandard rating surface.** `rated_block` is in
   the CLI JSON output today. Should the workbook's Assumptions
   sheet also include a block-rating panel (n_rated, % rated,
   face-weighted avg multiplier)? Default for Slice 2 is yes —
   committee reviewers will ask.
4. **Sensitivity source.** `scenario_results` in
   `DealPricingExport` is a flat list of `ScenarioMetric`. The CLI
   does not currently couple `polaris price` to `polaris scenario`
   — the Sensitivity sheet will be empty on a bare `polaris price
   --excel-out` run. Slice 2 options:
   a. Leave the Sensitivity sheet omitted on `polaris price`.
      Users who want it run `polaris scenario --excel-out`.
   b. Add a `--with-sensitivity` flag to `polaris price` that
      runs the standard scenarios inline and populates the
      Sensitivity sheet.
   Default for Slice 2 is (a) — keeps `polaris price` fast and
   `polaris scenario` authoritative for sensitivity analysis.

When all slices are DONE, update Status to COMPLETE.
