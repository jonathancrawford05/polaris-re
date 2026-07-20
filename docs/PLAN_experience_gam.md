# PLAN: Data-Driven Experience Analysis & Assumption-Setting (GAM)

**Status:** CONSTITUTED (plan locked 2026-07-15) — this is the next active
epic (A4′). Slice 1 is NEXT; the backing `CONTINUATION_experience_gam.md`
flips to IN PROGRESS when Slice 1 ships.

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

## Decomposition

### Slice 1: Experience-data contract + marginal effect isolation (NEXT)
- **Backend:** statsmodels `GLMGam`. **Status:** NEXT.
- **New module** `analytics/experience_gam.py` (sibling to
  `experience_study.py`). Defines the experience-record contract
  (`exposure, deaths, attained_age, issue_age, duration_months, calendar_year,
  sex, smoker, band, product, uw_class, channel, segment`), builds the static
  select-base offset via `MortalityTable.get_qx_vector`, fits an **additive**
  A/E GAM (`s(x) + s(d) + Σ factors`, Poisson/NB), and exposes per-feature
  smooth effect functions + confidence bands.
- **Export** `export_to_mortality_csv()` writing a blended base×multiplier
  table in the Polaris CSV schema that round-trips through
  `MortalityTable.load()`.
- **No tensor, no hierarchy, no calendar term yet** — de-risks the data
  contract + offset + export plumbing before the hard modeling.
- **Tests:** synthetic-recovery (data generated from a known multiplier surface
  → GAM recovers within tolerance); round-trip export→load identity; effect-CI
  coverage; import-guard when `[ml]` absent. ADR for the module + A/E design.

### Slice 2: Tensor MI surface (HEADLINE)
- **Backend:** bambi HSGP / pymc. **Depends on:** Slice 1 merged.
- `te(x, t)` age-varying improvement with the static select-base offset +
  `s_resid(d)`; anisotropic HSGP; extract `MI_x(y)` grid **with credible
  intervals**; posterior-predictive projection with a settable long-term-rate
  anchor → emit a `MortalityImprovement`-compatible custom scale
  (`ImprovementScale.CUSTOM` or a from-grid constructor).
- Encodes the Design-Anchor-3 identifiability rule: default issue-year term
  constrained to zero; optional `underwriting_era` factor.
- **Tests:** recover a known age×year improvement surface from synthetic data;
  MI grid matches an `mgcv` offline oracle within tolerance; projection anchors
  to the long-term rate; static-vs-generational-offset guard (a generational
  base offset is rejected / warned). ADR for the tensor form + attribution
  assumption + projection.

### Slice 3: Hierarchical partial pooling (credibility)
- **Backend:** bambi hierarchical HSGP. **Depends on:** Slice 2 merged.
- Segment-level MI/effect deviations shrunk toward the global surface (Pedersen
  GS/GI HGAM); generalizes `ExperienceStudy`'s limited-fluctuation `Z`. Thin
  segments borrow the population trend; shrinkage is estimated, not imposed.
- **Tests:** a thin segment shrinks toward the global surface; a data-rich
  segment escapes pooling; pooled estimate lies between raw-cell and global.

### Slice 4: Surface + versioning + validation + docs (CLOSES EPIC)
- CLI `polaris experience improvement` (+ `polaris experience fit`);
  assumption versioning under `data/assumption_versions/` (study-date +
  credibility-weight tags, preserved history); effect-shape + MI-surface
  diagnostic plots; ARCHITECTURE + QUICKSTART; ADR. Offline `mgcv`-via-`rpy2`
  validation oracle wired as a dev-only check.
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
