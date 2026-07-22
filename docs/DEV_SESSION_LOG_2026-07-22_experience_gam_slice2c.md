# Dev Session Log — 2026-07-22 (Slice 2c — CUSTOM improvement-scale emission)

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b),
  backing docs/CONTINUATION_experience_gam.md (IN PROGRESS)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 2c:
  `MortalityImprovement`-compatible custom-scale emission (`ImprovementScale.CUSTOM` /
  `from_grid`). Closes the Slice-2 HEADLINE (2a/2b/2c).
- **Slice:** 2c of the Slice-2 HEADLINE (Slice 2 now complete)
- **Branch:** `claude/loving-gauss-vvdlm3` (environment-designated; overrides the
  `feat/auto-*` default per step 8)

## Selection Rationale
Step 5 found the active epic's CONTINUATION (`experience_gam`) IN PROGRESS. Ledger-healed
(step 4b): Slice 2b-projection's **PR #144 confirmed merged** into `main` (git log shows
merge commit `7961e4e`) — the CONTINUATION's "draft — awaiting review/merge" marker was
stale because the routine never merges its own PRs. Recorded `#144 — MERGED 2026-07-22`.
Cross-checked #141/#142/#143 (all already recorded merged); no other stale entries. No
open PRs.

With Slice 2b merged, the epic's next unchecked slice (Slice 2c) is unblocked, so per the
ACTIVE-EPIC guardrail it is advanced before any fallback pick. No fallback item selected.
Slice 2c is the natural next step: 2a/2b produced the fitted/projected `MI_x(y)` grid but
it was a terminal analytics artefact — 2c makes it consumable by the pricing engine.

## Verify Premise (step 7b)
Confirmed the gap with own eyes before coding: `ImprovementScale` had only
`SCALE_AA/MP_2020/CPM_B/NONE` (no `CUSTOM`), and `MISurface`/`MIProjection` had no
emission method — there was no path from an experience-fitted improvement grid to a
`MortalityImprovement`. Premise holds.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + static-base offset + additive A/E GAM + export | ✅ Done | #141 (merged) |
| 2a | Frequentist tensor `te(x,t)` surface + `MI_x(y)` grid + delta-method band | ✅ Done | #142 (merged) |
| 2b-surface | Bayesian reduced-rank-GP MI surface + posterior credible intervals | ✅ Done | #143 (merged) |
| 2b-projection | CMI/MP-style mean-reverting posterior-predictive MI projection | ✅ Done | #144 (merged) |
| 2c | `MortalityImprovement` CUSTOM scale (`from_grid` / `to_mortality_improvement`) | ✅ Done | #145 (draft) |
| 3 | Hierarchical partial pooling (credibility shrinkage) | ⏳ Next | — |
| 4 | CLI + assumption versioning + validation decks/loaders + docs (CLOSES EPIC) | 🔲 Planned | — |

## What Was Done
Added a data-driven improvement scale to `assumptions/improvement.py`: a new
`ImprovementScale.CUSTOM` and four backward-compatible optional fields on
`MortalityImprovement` (`custom_ages`, `custom_years`, `custom_mi_grid`,
`custom_ultimate_rate`) that hold an attained-age × calendar-year `MI_x(y)` grid. The
fields default to `None`/`0.0`, so the four built-in scales and every existing caller are
byte-unchanged; a `@model_validator(mode="after")` enforces the CUSTOM contract (grid
present iff scale is CUSTOM, consistent shapes, strictly-increasing contiguous age/year
axes, and `base_year == custom_years[0] − 1`).

A `MortalityImprovement.from_grid(ages, years, mi_grid, ultimate_rate=0.0)` classmethod
builds the scale (`base_year = years[0] − 1`, the anchor whose mortality the grid improves
forward). `apply_improvement` gains a CUSTOM branch that accumulates
`q(Y) = q(base) · Π_{Z=base+1}^{Y} (1 − MI_x(Z))` — the same year-by-year product form as
MP_2020 — clamping attained ages to the grid edges and using `custom_ultimate_rate` for
step-end years beyond the grid. The grid is stored as immutable nested tuples so the frozen
model stays hashable and the scale round-trips through JSON (the representation Slice-4
assumption-versioning needs).

Two thin analytics hand-offs — `MISurface.to_mortality_improvement` and
`MIProjection.to_mortality_improvement` — call `from_grid`. `improvement.py` gains no
`analytics` import (the analytics dataclasses depend on assumptions, not vice-versa),
preserving the core layering. The projection default `ultimate_rate = long_term_rate`, so
pricing past the horizon continues the deterministic long-term assumption. The emitted
CUSTOM scale reproduces the dataclass's own `cumulative_factor()` exactly — the acceptance
identity `apply_improvement(q, ages, years[k]) == q · cumulative_factor()[:, k]`. ADR-143.

