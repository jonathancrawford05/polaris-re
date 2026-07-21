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
- **PR:** _(draft — this session)_
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
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Backend:** bambi HSGP / pymc (adds `bambi>=0.14`, `pymc>=5.16` to `[ml]`, imported
  only where used).
- **Files to create/modify:** extend `experience_gam.py` (or a `experience_mi.py`
  sibling) with the `te(x, t)` age-varying improvement term + `s_resid(d)`; a
  `MortalityImprovement`-compatible from-grid constructor / `ImprovementScale.CUSTOM`.
- **Tests to add:** recover a known age×year improvement surface from synthetic data;
  recover a plausible gradient from a real HMD age×year Deaths/Exposures slice; MI grid
  matches an `mgcv` offline oracle within tolerance; projection anchors to a settable
  long-term rate; static-vs-generational-offset guard.
- **Acceptance criteria:**
  - `te(x, t)` fitted with the static-base offset + `s_resid(d)`; anisotropic HSGP.
  - `MI_x(y)` grid extracted **with credible intervals**.
  - Emits a `MortalityImprovement`-compatible custom scale.
  - Encodes Design-Anchor-3 identifiability: default issue-year term = 0; optional
    `underwriting_era` factor.

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
