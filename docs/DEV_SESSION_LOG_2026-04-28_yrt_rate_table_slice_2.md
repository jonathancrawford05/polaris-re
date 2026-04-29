# Dev Session Log — 2026-04-28

## Item Selected
- **Source:** `docs/CONTINUATION_yrt_rate_table.md` (in-progress
  multi-session feature originally selected from
  `docs/PRODUCT_DIRECTION_2026-04-19.md`)
- **Priority:** IMPORTANT (last item in the IMPORTANT list,
  "YRT rate schedule by age × duration")
- **Title:** Tabular YRT rate schedule — Slice 2 of 3 (wire
  `YRTRateTable` into `YRTTreaty.apply()`)
- **Slice:** 2 of 3

## Selection Rationale

CONTINUATION file existed and was IN PROGRESS. Slice 1 PR #36 was
merged into `main` (`173b0cc Merge pull request #36 from
jonathancrawford05/claude/lucid-hawking-FDgDd`), so the routine's
"continue on a new branch from main" branch matched the
session-designated branch `claude/lucid-hawking-YY49U`. No other
CONTINUATION files were IN PROGRESS, so this was the only candidate
for continuation. Slice 2 is the next step in the CONTINUATION's
"Decomposition" section.

## Decomposition Plan

| Slice | Scope                                                           | Status        | PR  |
|-------|-----------------------------------------------------------------|---------------|-----|
| 1     | Standalone `YRTRateTable` data model (ADR-050)                  | ✅ Done       | #36 |
| 2     | Wire `YRTRateTable` into `YRTTreaty.apply()` + generator helper | ✅ Done (this) | TBD |
| 3     | CLI / API / Excel / dashboard surfacing + CSV loader            | 🔲 Planned    | —   |

## What Was Done

