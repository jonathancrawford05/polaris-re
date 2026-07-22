# Continuation: Data-Driven Experience Analysis & Assumption-Setting (GAM)

**Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~10–14 dev-days

## Overall Goal

Give actuaries a data-driven, **interpretable** way to isolate standard feature
effects and set mortality (then lapse) bases from experience, with robust
uncertainty. The headline capability (Slice 2) is a **tensor mortality-improvement
(MI) surface** — age-varying improvement `MI_x(y)` estimated from experience and
emitted as a `MortalityImprovement`-compatible scale. This is the auditable middle
layer between the grouped credibility in `experience_study.py` and the black-box
XGBoost in `ml_mortality.py`.

## Decomposition

### Slice 1: Experience-data contract + marginal effect isolation
- **Status:** DONE
- **Branch:** claude/loving-gauss-gjz7ld
- **PR:** #141 — **MERGED** 2026-07-21
- **Backend:** statsmodels `GLM` + `patsy` B-splines (regression splines).
- **What was done:** New module `analytics/experience_gam.py` defining the canonical
  grouped-cell contract, an `ExperienceGAM` additive A/E fitter (Poisson / quasi-
  Poisson) with a static select-base offset, per-feature smooth/factor effect
  functions with confidence bands, an `aggregate_seriatim` seriatim→grouped fold-in,
  an `attach_base_rate` offset builder over `MortalityTable.get_qx_vector`, and a
  blended base×multiplier `export_to_mortality_csv` that round-trips through
  `load_mortality_csv`. `statsmodels` added to the `[ml]` extra; imported lazily so
  `import polaris_re.analytics` still works without `[ml]`. ADR-139.
- **Key decisions (carry into later slices):**
  - A/E parameterization on the log scale, offset by the **static** annual select
    base (`q_annual = 1-(1-q_monthly)^12`, exact inverse of the table's constant-
    force monthly rate). Never a generational base.
  - Grouped cells are canonical; sufficiency verified to 1e-6 with a *balanced*
    synthetic seriatim (equal replication per age keeps the B-spline knots stable).
  - Overdispersion = quasi-Poisson Pearson-φ scaling, default-on for `basis=
    "amount"`. Full NB(α) deferred.
  - Regression splines (fixed df), NOT penalized-smoothness selection — the robust
    de-risking choice. Penalized/HSGP sophistication starts in Slice 2.

### Slice 2: Tensor MI surface (HEADLINE)

Sub-decomposed to keep CI lean and the suite deterministic: **2a** ships the tensor
surface + `MI_x(y)` grid on the existing statsmodels backend (frequentist, no new
dependency); **2b** adds the Bayesian HSGP backend for honest posterior credible
intervals + posterior-predictive projection; **2c** emits the
`MortalityImprovement`-compatible custom scale (the `ImprovementScale.CUSTOM` /
from-grid contract change, landed with the projected surface that feeds it). This
mirrors the Slice-1 de-risking pattern (regression splines before penalized/GP).

#### Slice 2a: Frequentist tensor MI surface + `MI_x(y)` grid
- **Status:** DONE
- **Branch:** claude/loving-gauss-4zyfr7
- **PR:** #142 — **MERGED** 2026-07-21
- **Backend:** statsmodels tensor-product B-splines (`bs(x, df):bs(t, df)` + margins)
  — reuses the Slice-1 `[ml]` dependency; no `pymc`/`bambi` yet.
- **What was done:** `TensorMIModel` fits `te(attained_age, calendar_year)` on the
  static-base offset; `MISurfaceResult.improvement_surface()` extracts
  `MI_x(y) = 1 − exp[η(x,y) − η(x,y−1)]` with a **delta-method** confidence band
  (`MISurface`). Design-Anchor-3 encoded by construction (no issue-year term; real
  `underwriting_era` factor as the escape hatch). Anchor-1 static-base guard
  (`_assert_static_base`) rejects a generational offset and unidentifiable
  (single-year-per-cell) data. ADR-140.
