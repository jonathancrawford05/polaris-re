# Dev Session Log — 2026-06-01 (run_scenarios)

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-05-23.md
- **Priority:** IMPORTANT (Recommended Next Sprint #2; Promoted Follow-ups
  IMPORTANT — provenance: CONTINUATION_portfolio_aggregation Refinement
  Backlog #3)
- **Title:** Portfolio-level scenario analysis (`Portfolio.run_scenarios`)
- **Slice:** complete (SMALL — single session)

## Selection Rationale

All six `docs/CONTINUATION_*.md` files are COMPLETE — no multi-session
work was in progress to continue.

PRODUCT_DIRECTION_2026-05-23.md has no BLOCKERs. The Recommended Next
Sprint listed two IMPORTANT items. Item #1 (per-duration YRT solver,
ADR-063) shipped earlier today via PR #50, so it was pruned from the
file as the first step of this session — closed by inspection
(commit efd2b58, ADR-063 referenced in DECISIONS.md). Item #2
(`Portfolio.run_scenarios`) is the natural successor: the aggregation
surface (ADR-057 / 058 / 059 / 060 / 061 / 062) already supports
everything `run_scenarios` needs, and the remaining design question
(correlated vs. independent stresses across cedants) has a clean
conservative default (correlated).

After sizing (3 files modified, ~410 lines net, no contract changes —
new `PortfolioScenarioResult` is an additive dataclass, `_apply_scenario`
rename is internal) the item classifies as SMALL, so I implemented it
fully in this session rather than creating a CONTINUATION.

The other listed IMPORTANT items (reserve-basis matching, IFRS 17
movement table) are 10 dev-days each — genuinely Phase 5.3+ work and
should be scoped as a dedicated roadmap entry rather than picked up
mid-sprint.

## Decomposition Plan (if multi-session)

Not multi-session. SMALL item, completed in one session.

## What Was Done

Added `Portfolio.run_scenarios(hurdle_rate, scenarios=None, *,
align="strict") -> PortfolioScenarioResult` (ADR-064). The method applies
each `ScenarioAdjustment` uniformly across every deal in the portfolio
— the correlated-stress baseline — and returns a full
`PortfolioResult` per scenario. Each scenario is run on a fresh
`Portfolio` built via the new private helper `_with_scenario`, which
clones every `Deal` (frozen dataclass) replacing only `assumptions` with
a scaled `AssumptionSet`. The original portfolio is not mutated;
`run` after `run_scenarios` reproduces the BASE result bit-for-bit. The
`align` parameter threads through to `Portfolio.run` so calendar-aligned
portfolios (ADR-061 / 062) participate in scenario analysis on the same
grid.

`PortfolioScenarioResult` mirrors the public surface of
`ScenarioResult`: `base_case`, `worst_case`, `irr_range`, and `to_dict`
helpers, with the same `None`-aware semantics (`worst_case` skips
scenarios whose aggregate `total_irr` is suppressed by the ADR-041
reporting guardrail rather than treating them as `-inf`).

`scenario._apply_scenario` was promoted to a public helper
`scenario.apply_scenario_to_assumptions` so `portfolio.py` and the
existing caller in `uq.py` share a single point of truth for the
multiplier semantics — no behaviour change.

Tests cover closed-form identity (BASE matches a direct `Portfolio.run`),
sensitivity (mortality / lapse multipliers move the aggregate in the
expected direction), correlated-stress invariance (every per-deal
profit test moves under +10% mortality, guarding against partial-
stress regressions), portfolio non-mutation, calendar alignment
threading, all four validation paths (empty portfolio / empty scenarios
list / invalid hurdle / invalid align), and the `PortfolioScenarioResult`
helpers via a new `_stub_portfolio_result` builder.

## Files Changed
- `src/polaris_re/analytics/scenario.py` — rename `_apply_scenario` ->
  `apply_scenario_to_assumptions`, public alias added to `__all__`,
  internal caller updated. (~+15 / 0 net behaviour change.)
- `src/polaris_re/analytics/uq.py` — single import + call-site rename.
- `src/polaris_re/analytics/portfolio.py` — `PortfolioScenarioResult`
  dataclass + helpers, `Portfolio.run_scenarios`, `Portfolio._with_scenario`.
  (~+150 lines.)
- `tests/test_analytics/test_portfolio.py` — `TestPortfolioRunScenarios`
  (14 tests), `TestPortfolioScenarioResultHelpers` (8 tests),
  `_stub_portfolio_result` builder. (~+260 lines.)
- `docs/DECISIONS.md` — ADR-064.
- `docs/PRODUCT_DIRECTION_2026-05-23.md` — pruned the shipped
  per-duration solver entry from Promoted Follow-ups (ADR-063, commit
  efd2b58); marked both items in Recommended Next Sprint as shipped
  with their ADR / commit / date.

## Tests Added

`TestPortfolioRunScenarios` (14 tests):
- `test_returns_portfolio_scenario_result` — type contract.
- `test_default_scenarios_match_standard_set` — default scenarios match
  `ScenarioRunner.standard_stress_scenarios()` in order.
- `test_base_scenario_matches_direct_portfolio_run` — closed-form
  identity vs `Portfolio.run()` on PV / aggregate NCF / NAR.
- `test_adverse_mortality_reduces_aggregate_pv_profits` — sensitivity
  sign (coinsurance reinsurer loses under +10% mortality).
