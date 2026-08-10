# Plan: a penalized tensor MI surface (P-splines with REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — promoted from the spline-diagnostics
epic (`PLAN_gam_spline_diagnostics.md`, COMPLETE 2026-08-08).
**Predecessors:** ADR-182 (the diligence harness), **ADR-184 + amendments 1–2**
(the diagnostic that produced the case for this).
**Total slices:** **7** (1–6 autonomous, 7 one maintainer run) — **revised
2026-08-09**, see below.
**Estimated scope:** ~7–9 dev-days autonomous + one `mgcv` conformance run and one
ILEC/HMD re-run, both maintainer-side. The largest single piece of numerical work in
the project to date.

> ## Revision 1 — 2026-08-09, after slice 3
>
> **The goal is now explicit: a Python estimator that can stand in for R's `mgcv`
> for this workflow.** The original plan treated `mgcv` as an optional oracle for one
> quantity. Slice 3 turned three separate claims into things that *must* be checked
> against it, and produced a measured reason the interval is not yet fit to publish.
>
> **What changed and why:**
>
> 1. **Slice 3 measured the penalized band at 87.1% against a nominal 95%** on a truth
>    the basis represents exactly, and localised the cause: `Vb` conditions on λ while
>    λ is itself a sampling quantity with real variance. The original slice 4 would
>    have shipped that to a reader with a caveat. **New slice 4 fixes it** — the
>    Kass–Steffey unconditional covariance — and a new **gate** forbids labelling
>    anything a 95% band until select-per-replicate coverage passes.
> 2. **A robustness defect blocks the study that would prove it.**
>    `select_lambdas_reml` aborts when a grid corner fails to converge (ADR-187
>    finding 5), which is why the unconditional coverage study is not yet delivered.
>    It is the first item of slice 4.
> 3. **The `mgcv` cross-check is promoted from a footnote to its own slice (5).**
>    `tr(F)`, the unconditional covariance and `gamma` are all *adopted from mgcv and
>    unverified*. One R run settles all three, and slice 5 builds the artifacts for it.
> 4. **A single global λ was considered and rejected** (ADR-187 amendment 1). The
>    evidence for it — λ_age looking unidentifiable — was an artifact of an age-flat
>    fixture: on a truth with age structure, λ_age's spread across replicates falls
>    from 5.50 decades to 0.75. And `te()` in mgcv is *defined* by one smoothing
>    parameter per marginal, so a global λ would move away from the parity goal.
> 5. **Old slices 4 and 5 become 6 and 7**, unchanged in scope but re-ordered behind
>    robustness and conformance — because slice 6 is where these numbers first reach a
>    human, and shipping an unverified `edf` beside an unverified band is the
>    "less auditable, not more" failure Anchor 4 exists to prevent.

---

## 1. What this fixes — stated narrowly, because the obvious answer is wrong

**It does not fix age 45 on ILEC.** Slice 4 of the diagnostics epic established
that age 45's climb is invariant to the calendar margin's flexibility — it survives
removing a whole polynomial order, moving the early-vs-late contrast by 0.01
points. A penalty is a *better-principled* way to choose flexibility; it is not a
remedy for something flexibility does not cause. Any framing of this epic as
"fixing age 45" would be a promise the previous epic already falsified, and it is
named here so nobody makes it later.

**What it actually fixes is that `df` is doing two jobs.** In the current model,
one integer sets both the basis dimension and the amount of wiggliness allowed.
That has three consequences, all of them demonstrated rather than argued:

1. **Complexity is a researcher degree of freedom.** `year_df` 4 → 3 moved a
   published ILEC finding (mean absolute difference vs SOA, 0.92% → 0.368%), and
   `df == degree` 3 → 2 improved agreement with SOA by a further 10% while cutting
   age-45 swing 4.5× on fixtures. Those were *hand* choices. Nothing in the fit
   selected them, and nothing recorded what else was tried.
2. **The same complexity is spent everywhere regardless of local information.**
   Three year parameters are estimated with wildly differing precision across the
   age range — deaths at 45 are ~24× scarcer than at 85 — and an unpenalized fit
   does not care. That is the mechanism ADR-184 measured: a 3.13-point swing at
   age 45 against 0.46 at 85, on a truth that is exactly flat.
3. **Lowering the order is a blunt instrument.** The linear rung removes the
   artifact *and* the ability to see a genuine 3.5-point climb. A penalty is
   precisely the tool that avoids having to make that trade globally.

**And there is direct evidence a better choice exists.** On real ILEC the quadratic
beat the shipped cubic on the one independent check — SOA's own expected deaths —
by 10% (mean absolute difference) and 35% (mean difference), at equal dispersion
and one fewer parameter. Something in the neighbourhood of "less than cubic" was
right, and it took two epics and a maintainer run to find by hand. **REML should
find it in one fit.** That is the epic's thesis and §6 turns it into a falsifiable
prediction.

## 2. Design anchors

Numbered so slices can cite them, in the style of the A4′ epic.

**Anchor 1 — the unpenalized fit is the λ=0 oracle, exactly.** At zero penalty the
new fitter must reproduce `TensorMIModel` to floating-point tolerance on identical
inputs. Not "close", not "statistically indistinguishable". This is the strongest
correctness test available and it is free, because the oracle already exists and is
already tested.

**Anchor 2 — the surface and band extraction layer does not change.** Every band is
`√(cᵀVc)` on a contrast row and is agnostic to how `V` was formed; the window
contrast, the telescoping property and the quasi-Poisson φ scaling all compose the
same way. **If this layer needs modifying, the covariance swap is wrong** and that
is the signal to stop, not to edit the layer.

**Anchor 3 — determinism is a requirement, not a discovery.** ADR-184 amendment 2
established that reports are *not* byte-for-byte reproducible: rounding ties flip
when a parallel sum reassociates. λ selection introduces an optimizer whose output
can move far more than the ~1e-14 that caused that. **λ must be quantised before it
reaches the covariance**, and the tolerance must be chosen and justified in slice 2
rather than discovered in slice 5.