## Files Changed
- `src/polaris_re/assumptions/improvement.py` — `CUSTOM` enum, custom-grid fields +
  validator, `from_grid`, CUSTOM branch in `apply_improvement`, `_custom_improvement_product`
  helper, docstrings.
- `src/polaris_re/analytics/experience_gam.py` — `MortalityImprovement` import;
  `MISurface.to_mortality_improvement`; `MIProjection.to_mortality_improvement`.
- `docs/DECISIONS.md` — ADR-143.
- `docs/CONTINUATION_experience_gam.md` — ledger-heal (#144 merged); Slice 2c → DONE;
  Slice 3 → NEXT.
- `docs/PLAN_experience_gam.md` — Slice 2c shipped; Slice 2 complete; Slice 3 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — two harvested NICE-TO-HAVE follow-ups.

## Tests Added
- `tests/test_assumptions/test_improvement.py` — `TestMortalityImprovementCustom`
  (closed-form uniform grid, partial horizon, age-varying grid, ultimate-rate beyond grid,
  age clamping, zero-years copy, [0,1] clip, rate sensitivity ×4, JSON round-trip) +
  `TestMortalityImprovementCustomValidation` (7 guard cases).
- `tests/test_analytics/test_experience_mi_custom_scale.py` — round-trip identity vs
  `cumulative_factor` (projection & surface), ultimate-rate default = long_term_rate,
  ultimate=0 freeze, and two end-to-end fit→project→emit tests.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `ImprovementScale.CUSTOM` + from-grid constructor | ✅ | `MortalityImprovement.from_grid` |
| Emitted scale plugs into `apply_improvement` | ✅ | CUSTOM branch; `q(Y)=q(base)·Π(1−MI)` |
| Reproduces `cumulative_factor()` exactly | ✅ | `apply(...years[k]) == q·factor[:,k]`, rtol 1e-12 |
| Backward-compatible (defaults, no golden change) | ✅ | 2295 passed (was 2268); goldens byte-identical |
| Surface & projection hand-offs | ✅ | `to_mortality_improvement` on both dataclasses |
| Contract validation | ✅ | 7 guard tests (shape/contiguity/base_year/scale) |

## Open Questions / Follow-ups
- **CUSTOM surfacing (Slice 4).** Wiring `ImprovementScale.CUSTOM` into the CLI/dashboard
  `--config` schema + an `AssumptionSet` selector, and persisting/loading a CUSTOM scale
  under `data/assumption_versions/`, are Slice-4 scope — the tuple/JSON representation was
  chosen to make the versioning trivial. Not harvested separately (already epic-tracked).
- **Two ADR-143 out-of-scope items harvested** to PRODUCT_DIRECTION_2026-06-18 (NICE-TO-HAVE,
  1st-order): per-duration (select/ultimate) CUSTOM grids; carrying the credible band into a
  stochastic CUSTOM scale.
- **PRODUCT_DIRECTION freshness.** The latest direction file (2026-06-18) is ~34 days old
  (> the 30-day step-17 threshold). Following the immediately-prior session's precedent
  (DEV_SESSION_LOG_2026-07-22_…_projection), I appended the genuine follow-ups to its
  Promoted Follow-ups section rather than spending this session regenerating the file — a
  full COMMERCIAL_VIABILITY_REVIEW + PRODUCT_DIRECTION regeneration is its own session
  (step 6 wall-clock guardrail) and the active-epic slice is the higher-value deliverable.
  Flagged so the next run can regenerate if it has the capacity.

## Parked Polish
None. (Both harvested items are 1st-order follow-ups of the planned Slice-2c emission, so
they were promoted normally as NICE-TO-HAVE — neither is 3rd-order-or-deeper.)

## Impact on Golden Baselines
None. The change is additive and the CUSTOM scale is only reachable when a caller
explicitly constructs one; no pricing path or existing assumption is touched. The golden
CLI regression (`tests/qa`) and the full suite pass unchanged (2295 passed, 3 skipped, 110
deselected, 0 failures; baseline was 2268 passed → +27 new tests, no regressions).

## Baseline
Pre-change (fresh checkout of `origin/main` @ `7961e4e`, after the step-2 pymort convert
left the 4 CIA tables MISSING as usual): **2268 passed, 3 skipped, 110 deselected**, 0
failures — matches the recorded Slice-2b-projection post-slice baseline, so no NEW/CHANGED
failures; proceeded. After this slice: **2295 passed, 3 skipped, 110 deselected**, 0
failures (+27 = the new CUSTOM-scale and hand-off tests).
