# A working primer on `mgcv` formula notation and HGAMs

**Written 2026-09-16** for the polaris-re parity objective. **Every number in
this document was measured**, on R 4.3.3 / mgcv 1.9.1, not recalled — the
counting rules in §3 and §4 in particular are stated as predictions and then
checked against `mgcv` at the bottom of each section.

> **The measurements in §1, §3 and §4 are reproducible**:
> `Rscript scripts/mgcv_penalty_count_probe.R`. That script does not print the
> readings, it **asserts** them and exits non-zero on the first disagreement, so
> an mgcv release that changes a construction fails the probe rather than
> silently falsifying this file. A local run is **tier 1**
> (`docs/ROUTINE_MGCV_PARITY.md`); the pinned-image run in `mgcv-conformance.yml`
> is tier 3.
>
> **Status: tier 3, and on two mgcv versions.** The probe passes locally on
> **mgcv 1.9.1** (where these numbers were first taken) and on the pinned oracle
> digest, which runs **mgcv 1.9.4** — step 18, *"Assert the notation primer's
> penalty counts against the pinned mgcv"*, of the `mgcv reference (R)` job in
> run [`35371316687`](https://github.com/jonathancrawford05/polaris-re/actions/runs/35371316687/job/105685696207)
> (whole run green, on `ca8cf04`). Every counting rule in §3 and §4 is therefore
> stable across both, which is more than the tier alone would tell you: a rule
> that held on one version could have been an artifact of it.
>
> *(This first cited run `35346285484`. That run's step 18 did pass, but a
> superseding push cancelled the run's downstream job, so its top-level
> conclusion reads `cancelled` — an auditor opening the link could not tell the
> citation was sound. Cited to a job URL in a fully green run instead. PR #235
> review round 2, [P2-4].)*
>
> Both sides of that probe are `mgcv`. It is a **reference-behaviour
> measurement, not parity evidence** — Polaris is absent from it, so under
> ADR-193 nothing here may be cited as agreement between two producers.

> **Why it exists.** This project spent two weeks treating a docstring's phrase
> `te(attained_age, calendar_year)` as an `mgcv` formula when the code was
> fitting an unpenalized `bs(age) + bs(year) + bs(age):bs(year)` patsy design.
> §7 records that and the other traps. The cure for that class of mistake is
> being fluent in what the notation actually denotes.

---

## 1. The three kinds of `bs=`, and why conflating them causes trouble

`bs=` is one argument, but it names objects from **three different categories**.
Almost every confusion about mgcv notation comes from treating them as one list.

| category | what it is | members | fills which slot |
|---|---|---|---|
| **Marginal smoothers** | An actual smoother of a **continuous** covariate. Interchangeable with one another. | `tp` (**default**), `cr`, `cs`, `ps`, `cp`, `cc`, `bs`, `ds`, `gp` | the smoother slot itself |
| **Ridge / random effects** | No smoothing at all. A quadratic penalty over a set of columns. | `re` | its own term |
| **Constructions over a margin** | Take one or more marginal bases and build something structured from them | `te`, `ti`, `t2`, `fs`, `sz` | *consume* a marginal basis |

The third row is the one that matters. A construction **does not replace** a
marginal basis, it **consumes** one — named via `xt`:

```r
s(FaceSize, AttdAge, bs = "sz", k = 13, xt = list(bs = "cr"))
#                    ^^^^^^^^^                    ^^^^^^^^^
#                    the construction             the margin it is built from
```

So *"should we do `sz` or `cr`?"* is not a well-formed question — `sz` is built
**on top of** `cr` (or `tp`, or `ps`; measured, all accepted). Marginal bases are
strictly more fundamental: every smooth term needs one, and constructions inherit
whatever you give them.

**Corollary for prioritisation:** advance the marginal axis first. `tp` in
particular, because it is the **default** — a bare `s(x)` is a thin-plate
regression spline, verified:

```
bare s(x) gives class: tprs.smooth      formals(mgcv::s)$bs = "tp"
```

(Both readings, and the three accepted `sz` margins above, are asserted in
`scripts/mgcv_penalty_count_probe.R`, §1 block.)

---

## 2. Reading a term

```r
s( AttdAge , by = StudyYear_C , k = 13 , bs = "cr" , m = 2 , xt = list(bs = "cr") )
#  ^^^^^^^   ^^^^^^^^^^^^^^^^   ^^^^^^   ^^^^^^^^   ^^^^^   ^^^^^^^^^^^^^^^^^^^^
#  covariate  scale/split by     basis    basis      penalty  options passed to a
#             a variable         dim      kind       order    construction's margin
```

| argument | meaning | gotcha |
|---|---|---|
| `k` | **basis dimension**, i.e. the *maximum* flexibility. Not the fitted flexibility — that is the EDF, chosen by the penalty. | `k` is an upper bound you set; EDF is what the data buys. Raising `k` past sufficiency costs compute, not fit. |
| `bs` | which basis (see §1) | defaults to `"tp"` |
| `m` | penalty order (and for some bases, basis order) | **changes the null-space dimension**, which changes penalty counts — see §4 |
| `by` | numeric → scale the smooth; factor → **one separate smooth per level** | these two are completely different constructions (§4) |
| `xt` | extra options handed to the *margin* of a construction | this is how `fs`/`sz` pick their marginal basis |
| `sp` | fix the smoothing parameter instead of estimating it | `fx = TRUE` is the harder version: **no penalty at all** |
| `fx` | `TRUE` = unpenalized regression spline | the switch that silently changed everything in §7 |

**The single most important distinction in the whole notation:** a term can be
**penalized** (a smoothing parameter is estimated, EDF < k) or **unpenalized**
(`fx = TRUE`, EDF = k). Two formulas that look identical but differ here are
*different models*, and §7 shows a case where that difference was worth
`3.7e-02` versus `8.9e-16`.

---

## 3. How many smoothing parameters does a term have?

This is the question that tells you how hard a model is to *fit*, because the
outer optimisation searches one dimension per smoothing parameter. **Measured**
(`scripts/mgcv_penalty_count_probe.R`, §3 block):

| term | smoothing parameters | coefficients | rule |
|---|---:|---:|---|
| `s(x, k=6)` | **1** | 5 | one penalty per smooth |
| `te(x, z, k=c(5,5))` | **2** | 24 | **one per margin** (`d` margins → `d`) |
| `ti(x, z, k=c(5,5))` | **2** | 16 | one per margin |
| `t2(x, z, k=c(5,5))` | **3** | 24 | **`2^d - 1`** |
| `te(x, z, w, k=c(4,4,4))` | **3** | 63 | `d` = 3 |
| `t2(x, z, w, k=c(4,4,4))` | **7** | 63 | `2^d - 1` = 7 |
| `s(x) + s(z) + ti(x,z)` | **4** | — | 1 + 1 + 2 |

**`t2` scales exponentially in the number of margins** — 7 smoothing parameters
for three covariates against `te`'s 3, for the same 63 coefficients. That is a
real cost in the outer search, and the reason to prefer `te`/`ti` unless you
specifically need `t2`'s strictly-nested penalty structure (which is what makes
it usable from `gamm`/`lme4`).