- **Key decisions (carry into 2b/2c):**
  - Frequentist tensor gradient = the fitted improvement; the delta-method band is the
    frequentist analogue of the Slice-2b credible interval.
  - MI is reported as year-to-year steps; the surface spans `years[1:]` (each column
    is the *end* year of an annual step). 2c's `MortalityImprovement` export consumes
    this grid directly (`q(Y) = q(base)·Π(1−MI)`).
  - `underwriting_era` added to `CANONICAL_KEY_COLUMNS` + candidate factors
    (backward-compatible — activates only when present with >1 level).

#### Slice 2b: Bayesian HSGP credible intervals + projection

Sub-decomposed **surface / projection** during the surface session (2026-07-22)
after a VERIFY-PREMISE discovery: the PLAN's locked `bambi`/`pymc`
`inference_method="laplace"` backend raises `NullTypeGradError` on an HSGP + offset
graph in the installed versions (`pymc` 6.1.0, `bambi` 0.19.0), and full NUTS is
non-deterministic + too slow for CI. The **surface** sub-slice therefore ships the
credible-interval surface as a pure-NumPy/SciPy reduced-rank GP (the identical HSGP
math in closed form — deterministic, core-only, no heavy dependency); the
stochastic **projection** work (and any `pymc`-NUTS audit path) is isolated into its
own sub-slice. Mirrors the Slice-1/2a de-risking pattern. See ADR-141.

##### Slice 2b-surface: Bayesian reduced-rank-GP MI surface + credible intervals
- **Status:** DONE
- **Branch:** claude/loving-gauss-dpfie6
- **PR:** #143 — **MERGED** 2026-07-22
- **Backend:** pure NumPy/SciPy Hilbert-space (reduced-rank) GP — Matérn-5/2
  anisotropic `te(attained_age, calendar_year)`, fit to MAP by penalised-Poisson
  IRLS with a closed-form **Laplace** posterior covariance. **No new dependency**
  (numpy/scipy are core); `pymc`/`bambi` NOT added.
- **What was done:** `BayesianTensorMIModel` + `BayesianMISurfaceResult` in
  `experience_gam.py`. Extracts the same `MISurface` grid as the frequentist model
  but with honest **posterior credible intervals** (`MI_x(y) = 1−exp[η(x,y)−η(x,y−1)]`,
  band propagated from the Laplace covariance through the linear year-contrast).
  Anisotropic fixed length-scales are the smoothness dial (the GP analogue of the
  frequentist spline df); `age_varying=False` gives a separable model. Reuses the
  Anchor-1 static-base guard and the Design-Anchor-3 (no issue-year term;
  `underwriting_era` escape hatch) structure. Deterministic (bit-identical on
  re-run); 23 tests in ~1.4s. ADR-141.
- **Key decisions (carry into 2b-projection/2c):**
  - Fixed length-scales, not empirical-Bayes selection (deferred — Matérn PSD
    underflows at large length-scales → singular Laplace Hessian; harvested).
  - The Laplace credible band == the delta-method band evaluated on the **posterior**
    covariance; it agrees with the 2a frequentist grid on the point estimate (tested).
  - Scale-robust Newton convergence (`max|step| < tol·(1+max|θ|)`) — absolute tol is
    unreachable at the by-amount 1e8 deaths scale.
  - `pymc`/`bambi` deferred to the projection sub-slice, imported lazily there.

##### Slice 2b-projection: posterior-predictive forward projection + NUTS audit
- **Status:** DONE (deterministic projection; `pymc`-NUTS audit path deferred — gated)
- **Branch:** claude/loving-gauss-koxn1s
- **PR:** #144 — **MERGED** 2026-07-22 (merge commit `7961e4e`)
- **Backend:** the same reduced-rank GP (ADR-141) — deterministic, pure NumPy/SciPy,
  core-only. The optional lazily-imported `pymc`-NUTS audit path is **deferred**: it is
  gated on the maintainer confirming the ADR-141 backend-deviation direction (an Open
  Question), and adds `pymc`/`bambi` to `[ml]` only if/when that path is built.
