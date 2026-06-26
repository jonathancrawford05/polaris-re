# Dev Session Log — 2026-06-26 (Solvency ratio: Excel block + dashboard)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` — active Epic
  (Tier-A A3, `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`), **Slice 4c-2b**.
- **Priority:** IMPORTANT (Epic-3 slice).
- **Title:** Surface the regulatory solvency ratio on the Excel deal-pricing
  block and the Streamlit dashboard.
- **Slice:** 4c-2b of the cross-jurisdiction-capital epic (4c-2c remains).
- **Branch:** `claude/awesome-bardeen-uduiso` (environment-designated).

## Selection Rationale

Step 5 found the active Epic's CONTINUATION `IN PROGRESS` with the prior slice
(4c-2a, PR #103) **merged** into `main` and no open PRs, so per step 5b.c the
session advances the Epic's next unchecked slice (4c-2b) before any fallback
pick. 4c-2b was the documented NEXT slice. No fallback work was considered — the
Epic consumed the session.

The Epic's machine surfaces (CLI `--available-capital`, API `available_capital`)
shipped in 4c-2a; 4c-2b is the presentation half — the Excel workbook and the
dashboard, which a reinsurer actually hands to a counterparty / uses to price a
deal interactively. Closing it makes the solvency ratio visible everywhere the
RoC and peak capital already are.

## Verify Premise (step 7b)

Reproduced before writing code: `grep -c "Solvency Ratio\|capital_ratio\|available_capital"`
returned **0** in both `src/polaris_re/utils/excel_output.py` and
`src/polaris_re/dashboard/views/pricing.py` — the two presentation surfaces had
no reference to the ratio at all, while the CLI/API (4c-2a) do. The Excel capital
block (`_CAPITAL_METRICS`) stopped at `Capital-Adjusted IRR`; the dashboard
`_run_pricing_for_cohort` called `run_with_capital` with no `available_capital`,
so `result.capital_ratio` was always `None`. Premise holds.

**Premise correction.** The slice plan said to "thread the numerator through
`DealPricingExport` and `CohortPricingData`". On inspection this is unnecessary:
4c-1 (ADR-103) already echoes `available_capital` and `capital_ratio` onto
`ProfitResultWithCapital`, and both surfaces already carry those result objects.
Reading them directly (as every other capital metric is read) avoids a parallel
field that could drift from the result. The corrected approach is recorded in
ADR-106 and the CONTINUATION.

## What Was Done

**Excel (`utils/excel_output.py`).** Added a `_CAPITAL_RATIO_METRICS` tuple
(`Available Capital`, `Solvency Ratio`) and, inside the existing capital-block
writer, appended those two rows below the 4b "Regulatory Capital — {label}"
header **only when** a rendered result carries a non-`None` `capital_ratio`.
`_write_capital_cell` gained the two metric branches (`$#,##0` for the numerator,
`0.0%` for the ratio; per-side `N/A` for a numerator-less side, e.g. a plain
reinsurer result). No `DealPricingExport` field added.

**Dashboard (`dashboard/views/pricing.py`).** Added an "Available capital
(solvency-ratio numerator, $)" `number_input` under the capital-basis selectbox,
shown only when a basis is chosen; a value `> 0` threads `available_capital`
through `_run_pricing_for_cohort` into both sides'
`run_with_capital(..., available_capital=)`. When a result carries a ratio, the
cedant and reinsurer capital tile rows widen from three columns to four with a
"Solvency Ratio" tile (the supplied numerator over that side's required capital).
Both surfaces gate on `capital_ratio is not None`, so capital-only runs are
byte-identical.

End-to-end verified: `polaris price ... --capital rbc --available-capital 5000000
--excel-out` produced a workbook whose Summary sheet shows `Available Capital`
and `Solvency Ratio` directly below the RBC capital block.

Recorded as ADR-106.

## Files Changed

- `src/polaris_re/utils/excel_output.py` — `_CAPITAL_RATIO_METRICS`, conditional
  ratio rows in the capital block, two new `_write_capital_cell` branches,
  field-comment note.
- `src/polaris_re/dashboard/views/pricing.py` — `available_capital` param +
  threading; numerator `number_input`; fourth "Solvency Ratio" tile on the
  cedant and reinsurer capital rows.
- `tests/test_utils/test_excel_output.py` — `_make_capital_result` gains
  `available_capital` / `capital_ratio`; new `TestSummarySheetSolvencyRatio`.
- `tests/test_dashboard/test_pricing_solvency_ratio.py` — new file.
- `docs/DECISIONS.md` — ADR-106.
- `docs/CONTINUATION_cross_jurisdiction_capital.md` — 4c-2b DONE, 4c-2c NEXT.
- `docs/DEV_SESSION_LOG_2026-06-26_solvency_ratio_excel_dashboard.md` — this log.

## Tests Added

- `TestSummarySheetSolvencyRatio` (6): rows absent on a capital run with no
  numerator and on a no-capital run; both rows present when a numerator is
  supplied; rows positioned directly below `Capital-Adjusted IRR`; cedant
  ratio + numerator values match; reinsurer cell `N/A` in a mixed run.
- `test_pricing_solvency_ratio.py` (8): numerator `None` → ratio `None`; each
  jurisdiction populates a finite ratio when a numerator is supplied; the ratio
  scales linearly with the numerator (fixed denominator); the three standards
  give distinct ratios on the same block.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Excel capital block renders the solvency ratio | ✅ | `Available Capital` + `Solvency Ratio` rows |
| Dashboard collects available capital + shows a ratio tile | ✅ | `number_input` + 4th tile, both sides |
| Numerator threaded into the dashboard pricing path | ✅ | `_run_pricing_for_cohort(..., available_capital=)` |
| Default / capital-only paths byte-identical | ✅ | gated on `capital_ratio is not None` |
| Closed-form verification | ✅ | ratio linear in numerator; distinct per standard |
| Own ADR | ✅ | ADR-106 |
| Full fast suite green | ✅ | 1664 passed (+14), 110 deselected |
| QA golden suite green | ✅ | 76 passed; golden price run unchanged |

## Open Questions / Follow-ups

- **Held-capital basis (carried from 4c-2a/ADR-104).** The dashboard + Excel
  accept an *absolute* available-capital figure. Reinsurers commonly express
  solvency appetite as a target *multiple* of ACL/SCR (e.g. 300–400%). A
  configurable target-multiple numerator form is the natural companion to the
  dashboard input but was deliberately NOT bundled into this presentation slice.
  IMPORTANT (it shapes how a real reinsurer would enter the figure).
- **Per-side numerator.** Both cedant and reinsurer divide the same supplied
  numerator by their own required capital (symmetric with peak/RoC). A per-side
  available-capital input is a later refinement, not a correctness gap.
  NICE-TO-HAVE.

## Parked Polish

None.

## Impact on Golden Baselines

None. The golden `polaris price` run passes no `--capital`, so no capital block
(and thus no ratio rows) is emitted — output byte-identical. The new behaviour is
gated on a supplied `available_capital` numerator. QA golden suite (76) green; the
flat golden price run reproduced unchanged.

## Baseline Note

`make test` at session start: **1650 passed, 110 deselected, 0 failures** (SOA
tables converted successfully this run, so none of the occasional 4 SOA-conversion
failures appeared). This is the recorded baseline. Post-change full fast suite:
**1664 passed** (+14 new tests), 110 deselected, zero failures. Ruff format +
check clean.
