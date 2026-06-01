# Dev Session Log — 2026-05-31

## Item Selected

- **Source:** CONTINUATION_calendar_aligned_portfolio.md (was IN PROGRESS;
  originally from PRODUCT_DIRECTION_2026-05-23.md — IMPORTANT, Recommended
  Next Sprint #1)
- **Priority:** IMPORTANT
- **Title:** Calendar-aligned portfolio aggregation — Slice 2 (CLI + API)
- **Slice:** 2 of 2 (feature now COMPLETE)

## Selection Rationale

A CONTINUATION file existed with Status `IN PROGRESS` and the prior PR
(#48, Slice 1) was merged on 2026-05-29, so per the Daily Dev step 5b
("If merged: continue on a new branch from main") this was the unambiguous
next work item. The CONTINUATION already had Slice 2 fully scoped with
explicit files-to-modify, tests-to-add, and acceptance criteria.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Core `align="calendar"` mode in `Portfolio.run` / `run_with_capital` | Done | #48 |
| 2 | CLI `--align` flag, API `align` field, grid metadata in `to_dict()` | Done | this session |

## What Was Done

Wired the calendar-aligned aggregation mode into the two user-facing
surfaces. The `polaris portfolio run` CLI command grew a
`--align {strict,calendar}` option (default `strict`) that threads into
`portfolio.run(effective_hurdle, align=align)`, with clean error handling
that catches `PolarisValidationError` from the core layer (mismatched
valuation dates under strict, mismatched day-of-month under calendar,
unrecognised align mode) and exits with code 1 and the same human-readable
message the core raises. The Rich overview table gained a `Grid Origin`
row, and the per-deal table grew an `Offset (mo)` column (always shown).

The `POST /api/v1/portfolio` endpoint gained an `align: Literal["strict",
"calendar"]` field on `PortfolioRequest` defaulting to `"strict"`,
delegating validation to Pydantic so bogus values become 422 before the
endpoint logic runs. The endpoint passes the validated value through to
`portfolio.run`.

For JSON-consumer transparency, `PortfolioResult.to_dict()` now carries a
top-level `grid_origin` (ISO date, equal to
`aggregate_cash_flow.valuation_date`) and each per-deal block carries
`valuation_date` (the deal's projection start) and `grid_offset` (whole
months from origin). The latter required two additive defaulted fields on
`DealResult` (`valuation_date: date | None = None`, `grid_offset: int =
0`) populated inside `Portfolio.run` via `dataclasses.replace` after
`_run_deal` returns — this keeps single-deal projection ignorant of grid
alignment while letting the frozen `DealResult` carry the resolved
metadata.

`data/configs/portfolio_demo.yaml` gained a comment block describing how
to flip the demo into calendar mode (no functional change so the existing
strict-mode demo keeps working).

## Files Changed

- `src/polaris_re/analytics/portfolio.py` — `valuation_date` /
  `grid_offset` on `DealResult`, `grid_origin` in `to_dict()`,
  `dataclasses.replace` in `run` to thread offsets, `_deal_result_to_dict`
  surfaces new fields, `AlignMode` in `__all__`.
- `src/polaris_re/cli.py` — `--align` option on `portfolio_run_cmd`,
  `PolarisValidationError` handling around `portfolio.run`, `Grid Origin`
  row + `Offset (mo)` column in `_render_portfolio_summary`.
- `src/polaris_re/api/main.py` — `align` field on `PortfolioRequest`,
  passed through to `portfolio.run`.
- `tests/test_analytics/test_cli_portfolio.py` — `valuation_date` kwarg on
  `_deal_block`; new `TestPortfolioRunAlignFlag` class (7 tests).
- `tests/test_api/test_portfolio.py` — `valuation_date` kwarg on
  `_deal_request`; new `TestPortfolioEndpointAlignField` class (5 tests).
- `data/configs/portfolio_demo.yaml` — commentary on flipping to calendar.
- `docs/DECISIONS.md` — ADR-062.
- `docs/CONTINUATION_calendar_aligned_portfolio.md` — Slice 2 marked DONE,
  Status flipped to COMPLETE, Refinement Backlog populated for the
  harvest step.
- `docs/PRODUCT_DIRECTION_2026-05-23.md` — removed the
  calendar-aligned IMPORTANT entry (shipped), updated the Recommended
  Next Sprint progress block, harvested two new NICE-TO-HAVE follow-ups.

## Tests Added

- `tests/test_analytics/test_cli_portfolio.py::TestPortfolioRunAlignFlag`
  (7): strict-default rejection of mixed dates, calendar mode accepting
  mixed dates with correct `grid_origin` and `projection_months = 126`,
  per-deal `valuation_date` / `grid_offset` exposure, strict-mode zero
  offsets, Rich overview `Grid Origin` row rendered, invalid `--align`
  value rejected, common-day-of-month requirement.
- `tests/test_api/test_portfolio.py::TestPortfolioEndpointAlignField`
  (5): default-strict 422 on mixed dates, `align="calendar"` 200 with
  correct origin and span, per-deal offsets exposed, explicit
  `align="strict"` matches default, Pydantic 422 on bogus align values.

Full suite: **1064 passed, 72 deselected** (1057 baseline + 7 fast new;
the 5 API tests are `@pytest.mark.slow`, matching the existing class).
mypy on the changed modules holds steady at the prior 34-error count —
no new errors introduced. Golden `polaris price` regression unchanged
($45,386).

## Acceptance Criteria

| Criterion (from CONTINUATION Slice 2) | Status | Notes |
|---------------------------------------|--------|-------|
| `polaris portfolio run --align calendar` aggregates a YAML config whose deals have different valuation dates and writes a JSON result | Done | `test_calendar_mode_accepts_mixed_dates` |
| `POST /api/v1/portfolio` with `align="calendar"` aggregates mixed-date deals; omitting `align` preserves the strict default | Done | `test_calendar_mode_accepts_mixed_valuation_dates` + `test_default_strict_rejects_mixed_valuation_dates` |
| `to_dict()` exposes the grid origin (and per-deal offsets if added) | Done | Top-level `grid_origin`; per-deal `valuation_date` + `grid_offset` |

## Open Questions / Follow-ups

- The Slice 1 open question on whether `total_irr` is the right book-level
  metric under calendar alignment was answered "yes, keep it" by this
  slice (no action taken). Reviewers can confirm the call on PR.
- A Streamlit dashboard page for portfolio runs was already a
  NICE-TO-HAVE in PRODUCT_DIRECTION_2026-05-23; this slice's
  `grid_origin` / `grid_offset` exposure makes the calendar-aware variant
  the production-shaped target. Promoted as a refinement of that entry.
- Sub-month / non-common day-of-month inception dates remain rejected by
  design (ADR-061 carried forward in ADR-062). Promoted as NICE-TO-HAVE
  for any future fractional-month / daily-grid work.

## Impact on Golden Baselines

None — `polaris price` is single-deal and does not touch portfolio
aggregation. The golden regression check produced the unchanged
$45,386 figure.
