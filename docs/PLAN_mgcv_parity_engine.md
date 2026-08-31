# Plan: a Python GAM engine at parity with `mgcv` for the mortality-improvement workflow

**Source:** maintainer direction 2026-08-10 (the target model form, supplied as R).
**Predecessors:** ADR-189 + amendment 1 (the conformance suite, and the first run that
used it), ADR-185 through ADR-188 (the penalized fitter this epic reuses).
**Supersedes:** `PLAN_penalized_mi_surface.md` slices 6-7 — see §8.
**Total slices:** **7** autonomous, plus one deferred to a later epic. **Plus slice 1b**
(inserted 2026-08-16, PR #197 review): mgcv-native per-term extraction, split out of
slice 1 rather than left folded into slice 2 — see
`docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`. **Plus slice 5b** (the production
path, `PolarisGAM` from a `ModelSpec`; inserted 2026-08-25, DONE same day, ADR-208),
**slice 5c** (`log|S|₊` under badly scaled λ plus the observed-Hessian weight, Wood
2011 §3.1/Appendix B and eq. 4; inserted 2026-08-25, DONE 2026-08-29, ADR-210 — both
defects closed to float precision at fixed `sp`, tier 1 and tier 3 identical), and
**slice 5d** (inserted 2026-08-29 after 5c's own measurement re-diagnosed the
free-`sp` residual as an optimiser-convergence question rather than a criterion one;
DONE the same day, ADR-212 — a finite-difference-step defect confirmed and fixed at
both tiers, and the remaining `log10(sp)` residual localised to weak identifiability
on one block rather than a defect, unblocking slice 6), **slice 5e** (inserted
2026-08-29/30, DONE 2026-08-30, ADR-213 — best-of-N multi-start built and measured;
recovers a real N=4 convergence failure, single-start already sufficient on a
covariate-DECOUPLED N=8 stress case), and **slice 5f** (inserted 2026-08-30, DONE
2026-08-31, ADR-214 — the same question on a covariate-SHARING N=8 structure;
single-start sufficient there too, and MORE stable than either of slice 5e's own
readings), and **slice 6b** (inserted 2026-08-31, ADR-215 — slice 6's own Stage A
closed the same day; a multi-term fit including an `sz` term, ADR-206's own
Stage-B pattern, remains open and is registered rather than left implicit). The
letter suffixes exist so inserting work does not renumber slices 6 and 7 and
break every cross-reference to them.
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

**Anchor 7 — the existing engine stays until a new one demonstrably matches it.**
**AMENDED 2026-08-24 (maintainer-authorized, ADR-207).** `TensorMIModel` and
`PenalizedTensorMIModel` are not deleted, and no caller is silently re-pointed at a
different implementation. **Building a new production path from the tier-3-verified
parity components is explicitly permitted and is this epic's intended route.** A caller
moves to it only when the new path has been measured against the old one on the same
input and the comparison is committed. The QA goldens and the λ=0 oracle chain keep the
old engine alive regardless.

> **Original form, and why it changed.** It read: *"the existing engine stays.
> `TensorMIModel` and `PenalizedTensorMIModel` are not deleted or silently re-pointed.
> Every committed report was produced by them, the QA goldens depend on nothing moving,
> and the λ=0 oracle chain needs them alive."* Carried verbatim from the old epic's
> Anchor 6, where it held for five slices, and it held for six more here.
>
> One of its three reasons is discharged: ADR-204's provenance stamps now give committed
> reports their own drift detection, so the old engine is no longer their only warrant.
> The other two — the QA goldens and the λ=0 oracle chain — are untouched and keep the
> engine alive.
>
> **What the anchor cost, which is why it moved.** By protecting the shipped engine it
> left every verified component homeless: nine tier-3-verified modules and nothing
> permitted to compose them, so each had to justify itself as a conformance artifact.
> Three ADRs (199, 200, 205) each stopped at Stage A or N=2 naming the same missing
> assembler — named three times, built zero, because nobody schedules scaffolding. The
> assembler and the production engine are the same object; the anchor was the reason
> that could not be said. See `docs/WORK_ORDER_multi_term_assembly.md`.
>
> **What did NOT change:** nothing is swapped silently, and the old engine stays. The
> long-open "re-point `smoothing_uncertainty` at `gam_uncertainty`" item is **withdrawn**
> rather than granted — ADR-207 decision 3.

**Anchor 8 — never tune a tolerance or a constant to close a gap; derive it.** This
project has earned this twice: ADR-188 refused to widen its way past a failing coverage
gate, and the maintainer restated the rule on PR #192. A tolerance chosen because it makes
a check green measures nothing.

**Anchor 9 — anything adopted from `mgcv` is marked adopted until `mgcv` has been run.**
Carried from the old epic's Anchor 8, where the clause about refutation was not decoration:
it fired, and the refutation (the Kass-Steffey covariance under-inflates) is the most
valuable result that epic produced. **`gamma`'s status update, 2026-08-21:** run and
AGREES (level 5, ADR-197/198) — moved from "adopted, unmeasured" to "adopted, measured,
AGREES". Its tolerances (0.5, 1.0) stay PROVISIONAL for now (ADR-198, the routine's own
reading — not a maintainer ruling): one passing exchange derives nothing, and Anchor 8
forbids tightening a bound *because a check went green*. This is not a gate on a later
session: once more conformance cells give something to derive a tighter number from,
tightening them is ordinary parity work — do it, and record the derivation that justifies
the new value.

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

- **Status:** DONE (2026-08-16). Tier 3 dispatched and returned (run 31946132947):
  the R script's `stop()`-gated internal guard passed on the pinned image — a
  genuine hard check, not a print — and the Python packaging raised no exception
  on the tier-3 payload. The per-metric diff table itself was not read (this
  environment's egress policy blocks the artifact blob-storage host); see
  `docs/CONFORMANCE_LEDGER.md` for exactly what was and was not confirmed.
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
`docs/CONFORMANCE_LEDGER.md` carries both tier readings.

**Acceptance.** See the work order §5. Confirmed at tier 3, same discipline as ADR-191 and
slice 1's `raw` path. `docs/CONFORMANCE_LEDGER.md` carries both tier readings. The
index-range design question (work order §4) is settled in writing, ADR-191's form.
`tests/qa/` untouched; goldens byte-identical.

### Slice 2: `bs = "cr"`, with supplied and default knots

- **Status:** DONE, 2026-08-17. `src/polaris_re/analytics/gam_basis_cr.py` — Wood's
  natural-cubic-spline construction, `mgcv`'s own default knot placement, and its
  `colMeans`-QR identifiability constraint, every detail read out of `mgcv`'s R source
  rather than guessed (ADR-194). Agrees with `smoothCon(bs="cr", absorb.cons=TRUE)` to
  float round-trip precision (~1e-14) on 5 cases — the harness's original 3 plus the
  target formula's own `AttdAge` (k=13) and `PolYear` (k=6) knot vectors, so acceptance
  criterion #1 below is met against the literal target knots, not a stand-in.
  `design_X`/`penalty_S`/`rank` are `INDEPENDENT` (`CR_BASIS_CLAIM`, `gam_stage_a.py`)
  — the epic's first genuine Stage-A parity result; `knots` agreement is checked too
  but reported separately, since it is ECHO rather than INDEPENDENT in the 3
  supplied-knot cases (PR #201 review [P1]). See ADR-194 and `docs/CONFORMANCE_LEDGER.md`.
- **Depends on:** Slice 1b (done — the mgcv-native extraction Stage A needs to check
  this basis against)

Wood's cubic regression spline: knots at supplied locations or `mgcv`'s default placement,
penalty the exact integrated squared second derivative. Stage A exact, term in isolation.

**This is the epic's first Stage-A parity slice** (ADR-193). Slices 1 and 1b built the
harness and are honest about being harness: slice 1's `X`/`S` are `ECHO` (Python supplies
them to `mgcv`), slice 1b's columns are all `TRANSPORT` (one producer, parsed by the
other). Neither compares a Python-computed basis against an mgcv-computed one, because
**no Python `cr` basis exists** — the shipped fitter builds a B-spline/P-spline tensor
(`experience_gam_penalized._basis`), which is a different construction entirely. Building
that basis is the substance of this slice; the harness is already in place to receive it.

**Parity claim (write this before the code, per `docs/VERIFICATION_STANDARD.md`):**

> `polaris_re`'s new `cr` basis computes `design_X` and `penalty_S` from the knot vector
> and Wood's basis/penalty definition; `mgcv` computes them via
> `smoothCon(s(x, bs="cr", k=…), absorb.cons=TRUE)`; compared on `design_X`, `penalty_S`
> and `rank`.

**Acceptance — every criterion names its provenance, so no harness result can tick one:**

1. **INDEPENDENT** comparison of `design_X`: Python's `cr` basis vs `smoothCon(...)$X`,
   `max_abs_design_diff < 1e-9`, for the target's own knot vectors *and* for `mgcv`'s
   default placement, at both `k = 13` and `k = 6`.
2. **INDEPENDENT** comparison of `penalty_S` to the same tolerance, over the same cases.
3. A disagreement is reported with which of the two (basis or penalty) drifted — and,
   because both are now independently produced, a disagreement is a *real result* about
   the basis rather than a broken round trip.
