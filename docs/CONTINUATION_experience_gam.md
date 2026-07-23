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
- **PR:** #146 — **MERGED** 2026-07-22
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

Sub-decomposed 4a/4b/4c/4d (mirrors the Slice-1/2 de-risking pattern) because the
original Slice-4 scope is 4+ sessions: **4a** ships the headline CLI surface
(`polaris experience improvement`) end-to-end (fit → emit CUSTOM scale); **4b** adds the
`fit` diagnostics + assumption versioning + `--config`/`AssumptionSet` wiring; **4c** adds
the loaders + insured validation deck + `mgcv` oracle; **4d** adds diagnostic plots +
ARCHITECTURE/QUICKSTART docs and CLOSES the epic. Each leaves goldens byte-identical.

#### Slice 4a: `polaris experience improvement` CLI surface
- **Status:** DONE
- **Branch:** claude/loving-gauss-wty4t3
- **PR:** #147 — **MERGED** 2026-07-22
- **Depends on:** Slice 3 merged (#146).
- **What was done:** New `experience` Typer command group + `polaris experience improvement`
  in `cli.py`. Reads a grouped-cell experience CSV (canonical contract), attaches the static
  `q_base` offset (used as-is if present, else `--table` + `attach_base_rate`, Anchor 1),
  fits the tensor MI surface (`--frequentist` default `TensorMIModel` / `--bayesian`
  `BayesianTensorMIModel`), optionally forward-projects (`--project-horizon`/`--long-term-rate`,
  Bayesian-only, ADR-142), and emits the `ImprovementScale.CUSTOM` `MortalityImprovement`
  as JSON (`--output`) plus the raw `MI_x(y)` grid long-format (`--grid-out`). Rich summary
  of A/E, dispersion, observed ranges, sampled MI grid + band, and the emitted scale. Heavy
  imports lazy; engine/goldens byte-identical (+11 tests). ADR-145.
- **Key decisions (carry into 4b/4c/4d):**
  - The CSV-on-disk contract accepts a pre-built `q_base` column OR builds it from a named
    standard table — so a Slice-1-exported extract and a raw grouped file both work.
  - The emitted CUSTOM-scale JSON (`model_dump_json`) is exactly the artifact Slice 4b's
    `data/assumption_versions/` persistence and `--config` wiring will consume.
  - `--project-horizon` is gated on `--bayesian` (the projection needs the posterior anchor).

#### Slice 4b: `polaris experience fit` diagnostics + assumption versioning + config wiring

Sub-decomposed 4b-1/4b-2/4b-3 (mirrors the Slice-1/2/4a de-risking cadence) because the
original 4b bundles three distinct capabilities (a diagnostics command, versioned
persistence, and pricing-config wiring) — each is its own session and each leaves the
goldens byte-identical.

##### Slice 4b-1: `polaris experience fit` effect-shape diagnostics CLI
- **Status:** DONE
- **Branch:** claude/loving-gauss-3tkl4n
- **PR:** #148 — **MERGED** 2026-07-23 (merge commit `df0aad0`; ledger-healed this session)
- **Depends on:** Slice 4a merged (#147).
- **What was done:** New `polaris experience fit` command in the existing `experience` Typer
  group. Reads the same grouped-cell contract as `experience improvement` (reusing
  `_load_experience_cells` / `_attach_base_rate_for_experience`), fits the Slice-1
  interpretable additive A/E GAM (`ExperienceGAM`, ADR-139), and reports each standard
  feature's smooth/categorical effect on the A/E multiplier with a confidence band. The Rich
  summary reports overall A/E, quasi-Poisson dispersion φ, overdispersion state, cell count,
  and active factors; each smooth is sampled at `--grid-points` across its observed range and
  each factor gives one row per level (contrast vs modal reference). `--effects-out` writes a
  tidy long-format CSV (`feature, term_type, x, x_value, multiplier, lower, upper`) — the
  artifact the Slice-4d diagnostic plots/dashboard consume, bands first-class. Additive;
  engine/goldens byte-identical (+7 tests). ADR-146.
- **Key decisions (carry into 4b-2/4b-3/4d):**
  - The smooth grid range is read from the cells frame in the CLI (the `GAMFitResult` does
    not carry the observed feature range); `_collect_experience_effects` takes `cells`.
  - `--effects-out` schema is deliberately the plot-ready long format (numeric `x_value` for
    smooths, null for factors) so Slice 4d renders bands straight from it (per the locked 4d
    band decision) — no band info lost between fit and plot.
  - Modal-reference factor level is a tie-break at equal exposure (inherited from Slice-1
    `factor_effect`); contrasts are reference-invariant, so it is cosmetic.

##### Slice 4b-2: assumption versioning under `data/assumption_versions/`
- **Status:** DONE
- **Branch:** claude/loving-gauss-yyrw5z
- **PR:** #149 — **MERGED** 2026-07-23 (merge commit `e0488ce`; ledger-healed this session)
- **Depends on:** Slice 4b-1 merged (#148).
- **What was done:** New `assumptions/version_store.py` — an `AssumptionVersion`
  (`PolarisBaseModel`) wrapping an experience-derived `ImprovementScale.CUSTOM`
  `MortalityImprovement` with `study_date` + optional `credibility` (∈[0,1]) + `label`/`notes`
  provenance, and an append-only `AssumptionVersionStore` persisting records under
  `{root}/{kind}/{version_id}.json` (`version_id = {study_date}-{seq:03d}`). `save` allocates
  the next sequence per `(kind, study_date)` so re-saving a study date never overwrites — the
  full history of frozen bases is preserved. Version ids are keyed on the pinned study date +
  a sequence counter, never the wall clock (ADR-074). CLI surface: `polaris experience save`
  (consumes the `experience improvement --output` JSON, wraps it, appends) and
  `polaris experience list` (Rich table of the stored history). `--store-dir` defaults to
  `$POLARIS_DATA_DIR/assumption_versions`. Additive; engine/goldens byte-identical (+19 tests).
  ADR-147. **No files land under `data/`** — tests use `tmp_path` exclusively, so the
  Dockerfile/`.dockerignore` allowlist is untouched (the #61/#66 trap does not apply).
- **Key decisions (carry into 4b-3):**
  - The store persists CUSTOM scales only (a `@model_validator` guard) — the study/credibility
    provenance is meaningless for a built-in scale. 4b-3 loads a version by id and threads its
    `.improvement` into the pricing `--config`/`AssumptionSet`.
  - `version_id` is the stable, human-legible handle (`{study_date}-{seq:03d}`) 4b-3's config
    schema references — deterministic, filesystem-safe, sortable.
  - `save` is decoupled from `improvement` (it consumes the emitted JSON artifact), so a scale
    can be reviewed/edited before it is frozen into the versioned store.

##### Slice 4b-3: wire `ImprovementScale.CUSTOM` into `--config` + `AssumptionSet`
- **Status:** DONE
- **Branch:** claude/loving-gauss-hdfvde
- **PR:** #150 — **MERGED** 2026-07-23 (merge commit `9f6551e`; ledger-healed 2026-07-23)
- **Depends on:** Slice 4b-2 merged (#149).
- **What was done:** `MortalityConfig` gained three optional default-preserving fields
  (`improvement_version_id` / `improvement_store_dir` / `improvement_kind`); a new
  `load_improvement_version(version_id, *, store_dir, kind)` selector loads the frozen CUSTOM
  scale from the append-only store; and `build_assumption_set` threads it onto
  `AssumptionSet.improvement` (else `None`, byte-identical). The product engines already consume
  `AssumptionSet.improvement` (ADR-125), so the versioned experience basis now drives
  best-estimate mortality on a `polaris price` run with no engine change. CLI: the nested-config
  parser reads `mortality.improvement_version_id` (+ store-dir/kind); a new
  `--improvement-version` flag overrides it (flag-over-config, the `--valuation-mortality`
  precedent); the selected id is echoed into the JSON summary as
  `mortality_improvement_version` only when set. `default_store_root()` lifted into
  `version_store.py` as the single shared store-root default (the `experience save/list`
  `_resolve_store_dir` now delegates to it). Contract-adjacent (config schema, not a data
  contract) — default-preserving, human-review-flagged. Engine/goldens byte-identical (+12
  tests). ADR-148.
- **Key decisions (carry into 4c/4d):**
  - The selector lives in the `mortality` config block (→ `MortalityConfig`), alongside the base
    table, since improvement is a mortality concept; `valuation_mortality` (a `deal`-block
    assumption selector) is the surfacing precedent but improvement groups with base mortality.
  - Dashboard + REST API request-schema surfacing is deferred to a dedicated slice (the
    `yrt_rate_table_*` / ALM precedent — a config field joins the parity surfaces only when a
    slice consumes it). `MortalityConfig`'s new fields default so both are unaffected today.
  - Only the experience-derived CUSTOM path is wired; a config selector for a **built-in** scale
    (Scale AA / MP-2020) is an orthogonal follow-up (harvested NICE-TO-HAVE).

#### Slice 4c: Loaders + insured validation deck + `mgcv` oracle

Sub-decomposed 4c-1/4c-2/4c-3 (mirrors the Slice-1/2/4a/4b de-risking cadence) because the
original 4c bundles three distinct capabilities (fetch-and-cache loaders, an insured validation
deck, and the `mgcv` oracle) — each is its own session and each leaves the goldens byte-identical.

##### Slice 4c-1: HMD / SOA-ILEC experience data loaders (loaders-not-data)
- **Status:** DONE
- **Branch:** claude/loving-gauss-84fcs2
- **PR:** _(this draft PR)_
- **Depends on:** Slice 4b merged (4b-1 #148, 4b-2 #149, 4b-3 #150 — all merged 2026-07-23).
- **What was done:** New `analytics/experience_loaders.py` — loaders, not data (Anchor 6 /
  #61/#66 trap). `parse_hmd_1x1` parses one HMD 1x1 text file (Deaths/Exposures) into long
  `(calendar_year, attained_age, sex, value)` — `.` missing markers and the `Total` column
  dropped, open `110+` parsed to age 110. `load_hmd(deaths, exposures, ...)` inner-joins the two
  on `(year, age, sex)` → by-count canonical cells (`central_exposure`/`death_count`), drops the
  open age group by default, applies year/age/sex windows, sorts deterministically.
  `load_ilec(path, *, basis, column_map, aggregate)` renames source columns via a default
  (overridable) `ILEC_COLUMN_MAP`, canonicalises gender/smoker to Polaris enum values, converts
  1-based `Duration` → `duration_months=(d-1)*12`, selects the `count`/`amount`/`both` measure
  pair(s), and group-and-sums over the present canonical keys (Anchor 7). `fetch_hmd` is a thin,
  dependency-injected fetch-and-cache helper (`hmd_1x1_url` + `default_experience_cache_dir`) —
  the `downloader` transport is injectable so tests exercise URL/cache/skip logic with no
  network; the default urllib transport is `pragma: no cover`. `sex`/`smoker` emitted as enum
  values so loaded cells feed `attach_base_rate` + `TensorMIModel` with no re-mapping (proven
  end-to-end). Additive; engine/goldens byte-identical (+32 tests). ADR-149. **No files land
  under `data/`** — tests use `tmp_path`; allowlist untouched.
- **Key decisions (carry into 4c-2/4c-3/4d):**
  - HMD is population (by-count only, no select/duration/factors) → the primary real-data
    engineering/regression fixture. ILEC is the insured source with all three Lexis axes + both
    count/amount bases → the validation-deck fit source (4c-2).
  - The parsers take a *local cached path* (hermetic, CI-safe); network is isolated to
    `fetch_hmd` with an injectable transport. ILEC has no fetch helper — it is a manual
    data-use-agreement download the loader then consumes.
  - `ILEC_COLUMN_MAP` is overridable per-vintage (ILEC header spellings differ between releases);
    the default targets the common SOA-ILEC flat-file names.

##### Slice 4c-2: insured A/E + improvement validation deck
- **Status:** NEXT
- **Depends on:** Slice 4c-1 merged (this PR).
- **Scope:** insured A/E + improvement **validation deck** (the A4′ analogue of the A1′
  validation pack) — fit the tensor MI surface on an ILEC extract (via `load_ilec`) and check the
  emitted `MI_x(y)` against SOA MIM-2021 / CIA aggregated improvement targets within tolerance;
  wire into the `analytics/validation.py` benchmark harness. In-repo tests use a small
  synthetic/sampled fixture only (loaders-not-data).

##### Slice 4c-3: offline `mgcv`-via-`rpy2` oracle (dev-only)
- **Status:** PLANNED
- **Depends on:** Slice 4c-2 merged.
- **Scope:** the offline `mgcv`-via-`rpy2` oracle wired as a dev-only check (never a runtime/CI
  dependency, Anchor 5) — a `@pytest.mark.slow`/opt-in cross-check that the Python GAM
  coefficients match R `mgcv` on a shared synthetic dataset.

#### Slice 4d: Diagnostic plots + docs (CLOSES EPIC)
- **Status:** PLANNED
- **Depends on:** Slice 4c merged.
- **Scope:** effect-shape + MI-surface diagnostic plots; ARCHITECTURE + QUICKSTART; ADR.
  HARVEST FOLLOW-UPS, then this CONTINUATION → COMPLETE.
- **Fold in the PR #148 review option-3 cleanup here (recommended landing point).** When the
  dashboard becomes a *second* consumer of the tidy effect-shape frame, capture
  `feature_ranges: dict[str, tuple[float, float]]` on `GAMFitResult` at fit time and move
  `_collect_experience_effects` onto the model as a public `all_effects(...) -> pl.DataFrame`
  (defaulting `smooth_effect`'s grid to the observed range). This removes the CLI's
  `cells`-frame reach-back for smooth spans so the CLI and the 4d dashboard call one public
  method instead of each re-deriving ranges. The public `GAMFitResult.smooth_features`
  accessor (the P2 half) already shipped in PR #148; this is the remaining half. See the
  PRODUCT_DIRECTION Promoted Follow-up (*Source: PR #148 review [P2] option 3*).
- **Uncertainty bands — LOCKED (maintainer decision 2026-07-22).** Every diagnostic plot
  renders its band by default — the bands are already first-class in the data structures
  (`SmoothEffect.lower/upper`, `MISurface.mi_lower/upper + confidence_level`,
  `MIProjection.mi_lower/upper`), so rendering them is the default, not extra scope.
  Rendering choices (the band drives the form):
  - **Smooth effects:** line + shaded band (`fill_between`). **Factor effects:** point +
    error bars.
  - **MI surface:** do NOT paint a band onto a 3-D age×year surface (unreadable). Render
    **1-D slices** (MI vs calendar year for selected ages; MI vs age for selected years) as
    line + shaded band; optionally a separate band-*width* heatmap to show where the surface
    is well- vs poorly-identified (edges / thin cells).
  - **Projection:** a **fan chart** — the band shape (widest at the join, narrowing to the
    deterministic long-term rate) is the point, so it is front-and-centre.
  - **Label the band type** in every caption/legend — frequentist *confidence* vs Bayesian
    *credible* vs projection *posterior-predictive* are NOT interchangeable.
  - **Backend note (matplotlib out of the runtime path):** primary rendering is *data →
    existing Streamlit dashboard* (reuse `--effects-out`/`--grid-out` output, no new heavy
    dep); an optional static `plot_effects()`/`plot_mi_surface()` helper lives behind a
    `[viz]` extra for reports (dev/report-only, never imported by the pricing path).

## Context for Next Session

- **Slice 4d bands (maintainer decision 2026-07-22, see Slice 4d scope):** diagnostic plots
  render uncertainty bands by default. Rationale worth carrying: per ADR-143,
  `to_mortality_improvement` **drops the band at the assumption boundary** (an improvement
  scale is a point basis), so the 4d diagnostics are the one place the uncertainty stays
  visible — they are where a reviewer signs off on the basis *before* it is frozen into a
  CUSTOM scale. Do not try to carry the band into the emitted scale (that is a separate
  harvested NICE-TO-HAVE — a stochastic CUSTOM scale).
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
