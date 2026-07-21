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
- **PR:** _(draft — this session)_
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
- **Status:** NEXT
- **Depends on:** Slice 2a merged.
- **Backend:** bambi HSGP / pymc (adds `bambi>=0.14`, `pymc>=5.16` to `[ml]`, imported
  only where used).
- **Scope:** anisotropic HSGP `te(x, t)` with **posterior credible intervals** on
  `MI_x(y)` and posterior-predictive **forward projection** anchored to a settable
  long-term rate (locked default: Matérn mean-reverting; RW2 offered). MAP+Laplace and
  full-NUTS run modes. Validate against the 2a frequentist grid + an `mgcv` offline
  oracle within tolerance; a plausible gradient from a real HMD age×year slice.

#### Slice 2c: `MortalityImprovement`-compatible custom-scale emission
- **Status:** PLANNED
- **Depends on:** Slice 2b merged.
- **Scope:** a from-grid constructor / `ImprovementScale.CUSTOM` (core-contract change,
  backward-compatible defaults, human-review flagged) that turns the projected
  `MI_x(y)` surface into a `MortalityImprovement` that plugs into
  `apply_improvement`. Static-vs-generational-offset guard already lives in 2a.

### Slice 3: Hierarchical partial pooling (credibility)
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** segment-level MI/effect deviations shrunk toward the global surface
  (Pedersen GS/GI HGAM); generalizes `ExperienceStudy`'s limited-fluctuation `Z`.
  Thin segments borrow the population trend; shrinkage estimated, not imposed.

### Slice 4: Surface + versioning + validation + docs (CLOSES EPIC)
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
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

- **Projection prior (Slice 2):** default Matérn HSGP mean-reverting to a settable
  long-term rate (CMI/MP-style) vs RW2 linear extrapolation — finalise in Slice 2's
  ADR. Locked default per the PLAN is Matérn; recorded so an autonomous run does not
  reopen it.
- **NB(α) vs quasi-Poisson on the by-amount basis:** Slice 1 ships quasi-Poisson
  dispersion. Promote a full negative-binomial (estimated α) only if a validation
  deck shows the quasi-Poisson bands materially misstate uncertainty.
