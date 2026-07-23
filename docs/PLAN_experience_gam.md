# PLAN: Data-Driven Experience Analysis & Assumption-Setting (GAM)

**Status:** IN PROGRESS (plan locked 2026-07-15; Slice 1 shipped 2026-07-21 as
PR #141/ADR-139; Slice 2a — frequentist tensor MI surface + `MI_x(y)` grid —
shipped 2026-07-21, ADR-140; Slice 2b-surface — Bayesian credible-interval MI
surface — shipped 2026-07-22, ADR-141; Slice 2b-projection — CMI/MP-style
mean-reverting posterior-predictive MI projection — shipped 2026-07-22, ADR-142;
Slice 2c — `MortalityImprovement`-compatible custom-scale emission
(`ImprovementScale.CUSTOM` / `from_grid`) — shipped 2026-07-22, ADR-143)
— this is the active epic (A4′). Slice 2 is sub-decomposed 2a/2b/2c and Slice 2b
is further split **2b-surface / 2b-projection** (see CONTINUATION). Slice 3
(hierarchical partial pooling / credibility) shipped 2026-07-22 as PR #146/ADR-144.
**Slices 1–3 are complete. Slice 4 (CLOSES EPIC) is sub-decomposed 4a/4b/4c/4d
(see CONTINUATION); Slice 4a — the `polaris experience improvement` CLI surface
— shipped 2026-07-22 as PR #147/ADR-145. Slice 4b (fit diagnostics + assumption
versioning + config wiring) is itself sub-decomposed 4b-1/4b-2/4b-3: 4b-1
(`polaris experience fit` diagnostics) shipped as PR #148/ADR-146; 4b-2 (append-only
assumption versioning) shipped as PR #149/ADR-147; 4b-3 (wire
`ImprovementScale.CUSTOM` into `--config` + `AssumptionSet`) shipped 2026-07-23 as
ADR-148 (this session). Slice 4c (loaders + insured validation deck + `mgcv`
oracle) is NEXT.** The optional
`pymc`-NUTS audit path for the projection is deferred/gated on the maintainer
confirming the ADR-141 backend direction (see CONTINUATION Open Questions). Note
(ADR-141): the
PLAN's locked `bambi`/`pymc` `laplace` backend is defective in the installed
versions (`NullTypeGradError` on HSGP + offset), so the surface ships as the
identical HSGP math in closed form (a pure-NumPy/SciPy reduced-rank GP —
deterministic, core-only); `pymc`/`bambi` are deferred to the projection slice.
The backing `CONTINUATION_experience_gam.md` is IN PROGRESS.

**Source / derivation.** Reframes ROADMAP Milestone 6.1 (Experience-Monitoring
Automation) and the 2026-07-05 review's C2, re-ranked to the active Tier-A epic
by `COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md` §3/§5 (last unstarted roadmap
milestone; realises the ML-native thesis in CLAUDE.md §1). Scope shaped by a
maintainer scoping discussion (2026-07-15): the meaningful ML enablement is an
**interpretable GAM layer** for experience analysis and basis-setting — the
auditable middle between the grouped-A/E credibility already in
`analytics/experience_study.py` and the black-box XGBoost in
`assumptions/ml_mortality.py` — NOT a black-box `--retrain-ml` loop.

## Overall Goal

Give actuaries a data-driven, **interpretable** way to isolate standard
feature effects and set mortality (then lapse) bases from experience, with
robust uncertainty. The headline capability is a **tensor mortality-
improvement (MI) surface** — age-varying improvement `MI_x(y)` estimated from
experience and emitted as a `MortalityImprovement`-compatible scale. Thin
segments borrow strength from the population via smooth partial pooling (a
continuous generalization of the limited-fluctuation `Z` already in
`ExperienceStudy`).

## Design Anchors (carry into every slice)

1. **Model on the log-mortality scale, offset by the *static select* base.**
   `log μ = log[exposure · q_base(x, d)] + η`, Poisson / negative-binomial.
   `q_base(x, d)` is the existing VBT/CIA **select-and-ultimate** table via
   `MortalityTable.get_qx_vector(ages, sex, smoker, durations)` — it pins the
   dominant age×duration structure so the GAM estimates only the company A/E
   level, the calendar trend, and small residual shape. **The base offset MUST
   be a single-reference-year static table, never a generational/projected
   one** — else the fitted trend is residual-vs-assumed improvement, not MI.
2. **A/E parameterization, not direct-qx.** For MI the two are identical on the
   calendar gradient (the age-only offset is absorbed by a free age term), but
   A/E gives variance reduction on thin data, a bias/variance dial, and a
   native multiplicative `MI_x(y)` output that plugs straight into
   `MortalityImprovement.apply_improvement` (`q(Y)=q(base)·Π(1−MI_x(y))`).