Added a new `yrt_rate_table: YRTRateTable | None` field on
`YRTTreaty`, with a Pydantic `model_validator` that raises
`PolarisValidationError` when both `flat_yrt_rate_per_1000` and
`yrt_rate_table` are set (the mutual-exclusion decision RESOLVED in
PR #36 review). When `yrt_rate_table` is set, `apply()` requires an
`InforceBlock` argument; absent one, it raises
`PolarisComputationError`.

The tabular consumption logic lives in two new helper methods.
`_compute_tabular_premiums` builds a per-policy rate matrix
`R[i, t]` by iterating once per (sex, smoker) cohort (the same
pattern `TermLife._build_rate_arrays` uses), then dispatches to
`_tabular_premiums_seriatim` when `gross.seriatim_lx` and
`gross.seriatim_reserves` are populated, otherwise to
`_tabular_premiums_aggregate`. The seriatim path computes
`prem[i, t] = lx[i, t] * max(face[i] - V[i, t], 0) * R[i, t] / 12 /
1000 * cession[i]` and sums across policies, with per-policy
effective cession respecting policy-level overrides
(`InforceBlock.effective_cession_vec`). The aggregate fallback
face-weight-averages per-policy rates and applies them to the
existing aggregate-runoff NAR. Both paths preserve the
`net + ceded == gross` invariant.

`YRTRateSchedule.generate_table(...)` was added as a closed-loop
sanity check: solve the existing per-(age, sex, smoker) flat rate
via brentq for each cell, then pack into a `YRTRateTable` with
rates broadcast across the requested select columns. A real
per-duration solver and CSV ingest live in Slice 3.

The flat-rate path was preserved byte-identically (refactored into
`_compute_flat_premiums`, which still produces the same arrays as
the previous inline implementation). All 33 QA tests pass —
including `TestGoldenYRT::test_yrt_golden_regression` and
`TestGoldenFlat::test_flat_golden_regression` — confirming no
regression on the existing golden runs.

## Files Changed

- `src/polaris_re/reinsurance/yrt.py` — new `yrt_rate_table` field,
  mutual-exclusion validator, refactor of premium calc into
  `_compute_flat_premiums` / `_compute_tabular_premiums` /
  `_tabular_premiums_seriatim` / `_tabular_premiums_aggregate`.
- `src/polaris_re/analytics/rate_schedule.py` — new
  `YRTRateSchedule.generate_table(...)` method.
- `docs/DECISIONS.md` — ADR-051 added.
- `docs/CONTINUATION_yrt_rate_table.md` — Slice 2 marked DONE,
  decision points and Slice 3 hand-off context recorded.

## Tests Added

- `tests/test_reinsurance/test_yrt_tabular.py` — 12 new tests:
  - `TestYRTTreatyValidation` (5)
  - `TestFlatPathUnchanged` (1)
  - `TestConstantTableMatchesFlat` (2)
  - `TestAgingBlockRisesWithAge` (2)
  - `TestSeriatimVsAggregateFallback` (1)
  - `TestMultiPolicyMixedCohort` (1)
- `tests/test_analytics/test_rate_schedule.py` — 2 new tests
  (`TestGenerateTable`).

Total: 14 new tests; full non-slow suite 845 → 847 (Slice 1 left
the count at 833 in the pre-`make test` baseline; my baseline was
also 833, then +12 tabular + +2 generate = 847).

## Acceptance Criteria

| Criterion                                                                         | Status | Notes |
|-----------------------------------------------------------------------------------|--------|-------|
| `YRTTreaty(..., yrt_rate_table=t).apply(gross, inforce)` returns valid (net, ceded) | ✅ | `TestConstantTableMatchesFlat` + `TestAgingBlockRisesWithAge` |
| Aging table fixes the PRODUCT_DIRECTION declining-premium concern                 | ✅ | aging vs flat-counterfactual + implied-rate monotonicity tests |
| Constant-rate table reproduces flat-rate output within float tolerance            | ✅ | `test_ceded_premiums_match_flat`, rtol=1e-6 |
| `net + ceded == gross` for premiums and claims under tabular rates                | ✅ | `test_ncf_additivity_preserved` + fallback-path additivity |
| Mutual exclusion enforced at construction                                         | ✅ | `test_both_flat_and_table_raises` |
| Tabular path requires `InforceBlock`                                              | ✅ | `test_table_without_inforce_raises` |
| Existing QA goldens unchanged                                                     | ✅ | `TestGoldenYRT` + `TestGoldenFlat` pass; CLI dev-check ran cleanly |
| `YRTRateSchedule.generate_table(...)` round-trips through treaty                  | ✅ | `test_generate_table_round_trips_through_treaty` |
| ADR-051 written                                                                   | ✅ | `docs/DECISIONS.md` |

## Open Questions / Follow-ups

- Slice 3 should decide whether `polaris price --yrt-rate-table` forces
  `seriatim=True` on the projection (so the per-policy path is always
  taken when a table is supplied). The aggregate fallback exists for
  back-compat with `YRTRateSchedule._solve_rate` but is documented as
  degraded; a CLI flag that defeats it would close the loop on the
  PRODUCT_DIRECTION concern.
- `generate_table()` currently broadcasts the per-age flat rate across
  every duration column. Slice 3 should add a real per-duration solver
  (or document explicitly that the duration variation comes from the
  CSV-loaded production tables, not from a generator).
- The CONTINUATION file's Open Question 3 (CSV format — one file per
  (sex, smoker) vs. a single multi-key CSV) and Open Question 4
  (default axis grid for `generate_table`) are deferred to Slice 3's
  ADR-052.

## Impact on Golden Baselines

None. The flat-rate path is byte-identical to the pre-Slice-2
implementation (refactor only); the tabular branch is opt-in via the
new field which no existing golden config sets. `TestGoldenYRT` and
`TestGoldenFlat` both pass against the existing baselines, and the
explicit `polaris price` CLI run on `golden_config_flat.json` and
`golden_config_yrt.json` produced the expected headline metrics
(Cedant PV ≈ $3.51M flat / -$1.43M YRT, Reinsurer PV ≈ $45K /
-$4.41M).