4. The Python producer takes **no R payload as an input** (the mechanical test). If the
   comparison needs the knot vector, it comes from the recipe — the same knots supplied
   to `mgcv` — not from `smoothCon()`'s output.
5. The slice's `VerificationClaim` declares `INDEPENDENT` for `design_X`/`penalty_S`, and
   `require_parity_evidence` gates the acceptance check.
6. Confirmed at tier 3 on the pinned oracle, per `docs/ROUTINE_MGCV_PARITY.md`.

**Carry forward from slice 1b:** `scripts/gam_term_extract.R`'s `extract_smooth_one` and
its four `stop()`-gated internal guards are a genuine independent producer *inside R*
(ADR-191) and are reused unchanged. What slice 2 replaces is the *left* operand —
`extract_smooth_terms`'s parse — with a real Python computation. `extract_smooth_terms`
itself remains useful for reading the reference payload, but it is the reference side,
not the Polaris side, once slice 2 lands.

### Slice 3: families, links and weights

- **Status:** DONE, 2026-08-17. `src/polaris_re/analytics/gam_family.py` (the
  `Family`/`Link` abstraction — standard GLM IRLS theory, Wood §3.1.2, no
  R-source archaeology needed) and `gam_fit.py` (`penalized_irls_general`, a
  general penalized-IRLS core proven to reduce to the already-verified Poisson
  recursion bit-for-bit, ADR-195 decision 1). `gam_family_conformance.py`'s
  `FAMILY_CLAIM` declares `eta`/`dispersion` `INDEPENDENT` and
  `require_parity_evidence` gates it — the epic's first Stage-B parity result
  outside the already-verified Poisson case. Confirmed at tier 3 (CI run
  32057694949): all four family/link/weight combinations agree to float
  round-trip precision (~1e-14 on `eta`) on the **first** measurement, no
  iteration needed. See ADR-195 and `docs/CONFORMANCE_LEDGER.md`.
- **Depends on:** Slice 1 (independent of 2)

Binomial with `cloglog` and `logit` on a proportion response with prior weights;
quasi-Poisson with `φ` estimated; Poisson with a log offset (already present). All four
confirmed to fit in `mgcv` on this term structure, so all four are verifiable.

**Acceptance.** At fixed `sp` on a shared design, `η` matches for each family/link/weight
combination — **met**, all four combinations, tier 3. `φ` matches where it is estimated
— **met** for quasi-Poisson (the one case `mgcv` estimates it), dispersion diff
9.671e-06 at tier 3. **Not yet run:** the absolute and relative idioms of Anchor 5 both
running end to end through this fitter (this slice built and verified the general IRLS
core itself, on a dedicated small shared design — wiring it through the absolute/relative
offset-vs-weight distinction on the target's own term structure is left to the slice that
assembles a full multi-term model, since no outer smoothing-parameter optimiser exists yet
for it to run against, slice 4).

### Slice 4: the outer optimisation — N-dimensional (f)REML

- **Depends on:** Slices 1-3
- **Status:** IN PROGRESS. **Part A DONE AND RESOLVED, 2026-08-18** (ADR-196): the
  REML score itself, generalized from `experience_gam_penalized.reml_score`
  (Poisson, exactly two hardcoded blocks) onto `gam_fit`'s general IRLS core
  (`gam_reml.reml_score_general`, known-scale families) — the criterion the
  outer search will need, built and measured BEFORE the search itself, since a
  search over a criterion known not to match `mgcv` would not be meaningful.
  **First measurement (tier 1 and tier 3 identical): the naive generalization's
  fit was correct (deviance matched `mgcv` to ~1e-11) but its multi-block REML
  score did NOT reproduce `mgcv`'s criterion shape** — an INDEPENDENT
  comparison that disagreed (a real result, ADR-193). **Resolved same day**:
  the maintainer supplied Wood (2011) directly; §2 eq. (4) names the missing
  term — the criterion needs the PENALIZED deviance `Dₚ = D(β̂) + β̂ᵀSβ̂`, not
  the plain deviance the first generalization used. Adding it closed the gap
  to float round-trip precision (~1e-12), tier 1 and tier 3 identical, CI run
  32142352655. `REML_SCORE_CLAIM`'s two quantities are both INDEPENDENT and
  both now agree — the epic's first Stage-C parity result.
  **`experience_gam_penalized.reml_score` (the shipped, production tensor-MI
  selector) had the identical omission — measured, then fixed. DONE
  2026-08-19/21** (ADR-197 and its resolution amendment): the work order
  `docs/WORK_ORDER_reml_penalized_deviance_production_check.md` measured it at
  both tiers, the maintainer gave the PLAN Anchor 7 sign-off for that one line,
  and `data/mgcv_exchange/synthetic/python_reference.json` was re-baselined
  through its own regeneration script. The two implementations now compute the
  identical criterion bit-for-bit. Conformance moved level 5 DISAGREES → AGREES,
  levels 1-3 AGREE throughout (no regression), level 4 unchanged and still
  DISAGREES (ADR-190's separate `dw/drho` gap). **Part B — the outer
  N-dimensional search itself — is now the epic's next piece of work**, with a
  registered prediction to test on arrival (ADR-198, in Acceptance below).
  **Part B's first slice DONE, 2026-08-22** (ADR-199, tier 1 and tier 3 both
  confirmed): `src/polaris_re/analytics/gam_reml_optimize.py`
  (`select_lambdas_continuous`) — a Newton/quasi-Newton search (SciPy
  L-BFGS-B) over `log10(lambda)` for any number of independently-scaled
  penalty blocks, built entirely on the already-verified
  `gam_fit.penalized_irls_general`/`gam_reml.reml_score_general`, no new
  fitting or scoring formula. **ADR-198's registered prediction HOLDS,
  decisively**: on the same four free-sp cells ADR-198 measured post-fix,
  `max_abs_log10_sp_diff` against `mgcv`'s own free-sp selection collapses
  from the grid's 0.0645/0.0791/0.1048/0.0776 to (tier 3) 6.9e-04/5.1e-05/
  1.7e-04/9.8e-04 — 2-3 orders of magnitude, landing at the search's own
  convergence tolerance rather than near 0.1, identical in verdict at tier 1
  and tier 3 (CI run 32544930172, oracle `sha256:0d54c192…` build 8).
  `CONTINUOUS_LAMBDA_CLAIM` (`gam_reml_optimize_conformance.py`) declares both
  compared quantities INDEPENDENT. Tested only at the existing 2-block designs
  (`d1`/`d2`/`d3`) — the module accepts any block count by construction, but
  nothing has exercised it above 2 yet; that is slice 5 onward's work once a multi-term
  mgcv-native model exists. `experience_gam_penalized.select_lambdas_reml`
  is untouched (PLAN Anchor 7) — see ADR-198 "Two searches, not one".

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

**Plus one registered prediction, added 2026-08-21 (ADR-198).** Part A's fix (ADR-196,
carried into production by ADR-197's resolution) left every free-`sp` conformance cell
disagreeing with `mgcv` by **less than half the grid's own refinement step** —
`max_abs_log10_sp_diff` of 0.0645 / 0.0791 / 0.1048 / 0.0776 against a half-step of 0.125,
where before the fix all four exceeded it (0.3145 / 0.1709 / 0.4322 / 0.6724). ADR-198
states the hypothesis that what
remains **is** the grid quantisation, and names part B as its decisive test:

> On `l2-free-sp`, `l2-free-sp-factors`, `l2-free-sp-kb` and `l5-gamma`, a continuous
> optimiser on the same criterion should drive `max_abs_log10_sp_diff` toward its own
> convergence tolerance rather than leaving it near 0.1.

**Measure this and record it either way** — a residual that stalls near 0.1 under a
continuous search refutes ADR-198 and means the criterion still differs from `mgcv`'s
somewhere, which is a more important result than the optimiser shipping. ADR-198 also names
a cheaper pre-test that needs no new code (re-run those cells at `refine_step = 0.05`);
running it first is optional but it is the fast way to learn the answer. Neither may be met
by moving a tolerance (Anchor 8).

**Out of scope here, explicitly:** replacing the *production* selector
(`experience_gam_penalized.select_lambdas_reml`) with a continuous search. It has two
dimensions where the grid is affordable, ADR-186 chose the grid deliberately to get
reproducibility by construction, and PLAN Anchor 7 protects it. If part B's optimiser
proves itself here, re-pointing production at it is a **separate** decision with its own
maintainer sign-off and its own answer to the determinism question — see ADR-198, "Two
searches, not one".

### Slice 5: `ti()` and the varying-coefficient MI term

- **Depends on:** Slices 2, 4
- **Status:** **DONE, 2026-08-24.** The MI term's own basis, `s(AttdAge, by = StudyYear_C)`,
  is **DONE (Stage A only), 2026-08-22** (ADR-200, tier 1 and tier 3 both confirmed,
  identical to the printed digit) — the epic's first INDEPENDENT Stage-A result for a
  numeric-`by` `cr` smooth. **`ti(AttdAge, PolYear)` is now also DONE (Stage A only),
  2026-08-24** (ADR-205, tier 1 and tier 3 both confirmed, CI run 32677470292) — the
  epic's second INDEPENDENT Stage-A result, and its first for a two-margin term.
  **The remaining Stage-B multi-term model is DONE, 2026-08-24** (ADR-206, tier 1 and
  tier 3 identical, CI run 32722872476): a three-term model (reference age smooth,
  the `by` term, `ti()`) fit together at fixed sp agrees with `mgcv`'s native fit on
  `eta` to 1.242e-10, first measurement — closing this slice's remaining scope. Not
  claimed: Anchor 2's primary MI-contrast-on-a-grid metric, or extending slice 4 part
  B's search to this design's N=4 blocks — both named as follow-on work in ADR-206.

