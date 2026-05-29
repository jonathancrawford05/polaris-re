# Dev Session Log — 2026-05-28

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-05-23.md
- **Priority:** IMPORTANT (Promoted Follow-up: ADR-058 "Out of scope" +
  ADR-057 "Out of scope" — "Aggregate return-on-capital on `Portfolio`")
- **Title:** Aggregate return-on-capital on `Portfolio`
- **Slice:** complete (SMALL, single-session)

## Selection Rationale
All five CONTINUATION files are COMPLETE — no multi-session feature is in
progress. Working from the latest PRODUCT_DIRECTION_2026-05-23 Recommended
Next Sprint, the four IMPORTANT items were, in priority order:

1. Calendar-aligned portfolio aggregation (3 dev-days, MEDIUM)
2. Aggregate `CashFlowResult` claims / expenses / reserves on `Portfolio`
   (1 dev-day, SMALL)  →  shipped 2026-05-27 via ADR-059
3. Aggregate return-on-capital on `Portfolio` (2 dev-days, MEDIUM)
4. Per-duration solver in `YRTRateSchedule.generate_table()` (3 dev-days,
   MEDIUM)

I picked #3 because its strict prerequisite (#2) shipped on 2026-05-27,
ADR-059 explicitly named this as the immediately-next follow-up
("Wiring the aggregate `CashFlowResult` into a portfolio-level
`run_with_capital` helper for aggregate return-on-capital — that is the
immediately-next item in PRODUCT_DIRECTION_2026-05-23"), and the work is
clearly bounded: one new dataclass + one new method, no contract change
to existing types. The 2 dev-day estimate was conservative — the
existing `aggregate_cash_flow` and `aggregate_ceded_nar` fields on
`PortfolioResult` are exactly the inputs LICATCapital consumes, so the
implementation is mostly plumbing plus the same metric set
`ProfitTester.run_with_capital` already produces. This made the item
fit comfortably in a single session.

Items #1 (calendar-aligned aggregation) and #4 (per-duration YRT solver)
are both genuine MEDIUM work requiring CONTINUATION files; deferring
them keeps the daily-dev pipeline producing mergeable single-session
PRs.

No PRUNE adjustments to PRODUCT_DIRECTION_2026-05-23 — item #2 was
already removed by virtue of the 2026-05-27 session and the item I
picked here is still active (this PR closes it but does not yet update
the file; the next session can prune both).

## What Was Done
Added `Portfolio.run_with_capital(hurdle_rate, capital_model)` returning
a new `PortfolioResultWithCapital(PortfolioResult)` frozen dataclass.
The method calls `Portfolio.run(hurdle_rate)` internally, then makes a
single `capital_model.required_capital(aggregate_cash_flow,
nar=aggregate_ceded_nar)` call to build the aggregate capital schedule.
The seven capital metrics that `ProfitResultWithCapital` exposes per
deal (`initial_capital`, `peak_capital`, `pv_capital`,
`pv_capital_strain`, `return_on_capital`, `capital_adjusted_irr`,
`capital_by_period`) now appear at the portfolio level — computed once
against the aggregate inputs, not summed from per-deal calls.

The single-call design is actuarially justified: LICAT's factor model is
linear in `reserve_balance` and `NAR`, both of which are summed across
deals into `aggregate_cash_flow` and `aggregate_ceded_nar`. A regression
test pins the invariant that the single-call schedule equals the
month-by-month sum of per-deal capital schedules under the same factors
(`test_capital_linearity_matches_sum_of_per_deal_capital`).

RoC denominator is `pv_capital` (stock) per ADR-048;
`return_on_capital` is `None` when `pv_capital <= 0` (zero-factor model
or coinsurance-only book where aggregate NAR is zero). The
capital-adjusted IRR reuses `ProfitTester._solve_irr` so the IRR
suppression rules from ADR-041 stay consistent at deal and portfolio
level.

`PortfolioResultWithCapital.to_dict()` extends the base `to_dict()`
output with a new top-level `capital` block. Every existing key on
`PortfolioResult.to_dict()` is unchanged, so CLI / API / dashboard
consumers of the base contract keep working.

## Files Changed
- `src/polaris_re/analytics/portfolio.py` (+~115 / -~5 lines: new
  `PortfolioResultWithCapital` dataclass + `Portfolio.run_with_capital`
  method + `__all__` update + capital import).
- `src/polaris_re/analytics/__init__.py` (+2 lines: re-export
  `PortfolioResultWithCapital`).
- `tests/test_analytics/test_portfolio.py` (+~210 lines: 10 new tests
  in `TestPortfolioRunWithCapital` + a small `_yrt` helper).
- `docs/DECISIONS.md` (+~93 lines: ADR-060 records the design decision,
  the actuarial invariant, and the scope boundary).

## Tests Added
- `test_returns_portfolio_result_with_capital` — type + isinstance
  checks; result IS a `PortfolioResult` so base consumers keep working.
- `test_base_portfolio_fields_preserved` — every base
  `PortfolioResult` field equals what `run(hurdle_rate)` returns.
- `test_capital_equals_single_call_on_aggregate` — closed-form pin
  that the schedule matches
  `capital.required_capital(aggregate_cash_flow, nar=aggregate_ceded_nar)`.
- `test_capital_linearity_matches_sum_of_per_deal_capital` — the
  actuarial invariant: with the same factors, the single-call portfolio
  capital equals the sum of per-deal capital schedules.
- `test_roc_closed_form_pv_profits_over_pv_capital` — RoC equals
  `total_pv_profits / pv_capital`.
- `test_zero_capital_factor_yields_none_roc` — guardrail when
  `pv_capital <= 0`.
- `test_doubling_c2_factor_halves_roc` — sensitivity check on a
  YRT-only book.
- `test_empty_portfolio_run_with_capital_rejected` — same validation
  semantics as `run`.
- `test_capital_by_period_shape_matches_projection_months` — shape
  pin + check that the schedule steps down (not up) at the seam where
  a shorter deal drops out.
- `test_to_dict_exposes_capital_block` — JSON-serialisable round-trip
  with the new `capital` block alongside the existing keys.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Single `LICATCapital` call at portfolio level | OK | `Portfolio.run_with_capital` makes exactly one `required_capital` call against `(aggregate_cash_flow, aggregate_ceded_nar)`. |
| NAR aggregation per deal | OK | `aggregate_ceded_nar` is the sum of per-deal `ceded_nar` (already computed by `Portfolio.run` since ADR-057); passed explicitly to `LICATCapital`. |
| Affected: `analytics/portfolio.py` | OK | New dataclass + method, additive. |
| Affected: tests | OK | 10 new tests, all 53 portfolio tests pass. |
| No contract change on `PortfolioResult` | OK | Base class unchanged; capital metrics live on a new subclass. |

## Open Questions / Follow-ups
- CLI / API / Excel surfacing of the new `capital` block is deferred —
  flagged as "Out of scope" in ADR-060. The raw fields are in
  `to_dict()` so any JSON consumer can read them today; Rich rendering
  for `polaris portfolio --capital` (or similar) is a small follow-up
  that should land together with a coherent set of portfolio-level
  summary numbers (e.g. aggregate loss ratio from ADR-059).
- Heterogeneous-product capital factors. The single `LICATCapital`
  applies one factor set to the entire portfolio. A mixed term / WL / UL
  book may benefit from product-aware C-2 factors; today the caller
  supplies a blended `LICATFactors` or runs per-product sub-portfolios.
  A built-in product-aware aggregation is tracked separately under
  PRODUCT_DIRECTION_2026-05-23 "LICAT lapse-risk and morbidity-risk
  capital components" and is a separate design ADR.

## Impact on Golden Baselines
None. The `polaris price` golden regression check produced unchanged
output — this change touches `Portfolio.run_with_capital` only, and the
pricing CLI does not invoke the portfolio runner. The change is purely
additive: a new method + a new subclass; no existing field or method
behaviour changes.