### `te` vs `ti` vs `t2`

All three build a surface from marginal bases. They differ in **what they
include** and **how they penalise**:

- **`te(x, z)`** — the full tensor product: main effects *and* interaction
  together, in one term.
- **`ti(x, z)`** — the interaction **only**: each margin is constrained to
  exclude its own main effect, so `ti` is meant to sit *beside* `s(x) + s(z)`.
- **`t2(x, z)`** — the full surface again, but decomposed so the penalties are
  strictly nested; the form you need if the fit has to go through a mixed-model
  engine.

**`te(x,z)` and `s(x) + s(z) + ti(x,z)` span the same space but are NOT the same
fit.** They differ in penalty structure — 2 smoothing parameters against 4 — and
the difference is real: measured at `3.72e-02` on `eta` where this project's
acceptance bound is `2e-2`. Same span, different penalty, different maximiser.
**Unpenalized (`fx=TRUE`) they coincide exactly** (`8.9e-16`), which proves the
difference is entirely the penalty. See §7.

---

## 4. The four ways to make something vary by a group

This is the heart of HGAMs, and the four idioms are genuinely different models —
not stylistic variants.

| idiom | what it says | smoothing parameters | coefficients |
|---|---|---|---|
| `s(f, bs="re")` | each level gets a **scalar** offset, drawn from one common distribution | **1**, always | one per level |
| `s(x, f, bs="fs")` | each level gets its **own curve**, all shrunk toward a common shape | **`1 + M`**, independent of level count | `k` × levels |
| `s(f, x, bs="sz")` | each level gets a **sum-to-zero deviation** from a main effect | **one per level** | grows with levels |
| `s(x, by=f)` | each level gets a **completely separate, independent** smooth | **one per level** (as separate *terms*) | `k` × levels |

Measured, for a `cr` margin at `k=10`
(`scripts/mgcv_penalty_count_probe.R`, §4 block):

```
levels=2   fs: n_pen=3 ncoef=20  |  sz: n_pen=2 ncoef=10  |  re: n_pen=1 ncoef=2
levels=4   fs: n_pen=3 ncoef=40  |  sz: n_pen=4 ncoef=30  |  re: n_pen=1 ncoef=4
levels=6   fs: n_pen=3 ncoef=60  |  sz: n_pen=6 ncoef=50  |  re: n_pen=1 ncoef=6
```