- **What was done:** `MIProjection` dataclass + `BayesianMISurfaceResult.
  project_improvement(horizon_years, long_term_rate, ...)`. Each age's improvement
  anchors on `initial_mi(x)` (the fitted final-step annual improvement + its Laplace
  posterior SE) and **mean-reverts** to a settable `long_term_rate` over
  `convergence_period` years — the CMI/MP-style locked default. Convergence shape is
  selectable (`cosine` default / `linear` / `immediate`). The band is
  posterior-predictive (`MI ± z·w_k·se(initial_mi)`): widest at the join (= the in-window
  surface band), narrowing to zero as improvement converges to the deterministic
  long-term rate. `MIProjection.cumulative_factor()` returns `Π(1−MI)` — the multiplier
  Slice 2c's `MortalityImprovement` emission consumes. Additive; engine byte-identical.
  ADR-142.
- **Key decisions (carry into 2c):**
  - The reduced-rank GP eigenbasis is valid only inside its fit-time boundary, so the
    projection mean-reverts the *improvement rate* rather than re-evaluating the basis
    out of domain (ADR-142). This is the honest, deterministic route.
  - The long-term rate is a deterministic actuarial assumption (a scalar) → the band
    narrows to it. A per-age long-term rate and the RW2 fanning-band alternative are
    harvested follow-ups, not shipped.
  - `cumulative_factor()` is the Slice-2c hand-off: `q(Y) = q(base)·Π(1−MI)`.