3. **The three-axis (Lexis) identifiability rule.** Coordinates are attained
   age `x`, policy duration `d`, calendar year `t`, with `issue_year = t − d`.
   A linear improvement (period) trend is confounded with a linear issue-year /
   secular-underwriting-drift trend. **Default attribution: the calendar
   gradient is improvement; the issue-year term is constrained to zero.** An
   optional `underwriting_era` factor exposes the alternative for cedants with
   a known UW change in the experience window (see Open Decisions — this is the
   locked default with the escape hatch).
4. **Duration enters twice, deliberately.** Its primary effect is the select
   base offset `q_base(x,d)`; a penalized residual smoother `s_resid(d)`
   (shrunk → 0) catches only company-specific deviation from the standard
   select wear-off. Improvement is duration-invariant in this form.
5. **Interpretable + auditable over predictive.** Every fitted effect ships
   with a shape function + uncertainty band. Validate against an offline
   `mgcv`-via-`rpy2` oracle and synthetic-recovery tests — never ship the R
   dependency at runtime (protects the Python-native thesis + Docker/CI).
6. **Additive / byte-identical to the engine until a surface slice.** New
   modules only; no pricing-path or golden change until Slice 4 wires a CLI
   surface. All fixtures pin dates (ADR-074 guard). If any exported/fixture CSV
   is referenced by a test, update the Dockerfile COPY + `.dockerignore`
   allowlist in the same PR (#61/#66 trap).
7. **Grouped Lexis cells are the canonical input (not seriatim).** For the
   Poisson/NB GAM with a log-exposure offset, grouped exposed-and-deaths cells
   give **identical** smooth/coefficient estimates to seriatim (the grouped
   likelihood equals the seriatim likelihood up to a constant when covariates
   are constant within a cell) — so grouping is sufficiency, not compromise, and
   it collapses 10⁸–10⁹ policy-years to 10⁵–10⁶ cells. This is also the shape
   the public data ships in (SOA ILEC). A seriatim extract is folded in via an
   optional aggregator. **Carry both by-count and by-amount exposure/deaths; the
   by-amount basis is overdispersed (a few large claims dominate) → NB /
   dispersion parameter is mandatory there, optional for by-count.**

## Canonical Model Form (target, reached by Slice 2)

```
deaths(x,d,t,z) ~ NegBinomial(μ, α)
log μ = log[ exposure · q_base(x, d) ]     # offset — static select-&-ultimate base
        + β0                                # company A/E level
        + te(x, t)                          # tensor MI surface (age-varying improvement)
        + s_resid(d)                        # residual select deviation (penalized → 0)
        + Σ_k f_k(z_k)                       # sex, smoker, band, product, UW class, channel
        + segment terms                     # hierarchical partial pooling (Slice 3)
MI(x,y) = 1 − exp( te(x,y) − te(x,y−1) )    # exported reduction grid → apply_improvement
```

## Backends (staged with the slices that use them)

- **Slice 1 — `statsmodels` `GLMGam`** (frequentist penalized splines,
  GLM-native, maintained). Optional richer marginal backend: `interpret` (EBM /
  GA2M) — deferred, not a Slice-1 dependency.
- **Slice 2+ — `bambi` (on `pymc`)** for the tensor surface: `hsgp(x, t, …)`
  Hilbert-space-GP gives an **anisotropic** 2-D smoother (ARD length-scales =
  the two smoothing parameters), honest posterior credible intervals on
  `MI_x(y)`, and posterior-predictive **forward projection** (the prior is the
  extrapolation model — RW2 fans out linearly; Matérn mean-reverts to a
  settable long-term rate). Offer two run modes: MAP+Laplace (fast point + SE)
  and full NUTS (audit / credible intervals).

**Dependency plan (locked pins; added with the slice that imports them, not
ahead of it):** Slice 1 adds `statsmodels>=0.14` to the `[ml]` extra; Slice 2
adds `bambi>=0.14` and `pymc>=5.16` (pulls `pytensor`). `pymc` is compile-heavy,
so it lands only when Slice 2's code imports it — Slice 1 CI stays lean. Both
guarded behind the `[ml]` optional extra; the module import-errors with an
actionable message when `[ml]` is absent (mirrors `ml_mortality.py`).

## Data Sources & Strategy

Industry experience data is intercompany-**aggregated**; true seriatim is
confidential to contributing companies, and licensed insured files are not
repo-redistributable. The strategy separates *building/testing the method* from
*validating on insured data*, and ships **loaders, not data** (mirrors
`scripts/convert_soa_tables.py` + the QA-golden pattern):

- **Develop & unit-test the tensor-MI engine on population data — Human
  Mortality Database (mortality.org).** Free (account + citation), programmatic,
  gives **Deaths and Exposures as age × calendar-year matrices** by sex — the
  exact `(age, year)` Lexis structure `te(age, calendar_year)` consumes.
  Population, not insured, but ideal for engineering/regression-testing the
  improvement surface on *real* data before touching insured files. **CHMD**
  (Canada) / **USMDB** (US states) share the format.
- **Fit & validate insured experience — SOA ILEC.** The 2019 Individual Life
  Mortality Experience report (observation years **2012–2019**, and prior
  vintages back to 2009) publishes a **grouped exposed-and-deaths flat file +
  interactive tool** under a data-use agreement. Its schema carries **all three
  Lexis axes** (issue age, duration, observation year) plus gender / smoker /
  plan / face band / preferred class, with **both policy- and amount-**exposure
  and deaths — a one-to-one match to this epic's model form and the anchor-7
  grouped contract. **SOA MIM-2021** ships an ILEC-derived insured dataset +
  improvement tool — a ready-made reference for the Slice-2 `MI_x(y)` output.
- **Canadian validation targets — CIA.** The annual Canadian Individual Life
  Experience study (to policy year 2022–23) and **CIA2014** (2009–2019;
  *already in this repo*) are published as **aggregated tables / workbooks**,
  not a row-level file — so CIA is a validation *target*, not a fit source. The
  CIA credibility-theory paper is directly relevant to Slice 3's partial
  pooling.

**Loaders-not-data rule:** provide `load_hmd()` / `load_ilec()` fetch-and-cache
helpers + a small **synthetic or sampled** in-repo fixture (respecting each
source's terms); keep large/licensed files **out of the Docker image and CI**
(anchor 6 / the #61/#66 trap). HMD is the primary real-data test fixture; ILEC +
CIA are the insured validation decks (the A4′ analogue of the A1′ validation
pack, wired in Slice 4).

## Decomposition

### Slice 1: Experience-data contract + marginal effect isolation (DONE)
- **Backend:** statsmodels `GLM` + `patsy` B-splines (regression splines — the
  robust de-risking choice; penalized/HSGP starts Slice 2). **Status:** DONE
  (shipped 2026-07-21, ADR-139; see `CONTINUATION_experience_gam.md`).
- **New module** `analytics/experience_gam.py` (sibling to
  `experience_study.py`). Defines the **canonical grouped-cell contract** (one
  row per covariate combination; anchor 7): keys `issue_age, duration_months,
  attained_age, calendar_year, sex, smoker, band, product, uw_class, channel,
  segment` → measures `central_exposure, death_count` and the by-amount pair
  `amount_exposed, death_amount`, plus an NB **dispersion** parameter (mandatory
  on the by-amount basis). Ships an **optional seriatim→grouped aggregator** so a
  cedant's row-level extract folds into the same contract. Builds the static
  select-base offset via `MortalityTable.get_qx_vector`, fits an **additive**
  A/E GAM (`s(attained_age) + s(duration) + Σ factors`, Poisson/NB), and exposes
  per-feature smooth effect functions + confidence bands.
- **Export** `export_to_mortality_csv()` writing a blended base×multiplier
  table in the Polaris CSV schema that round-trips through
  `MortalityTable.load()`.
- **No tensor, no hierarchy, no calendar term yet** — de-risks the data
  contract + offset + export plumbing before the hard modeling.
- **Tests:** grouped-vs-seriatim sufficiency (aggregating a synthetic seriatim
  set and fitting gives identical coefficients within tolerance); synthetic
  multiplier-surface recovery; by-amount overdispersion handled (NB dispersion >
  1 recovered); round-trip export→load identity; effect-CI coverage;
  import-guard when `[ml]` absent. ADR for the module + A/E design + grouped
  contract.

### Slice 2: Tensor MI surface (HEADLINE)
- **Sub-decomposed 2a/2b/2c** (CI-lean de-risking, mirrors Slice 1). **2a — DONE**
  (2026-07-21, ADR-140): frequentist tensor-product `te(x, t)` on the statsmodels
  backend, `MI_x(y)` grid via `1 − exp[η(x,y) − η(x,y−1)]` with a delta-method band,
  Design-Anchor-3 by construction (no issue-year term; real `underwriting_era`
  factor), Anchor-1 static-base guard. **2b — DONE** (split surface/projection):
  2b-surface (ADR-141) ships the Bayesian reduced-rank-GP credible-interval surface;
  2b-projection (ADR-142) ships the CMI/MP-style mean-reverting posterior-predictive
  `MI_x(y)` forward projection (deterministic; optional `pymc`-NUTS audit deferred/
  gated). **2c — NEXT**: `MortalityImprovement`-compatible custom-scale emission
  (`ImprovementScale.CUSTOM` / from-grid). Original Slice-2 spec (the full target)
  follows.
- **Backend:** bambi HSGP / pymc (2b). **Depends on:** Slice 1 merged.
- `te(x, t)` age-varying improvement with the static select-base offset +
  `s_resid(d)`; anisotropic HSGP; extract `MI_x(y)` grid **with credible
  intervals**; posterior-predictive projection with a settable long-term-rate
  anchor → emit a `MortalityImprovement`-compatible custom scale
  (`ImprovementScale.CUSTOM` or a from-grid constructor).
- Encodes the Design-Anchor-3 identifiability rule: default issue-year term
  constrained to zero; optional `underwriting_era` factor.
- **Tests:** recover a known age×year improvement surface from synthetic data;
  **recover a plausible improvement gradient from a real HMD age×year
  Deaths/Exposures slice** (see Data Sources — sanity, not a golden); MI grid
  matches an `mgcv` offline oracle within tolerance; projection anchors to the
  long-term rate; static-vs-generational-offset guard (a generational base
  offset is rejected / warned). ADR for the tensor form + attribution assumption
  + projection.

### Slice 3: Hierarchical partial pooling (credibility) — DONE
- **Backend:** reduced-rank GP + Laplace posterior (ADR-141), NOT bambi HSGP — the
  segment random effect is a ridge block with an EB-estimated variance; deterministic,
  core-only. **Status:** DONE (shipped 2026-07-22, ADR-144; PR #146).
- Segment-level MI/level deviations shrunk toward the global surface; generalizes
  `ExperienceStudy`'s limited-fluctuation `Z`. Thin segments borrow the population
  trend; shrinkage is estimated by empirical Bayes, not imposed. Sum-to-zero
  identifiability so per-segment credibility reflects each segment's own exposure.
- **Tests (all green):** a thin segment shrinks toward the global surface; a data-rich
  segment escapes pooling; the pooled estimate lies between the raw-cell and the global;
  credibility rises monotonically with exposure; EB recovers a known variance component;
  segment trend deviations shrink; deterministic; contract validation.
- **Deferred/harvested:** exposure-weighted centring; age-varying group-specific
  *smoother* (Pedersen GS/GI); per-segment forward projection; NB variance component.

### Slice 4: Surface + versioning + validation + docs (CLOSES EPIC)
- CLI `polaris experience improvement` (+ `polaris experience fit`);
  assumption versioning under `data/assumption_versions/` (study-date +
  credibility-weight tags, preserved history); effect-shape + MI-surface
  diagnostic plots; ARCHITECTURE + QUICKSTART; ADR.
- **Validation decks + loaders (per Data Sources & Strategy):** `load_hmd()` /
  `load_ilec()` fetch-and-cache helpers (loaders-not-data; large/licensed files
  excluded from the image + CI); an insured **A/E + improvement validation
  deck** against SOA ILEC / MIM-2021 and CIA aggregated tables (the A4′ analogue
  of the A1′ validation pack); the offline `mgcv`-via-`rpy2` oracle wired as a
  dev-only check. In-repo tests use a small synthetic/sampled fixture only.
- HARVEST FOLLOW-UPS, then `CONTINUATION_experience_gam` → COMPLETE.

## Explicitly Out of Scope (epic level)
- **New-data-source risk segmentation** (the maintainer's current work):
  carriers lack these fields on *historical* experience, so they cannot be
  validated retrospectively. That is a **forward / prospective-rating**
  capability (a later Phase-7 candidate) reusing this GAM machinery once the
  data exists — not part of this retrospective epic.
- Full black-box `--retrain-ml` automation loop (the original 6.1 framing);
  the XGBoost path in `ml_mortality.py` remains the predictive, non-interpretable
  alternative.
- Lapse experience: the module generalizes to lapse, but mortality (incl. MI)
  is Slices 1–4; lapse is harvested as a follow-up.

## Open Decisions (locked defaults; revivable by maintainer)
- **Identifiability attribution:** LOCKED default = calendar gradient →
  improvement, issue-year term constrained to zero, with an **optional
  `underwriting_era` factor** exposed for cedants with a known UW change
  (Design Anchor 3). Default chosen 2026-07-15; recorded here so an autonomous
  run does not re-open it.
- **Projection prior:** default Matérn HSGP mean-reverting to a settable
  long-term rate (CMI/MP-style); RW2 linear extrapolation offered as an
  alternative. Finalise in Slice 2's ADR.
