# Continuation: Calendar-Aligned Portfolio Aggregation

**Source:** PRODUCT_DIRECTION_2026-05-23.md — IMPORTANT (Recommended Next
Sprint #1; Refinement Backlog #1 from CONTINUATION_portfolio_aggregation)
**Status:** IN PROGRESS
**Total slices:** 2
**Estimated total scope:** ~3 dev-days

## Overall Goal

A reinsurer's assumed book has treaties inception-dated across many years.
`Portfolio.run()` originally aggregated cash flows by month index, which is
only valid when every deal shares a valuation date (Slice 1 of Milestone 5.2
*guarded* this by rejecting mixed dates). This feature lets the portfolio
runner aggregate deals on a common monthly **calendar** grid keyed off the
earliest valuation date, so deals with different inception dates aggregate
correctly. When complete, `polaris portfolio run` (CLI) and
`POST /api/v1/portfolio` (API) both expose the calendar-aligned mode, and the
serialised result carries the grid origin and per-deal grid offsets.

## Decomposition

### Slice 1: core calendar alignment in `Portfolio.run` / `run_with_capital`

- **Status:** DONE
- **Branch:** claude/vibrant-turing-hNSGv
- **PR:** — (draft)
- **What was done:** Added an opt-in keyword-only `align: "strict" |
  "calendar"` parameter to `Portfolio.run` and `Portfolio.run_with_capital`,
  defaulting to `"strict"` (the prior behaviour — reject mixed valuation
  dates, PV sums). `align="calendar"` keys a common monthly grid off the
  earliest valuation date, places each deal's cash flows at its whole-month
  offset via a generalised `_place(arr, offset, length)` primitive (which
  replaced the trailing-only `_pad`), and sets the aggregate
  `CashFlowResult.valuation_date` to the grid origin and `projection_months`
  to `max(offset_i + T_i)`. Calendar mode requires a common day-of-month so
  the monthly grids line up. ADR-061 records the design.
- **Key decisions:**
  - **PV semantics.** Because PV discounts from the array origin, a deal at
    offset `o` contributes `v**o ×` its standalone PV, so the aggregate
    `total_pv_profits` under `"calendar"` is the portfolio NPV *as of the
    common origin* — NOT the naive sum of per-deal PVs. This is the correct
    economic number and resolves Refinement Backlog #4's structural concern.
    Per-deal `DealResult` PVs stay as-of each deal's own inception.
  - **Backward compatibility.** `align` defaults to `"strict"`; `_place(arr,
    0, length)` is identical to the old zero-pad, so strict-mode output is
    byte-for-byte unchanged. The strict error message keeps the matched
    substring "same valuation date".
  - **No contract change.** `PortfolioResult` /
    `PortfolioResultWithCapital` fields are unchanged; the grid origin is
    surfaced via `aggregate_cash_flow.valuation_date`.

### Slice 2: CLI + API integration

- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:**
  - `src/polaris_re/cli.py` — add `--align {strict,calendar}` to the
    `polaris portfolio run` command (default `strict`); pass through to
    `portfolio.run(effective_hurdle, align=...)`. Consider rendering the
    grid origin in the Rich summary.
  - `src/polaris_re/api/main.py` — add an optional `align` field to the
    portfolio request model (default `"strict"`); pass through to
    `portfolio.run(request.hurdle_rate, align=...)`.
  - `src/polaris_re/analytics/portfolio.py` — surface the grid origin
    (`aggregate_cash_flow.valuation_date`) and, ideally, each deal's grid
    offset in `PortfolioResult.to_dict()` so JSON consumers can reconstruct
    placement without re-deriving dates. Adding a per-deal `grid_offset`
    requires either a new `DealResult` field (defaulted, additive) or
    computing offsets in `to_dict()` — decide in Slice 2.
  - `data/configs/portfolio_demo.yaml` — optionally add a second deal with a
    later inception date to demo calendar mode.
- **Tests to add:**
  - `tests/test_analytics/test_cli_portfolio.py` — `--align calendar` on a
    mixed-date 2-deal config produces a result whose `projection_months`
    spans the calendar grid; `--align strict` (default) still rejects mixed
    dates.
  - `tests/test_api/test_portfolio.py` — `align="calendar"` round-trips a
    mixed-date 2-deal request; default rejects mixed dates.
- **Acceptance criteria:**
  - `polaris portfolio run --align calendar` aggregates a YAML config whose
    deals have different valuation dates and writes a JSON result.
  - `POST /api/v1/portfolio` with `align="calendar"` aggregates mixed-date
    deals; omitting `align` preserves the strict default.
  - `to_dict()` exposes the grid origin (and per-deal offsets if added).

## Context for Next Session

- The CLI portfolio command is at `src/polaris_re/cli.py:~1812` (builder) and
  calls `portfolio.run(effective_hurdle)` at `~2013`. The API endpoint builds
  the portfolio at `src/polaris_re/api/main.py:~1322` and calls
  `portfolio.run(request.hurdle_rate)` at `~1377`. Both call `run` with no
  `align` kwarg today, so they default to `"strict"` and are unaffected by
  Slice 1.
- The per-deal config blocks already reuse `_parse_config_to_pipeline_inputs`
  and each deal carries its own `config.valuation_date`, so a mixed-date
  portfolio config is already expressible — Slice 2 only needs to flip the
  `align` switch and stop the strict rejection for those configs.
- Surfacing per-deal grid offsets: the cleanest path is to compute them in
  `to_dict()` from `aggregate_cash_flow.valuation_date` and each
  `DealResult`'s deal config — but `DealResult` does not currently carry the
  deal's valuation date. Either add a defaulted `valuation_date` /
  `grid_offset` field to `DealResult` (additive, backward-compatible) or have
  `Portfolio.run` stash the offsets. Decide in Slice 2.

## Open Questions (for human)

- Should the calendar-aligned `total_irr` be reported at all? IRR of the
  calendar-aligned aggregate NCF is well-defined (it is just the IRR of the
  combined stream from the common origin), but reviewers should confirm that
  a single book-level IRR across mixed-inception deals is the metric they
  want, versus a weighted blend. Slice 1 reports it (it falls out of the
  aggregate `ProfitTester`); flag for confirmation, not blocking.

When all slices are DONE, update Status to COMPLETE — and first run the
HARVEST FOLLOW-UPS step so this CONTINUATION's surviving refinement items and
ADR-061's "Out of scope" list are promoted to the latest PRODUCT_DIRECTION.