**Anchor 4 — effective degrees of freedom are reported or the fit is worse than
what it replaces.** An unpenalized fit at least tells you its complexity in the
arguments. A penalized fit that hides `edf` behind an opaque λ is *less*
auditable, not more. A fitted `edf` sitting at its `k` ceiling is a caveat the
report must raise itself.

**Amended 2026-08-08 (PR #187 review) — what gets reported, exactly.** Slice 1
shipped a per-margin split that was first inert and then, once fixed, well-defined
but **non-additive**: `edf_age` and `edf_year` overlap and do not sum to
`edf_total`, so a reader doing the obvious arithmetic gets a wrong answer. Two
numbers now, with different jobs:

| Quantity | Definition | Role |
|---|---|---|
| **Per-term EDF** | `tr(F)` over the tensor block, `F = (XᵀWX + S)⁻¹ XᵀWX` | **Headline.** This is what `mgcv` reports per smooth, and it **closes**: tensor-term EDF + factor-block EDF = `edf_total` |
| **Per-penalty shrinkage** | one per marginal penalty | **Margin diagnostic**, and it must be labelled **dimensions *removed*, not dimensions *spent*** |

The labelling is the load-bearing half. A number called "edf_year" reads as
"degrees of freedom the calendar margin is using", invites addition, and is wrong
on both counts. Called a *shrinkage* it reads as what it is — how much that penalty
took away — and nobody sums it.

This keeps Anchor 4's requirement that complexity is visible per margin while every
published number is exactly defined and the arithmetic closes. **Not settled until
validated against real `mgcv`** — see §7.

**Anchor 5 — `k` is an upper bound checked against `edf`, never a tuning knob.**
The rule is Wood's: choose `k` generously, fit, confirm `edf` sits well below it,
raise `k` if it does not. Concretely — HMD's 30 years support `k` 10–15; **ILEC's
eight distinct calendar years do not support 10**, where a `k=10` margin has more
basis functions than data points. 6–8 there. "10 basis vectors" is not a universal
answer and this anchor exists because it was nearly adopted as one.

**Anchor 6 — the unpenalized path stays.** `TensorMIModel` is not deleted or
silently re-pointed. Every committed report was produced by it, the QA goldens
depend on nothing moving, and Anchor 1 needs it alive as the oracle.

**Anchor 7 — added 2026-08-09, AMENDED 2026-08-09 (maintainer) — an interval is not
published *without its measured coverage* until its coverage is measured under the
procedure that produced it.**

> **Amendment (maintainer decision, 2026-08-09).** The original anchor read as a bar on
> *display*. It is not. **The band may keep being shown.** What the failing gate forbids
> is the unqualified **nominal label** — calling it a 95% band when it measures 85%.
>
> The standing obligation while it is shown is threefold, and slice 6 owns all of it:
> quote the **measured** rate rather than the nominal one; state a **reason for the
> deviation** beside it; and keep the target live. The anchor closes when we either
> reach nominal coverage or record a decision that it is not achievable or not worth
> pursuing — and either of those is a result, not a failure.
>
> This is a narrowing, not a relaxation: "show it with the number it actually achieves
> and why" is a stronger requirement than the pre-gate status quo, which showed a band
> whose coverage nobody had measured at all. Slice 3 measured coverage
*conditional* on λ and found 87.1% against a nominal 95%. Conditional coverage is a
statement about the formula; **unconditional coverage — select λ per replicate, fit,
count — is a statement about what a user gets**, and it is the only one that licenses
the label "95%". This anchor is why slice 4 exists and why slice 6 sits behind it.
It applies to the delta-method bands too, which is what makes slice 3's finding 1 a
release-grade result rather than a reassurance.

**Anchor 8 — added 2026-08-09 — anything adopted from `mgcv` is marked adopted until
`mgcv` has been run.** Three quantities now carry this: `tr(F)` as the per-term EDF,
the Kass–Steffey unconditional covariance, and Wood's `gamma`. Each is a defensible
choice *because* a mature reference implementation makes it, and none of that is
evidence about **our** implementation of it. Slice 5 converts them; until it does,
every document that quotes them says "adopted, not verified" — and a conformance run
that **refutes** one is a successful run that changes the anchor, not a failed slice.

## 3. Slices

### Slice 1: the penalized fitter core, at fixed λ (autonomous — no data)

- **Status:** **DONE (2026-08-08)** — `experience_gam_penalized.py`, 11 tests,
  **ADR-185**. Both limits verified. **Two plan assumptions were wrong:**
  - **patsy cannot build a P-spline basis.** It always clamps boundary knots, so a
    difference penalty over it does not annihilate linear trends (step spread
    5.6e-01 against 8.9e-16 on a properly extended uniform sequence). The module now
    carries two knot schemes and **Anchor 1 is amended**: λ=0 reproduces
    `TensorMIModel` exactly in the *clamped* scheme, which verifies the fitting
    machinery against the oracle; it cannot also hold in the production scheme
    because a different basis is the point.
  - **IRLS must converge on deviance.** At λ=1e12 the coefficients never settle to
    a `max|Δβ|` tolerance while the deviance has stabilised within 8 iterations.
- **Depends on:** nothing

**Scope.** Marginal B-spline bases `B_age (n×k₁)` and `B_year (n×k₂)`; the tensor
design by row-wise Kronecker product; Kronecker-structured second-difference
penalties `S_age = DᵀD ⊗ I` and `S_year = I ⊗ DᵀD`; penalized IRLS solving
`(XᵀWX + Σλⱼ Sⱼ) β = XᵀWz` at **fixed, caller-supplied λ**. No selection yet — one
hard thing at a time.

`statsmodels` cannot supply this. `GLMGam` + `BSplines` penalizes and
`select_penweight` selects, but the smooths are **additive only** — there is no
tensor-product class (verified on 0.14.6). The Kronecker design and penalty are
ours to build; the IRLS loop can still lean on statsmodels for the family and link.

**Tests.**
- `test_zero_penalty_reproduces_the_unpenalized_fit` — **Anchor 1**, on the
  existing ILEC-shaped and HMD-shaped fixtures, to ~1e-10 on the fitted surface.
- `test_infinite_penalty_shrinks_to_the_penalty_null_space` — a second-difference
  penalty leaves linear functions unpenalized, so as λ→∞ the fitted MI must become
  **constant in year** at every age. That is a closed form, and it is the same
  quantity `df=degree=1` produced in ADR-184 amendment 1 — so the two
  implementations can be cross-checked against each other.
- `test_effective_df_falls_monotonically_in_lambda` — `edf = tr(H)` between the
  two limits, bounded by `k` above and by the null-space dimension below.
- `test_the_penalty_is_isotropic_under_rescaling` — rescaling `calendar_year` to
  a different origin must not change the fitted surface. Difference penalties are
  scale-dependent by construction, so this is where that bites, and it must be
  handled explicitly rather than left to whatever the data happens to look like.

**Acceptance criteria.** Anchor 1 holds exactly. Nothing in `products/` moves;
`tests/qa/` goldens untouched.

---

### Slice 2: λ selection by REML, and the determinism it threatens (autonomous)

- **Status:** **DONE (2026-08-08)** — **ADR-186 + amendments 1-2**, 26 tests
  (was 15), across two review rounds.
  **Anchor 3 resolved by design rather than by management:** selection is a
  deterministic grid, so λ is a grid point and reproducible by construction — no
  optimiser state, nothing to quantise. The plan's fallback became the design, and
  `lambda_grid_step` records the resolution that bought it — **on fits from
  `fit_reml()`**, which is the entry point that does selection and fitting together.
  It shipped inert and was wired in amendment 1; amendment 2 then had to correct two
  docstrings that still pointed at the two-step dance, and thread the grid step so
  the value reported is the value swept.
  **Anchor 4's reporting fix landed:** `edf_tensor` (additive, closes against
  `edf_factors`) plus shrinkages labelled *removed*.
  **Thesis supported at fixture scale**, 2.3x RMSE improvement over the hand-tuned
  quadratic on a truth outside the penalty null space — and the 40x figure from a
  truth *inside* it is rejected as unrepresentative rather than quoted.
