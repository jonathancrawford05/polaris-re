# Dev Session Log — 2026-07-21 (Slice 2a)

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b),
  backing docs/CONTINUATION_experience_gam.md (IN PROGRESS)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 2
  (tensor MI surface, HEADLINE), **sub-slice 2a**: frequentist tensor surface + `MI_x(y)` grid
- **Slice:** 2a of the Slice-2 HEADLINE (Slice 2 sub-decomposed 2a/2b/2c)
- **Branch:** `claude/loving-gauss-4zyfr7`

## Selection Rationale
Step 5 found the active epic's CONTINUATION (`experience_gam`) IN PROGRESS with Slice 1
DONE. Ledger-healed (step 4b): Slice 1's PR **#141 confirmed merged** into `main`
(the routine never merges its own PRs, so the CONTINUATION's "draft — this session"
marker was stale); recorded `#141 — MERGED`. With Slice 1 merged, the epic's next
unchecked slice (Slice 2, the tensor MI surface) is unblocked, so per the ACTIVE-EPIC
guardrail it is advanced before any fallback pick. No fallback item was selected.

**Sub-decomposition decision.** Slice 2's PLAN target backend is a Bayesian anisotropic
HSGP (bambi/pymc). `pymc` is compile-heavy and its NUTS sampling is slow and
non-deterministic — hostile to a single autonomous session that must keep CI lean and
the suite deterministic. Following the exact de-risking pattern Slice 1 used (regression
splines before penalized/GP sophistication) and the repo's established sub-slice
convention, Slice 2 is split: **2a** ships the tensor surface + `MI_x(y)` grid on the
existing statsmodels backend (this session); **2b** adds the Bayesian HSGP credible
intervals + projection; **2c** emits the `MortalityImprovement`-compatible custom scale.

**Premise check (step 7b).** The claim is that the engine has no calendar-year
improvement term / MI surface. Confirmed by inspection: `calendar_year` appears in
`experience_gam.py` only inside `CANONICAL_KEY_COLUMNS` (a contract key), and
`ExperienceGAM.fit()`'s formula is `bs(attained_age) + bs(duration_years) + Σ C(factor)`
— no calendar term, no way to extract `MI_x(y)`. The gap is real; Slice 2a fills it.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + static-base offset + additive A/E GAM + export | ✅ Done | #141 (merged) |
| 2a | Frequentist tensor `te(x,t)` surface + `MI_x(y)` grid + delta-method band | ✅ Done | _(this draft PR)_ |
| 2b | Bayesian HSGP credible intervals + posterior-predictive projection (bambi/pymc) | ⏳ Next | — |
| 2c | `MortalityImprovement`-compatible custom scale (`ImprovementScale.CUSTOM`/from-grid) | 🔲 Planned | — |
| 3 | Hierarchical partial pooling (credibility shrinkage) | 🔲 Planned | — |
| 4 | CLI + assumption versioning + validation decks/loaders + docs (CLOSES EPIC) | 🔲 Planned | — |

## What Was Done
Added the epic headline — the **tensor mortality-improvement surface** — to
`analytics/experience_gam.py` as `TensorMIModel` + `MISurfaceResult` + `MISurface`,
on the existing Slice-1 statsmodels backend (no new dependency). The model fits
`deaths ~ offset(log[exposure·q_base]) + te(attained_age, calendar_year)
+ s(duration_years) + Σ factors` as a Poisson / quasi-Poisson GLM, where
`te(attained_age, calendar_year)` is a tensor-product B-spline (the patsy interaction
`bs(attained_age, df):bs(calendar_year, df)` plus its margins). `age_varying=False`
drops the interaction for a separable age + calendar model.

`MISurfaceResult.improvement_surface()` extracts the annual improvement grid
`MI_x(y) = 1 − exp[η(x,y) − η(x,y−1)]` with a pointwise **delta-method** confidence
band (the frequentist analogue of the Slice-2b credible interval): the year-to-year
change in the linear predictor is a linear contrast whose covariance propagates through
`1 − exp(·)`. Because the base offset and every non-calendar term are calendar-invariant
they cancel in the difference, so the grid is exactly the fitted calendar/tensor trend
regardless of reference covariates.

Identifiability is Design-Anchor-3 by construction: the model carries **no issue-year
term**, so the calendar gradient is attributed to improvement (the locked default). The
escape hatch is a real, supported `underwriting_era` factor (added to
`CANONICAL_KEY_COLUMNS` + the candidate-factor list, backward-compatible — activates
only when present with >1 level). The Anchor-1 static-base guard (`_assert_static_base`)
rejects a `q_base` offset that drifts with calendar year (a generational base would make
the trend residual-vs-assumed improvement) and rejects data where no covariate cell
spans >1 calendar year (the trend is then unidentifiable); `allow_generational_base=True`
overrides it. ADR-140.

