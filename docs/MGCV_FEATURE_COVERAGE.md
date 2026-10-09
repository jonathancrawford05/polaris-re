# mgcv feature coverage — what the engine can express, and what is verified

> **This file exists because a docstring's prose became a load-bearing target
> for two weeks and nothing in the repo could contradict it.**
> `CONFORMANCE_LEDGER.md` is a hypothesis log — one row per thing tried. It
> cannot answer *"can we express `s(x, bs='re')` yet?"*, and that is the question
> the objective turns on. This file answers it, in one table, and is updated by
> the slice that changes the answer.

**Created 2026-09-16**, from the maintainer's own statement of the objective.

---

## 1. The objective, in the maintainer's words

> 1. **mgcv parity for a suite of model forms**, including `ti`, `s(..., bs='re')`, etc.
> 2. **`fREML` and `discrete=TRUE` as well as `bam`** are also desirable for efficient fitting.
> 3. **`select=TRUE`** helps to incorporate credibility into parameter estimates automatically.
>
> *"All of these and other core mgcv features are the target … really any
> hierarchical gam (or bam) specification in mgcv."*

**The dashboard is NOT the target.** It was spun up as a placeholder given what
is available in Python, and it is not a parity target except insofar as it falls
out of the capability ladder below. `docs/PLAN_gam_production_wiring.md` slice 1
learned this the expensive way — see §5.

**The concrete reference point** is `PLAN_mgcv_parity_engine.md` §1's
`hgam_formula`, a `bam(..., discrete = TRUE, select = TRUE)` call. Note what it
contains and what it does not:

```r
FaceSize + Smoke + FaceSize:Smoke +                              # parametric
s(AttdAge, k = 13, bs = "cr") +                                  # reference age
s(PolYear, k = 6,  bs = "cr") +                                  # reference duration
ti(AttdAge, PolYear, k = c(13, 6), bs = "cr") +                  # age x duration
s(FaceSize, AttdAge, bs = "sz", k = 13, xt = list(bs = "cr")) +  # level deviations
s(Smoke,    AttdAge, bs = "sz", k = 13, xt = list(bs = "cr")) +
s(FaceSize, PolYear, bs = "sz", k = 6,  xt = list(bs = "cr")) +
s(Smoke,    PolYear, bs = "sz", k = 6,  xt = list(bs = "cr")) +
s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")                  # the MI term
```

It is the **ANOVA decomposition** (`s + s + ti`), it carries a **parametric
block**, and **there is no `te` anywhere in it.**

---

## 2. Coverage today

**Stage A** = the basis/penalty matrices compared against `mgcv`'s own, term in
isolation. **Stage B** = a fitted model compared on `eta`/`edf`. **Tier 3** =
confirmed on the pinned oracle digest, per `ROUTINE_MGCV_PARITY.md`.

### 2.1 Smooth bases

