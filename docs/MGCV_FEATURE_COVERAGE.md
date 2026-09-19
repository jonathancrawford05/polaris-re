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
| `ti` | tensor interaction, margins constrained out | **yes** | ✅ tier 3 (ADR-205) | ✅ tier 3 fixed + free `sp` | best-verified after `cr` |
| `sz` | sum-to-zero factor-smooth interaction | **yes** | ✅ tier 3 (ADR-215) | ✅ fixed `sp` only (ADR-217) | free-`sp` search never exercised on this block shape. **DEPRIORITISED to L11** (maintainer, 2026-09-16: "not absolutely necessary") — its penalty count grows with factor levels, unlike `fs` |
| `raw` | caller supplies design + penalty | n/a | n/a | n/a | not an mgcv basis; the `paraPen` escape hatch |
| **`re`** | **random effect (identity penalty)** | **NO** | — | — | **named in the objective; the backbone of HGAMs** |
| **`tp`** | **thin-plate regression spline** | **NO** | — | — | **mgcv's DEFAULT — a bare `s(x)` is inexpressible** |
| `te` | full tensor product | **NO** | — | — | shares `ti`'s machinery minus the `mc` constraint |
| `t2` | alternative tensor decomposition | **NO** | — | — | genuinely different penalty decomposition |
| **`fs`** | **factor-smooth interaction (random smooths)** | **NO** | — | — | **maintainer-requested 2026-09-16, ladder rung L6.** One penalty per marginal null-space dimension, **independent of factor level count** — see `docs/MGCV_NOTATION_PRIMER.md` §4 |
| `cc` | cyclic cubic | **NO** | — | — | not in the target form |
| `ps` / `cp` | P-splines | **NO** | — | — | `experience_gam_penalized` has its own, unrelated to this engine |
| `gp`, `mrf`, `sos`, `ds`, `so` | Gaussian-process, Markov-random-field, sphere, Duchon, soap | **NO** | — | — | not in the target form |

**Also missing on the `by` axis:** factor-`by` (`s(x, by = fac)`). Only numeric
`by` exists, and there is **no partial route to it** — `TermSpec.by` is
documented as *numeric*, and `TermSpec.factor` is **not** a factor-`by` flag: it
marks the `sz`/`fs` construction, is explicitly *mutually exclusive* with `by`,
and `sz` already has its branch. So L3 needs a representation decision (widen
`by`, or add a field), not just a missing `elif`.

> **Corrected 2026-09-18.** This paragraph previously read *"`TermSpec` has a
> `factor` flag but `assemble_model_design` has no branch for it"*, which implied
> the flag was a half-built factor-`by` route. `gam_term_spec.py:78-79` says
> otherwise. Caught while sizing the rung in `PLAN_mgcv_capability_ladder.md` —
> by reading the code rather than this file, which is the §5 lesson applied to
> §5's own document.

### 2.2 Families and links

| family / link | expressible? | Stage B | notes |
|---|---|---|---|
| `poisson(log)` | **yes** | ✅ tier 3 (ADR-195) | |
| `quasipoisson(log)` | **yes** | ⚠️ partial | `reml_score_general` **raises** on `dispersion_fixed=False` — see §2.3 |
| `binomial(logit)` | **yes** | ✅ tier 3 (ADR-195) | |
| `binomial(cloglog)` | **yes** | ✅ tier 3 (ADR-195) | the target formula's own family |
| **`gaussian(identity)`** | **yes** (2026-09-19, L1) | ✅ tier 3, **fixed `sp` only** (ADR-229) | `eta` `2.442e-14` and `edf_total` `-7.105e-15` against ADR-221's committed criterion, on the tier-3-verified three-term design with only the family changed. **FIXED `sp` ONLY**: Gaussian estimates its scale and `reml_score_general` raises on a free one until **L5** (slice 3), so free-`sp` selection under this family is neither measured nor claimed. Also closed-form verified (IRLS vs `lstsq` and vs the closed-form ridge, both `1e-12`) |
| `Gamma`, `inverse.gaussian` | **NO** | — | |
| `nb` / `negbin` | **NO** | — | |
| `tw` (Tweedie) | **NO** | — | |
| `ocat`, `scat`, `betar`, `ziP` | **NO** | — | extended families |
| location-scale (`gaulss`, `gammals`, …) | **NO** | — | multi-linear-predictor |