`ti(AttdAge, PolYear)` — tensor interaction with the marginal main effects excluded. And
`s(AttdAge, by = StudyYear_C)` — a `cr` basis scaled by a numeric variable.

**The MI term is the cheap one and it is the important one.** 13 coefficients, and it says
log-hazard is linear in calendar year with an age-varying slope: the classic
mortality-improvement structure. The old epic's full `te(age, year)` tensor spent 38-60
coefficients on the same question and was the source of every conditioning problem from
ADR-184 to ADR-188. **Ship the MI term before `ti`** if they must be split — done, per
ADR-200: `mgcv` absorbs no identifiability constraint on a numeric-`by` smooth at all, so
the by-term's design is the *unconstrained* `cr` basis with each row scaled by the
by-variable, and its penalty is that same unconstrained `S`.

**`ti(AttdAge, PolYear)` reuses two per-margin `cr` constructions unchanged (ADR-194),
plus three steps derived by instrumenting `mgcv`'s tensor-smooth constructor directly
(ADR-205, Anchor 8): no reparameterization for `cr` margins (they set `noterp`, so
`ti()`'s own `np=TRUE` default never fires here), a row-wise Kronecker of the marginal
designs and penalties, and a SECOND tensor-level `scale.penalty` rescaling on top of each
margin's own.** Both terms had Stage A only until 2026-08-24 — the multi-term
mgcv-native model exercising both (ADR-206) now gives the first Stage-B `eta`
comparison; Anchor 2's MI-contrast-on-a-grid metric specifically remains open, named
in ADR-206 rather than attempted there.

### Slice 5b: the production path — `PolarisGAM` from a `ModelSpec`

- **Depends on:** Slices 2, 4, 5
- **Status:** **DONE, 2026-08-25** (ADR-208, tier 1 AND tier 3 both confirmed, CI
  run 32855338611). `analytics/gam_model.py`'s `assemble_model_design` generalises
  ADR-206's assembly to any `ModelSpec`; `fit_polaris_gam` selects its own λ via
  `select_lambdas_continuous` and fits with `penalized_irls_general`. The work
  order's §4 registered prediction (N=4 lands in ADR-199's 2-block range) is
  **REFUTED at both tiers** — `max_abs_log10_sp_diff=0.7766` (tier 1) / `0.6398`
  (tier 3). **Diagnosis corrected same-day (PR #212 review [P1]), then
  CONFIRMED at tier 3 same day too:** the discriminating measurement shows
  `mgcv`'s own criterion and ours rank `mgcv`'s point and Python's point in
  OPPOSITE order (`delta_mgcv=-0.121389`, identical at tier 1 R 4.3.3/mgcv
  1.9.1 and tier 3 R 4.6.1/mgcv 1.9.4, CI run 32874213883) — real evidence of
  an `sp`-dependent criterion discrepancy at this N=4/`ti()`-sharing-a-span
  structure, not merely a flat surface. **Slice 6 should not be designated
  until this is localised or closed** (confirming it is real is not the same
  as fixing it). See ADR-208's amendment and `docs/CONFORMANCE_LEDGER.md`.
- **Work order:** `docs/WORK_ORDER_multi_term_assembly.md` — full scope, sequencing, the
  registered prediction and two already-paid-for traps live there. **This slice entry
  exists so the routine can select it**; the work order is the specification.
- **Authorized by:** ADR-207. Before that amendment this work had no permitted form, which
  is why it reached 2026-08-24 as a work order with no slice to belong to.

**The gap, stated narrowly.** ADR-206's `assemble_multiterm_design` takes an
`RMultiTermRecipe` — `mgcv`'s own JSON payload — at fixed `sp`. Two things follow: it
cannot fit a model `mgcv` has not already defined, and it does not choose its own λ.
Everything on either side of that gap (bases, fitter, criterion, search, covariance) is
already tier-3 verified and is reused, not rewritten.

**The new measurement is free `sp` at N=4.** `select_lambdas_continuous` has been measured
against `mgcv` only on 2-block designs (ADR-199). Extending it to a multi-term design is
the one genuinely unverified step, and it is why this slice precedes slice 6: adding a
fourth basis to a stack that still cannot select its own smoothing parameters widens the
surface without closing the open question. Note also that `mgcv`'s `sp` moves from
**shared input** to **compared quantity** here, which changes its ADR-193 classification —
the `VerificationClaim` must say so.

**Scope is the three-term subset** (`cr` + numeric-`by` + `ti`), not the target's eight
terms. Slices 6 and 7 remain required for the full form, and this slice does not
anticipate them.

### Slice 5c: the REML criterion — TWO defects, Wood (2011) §3.1/Appendix B and eq. (4)

- **Depends on:** Slice 5b (ADR-208 and its amendment).
- **Status:** **DONE for both defects, 2026-08-29** (ADR-210, tier 1 AND tier 3
  confirmed identical, CI runs 33267701996/33267879635). `gam_reml_appendix_b.py`
  builds Wood's Appendix B whole (similarity transform, pivoted-QR determinant,
  the stable square root `E`); `Family.observed_information_weight` supplies
  Wood §3.2's analytic observed-Hessian weight, verified to equal exactly 1 for
  both canonical links this module defines. The eight-point fixed-`sp` spread
  against `mgcv` collapses from **3.910776** (raw, shipped) to **4.271e-07**
  (tier 1) / **0.000000 at print precision** (tier 3) — float round-trip
  precision, ~9.2 million times smaller. **The §4 registered prediction lands
  on its third branch**: fixed-`sp` closes as predicted, but free-`sp`
  selection on ADR-208's own N=4 structure does NOT (`max_abs_log10_sp_diff`
  1.0996 at tier 3, WORSE than the 0.6398 pre-fix reading) — re-diagnosed, not
  merely re-measured: under our own now-correct criterion, `mgcv`'s own
  selected point scores measurably better than our optimiser's own converged
  point, an OPTIMISER CONVERGENCE finding rather than a criterion one. See
  ADR-210 for the full measurement, the mutation-protocol table (2 of 6
  mutations caught, 4 recorded as an honest test-coverage gap), and the
  eq. (4) term-by-term audit. **Slice 6 stays BLOCKED** — see slice 5d below,
  which this finding registers.
- **Diagnosis:** `docs/RECALIBRATION_mgcv_parity_2026-08-25.md` §1 (tier 1).

> **There are two defects, found in that order and both `sp`-dependent.** Defect A is
> numerical and is the rest of this section. **Defect B is a formula error** and is
> written up in `#### Defect B` below — it accounts for essentially all of the
> residual A leaves behind. A session that fixes only A will see the gap shrink by
> three orders of magnitude and still not close; **fix both, or the §4 prediction
> cannot resolve.**

**Defect A, in one line.** `gam_reml.reml_score_general` evaluates `log|S|₊` by
forming `S = Σⱼ λⱼSⱼ`, eigendecomposing it, and cutting the null space at a fixed
relative tolerance of `1e-10`. When the λ's span many decades that cut is arbitrary,
and the score moves discretely as eigenvalues are misclassified.

**Wood names this failure mode and it is the paper's own §3.1.** *"`log|S|₊` … is the
most numerically troublesome term in the REML/ML objective."* His account, and it
matches the measurement point for point:

- The computed eigendecomposition `Ŝ₁ = ÛΛ̂Ûᵀ` has *should-be-zero* eigenvalues `Λ̂⁰`
  of typical magnitude `‖S₁‖ε_m`. As `λ₁/λ₂ → ∞` the computed determinant tends to
  `λ₁^{r₁} ∏ᵢΛ̂⁺ᵢ · λ₁^{d₁} ∏ᵢΛ̂⁰ᵢ`, and **the second factor is essentially
  arbitrary** (`d₁` = rank deficiency of `S₁`). Wood calls this **"numerical zero
  leakage."**
- His trigger condition: it *"spoils determinant calculations whenever the ratio of
  the largest strictly positive eigenvalue of `λ₁S₁` … to the smallest strictly
  positive eigenvalue of `λ₂S₂` is too great."* Our departures occur at exactly the
  points where the λ's span ≳6 decades and the spectrum's null-space gap collapses
  from ~1e10 to ~1e5.
- *"The problem vanishes for a full rank `S₁`."* Which is why every flat-λ point in
  the measurement agreed to ~7e-3 and only the spread-λ points departed.

**And Wood rules out the tolerance approach explicitly** — quote it in the ADR,
because it is the reason Anchor 8 applies here: *"re-parameterization is preferable
to simply limiting the working λ range. To keep the non zero eigenvalues of all
`λᵢSᵢ` within limits that guarantee computational stability usually entails
unacceptably restrictive limits on the `λᵢ`."*

