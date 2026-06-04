# Continuation: Calendar-Aligned Portfolio Aggregation

**Source:** PRODUCT_DIRECTION_2026-05-23.md — IMPORTANT (Recommended Next
Sprint #1; Refinement Backlog #1 from CONTINUATION_portfolio_aggregation)
**Status:** COMPLETE (Slice 2 shipped 2026-05-31)
**Harvest status:** All surviving refinement items promoted to
PRODUCT_DIRECTION_2026-05-23.md (confirmed 2026-06-04).
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

- **Status:** DONE
- **Branch:** claude/vibrant-turing-knGTC
- **PR:** — (draft, this session)
- **What was done:** Added `--align {strict,calendar}` (default `strict`) to
  `polaris portfolio run`; routed it through
  `portfolio.run(effective_hurdle, align=align)`. Added an `align:
  Literal["strict","calendar"]` field to `PortfolioRequest` and passed it
  through to `portfolio.run` in `api_portfolio`. Surfaced grid metadata in
  `PortfolioResult.to_dict()`: a top-level `grid_origin` (ISO date,
  equal to `aggregate_cash_flow.valuation_date`) plus per-deal
  `valuation_date` and `grid_offset` (months from origin). Chose to add
  defaulted `valuation_date: date | None = None` and `grid_offset: int = 0`
  fields on `DealResult` rather than computing offsets in `to_dict()` — the
  dataclass already owns the per-deal serialisation site and the additive
  defaults keep every existing reader untouched. `Portfolio.run` builds
  each `DealResult` with offset 0 inside `_run_deal` and uses
  `dataclasses.replace` to inject the resolved offset before appending.
  The Rich overview gains a `Grid Origin` row; the per-deal table grows an
  `Offset (mo)` column (always shown — `0` for the strict / earliest-deal
  case). ADR-062 records the design.
- **Key decisions:**
  - **`DealResult` additive fields over external offset store.** Per-deal
    JSON already flows through `_deal_result_to_dict`; carrying the date
    stamp on `DealResult` keeps `to_dict()` from reaching across two
    structures. Defaults preserve backward compatibility for any external
    constructor.
  - **`Offset (mo)` column always rendered.** The CONTINUATION suggested
    conditional rendering based on whether any deal was off-origin, but
    that required iterating `result_dict["deals"]` twice through the
    `dict[str, object]` interface and added a mypy-ignore hop. Always
    rendering the column keeps the table shape stable across
    strict/calendar runs and matches the JSON output's permanent
    `grid_offset` field.
- **Tests added (12 total):**
  - `tests/test_analytics/test_cli_portfolio.py::TestPortfolioRunAlignFlag`
    (7 tests): strict-default rejection of mixed dates, calendar mode
    accepting mixed dates with correct `grid_origin` and
    `projection_months = 6 + 120 = 126`, per-deal `valuation_date` /
    `grid_offset` exposure, strict-mode zero offsets with origin equal to
    shared date, Rich overview's `Grid Origin` row rendered, invalid
    `--align` value rejected, common-day-of-month requirement.
  - `tests/test_api/test_portfolio.py::TestPortfolioEndpointAlignField`
    (5 tests): default-strict 422 on mixed dates, `align="calendar"` 200
    with `grid_origin` and `projection_months = 126`, per-deal offsets
    exposed, explicit `align="strict"` matches default, Pydantic 422 on
    bogus align values.

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

## Refinement Backlog (harvested 2026-05-31 into PRODUCT_DIRECTION_2026-05-23)

These items are documented as out-of-scope for the two-slice feature and
have been promoted (via the Daily Dev HARVEST step) to
PRODUCT_DIRECTION_2026-05-23 so future routine runs can pick them up. They
remain listed here as the audit trail.

1. **Streamlit dashboard page for calendar-aligned portfolios.** The
   dashboard prices one deal at a time today. A portfolio page would
   consume the same `to_dict()` shape and surface `grid_origin` /
   `grid_offset` alongside the per-deal table. NICE-TO-HAVE; ~3 dev-days.
   Source: ADR-062 Out of scope.

2. **Sub-month / non-common day-of-month inception dates.** Calendar mode
   today requires all valuation dates on the same day-of-month. Supporting
   arbitrary days would require a daily grid or fractional-month
   discounting. NICE-TO-HAVE; design ADR + ~2 dev-days. Source: ADR-061
   Out of scope (carried forward in ADR-062).

3. **Deal-specific hurdle rates on `Portfolio`.** The PV-origin question
   under calendar alignment makes this even more pointed — `Σ_i v**(o_i,
   r_i) · PV_i` does not collapse to a single discount factor. Still
   NICE-TO-HAVE and tracked in PRODUCT_DIRECTION_2026-05-23 already; no
   change required from Slice 2 beyond noting the interaction. Source:
   CONTINUATION_portfolio_aggregation Refinement Backlog #4 (existing).

## Open Questions — resolved

The Slice 1 open question on whether to report `total_irr` under calendar
alignment is **answered: yes, keep reporting it.** Slice 2 took no
action — the aggregate IRR is the IRR of the calendar-aligned NCF, which
is the well-defined book-level metric reviewers consume. The naive
weighted blend remains derivable from per-deal `profit_test.irr` for
callers who want it.
