# Dev Session Log — 2026-04-26

## Item Selected

- **Source:** docs/CONTINUATION_licat_capital.md (continuation of
  PRODUCT_DIRECTION_2026-04-19.md — BLOCKER #5: LICAT regulatory capital)
- **Priority:** BLOCKER
- **Title:** LICAT regulatory capital — Slice 2: ProfitTester integration
  (`run_with_capital` + RoC + capital-adjusted IRR)
- **Slice:** 2 of 3

## Selection Rationale

Step 5 of the Daily Dev routine identified `CONTINUATION_licat_capital.md`
as the only IN-PROGRESS multi-session feature. PR #33 (Slice 1) is
merged; no other PRs are open. Per the routine the in-progress
continuation takes precedence over new PRODUCT_DIRECTION items, so I
proceeded directly to Slice 2 from main.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Standalone `LICATCapital` calculator (factor model + `for_product`) | ✅ Done | #33 (merged) |
| 2 | `ProfitTester.run_with_capital` + RoC + capital-adjusted IRR + ADR-048 | ✅ Done (this session) | (this PR — draft) |
| 3 | CLI `--capital licat`, API `capital_model`, Excel Summary rows, dashboard tile | 🔲 Planned | — |

## What Was Done

Wired the Slice-1 `LICATCapital` calculator into `ProfitTester` via a
new `run_with_capital(capital_model, *, nar=None)` method that returns
`ProfitResultWithCapital`. The new dataclass extends `ProfitTestResult`
with seven capital fields (`initial_capital`, `peak_capital`,
`pv_capital`, `pv_capital_strain`, `return_on_capital`,
`capital_adjusted_irr`, `capital_by_period`). Existing `run()` callers
are unaffected — every base field is preserved by value, the new method
is opt-in, and the existing 757 non-slow tests + 33 QA tests still pass
unchanged.

ADR-048 records three design decisions: (1) RoC denominator defaults to
PV(capital STOCK) at the hurdle rate (the simpler, more widely cited
metric); (2) NAR sourcing for non-YRT runs is the caller's
responsibility via the `nar=` keyword (honouring the PR #33 guard rail
of not expanding `CashFlowResult` with a stock variable); and (3)
capital-adjusted IRR is computed on distributable cash flow
`net_cash_flow_t - strain_t` with terminal release of the residual
capital balance, which sets the undiscounted total equal to the
vanilla profit total.

To support the new metrics, `CapitalResult` gained two methods:
`capital_strain()` (period-over-period diff with `capital_{-1} = 0`,
no terminal release inside the calculator) and `pv_capital_strain(rate)`
(PV of strain at the hurdle rate, useful as the alternative RoC
denominator). The IRR computation in `ProfitTester` was refactored into
a shared `_solve_irr(profits)` helper that mirrors the ADR-041
sign-change suppression and large-magnitude guard rail; `run()`
continues to inline the same logic for byte-equality on the existing
fields.

## Files Changed

- `src/polaris_re/analytics/profit_test.py` — added
  `ProfitResultWithCapital` dataclass, `run_with_capital` method, and
  `_solve_irr` helper.
- `src/polaris_re/analytics/capital.py` — added
  `CapitalResult.capital_strain()` and
  `CapitalResult.pv_capital_strain(rate)` methods.
- `src/polaris_re/analytics/__init__.py` — re-exports
  `ProfitResultWithCapital`; `__all__` re-sorted.
- `docs/DECISIONS.md` — appends ADR-048.
- `docs/CONTINUATION_licat_capital.md` — Slice 2 marked DONE; Open
  Question #1 (RoC stock vs strain) resolved.
- `docs/DEV_SESSION_LOG_2026-04-26_licat_capital_slice_2.md` — this
  file.

## Tests Added

`tests/test_analytics/test_profit_test.py` — 14 new tests across two
classes:

- **`TestProfitTesterWithCapital`** (12) — return type
  (`ProfitResultWithCapital` IS-A `ProfitTestResult`), base-field
  preservation (every `ProfitTestResult` field equals the value
  returned by `run()`), RoC closed-form (`pv_profits / pv_capital`
  matches direct computation), doubling-factor halves RoC
  sensitivity, explicit `nar=` plumbing, missing-NAR raises
  `PolarisComputationError`, zero-factor capital model yields
  `return_on_capital is None`, `capital_by_period` shape and value
  match the standalone calculator, `pv_capital_strain` for flat
  capital equals `K × v`, capital-adjusted IRR strictly below
  vanilla IRR for a strained deal, `run()` is byte-equal before and
  after a `run_with_capital` call (no shared mutable state), and
  module export of `ProfitResultWithCapital` via
  `polaris_re.analytics`.
- **`TestPvCapitalStrainClosedForm`** (2) — strain telescope at
  rate=0 (sum of strain equals `capital[T-1]`), and flat-capital
  PV(strain) = `K × v`.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `ProfitTester.run_with_capital(LICATCapital.for_product(TERM))` returns `ProfitResultWithCapital` with non-None capital fields | ✅ | covered by `test_returns_profit_result_with_capital` |
| Closed-form RoC test passes within float tolerance | ✅ | `test_roc_closed_form_pv_profits_over_pv_capital` |
| Existing `ProfitTester.run()` callers unaffected | ✅ | 757 baseline tests still pass; explicit `test_run_unaffected_by_run_with_capital` and `test_base_profit_fields_preserved` |
| Doubling capital factor halves RoC | ✅ | `test_doubling_capital_factor_halves_roc` |
| `nar=` argument plumbed through to `LICATCapital` | ✅ | `test_explicit_nar_plumbed_through_to_calculator` |
| Missing NAR raises a clear `PolarisComputationError` | ✅ | `test_no_nar_raises` |
| Capital-adjusted IRR is well-defined and strictly below vanilla IRR for a strained profitable deal | ✅ | `test_capital_adjusted_irr_falls_below_vanilla_when_capital_strained` |
| Golden baselines unchanged | ✅ | `polaris price` golden regression byte-identical (Slice 2 is opt-in; no pricing path calls `run_with_capital`) |
| ADR-048 written | ✅ | appended to `docs/DECISIONS.md` |
| Ruff format / check clean on modified files | ✅ | both clean |

## Open Questions / Follow-ups

- **C-1 / C-3 still zero stubs.** Phase 5.4 (asset / ALM model) will
  populate them. Slice 3 should note in the Excel "Assumptions" sheet
  that C-1 and C-3 are not modelled in v1.
- **Strain vs stock denominator default.** ADR-048 picks stock; if
  deal committee feedback prefers strain after Slice 3 ships, a one-
  line change in `run_with_capital` flips the default and a follow-up
  ADR-048a documents the rationale.
- **Cost-of-capital interest credit.** Some firms credit the
  held-capital balance with the risk-free rate as an offset to the
  capital charge. Out of scope until Phase 5.4 exposes a risk-free
  curve; document in Slice 3 PR if reviewer asks.
- **Lapse-risk and morbidity-risk capital.** Still pending the
  Phase 5.1.b ADR after Slice 3 ships.

## Impact on Golden Baselines

None. Slice 2 is purely additive and opt-in; no existing pricing path
calls `run_with_capital`. The golden regression check
(`polaris price --inforce data/qa/golden_inforce.csv --config
data/qa/golden_config_flat.json -o /tmp/dev_check.json`) produces
output byte-identical to the prior committed baseline.