| `bs=` | what it is | expressible? | Stage A | Stage B | notes |
|---|---|---|---|---|---|
| `cr` | Wood's cubic regression spline | **yes** | ✅ tier 3 (ADR-194) | ✅ tier 3 | the workhorse; supplied + default knots |
| `cr` + numeric `by` | varying-coefficient smooth | **yes** | ✅ tier 3 (ADR-200) | ✅ tier 3 | the MI term's own form |
| **`cr` + factor `by`** | **term multiplier — one separate smooth per level** | **yes** (2026-09-26, L3) | ✅ tier 3, exact per level (ADR-232) | ✅ tier 3, **fixed AND free `sp`** (ADR-232) | one smoothing parameter PER LEVEL (unlike numeric `by`'s single shared one); the shared no-`by` `cr` construction, masked to one level after the constraint is absorbed — see `gam_basis_cr.py`'s module docstring |
| `ti` | tensor interaction, margins constrained out | **yes** | ✅ tier 3 (ADR-205) | ✅ tier 3 fixed + free `sp` | best-verified after `cr` |
| `sz` | sum-to-zero factor-smooth interaction | **yes** | ✅ tier 3 (ADR-215) | ✅ fixed `sp` only (ADR-217) | free-`sp` search never exercised on this block shape. **DEPRIORITISED to L11** (maintainer, 2026-09-16: "not absolutely necessary") — its penalty count grows with factor levels, unlike `fs` |
| `raw` | caller supplies design + penalty | n/a | n/a | n/a | not an mgcv basis; the `paraPen` escape hatch |
| **`re`** | **random effect (identity penalty)** | **yes** (2026-09-21, L2) | ✅ tier 3, exact (ADR-230) | ✅ tier 3, **fixed AND free `sp`** (ADR-230) | Stage A `max_abs_X_diff`/`max_abs_S_diff` exactly `0.000e+00` at both 4 and 7 levels — `absorb.cons` measured to not change mgcv's own output for this basis. Stage B: fixed `sp` (gaussian identity) `max_abs_eta_diff=2.176e-14`; free `sp` (poisson log, so it does not wait on L5) `max_abs_eta_diff=3.226e-05`, `log10(sp)` diff `0.0010` — both inside ADR-221's `2e-2`/`1.0` gate |
| **`parametric`** | **unpenalized main effect / interaction of factors** | **yes** (2026-09-27, L4) | ✅ tier 3, exact (ADR-233) | ✅ tier 3, **fixed AND free `sp`** (ADR-233) | not an `mgcv` smooth class — `mgcv`'s own formula parser builds it via `model.matrix()` under `contr.treatment`, the same call an `lm()`/`glm()` formula uses, with ZERO smoothing parameters. Stage A `max_abs_design_diff` exactly `0.000e+00` on all 3 terms of the target formula's own `FaceSize + Smoke + FaceSize:Smoke` (no fit needed — the block doesn't depend on `sp`/`y`/the smooth). Stage B (gaussian identity, paired with `s(AttdAge)`), tier 3: fixed `sp` `max_abs_eta_diff=1.066e-14`; free `sp` `max_abs_eta_diff=3.261e-07` — both far inside ADR-221's `2e-2`/`1.0` gate |
| **`tp`** | **thin-plate regression spline** | **NO** | — | — | **mgcv's DEFAULT — a bare `s(x)` is inexpressible** |
| `te` | full tensor product | **NO** | — | — | shares `ti`'s machinery minus the `mc` constraint |
| `t2` | alternative tensor decomposition | **NO** | — | — | genuinely different penalty decomposition |
| **`fs`** | **factor-smooth interaction (random smooths)** | **NO** | — | — | **maintainer-requested 2026-09-16, ladder rung L6.** One penalty per marginal null-space dimension, **independent of factor level count** — see `docs/MGCV_NOTATION_PRIMER.md` §4 |
| `cc` | cyclic cubic | **NO** | — | — | not in the target form |
| `ps` / `cp` | P-splines | **NO** | — | — | `experience_gam_penalized` has its own, unrelated to this engine |
| `gp`, `mrf`, `sos`, `ds`, `so` | Gaussian-process, Markov-random-field, sphere, Duchon, soap | **NO** | — | — | not in the target form |

**The `by` axis is now complete.** Numeric `by` (the MI term's own form,
ADR-200) and factor `by` (`s(x, by = fac)`, capability ladder rung **L3**,
ADR-232) both exist, as genuinely different constructions: `TermSpec.by`
(numeric) scales an *unconstrained* basis; `TermSpec.by_factor`/`.by_level`
(factor) *masks a constrained* basis to one level and is a term
**multiplier** — `gam_term_spec.factor_by_terms` expands one factor-`by`
term into its `n_levels` separate `TermSpec`s, matching `mgcv`'s own
per-level bookkeeping (`m$smooth` carries one entry per level). Both remain
mutually exclusive with `TermSpec.factor` (the `sz`/`fs` marker) and with
each other.

> **Corrected 2026-09-18, resolved 2026-09-26 (ADR-232).** This paragraph
> previously read *"`TermSpec` has a `factor` flag but `assemble_model_design`
> has no branch for it"*, which implied the flag was a half-built factor-`by`
> route. `gam_term_spec.py:78-79` said otherwise, and sizing the rung in
> `PLAN_mgcv_capability_ladder.md` correctly identified the real gap: a
> **representation decision** (widen `by`, or add a field) was owed before any
> basis work. The decision, made when the rung was climbed: add a field
> (`by_factor`/`by_level`), never widen `by` — the two constructions are
> algebraically different (row-scale vs row-mask, unconstrained vs
> constrained), so conflating them into one field would have hidden that
> difference rather than expressed it.

**Predict at new rows (2026-10-06, preview slice P1, ADR-249).** `PolarisGAMFit.predict(newdata, type)` rebuilds `cr` (plain, numeric/factor `by`), `ti`, `re`, `parametric` and `sz` designs from stored per-term state. The design at held-out rows, in and beyond the training range, is compared with `predict.gam(type="lpmatrix")` on all seven cells (INDEPENDENT; tier 3, ADR-249: <= 1.6e-13). `cr` extrapolates linearly beyond the end knots, as `mgcv` does. `sz` is compared at the lpmatrix only (no verified free-`sp` fit). **Known limitation:** a `s(x) + s(x, by=f)` fit (3 levels) did not converge under Newton and missed ADR-221 at tier 3 on the probe's draw (eta 2.5e-02, edf +0.458) — a plateau block, recorded, not a slice; a P3 refusal candidate.

**Standard errors (2026-10-07, preview slice P2, ADR-250).** `PolarisGAMFit.vcov(unconditional=False)` and `predict(..., se_fit=True)` reproduce `predict.gam(se.fit=TRUE[, unconditional=TRUE])` on seven fitted cells, `Vp` and `Vc`, free- and fixed-scale, including a `select=TRUE` plateau row (INDEPENDENT; tier 3, ADR-250: `Vp` <= 3.0e-03, `Vc` <= 1.2e-02 relative, gate 2e-02). The 4-term HGAM held-out `eta` also agrees (P1's carried item). **Rank-deficient designs (superseded by Slice 9, ADR-255, below).** A smooth plus a factor-`by` smooth of the same covariate makes `X'WX + S` exactly singular (`rank(X) = 22` of 29 on the probe draw); ADR-249's "outer-search plateau" label is superseded: it was a criterion/rank defect (class ii).

**Formula front end (2026-10-08, preview slice P3, ADR-251).** `polaris_re.gam.gam(formula, data, family)` parses the verified subset (`s(bs="cr")` plain / numeric-`by` / factor-`by`, `s(bs="re")`, `ti(bs="cr")`, factors `a`, `a:b`, `offset(col)`) and fits it; on ten cells it agrees with `mgcv::gam(<the same string>)` on `eta`/`edf_total` (ADR-221) and exactly on smooth labels, `bs.dim`, coefficients per smooth, `nsdf` and factor level order (INDEPENDENT; tier 3, ADR-251). **Refused by name:** a bare `s(x)` (mgcv's `tp` default, rung L7), every NO row above, `scale=`, `select=True` with a factor-`by` smooth (accepted with `cr`/`by`/`ti`/`re`/parametric; two tier-3 cells, ADR-252), (a design whose unpenalised null space the data do not identify, `s(x) + s(x, by=f)`, was refused here until Slice 9 and is now fitted with a pivot, below). Factor levels follow the oracle image's `en_US.UTF-8` collation for `[A-Za-z0-9_]` strings, or a Polars `Enum`'s declared order.

**Rank pivoting (2026-10-09, parity Slice 9, ADR-255).** `fit_polaris_gam` / `gam()` eliminate each structurally unidentified coefficient (`S_j v = 0` for all penalties and `X v = 0`) by column-pivoted QR and fit the reduced design; the function space, `eta` and `edf_total` are unchanged. `s(x) + s(x, by=f)` and `f + s(x) + s(x, by=f)` now agree with `mgcv` on `eta`, `edf_total`, term structure and the `Vp`-based `se` (INDEPENDENT; tier 3, run 37977750939: `eta` <= 8.5e-05, `edf` <= +0.0037, `Vp` `se` 1.7e-04, all converged). **Recorded limitations of a pivoted fit:** the unconditional covariance `Vc` is REFUSED (eq. (7)'s `V''` depends on which coefficient is eliminated: 1.8e-2..9.5e-2 against `mgcv` across pivots, tier 1), and per-term edf is pivot-dependent (summary comparison: 1 of 2 rank-deficient cells misses `summary.gam` by 1.002, the other agrees; `edf_total` agrees on both). `select=TRUE` with a factor-`by` smooth stays refused.

### 2.2 Families and links

| family / link | expressible? | Stage B | notes |
|---|---|---|---|
| `poisson(log)` | **yes** | ✅ tier 3 (ADR-195) | |
| `quasipoisson(log)` | **yes** | ✅ tier 3, score level (ADR-231) AND fit level at free `sp` (ADR-235). **Dispersion exposed (ADR-238): `PolarisGAMFit.dispersion.fletcher` — Fletcher (2012), what mgcv reports as `m$scale`; Pearson and deviance also exposed, as different numbers.** The default (Newton, one `initial.spg` start) agrees from one start (ADR-245, ADR-248 made it the default); the old L-BFGS-B single start could miss mgcv's basin (slice 3d) | `reml_score_general`'s free-scale branch (L5, ADR-231) reproduces `mgcv`'s own `m$gcv.ubre` **pairwise-difference** (quasi-likelihood has no proper saturated log-likelihood, so the absolute score carries its own small additive residual — same convention ADR-196 already accepted for the known-scale Poisson criterion). The FIT-level free-sp measurement landed in ladder slice 3b (ADR-235, tier 3, INDEPENDENT). **The OTHER mgcv dispersion mode** — an externally-supplied fixed `scale`, distinct from estimating it — measured in ladder Slice 7 (ADR-236, tier 3, INDEPENDENT): **agrees at phi=2, DISAGREES at phi=6** (second stationary point; slice 7b). `mgcv`'s `poisson(scale=)` ignores `scale` |
| `binomial(logit)` | **yes** | ✅ tier 3 (ADR-195) | |
| `binomial(cloglog)` | **yes** | ✅ tier 3 (ADR-195) | the target formula's own family |
| **`gaussian(identity)`** | **yes** (2026-09-19, L1) | ✅ tier 3 fixed `sp` (ADR-229); ✅ **free `sp`, tier 3** (ADR-231) | `eta` and `edf_total` agree to **order `1e-14`** at fixed `sp` against ADR-221's committed criterion (`2e-2` / `1.0`), on the tier-3-verified three-term design with only the family changed. **No single figure is quoted here on purpose**: the reading is NOT bit-reproducible across oracle runs — five runs gave three distinct `max_abs_eta_diff` values and two distinct `edf_total_diff` values, while `edf_total` read `55.972550` on both sides every time. Treat a last-bits difference as host noise, not a regression; **ADR-229** has the numbers and the (unestablished) mechanism. **FREE `sp`, unblocked 2026-09-26 (L5, ADR-231)**: the IDENTICAL recipe refit under `mgcv`'s own free-sp REML selection agrees on the first measurement — see ADR-231 for the tier-3 figures. Also closed-form verified (IRLS vs `lstsq` and vs the closed-form ridge, both `1e-12`) |
| `Gamma`, `inverse.gaussian` | **NO** | — | |
| `nb` / `negbin` | **NO** | — | |
| `tw` (Tweedie) | **NO** | — | |
| `ocat`, `scat`, `betar`, `ziP` | **NO** | — | extended families |
| location-scale (`gaulss`, `gammals`, …) | **NO** | — | multi-linear-predictor |

`_FAMILY_LINKS` in `gam_model.py` is a **five**-entry dict (four since slice 3,
plus `gaussian`/`identity` at L1 on 2026-09-19), deliberately with no fallback —
an unrecognised pair raises rather than guessing. **Being in that dict means
"expressible", not "verified against mgcv"** — the next pair added will sit
there unmeasured until its own slice measures it.

All five entries happen to be mgcv-verified today, but **not to the same
reach**, and the fault line is **the free scale**, not the count/binary divide:

- **All five** at **fixed `sp`** — ADR-195 for the four count/binary pairs,
  ADR-229 for `gaussian`/`identity`.
- **`quasipoisson(log)` and `gaussian(identity)` stop there**, for the same
  reason: both are `dispersion_fixed=False`, so `reml_score_general` raises
  until **L5**. That is why the `quasipoisson` row above reads `⚠️ partial` and
  why §2.3's scale-estimated-REML row names the two families together. **L5
  unblocks two of them, not one.**
- **Free-`sp` selection** is measured on `binomial(cloglog)` — the target
  formula's own family — by the REML/selection work (ADR-210, ADR-217/218,
  slices 5b/7b), **not** by ADR-195, which is the fixed-`sp` result (§2.3's
  first row).

The docstring carries that split so it travels with the code; the Stage B
column above is the authority.

### 2.3 Fitting machinery

| feature | status | notes |
|---|---|---|
| Penalized IRLS at fixed `sp` | ✅ tier 3 | `gam_fit.penalized_irls_general` (ADR-195) |
| REML criterion (`gam`'s) | ✅ tier 3 | `gam_reml.reml_score_general` (ADR-197, ADR-210) |
| **Outer `sp` search — safeguarded Newton (DEFAULT)** | ✅ tier 3 (2026-10-06, ADR-241..248) | `gam_reml_newton.newton_select_lambdas`, `fit_polaris_gam`'s default since ADR-248: exact Hessian, `mgcv`'s step controls and `conv.tol`, ONE `initial.spg` start, deterministic. Meets ADR-221 on all ten gauntlet rows from one start (ADR-245/246), BLAS-thread reproducible (ADR-247). **Known limitation:** on a low-curvature direction (~4e-4) a 1e-6 relative gradient test resolves `log10(sp)` to ~0.5 decade, ours and `mgcv`'s alike — `log10(sp)` is reported, never gated (ADR-248) |
| Continuous outer `sp` search (L-BFGS-B) | ✅ diagnostic only | `gam_reml_optimize`, `outer="lbfgsb"` (with `multistart`, seeded starts); kept for the recorded conformance claims; see §3 for its caveats |
| Analytic REML gradient | ✅ | Wood (2011), ADR-220 |
| `select = TRUE` | ✅ tier 3 | null-space double penalty (ADR-217); **objective item 3, DONE** |
| **Scale-estimated REML** | ✅ tier 3 (2026-09-26, **L5**, ADR-231) | `gam_reml.reml_score_general`'s free-scale branch — Wood (2011) eq. (4) profiled over the unknown scale, `phi_hat = Dp/(n-Mp)`. Unblocks Gaussian and quasi-Poisson (both registered); Gamma and Tweedie are not yet registered families regardless. See §2.1/§2.2 for the fit- and score-level readings |
| **`fREML`** | **NO** | `bam`'s criterion; a *different* criterion, not a faster REML |
| **`bam`** | **NO** | **objective item 2**; deferred 2026-08-10 (PLAN §3) |
| **`discrete = TRUE`** | **NO** | **objective item 2**; a different algorithm (Wood/Li/Shaddick/Augustin) |
| **Unpenalized parametric block** | ✅ tier 3 (2026-09-27, **L4**, ADR-233) | `gam_basis_parametric.parametric_design` — `mgcv`'s own `contr.treatment` dummy coding, zero smoothing parameters. Closes the LAST rung `PLAN_mgcv_capability_ladder.md`'s ORIGINAL five slices name; the target formula's own `FaceSize + Smoke + FaceSize:Smoke` is expressible |
| **`cr` + `re` + `ti` fit jointly, one model** | ✅ tier 3, **fixed AND free `sp`** (2026-09-28, ADR-234, Slice 6) | Each basis was individually verified; composed, `gaussian(identity)` fixed/free `sp` and `poisson(log)` free `sp` agree with `mgcv` (`eta` ≤ 3e-5, run 36476048762). One dataset; `select=TRUE` and quasi-Poisson dispersion not exercised on it |
| **Quasi-Poisson: externally-supplied/fixed dispersion** (`mgcv`'s `scale = <value>`) | ✅ tier 3 at phi=2 AND phi=6 (ADR-236 measured; ADR-237 closed the far phi via a two-start search, conformance module only — production `fit_polaris_gam` unchanged, slice 7c) | Distinct from "estimate the dispersion" (Slice 3b, landed — ADR-235). Measured in Slice 7 (ADR-236): `fit_polaris_gam(ModelSpec(family="poisson"), gamma=phi)` reproduces `mgcv`'s `quasipoisson(scale=phi)` at phi=2 and does NOT at phi=6 (a lower-scoring stationary point; slice 7b). `mgcv`'s `poisson(scale=)` ignores `scale`, so the `quasipoisson()` call is the only mgcv reference |
| `gamm` / `lme4` route | **NO** | out of scope unless the objective changes |
| Unconditional covariance (Kass-Steffey / WPS) | ⚠️ known-defective | standing BLOCKER, ADR-190 / ADR-202 |

### 2.4 Scorecard against the stated objective

| objective item | status |
|---|---|
| 1. A suite of model forms, incl. `ti`, `bs="re"` | **partial** — 5 bases of ~14; `ti` ✅, `re` ✅ (2026-09-21), **the unpenalized parametric block ✅ (2026-09-27)**, and mgcv's default `tp` ✗ |
| 2. `fREML`, `discrete=TRUE`, `bam` | **not started** — explicitly deferred |
| 3. `select=TRUE` | **done** ✅ |

---

## 3. The honest read on trajectory (2026-09-16)

Sorting the parity epic's registered slices by what they buy:

| | slices | last landed |
|---|---|---|
| **Capability** (harness, `cr`, families, `ti`, `sz`, `select=TRUE`, the `ModelSpec` path) | 1, 1b, 2, 3, 5, 5b, 5c, 6, 6b, 7 | **~2026-09-01** |
| **Outer-optimiser convergence** | 4, 5d, 5e, 5f, 7b, 7c, 7d, 7e, 7f, 7g, 7h, 7i, 8 | ongoing |

**The last nine registered slices — 7b through 8 — are all outer-optimiser work
on one N=7 structure.** Feature coverage has not moved in roughly two weeks.

**And that solver work has not been aimed at the target's scale.** It is tuned at
N=4 and N=7 blocks. PLAN §1 puts the target formula at **13–21 blocks**, which
`select=TRUE` then doubles. The convergence properties being polished to the
fourth significant figure belong to a structure roughly a third of the size of
the one the objective requires.

This is **not** an argument that the solver work is wasted. A 21-to-42-parameter
outer optimisation genuinely has to be robust, and slices 7f–7h closed real
defects. It is an argument about **proportion** and about **which structure the
robustness is being demonstrated on**.

---

## 4. The capability ladder

Ordered so that each rung is verifiable against `mgcv` with the rungs below it
already trusted — the maintainer's own instruction: *"a rigorous plan that
tackles simpler mgcv features first."*

> **L1–L5 were the ACTIVE EPIC from 2026-09-18, COMPLETE as of 2026-09-27**
> (maintainer direction, `docs/PLAN_mgcv_capability_ladder.md`). That plan
> sequenced these rungs into five slices; it did **not** renumber them. Note its
> one reordering — L5 was pulled forward to slice 3 — because it is on the
> **critical path to L9/L10** (`fREML` needs free-scale handling) while being
> the epic's least-measured estimate, and because it closes a **live** hole:
> `quasipoisson` is marked expressible above and raised at free `sp` before
> ADR-231. `PLAN_…ladder.md` §2.1 gives the argument in full, including the
> case against it. A successor epic for L6-L8 is the expected next ACTIVE EPIC
> — see §5.

> **REOPENED 2026-09-27** (`PLAN_mgcv_capability_ladder.md` §2.3, maintainer
> direction). The near-term target formula is `cr` + `re` (+ `ti`) plus both
> quasi-Poisson dispersion modes — **none of L6-L11 below.** Two new slices
> (6, 7) were added to the SAME plan for the resulting gaps: fitting
> `cr`+`re`+`ti` jointly (never done — each is individually verified,
> nothing has fit all three together), and quasi-Poisson's
> externally-supplied/fixed dispersion mode (mgcv's `scale=`, distinct from
> "estimate," which is Slice 3b and also not yet run). Neither is a new
> `L`-rung — both are compositional/family-axis gaps, not a new basis — so
> they are not added to the table below; see the two new §2.3/§2.2 rows and
> the PLAN's own Slice 6/7 text. **L6-L11 are reordered behind Slices 6-7,
> not dropped.**

| # | rung | why here | rough size |
|---|---|---|---|
| **L1** ✅ | **`gaussian(identity)`** | **CLIMBED 2026-09-19 (ADR-229), fixed `sp` only.** The simplest family. Decouples every later basis check from IRLS confounds: at Gaussian identity the penalized fit is a single linear solve, so a basis disagreement cannot hide behind IRLS convergence. Also what every mgcv textbook check uses. | small |
| **L2** ✅ | **`bs="re"`** | **CLIMBED 2026-09-21 (ADR-230), fixed AND free `sp`.** Named in the objective. The **cheapest basis in mgcv** — model matrix is the level indicators, penalty is the identity, **always exactly one smoothing parameter** regardless of level count — and the backbone of hierarchical structure. In actuarial terms this *is* credibility: Bühlmann-Straub is a random-effects model. Highest value-to-effort on the board. | small |
| **L3** ✅ | **factor-`by`** (`s(x, by = fac)`) | **CLIMBED 2026-09-26 (ADR-232), fixed AND free `sp`.** Completes the `by` axis (numeric `by` already done). **Note it is not a term parameter but a term multiplier**: `s(x, by = f)` on a 3-level factor produces *three separate smooths*, each with its own `sp` (measured). | small–medium |
| **L4** ✅ | **Unpenalized parametric block** | **CLIMBED 2026-09-27 (ADR-233), fixed AND free `sp`.** The target formula opens with `FaceSize + Smoke + FaceSize:Smoke`. `mgcv` builds this via its own `model.matrix()`, zero smoothing parameters — `assemble_model_design` now carries this alongside every penalized basis. (Was wiring slice 1c.) **The last rung this plan names — L1 through L5 are all climbed.** | small |
| **L5** ✅ | **Scale-estimated REML** | **CLIMBED 2026-09-26 (ADR-231).** Wood (2011) eq. (4) profiled over the unknown scale. Unblocks Gaussian and quasi-Poisson (both registered — Gamma/Tweedie are not registered families regardless of this rung). Removed ladder L1's own "fixed `sp` only" qualifier in the same PR. | medium |
| **L6** | **`bs="fs"`** — factor-smooth interaction | **Maintainer-requested, 2026-09-16.** The "random smooths" idiom: a separate curve per level, all shrunk toward a common shape. Together with L2 it covers the HGAM taxonomy's group-level models (`docs/MGCV_NOTATION_PRIMER.md` §5). **Its penalty count is `1 + M` (M = the margin's unconstrained null-space dimension) and does NOT grow with factor levels** — measured 3 penalties at 2, 4 and 6 levels (`scripts/mgcv_penalty_count_probe.R`, **tier 3** — mgcv 1.9.4 pinned and 1.9.1 local) — so unlike `sz` it does not inflate the outer search. | medium |
| **L7** | **`bs="tp"`** | mgcv's **default** basis. Until it exists, a user writing a bare `s(x)` gets something this engine cannot express. Harder — eigen-decomposition of the thin-plate penalty — which is why it sits above the cheap rungs. | medium–large |
| **L8** | **`te` + `t2`**, checked jointly with `ti` | Completes the tensor family. `te` is largely "the `ti` machinery without the `mc` constraint", so it is cheap given `ti`; `t2` is the genuinely different one (an alternative decomposition, and note its penalty count is `2^d - 1` — measured 7 for three margins, against `te`'s 3 (`scripts/mgcv_penalty_count_probe.R`, **tier 3** — mgcv 1.9.4 pinned and 1.9.1 local)). **`ti` needs no rework.** The value of grouping is the **joint check**: their relationships on one recipe are what catch construction errors, and §5 is the live demonstration. | medium |
| **L9** | **`fREML`** | `bam`'s criterion. A different criterion, not a faster REML. | large |
| **L10** | **`bam` + `discrete = TRUE`** | Objective item 2. A different algorithm (Wood/Li/Shaddick/Augustin), not a faster `gam`. Its own epic, as PLAN §3 says — but **scheduled**, not deferred indefinitely. | large |
| **L11** | **`sz` free-`sp` search** | **DEPRIORITISED here 2026-09-16** (maintainer: `sz` "is not absolutely necessary… we come back for it"). `sz` assembles and fits at *fixed* `sp` already (ADR-215/217); what is unexercised is the outer search on its block shape. It sits last because **its penalty count grows one-per-factor-level** (measured: 2/4/6 penalties at 2/4/6 levels, `scripts/mgcv_penalty_count_probe.R`, **tier 3** — mgcv 1.9.4 pinned and 1.9.1 local), so it is the single largest contributor to the target formula's block count — and `fs` at L6 covers much of the same modelling intent at a constant 3. | medium |

**Two axes, not one list.** `cr`/`tp`/`ps`/`cc` are **marginal bases** — the slot a smooth of a continuous covariate fills. `te`/`ti`/`t2`/`sz`/`fs` are **constructions that consume a marginal basis** (via `xt = list(bs = …)`), and `re` is neither — it is a ridge penalty over factor levels with no smoothing. So `sz` is *downstream* of `cr`/`tp`, never an alternative to them, and our own `build_python_sz_term` is welded to a `cr` margin (`gam_basis_cr.sz_basis`, no `xt` on `TermSpec`). Advance the marginal axis first; constructions inherit from it. Full treatment: `docs/MGCV_NOTATION_PRIMER.md`.

**Solver work re-aims** at the target's real block count (13–21, doubled under
`select=TRUE`) rather than N=7, and is sequenced against these rungs rather than
run open-endedly between them.

**This is no longer a map with nothing behind it.** The ladder's first five rungs
were registered as an epic with slices, acceptance criteria and a named blocker:
`docs/PLAN_mgcv_capability_ladder.md` (2026-09-18) — **L1 through L5 are all
climbed (ADR-233), and the same plan was reopened the same day (§2.3) with
Slices 6-7** for the maintainer's actual near-term target formula. A
successor epic for L6–L8 remains expected but deliberately unregistered
until it is sized, and is now explicitly behind Slices 6-7 as well.

### What the ladder deliberately does not include

- **The dashboard.** Not a target (§1). It may be re-pointed once the engine can
  express what it needs, as a *consequence* of the ladder, never as a driver.
- **`gamboost`, `gamm`, soap films, MRF** — out of scope unless the objective moves.

> **`bs="fs"` was on this list until 2026-09-16**, on the reasoning that `sz`
> superseded it in the dashboard's target form (PLAN §4). That reasoning fell
> with the target: the dashboard is not a target (§1), and the maintainer asked
> for `fs` directly. It is now rung **L6**, and `sz` is **L11**.

---

## 5. Why this file exists — the two-week detour, recorded so it is not repeated

`PLAN_gam_production_wiring.md` blocker A asserted:

> The dashboard fits `deaths ~ offset(...) + te(attained_age, calendar_year) + s(duration_years) + Σ factors`.

and built a gating argument on `te`-vs-`ti` penalty semantics. **Every part of
that premise was wrong**, and it took a slice to find out:

1. **The `te(...)` came from a docstring's prose.** `TensorMIModel`'s docstring
   says *"… `te(attained_age, calendar_year)` … **where `te(attained_age,
   calendar_year)` is a tensor-product B-spline surface**"* — the same sentence
   glosses it. It also writes `s(duration_years)` for what is really
   `bs(duration_years, df=4)`. It is descriptive English, not an mgcv formula.
2. **The design is ANOVA-shaped, not tensor-shaped.** The code builds
   `bs(age) + bs(year) + bs(age):bs(year)` — main effect + main effect +
   interaction. `experience_gam_penalized`'s own docstring **already said so**:
   *"`TensorMIModel` builds `1 + bs(age) + bs(year) + interaction` — patsy's
   main-effects form."* The blocker contradicted a statement already in the
   codebase.
3. **The fit is unpenalized.** `sm.GLM(deaths, x, family=Poisson(), offset=...)`.
   No smoothing parameters exist, so "a different penalty structure" describes a
   property the shipped model does not have.
4. **Measured, `fx=TRUE`:** unpenalized, `te` and `s+s+ti` agree to **`8.88e-16`** (tier 3; `2.14e-15` tier 1).
   Penalized, they differ by `3.72e-02`. **100% of the gap is generated by a
   penalty the dashboard does not have.**
5. **The target formula has no `te` in it either** (§1).

**Three lessons, and they are why this file is structured as it is:**

- **A docstring is not a specification.** If a plan quotes source prose as a
  formula, the plan owes a citation to the *code*.
- **A coverage question needs a coverage artifact.** The ledger could not answer
  "is `te` the dashboard's model?" because it is not that kind of document.
- **State the fitting regime, not just the formula.** "Penalized or not" changed
  the answer completely here, and no version of blocker A mentioned it.

**What slice 1 is worth, correctly classified:** it measured our engine against
`mgcv` on a four-term penalized ANOVA-shaped HGAM (two main effects, a tensor
interaction, a third main effect; Poisson-log with offset; free-`sp` REML) at
`max_abs_eta_diff = 3.18e-05`, tier-3 confirmed — the best free-`sp` agreement
this epic has produced. That is a **capability data point on rung L8's
neighbourhood**, not a gate verdict. It is recorded as such in ADR-227.

---

## 6. Keeping this file true

- **The slice that changes the answer updates the table**, in the same PR. A rung
  that lands without its row moving has not landed.
- **Every ✅ names its tier.** A tier-1 reading is a hypothesis
  (`ROUTINE_MGCV_PARITY.md`); only tier 3 may appear here unqualified.
- **`expressible?` means `assemble_model_design` builds it**, not that a probe
  exists. Those are different claims and the column means the first.
- **No row is marked done on a Stage-A result alone.** `sz` is the standing
  example: Stage A verified, Stage B fixed-`sp` only, free-`sp` unexercised — and
  the table says so rather than showing a tick.