- **Depends on:** Slice 1

**Scope.** Outer optimisation of the (Laplace-approximate) REML criterion over
`log λ`. **REML rather than GCV**, deliberately: GCV undersmooths and is prone to
multiple minima, which on an eight-year window is not a theoretical concern.

**Also in this slice: the Anchor-4 reporting fix.** Slice 1's per-margin `edf` is
non-additive and its field names invite addition. Replace with the two quantities
the amended Anchor 4 specifies — `tr(F)` over the tensor block as the headline
per-term EDF, and the per-penalty shrinkages renamed to say *removed* rather than
implying *spent*. Deferred here rather than patched into slice 1 on maintainer
direction (PR #187 was approved and out of draft, and an mgcv-consistent definition
cannot be validated against mgcv in this container anyway).

**Tests for it.** The additivity that the current split lacks is the whole point, so
assert it: tensor-term EDF plus factor-block EDF equals `edf_total` to floating
point, on a fixture that *has* factors — without them the identity is trivial and
the test says nothing. And the shrinkages keep slice 1's two-sided guard: saturate
one margin and only its own shrinkage saturates.

**Anchor 3 is the hard part of this slice, not the optimiser.** The plan is:
quantise `log λ` to a fixed number of significant digits **before** it is used to
form the covariance, so a converged λ that differs in its 12th digit across runs
produces a bit-identical `V`. The quantisation grid must be coarse enough to
absorb optimiser jitter and fine enough that `edf` does not visibly step. Slice 2
must **measure** both, not assert them.

**Tests.**
- `test_reml_recovers_known_smoothness` — inject surfaces of graded true
  wiggliness (constant, linear-in-year, genuinely curved) and require the selected
  `edf` to increase monotonically across them. **Two-sided by construction**: a
  selector that always picks maximum smoothing would pass the constant case and
  fail here, which is the ADR-182 discipline this project applies to every verdict.
- `test_lambda_selection_is_reproducible_across_processes` — the actual guard for
  Anchor 3, run in separate processes as the determinism work in ADR-182 was, not
  two calls in one interpreter. That distinction has already caught one false
  determinism claim in this project.
- `test_edf_does_not_step_visibly_under_quantisation` — the other side of the
  same trade.
- `test_selection_is_not_worse_than_the_hand_choice` — on the ILEC-shaped fixture,
  REML's selected fit must have SOA-comparison error no worse than the hand-tuned
  quadratic. If it is worse, the epic's thesis is in trouble and that is worth
  knowing at slice 2 rather than slice 5.

**Acceptance criteria.** A stated λ quantisation with the measurements that
justify it. Reproducibility across processes. `edf` recovering graded smoothness.

> **Discharged 2026-08-08, but only on the second attempt for the first criterion.**
> The quantisation was *stated* (`REFINE_STEP`, 0.25 decade) while
> `test_edf_does_not_step_visibly_under_quantisation` — the thing that **measures**
> it — was dropped without record, so the criterion read as met when half of it was
> (PR #188 review [P1]). Restored and now measured; a second test sweeps a
> non-default step so the recorded resolution is checked against the one actually
> used rather than against the module constant. The lesson is about the criterion's
> wording, not the slice: "stated **with the measurements**" was doing real work in
> that sentence and a status line claiming it was satisfied did not check it.

---

### Slice 3: Bayesian bands, and proving Anchor 2 (autonomous)

- **Status:** **DONE (2026-08-09)** — **ADR-187**, 34 module tests (was 26), across
  one review round that changed two of the three original findings.
  **Anchor 2 came out neither satisfied nor violated**, and the distinction is the
  slice's main structural result: the covariance swap needed *nothing* (Wood's `Vb`
  drops straight into `√(cᵀVc)`), while the design *rebuild* could not be reused
  because it goes through patsy and slice 1 established patsy cannot express this
  basis. Basis incompatibility, not covariance incompatibility.
  **The anchor also assumed a shared layer that did not exist** — three
  byte-identical copies of the band arithmetic lived in `experience_gam.py`, one of
  them (RRGP) already fed by a non-patsy design. Extracted to
  `mi_surface_from_design()` rather than copied a fourth time.
  **Coverage measured for both estimators**, and the pre-registered hypothesis
  below is **falsified** — the committed delta-method bands are calibrated.
  **Two results were withdrawn in review** once a corrected selection seed showed
  REML λ selection is unstable across replicates (~5 decades of log10 λ_age on the
  same truth): the "2.4 points" coverage cost and the claim that the penalized
  estimator degrades further under misspecification. **One blocker was found and
  left unfixed on purpose** — `select_lambdas_reml` aborts when a grid corner fails
  to converge (ADR-187 finding 5), which slice 4 must fix before it can run the
  selector on the real book.
