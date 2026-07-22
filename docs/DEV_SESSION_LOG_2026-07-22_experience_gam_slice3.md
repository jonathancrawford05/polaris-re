# Dev Session Log — 2026-07-22 (experience GAM, Slice 3)

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md (active Tier-A epic A4′) — the
  in-progress feature picked up by routine step 5.
- **Priority:** Tier-A epic (A4′ — Data-Driven Experience Analysis & Assumption-Setting)
- **Title:** Hierarchical partial pooling (segment credibility)
- **Slice:** 3 of 4
- **Branch:** `claude/loving-gauss-0c0ars` (environment-designated `claude/*` branch)

## Selection Rationale
The active epic's CONTINUATION was IN PROGRESS with Slice 2c (PR #145) **merged**
(merge commit `0b0580c`), so Slice 3 was unblocked and is the routine's mandated work
before any fallback pick (step 5b / the always-on-Epic guardrail). No fallback item was
considered. Ledger-heal (step 4b): PR #145 was merged since the last session log but the
CONTINUATION still marked it "(draft — awaiting review/merge)"; healed to MERGED, and the
Slice-3 dependency line updated to note all Slice-2 PRs merged.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Experience-data contract + additive A/E model | ✅ Done | #141 |
| 2a | Frequentist tensor MI surface + `MI_x(y)` grid | ✅ Done | #142 |
| 2b-surface | Bayesian reduced-rank-GP credible-interval surface | ✅ Done | #143 |
| 2b-projection | CMI/MP-style mean-reverting MI projection | ✅ Done | #144 |
| 2c | `MortalityImprovement` CUSTOM-scale emission | ✅ Done | #145 |
| 3 | Hierarchical partial pooling (credibility) | ✅ Done | #146 |
| 4 | CLI + versioning + validation + docs (CLOSES EPIC) | ⏳ Next | — |

## Verify Premise (step 7b)
Reproduced the gap before writing code: today a `segment` grouping enters
`BayesianTensorMIModel` only as a **fixed factor** with a near-flat `1e-6` precision — no
credibility shrinkage. A two-segment reproduction confirmed the segment dummy is
un-pooled (precision `1e-6`), so a thin segment's level is trusted as fully as a
million-life segment's. The premise (a real capability gap, the limited-fluctuation
credibility problem) holds. During implementation a **discovery** refined the approach:
a complete indicator block + the global intercept is exactly collinear, which — with the
soft prior — gives every segment the **same** posterior SE (0.175) and identical
credibility (0.484) regardless of exposure. Fixed with the standard GAM sum-to-zero
identifiability constraint (orthonormal deviation basis); after the fix, per-segment
posterior variance correctly tracks each segment's own exposure.

## What Was Done
Added `HierarchicalMIModel` + `HierarchicalMISurfaceResult` to
`analytics/experience_gam.py`. A `segment` grouping now enters as a **zero-mean Gaussian
random effect** — a per-segment log-A/E *level* deviation and (optionally) a per-segment
calendar *trend* (MI) deviation — shrunk toward the global reduced-rank-GP surface. The
pooling strengths `tau_level`/`tau_trend` are estimated by **empirical Bayes**: an EM
variance-component loop alternates the penalised-Poisson MAP fit (factored out as
`_penalised_poisson_irls`) with the closed-form update `tau^2 <- mean(alpha^2 +
Var_post(alpha))`. The random effect is parameterised in an orthonormal **sum-to-zero**
basis (`_sum_to_zero_basis`), so each segment's posterior variance — and thus its
credibility — reflects its own Fisher information, not a shared intercept-confounded mode.

The global surface reuses the Slice-2 `BayesianTensorMIModel` unchanged via a small
backward-compatible `exclude_factors` hook (keeps `segment` out of the fixed factors).
`segment_effects()` returns a per-segment table: the shrunk level multiplier, its
posterior band, exposure/`n_cells`, the per-year MI trend deviation (in MI units,
positive = faster than global), and the credibility weight
`Z_g = clip(1 - Var_post(b_g)/prior_var, 0, 1)` — the estimated, continuous analogue of
`ExperienceStudy`'s imposed `Z`. `improvement_surface(segment=...)` returns the
segment-specific surface (global + pooled trend) or the global surface (`segment=None`).
Pure NumPy/SciPy, deterministic, core-only — no `pymc`/`bambi`, no `[ml]` dependency.
ADR-144.