**`fs` holds at 3 penalties while `sz` grows one per level.** For a model with
several grouping factors that is the difference between a tractable outer search
and an intractable one.

And `by=` with a factor is not a term *parameter* — it is a term **multiplier**:

```
s(x, by=f), f 3-level   ->  smooths=3  [s(x):f1, s(x):f2, s(x):f3]  total_sp=3
s(x, by=z), z numeric   ->  smooths=1  [s(x):z]                     total_sp=1
```

### Where `fs`'s penalty count comes from — the `1 + M` rule

**`fs` treats the per-level curves as random effects.** For that to be a proper
random effect, the *entire* coefficient vector must be penalized — including the
**null space**, the functions an ordinary smoothing penalty leaves free. A cubic
spline's second-derivative penalty does not penalize a straight line, so in an
ordinary `s(x)` the constant and the slope are unpenalized. `fs` cannot allow
that: an unpenalized per-level intercept would mean no shrinkage at all.

So `mgcv` reparameterises the margin into (range space, null space) and applies:

- **one penalty to the range space** — the shared "wiggliness" of the curves; plus
- **one ridge penalty per null-space dimension** — one variance component for the
  per-level intercepts, another for the per-level slopes, and so on.

Hence **`n_penalties(fs) = 1 + M`**, where `M` is the null-space dimension of the
**unconstrained** margin. Note *unconstrained*: a standalone `s(x)` has the
centering constraint absorbed (which removes the constant, leaving `M = 1`), but
`fs` keeps the full margin because each level needs its own level.

For a `cr` or `tp` margin with the default second-derivative penalty, the null
space is {constant, linear} → `M = 2` → **3 penalties**. That is the answer to
"why three".

**Tested as a prediction, by stepping the margin's penalty order** (a P-spline
with difference-penalty order `m`, whose null space is polynomials of degree
`m−1`, so `M = m`) — `scripts/mgcv_penalty_count_probe.R`, §4b block:

```
fs over ps margin, m=1  ->  predicted M=1, predicted n_pen=2, ACTUAL n_pen=2
fs over ps margin, m=2  ->  predicted M=2, predicted n_pen=3, ACTUAL n_pen=3
fs over ps margin, m=3  ->  predicted M=3, predicted n_pen=4, ACTUAL n_pen=4
```

And the cross-check on a cyclic margin, whose null space is constants only:
`fs` over `cc` gives **2** penalties, not 3. The rule holds.

---

## 5. HGAM structures — the five-model taxonomy

The standard framing (Pedersen, Miller, Ross & Simpson, *"Hierarchical
generalized additive models in ecology"*, PeerJ 2019) sorts hierarchical GAMs by
two questions: **is there a global smooth?** and **do the group-level smooths
share a smoothing parameter?**

| model | global shape? | group deviations? | shared smoothness? | typical formula |
|---|---|---|---|---|
| **G** | yes | none | — | `y ~ s(x)` |
| **GS** | yes | yes | **shared** | `y ~ s(x) + s(x, f, bs="fs")` |
| **GI** | yes | yes | **individual** | `y ~ s(x) + s(x, by=f) + s(f, bs="re")` |
| **S** | no | yes | **shared** | `y ~ s(x, f, bs="fs")` |
| **I** | no | yes | **individual** | `y ~ s(x, by=f) + s(f, bs="re")` |

Reading it practically:

- **Shared smoothness (`fs`)** = all groups are assumed *equally wiggly*. Strong
  pooling of the shape; a thin group borrows its smoothness from the rest. Cheap
  in smoothing parameters (§4).
- **Individual smoothness (`by=`)** = each group chooses its own flexibility. More
  faithful when groups genuinely differ; costs one smoothing parameter per level
  and pools nothing.
- The `s(f, bs="re")` alongside `by=` in GI/I is **not decorative** — `by=`
  smooths are each centered, so without a random intercept the group *levels* are
  unmodelled.

**This is why `re` and `fs` together are the load-bearing pair**: with those two
plus an ordinary smooth you can write G, GS and S, which is most of the taxonomy.

---

## 6. The actuarial reading: this is credibility

For a reinsurance audience the mapping is direct, and it is not a loose analogy:

- **`s(f, bs="re")` is credibility.** Bühlmann–Straub is a random-effects model.
  The penalty is a ridge; the fitted level effects are shrunk toward the grand
  mean by an amount the data chooses. A thin `FaceSize` cell gets pulled toward
  the book; a thick one stands on its own. The smoothing parameter *is* the
  credibility constant.
- **`bs="fs"` is credibility on whole curves.** Instead of shrinking a scalar
  level toward the mean, it shrinks an entire age curve toward the common shape.
  This is what you want when a segment has enough data to suggest a different
  *pattern* but not enough to assert one.
- **`select=TRUE`** adds a null-space penalty to every term, so a term with no
  signal can be shrunk to exactly zero — automatic term selection, which is the
  "credibility of the model form" rather than of its parameters.

Where the analogy breaks: classical credibility gives a closed-form weight from
assumed variance components, while REML estimates them from the data and the
resulting uncertainty is only approximately accounted for. That is exactly what
the unconditional-covariance work (Kass–Steffey, Wood–Pya–Säfken) is about, and
it is a known-defective area in this codebase — see `MGCV_FEATURE_COVERAGE.md`.

---

## 7. Traps this project actually hit

**1. A docstring is not a specification.** `TensorMIModel`'s docstring says it
fits `te(attained_age, calendar_year)`. The code builds
`bs(age) + bs(year) + bs(age):bs(year)` and fits it with an **unpenalized**
`sm.GLM`. The docstring's own sentence glosses `te(...)` as "a tensor-product
B-spline surface" — it was descriptive English, read as a formula. Two weeks of
work followed from that.

**2. State the fitting regime, not just the formula.** The same two forms that
differ by `3.72e-02` when penalized agree to `8.9e-16` when unpenalized. If you
write down a model form without saying whether it is penalized, you have not
specified the model.

**3. `predict(type="link")` silently drops an argument-supplied offset.**

```r
m <- gam(y ~ ..., offset = log_offset)   # offset as an ARGUMENT
predict(m, type = "link")                # does NOT include log_offset
m$linear.predictors                      # DOES
```

Comparing the wrong one against a Python `eta = offset + X %*% coef` produced a
spurious `1.9751` discrepancy against a `2e-2` bound — which was simply
`max(log(exposure * q_base))`. Use `m$linear.predictors`, or put the offset in
the formula as `offset(...)`.

**4. Equal column counts do not prove equal span.** Two 39-column designs can
span different 39-dimensional subspaces. Test it — project each design's columns
onto the other's column space, both ways, and check the residual (measured
`~1e-14` when they genuinely coincide) plus `rank([X1 X2])` against each rank.

