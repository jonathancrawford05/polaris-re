# Dev Session Log — 2026-07-21

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 1:
  Experience-data contract + marginal effect isolation
- **Slice:** 1 of 4
- **Branch:** `claude/loving-gauss-gjz7ld`

## Selection Rationale
Step 5 found no IN PROGRESS CONTINUATION to continue (the only IN PROGRESS file,
`CONTINUATION_reserve_basis_correctness.md`, is explicitly DEPRIORITISED / parked and
is not the active epic). Step 5b: the active epic is the most recent `PLAN_*.md` with
unchecked slices — `PLAN_experience_gam.md` (CONSTITUTED 2026-07-15, Slice 1 = NEXT,
backing CONTINUATION not yet created). Per the ACTIVE EPIC guardrail, the epic's next
unchecked slice is advanced before any fallback pick, so this session ships Slice 1 and
opens `CONTINUATION_experience_gam.md`. No fallback item was selected.

**Premise check (step 7b).** The epic's premise is that Polaris has no interpretable
experience-GAM layer — only grouped limited-fluctuation credibility
(`experience_study.py`) and black-box XGBoost (`ml_mortality.py`). Confirmed by
inspection: `experience_study.py` computes grouped A/E ratios + a `min(1,√(n/n_full))`
credibility weight only, with no smooth effect isolation. The gap is real; Slice 1 fills
the contract + offset + additive-fit + export plumbing.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + static-base offset + additive A/E GAM + export round-trip | ✅ Done | _(this draft PR)_ |
| 2 | Tensor MI surface `te(x,t)` with credible intervals (bambi/pymc) — HEADLINE | ⏳ Next | — |
| 3 | Hierarchical partial pooling (credibility shrinkage) | 🔲 Planned | — |
| 4 | CLI + assumption versioning + validation decks/loaders + docs (CLOSES EPIC) | 🔲 Planned | — |

## What Was Done
Added a new additive-model module `analytics/experience_gam.py` — the auditable middle
layer between grouped credibility and black-box ML. It defines the canonical grouped-cell
contract (`CANONICAL_KEY_COLUMNS` + the by-count / by-amount measure pairs), an
`ExperienceGAM` fitter, and a `GAMFitResult` carrying per-feature effect and export
helpers. The model is an A/E parameterization on the log scale: `deaths ~
offset(log[exposure·q_base]) + bs(attained_age) + bs(duration_years) + Σ C(factor)`, fit
as a Poisson (by-count) or quasi-Poisson (by-amount) GLM via statsmodels + patsy
B-splines, so `exp(η)` is the fitted multiplicative deviation from the static
select-and-ultimate base table.

Supporting helpers: `aggregate_seriatim` folds a row-level extract into the grouped
contract (grouping is exact sufficiency, verified to 1e-6); `attach_base_rate` builds the
static annual base offset from `MortalityTable.get_qx_vector` (inverting the constant-force
monthly rate exactly), looping over the handful of (sex, smoker) categories rather than
per policy. `GAMFitResult.smooth_effect` / `factor_effect` return marginal effects with
confidence bands; `export_to_mortality_csv` writes a blended base×multiplier `age,rate`
table that round-trips through `load_mortality_csv`. `statsmodels>=0.14` was added to the
`[ml]` extra and is imported lazily, so `import polaris_re.analytics` still works without
`[ml]`; the first `fit()` then raises an actionable `PolarisComputationError`.