- `test_favorable_mortality_increases_aggregate_pv_profits` — symmetric.
- `test_stress_is_correlated_across_deals` — every per-deal PV moves;
  no partial-stress regression.
- `test_run_scenarios_does_not_mutate_portfolio` — `run` after
  `run_scenarios` reproduces BASE.
- `test_run_scenarios_threads_calendar_alignment` — `align="calendar"`
  with mixed inception dates produces stress-direction-correct results.
- `test_run_scenarios_calendar_rejects_mixed_day_of_month` —
  `Portfolio.run` validation propagates.
- `test_empty_scenarios_list_rejected` — explicit empty-list error.
- `test_empty_portfolio_rejected` — inherited.
- `test_invalid_hurdle_rate_rejected` — inherited.
- `test_invalid_align_mode_rejected` — inherited.
- `test_lapse_stress_changes_aggregate_pv` — lapse multiplier reaches
  every deal's projection.

`TestPortfolioScenarioResultHelpers` (8 tests):
- `test_base_case_returns_base_portfolio_result` — present case.
- `test_base_case_returns_none_when_absent` — absent case.
- `test_worst_case_picks_lowest_aggregate_irr` — closed-form pick with
  stubbed IRRs (avoids ADR-041 IRR suppression in the synthetic
  fixture).
- `test_worst_case_skips_none_irrs` — `None` is not treated as `-inf`.
- `test_worst_case_returns_none_when_all_irrs_suppressed`.
- `test_irr_range_is_ordered` — `min <= max` when both present.
- `test_empty_result_helpers_return_none` — empty result.
- `test_to_dict_shape` — JSON shape carries nested `PortfolioResult`.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `Portfolio.run_scenarios` returns aggregate `PortfolioResult` per scenario | OK | `test_returns_portfolio_scenario_result` |
| Default scenarios = `ScenarioRunner.standard_stress_scenarios()` | OK | `test_default_scenarios_match_standard_set` |
| BASE scenario aggregate identical to `Portfolio.run()` | OK | `test_base_scenario_matches_direct_portfolio_run` |
| Mortality / lapse stress moves aggregate in expected direction | OK | `test_adverse_mortality_reduces_aggregate_pv_profits`, `test_favorable_mortality_increases_aggregate_pv_profits`, `test_lapse_stress_changes_aggregate_pv` |
| Stress is uniform (every per-deal PV moves) | OK | `test_stress_is_correlated_across_deals` |
| Original portfolio not mutated | OK | `test_run_scenarios_does_not_mutate_portfolio` |
| `align="calendar"` threads through | OK | `test_run_scenarios_threads_calendar_alignment`, `test_run_scenarios_calendar_rejects_mixed_day_of_month` |
| Validation: empty / invalid inputs raise `PolarisValidationError` | OK | 4 dedicated tests |
| `PortfolioScenarioResult` helpers mirror `ScenarioResult` | OK | 8 helper tests |
| `make test` green (fast + qa) | OK | 1093 + 40 passed |
| Golden regression unchanged | OK | `polaris price` runs cleanly; no QA golden test changed |

## Open Questions / Follow-ups
- **Per-deal scenario overrides.** The open design question from
  CONTINUATION_portfolio_aggregation Refinement Backlog #3 — heterogeneous
  stresses across cedants — is deferred. The conservative correlated
  baseline shipped here is what the deal committee defaults to; the
  heterogeneous case requires a `ScenarioAdjustment`-per-deal contract
  and result-shape changes (likely a `ScenarioAdjustmentMap` keyed by
  `deal_id`). Track as a follow-up: NICE-TO-HAVE (a refinement of the
  correlated baseline, not a deal-blocker).
- **CLI / API surfacing.** `polaris portfolio --scenarios <name1,...>`
  and a `POST /api/v1/portfolio/scenarios` endpoint are NICE-TO-HAVE
  follow-ups. The internal helper is in place; surfacing is mostly
  serialisation work and a CLI flag.
- **Parallel execution.** `run_scenarios` is sequential — same
  constraint as `Portfolio.run` (CONTINUATION_portfolio_aggregation
  Refinement Backlog #6 — Parallel portfolio execution). Wall-clock
  cost is `len(scenarios) × cost(Portfolio.run)`. Out of scope for this
  slice — would benefit `run` first.
- **Dashboard scenario page.** A Streamlit page showing portfolio
  scenario results (PV / IRR / waterfall per scenario) is a NICE-TO-HAVE
  surface follow-up. Same pattern as the existing "Streamlit dashboard
  page for portfolio runs" entry in PRODUCT_DIRECTION.

## Impact on Golden Baselines

None. The change is purely additive at the API level (new method, new
result type). The aggregation pipeline reuses `Portfolio.run`
unchanged, so any `polaris price` or `polaris portfolio` invocation
produces bit-identical output. `dev_check.json` via the golden CLI
input matches main; `tests/qa/test_pipeline_golden.py` passes
unchanged.

## PRUNE log (per routine step 6)

Closed by inspection from PRODUCT_DIRECTION_2026-05-23 Promoted
Follow-ups (IMPORTANT):

- **Per-duration solver in `YRTRateSchedule.generate_table()`** —
  already shipped via ADR-063 (commit efd2b58, PR #50 merged
  2026-06-01). Entry removed from the IMPORTANT block; the
  Recommended Next Sprint annotation updated to reference the shipping
  ADR.