**5. `k` is not EDF.** `k` caps flexibility; the penalty decides what is used.
Reporting `k` as though it were the fitted complexity overstates the model.

---

## 8. Quick reference

```r
# --- marginal bases (the smoother slot) ---
s(x)                          # thin-plate (tp) — THE DEFAULT
s(x, bs = "cr", k = 13)       # cubic regression spline, 13 basis functions
s(x, bs = "cc")               # cyclic — ends meet (seasonality)
s(x, bs = "ps", m = c(2, 2))  # P-spline, 2nd-order difference penalty

# --- surfaces ---
te(x, z)                      # full tensor:      d smoothing parameters
ti(x, z)                      # interaction only: d smoothing parameters
t2(x, z)                      # nested decomp:    2^d - 1 smoothing parameters
s(x) + s(z) + ti(x, z)        # the ANOVA decomposition (NOT equal to te)

# --- group structure ---
s(f, bs = "re")               # random intercept   -> 1 sp, always
s(x, f, bs = "fs")            # random smooths     -> 1 + M sp, level-independent
s(f, x, bs = "sz")            # sum-to-zero devs   -> one sp PER LEVEL
s(x, by = f)                  # separate smooths   -> one TERM per level
s(x, by = z)                  # varying coefficient (z numeric) -> 1 sp

# --- fitting ---
gam(..., method = "REML")             # the criterion to use
bam(..., discrete = TRUE)             # fREML + discretisation: different ALGORITHM
gam(..., select = TRUE)               # null-space penalty: terms can shrink to 0
s(x, fx = TRUE)                       # UNPENALIZED — a different model
```

**Counting smoothing parameters** (what the outer search must explore):

```
s()                    1
te()/ti(), d margins   d
t2(), d margins        2^d - 1
re                     1
fs over margin with null dim M     1 + M          (independent of levels)
sz, L levels                       L
by = factor, L levels              L  (as L separate terms)
select = TRUE                      doubles the count (one extra per term)
```

---

## 9. Where polaris-re stands against this

`docs/MGCV_FEATURE_COVERAGE.md` is the live table. Summary as of 2026-09-16:
**`cr`, `cr`+numeric-`by`, `ti` and `sz` are expressible; `tp` (the default),
`re`, `fs`, `te`, `t2` and factor-`by` are not.** Four family/link pairs, no
Gaussian. REML only — no `fREML`, no `bam`, no `discrete=TRUE`, and no
scale-estimated REML (which blocks every free-scale family).

The capability ladder in that file's §4 is ordered by this document's logic:
marginal bases before the constructions that consume them, cheap-and-load-bearing
(`re`, `fs`) before expensive-and-optional (`sz`).