#### What to implement — Appendix B, scoped to the determinant only

Appendix B generalises §3.1's two-term similarity transform to any number of
rank-deficient `Sᵢ`. `O(q³)`.

**Pre-step (S not formally full rank).** Symmetric eigendecomposition
`ÛΛ̂Ûᵀ = Σᵢ Sᵢ/‖Sᵢ‖_F`; let `U₊` be the columns with positive eigenvalues and set
`S̄ᵢ = U₊ᵀSᵢU₊`. Then `|S|₊ = |Σᵢ λᵢS̄ᵢ|` and that sum has full rank.

**Initialise.** `K = 0`, `Q = q`, `S̄ᵢ = Sᵢ ∀i`, `γ = {1…M}`.

**Iterate to termination at step 4:**

1. `Ωᵢ = ‖S̄ᵢ‖_F λᵢ` for `i ∈ γ`.
2. `α = {i : Ωᵢ ≥ ε·max(Ω)}`, `γ' = {i : Ωᵢ < ε·max(Ω)}`, with `ε` the **cube root of
   machine precision**. `α` indexes the dominant terms.
3. Eigenvalues of `Σ_{i∈α} S̄ᵢ/‖S̄ᵢ‖_F` give the formal rank `r` — count those larger
   than `ε̃` times the dominant eigenvalue, `ε̃` = machine precision raised to a power
   in `[0.7, 0.9]`.
4. **If `r == Q`, terminate.** The current `S` is the one to use.
5. `UDUᵀ = Σ_{i∈α} λᵢS̄ᵢ`, eigenvalues descending. `U_r` = first `r` columns, `U_n`
   the remainder.
6. Partition `S = [[A_{K×K}, B_{K×Q}], [Bᵀ, C_{Q×Q}]]`. Set `B' = BU` and
   `C' = [[D_r + U_rᵀS_{γ'}U_r, U_rᵀS_{γ'}U_n], [U_nᵀS_{γ'}U_r, U_nᵀS_{γ'}U_n]]`
   where `S_{γ'} = Σ_{i∈γ'} λᵢS̄ᵢ`. Then
   `S' = diag(I_K, Uᵀ) S diag(I_K, U)` and `|S| = |S'|`.
7. `T_α = diag(I_K, U_r, 0)`, `T_{γ'} = diag(I_K, U)`; transform
   `Sᵢ ← T_αᵀSᵢT_α ∀ i∈α` and `Sᵢ ← T_{γ'}ᵀSᵢT_{γ'} ∀ i∈γ'`.
8. `S̄ᵢ ← U_nᵀS̄ᵢU_n ∀ i ∈ γ'`.
9. `K ← K+r`, `Q ← Q−r`, `S ← S'`, `γ ← γ'`. Return to 1.

**Then take the determinant by pivoted QR on the transformed `S`** — `∏ᵢ R̂ᵢᵢ`. Wood
is explicit that QR is the right decomposition here *because it operates on columns
without mixing them*, preserving the column separation the iteration created;
*"alternative methods (Choleski or symmetric eigen) would require an additional
pre-conditioning step."*

#### Scope: build Appendix B in full, wire only the determinant — and why

