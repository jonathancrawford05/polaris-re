# Plan: a Python GAM engine at parity with `mgcv` for the mortality-improvement workflow

**Source:** maintainer direction 2026-08-10 (the target model form, supplied as R).
**Predecessors:** ADR-189 + amendment 1 (the conformance suite, and the first run that
used it), ADR-185 through ADR-188 (the penalized fitter this epic reuses).
**Supersedes:** `PLAN_penalized_mi_surface.md` slices 6-7 — see §8.
**Total slices:** **7** autonomous, plus one deferred to a later epic. **Plus slice 1b**
(inserted 2026-08-16, PR #197 review): mgcv-native per-term extraction, split out of
slice 1 rather than left folded into slice 2 — see
`docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`.
**Estimated scope:** the largest numerical undertaking in the project. Sized honestly
below rather than optimistically.

---

## 1. The target, stated as the maintainer stated it

This is the *selected* model form from the maintainer's own exploration, and it is the
north star. Everything in this plan exists to fit this and report from it.

```r
my_knots <- list(PolYear = c(1, 2, 3, 5, 10, 21),
                 AttdAge = c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95))

hgam_formula <- (DthCnt / ExposCnt) ~
  FaceSize + Smoke + FaceSize:Smoke +                                  # parametric
  s(AttdAge, k = 13, bs = "cr") +                                      # reference age
  s(PolYear, k = 6,  bs = "cr") +                                      # reference duration
  ti(AttdAge, PolYear, k = c(13, 6), bs = "cr") +                      # age x duration
  s(FaceSize, AttdAge, bs = "sz", k = 13, xt = list(bs = "cr")) +      # level deviations
  s(Smoke,    AttdAge, bs = "sz", k = 13, xt = list(bs = "cr")) +
  s(FaceSize, PolYear, bs = "sz", k = 6,  xt = list(bs = "cr")) +
  s(Smoke,    PolYear, bs = "sz", k = 6,  xt = list(bs = "cr")) +
  s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")                      # the MI term

bam(hgam_formula, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = my_knots, discrete = TRUE, select = TRUE, nthreads = ...)
```

**Measured on synthetic data of this shape** (R 4.6.1 / mgcv 1.9.4 locally 1.9-1;
30,000 rows; `FaceSize` and `Smoke` both two-level):

| | `select = FALSE` | `select = TRUE` |
|---|---:|---:|
| coefficients | 110 | 110 |
| smooth terms | 8 | 8 |
| **smoothing parameters** | **13** | **21** |
| total edf | 47.36 | **16.96** |
| fit time (30k rows) | 0.57 s | 0.76 s |

Basis classes required: `cr.smooth`, `tensor.smooth` (`ti`), `sz.interaction`, and a
`cr` basis scaled by a numeric `by` variable.

**A secondary target** — the same maintainer's earlier `bam` form with `bs="fs"`
factor-smooths and a Poisson/log-offset response — is *not* in this epic's scope. `sz`
supersedes `fs` in the selected form. It is recorded in §7 so a later epic can pick it up.

### What this fixes, narrowly

The existing engine fits a **two-margin P-spline tensor with difference penalties** and
selects two smoothing parameters on a grid. The target needs eight terms, three basis
classes it does not have, 13-21 smoothing parameters, a binomial/cloglog response with
prior weights, and user-supplied non-uniform knots. **The fitting core carries over; the
basis layer is a rebuild.** That is the honest description and it is why this is a new
epic rather than slices 8-12 of the old one.

### What it explicitly does not fix

**It does not replace `mgcv` in the maintainer's workflow.** The purpose is a Python
engine that can *stand in* for `mgcv` on this workflow, verified against it. `mgcv`
remains the oracle, and remains the tool the maintainer explores in.

**It does not implement `gamboost`.** Componentwise boosting is a different algorithm
with different regularisation (early stopping and step length, not smoothing parameters)
and **no likelihood covariance at all**. The maintainer uses it for feature selection;
`select = TRUE` provides shrinkage-based term selection inside penalized likelihood,
which is why the parity target can be `mgcv`-only. `mboost` is in the oracle image
(digest below) for exploratory comparison, not as a parity target.

## 2. Design anchors

Numbered so slices can cite them, in the style this project has used four epics running.

**Anchor 1 — two-stage conformance: construction before fit.** Every term is verified in
two separable stages, and Stage A comes first.

| stage | question | mechanism | tolerance |
|---|---|---|---|
| **A — construction** | does our `X` block and each `S_j` equal `mgcv`'s? | extract both, compare matrix-wise | tight (§3 slice 1) |
| **B — fit** | given a shared `(X, {S_j})`, do we get the same answer? | the existing `paraPen` route | already 5e-13 (ADR-189 amd 1) |

**This is the anchor the whole epic rests on**, because a basis defect and a fitter defect
are different defects and a single end-to-end comparison cannot tell them apart. Measured
and proven feasible before this plan was written: `predict(type="lpmatrix")` reproduces
`predict(type="link")` to **3.553e-15**, and all penalty blocks are extractable per term
with coefficient index ranges and ranks.

**Anchor 2 — the fitted surface is the acceptance criterion; coefficients are not.**
`mgcv` reparameterises smooths internally and absorbs identifiability constraints, so `β`
is basis-dependent while `η` is not. Two correct implementations can agree exactly on the
surface and share not one coefficient. Therefore:

1. **Primary metric — the MI contrast.** `η(age, year+1) − η(age, year)` on a pinned
   prediction grid. Basis-invariant, and it is the number that reaches a reader.
2. **Secondary — `η` itself** on the same grid, on the link scale.
3. **Localising — per-term contributions** (`predict(type="terms")`), which say *which*
   term drifted.
4. **Uncertainty — `√(cᵀVc)`** on the same contrast rows. Also basis-invariant.
5. **Coefficients are compared in Stage A only**, where the basis is the thing under test.

Tolerances are stated **on the link scale and on the response scale separately**, because
1e-6 in `η` means something different at `q = 0.001` than at `q = 0.5`.

**Anchor 3 — a term specification is data, not code.** The engine takes a list of term
objects (basis, `k`, knots, `by` variable, factor, penalty order) plus a family / link /
weights / offset spec. The maintainer needs to move between configurations; if a
configuration is a code change, that workflow does not exist. New conformance cases are
then **fixtures**, not new modules.

**Anchor 4 — `k` and knots are inputs, never tuned.** The target's knots are hand-chosen
and markedly non-uniform (`AttdAge` from 1 to 95 in thirteen unequal steps). The engine
accepts supplied knots and **never derives its own when they are supplied**. When they are
not, it reproduces `mgcv`'s default placement — which is itself a Stage-A comparison, not
a guess. `k` is checked against `edf` as an upper bound, carried from the old epic's
Anchor 5.

**Anchor 5 — weights and offsets are orthogonal controls, and both are supported.**

| idiom | response | weights | offset | `η` estimates |
|---|---|---|---|---|
| **absolute** (the target) | `deaths / exposure` | exposure | none | log force of mortality |
| **relative / A-over-E** | same | exposure | `log(−log(1 − q_base))` | log of the A/E force ratio |

The offset is what makes a model *relative*; the weights are how the likelihood learns
how much each cell counts. **A/E is what `η` estimates, not an input** — putting A/E in as
an offset *and* modelling it would double-count, and the plan says so here so nobody tries.

**Anchor 6 — the oracle runs locally, in seconds.** `apt-get install r-base-core
r-cran-mgcv r-cran-jsonlite` takes ~3.5 min once; the ten-cell suite runs in 2.2 s and
`bam(discrete=TRUE)` at 125,000 rows in 1.69 s. **This retires ADR-189's governing
premise.** "The expensive resource is the round trip" was true when no environment had R;
it is false now. Iterate locally, confirm on the pinned digest, and stop designing around
a cost that no longer exists.

**Anchor 7 — the existing engine stays.** `TensorMIModel` and `PenalizedTensorMIModel`
are not deleted or silently re-pointed. Every committed report was produced by them, the
QA goldens depend on nothing moving, and the λ=0 oracle chain needs them alive. Carried
verbatim from the old epic's Anchor 6, where it held for five slices.

**Anchor 8 — never tune a tolerance or a constant to close a gap; derive it.** This
project has earned this twice: ADR-188 refused to widen its way past a failing coverage
gate, and the maintainer restated the rule on PR #192. A tolerance chosen because it makes
a check green measures nothing.

**Anchor 9 — anything adopted from `mgcv` is marked adopted until `mgcv` has been run.**
Carried from the old epic's Anchor 8, where the clause about refutation was not decoration:
it fired, and the refutation (the Kass-Steffey covariance under-inflates) is the most
valuable result that epic produced.

## 3. Slices

Ordered so that slices 1-3 are verifiable **without** the outer optimiser, which is the
largest single piece of work and sits at 4.

### Slice 1: the Stage-A harness, and a term spec to hang it on

- **Status:** DONE (raw path only) (2026-08-15b) — see
  `docs/CONTINUATION_mgcv_parity_engine.md` for what shipped. The mgcv-native half is
  slice 1b (below), not slice 2 — `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`
  is its authoritative spec.
- **Depends on:** nothing (the conformance harness from ADR-189 is on `main`)

**Scope.** An R-side extractor that emits, per term: the design block, every `S_j`, the
coefficient index range, the rank, the knots actually used, and the label. A Python
comparator for the same. The term-spec dataclasses of Anchor 3.

**Prove the harness on a known-good basis first.** The existing B-spline/difference-penalty
basis is already verified to 5e-13 through the fitter. Run Stage A on *that* before any new
basis exists, so a Stage-A disagreement later is attributable to the new basis rather than
to the harness. A harness first exercised on the thing it is meant to judge cannot be
trusted.

**One risk to resolve inside this slice, not later.** `predict(type="lpmatrix")` returns
the design **after** `mgcv` absorbs identifiability constraints and reparameterises;
`smoothCon()` returns the smooth **before**. Which of the two Stage A compares against
changes what "our `X` equals `mgcv`'s `X`" even means. Decide it here, in writing, with
the measurement that justifies it.

**Acceptance.** ~~Stage A runs green on the existing basis.~~ **Corrected 2026-08-16, PR
#197 review:** that wording is what let a raw-only extractor read as satisfying the whole
slice — the "existing basis" is precisely the one with no `smoothCon` path. **The
extractor handles both a supplied basis and an mgcv-native basis, each cross-checked
against the fitted model.** The raw/supplied half shipped 2026-08-15b; the mgcv-native
half is slice 1b. The decision above is recorded (ADR-191). Nothing in `products/`,
`reinsurance/` or the CLI moves; `tests/qa/` untouched.

### Slice 1b: mgcv-native per-term extraction

- **Status:** DONE (2026-08-16), pending tier-3 confirmation in CI (dispatched with
  this PR — `docs/CONFORMANCE_LEDGER.md` will carry the tier-3 row once it returns).
- **Depends on:** Slice 1 (raw path — done)
- **Spec:** `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`, in full, before writing
  code. Raised by the PR #197 review, which found the referent slice 1 needs already
  exists and is already tier-3-green (ADR-191, `scripts/smoothcon_lpmatrix_probe.R`) — so
  this is packaging (emit the existing per-term schema via `smoothCon()`, wire in
  `compare_term_extract`'s `knots` comparison) rather than new verification work, and
  Anchor 8 does not block it.

**Shipped:** `scripts/gam_term_extract.R`'s `smoothCon` branch (`extract_smooth_one`),
emitting the existing per-term schema for isolated `bs="cr"` cases (default knots
`k=8`/`k=13`, supplied knots `k=8`) with its own internal consistency guard against
`predict(type="lpmatrix")`/`m$smooth[[j]]`, promoted from
`smoothcon_lpmatrix_probe.R`'s one-off diagnostic into a standing check. Python side:
`extract_smooth_terms` (`gam_stage_a.py`) packages the R payload into `TermExtract`
— no independent Python basis exists yet, so this is packaging, not re-verification
(ADR-192) — and `compare_term_extract` now compares `knots`. The index-range design
question (work order §4) is settled in writing as ADR-192: assigned by the harness
assembling a term into a model, not read off a fit — an isolated term's model *is*
that term, so `[0, width)`.

**Caught one real bug** (Anchor 1's harness-first discipline doing its job):
jsonlite's `auto_unbox` collapsed the single-penalty `rank` field to a bare scalar,
breaking the Python side's iteration. Fixed with `rank = I(sm$rank)`.
`docs/CONFORMANCE_LEDGER.md` carries the tier-1 reading; tier-3 pending.

**Acceptance.** See the work order §5. Confirmed at tier 3, same discipline as ADR-191 and
slice 1's `raw` path. `docs/CONFORMANCE_LEDGER.md` carries both tier readings. The
index-range design question (work order §4) is settled in writing, ADR-191's form.
`tests/qa/` untouched; goldens byte-identical.

### Slice 2: `bs = "cr"`, with supplied and default knots

- **Depends on:** Slice 1b (done — the mgcv-native extraction Stage A needs to check
  this basis against)

Wood's cubic regression spline: knots at supplied locations or `mgcv`'s default placement,
penalty the exact integrated squared second derivative. Stage A exact, term in isolation.

**Acceptance.** `X` and `S` match `mgcv` for the target's own knot vectors and for default
placement, at both `k = 13` and `k = 6`. A disagreement is reported with which of the two
(basis or penalty) drifted.

### Slice 3: families, links and weights

- **Depends on:** Slice 1 (independent of 2)

Binomial with `cloglog` and `logit` on a proportion response with prior weights;
quasi-Poisson with `φ` estimated; Poisson with a log offset (already present). All four
confirmed to fit in `mgcv` on this term structure, so all four are verifiable.

**Acceptance.** At fixed `sp` on a shared design, `η` matches for each family/link/weight
combination. `φ` matches where it is estimated. The absolute and relative idioms of
Anchor 5 both run, and the plan's claim that they answer different questions is
demonstrated rather than asserted.

### Slice 4: the outer optimisation — N-dimensional (f)REML

- **Depends on:** Slices 1-3

**This is the prerequisite for everything multi-term, and the largest piece of work in the
epic.** `select_lambdas_reml` sweeps a two-dimensional grid in ~200 fits. The target has
**13 smoothing parameters, or 21 with `select = TRUE`**; three points per dimension in 14
dimensions is 4.8 million fits. The grid is not slow here, it is impossible.

Newton (or quasi-Newton) on the (f)REML score in `log λ`, with the derivatives Wood gives.

**Acceptance.** At two smoothing parameters, it reproduces the existing grid's selection
to within the grid's own resolution — a regression check against something already trusted.
At 13, it converges on the target structure and lands within a stated distance of `mgcv`'s
`sp`, with `edf` agreeing **better** than `sp` does (see §6). Determinism across processes,
as ADR-186 required of the grid.

### Slice 5: `ti()` and the varying-coefficient MI term

- **Depends on:** Slices 2, 4

`ti(AttdAge, PolYear)` — tensor interaction with the marginal main effects excluded. And
`s(AttdAge, by = StudyYear_C)` — a `cr` basis scaled by a numeric variable.

**The MI term is the cheap one and it is the important one.** 13 coefficients, and it says
log-hazard is linear in calendar year with an age-varying slope: the classic
mortality-improvement structure. The old epic's full `te(age, year)` tensor spent 38-60
coefficients on the same question and was the source of every conditioning problem from
ADR-184 to ADR-188. **Ship the MI term before `ti`** if they must be split.

### Slice 6: `bs = "sz"` — orthogonal factor-smooth interactions

- **Depends on:** Slices 2, 4

Sum-to-zero factor-smooth deviations from a reference smooth. Four terms in the target.
Expect this to be the hardest basis of the three: the constraint and reparameterisation are
where `mgcv`-specific machinery lives, and Stage A is the only place a mistake is cheap.

### Slice 7: `select = TRUE`

- **Depends on:** Slices 4-6

`mgcv`'s double penalty — an extra null-space penalty per smooth, so a term can shrink to
exactly zero. Takes the smoothing-parameter count from 13 to **21**, and total edf from
47.36 to 16.96 on synthetic data of the target's shape. It is a **term-selection mechanism
inside penalized likelihood**, and it is the reason `gamboost` is not a parity target.

### Deferred to a later epic: `bam` + `discrete = TRUE` + fREML

`bam(discrete = TRUE)` is a different algorithm, not a faster `gam` — discretised
covariates and the Wood/Li/Shaddick/Augustin method. Two measurements bound the decision:
at fixed `sp` on a `paraPen`-only model, `bam` agrees with `gam` to **2.1e-12**, so nothing
in slices 1-7 is invalidated by deferring it; and `bam` at 125,000 rows takes **1.69 s**,
so performance is not the reason to want it. Maintainer decision, 2026-08-10.

## 4. What is explicitly out of scope

- **Replacing `mgcv` in the exploration workflow** (§1).
- **`gamboost` / componentwise boosting** (§1). `mboost` is in the image for comparison.
- **`bs = "fs"`** — superseded by `sz` in the selected form; recorded in §7.
- **Deleting or re-pointing the existing engine** (Anchor 7).
- **Re-deriving the committed findings.** This epic compares; it does not overwrite
  `MEASUREMENT_experience_gam_*.md`.

## 5. Risks, in the order they are likely to bite

1. **`mgcv`'s internal reparameterisation may make Stage A ill-posed as stated.** If
   `lpmatrix` is post-constraint and `smoothCon()` pre-constraint, then "our `X` equals
   `mgcv`'s" needs a chosen referent. Slice 1 resolves it; if neither referent works, the
   fallback is to compare the **column space** and the fitted values rather than the matrix,
   which is weaker and must be recorded as such.
2. **`sz` is under-documented relative to `cr` and `te`.** Reading the constraint
   construction out of `mgcv`'s source may be necessary. Budget real time; Stage A makes it
   safe to get wrong repeatedly.
3. **The 21-dimensional optimiser may be badly conditioned** where the 2-D grid was merely
   shallow. ADR-187 amendment 2 measured 3.85 REML units across 5.5 decades for a 2.6x edf
   change; in 21 dimensions that flatness is a convergence problem, not a curiosity.
4. **The Kass-Steffey covariance is already known wrong** (ADR-189 amendment 1: ours
   inflates 1.11-1.21x where `mgcv` inflates 1.49-1.87x). Whatever this engine reports as a
   band inherits that defect until it is fixed. It is tracked as a BLOCKER against the old
   epic's arithmetic, and it is **not** re-solved here by assumption.

## 6. Predictions, registered before slice 1 is written

The discipline that has now paid off three epics running: write the interpretation table
before the measurement, including the rows nobody wants.

| Prediction | If it holds | If it fails |
|---|---|---|
| **Stage A on `cr` agrees exactly once knots match, and any disagreement is knot placement rather than the spline recursion** | The basis work is a transcription job with a tight oracle, and the remaining risk is all in `sz` and the optimiser | The recursion or the penalty derivation differs, and slice 2 is materially larger than planned |
| **`sz` is the hardest of the three bases** | Budgeting most of the basis time there was right | Whichever is harder tells us where `mgcv`'s machinery actually lives, which is worth knowing |
| **The optimiser does not land on `mgcv`'s `sp`, but `edf` agrees far better than `sp` does** | Confirms `edf` as the quantity to gate on and `sp` as a diagnostic — the same lesson the old epic's level 2 taught at two dimensions | If `sp` agrees tightly, the criterion is better identified than expected and the tolerances can tighten |
| **The MI contrast agrees better than `η` does** | Anchor 2's ordering is right: the contrast cancels the intercept and anything constant in year | Something term-specific is wrong in the year direction, and the contrast is the diagnostic that found it |

**A slice that refutes one of these is a successful slice.** Anchor 9, and the old epic's
record: its registered hypothesis came back false in slice 3 and was trustworthy for
exactly that reason.

## 7. Context for the next session

- **Read Anchor 1 and Anchor 2 before writing code.** They are the two that change what
  you build, not just how you check it.
- **The local oracle is a SCRATCH oracle.** `apt-get install -y r-base-core r-cran-mgcv
  r-cran-jsonlite`, ~3.5 min. It gives **mgcv 1.9.1 / R 4.3.3 on reference `libblas`** —
  where the image is **1.9.4 / 4.6.1 on OpenBLAS**. Different release *and* different BLAS,
  so it cannot reproduce the image's last bits at Anchor-1 precision. Iterate locally,
  verify on CI (~1 min per dispatch); only a CI number may be committed.
- **The oracle image now carries `mboost` 2.9.13**, at digest
  `sha256:8853bf2b600f6ce0fcae8e29d0a78e4b95ed3603dacb4f5cafa49e7c29606b7c` — upstream
  build 2. **The predecessor, build 1
  (`sha256:a77a61cf231933e17ec037ee0a63450067f66200a29ebc1cddbed14b8625ce8e`), is the
  build that produced ADR-189 amendment 1's numbers**, and it still resolves.
  **And the maintainer recorded a finding worth keeping:** the `r4.6.1-2026-08-01` tag was
  moved onto the new image, so that tag no longer identified a unique build — anyone pinning
  it silently picked up `mboost`. Nothing broke, and it is a live demonstration of why the
  workflow pins by digest on a tag that *looks* like it encodes everything relevant.
  **Fixed upstream in R-Gam-base PR #3:** immutable never-reused tags
  (`r<R>-cran<snapshot>-b<NN>`), a digest-keyed `BUILDS.md` catalog, and a CI refusal to
  push an existing tag. `r4.6.1-2026-08-01` is deprecated rather than deleted, because GHCR
  deletes package *versions* and that tag sits on a digest this repo pins.
- **`select = TRUE` is why `gamboost` is not a parity target.** It shrinks terms to exactly
  zero inside penalized likelihood: edf 47.36 → 16.96 on synthetic data of the target shape.
- **The MI term is a varying-coefficient term, not a tensor**, and it is better conditioned
  than what the old epic built. Do not "improve" it into a `te()`.
- **`weights` are not an `offset`.** Anchor 5. The target uses weights and no offset; the
  existing polaris engine uses an offset. Both are wanted.
- **`bs = "fs"` was in an earlier maintainer formula and is superseded by `sz`.** If a later
  epic wants it: 2-3 penalties per term, versus `sz`'s constraint-based construction.
- **Do not compare coefficients outside Stage A** (Anchor 2). It is the mistake that looks
  most like rigour and is least informative.

## 8. Disposition of `PLAN_penalized_mi_surface.md`

Slices 1-5 of that epic are **done and merged**; `tr(F)` is verified and the Kass-Steffey
covariance is refuted. Slices 6-7 are **PARKED, not abandoned**, on maintainer direction:

- **Slice 6 (harness integration)** would surface `--penalized`, `edf` and a band for a
  two-margin P-spline tensor that this epic supersedes. Throwaway work.
- **Slice 7 (real data against the registered predictions)** would run that same superseded
  model on real experience.

**The level-4 Kass-Steffey under-inflation is NOT parked.** It is covariance arithmetic,
engine-agnostic, small, and it closes the standing bar on labelling any interval a 95%
band. It stays a BLOCKER against the old epic and should be taken before or alongside slice
1 here.

The old CONTINUATION's refinement backlog must be harvested into the latest
PRODUCT_DIRECTION **before** its status changes — the routine's rule, and the reason
~25 items were once invisible the day their feature shipped.