#### Slice 2c: `MortalityImprovement`-compatible custom-scale emission
- **Status:** DONE
- **Branch:** claude/loving-gauss-vvdlm3
- **PR:** #145 — **MERGED** 2026-07-22 (merge commit `0b0580c`)
- **Depends on:** Slice 2b merged (surface #143 merged; projection #144 merged 2026-07-22).
- **What was done:** Added `ImprovementScale.CUSTOM` + a backward-compatible data-driven
  grid payload (`custom_ages`/`custom_years`/`custom_mi_grid`/`custom_ultimate_rate`,
  all `None`/`0.0` by default) and a `@model_validator` guard on `MortalityImprovement`;
  a `MortalityImprovement.from_grid(ages, years, mi_grid, ultimate_rate)` constructor
  (`base_year = years[0] − 1`) whose `apply_improvement` accumulates
  `q(Y)=q(base)·Π(1−MI_x(Z))` (reusing the MP_2020 year-by-year product form, ages
  clamped to grid edges, step-end years past the grid using `custom_ultimate_rate`); and
  thin `MISurface.to_mortality_improvement` / `MIProjection.to_mortality_improvement`
  hand-offs (projection default `ultimate_rate = long_term_rate`). The emitted scale
  reproduces the dataclass `cumulative_factor()` exactly. Grid stored as immutable tuples
  → hashable + JSON round-trips (Slice-4 versioning). Engine/goldens byte-identical.
  ADR-143.
- **Key decisions (carry into 3/4):**
  - `improvement.py` stays dependency-free (no `analytics` import); the analytics dataclasses
    call `from_grid`, preserving core layering.
  - CUSTOM grid axes are attained-age × calendar-year (duration-invariant, per
    Design-Anchor-4). Per-duration (select/ultimate) custom grids are harvested NICE-TO-HAVE.
  - The credible band is dropped at the assumption boundary (an improvement scale is a
    point basis); carrying it into a stochastic pricing run is harvested NICE-TO-HAVE.
  - CLI/`--config`/`AssumptionSet` surfacing + `data/assumption_versions/` persistence of a
    CUSTOM scale are **Slice 4** scope (the tuple/JSON representation is chosen for it).

### Slice 3: Hierarchical partial pooling (credibility)
- **Status:** DONE
- **Branch:** claude/loving-gauss-0c0ars
- **PR:** #146 (draft — awaiting review/merge)
- **Depends on:** Slice 2 merged (2a #142, 2b-surface #143, 2b-projection #144, 2c #145 — all merged 2026-07-22).
- **Backend:** the same reduced-rank GP + Laplace posterior (ADR-141) — deterministic,
  pure NumPy/SciPy, core-only. Segment random effects are a ridge block whose prior
  precision is estimated by an EM variance-component loop. No `pymc`/`bambi`.
- **What was done:** `HierarchicalMIModel` + `HierarchicalMISurfaceResult` in
  `analytics/experience_gam.py`. A `segment` grouping enters as a **zero-mean Gaussian
  random effect** — a per-segment log-A/E *level* deviation and (optionally) a per-segment
  calendar *trend* (MI) deviation — shrunk toward the global surface, with the pooling SDs
  `tau_level`/`tau_trend` estimated by **empirical Bayes** (EM: `tau^2 <- mean(alpha^2 +
  Var_post(alpha))`). The random effect is parameterised in an orthonormal **sum-to-zero**
  basis so each segment's posterior variance reflects its own exposure (not a shared
  intercept-confounded mode). `segment_effects()` reports the shrunk multiplier, posterior
  band, and the credibility weight `Z_g = 1 − Var_post/prior_var`;
  `improvement_surface(segment=...)` returns the segment-specific or global surface. Reuses
  the Slice-2 global surface via a small backward-compatible `exclude_factors` hook on
  `BayesianTensorMIModel`. Engine/goldens byte-identical (+21 tests). ADR-144.
- **Key decisions (carry into 4):**
  - Sum-to-zero (unweighted) identifiability — deviations are relative to the *average
    segment*; a weighted (exposure-weighted) centring is a harvested follow-up.
  - `trend_deviation` is reported in MI units (positive = the segment improves faster than
    the global trend), matching `MI = 1 − exp(Δη)`.
  - Level + linear-trend deviations only; a full age-varying group-specific *smoother*
    (Pedersen GS/GI) and per-segment projection are harvested NICE-TO-HAVE.

### Slice 4: Surface + versioning + validation + docs (CLOSES EPIC)
- **Status:** NEXT
- **Depends on:** Slice 3 merged (#146).
- **Scope:** CLI `polaris experience improvement` (+ `polaris experience fit`);
  assumption versioning under `data/assumption_versions/`; effect-shape + MI-surface
  diagnostic plots; `load_hmd()` / `load_ilec()` fetch-and-cache loaders (loaders-not-
  data; large/licensed files excluded from image + CI); insured A/E + improvement
  validation deck vs SOA ILEC / MIM-2021 + CIA; offline `mgcv`-via-`rpy2` oracle as a
  dev-only check; ARCHITECTURE + QUICKSTART; ADR. HARVEST FOLLOW-UPS, then this
  CONTINUATION → COMPLETE.

## Context for Next Session

- Slice 1 leaves the engine byte-identical — no pricing path or golden touched. The
  new module is additive and only reachable via `polaris_re.analytics.ExperienceGAM`.
- The `[ml]` extra now includes `statsmodels>=0.14` (pulls `patsy`, `scipy`). Slice 2
  will add the compile-heavy `pymc`/`bambi` — add them only when the Slice-2 code
  imports them so Slice-1 CI stays lean.
- Sufficiency (grouped == seriatim) is exact **only** when the B-spline knots
  coincide; the test achieves that with a balanced synthetic seriatim. Real seriatim
  extracts will not be knot-balanced, but that does not matter in practice — the
  grouped cells are the canonical fit input and `aggregate_seriatim` is the supported
  path. Do not "improve" the sufficiency test toward unbalanced data; it would fail
  for a benign knot-placement reason, not a real discrepancy.
- The export writes the ultimate-only `age,rate` schema (`select_period=0`). A select-
  and-ultimate export (per-duration columns) is a Slice-2+ option if wanted.

## Open Questions (for human)

- **`pymc`-NUTS audit backend (gated).** The 2b-projection slice ships only the
  deterministic reduced-rank-GP projection. Per ADR-141's human-review flag, adding the
  optional `pymc`-NUTS audit path (and the `pymc`/`bambi` dependency) is **held until the
  maintainer confirms the ADR-141 reduced-rank-GP backend direction**. If confirmed and an
  audit path is still wanted, it lands as a follow-up; if the maintainer prefers the
  original `bambi`/`pymc` backend, that supersedes ADR-141/142. Harvested to
  PRODUCT_DIRECTION as IMPORTANT.
- **Projection prior (Slice 2):** default Matérn HSGP mean-reverting to a settable
  long-term rate (CMI/MP-style) vs RW2 linear extrapolation — finalise in Slice 2's
  ADR. Locked default per the PLAN is Matérn; recorded so an autonomous run does not
  reopen it.
- **NB(α) vs quasi-Poisson on the by-amount basis:** Slice 1 ships quasi-Poisson
  dispersion. Promote a full negative-binomial (estimated α) only if a validation
  deck shows the quasi-Poisson bands materially misstate uncertainty.