**The maintainer directed the full Appendix B reparameterisation** (*"I think the
full appendix B parametrization makes sense to include, especially if we need to do
it for parity"*). The conditional is the right question and it was **measured** rather
than argued — tier 1, figures in `RECALIBRATION_mgcv_parity_2026-08-25.md` §1.2. The
measurement changes *which parts* are needed:

| Wood's motivation for the full reparameterisation | applies to us? | evidence |
|---|---|---|
| `log\|S\|₊` unstable under badly scaled λ | **YES, catastrophically** | the rank cut misreads the null space badly at a λ spread of 12 decades, which is inside `PRODUCTION_LOG10_BOUNDS`; the resulting score error is large enough to flip which of two optima looks better |
| `log\|XᵀWX + S\|` likewise unstable | **No** | naive `slogdet` tracks a diagonally-preconditioned Cholesky closely even at the worst conditioning reached. **Structural reason:** it is full rank and positive definite, so there is **no null-space decision to get wrong** — only the *generalised* determinant has one |
| β̂ unstable; §3.3's stable least squares | **No, and structurally so** | §3.3 exists for the **negative weights** Newton-based PIRLS produces. `gam_fit.penalized_irls_general` uses **Fisher scoring** (`w·(dη/dμ)²/V(μ)`, the expected weight), so weights are non-negative by construction. The measured `eta` degradation across the same λ range is ordinary conditioning loss, orders of magnitude below the determinant error |
| derivatives of `log\|S\|₊` w.r.t. `ρ` | **Not yet** | `select_lambdas_continuous` uses L-BFGS-B with a **finite-difference** gradient |

**Every figure behind that table is tier 1 and lives in
`RECALIBRATION_mgcv_parity_2026-08-25.md` §1.2, not here.** The structural claims —
Fisher scoring, the finite-difference gradient, full-rank versus generalised
determinant — are facts about the code and the mathematics rather than measurements,
and stand on their own.

**So the resolution, and it is the maintainer's direction taken on the evidence:**
**build Appendix B in full** — the similarity transform, the accumulated `Q_s`, the
pivoted-QR determinant *and* the stable square root `E` — as a self-contained,
R-free-testable component. **Wire only `log|S|₊` into `reml_score_general` in this
slice.** Everything else stays available and unused.

That is deliberately more than the determinant needs and deliberately less than a
re-pointing. The reason not to re-point now is not that the machinery is unwanted, it
is that **every tier-3 result this epic owns runs through the fitter path** —
ADR-195, ADR-206's 1.242e-10, ADR-208 — so adopting the reparameterisation through
the fit re-verifies all of them, and today there is no measured defect asking for it.
Building the component makes that adoption a later, additive, separately-measurable
step rather than a rewrite.

**Two futures that would change the answer, and both are plausible:**

1. **Newton PIRLS.** The target family is binomial/**cloglog** — non-canonical — and
   Wood recommends Newton over Fisher exactly there (*"the Newton scheme tends to
   converge faster than Fisher scoring in non-canonical link situations, an effect
   which can be particularly marked"*). Newton produces negative weights, and then
   §3.3 and the stable `E` become **required**, not optional.
2. **An analytic gradient for the outer search**, which Wood's whole method is built
   around and which needs Appendix B's derivative expressions:
   `∂log|S|/∂ρⱼ = λⱼ tr(S⁻¹Sⱼ)` and
   `∂²log|S|/∂ρᵢ∂ρⱼ = δⁱⱼ λᵢ tr(S⁻¹Sᵢ) − λᵢλⱼ tr(S⁻¹SᵢS⁻¹Sⱼ)`
   (all on transformed versions).

Build for both; adopt neither here.

#### What NOT to do

- **Do not change the tolerance.** Tightening it collapses the measured spread
  sharply (tier 1 — figures in `RECALIBRATION_mgcv_parity_2026-08-25.md` §1), which
  is what demonstrates the cause; it is still a tuned constant that would work only
  by luck of this spectrum — Anchor 8, and Wood's own paragraph above.
- **Do not touch the fitter, the bases or the search.** The defect is one term of one
  function.
- **Implement from the paper, not from `mgcv`'s source.** Same footing as ADR-196
  (Wood 2011 eq. 4) and ADR-202 (WPS-2016 eq. 7); transcription is barred by
  licensing anyway (Anchor 8's companion rule).

#### Defect B: the score uses the EXPECTED Hessian where Wood's eq. (4) uses the OBSERVED one

**Found by the maintainer, in one word: "Newton."** It is a formula error of exactly
the class ADR-196/197 already fixed once in this same function, and it is independent
of Defect A.

Wood eq. (4) builds the criterion on `H = −∂²l/∂β∂βᵀ`, the **observed** Hessian, which
Newton-based PIRLS produces as a by-product — §3.2's weights carry
`αᵢ = 1 + (yᵢ − μᵢ)(V′ᵢ/Vᵢ + g″ᵢ/g′ᵢ)`. `reml_score_general:147` uses
`weights · (dμ/dη)² / V(μ)` instead: the **expected** (Fisher) weight, Wood's
`αᵢ ≡ 1`. He flags the substitution directly:

> *"The simpler approach of using the expected Hessian in place of `H` was also
> investigated, but in simulations gave worse performance than GCV **when
> non-canonical links were used**."*

**The target family is binomial/cloglog. Binomial's canonical link is logit, so ours
is non-canonical** — Wood's warned case. `W` depends on `μ`, hence on `β̂`, hence on
`sp`, so the discrepancy is `sp`-dependent, which is the signature the epic has been
chasing since ADR-208.

**Why `eta` agreeing did not rule this out, which is the trap worth naming.** Fisher
scoring and Newton converge to the *same* penalized MLE — they differ in path, not in
fixed point. So β̂ and `eta` are right under either scheme, and every Stage-B `eta`
result the epic owns stays valid. **The criterion is still wrong**, because it needs a
Hessian Fisher scoring never computes. No amount of checking `eta` would have found
this; only comparing the criterion itself does.

**What to implement.** The score needs the observed Hessian's diagonal. Two routes,
and the choice is the implementer's:

1. **Derive `αᵢ` analytically** per Wood §3.2, needing `V′(μ)` and `g″(μ)` for each
   family/link. Exact, and it is what a Newton PIRLS would need anyway.
2. **Difference the per-observation deviance in `η`.** The terms are independent, so
   `Wᵢᵢ = ½·∂²Dᵢ/∂ηᵢ²` is a vectorised central difference. Cheap and family-agnostic,
   but carries the step-size error — the recalibration's own residual is at that
   level, so **route 2 alone cannot demonstrate closure at tier 3.**

Route 1 is the one that closes it. Route 2 is how the defect was found and is a
legitimate cross-check on route 1.

**Scope note.** This does **not** require switching the fitter to Newton PIRLS. The
criterion needs the observed Hessian; β̂ does not need to be *estimated* by Newton to
compute one. Whether to adopt Newton PIRLS as well is a separate question — Wood
recommends it for non-canonical links on convergence grounds — and it stays out of
this slice.

**Negative weights.** Under Newton with a non-canonical link the observed weights
*"need not all be positive"*. Measured here: none are negative on the synthetic case
(minimum ≈ 0.37). That is a property of this data, not a guarantee; sparser real ILEC
cells could produce them, and that is when §3.3's stable least squares and Appendix
B's `E` become required rather than available. Build `E`; do not wire it.

#### The registered prediction

> Wood §3.1's numerical-zero-leakage account is the mechanism. Implementing Appendix
> B's similarity transform and pivoted-QR determinant should collapse the fixed-`sp`
> difference `ours − mgcv` **to a constant across λ configurations spanning any
> number of decades** — a spread at or below what tightening the null-space cut
> already achieves, which is the tier-1 residual recorded in
> `RECALIBRATION_mgcv_parity_2026-08-25.md` §1. And it should bring free-`sp`
> `max_abs_log10_sp_diff` from **0.6398 (ADR-208, tier 3)** back toward ADR-199's
> 2-block range of **6.9e-04 – 9.8e-04**.
>
> **If the fixed-`sp` spread collapses but free-`sp` `sp` does not**, something else
> also differs under selection, the tolerance was only part of it, and *that* is the
> finding — it would mean the search has its own defect that the criterion fix has
> been masking.
>
> **Amended once already, and the amendment is the point.** The first version of this
> prediction assumed Defect A was the whole story. It is not: A alone leaves a
> residual that B accounts for almost exactly (§1.3 of the recalibration note). So the
> prediction now has a **third branch**, and a session must say which one it landed
> on: **A alone** shrinks the spread by ~3 orders and stops; **A + B** should close it
> to the level of the implementation's own arithmetic; **anything left after both** is
> a genuinely new finding and the most valuable outcome this slice can produce.

**All branches must be resolved against the slice's own tier-3 re-measurement, not
against the tier-1 figures in the recalibration note.** Step 1 of the sequencing
below exists to establish the tier-3 baseline first, precisely so this prediction has
a legitimate quantity to be judged against. ADR-203's reminder applies: register
against a *re-measurement*, never against a stored number.

#### Sequencing

1. **Establish the tier-3 baseline for the fixed-`sp` spread.** This is what makes
   the diagnosis citable and gives §4's prediction a legitimate quantity to be judged
   against. **It is not a bare dispatch of an existing probe** — that description was
   wrong when this slice was first written (PR #213 review [P1]). It needs three
   things: `scripts/gam_fixed_sp_score_probe.R` (exists), its Python side
   `scripts/gam_fixed_sp_score_compare.py` (exists — emits the `ours` column, the
   rank-at-tolerance readings and the corrected-cut spread), and **a new step in
   `.github/workflows/mgcv-conformance.yml`** wiring them, which does not exist yet.
   Budget for the workflow step.
2. **Implement Appendix B's determinant path**, R-free tests first: `log|S|₊` is
   invariant to an orthogonal similarity transform; it is exact for a
   known-rank synthetic `S`; it agrees with the naive path where the naive path is
   *reliable* (flat λ); and it does **not** move when λ's are spread. **Then run the
   mutation protocol in the next section** — an R-free test that passes against a
   wrong implementation is worse than no test, and this is the slice where that is
   most likely, because every one of those four invariants can be satisfied by an
   implementation that quietly skips the step that matters.
3. **Re-measure**, tier 1 then tier 3: the eight-point fixed-`sp` spread, then
   free-`sp` on the slice-5b case.
4. **Ledger rows at both tiers, an ADR, and the §4 prediction resolved in its own
   words.**

#### The mutation protocol — what "mutation-test each" means, since nothing defines it

**This slice is where the phrase has to stop being decoration.** It appeared twice in
an earlier draft of this document with no method behind it, and the repository has no
mutation-testing tooling at all — no `mutmut`, no `cosmic-ray`, nothing in
`pyproject.toml` or the `Makefile`. **Do not add one**: a whole-suite mutation runner
on a numerics repo is slow and mostly reports mutants that are numerically
indistinguishable. What is wanted is narrower and stronger.

**The protocol.** For each mutation below: apply it to the implementation, run the
R-free tests, and record **which test fails and on which assertion**. A mutation that
leaves the suite green is a hole in the tests, not a harmless variant — fix the test
and say so in the ADR. Revert each mutation before the next.

| # | mutation | what it models | must be caught by |
|---|---|---|---|
| 1 | skip the `Λ̂⁰ = 0` truncation (Appendix B step 5 / §3.1's "setting `Λ̂⁰ = 0`") | the whole point of the transform — the arbitrary `λ₁^{d₁}∏Λ̂⁰ᵢ` factor is left in | the spread-λ invariance test |
| 2 | replace the pivoted QR determinant with a plain Cholesky or symmetric-eigen determinant | Wood's stated reason for QR: it acts on columns without mixing them, so it preserves the separation the iteration built | the spread-λ test; the flat-λ test must still pass, which is what makes this mutation informative |
| 3 | use machine precision, not its **cube root**, for the dominant/subordinate split (step 2's `ε`) | a plausible misreading of the paper | the spread-λ test at large block-count |
| 4 | use a fixed `1e-10` for the rank count instead of `ε̃ = eps^[0.7,0.9]` (step 3) | reintroduces exactly the shipped defect | the known-rank synthetic test |
| 5 | skip the pre-step (`S̄ᵢ = U₊ᵀSᵢU₊`) for a rank-deficient `S` | Appendix B's stated precondition | the known-rank synthetic test, at deficient rank |
| 6 | transpose `Q_s` where it is accumulated | an orientation error that leaves `\|S\|` invariant | the `EᵀE = S` test — and **only** that test, which is why `E` must be tested on its own terms rather than through the score |

**Mutation 6 is the one that justifies building `E` in this slice at all.** `log|S|₊`
is invariant to a transposed `Q_s`, so every determinant test passes under it. Only
the square-root identity catches it — and if `Q_s` is wrong, the later adoption of the
reparameterisation through the fit inherits a silent orientation bug. Building `E`
now and testing it is what makes that adoption safe later.

**Record the protocol's outcome in the ADR as a table**, mutation by mutation, with
the failing test named. "Mutation-tested" without that table is the same unbacked
claim this section exists to retire.

#### Definition of done

**Tagged per ADR-209 decision 3, and NAMED.** A `[machine]` item names the test or
command that proves it; a `[judgement]` item names who confirms it. **The naming is
the point, not the tag** — a tag applied without a named check costs nothing, and an
item that cannot carry a name is an item with no method behind it yet. That is the
write-time failure ADR-209 exists to force. Tests marked *(new)* do not exist and are
part of this slice's work; naming them now is what makes their absence visible.

The PR body reproduces this list as a checklist with evidence per item, or an explicit
"NOT MET, because …".

- `[machine]` **Defect A:** `reml_score_general`'s `log|S|₊` uses Appendix B's
  transform and a pivoted-QR determinant, with no tuned tolerance in the path.
  → `test_logdet_s_is_invariant_to_lambda_spread` *(new)*, plus
  `test_no_bare_tolerance_constant_in_the_logdet_path` *(new)*, which asserts the
  shipped `1e-10` is gone rather than replaced.
- `[machine]` **Defect B:** the score's Hessian term uses the **observed** Hessian per
  Wood eq. (4), derived analytically (route 1) rather than by differencing — a
  finite-difference `H` cannot demonstrate closure at tier 3, because its own step
  error sits at the level being measured.
  → `test_analytic_alpha_matches_the_finite_difference_probe` *(new)*, cross-checking
  the analytic `αᵢ` against `scripts/gam_hessian_weight_probe.py`'s differenced `H`.
- `[machine]` `experience_gam_penalized.reml_score` **checked for the same defect and
  the finding recorded either way** — ADR-197 is the precedent for that check being
  worth running, and its answer is not assumed here.
  → `test_experience_gam_penalized_hessian_weight_provenance` *(new)*: asserts which
  weight that function uses, so the answer is recorded as a test rather than as prose.
- `[machine]` **Appendix B exists as a whole**, not just the determinant slice of it:
  the similarity transform, the accumulated `Q_s`, the pivoted-QR determinant and the
  stable square root `E`. `E` and `Q_s` are built and **deliberately unused** by this
  slice — the test that they are correct is their own, not the score's.
  → `test_E_transpose_E_reconstructs_S` and
  `test_Qs_similarity_transform_preserves_the_determinant` *(both new)*.
- `[machine]` **All six mutations in the protocol above applied**, each with its
  failing test recorded.
  → the protocol's own table; each mutation names the test that must catch it, and
  `test_E_transpose_E_reconstructs_S` is the only one that catches mutation 6.
- `[judgement]` **Any mutation that left the suite green is reported as a test hole
  that was then closed, not omitted.** → confirmed by the PR reviewer against the
  mutation table; a green mutation with no accompanying new test is the finding.
- `[judgement]` **A term-by-term audit of `reml_score_general` against Wood eq. (4),
  written into the ADR as a table** — one row per term of
  `V = Dₚ/(2φ) + log|XᵀWX + S|/2 − log|S|₊/2 − (p − r)·log(φ)/2`, each marked verified
  or defective against the paper. → confirmed by the PR reviewer, who checks the rows
  against the paper rather than against the author's summary of it. **The motivation:**
  ADR-196 found a missing penalized-deviance term in this function; Defect B is a wrong
  Hessian in it; Defect A is a wrong null-space cut in it — three defects in one
  function, each found after the previous was declared closed. Raised in PR #213's
  round-3 review.
- `[machine]` **Nothing is re-pointed.** `gam_fit.penalized_irls_general` still
  receives the untransformed design and penalty.
  → `tests/test_analytics/test_gam_family_conformance.py` (ADR-195) and
  `test_gam_multiterm_conformance.py` (ADR-206) pass **unchanged**, and
  `tests/qa/test_pipeline_golden.py` keeps `tests/qa/golden_outputs/` byte-identical.
- `[machine]` The eight-point fixed-`sp` spread measured at **tier 3** both before
  (step 1) and after the fix, so the improvement is a tier-3 delta rather than a
  tier-3 number compared against a tier-1 one.
  → `scripts/gam_fixed_sp_score_probe.R` + `gam_fixed_sp_score_compare.py`, dispatched
  through the new `mgcv-conformance.yml` step that step 1 has to build.
- `[machine]` Free-`sp` re-measured at tier 3, and ADR-208's refuted §4 prediction
  revisited in light of it.
  → the existing `gam_model_conformance.compare_free_sp_case` path, tier-3 dispatch.
- `[judgement]` **The §4 prediction resolved — confirmed or refuted, in those words**,
  and which of its three branches was landed on. → confirmed by the PR reviewer;
  escalated to the maintainer if the third branch (something left after both defects)
  is the outcome, because that reopens the epic's cost estimate.
- `[judgement]` Slice 6's BLOCKED note removed, or its reason restated if this does
  not close it. → the maintainer, since designating or unblocking a slice is a
  `ROUTINE_MGCV_PARITY.md` scheduling call rather than a session's.

**Two items stay `[judgement]` for a reason worth naming.** The eq. (4) audit and the
prediction's resolution are the ones a machine cannot check: a test can assert the
audit *table exists with N rows*, never that its rows are *right*. That is precisely
the limit ADR-209 states — the tagging guards against a MISSING claim, never a WRONG
one. Only the tier-3 oracle and ADR-193's two-producer rule do that.

### Slice 5d: localise the free-`sp` residual on the N=4 structure — optimiser or surface?

- **Depends on:** Slice 5c (ADR-210).
- **Status:** **DONE, 2026-08-29** — resolved TWICE, the same day, by two
  daily-dev sessions running concurrently against the same base and unaware
  of each other: **ADR-212** (PR #216, merged first) and **ADR-211**
  (PR #217). Both hypotheses were distinguished with evidence at both tiers,
  without needing the analytic gradient hypothesis 1 named as available to
  build on. The two findings are complementary — see "What the concurrent
  session found" below.
- **The gap, as stated when this slice was registered.** ADR-210 closed the
  fixed-`sp` REML criterion to float round-trip precision (both tiers) — the
  score itself was no longer in question. Free-`sp` selection on the same
  N=4, `ti()`-sharing-a-span structure still disagreed with `mgcv`'s own
  selection by `max_abs_log10_sp_diff = 0.7560` (tier 1) / `1.0996` (tier 3),
  and the discriminating measurement showed `mgcv`'s point scoring measurably
  BETTER than our optimiser's own converged point (`612.611` vs `612.663`,
  tier 1).
- **What was found.** The cheap step (re-running the discriminating
  measurement at tier 3) confirmed the tier-1 reading exactly and, since the
  fixed-`sp` spread is 0 everywhere, mechanically ruled out hypothesis (b)
  ("the two criteria disagree") — leaving purely an optimiser question. An
  interpolation sweep between the two points found a single smooth,
  monotonic surface (no barrier), refuting hypothesis 2 (genuine
  multi-modality) for this pair of points. A forward-difference step scan at
  the optimiser's own "converged" point localised hypothesis 1's exact
  mechanism: SciPy's L-BFGS-B default step (`eps=1.49e-8`) sits inside the
  noise floor `penalized_fit_and_score`'s nested IRLS solve creates
  (`_IRLS_TOL=1e-10` relative), so the "converged" point had a true residual
  gradient of `~0.55`, not the near-zero SciPy's own noisy estimate implied.
  **Fixed** by deriving `gam_reml_optimize._FINITE_DIFF_STEP = 1e-5` from
  this module's own measured noise floor (never from a comparison against
  `mgcv`) and wiring it into the one `scipy.optimize.minimize` call. Result,
  confirmed at both tiers: `mgcv`'s own criterion now ranks Python's
  default-start point within `0.0007` of its own optimum (was `0.0523`, a
  ~78x tighter agreement), `eta` agreement improves to `~8e-4` (from an
  earlier `3.7e-2`), `edf_total` agreement to `~0.015-0.018`. The raw
  `max_abs_log10_sp_diff` metric, however, is NOT fixed by this — and swings
  3.4x between tiers (`0.8777` tier 1, `0.2606` tier 3) while `eta` barely
  moves, which is itself the decisive evidence for a THIRD finding: the
  by-term's own smoothing parameter is weakly identified by this criterion
  on this fixture (moving it across a decade and a half changes the score by
  a few thousandths), so different converged runs — and even different R
  builds' own selections — land at different values along that near-flat
  direction without disagreeing about the fitted model. See ADR-212 for the
  full measurement.
- **What the concurrent session (ADR-211) found, and why it is not a
  duplicate.** Working the same slice at the same time, PR #217 approached it
  from the environment rather than the objective. Two results stand
  independently of the fix above. (1) **The blind search's own converged point
  moves with `OPENBLAS_NUM_THREADS` alone** — by-term `log10(sp)` reads
  `9.116` / `8.519` / `8.773` at 1 / 2 / 4 threads on one identical fixture,
  while a FIXED-`sp` evaluation of the same criterion moves by `~4e-10` across
  the same sweep. That is what made ADR-210's tier-1 (`0.7560`) and tier-3
  (`1.0996`) readings of the identical measurement disagree: a confound in the
  epic's own tooling, not a data-draw or `mgcv`-version artifact. It is now
  pinned in `.github/workflows/mgcv-conformance.yml`. (2) **Hypothesis 2 was
  refuted directly rather than by inference**: warm-starting
  `select_lambdas_continuous` at `mgcv`'s own point converges back to it
  (within `1e-6` tier 1, `1.09e-4` tier 3) at a BETTER score than the blind
  start reaches — so `mgcv`'s point is reachable under our own criterion, not
  structurally out of reach. That check is DIAGNOSTIC by ADR-193's mechanical
  test (`mgcv`'s own output is its input) and is never folded into
  `FREE_SP_MODEL_CLAIM`. A gradient step inside the objective's noise floor is
  precisely what lets BLAS summation order move the landing point, so ADR-212's
  mechanism and ADR-211's confound are two readings of one defect: ADR-212
  fixes CONVERGENCE QUALITY, ADR-211 fixes MEASUREMENT REPRODUCIBILITY, and
  neither substitutes for the other.
- **Out of scope, honoured:** the production grid selector
  (`experience_gam_penalized.select_lambdas_reml`) was not touched
  (PLAN Anchor 7, ADR-198 "Two searches, not one").
- **Acceptance, as met:** hypothesis 1 confirmed and fixed with a
  non-`mgcv`-tuned derivation; hypothesis 2 refuted for this structure; the
  residual `max_abs_log10_sp_diff` is now understood, not merely observed.
  **Unblocks slice 6** on the finding that the remaining `log10(sp)` gap is a
  weak-identifiability property of the model, not an unresolved optimiser or
  criterion defect — see slice 6's own restated note below. Whether
  `FREE_SP_MODEL_CLAIM`'s own primary metric should be revisited to weight
  `eta`/`edf` over raw `log10(sp)` remains a maintainer call (ADR-212
  Consequences). The follow-on robustness question ADR-211 registered stays
  open as slice 5e below, with its premise restated against the merged fix.

### Slice 5e: robustify the outer search's own convergence before scaling past N=4 blocks

- **Depends on:** Slice 5d (ADR-211 and ADR-212).
- **Status: DONE, 2026-08-30 (ADR-213).** `select_lambdas_continuous_multistart`
  (best-of-9, deterministic starts) built; measured, thread-pinned, at N=4
  (recovers a real single-start convergence failure at 4 threads — the
  reproducible improvement this slice's acceptance criterion asked for) and
  at a synthetic N=8 stress case (single-start already sufficed on this
  specific, deliberately-decoupled construction — a genuine answer, not the
  one the slice's premise anticipated). Cost stated: ~8-21x a single
  search's own function evaluations. See ADR-213 for the full measurement,
  what remains open (a covariate-SHARING N>4 structure, closer to the
  target formula's own shape, is untested), and why no mgcv comparison is
  made anywhere in this slice.
- **PREMISE RESTATED, 2026-08-30, against the merged fix.** This slice was
  registered by ADR-211 while ADR-212's `_FINITE_DIFF_STEP` fix was being
  written concurrently and had not yet landed. Every reading below marked
  PRE-FIX was taken against the old SciPy-default step and no longer
  describes the shipped default. What ADR-212 closed, and what it did not:
  - **Closed (mostly): the score gap.** PR #216's own post-fix thread sweep
    (reported in its review response; not independently re-measured here)
    has the production default landing in a `612.6101`-`612.6116` band
    across 1 / 2 / 4 threads — spread `0.0015`, against `612.6630`-`612.6760`
    (spread `0.013`) pre-fix, roughly 9x tighter, and now essentially tied
    with `mgcv`'s own `612.6108`. The original framing here — "a full log10
    decade short of a reachable, better-scoring point" — is no longer true
    of the SCORE.
  - **Not closed: the coordinate.** The by-term's own `log10(sp)` still
    moves with thread count post-fix (`9.60` / `9.61` / `10.75` at threads
    `{2, 4, 1}`), and `max_abs_log10_sp_diff` still swings across tiers
    (`0.8777` tier 1, `0.2606` tier 3, ADR-212). Whether that is worth
    chasing at all depends on the maintainer's reserved metric question
    (ADR-212 Consequences) — if `eta`/`edf` become the primary measure, much
    of this slice's motivation goes with it.
  - **Not answered at all: does one start still suffice at N > 4?** This is
    the part of the slice that survives the fix intact. The target formula
    has 13-21 blocks — more directions for a flat or weakly-identified
    pathology to hide in, not fewer — and nothing measured so far speaks to
    the search's behaviour above N=4. That makes this the live question
    before slice 7 (`select = TRUE`, which pushes the block count to 21),
    and arguably before slice 6 if `sz`'s own blocks interact with the
    by-term's.
- **What a blind, non-cheating multi-start check showed PRE-FIX (ADR-211):**
  bounds-centre + 8 uniform-random starts reached as low as 612.6149 in 9
  tries (closer to `mgcv`'s 612.6108 than the single default start's
  612.6630, but not equal to it), and 2 of 9 far-corner starts FAILED TO
  CONVERGE outright. Kept as the record of what motivated this slice; it is
  **not** a valid baseline for measuring any future fix, because the
  single-start number it was compared against has since moved. A first task
  for whoever takes this slice is to re-run that check against the current
  default.
- **A merge artifact to clear first, created by neither PR alone.** ADR-212
  refreshed the hardcoded `python_opt_log10` that
  `scripts/gam_fixed_sp_score_probe.R` and the `gam_multiterm_sp_delta_probe.R`
  workflow invocation carry (`6.69944259, 10.74980618, 3.29280772,
  3.02752645`), measured in its own session's container; ADR-211 then pinned
  `OPENBLAS_NUM_THREADS=1` — but only for the `compare` job, since the R
  probe's own work runs inside `docker run` and would not inherit it. Those
  two changes are individually correct and were written concurrently, so
  neither session could see the result: the discriminator now scores `mgcv`
  against a Python point that the pinned pipeline would not necessarily
  reproduce today. Not a defect in either ADR and not urgent — the point is
  hand-supplied by construction, and ADR-212 recorded its provenance
  (`nproc=4`, `OPENBLAS_NUM_THREADS=1`) precisely so this could be checked.
  Refresh it once under the pinned regime and record the reading, before
  using this discriminator as a baseline for anything in this slice.
- **Candidate approaches, not chosen here:** (1) multiple starts with a
  best-of-N selection (simple, cheap, the natural next thing to measure —
  ADR-211's own blind check is a first data point, not a designed
  experiment); (2) an analytic gradient built on Appendix B's own
  derivative expressions, already stated in slice 5c's text —
  `∂log|S|/∂ρⱼ = λⱼ tr(S⁻¹Sⱼ)` and the corresponding second derivative —
  built but unused there (`E`, `Q_s`). ADR-212 makes this one MORE
  attractive, not less: it removed a finite-difference step error, but the
  search still has no exact derivatives. (3) A different search algorithm
  (e.g. a trust-region method less sensitive to a near-flat direction than
  a finite-difference quasi-Newton line search).
- **Acceptance.** A measured, reproducible (thread-count-pinned) improvement
  at N > 4 blocks — the question the fix did not answer — stated against a
  freshly-taken POST-FIX baseline, never against the pre-fix numbers above,
  and with the chosen approach's own cost (extra fit evaluations) stated.
  Not a claim that `max_abs_log10_sp_diff` reaches zero: ADR-211's own
  multi-start data point and ADR-212's weak-identifiability finding both
  suggest that is not cheaply achievable on this specific landscape, and may
  be the wrong target entirely pending the maintainer's metric call.
- **DONE, 2026-08-30 (ADR-213).** Candidate (1), best-of-9 multi-start
  (`select_lambdas_continuous_multistart`), built and measured, thread-pinned,
  at two points: the ACTUAL N=4 fixture (multi-start recovers a real
  single-start convergence failure at 4 threads) and a synthetic N=8 stress
  case built by duplicating the N=4 shape onto an independent,
  covariate-DECOUPLED second draw (single-start already sufficed there at
  every thread count tested — a real finding, not the one the slice's
  premise anticipated). Cost: ~8-21x a single search's own function
  evaluations. See ADR-213 for the full measurement and every number.

  > **Acceptance criterion restated, 2026-08-30 (PR #218 review [P1]).** The
  > criterion as originally worded above — "a measured, reproducible
  > improvement **at N > 4 blocks**" — presupposes the answer. The N=8
  > measurement REFUTES that presupposition (single-start already
  > sufficed), so ticking the original wording "MET" overstates what was
  > found. **What the criterion actually became, and what this slice
  > delivers**: *answer*, with thread-pinned evidence, whether one start
  > still suffices past N=4 — which this slice does, on the one structure
  > tested (yes) — while separately demonstrating, on the exact N=4
  > structure the premise was restated against, that best-of-N is a real
  > and reproducible mitigation when it IS needed. Slice 5e is DONE because
  > the question is answered with evidence, not because the originally
  > anticipated failure mode was reproduced and fixed at N>4. A reader of
  > slice 6/7 (13-21 blocks) should take from this: N>4 robustness is
  > MEASURED on one (covariate-decoupled) structure, not settled in
  > general — slice 5f is exactly the structure that would settle more of it.

### Slice 5f: multi-start's own value on a covariate-SHARING N>4 structure

- **Depends on:** Slice 5e (ADR-213). **Not blocking** slice 6 or 7 — the
  same non-blocking relationship slice 5e itself had to slice 6.
- **Status:** READY, not designated. Registered per ADR-209 decision 1 ("a
  gap you open is closed or registered — never merely filed"): ADR-213's own
  N=8 stress case deliberately duplicated the N=4 shape onto an
  INDEPENDENT, covariate-decoupled second draw (to rule out a rank-deficient
  design after a covariate-reuse attempt failed that way) — and found
  single-start already sufficient there. That is real evidence for a
  decoupled structure, but the target formula's own 13-21 blocks mostly
  SHARE covariates (`AttdAge`, `PolYear`, factor levels across multiple
  terms, closer to `sz`'s own eventual shape than two independent copies
  are), which is exactly the structure ADR-213 did not test and flagged as
  open.
- **What to build.** An N>4 (6-8 block) structure where the additional
  terms reuse `AttdAge`/`PolYear`/`StudyYear_C` under different
  `by`-scalings or margins, without hitting the exact rank-deficiency ADR-213
  hit on its own first attempt (its own module docstring records what
  failed and why, as a starting point — a smaller `k` on the added terms,
  or terms whose column spans are argued rather than merely tried to be
  distinct, are both worth trying before another blind attempt).
- **Acceptance.** The same measurement shape ADR-213 used (single vs.
  best-of-9, thread-pinned at >=2 thread counts, cost stated) on a
  covariate-sharing structure — reporting whichever finding actually
  results (single suffices / multi-start meaningfully helps / neither
  converges reliably) is the deliverable; this is not registered with a
  predicted answer.
- **DONE, 2026-08-31 (ADR-214).** `scripts/gam_multistart_shared_covariates_diagnostic.py`
  built an N=8 design (the N=4 fixture's own `ref`+`by`+`ti` plus four
  `s(x, by=Group)` terms, two on `AttdAge` and two on `PolYear`, four
  independent binary indicators — a first two-indicator draft reusing one
  indicator across both variables was exactly rank-deficient by 2,
  SVD-confirmed, the mechanism recorded in ADR-214). At all three thread
  counts (1/2/4), single-start CONVERGED and matched best-of-9 EXACTLY
  (gap `0.000000` throughout); thread-to-thread spread was `0.000656` for
  BOTH — the smallest spread of any structure measured across slices
  5e/5f, tighter than ADR-213's own N=4 reading (0.001483/0.000006) and
  its decoupled-N=8 reading (0.001180/0.001165), not between them. **The
  acceptance criterion's own predicted range of outcomes resolves to
  "single suffices, and this structure is MORE stable than either prior
  one"** — the opposite of what "covariate-sharing compounds the
  pathology" would predict, for this specific construction. One
  structural feature persists regardless of N or covariate-sharing: the
  MI by-term (block index 1) sits exactly on the search's own upper bound
  at every reading across N=4 and both N=8 shapes — present but, on this
  structure, not destabilising. Cost: best-of-9 ~9x-15x a single search's
  own evaluations, inside ADR-213's own stated 8x-21x range. **Caveat
  named, not resolved:** this is one covariate-sharing construction
  (independent `by`-indicators), not `sz`'s own constrained
  parameterisation (slice 6) — evidence about the outer search's
  robustness, not a preview of `sz`'s own basis behaviour. See ADR-214.

### Slice 6: `bs = "sz"` — orthogonal factor-smooth interactions

- **Depends on:** Slices 2, 4
- **BLOCKED, 2026-08-25** (PR #212 review [P1], CONFIRMED at tier 3 same day);
  **RESTATED, 2026-08-29** (ADR-210): diagnosed as an optimiser-convergence
  question rather than a criterion one; **UNBLOCKED, 2026-08-29, same day**
  (ADR-212): slice 5d localised the optimiser defect to a specific,
  now-fixed finite-difference-step bug (`gam_reml_optimize._FINITE_DIFF_STEP`)
  and found the REMAINING `max_abs_log10_sp_diff` residual is a weak-
  identifiability property of the by-term's own smoothing parameter on this
  fixture (the metric swings 3.4x between tiers while `eta`/`edf` agree
  tightly and consistently at both) — not an unresolved defect a fourth
  basis's own `sp` selection would compound. The concurrently-written ADR-211
  reaches the same unblock from the other side: `mgcv`'s own point is
  REACHABLE under our criterion (a warm start converges back to it at a
  better score than the blind start reaches), so what remains is a named,
  characterised robustness question (slice 5e) rather than an unlocalised
  one — the same status slice 5 itself shipped under (ADR-206 named the
  N>2 search extension as follow-on work rather than blocking on it). **Status: READY**, same
  registration mechanism slices 5b/5c/5d used — designating it for a session
  is still a `ROUTINE_MGCV_PARITY.md` scheduling call, and per the routine's
  "one slice per session" rule this was not started the same session as 5d.

  **Stage A DONE, 2026-08-31** (ADR-215, tier 1 AND tier 3 confirmed identical,
  CI run 33353326193). `gam_basis_cr.sz_basis` —
  a single-factor construction independently re-derived from `mgcv`'s measured
  behaviour (the raw, un-rescaled per-level `cr` block tensored against a
  factor-level indicator, one shared `scale.penalty` factor, then a
  contrast-against-the-last-level constraint — NOT a transcription of
  `mgcv:::XZKr`, which has no closed-form statement in `mgcv`'s own
  documentation) — agrees with `smoothCon(bs="sz", absorb.cons=TRUE)` to float
  round-trip precision (~1e-14) on `design_X`, every `penalty_S` block and
  `rank`, on a synthetic three-level-factor case and the target formula's own
  `AttdAge` (k=13) / `PolYear` (k=6) knots at two levels (matching
  `FaceSize`/`Smoke`). `SZ_BASIS_CLAIM` declares all three quantities
  `INDEPENDENT`. **PLAN §6's own "hardest basis" prediction did not bite Stage
  A** — no iteration was needed once `mgcv`'s constraint machinery was
  instrumented and understood; see ADR-215. **Scope: single factor, no `id`**
  (every one of the target's four terms fits this exactly). **Stage B —
  a multi-term fit including an `sz` term — is NOT yet built**, registered
  below as slice 6b.

Sum-to-zero factor-smooth deviations from a reference smooth. Four terms in the target.
Expect this to be the hardest basis of the three: the constraint and reparameterisation are
where `mgcv`-specific machinery lives, and Stage A is the only place a mistake is cheap.

### Slice 6b: `sz` Stage B — a multi-term fit including an `sz` term

- **Depends on:** Slice 6 (ADR-215).
- **Status: DONE, 2026-08-31** (ADR-216, tier 1 AND tier 3 confirmed, CI run
  33393744694). `gam_model.assemble_model_design` now dispatches `basis="sz"`
  (via `TermSpec.n_levels`, an input never derived from a sample's own
  observed factor codes, Anchor 4). `gam_multiterm_sz_conformance.py`
  assembles and fits `s(AttdAge,k=13,bs="cr") + s(FaceSize,AttdAge,k=13,
  bs="sz",xt=list(bs="cr"))` — the target formula's own first `sz` term
  verbatim, PLAN Section 1 — at a fixed `sp`, agreeing with `mgcv`'s native
  fit on `eta` at `3.921e-12` (tier 1) / `3.912e-12` (tier 3), the first
  measurement, no iteration needed — the same shape ADR-206's own first
  multi-term result had. `SZ_MULTITERM_CLAIM` declares `eta` INDEPENDENT.
- **What was built.** The same pattern ADR-206 used for the `ti`/numeric-`by`
  terms: assemble a multi-term design (a reference `cr` smooth plus one `sz`
  term) via `gam_model.assemble_model_design`, fit at a fixed,
  externally-supplied `sp` per block with `penalized_irls_general`, and
  compare `eta` against a native `gam()` fit of the identical formula.
  **Not built, named rather than silently skipped:** extending slice 4 part
  B's `select_lambdas_continuous` to an `sz`-shaped block structure (one
  smoothing parameter per factor level); a model combining `sz` with
  `ti`/`by`; a model with more than one `sz` term. See ADR-216's
  "Consequences" section.
- **Acceptance — MET.** An INDEPENDENT `eta` comparison (ADR-206's own
  pattern) on a multi-term model containing at least one `sz` term, agreeing
  to a derived — not tuned — tolerance (`1e-9`, the same order ADR-206's
  `MULTITERM_CLAIM` used). Not blocking slice 7 (the same non-blocking
  relationship slice 5f had to slice 6).

### Slice 7: `select = TRUE`

- **Depends on:** Slices 4-6
- **Status: DONE FOR STAGE A AND A FIXED-`sp` STAGE B, 2026-09-01** (ADR-217,
  tier 1 AND tier 3 confirmed identical, CI run 33417357327). The at-bound
  guard collision below is FIXED (`strict=` parameter, the reviewer's own
  suggested shape). **Stage A**: `gam_select_penalty.null_space_penalty` —
  ONE basis-agnostic rule (eigendecompose the sum of a term's own existing
  penalty block(s) at their natural, unscaled magnitude; the extra penalty
  is `U0 @ U0.T` for the null-space eigenvectors) — agrees with `mgcv`'s own
  `gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S` to float round-trip
  precision on all six target-formula term archetypes (`cr` reference x2,
  the `by` MI term, `ti`, `sz` x2), no per-basis special-casing needed.
  **Stage B**: the same three-term model ADR-206 verified, now fit with
  `ModelSpec.select=True` (7 blocks) via `gam_model.assemble_model_design`,
  agrees with `mgcv`'s native `select=TRUE` fit on `eta` to `6.164e-11`
  (tier 1) / `5.691e-11` (tier 3) — no iteration needed on either stage.
  **What remains**: extending
  `select_lambdas_continuous`/`fit_polaris_gam`'s own free-`sp` search to
  the doubled/increased block count `select=True` produces — nothing here
  reproduces PLAN §1's own headline 13→21/47.36→16.96 figures yet, since
  every case measured uses a fixed, externally-supplied `sp`. See ADR-217
  and `docs/CONFORMANCE_LEDGER.md`.

`mgcv`'s double penalty — an extra null-space penalty per smooth, so a term can shrink to
exactly zero. Takes the smoothing-parameter count from 13 to **21**, and total edf from
47.36 to 16.96 on synthetic data of the target's shape. It is a **term-selection mechanism
inside penalized likelihood**, and it is the reason `gamboost` is not a parity target.

**Known collision, filed by PR #212 review round 2 (2026-08-25) — FIXED, 2026-09-01
(ADR-217).** `gam_model.fit_polaris_gam`'s at-bound guard (added for slice 5b) raised
`PolarisComputationError` whenever the selected `log10(sp)` landed on *either*
search bound. The lower bound genuinely indicates a defect and still raises
unconditionally; the upper bound (λ→∞) is exactly what `select = TRUE` is meant to
produce for a shrunk-to-zero term, so it is now reported on the fit
(`PolarisGAMFit.at_bound`/`.at_bound_blocks`) by default rather than raised, with a new
`strict=True` parameter for the conformance/harness mode that still wants a hard raise
at either bound — the reviewer's own suggested shape
(`docs/DEV_SESSION_LOG_2026-08-25_mgcv_parity_slice5b_polarisgam.md`'s "PR #212 review
response, round 2" section).

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