- **Depends on:** Slice 2

**Scope.** `Vb = (XᵀWX + S)⁻¹ φ` — Wood's Bayesian covariance — handed to the
**existing** surface extractor unchanged.

**This slice is also the first honest coverage test this project has ever run.**
The current delta-method bands have never been checked against their nominal rate;
they are asserted to be 95% because that is what the formula says. Simulation makes
it measurable: fit many seeded replicates of a known surface and count how often
the nominal 95% band contains the truth.

**Tests.**
- `test_the_existing_extractor_consumes_the_bayesian_covariance_unchanged` —
  Anchor 2, asserted structurally: the window contrast, the telescoping identity
  and the φ scaling all still hold.
- `test_nominal_coverage_is_approximately_nominal` — across ~200 replicates, the
  95% band covers the true MI within a stated tolerance. Report the number; do not
  round it to "about right".
- `test_unpenalized_delta_method_coverage_is_measured_too` — **the comparison is
  the point.** If the existing bands under-cover at the death-poor young end, that
  is a finding about every committed report, and it should be published whichever
  way it comes out.

**Acceptance criteria.** Coverage measured and stated for both estimators. Anchor 2
held without editing the extractor.

> **Discharged 2026-08-09, with the registered hypothesis falsified and one
> criterion met only in spirit.**
>
> *Coverage measured and stated* — yes, at 200 replicates against nominal 95%, over
> three truths chosen to separate the flattering regime (constant MI, inside the
> penalty null space) from **band calibration** (quadratic MI: outside the null
> space, exactly representable by both bases) from **bias** (a sine cycle neither
> basis resolves). ADR-187 carries the table. **Stated with a caveat the criterion
> did not anticipate:** the penalized rows are conditional on a λ that is itself a
> wide-variance draw, so their decimals are provisional and only their direction is
> published. The unconditional (select-per-replicate) study that would settle it is
> **not delivered** — it is blocked by ADR-187 finding 5.
>
> *The registered hypothesis is **falsified**.* The delta-method bands do **not**
> under-cover at the death-poor young end: 95.7% / 95.9% overall, and young ages are
> the best-covered region. The bands in the committed reports stand, and ADR-184's
> age-45 artifact is a statement about the point estimate's spread rather than about
> the interval. Published as it came out, per the criterion.
>
> *Anchor 2 held **without editing the extractor**, but not without touching the
> module.* The band arithmetic was extracted from three byte-identical copies into
> one shared function that all four paths now call. No behaviour changed and 1227
> analytics tests passed unmodified — but the criterion as written ("without editing
> the extractor") reads as satisfied only if "the extractor" means its behaviour. It
> is recorded as met-in-spirit rather than quietly ticked, because a fourth copy
> would have satisfied the letter and destroyed the intent.

---

### Slice 4: selector robustness and an interval that does not condition on λ (autonomous)

- **Status:** **DONE (2026-08-09)** — **ADR-188**, 51 module tests (was 34) plus 10 on
  the study harness, and **the gate does NOT pass**.
  All three pieces shipped: the abort became a scored rejection with the count carried
  onto the fit, the Kass–Steffey unconditional covariance landed with a variance cap
  derived from the selector's own bounds, and `gamma` entered as the scale parameter
  (exactly inert at 1.0, so slice 2's tests stand unchanged as a regression guard).
  **Anchor 7 is discharged as measured-and-failed**, which is the outcome the anchor
  was written to make visible rather than a failure of the slice — see below.
- **Depends on:** Slice 3

**Why this slice exists, and why it was not in the original plan.** Slice 3 measured
the penalized band at **87.1% against a nominal 95%** on a truth the basis represents
exactly, and traced the shortfall to `Vb = (XᵀWX + S)⁻¹φ` **conditioning on λ** while λ
itself is a sampling quantity. The original plan went straight from bands to harness
integration, which would have shipped that interval to a reader with a caveat instead
of a fix. This slice is the fix.

**Three pieces, in dependency order.**

1. **The abort must go first** (ADR-187 finding 5). `select_lambdas_reml` raises when a
   grid point fails penalized IRLS — `log10 λ = (-1, 8)`, essentially unpenalized in
   age and saturated in year, on roughly one replicate in a hundred — and the whole
   search dies with it. **Decision: score a non-converging point as `+inf` and
   continue.** A λ whose own fit does not converge is not a λ to select, so treating
   it as infinitely bad is the right answer rather than a workaround; the alternatives
   (damping the IRLS step, raising the cap) make the search slower to hide a point it
   should be rejecting. The count of rejected points is recorded on the fit, because a
   search that silently discarded half its grid is a different object from one that
   discarded nothing.

2. **The unconditional covariance** — Wood's `Vb'`, the Kass–Steffey correction that
   `mgcv` exposes as `vcov(..., unconditional = TRUE)`. This adds the curvature of the
   REML criterion with respect to `log λ` back into the parameter covariance, so the
   interval widens by roughly the amount λ's own uncertainty warrants. It is the
   direct answer to the 87%, and it is the piece most likely to move coverage back
   toward nominal.

3. **Wood's `gamma`** — the multiplier on the effective-degrees-of-freedom cost in the
   selection criterion (his recommended 1.4), included **for parity, not as a fix**.
   ADR-187 amendment 2 is explicit that the "REML undersmooths" direction was measured
   on the age-flat fixture and **does not reproduce** on an age-varying one. Shipping
   `gamma` as a remedy for a bias this project has not demonstrated would be adopting
   a number because a reference implementation uses it — the exact move `tr(F)` is
   already carrying as a caveat. It defaults to 1.0 and its effect is measured.

**Tests.**
- `test_a_non_converging_grid_point_is_rejected_not_raised` — reconstruct the known
  failure (quadratic fixture, seed 1098) and require selection to complete, with the
  rejected-point count exposed.
- `test_the_unconditional_band_is_wider_than_the_conditional_one` — the correction is
  additive in the covariance and must widen, never narrow. A one-line direction check
  that would catch a sign error.
- `test_gamma_above_one_selects_a_smoother_fit` — higher `gamma`, lower `edf`,
  monotonically. Two-sided by construction.
- **`test_unconditional_coverage_of_the_shipped_procedure`** — see the gate below.

**Acceptance criterion, and it is a gate rather than a checklist item.**

> **Nothing in this project may be labelled a 95% band until select-per-replicate
> coverage has been measured and is acceptable.** Slice 3 measured coverage
> *conditional* on λ. The number a user needs is the **unconditional** one — select λ
> on each replicate, fit, and count — because that is the procedure they run. It was
> registered as blocked by the abort in slice 3 and is the first thing the abort fix
> unblocks. Measure it for the conditional band *and* the unconditional band, on both
> the age-flat and age-varying truths, and publish both whichever way they come out.
>
> **This bars the LABEL, not the display** — see the Anchor 7 amendment in §2
> (maintainer, 2026-08-09). The band keeps being shown; what it may not be called is a
> 95% band while it measures 85%.

**Cost note.** Per-replicate selection is ~200 penalized fits per replicate, so a
200-replicate study is ~40,000 fits. Budget it as a `@slow`-marked test or a
measurement script with a committed report; do not silently reduce the replicate count
to make it fit, and if it is reduced say so in the report (ADR-187's Monte-Carlo SE at
200 replicates is ~1.5pp and grows as `1/√R`).

> **Discharged 2026-08-09 — the gate was measured at the full 200 replicates and it
> does NOT pass.** `scripts/unconditional_coverage_study.py`;
> `docs/MEASUREMENT_unconditional_coverage.md` carries the report.
>
> | truth | conditional | **unconditional** | floor |
> |---|---:|---:|---:|
> | age-flat | 0.8201 | **0.8516** | 0.9192 |
> | age-varying | 0.8200 | **0.8581** | 0.9192 |
>
> Three results, all of which change what later slices may say:
>
> 1. **Kass–Steffey is directionally right and quantitatively insufficient** — +3.2 and
>    +3.8 points against a ~13-point shortfall, about a quarter of the gap, at ~12%
>    extra width. It was the plan's "piece most likely to move coverage back toward
>    nominal"; it moved it a quarter of the way.
> 2. **Selecting λ per replicate costs another ~5 points.** ADR-187's conditional
>    0.8710 becomes 0.8201 for the *same band* once λ is re-selected. That gap is
>    exactly what Anchor 7 exists to expose, and it means 87.1% was an optimistic
>    figure conditioned on knowledge the user does not have.
> 3. **The unpenalized delta-method band covers 10 points better** (0.9586 at 4.4x the
>    width, same truth, same seeds). This is a statement about the *interval* and does
>    not retract ADR-186's RMSE result for the point estimate — both can hold, and
>    jointly they say the penalized surface may be the better estimate inside an
>    interval that is not yet honest about it.
>
> **The failing gate does not license tuning.** `gamma`, a wider `k`, or moved bounds
> would each be choosing a number to make a measurement come out. The next step is the
> one the plan already sequenced: slice 5 settles whether the shortfall is *our
> arithmetic* (three quantities here are adopted from `mgcv` and unverified) or the
> estimator's shrinkage bias, which no covariance correction can reach.
>
> **A fourth result is about the study rather than the estimator.** The first
> age-varying fixture used a *linear* age gradient, which sits inside the age penalty's
> null space — so it reproduced the age-flat degeneracy under a different name (λ_age
> spread 5.50 decades, against 1.25 for the corrected quadratic and 5.00 for age-flat).
> Caught by measuring it, fixed before publication, and now asserted by a test on the
> *second* difference. Correcting it also **confirms ADR-187 amendment 1 at 200
> replicates rather than 8**, which is the stronger claim.

---

### Slice 5: the `mgcv` conformance suite (autonomous build, maintainer runs R)

- **Status:** **BUILT (2026-08-10)** — **ADR-189**, **PR #192**, 46 tests. Every deliverable below is
  committed, including the synthetic exchange and our own reference for it. **The R run
  itself has NOT happened** — it is the maintainer's, and until it does all three
  quantities remain *adopted, not verified* (Anchor 8 stands).
  Three things the build settled that the plan left open, and one it contradicted:
  - **The correctness claim is checkable without R.** `penalized_score_infinity_norm`
    verifies `||Xᵀ(y-μ) - Sβ||∞` at the exported coefficients — worst committed cell
    **2.19e-10** on O(1e2-1e3) counts — so the exported coefficients *are* the unique
    penalized MLE of the exported problem, and strict concavity pins what any conformant R
    solver must return. A test pins it against ADR-151's unpenalized version at `S = 0`.
  - **Level 4 cannot be one metric.** `mgcv` forms `Vc` only when `sp` was *estimated*, and
    at free `sp` the two sides select different λ. So it is the conditional `Vb` at fixed λ
    (exact, 1e-6) plus the *inflation ratio* at free λ (0.25) — and the second cannot
    separate a wrong Jacobian from a λ disagreement on its own. Stated, not hidden.
  - **A coarser synthetic grid breaks level 2, measured.** At a 2-year age step both
    penalties saturate at the bound and `edf_total` lands on exactly 4.000 — the bilinear
    null space. The fixture is narrowed in *range* instead, and a test guards it.
  - **`scalePenalty = FALSE` is itself adopted-not-verified** (no R here), so it is flagged
    the way Anchor 8 flags the other three rather than asserted: the script fails loudly if
    the argument is rejected, records the scaling artefacts the fit exposes, and the
    comparator refuses a reference that reports rescaling left on.
- **Depends on:** Slice 4

> **Slice 4 raised this slice's stakes rather than merely unblocking it.** Level 4 —
> `vcov(m)` against `vcov(m, unconditional = TRUE)` — is now the check that decides
> whether the failing gate is *our arithmetic* or the estimator's shrinkage bias. Those
> two have different remedies and the project cannot choose between them without an
> independent implementation. Run levels 1 and 4 first if the maintainer's R time is
> limited.

**This is the slice that turns "adopted, not verified" into "verified", and it is now
load-bearing rather than optional.** Three separate claims currently rest on "this is
what `mgcv` does" with nothing checking it: `tr(F)` as the per-term EDF (Anchor 4),
the Kass–Steffey unconditional covariance, and `gamma`. All three are settled by the
same R run.

**The construction, and why it is exact.** ADR-151's oracle works because the
unpenalized Poisson log-likelihood over a *shared* design is strictly concave, so its
maximiser is unique and any conformant solver must return it. **That argument extends
to the penalized case**: adding a positive-semidefinite penalty keeps the objective
strictly concave, so at fixed λ over a shared `(X, S_age, S_year)` the penalized MLE
is unique too.

`mgcv` accepts exactly that model through **`paraPen`** — a parametric term with
caller-supplied penalty matrices:

```r
m <- mgcv::gam(y ~ 0 + X, paraPen = list(X = list(S_age, S_year)),
               sp = c(lambda_age, lambda_year),      # level 1: fixed
               family = poisson(), offset = off, method = "REML")
```

**This is the whole design.** Because the design *and* the penalties are ours, every
disagreement is **our arithmetic** rather than a basis convention. Trying instead to
match `te(attained_age, calendar_year)` would compare two different bases, two
different knot placements and two different identifiability constraints, and
disagreement would be uninterpretable — the same reason Anchor 1 is asserted on the
fitted surface and never on coefficients.

**Five levels, each settling one claim.**

| level | R side | settles |
|---|---|---|
| 1 | `sp` fixed to ours | the penalized IRLS itself — **coefficients** must match element-wise |
| 2 | `sp` free, `method = "REML"` | our REML criterion and search — compare selected `sp` and `edf` |
| 3 | `sum(m$edf)`, `m$edf` | **`tr(F)`** — Anchor 4's definition, finally checked |
| 4 | `vcov(m)` vs `vcov(m, unconditional = TRUE)` | the Kass–Steffey correction slice 4 implements |
| 5 | `gamma = 1.4` | `gamma`'s reference behaviour |

Level 1 is the foundation: if coefficients agree at fixed λ, every later disagreement
is localised to selection, EDF or covariance rather than to the fit. **λ is comparable
here in a way it would not be under `te()`** — `sp` multiplies the supplied `S`
directly — but that is an assumption to *verify* at level 1, not to assume.

**Two datasets, and the licensing line runs between them.**

- **Synthetic (primary).** The exchange file is generated from a pinned seed and is
  **committed**, so the maintainer runs one R script against a file already in the
  repo and needs no data of their own. This case must be sufficient on its own to
  settle all five levels.
- **HMD USA and ILEC (scale check).** Real data exercises 125k cells, real
  overdispersion and real sparsity, which the synthetic case does not. The exchange
  file for these contains `deaths` and `log(exposure · q_base)` per cell — **that is
  the dataset at cell grain and is never committed** (Design Anchor 6,
  `DATA_LICENSING.md` §1). It is written to the maintainer's local working directory,
  consumed by R there, and **only the comparison report is committed** — max absolute
  coefficient difference, `edf` difference, λ ratio, max surface difference. Those are
  derived scalars, not experience.

**The R run happens AFTER slice 5 is built** (maintainer decision, 2026-08-09), and
the workflow below is designed around one fact: **the expensive resource is the
round trip, not the R compute.** Each round trip costs a session boundary, so the
build must make one run sufficient for many iterations.

**The governing decision: the mgcv output is a COMMITTED GOLDEN, not a live oracle.**
The R side is a pure function of the exchange file, so once the maintainer runs it, the
reference is committed and the implementer iterates entirely **offline** against it —
zero further R runs while fixing our arithmetic. A second run is needed only if the
design or penalties change (which changes the exchange file), or to add cases. This
differs from the original plan, which committed only the *comparison report*: for the
**synthetic** case there is no licensing reason to withhold the reference, since it is
generated from a pinned seed. (HMD/ILEC are unchanged — exchange local-only, report
committed, `DATA_LICENSING.md` §1.)

**Four build requirements that make the one run count.**

1. **The exchange file must be R-readable with no extra R packages.** Plain TSV plus a
   JSON manifest — `read.table` and `jsonlite::fromJSON` — **not** `.npz`, which an
   earlier revision of this plan specified and which R cannot read without `reticulate`
   or `RcppCNPy`. Floats at `%.17g` so the round-trip is exact.
2. **Export a matrix, not a case.** Extra cells cost seconds inside one R invocation and
   days as a second round trip. ~8-12 cells: three fixed-λ pairs (interior,
   age-saturated, year-saturated), free-`sp` REML, with and without a factor block, two
   `(k_age, k_year)` pairs. A single case can agree by accident — especially for the
   λ-relative-to-φ convention flagged in the PR #190 review, which a well-chosen cell
   exposes and an unlucky one hides.
3. **Dump intermediates, not just answers.** Per cell: coefficients, `sum(m$edf)`,
   `m$edf` per block, `m$sp`, both `vcov` variants, deviance, scale, iteration count,
   rank. "Coefficients differ by 0.03" is not actionable offline; the intermediates are
   what let the implementer bisect without asking for another run.
4. **Pin the environment in the output** — `sessionInfo()` and
   `packageVersion("mgcv")` — so a later disagreement cannot be quietly attributed to a
   version bump.

**The guard that matters: the comparator hashes the exchange file** and refuses to
compare a reference produced from a different hash. The worst failure mode available
here is iterating against a stale reference and declaring parity with a file R never
saw — a silent, confident wrong answer of exactly the class this epic keeps catching.

**Expected round trips: two to three.** Run 1 establishes the deltas; the implementer
fixes offline; run 2 confirms. A third only if reaching parity requires changing the
design or the penalty.

**Deliverables — the artifacts the maintainer needs.**
- `scripts/export_mgcv_case.py` — writes the exchange file (**TSV + JSON manifest**)
  for a named case: `synthetic`, `hmd-usa`, `ilec-banded`. Committed for `synthetic`.
- `scripts/mgcv_conformance.R` — reads it, runs all five levels over the case matrix,
  writes one reference JSON. **No arguments needed**; paths default. Exits non-zero on
  any R-side error. Requires only `mgcv` (base R recommended package) and `jsonlite`.
- `scripts/compare_mgcv_conformance.py` — reads both sides, verifies the exchange hash,
  prints a pass/fail table immediately and emits the committed report with the
  tolerance each level was judged against.
- `docs/RUNBOOK_mgcv_conformance.md` — the **two** commands and what each level means.

**Level ordering is now moot** and deliberately so. An earlier note recommended running
levels 1 and 4 first if R time was short; batching every level into a single invocation
removes the question, which is better than answering it.

**Tests.** The Python side is testable without R, and must be: the exporter round-trips,
the comparator's tolerances are asserted against a synthetic "known agreement" and a
seeded "known disagreement" so it can actually fail, and `mgcv_available()` gates the
R path exactly as ADR-151 established. **CI never grows an R dependency** — that
constraint is unchanged and is why the comparator is a separate script rather than a test.

**Acceptance criteria.** Levels 1–3 agree within stated tolerances on the synthetic
case, or the disagreement is recorded as a finding with the tolerance that failed.
`tr(F)` moves from *adopted* to *verified or refuted* — and refuted is an acceptable
outcome that changes Anchor 4 rather than a failure of the slice.

> **Discharged 2026-08-10 as BUILT-BUT-NOT-RUN, and the distinction is the whole status.**
>
> Every artefact is committed — exporter, R script, comparator, runbook, the synthetic
> exchange (`data/mgcv_exchange/synthetic`, 640 KB, seed-pinned and byte-reproducible) and
> our reference for it (90 KB). 45 tests, all passing with **no R present**: the exchange
> round-trips bit-exactly, the comparator is exercised against a known-agreement *and* a
> seeded known-disagreement per metric so every tolerance is shown to bite, and two
> staleness guards regenerate the committed exchange and the committed reference and compare.
>
> **The acceptance criterion above is NOT met, and cannot be met by this slice.** It asks
> whether levels 1–3 *agree*, which requires the R run. What is delivered is the thing that
> makes one R invocation sufficient for the two-to-three round trips the plan budgets. The
> criterion as written did not distinguish "build the suite" from "run it"; the status line
> now does, because a slice reported as discharged against a criterion it structurally
> cannot satisfy is the "stated **with the measurements**" failure PLAN slice 2 already
> recorded once.
>
> **What the build itself settled, without R:** the exported coefficients sit at the unique
> penalized maximiser (worst cell 2.19e-10), so any level-1 disagreement will be R's solver
> or a convention, never our fit. That is the strongest statement available before the run,
> and it is a measurement rather than an argument.
>
> **One tolerance pair is explicitly PROVISIONAL** — the free-`sp` metrics
> (`max_abs_log10_sp_diff` at 0.5 decades, `abs_edf_total_diff_free_sp` at 1.0). They are
> reasoned from the 0.25-decade grid and ADR-187 amendment 2's shallow profile, not
> measured against R. Named as provisional in `LEVEL_METRICS`, in the report the comparator
> emits, and in the runbook.

---

### Slice 6: harness integration and reporting (autonomous)

- **Status:** BLOCKED on slices 4–5
- **Depends on:** Slices 4, 5

*(Was slice 4 in the original plan. Moved behind robustness and conformance for a
reason worth stating: this slice is where the numbers reach a human, and shipping a
selected λ, an `edf` and a band to a reader before any of the three were verified is
precisely the "less auditable, not more" failure Anchor 4 exists to prevent.)*

**Scope.** `--penalized` on `scripts/experience_diligence.py`, defaulting **off**
(Anchor 6). The report gains `edf` per margin, the selected λ, the selection
criterion, the `k` ceilings, and — new since the original plan — **the count of
rejected grid points** and **whether the band is conditional or unconditional**.

**This slice owes the Anchor-7 amendment's three duties** (maintainer decision,
2026-08-09). The band is shown, so the report must carry: the **measured** coverage
rather than the nominal level; a **stated reason for the deviation** beside it; and the
target kept live rather than quietly dropped. A displayed band with a nominal label and
no reason is the exact thing the amendment forbids.

**Reporting obligations carried from slices 3–4**, all of which are ways the report
could mislead while being technically correct:
- Quote the coverage **direction**, not a point figure, unless slice 4's unconditional
  study produced a stable one.
- A band displayed beside a selected λ is **not jointly calibrated with it** unless
  the unconditional covariance is in use — so the report must say which it used.
- λ is one draw. ADR-187 amendment 1 bounds the instability at ~1 decade in age and
  ~2 in year on a structured truth; that is the number to caveat with, **not** the
  5-decade figure, which was fixture-specific.

**Performance budget, unchanged from the original plan** — the fitting stage may grow
by up to 10× wall-clock without being considered a regression, on the grounds that the
12.5 GB read dominates. If it exceeds that, say so in the report rather than absorbing
it.

**Tests.** Defaults byte-identical to the current harness; report schema additive so
the notebook's `DEGRADED` machinery handles older committed reports; the CLI refuses
`k` below the penalty null-space dimension with a sentence, not a traceback.

---

### Slice 7: real data, against predictions registered in advance (maintainer run)

- **Status:** BLOCKED on slices 4–6
- **Depends on:** Slices 4, 5, 6

*(Was slice 5.)* Two runs — HMD USA and ILEC duration-banded — with the same
pre-registration discipline the diagnostics epic used, and for the same reason: it
worked. §6 is the interpretation table, written before slice 1 existed and unchanged.

**Acceptance criteria.** The predictions in §6 are checked and recorded either way.
`MEASUREMENT_penalized_mi_surface.md` written. No data files added; Design Anchor 6
and `DATA_LICENSING.md` §5c (the SOA permission request is outstanding, so no new
absolute counts).

## 4. What is explicitly out of scope

- **Replacing the unpenalized path** (Anchor 6).
- **Fixing age 45** (§1).
- **Adaptive / spatially-varying penalties.** A single λ per margin is the target.
  Locally-adaptive smoothing is a real answer to "information varies across age",
  and it is a *later* epic, not a stretch goal for this one.
- **Re-deriving the committed findings.** Slice 5 compares; it does not overwrite
  `MEASUREMENT_experience_gam_*.md`.

## 5. Risks, in the order they are likely to bite

1. **The determinism problem is not solved by quantisation.** If the optimiser
   lands in different local minima across runs rather than merely jittering, no
   rounding saves it. Mitigation: measure the spread of selected λ across seeds and
   platforms in slice 2, and if it is multi-modal, fall back to a fixed λ grid with
   the selection *reported* rather than a continuous optimum.
2. **REML on an eight-year margin may be badly determined.** Eight distinct years
   is little information about smoothness. This may be where the honest answer is
   "the data do not identify λ for the calendar margin on ILEC", which would be a
   finding, not a failure.
3. **Anchor 1 turns out not to hold.** Most likely cause is an identifiability or
   centering difference between the hand-built tensor and patsy's. Worth budgeting
   real time for; it is also exactly the kind of thing the λ=0 test exists to catch
   early rather than at slice 5.
4. **Performance.** See slice 4's budget.

## 6. Predictions, registered before slice 1 is written

The diagnostics epic's interpretation table was written before the run and two of
its three rows described outcomes the diagnostic did not want. That is why its
result was trustworthy when it came back *against* the hypothesis. Same discipline
here.

| Prediction | If it holds | If it fails |
|---|---|---|
| **On ILEC, REML selects a calendar `edf` between 1 and 3** — i.e. near the quadratic that beat the cubic by hand | The epic's thesis is demonstrated: the penalty finds in one fit what took two epics and a maintainer run to find by hand | The selector and the independent SOA check disagree. **The SOA check wins** — it is the only comparison here not using our model on both sides — and the epic must explain the selector, not the data |
| **On HMD (30 years), REML selects a materially higher calendar `edf` than on ILEC** | The penalty is responding to information, which is the whole claim | A single λ per margin is not adapting across datasets, and the adaptive-penalty epic in §4 becomes the real answer |
| **Age 45's ILEC climb survives penalization** | Consistent with ADR-184 amendment 2; the climb is not a flexibility artifact and the rebuild was correctly scoped not to promise fixing it | Slice 4 of the diagnostics epic was wrong, which would be a significant retraction and must be published as one |
| **Bayesian bands are wider than delta-method bands at the death-poor young end** | The current bands under-state uncertainty exactly where ADR-184 says information is thinnest — a finding about every committed report | Delta-method was adequate; say so plainly and stop implying otherwise in the docs |

**A slice-5 run that contradicts row 1 is a successful run.** The epic's value is
in the measurement, not in the thesis being right — the same sentence PLAN §2 of
the A4′ epic used, which has now paid off twice.

## 7. Context for the next session

- **Read ADR-184 and its two amendments before writing any code.** Amendment 2 in
  particular: the artifact this epic's motivation rests on is real *and* does not
  explain the observation that motivated finding it. Both halves matter.
- **The oracle already exists.** `TensorMIModel` at λ=0 is the correctness spec,
  and `tests/test_analytics/test_experience_gam_ramp_diagnostic.py` already has
  ILEC-shaped and HMD-shaped fixtures with injected known surfaces. Reuse them
  rather than building new ones.
- **ADR-151's `mgcv` oracle is now slice 5, not a footnote** (revised 2026-08-09).
  It has three jobs, not one: `tr(F)` (Anchor 4), the Kass–Steffey unconditional
  covariance, and `gamma`. **And its construction changes.** The original note
  imagined comparing against a `te(attained_age, calendar_year)` fit; that would
  compare two different bases, two knot placements and two identifiability
  constraints, and any disagreement would be uninterpretable. Slice 5 instead ships
  **our** design and **our** penalties to `mgcv` via `paraPen`, so the model is
  identical and every disagreement localises to our arithmetic — the same
  correct-by-construction argument ADR-151 already makes for the unpenalized case,
  which extends because a PSD penalty keeps the objective strictly concave.
- **The maintainer can run R** (confirmed 2026-08-09). Slice 5's job is to make that
  run cheap: a committed synthetic exchange file so the primary conformance needs no
  data at all, and a local-only exporter for HMD/ILEC where only the *comparison
  report* comes back into the repo.
- **Do not tune until it agrees.** If REML selects something that disagrees with
  the hand-tuned quadratic, that is data about the selector.
- **The λ-instability headline is fixture-specific — quote ~1 decade, not 5**
  (ADR-187 amendment 1). The 5.50-decade figure came from an age-flat truth where the
  age penalty had nothing to identify. On a structured truth it is 0.75 decades in age
  and 1.75 in year, with RMSE across selected λ varying by only 1.13×.
- **The REML profile is shallow, not flat** (ADR-187 amendment 2): 3.85 REML units
  across 5.5 decades for a 2.6× change in `edf`. A better optimiser does not help,
  because the grid already locates each dataset's optimum. What helps is an interval
  that stops conditioning on λ. Do not respond to instability by rebuilding the search.

## 8. Open questions (for human)

- **Is a single global λ per margin enough?** §4 defers adaptive smoothing. If
  slice 5 shows `edf` wanting to differ across the age range — which ADR-184's
  information gradient predicts it might — the adaptive epic gets promoted rather
  than deferred.
- **Does the `mgcv` cross-check happen?** It needs R and it is the maintainer's
  machine. Real-data penalized fitting is precisely when an independent
  implementation is worth most.
- **Should the penalized path eventually become the default?** Not decidable
  before slice 5. Anchor 6 keeps the option open in both directions; flipping it
  would mean re-deriving every committed report, which is a separate decision with
  its own licensing implications under `DATA_LICENSING.md` §5c.
