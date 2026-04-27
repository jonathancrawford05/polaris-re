# Dev Session Log — 2026-04-27

## Item Selected

- **Source:** PRODUCT_DIRECTION_2026-04-19.md
- **Priority:** IMPORTANT (last item under "IMPORTANT" — "YRT rate
  schedule by age × duration")
- **Title:** Tabular YRT rate schedule (age × sex × smoker × duration)
- **Slice:** 1 of 3 (data model first; "data-model-first, then
  consumers" decomposition pattern)

## Selection Rationale

All three previously-active CONTINUATION features were verified
COMPLETE before selecting new work:

- `CONTINUATION_substandard_rating.md` — COMPLETE (slices 1-3 merged
  via PRs #28-#30)
- `CONTINUATION_deal_pricing_excel.md` — COMPLETE (slices 1-2 merged
  via PRs #31-#32)
- `CONTINUATION_licat_capital.md` — COMPLETE (slices 1-3 merged via
  PRs #33-#35)

`gh pr list --state open` (via `mcp__github__list_pull_requests`)
returned an empty list, confirming no in-flight work.

Within the IMPORTANT tier of PRODUCT_DIRECTION_2026-04-19, the
candidates ranked by self-containedness × clarity-of-scope ×
testability:

| Item | Scope | Class | Why selected / not |
|---|---|---|---|
| YRT rate schedule by age × duration | ~4 days | MEDIUM | **Selected.** Cleanly additive — extends an existing module with a new optional field. PRODUCT_DIRECTION explicitly calls out the WL YRT shape limitation that this fixes. Decomposes naturally into 3 slices with a zero-risk "data model first" Slice 1. |
| Reserve basis matching | ~10 days | LARGE | Skipped — touches `core/projection.py` and all four product engines. Cross-cutting contract change with high regression risk. |
| Portfolio aggregation | ~5 days | MEDIUM/LARGE | Skipped — Roadmap 5.2; less commercially urgent than fixing tabular YRT, which the deal-committee shape review explicitly flagged as a current understatement of reinsurer cost. |
| IFRS 17 movement table | ~10 days | LARGE | Skipped — Roadmap 5.3; large multi-session scope; better tackled after a smaller IMPORTANT item lands. |
| Reporting guardrails on ProfitTester | (already done) | — | Closed by ADR-041 / commit `31f6ca8`. |

The remaining BLOCKERs from PRODUCT_DIRECTION_2026-04-19 (WL expense
fix, substandard rating, deal-pricing Excel, LICAT capital) are all
shipped — see `git log`.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Standalone `YRTRateTable` + `YRTRateTableArray` data model + tests + ADR-050 | DONE | (this PR — to be opened as draft) |
| 2 | Wire `yrt_rate_table` field into `YRTTreaty.apply()`; per-(sex, smoker) cohort lookup; backward-compat with flat-rate path; extend `YRTRateSchedule` to solve tabular grids | NEXT | — |
| 3 | CSV loader (`load_yrt_rate_csv`, `YRTRateTable.load`); CLI `--yrt-rate-table`; API field; Excel `YRT Rate Table` sheet; dashboard upload + heatmap | PLANNED | — |

The decomposition pattern is "data model first, then consumers" — see
`CONTINUATION_yrt_rate_table.md` for the detailed handoff to Slice 2.

## What Was Done

Added a standalone `YRTRateTable` data model that mirrors the
`MortalityTable` storage and lookup contract but stores annual YRT
rates per `$1,000` NAR rather than mortality probabilities. The
storage class `YRTRateTableArray` is a small parallel of
`MortalityTableArray` — same 2-D `[age - min_age, min(duration_years,
select_period)]` indexing, same `(n_ages, select_period + 1)` shape,
same vectorised lookup contract — but it does **not** validate rates
in `[0, 1]` because YRT rates routinely exceed `$50/$1,000` at
advanced ages. The Pydantic wrapper `YRTRateTable` keys arrays by
`f"{sex.value}_{smoker.value}"` (matching the mortality convention)
and falls back to the aggregate `UNKNOWN` smoker key when a
smoker-specific array is absent.

The slice is intentionally pure-additive: only
`reinsurance/__init__.py` is modified (to re-export the two new
symbols). `YRTTreaty` is unchanged — wiring the new field
`yrt_rate_table: YRTRateTable | None = None` into the treaty would
have shipped a half-finished implementation in this session and is
deferred to Slice 2 alongside the consumption logic.

ADR-050 records the design choices and explicitly enumerates what is
out of scope so Slice 2 can pick up cleanly. The
`CONTINUATION_yrt_rate_table.md` file carries the full multi-session
plan including open questions for Slice 2 (per-policy seriatim vs
aggregate-runoff for tabular consumption; precedence between
`flat_yrt_rate_per_1000` and `yrt_rate_table` when both are set).

## Files Changed

- **Added:** `src/polaris_re/reinsurance/yrt_rate_table.py` — new
  module with `YRTRateTable` (Pydantic frozen) and `YRTRateTableArray`
  (storage class).
- **Modified:** `src/polaris_re/reinsurance/__init__.py` — re-export
  `YRTRateTable` and `YRTRateTableArray`; alphabetised `__all__`.
- **Added:** `tests/test_reinsurance/test_yrt_rate_table.py` — 34
  tests across 5 classes.
- **Modified:** `docs/DECISIONS.md` — appended ADR-050.
- **Added:** `docs/CONTINUATION_yrt_rate_table.md` — multi-session
  decomposition plan with Slice 2 / Slice 3 scope, key decisions, and
  open questions.
- **Added:** `docs/DEV_SESSION_LOG_2026-04-27_yrt_rate_table_slice_1.md`
  — this file.

## Tests Added

`tests/test_reinsurance/test_yrt_rate_table.py`:

- `TestYRTRateTableArrayConstruction` (8) — construction validation:
  float64 rates, int promotion, non-2D rejection, age-range mismatch,
  select-period mismatch, negative-rate rejection, NaN rejection,
  large-rate (`> 1`) acceptance.
- `TestYRTRateTableArrayLookup` (11) — scalar known-cell, ultimate-
  column clamp, age out-of-range (below/above), negative duration,
  vector shape/dtype, vector values match scalar, vector duration
  clamp, vector shape mismatch, vector age out-of-range, vector
  negative duration.
- `TestYRTRateTableConstruction` (6) — smoker-distinct, aggregate-
  only, empty raises, age-range inconsistency across arrays,
  select-period inconsistency, frozen-after-construction (Pydantic
  `ValidationError`).
- `TestYRTRateTableLookup` (7) — scalar smoker-vs-non-smoker
  closed-form, smoker-rate strictly > non-smoker rate at every cell,
  vector shape/dtype, smoker fallback to aggregate, missing-sex
  raises, age-monotone increase, duration-monotone increase through
  select period.
- `TestPublicExports` (2) — `YRTRateTable` and `YRTRateTableArray`
  importable from `polaris_re.reinsurance`.

Full suite: 827 non-slow tests pass (up from 793, +34 new). QA suite
33/33 pass. Ruff format + check both clean. Slow tests not run (gated
behind `@pytest.mark.slow` per CLAUDE.md).

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| New module importable as `from polaris_re.reinsurance import YRTRateTable, YRTRateTableArray` | ✅ | `TestPublicExports` |
| Closed-form scalar lookup matches `base_rate + age_slope*i + duration_slope*j` formula | ✅ | `test_scalar_lookup_known_cell` |
| Vector lookup matches scalar lookup element-wise | ✅ | `test_vector_lookup_values_match_scalar` |
| Smoker rates > non-smoker rates at every cell (economic invariant) | ✅ | `test_smoker_higher_than_non_smoker` |
| Duration beyond `select_period` clamps to ultimate | ✅ | `test_duration_beyond_select_period_uses_ultimate`, `test_vector_lookup_clamps_duration_at_select_period` |
| Smoker-specific lookup falls back to aggregate (`UNKNOWN`) | ✅ | `test_smoker_specific_falls_back_to_aggregate_when_absent` |
| Negative / NaN / inconsistent-shape inputs raise `PolarisValidationError` | ✅ | 7 negative-path tests across construction & lookup |
| Existing 793 non-slow tests still pass (purely additive slice) | ✅ | Suite now 827 non-slow, 33/33 QA |
| Golden baselines unchanged | ✅ | No existing pricing path consumes the new module; `TestGoldenFlat` / `TestGoldenYRT` both pass |
| ADR-050 written | ✅ | `docs/DECISIONS.md` |

## Open Questions / Follow-ups

Captured in `CONTINUATION_yrt_rate_table.md` § "Open Questions" — all
four are Slice 2 design decisions (not blockers for this slice):

1. Per-policy seriatim vs aggregate-runoff approximation for tabular
   consumption.
2. Precedence when both `flat_yrt_rate_per_1000` and
   `yrt_rate_table` are set on the same treaty.
3. CSV format choice for Slice 3 (one file per (sex, smoker) vs
   single multi-column).
4. Default age × duration grid for `YRTRateSchedule.generate_table`.

## Impact on Golden Baselines

**None.** Slice 1 adds a new module with no consumers in the existing
pricing pipeline. `TestGoldenFlat` and `TestGoldenYRT` remain green
without regeneration.