The behaviour was validated on synthetic data: the thinnest segment shrinks from a raw
deviation of −0.309 to −0.149 (credibility 0.51) while rich segments keep their raw
deviation (credibility ~0.99); credibility rises monotonically with exposure; and EB
recovers a known between-segment SD (0.125 vs a true 0.15 on 12 segments; collapses toward
the floor when segments are identical).

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` — `_penalised_poisson_irls`,
  `_sum_to_zero_basis`, `_SegmentSpec`, `HierarchicalMISurfaceResult`,
  `HierarchicalMIModel`; `exclude_factors` kwarg on `BayesianTensorMIModel`; `__all__`.
- `src/polaris_re/analytics/__init__.py` — export the new public API.
- `docs/DECISIONS.md` — ADR-144.
- `docs/CONTINUATION_experience_gam.md` (ledger-heal #145 → MERGED; Slice 3 → DONE,
  Slice 4 → NEXT), `docs/PLAN_experience_gam.md`, `docs/PRODUCT_DIRECTION_2026-06-18.md`
  (3 harvested NICE-TO-HAVE follow-ups), this session log.

## Tests Added
- `tests/test_analytics/test_experience_mi_hierarchical.py` (21 tests): thin-segment
  shrinkage; rich-segment escape; pooled-between-raw-and-global (both directions);
  credibility monotonic in exposure; EB variance-component recovery + complete-pooling
  collapse; sum-to-zero identifiability; segment-trend shrink/separation; global surface
  recovers population improvement and matches a plain model without `segment`; thin-segment
  band wider than rich; MISurface shape; determinism; volume/metadata reporting;
  no-trend option; and contract validation (missing/single-level segment, single calendar
  year, bad tau, unknown-segment surface, single-year surface request, generational-base
  guard).

## Acceptance Criteria
| Criterion (PLAN Slice 3) | Status | Notes |
|--------------------------|--------|-------|
| A thin segment shrinks toward the global surface | ✅ | credibility <0.6; |pooled|<0.75·|raw| |
| A data-rich segment escapes pooling | ✅ | credibility >0.95; pooled ≈ raw |
| Pooled estimate lies between raw-cell and global | ✅ | strictly between 0 and raw, both signs |
| Shrinkage estimated, not imposed | ✅ | EB EM recovers `tau`; monotone in marginal lik |
| Deterministic + core-only (no `pymc`) | ✅ | pure NumPy/SciPy, bit-identical on re-run |
| Engine byte-identical (no golden change) | ✅ | `polaris price` golden + full QA/validation unchanged |

Full non-slow suite: **2316 passed, 3 skipped, 110 deselected**, 0 failures (+21).
ruff format + check clean.

## Open Questions / Follow-ups
- The full **Pedersen GS/GI age-varying group-specific smoother** (a shrunk per-segment
  `te(age, year)` deviation surface, not just level + linear trend) is the richer form of
  the planned Slice-3 hierarchy — harvested as NICE-TO-HAVE.
- **Exposure-weighted** (Bühlmann-collective) sum-to-zero centring vs the unweighted GAM
  convention shipped here — harvested as NICE-TO-HAVE.
- Per-segment forward projection and a full NB (vs quasi-Poisson) between-segment variance
  component — harvested as NICE-TO-HAVE.

## Parked Polish
None. All harvested items this session are 1st-order follow-ups of the planned Slice-3
feature (promoted normally as NICE-TO-HAVE).

## Impact on Golden Baselines
None. Purely additive — a new model class + result and an optional `exclude_factors`
kwarg (default empty → prior behaviour). No pricing path, assumption contract, or golden
touched. Baseline `make test` at session start: **2295 passed, 3 skipped, 110 deselected,
0 failures** — matches the recorded post-Slice-2c baseline (tolerance-aware: no
new/changed failures, the 4 CIA SOA-conversion tables were MISSING as usual and their
tests were unaffected). After this slice: **2316 passed** (+21).

## Ledger / Housekeeping Note
The latest `PRODUCT_DIRECTION_2026-06-18.md` is now 34 days old (>30). Consistent with the
immediately-prior slices (#142–#145, all 2026-07-21/22), the harvested follow-ups were
**appended** to its "Promoted Follow-ups" section rather than opening a new file, to avoid
fragmenting the active epic's harvest trail. A fresh `PRODUCT_DIRECTION` regeneration
(and/or the ~30-day COMMERCIAL_VIABILITY_REVIEW re-rank) is flagged for the next run.
