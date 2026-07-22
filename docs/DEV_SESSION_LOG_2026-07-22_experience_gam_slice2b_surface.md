# Dev Session Log — 2026-07-22 (Slice 2b — surface)

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b),
  backing docs/CONTINUATION_experience_gam.md (IN PROGRESS)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 2b
  (Bayesian HSGP credible intervals), **sub-slice "surface"**: reduced-rank-GP MI
  surface + posterior credible intervals
- **Slice:** 2b-surface of the Slice-2 HEADLINE (Slice 2 = 2a/2b/2c; 2b split
  surface/projection this session)
- **Branch:** `claude/loving-gauss-dpfie6`

## Selection Rationale
Step 5 found the active epic's CONTINUATION (`experience_gam`) IN PROGRESS. Ledger-healed
(step 4b): Slice 2a's **PR #142 confirmed merged** into `main` (git log + GitHub MCP;
the CONTINUATION's "draft — awaiting review/merge" marker was stale because the routine
never merges its own PRs) — recorded `#142 — MERGED`. Also cross-checked PRs #137–#142:
all merged; the cedant epic already shows COMPLETE, so no other stale ledger entries.
With Slice 2a merged, the epic's next unchecked slice (Slice 2b, the Bayesian HSGP
credible intervals) is unblocked, so per the ACTIVE-EPIC guardrail it is advanced before
any fallback pick. No fallback item was selected.

**Sub-decomposition + backend decision (VERIFY-PREMISE / DISCOVERY, steps 7b/11b).**
Slice 2b's PLAN backend is a Bayesian anisotropic HSGP via `bambi` (on `pymc`), fit with
`inference_method="laplace"` (deterministic) + full NUTS (audit). I reproduced the intended
path first: with the installed stack (`pymc` 6.1.0, `bambi` 0.19.0) a `bambi` HSGP model
with an `offset()` term fit via `laplace` raises **`NullTypeGradError`** inside
`pymc.tuning.scaling.find_hessian` — the Laplace Hessian cannot be differentiated through
the HSGP + offset graph. Full NUTS avoids it but is non-deterministic across platforms and
too slow for the default suite. So the PLAN's *locked* default backend does not work as
specified; following it literally would ship a broken import or a flaky/slow test.

Rather than that, I shipped the surface as the **identical HSGP math in closed form**: a
Hilbert-space (reduced-rank) GP (Solin & Särkkä 2020) is a fixed Laplacian-eigenbasis
linear model whose coefficient prior is scaled by the Matérn-5/2 spectral density; with
fixed length-scales it is a penalised-Poisson GLM fit to its MAP by Newton/IRLS with a
closed-form **Laplace** posterior covariance. This is deterministic, pure NumPy/SciPy
(numpy/scipy are core — no `[ml]` extra, no `pymc`/`bambi` dependency), and delivers 2b's
headline: honest **posterior credible intervals** on `MI_x(y)`. The stochastic
forward-projection work (and any `pymc`-NUTS audit path) is isolated into a 2b-projection
sub-slice. See ADR-141 (with an explicit human-review flag on the backend deviation).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + static-base offset + additive A/E GAM + export | ✅ Done | #141 (merged) |
| 2a | Frequentist tensor `te(x,t)` surface + `MI_x(y)` grid + delta-method band | ✅ Done | #142 (merged) |
| 2b-surface | Bayesian reduced-rank-GP MI surface + posterior credible intervals | ✅ Done | _(this draft PR)_ |
| 2b-projection | Posterior-predictive forward projection + optional pymc-NUTS audit | ⏳ Next | — |
| 2c | `MortalityImprovement`-compatible custom scale (`ImprovementScale.CUSTOM`/from-grid) | 🔲 Planned | — |
| 3 | Hierarchical partial pooling (credibility shrinkage) | 🔲 Planned | — |
| 4 | CLI + assumption versioning + validation decks/loaders + docs (CLOSES EPIC) | 🔲 Planned | — |

## What Was Done
Added the Bayesian counterpart to the Slice-2a frequentist surface:
`BayesianTensorMIModel` + `BayesianMISurfaceResult` in `analytics/experience_gam.py`. The
model fits `deaths ~ offset(log[exposure·q_base]) + te(attained_age, calendar_year)
+ s(duration_years) + Σ factors` where `te` is an **anisotropic reduced-rank Gaussian
process** (Hilbert-space HSGP expansion, Matérn-5/2 covariance, per-axis length-scales)
plus additive 1-D age/year/duration GP margins and factor dummies. The GP becomes a
penalised-Poisson GLM: the Laplacian eigenfunctions form a fixed basis, the Matérn spectral
density scales the shared `Normal(0, prior_scale²)` coefficient prior, and the fit is the
MAP by Newton/IRLS with a closed-form Laplace posterior covariance `(XᵀWX + P)⁻¹`.

`BayesianMISurfaceResult.improvement_surface()` returns the same `MISurface` dataclass as
the frequentist model, but with honest **posterior credible intervals**: the year-to-year
MI contrast `d = η(x,y) − η(x,y−1)` is linear in the coefficients, so its posterior is
Gaussian and the band propagates the Laplace covariance through `1 − exp(·)` exactly.
`age_varying=False` gives a separable model (improvement constant across age); the
Anchor-1 static-base guard and the Design-Anchor-3 (no issue-year term, `underwriting_era`
escape hatch) structure are reused from Slice 2a. Fixed anisotropic length-scales are the
smoothness dial — the GP analogue of the frequentist fixed spline df.