`_FAMILY_LINKS` in `gam_model.py` is a **five**-entry dict (four since slice 3,
plus `gaussian`/`identity` at L1 on 2026-09-19), deliberately with no fallback —
an unrecognised pair raises rather than guessing. **Being in that dict means
"expressible", not "verified against mgcv"**: its docstring splits the two
claims, and the Stage B column above is the authority.

### 2.3 Fitting machinery

| feature | status | notes |
|---|---|---|
| Penalized IRLS at fixed `sp` | ✅ tier 3 | `gam_fit.penalized_irls_general` (ADR-195) |
| REML criterion (`gam`'s) | ✅ tier 3 | `gam_reml.reml_score_general` (ADR-197, ADR-210) |
| Continuous outer `sp` search | ✅ | `gam_reml_optimize`; see §3 for its caveats |
| Analytic REML gradient | ✅ | Wood (2011), ADR-220 |
| `select = TRUE` | ✅ tier 3 | null-space double penalty (ADR-217); **objective item 3, DONE** |
| **Scale-estimated REML** | **NO** | blocks quasi-Poisson, Gaussian, Gamma, Tweedie — everything with a free scale |
| **`fREML`** | **NO** | `bam`'s criterion; a *different* criterion, not a faster REML |
| **`bam`** | **NO** | **objective item 2**; deferred 2026-08-10 (PLAN §3) |
| **`discrete = TRUE`** | **NO** | **objective item 2**; a different algorithm (Wood/Li/Shaddick/Augustin) |
| **Unpenalized parametric block** | **NO** | `assemble_model_design` builds an intercept then penalized terms only — no route for parametric *columns*. The target formula has `FaceSize + Smoke + FaceSize:Smoke` |
| `gamm` / `lme4` route | **NO** | out of scope unless the objective changes |
| Unconditional covariance (Kass-Steffey / WPS) | ⚠️ known-defective | standing BLOCKER, ADR-190 / ADR-202 |

### 2.4 Scorecard against the stated objective

| objective item | status |
|---|---|
| 1. A suite of model forms, incl. `ti`, `bs="re"` | **partial** — 3 bases of ~14; `ti` ✅, **`re` ✗**, and mgcv's default `tp` ✗ |
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

> **L1–L5 are the ACTIVE EPIC as of 2026-09-18** (maintainer direction):
> **`docs/PLAN_mgcv_capability_ladder.md`**. That plan sequences these rungs into
> five slices; it does **not** renumber them. Note its one reordering — L5 is
> pulled forward to slice 3 — because it is on the **critical path to L9/L10**
> (`fREML` needs free-scale handling) while being the epic's least-measured
> estimate, and because it closes a **live** hole: `quasipoisson` is marked
> expressible above and raises at free `sp` today. `PLAN_…ladder.md` §2.1 gives
> the argument in full, including the case against it.

| # | rung | why here | rough size |
|---|---|---|---|
| **L1** ✅ | **`gaussian(identity)`** | **CLIMBED 2026-09-19 (ADR-229), fixed `sp` only.** The simplest family. Decouples every later basis check from IRLS confounds: at Gaussian identity the penalized fit is a single linear solve, so a basis disagreement cannot hide behind IRLS convergence. Also what every mgcv textbook check uses. | small |
| **L2** | **`bs="re"`** | Named in the objective. The **cheapest basis in mgcv** — model matrix is the level indicators, penalty is the identity, **always exactly one smoothing parameter** regardless of level count — and the backbone of hierarchical structure. In actuarial terms this *is* credibility: Bühlmann-Straub is a random-effects model. Highest value-to-effort on the board. | small |
| **L3** | **factor-`by`** (`s(x, by = fac)`) | Completes the `by` axis (numeric `by` already done). **Note it is not a term parameter but a term multiplier**: `s(x, by = f)` on a 3-level factor produces *three separate smooths*, each with its own `sp` (measured). | small–medium |
| **L4** | **Unpenalized parametric block** | The target formula opens with `FaceSize + Smoke + FaceSize:Smoke`. Today `assemble_model_design` cannot carry unpenalized columns at all, so the target formula is inexpressible for this reason *as well*. (Was wiring slice 1c.) | small |
| **L5** | **Scale-estimated REML** | Unblocks quasi-Poisson, Gaussian, Gamma, Tweedie — everything with a free scale. `reml_score_general` currently *raises* on `dispersion_fixed=False`. Gates L1's usefulness at free `sp`. | medium |
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
are registered as an epic with slices, acceptance criteria and a named blocker:
`docs/PLAN_mgcv_capability_ladder.md` (2026-09-18). A successor epic for L6–L8 is
expected but deliberately unregistered until it is sized.

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