The slice is additive: no pricing path, treaty, or golden output changed. The golden
`polaris price` regression and all 76 QA tests are byte-identical to the session baseline.

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` (extended: `TensorMIModel`,
  `MISurfaceResult`, `MISurface`, `_assert_static_base`, `_predict_eta_se`;
  `underwriting_era` added to the contract + candidate factors; docstring)
- `src/polaris_re/analytics/__init__.py` (export the new public API)
- `docs/DECISIONS.md` (ADR-140)
- `docs/CONTINUATION_experience_gam.md` (Slice 1 → PR #141 merged; Slice 2 sub-decomposed 2a/2b/2c, 2a DONE)
- `docs/PLAN_experience_gam.md` (status + Slice 2 sub-decomposition)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (harvested follow-up)

## Tests Added
- `tests/test_analytics/test_experience_mi_surface.py` (15 tests): constant-improvement
  recovered to machine precision; age-varying gradient recovered (young > old, each age
  within 5e-4); no-trend → MI ≈ 0; separable-vs-tensor attribution (separable flattens
  the age gradient, tensor resolves it); `underwriting_era` factor enters; generational
  base rejected + override; no-cell-spans-multiple-years rejected; delta-method band
  brackets the truth and widens as exposure thins and as confidence rises; `to_frame`
  shape/columns; contract validation (single year, missing columns, bad basis, <2 surface
  years); `[ml]`-absent import guard. Recovery tests use deterministic expected deaths
  (closed-form verification); band tests use seeded Poisson draws. No wall-clock
  dependency (ADR-074 guard). Runs in ~1.4s.

## Acceptance Criteria
| Criterion (PLAN Slice 2, 2a subset) | Status | Notes |
|-----|--------|-------|
| `te(x, t)` fitted with the static-base offset | ✅ | tensor-product B-spline; Poisson/quasi-Poisson GLM |
| `MI_x(y)` grid extracted with uncertainty bands | ✅ | `1 − exp[η(x,y) − η(x,y−1)]`; delta-method band (credible intervals → 2b HSGP) |
| Design-Anchor-3 identifiability (issue-year term = 0; optional `underwriting_era`) | ✅ | no issue-year term by construction; real `underwriting_era` factor |
| Static-vs-generational-offset guard | ✅ | `_assert_static_base`; also guards unidentifiable single-year cells |
| Recover a known age×year improvement surface from synthetic data | ✅ | constant + age-varying recovered to machine precision |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + 76 QA tests unchanged |
| Anisotropic HSGP; credible intervals; MortalityImprovement custom scale; HMD/mgcv oracle | ⏳ | deferred to 2b/2c (see CONTINUATION) |

## Open Questions / Follow-ups
- **Bayesian HSGP backend (Slice 2b).** Honest posterior credible intervals +
  posterior-predictive projection with a settable long-term-rate anchor (locked default
  Matérn mean-reverting; RW2 offered). Tracked as the epic's next slice — not harvested.
- **`MortalityImprovement` custom-scale emission (Slice 2c).** The `ImprovementScale.CUSTOM`
  / from-grid core-contract change that lets the projected `MI_x(y)` grid drive
  `apply_improvement`. Deliberately deferred so the contract change lands with the
  projected surface that feeds it. Tracked — not harvested.
- **Frequentist smoothness selection.** 2a uses fixed-df tensor splines; data-driven
  smoothness (penalized GAM / GCV) could refine band calibration on noisy real data, but
  2b's HSGP largely subsumes it. Harvested to PRODUCT_DIRECTION (NICE-TO-HAVE, 2nd-order).
- **PRODUCT_DIRECTION freshness.** The latest direction file (2026-06-18) is now ~33 days
  old (>30). Consistent with the Slice-1 decision earlier today, this session appended the
  single genuine follow-up to its Promoted Follow-ups section rather than regenerating
  mid-day (regeneration is a substantial shipped-since + carry-forward task that would risk
  the wall-clock guardrail). A dedicated `PRODUCT_DIRECTION_{today}` regeneration remains a
  reasonable standalone next-session housekeeping task.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced. The epic's own future slices (2b, 2c,
Slice 3, Slice 4) are tracked in PLAN/CONTINUATION, not harvested as polish.

## Impact on Golden Baselines
None. The slice is additive (new classes in an existing module); the golden
`polaris price` regression and the full QA suite are byte-identical to the session baseline.

## Baseline
`make test` at session start (on `main` post-#141 merge): **2212 passed, 3 skipped,
110 deselected**, 0 failures. After this slice, full non-slow suite: **2227 passed,
3 skipped, 110 deselected**, 0 failures (+15 = the new `test_experience_mi_surface.py`);
no new or changed failures. QA suite (76) and the golden `polaris price` regression
byte-identical. (The +1 vs the Slice-1 log's 2211 is an unrelated test added on `main`
between merges, not a regression.)