The slice is additive: no pricing path, treaty, or golden output changed. The golden
`polaris price` regression and all 76 QA tests are byte-identical to the session baseline.

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` (new, ~430 lines)
- `src/polaris_re/analytics/__init__.py` (export the new public API)
- `pyproject.toml` (`statsmodels>=0.14` → `[ml]` extra)
- `uv.lock` (statsmodels + patsy resolved)
- `docs/DECISIONS.md` (ADR-139)
- `docs/CONTINUATION_experience_gam.md` (new — epic handoff, Status IN PROGRESS)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (harvested follow-ups)

## Tests Added
- `tests/test_analytics/test_experience_gam.py` (16 tests):
  grouped-vs-seriatim sufficiency (coefficients identical to 1e-6); `aggregate_seriatim`
  correctness + guard; flat and age-varying multiplier recovery; by-amount overdispersion
  (φ > 1 recovered, bands widen vs count basis); count-basis no-overdispersion default;
  export→load round-trip identity; non-contiguous-age export guard; `attach_base_rate`
  matches direct annual lookup; contract validation (missing measures, invalid q_base, bad
  basis); import-guard when statsmodels is absent. All randomness seeded; no wall-clock
  dependency (ADR-074 guard).

## Acceptance Criteria
| Criterion (PLAN Slice 1) | Status | Notes |
|-----|--------|-------|
| Canonical grouped-cell contract defined | ✅ | `CANONICAL_KEY_COLUMNS` + count/amount measure pairs |
| Static select-base offset via `get_qx_vector` | ✅ | `attach_base_rate`; annual = exact inverse of constant-force monthly |
| Additive A/E GAM (Poisson/NB) with smooth effects + CIs | ✅ | statsmodels + patsy; `smooth_effect` / `factor_effect` with bands |
| Optional seriatim→grouped aggregator | ✅ | `aggregate_seriatim` |
| `export_to_mortality_csv` round-trips through the loader | ✅ | ultimate-only `age,rate`; identity to 1e-9 |
| Grouped-vs-seriatim sufficiency test | ✅ | coefficients identical to 1e-6 (balanced seriatim) |
| Synthetic multiplier-surface recovery test | ✅ | flat 1.35 and rising gradient recovered |
| By-amount overdispersion handled (dispersion > 1) | ✅ | quasi-Poisson φ; NB(α) deferred (harvested) |
| Effect-CI coverage test | ✅ | band brackets point estimate; widens under overdispersion |
| Import-guard when `[ml]` absent | ✅ | lazy import → `PolarisComputationError` |
| ADR for module + A/E design + grouped contract | ✅ | ADR-139 |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + 76 QA tests unchanged |

## Open Questions / Follow-ups
- **NB(α) vs quasi-Poisson on the by-amount basis.** Slice 1 ships quasi-Poisson Pearson-φ
  scaling. Promote a full negative-binomial (estimated α) only if a validation deck shows
  the quasi-Poisson bands materially misstate uncertainty. Harvested to PRODUCT_DIRECTION
  (NICE-TO-HAVE).
- **Lapse experience through the same GAM machinery.** The module generalizes to lapse;
  the epic's Slices 1–4 are mortality. Harvested to PRODUCT_DIRECTION (NICE-TO-HAVE).
- **Projection prior (Slice 2 decision).** Locked default = Matérn HSGP mean-reverting to a
  settable long-term rate; RW2 offered as an alternative — finalise in Slice 2's ADR. Not
  reopened here.
- **PRODUCT_DIRECTION freshness.** The latest direction file (2026-06-18) is >30 days old
  but is still the living, actively-appended file (carries 2026-07-12 entries), so follow-ups
  were appended to its Promoted Follow-ups section per the repo convention rather than
  regenerating. A dedicated regeneration (shipped-since + carry-forward) is a reasonable
  next-session housekeeping task.

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups surfaced this session; the epic's own future
slices are tracked in PLAN/CONTINUATION, not harvested as polish.)

## Impact on Golden Baselines
None. The slice is additive (new module only); the golden `polaris price` regression and
the full QA suite are byte-identical to the session baseline.

## Baseline
`make test` at session start (on `main` post-#139/PR#140 merge): **2195 passed, 3 skipped,
110 deselected**, 0 failures. After this slice: **2211 passed, 3 skipped, 110 deselected**
(+16 = the new `test_experience_gam.py`). No new or changed failures.
