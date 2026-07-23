# Dev Session Log — 2026-07-23 (experience GAM, Slice 4d-1)

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md (active Tier-A epic A4′) — the
  in-progress feature picked up by routine step 5.
- **Priority:** Tier-A epic (A4′ — Data-Driven Experience Analysis & Assumption-Setting)
- **Title:** Public `all_effects()`/`feature_ranges` + `fitted_glm_arrays()` accessors
  (the two folded-in review items that are the epic-closing Slice 4d's refactor foundation)
- **Slice:** 4d-1 of Slice 4d (4d-1/4d-2/4d-3); Slice 4d was sub-decomposed this session.
- **Branch:** `claude/loving-gauss-tutmj6` (environment-designated `claude/*` branch)

## Selection Rationale
The active epic's CONTINUATION is IN PROGRESS. Slice 4c-3 (PR #153) is **merged** on `main`
(merge commit `e7f341f`), so the next slice is unblocked and is the routine's mandated work before
any fallback pick (step 5b / the always-on-Epic guardrail). No fallback item was considered. No open
PRs (`list_pull_requests state=open` → `[]`), so no draft dependency blocks the next slice.

**Ledger-heal (step 4b):** PR #153 was merged since the last session log but the CONTINUATION
still marked Slice 4c-3 "(draft — awaiting review/merge)"; healed to **MERGED 2026-07-23** (merge
commit `e7f341f`). No other merged-but-uncrossed CONTINUATION entries (`git log origin/main` shows
#153 as the latest merge; #148–#152 were crossed out in prior sessions).

**Why sub-decompose Slice 4d.** As written, Slice 4d bundles four distinct pieces — two
public-accessor refactors (PR #148 option-3, PR #153 `_result` migration), the diagnostic plots, and
the ARCHITECTURE/QUICKSTART docs + epic close — which together are 3+ sessions. Per the routine's
"decompose, don't defer" and the epic's own established sub-decomposition cadence (4b-1/4b-2/4b-3,
4c-1/4c-2/4c-3), Slice 4d was split into 4d-1 (the refactor foundation, this session), 4d-2 (plots),
4d-3 (docs + close). Landing the accessors first de-risks 4d-2: the plots and the dashboard render
straight from the public `all_effects()` frame rather than each re-deriving smooth ranges from cells.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 … 4c-3 | (see CONTINUATION — all merged 2026-07-21..23) | ✅ Done | #141–#153 |
| 4d-1 | Public `all_effects()`/`feature_ranges` + `fitted_glm_arrays()` | ✅ Done (this PR) | #154 |
| 4d-2 | Effect-shape + MI-surface + projection diagnostic plots | ⏳ Next | — |
| 4d-3 | ARCHITECTURE + QUICKSTART docs (CLOSES EPIC) | 🔲 Planned | — |

## Verify Premise (step 7b)
Reproduced both reach-ins before writing code, by reading the shipped code on `main`:
- **PR #148 option-3:** `cli.py::_collect_experience_effects(result, cells, …)` derives each smooth's
  span from the *source cells* (lines 4171–4177), including a special-case for the fit-derived
  `duration_years` (never a cells column). The `GAMFitResult` carried no `feature_ranges`, so a
  second consumer (the 4d dashboard) would have to re-derive spans the same fragile way. Premise holds.
- **PR #153:** `experience_oracle.build_oracle_case` pulled `glm.model.endog`/`.exog`/`.offset` and
  `glm.params` out of the **private** `MISurfaceResult._result` (line 194: `glm = result._result`).
  Premise holds.

Both are genuine private reach-ins a public accessor removes; neither is a no-op.

## What Was Done
Landed the two folded-in review items as a pure-refactor foundation, leaving the engine and goldens
byte-identical:

1. **PR #148 review option-3.** Added `GAMFitResult.feature_ranges: dict[str, tuple[float, float]]`
   (observed `(min, max)` per fitted smooth, keyed like `smooth_features`), captured in
   `ExperienceGAM.fit()` from the modelling frame — the one place `duration_years` exists. Moved the
   CLI's private `_collect_experience_effects(result, cells, …)` onto the model as a public
   `GAMFitResult.all_effects(*, grid_points=50, confidence_level=0.95) -> pl.DataFrame`, sampling each
   smooth over its own `feature_ranges` span. The `experience fit` CLI now calls
   `result.all_effects(...)` and no longer reaches into `cells`; the emitted `--effects-out` CSV is
   byte-identical (the ranges are the same numbers, now sourced from the fit). Removed the dead helper
   and its now-unused `SmoothEffect` type import.

2. **PR #153 review.** Added `FittedGLMArrays` (frozen dataclass: `response`, `design`, `offset`,
   `coefficients`) + `MISurfaceResult.fitted_glm_arrays()`, a public accessor for the exact
   `statsmodels` fit artefacts. `experience_oracle.build_oracle_case` consumes it instead of the
   private `_result` reach-in. Both types exported from `analytics/__init__.py` and `experience_gam`'s
   `__all__`.

ADR-152. Additive/refactor — no pricing path, `Policy`/`CashFlowResult`/`InforceBlock` contract,
treaty, CLI pricing surface, or golden touched.

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` — `GAMFitResult.feature_ranges` field +
  `GAMFitResult.all_effects()`; `feature_ranges` populated in `ExperienceGAM.fit()`; new
  `FittedGLMArrays` dataclass + `MISurfaceResult.fitted_glm_arrays()`; `__all__` += `FittedGLMArrays`.
- `src/polaris_re/analytics/experience_oracle.py` — `build_oracle_case` uses `fitted_glm_arrays()`;
  docstring updated (no private reach-in).
- `src/polaris_re/analytics/__init__.py` — re-export `FittedGLMArrays`.
- `src/polaris_re/cli.py` — `experience fit` calls `result.all_effects(...)`; removed
  `_collect_experience_effects` and the unused `SmoothEffect` TYPE_CHECKING import.
- `tests/test_analytics/test_experience_gam.py` — +4 tests (feature_ranges capture; age-only fit;
  all_effects schema/grid; **byte-identical regression guard** vs the old cells-derived frame).
- `tests/test_analytics/test_experience_mi_surface.py` — +2 tests (fitted_glm_arrays exactness vs
  `_result`; Poisson-optimum identity on the exposed arrays).
- `docs/DECISIONS.md` — ADR-152.
- `docs/CONTINUATION_experience_gam.md` — ledger-heal #153 → MERGED; Slice 4d sub-decomposed into
  4d-1 (DONE) / 4d-2 (NEXT) / 4d-3 (PLANNED).
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — struck through the PR #148 option-3 promoted item
  (SHIPPED footer, audit trail preserved).
- `docs/DEV_SESSION_LOG_2026-07-23_experience_gam_slice4d1.md` — this log.

## Tests Added
`tests/test_analytics/test_experience_gam.py` (+4):
- `test_feature_ranges_captured_at_fit`: ranges keyed like `smooth_features`; `attained_age` matches
  cells; fit-derived `duration_years` span correct though absent from cells.
- `test_feature_ranges_age_only_fit`: no varying duration ⇒ only `attained_age` carries a range.
- `test_all_effects_tidy_schema_and_grid`: exact column list; each smooth block spans exactly its
  `feature_ranges` at `grid_points`; one row per factor level with null `x_value`; bands bracket.
- `test_all_effects_matches_legacy_cells_derived_frame`: **regression guard** — reproduces the old
  `_collect_experience_effects` (cells-derived spans) and asserts `all_effects` equals it at `atol=0`
  on every numeric column, so `--effects-out` is byte-identical after the refactor.

`tests/test_analytics/test_experience_mi_surface.py` (+2):
- `test_fitted_glm_arrays_exposes_exact_fit_state`: arrays equal `_result.model.endog/.exog/.offset`
  + `params` (`assert_array_equal`), consistent shapes, all `float64`.
- `test_fitted_glm_arrays_sits_at_poisson_optimum`: `||Xᵀ(y−μ)||∞` at the fitted coefficients is
  near zero — the property the mgcv oracle relies on.

## Acceptance Criteria
| Criterion (CONTINUATION Slice 4d-1) | Status | Notes |
|-------------------------------------|--------|-------|
| `GAMFitResult.feature_ranges` captured at fit time, keyed like `smooth_features` | ✅ | populated in `fit()` from the modelling frame |
| Public `GAMFitResult.all_effects(...)`; CLI drops `_collect_experience_effects`/`cells` reach-back | ✅ | CLI calls `result.all_effects(...)`; helper removed |
| `--effects-out` byte-identical after refactor | ✅ | regression-guarded at `atol=0` + CLI test `test_fit_effects_out_recovers_factor_multiplier` green |
| Public `MISurfaceResult.fitted_glm_arrays()`; oracle drops `_result` reach-in | ✅ | `FittedGLMArrays` + accessor; oracle consumes it; oracle tests green |
| Engine/goldens byte-identical (no golden change) | ✅ | golden `polaris price` exit 0, unchanged; QA suite green |

Targeted analytics suites (`test_experience_gam` + `test_experience_mi_surface` +
`test_experience_oracle`): **48 passed, 2 skipped** (the 2 `mgcv` opt-in cases). CLI experience:
18 passed. QA suite: 76 passed. ruff format + check clean. Golden `polaris price` regen check:
exit 0, unchanged.

## Open Questions / Follow-ups
- None new. The refactor is a clean consolidation; no discoveries (step 11b) were made. The
  remaining epic work (4d-2 plots, 4d-3 docs + close) is tracked as the active epic's own next
  slices in the CONTINUATION, not as loose follow-ups.

## Parked Polish
None.

## Impact on Golden Baselines
None. Additive/refactor only — no pricing path, assumption/data contract, treaty, or CLI pricing
surface touched. Baseline `make test` at session start: **2428 passed, 3 skipped, 112 deselected,
0 failures** — matches the recorded post-4c-3 baseline (2419 + 9 from PR #153); tolerance-aware, no
new/changed failures (VBT/CSO tables OK; CIA 2014 MISSING but tests handle it, the standing
baseline). After this slice: **+6 runnable tests** (full non-slow suite: 2434 passed, 3 skipped,
112 deselected, 0 failures).

## Ledger / Housekeeping Note
`PRODUCT_DIRECTION_2026-06-18.md` is now **35 days old (>30)**. Consistent with the prior slices
(#142–#153), this session's ledger touch was a **PRUNE** (strike-through of the now-shipped PR #148
option-3 item) on the existing file rather than opening a new one, to avoid fragmenting the active
epic's harvest trail while the epic is mid-flight (only 4d-2/4d-3 remain). This session's HARVEST
(step 17) surfaced **nothing new to promote**: the only ADR-152 out-of-scope items are the active
epic's own tracked next slices (4d-2/4d-3) plus items already harvested at 4c-2/4c-3 (the ILEC
diligence run and the dev-box `rpy2`/`mgcv` glue run). A full `PRODUCT_DIRECTION` regeneration
(list-shipped-since #69..#153, carry-forward unresolved, then harvest) remains **overdue and flagged
for the next run** — a substantial standalone task the routine says should be a session's sole
deliverable when it cannot fit beside a slice. `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is 8 days
old — fresh, no re-rank needed. **Recommendation:** the next run should either ship Slice 4d-2 (once
this PR merges) or take the overdue PRODUCT_DIRECTION regeneration as its deliverable.