The whole model is pure NumPy/SciPy, deterministic (bit-identical on re-run), and needs no
`[ml]` extra (cleaner than 2a's statsmodels backend). The slice is additive: no pricing
path, treaty, or golden output changed. The golden `polaris price` regression and all 76
QA tests are byte-identical to the session baseline.

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` (extended: `BayesianTensorMIModel`,
  `BayesianMISurfaceResult`, `_RRGPSpec`, `_rrgp_eigenbasis_1d`,
  `_matern52_spectral_density`; module docstring; `__all__`)
- `src/polaris_re/analytics/__init__.py` (export the new public API)
- `docs/DECISIONS.md` (ADR-141)
- `docs/CONTINUATION_experience_gam.md` (Slice 2a → PR #142 merged; Slice 2b sub-split
  surface/projection, 2b-surface DONE)
- `docs/PLAN_experience_gam.md` (status + backend-deviation note)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (harvested 2 follow-ups)
- `tests/test_analytics/test_experience_mi_bayesian.py` (new, 23 tests)

## Tests Added
- `tests/test_analytics/test_experience_mi_bayesian.py` (23 tests): constant improvement
  recovered on the interior grid (closed-form, deterministic deaths, atol 1.5e-3);
  age-varying gradient recovered (young > old, each within 3e-3); no-trend → MI ≈ 0;
  separable vs tensor attribution (separable flattens the age gradient to machine eps,
  tensor resolves a positive gradient); `underwriting_era` factor enters; 95% credible
  band brackets the truth on >90% of cells and widens as exposure thins and as the
  credible level rises; by-amount overdispersion applied (φ > 1) widens the band
  (parametrized over exposure); the fit is deterministic (bit-identical surfaces); the
  Bayesian point estimate agrees with the Slice-2a frequentist grid within 3e-3;
  effective-df bounded (shrinkage); `to_frame` shape/columns; Anchor-1 generational-base
  reject + override; single-year-per-cell reject; contract/config validation (missing
  columns, single year, bad basis, boundary_factor ≤ 1, < 2 surface years). Recovery
  tests use deterministic expected deaths (closed-form verification); band tests use
  seeded Poisson draws. No wall-clock dependency (ADR-074 guard). Runs in ~1.4s.

## Acceptance Criteria
| Criterion (PLAN Slice 2b, surface subset) | Status | Notes |
|-----|--------|-------|
| Anisotropic GP `te(x, t)` with the static-base offset | ✅ | reduced-rank Matérn-5/2 HSGP (ADR-141 backend) |
| `MI_x(y)` grid with **posterior credible intervals** | ✅ | Laplace covariance propagated through the year-contrast |
| Recover a known age×year improvement surface from synthetic data | ✅ | constant + age-varying recovered (closed-form) |
| Design-Anchor-3 identifiability (issue-year = 0; optional `underwriting_era`) | ✅ | inherited structure; separable/tensor attribution tested |
| Static-vs-generational-offset guard | ✅ | reused `_assert_static_base` + override |
| Deterministic + CI-lean | ✅ | pure NumPy/SciPy, bit-identical, 23 tests ~1.4s, core-only |
| Agrees with the 2a frequentist grid | ✅ | within 3e-3 on the interior |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + 76 QA tests unchanged |
| Posterior-predictive projection; long-term-rate anchor; NUTS audit; HMD/mgcv oracle | ⏳ | deferred to 2b-projection (see CONTINUATION) |

## Open Questions / Follow-ups
- **Backend deviation (ADR-141).** The surface deviates from the PLAN's locked
  `bambi`/`pymc` HSGP backend because that backend is defective in the installed versions
  (`NullTypeGradError` on HSGP + offset). The reduced-rank GP is the identical GP math in
  closed form and strictly better for CI, but the maintainer should confirm the direction
  before the 2b-projection slice (which is where a `pymc`-NUTS audit path would land).
  Harvested to PRODUCT_DIRECTION as IMPORTANT.
- **Empirical-Bayes length-scale/amplitude selection.** Prototyped, deferred (Matérn PSD
  underflows at large length-scales → singular Laplace Hessian); fixed length-scales work
  on the common path. Harvested to PRODUCT_DIRECTION as NICE-TO-HAVE.
- **2b-projection (next slice) + 2c custom-scale emission.** Tracked in PLAN/CONTINUATION
  as the epic's next slices — not harvested.
- **PRODUCT_DIRECTION freshness.** The latest direction file (2026-06-18) is now ~34 days
  old (>30). Consistent with the Slice-1 and Slice-2a decisions, this session appended the
  genuine follow-ups to its Promoted Follow-ups section rather than regenerating mid-run
  (a full shipped-since + carry-forward regeneration would risk the wall-clock guardrail).
  A dedicated `PRODUCT_DIRECTION_{today}` regeneration remains a reasonable standalone
  next-session housekeeping task.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced. The epic's own future slices
(2b-projection, 2c, Slice 3, Slice 4) are tracked in PLAN/CONTINUATION, not harvested.

## Impact on Golden Baselines
None. The slice is additive (new classes in an existing module); the golden `polaris price`
regression and the full QA suite are byte-identical to the session baseline.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (on `main` post-#142
merge): **2227 passed, 3 skipped, 110 deselected**, 0 failures — matches the recorded
Slice-2a baseline, so no NEW/CHANGED failures; proceeded. After this slice: **2250 passed,
3 skipped, 110 deselected**, 0 failures (+23 = the new `test_experience_mi_bayesian.py`).
QA suite (76) and the golden `polaris price` regression byte-identical.
