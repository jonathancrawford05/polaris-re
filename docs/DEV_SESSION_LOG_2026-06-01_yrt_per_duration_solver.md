# Dev Session Log — 2026-06-01

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-05-23.md
- **Priority:** IMPORTANT (Promoted Follow-ups section)
- **Title:** Per-duration solver in `YRTRateSchedule.generate_table()`
- **Slice:** complete (SMALL — single session)

## Selection Rationale

All six `docs/CONTINUATION_*.md` files are COMPLETE — no multi-session
work was in progress to continue.

PRODUCT_DIRECTION_2026-05-23.md has no BLOCKERs remaining. Among the
IMPORTANT items, the recommended next sprint named:

1. Per-duration solver in `YRTRateSchedule.generate_table()` (3 days,
   IMPORTANT) — the storage contract (`solved_mask`) and renderers are
   already in place; this lights them up.
2. `Portfolio.run_scenarios` (IMPORTANT) — broader scope.

Selected #1 because the spec explicitly notes that "CLI / Excel / JSON /
dashboard renderers already consume the 2-D solved_mask, so this lands
without surface changes" — i.e. it is genuinely self-contained at the
storage contract. After sizing (2 files touched, ~250 lines, no
contract change) the item classifies as SMALL, so I implemented it
fully in this session rather than creating a CONTINUATION.

The other listed IMPORTANT items (Reserve-basis matching, IFRS 17
movement table, Portfolio.run_scenarios, LICAT lapse/morbidity-risk)
are all multi-session and the PRODUCT_DIRECTION explicitly says they
"should be scoped as a dedicated roadmap entry rather than picked up
mid-sprint."

## Decomposition Plan (if multi-session)

Not multi-session. SMALL item, completed in one session.

## What Was Done

Added `solve_mode: Literal["flat", "per_duration"] = "flat"` to
`YRTRateSchedule.generate_table()`. The default `"flat"` mode is the
prior contract — solve one flat rate per `(age, sex, smoker)` row and
broadcast across every duration column, producing a row-uniform
`solved_mask`. The new `"per_duration"` mode solves a separate rate per
`(age, duration)` cell by projecting a synthetic policy that has been
inforce for `d` years at the row's issue age (`duration_inforce = d*12`
months, `attained_age = age + d`, `issue_date` shifted back `d` years).
The mortality lookup then picks up at column `d` of the select-period
table, giving the actuarially correct "rate quoted today for a policy at
duration d" semantics. `solved_mask` becomes a genuinely 2-D per-cell
map — True only for cells that were directly solved at requested ages.

Refactored the post-solve fill / pack code into a shared
`_fill_and_pack_cohorts` helper used by both modes. Column-wise forward/
back-fill in per-duration mode runs independently per duration column;
the global cohort mean is the last-resort fill for cohorts where no cell
solved (same fallback as the flat mode). At `select_period_years = 0`
the two modes collapse to the same single-column solve and produce
numerically identical rates (closed-form equivalence test).

Renderers — CLI text table (`src/polaris_re/cli.py`), Excel exporter
(`src/polaris_re/utils/excel_output.py`), dashboard heatmap
(`src/polaris_re/dashboard/components/yrt_rate_table.py`) — already loop
over the 2-D `solved_mask` per ADR-054 and required no changes. Per the
golden regression check below, no pricing-output baselines change.

## Files Changed
- `src/polaris_re/analytics/rate_schedule.py` (+~150 / -~50 lines)
- `tests/test_analytics/test_rate_schedule.py` (+~170 lines)
- `docs/DECISIONS.md` (+ADR-063)

## Tests Added
`TestGenerateTablePerDuration` (7 tests):
- `test_per_duration_yields_distinct_rates_across_columns` — confirms
  per-duration rates are not row-uniform.
- `test_per_duration_rates_increase_within_select_period` — closed-form
  check on the synthetic select fixture: rates rise monotonically with
  duration and the ultimate rate strictly exceeds the duration-0 rate.
- `test_per_duration_dense_grid_is_fully_solved` — 2-D all-True
  `solved_mask` on a dense grid.
- `test_per_duration_sparse_ages_mark_only_solved_cells` — sparse age
  input: only requested-age rows are True across every column; filled
  rows are False across every column.
- `test_per_duration_select_period_zero_matches_flat` — closed-form
  equivalence to flat mode at `select_period_years=0` (rtol=1e-3).
- `test_per_duration_round_trips_through_treaty` — generated table
  flows back through `YRTTreaty.apply()` with finite cash flows and
  non-zero ceded premium.
- `test_invalid_solve_mode_raises` — unknown `solve_mode` rejected up
  front with `PolarisValidationError` (no silent fallback).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Per-duration solver produces a 2-D `solved_mask` | OK | `test_per_duration_sparse_ages_mark_only_solved_cells` |
| Storage contract unchanged (`YRTRateTableArray` shape and key) | OK | Renderers loop over 2-D mask; no CLI/Excel/JSON/dashboard changes needed |
| Existing flat-mode contract preserved | OK | `TestGenerateTableSolvedMask` (3 tests) untouched and passing |
| Round-trip through `YRTTreaty.apply()` works | OK | `test_per_duration_round_trips_through_treaty` |
| `make test` green (fast + qa) | OK | 1071 + 40 = 1111 passed |
| Golden regression unchanged | OK | `polaris price` output bit-identical to main |

## Open Questions / Follow-ups
- **CLI surfacing.** The internal helper now supports `solve_mode`;
  surfacing through `polaris rate-schedule --table` is a NICE-TO-HAVE
  follow-up. The CLI currently always calls `generate_table()` with no
  `solve_mode` (i.e. flat). A `--solve-mode {flat,per_duration}` flag
  would be a single-day add.
- **Cell-failure interpolation.** Column-wise forward/back-fill is the
  current fallback for cells where brentq fails. A richer interpolator
  (e.g. linear across the duration axis for an interior column failure)
  would be a quality improvement but is not needed for the dense-grid
  case the test suite covers.
- **Warm-start `brentq`.** Per-duration mode runs the solver
  `select_period_years + 1` times per `(age, sex, smoker)`. Warm-
  starting from the adjacent column's solution would cut wall-clock
  cost meaningfully on long select periods; not implemented.

## Impact on Golden Baselines

None. The change is additive (new parameter with a default that
preserves prior behaviour); the golden regression suite calls
`polaris price`, not `polaris rate-schedule`, and the flat-mode default
through `generate_table()` is bit-identical to main. `/tmp/dev_check.json`
output matches the prior baseline.
