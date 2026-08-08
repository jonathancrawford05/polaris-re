# Plan: a penalized tensor MI surface (P-splines with REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — promoted from the spline-diagnostics
epic (`PLAN_gam_spline_diagnostics.md`, COMPLETE 2026-08-08).
**Predecessors:** ADR-182 (the diligence harness), **ADR-184 + amendments 1–2**
(the diagnostic that produced the case for this).
**Total slices:** 5 (slices 1–4 autonomous, slice 5 one maintainer run)
**Estimated scope:** ~4–6 dev-days autonomous + a single ILEC/HMD re-run.
The largest single piece of numerical work in the project to date.

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

- **Status:** **DONE (2026-08-08)** — **ADR-186**, 23 tests (was 15).
  **Anchor 3 resolved by design rather than by management:** selection is a
  deterministic grid, so λ is a grid point and reproducible by construction — no
  optimiser state, nothing to quantise. The plan's fallback became the design, and
  `lambda_grid_step` records the resolution that bought it.
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

---

### Slice 3: Bayesian bands, and proving Anchor 2 (autonomous)

- **Status:** NOT STARTED
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

---

### Slice 4: harness integration and reporting (autonomous)

- **Status:** NOT STARTED
- **Depends on:** Slice 3

**Scope.** `--penalized` on `scripts/experience_diligence.py`, defaulting **off**
(Anchor 6). The report gains `edf` per margin, the selected λ, the selection
criterion, and the `k` ceilings — and raises its own caveat when any `edf` sits
near its `k`, per Anchor 4.

**Performance budget, stated in advance.** `k=12` per margin gives 144 interaction
columns against today's 24, so the ILEC design becomes ~125,676 × ~160 floats
(~160 MB) and each IRLS solve is a 160×160 system — cheap. The cost is the **outer
λ loop**: ~20–50 penalized IRLS fits where there is currently one. Budget: the
fitting stage may grow by up to 10× wall-clock without being considered a
regression, on the grounds that the 12.5 GB read dominates the run either way. If
it exceeds that, say so in the report rather than absorbing it.

**Tests.** Defaults byte-identical to the current harness; report schema additive
so the notebook's `DEGRADED` machinery handles the older committed reports; the
CLI refuses `k` below the penalty null-space dimension with a sentence, not a
traceback.

---

### Slice 5: real data, against predictions registered in advance (maintainer run)

- **Status:** BLOCKED on slices 1–4
- **Depends on:** Slices 1–4

Two runs — HMD USA and ILEC duration-banded — with the same pre-registration
discipline the diagnostics epic used, and for the same reason: it worked. §6 is
the interpretation table, written now.

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
- **ADR-151's `mgcv` oracle finally earns its keep here, and now has a second job.**
  An independent implementation of exactly this estimator, on an R-equipped machine,
  is the strongest external check available and is the maintainer's to run.
  Beyond checking the fitted surface, it is what **settles the Anchor-4 EDF
  definition**: `tr(F)` over the tensor block is chosen precisely because it is what
  `mgcv` reports per smooth term, and that claim is unverified until a `te(age,
  year)` fit in `mgcv` returns the same number on the same data. Until then the
  definition is **adopted, not validated**, and the plan says so rather than
  presenting a borrowed convention as a checked one. Still formally out of scope;
  worth running alongside slice 5.
- **Do not tune until it agrees.** If REML selects something that disagrees with
  the hand-tuned quadratic, that is data about the selector.

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
