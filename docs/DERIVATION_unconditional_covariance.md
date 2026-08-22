# Derivation: the unconditional covariance of a penalized GAM

**Status:** the **delta-method term is derived and verified**. It is **not** what
`mgcv::vcov(unconditional = TRUE)` returns — it reproduces roughly **28–32%** of `mgcv`'s
correction, and §5 shows by a **rank argument** that no `J V_rho J'` of any kind can
reproduce it. The remaining term is not yet derived.

**Sources.** Simon N. Wood, *Generalized Additive Models: An Introduction with R*
(2nd ed., 2017) §6.10, and Wood, Pya & Säfken (2016), *JASA* 111:1548. Supplied by the
maintainer 2026-08-15 in response to `PRODUCT_DIRECTION`'s "Supply the Wood derivation"
item. **No text or code was taken from `mgcv` itself** — it is GPL (>= 2) and this project
is MIT (ADR-190 decision 3). The mathematics below is a rewriting from the published
sources; the `mgcv` attribute names in §4 are public API surface, used to say where a
quantity can be read, not how it is computed.

---

## 1. Why the conditional covariance is not enough

The Bayesian posterior covariance of the coefficients is computed **given** the smoothing
parameters:

    V_beta = (X' W X + S)^-1,    S = sum_j lambda_j S_j

with `X` the model matrix, `W` the IRLS weight matrix, and `S_j` the individual penalties.
Because it conditions on `lambda`, it ignores the fact that `lambda` was itself estimated,
and so **understates the true variance**. ADR-187 finding 2 measured that the selected
`lambda` is one draw from a wide distribution, and ADR-188 measured the consequence:
**87.1% coverage against a nominal 95%** on a truth the basis represents exactly.

## 2. The delta-method correction

Work in log smoothing parameters, `rho_j = log(lambda_j)`.

### 2.1 The score equation

At convergence the penalized IRLS estimate satisfies

    (X' W X + S) beta_hat = X' W z

with `z` the pseudodata. Write `H = X' W X + S`, so `H^-1 = V_beta`.

### 2.2 The Jacobian

Differentiate the score equation implicitly with respect to one `rho_j`. **Treating `W` and
`z` as not depending on `rho`** — Wood's standard approximation, and §5 below is about
exactly this assumption — the right-hand side contributes nothing:

    (dH/drho_j) beta_hat + H (dbeta_hat/drho_j) = 0

Since `dS/drho_j = e^{rho_j} S_j = lambda_j S_j`, only the penalty survives in `dH/drho_j`:

    (lambda_j S_j) beta_hat + H (dbeta_hat/drho_j) = 0

so the `j`-th column of the Jacobian is

    J[, j] = dbeta_hat/drho_j = -H^-1 (lambda_j S_j beta_hat)
                              = -V_beta (lambda_j S_j beta_hat)

**This is exact, closed-form, and needs no extra model fits** — only `V_beta`, `lambda_j`,
`S_j` and `beta_hat`, all of which a converged fit already has.

### 2.3 The smoothing-parameter covariance

`V_rho` is the covariance of `rho_hat`, obtained from the inverse Hessian of the REML (or
ML) score at convergence.

### 2.4 The correction

    V_beta_unconditional = V_beta + J V_rho J'

---

## 3. What this project measured, and it matters before anyone implements it

**The derivation above is confirmed exactly**, and it is **insufficient**. Both halves were
measured on the pinned oracle via `scripts/ks_formula_probe.R`.

**Confirmed — §2.2 is precisely what `mgcv` computes.** `mgcv`'s own `db.drho` matches the
closed form `-V_beta (lambda_j S_j beta_hat)` to **1.5e-15 / 5.8e-15 / 2.3e-14** across the
three free-`sp` conformance cells. There is no ambiguity about the Jacobian.

**Confirmed — `V_rho` is the inverse outer Hessian.** `sp.vcov()` and
`solve(outer.info$hess)` agree to within 0.5–7% element-wise, i.e. they are the same object
up to the optimiser's own bookkeeping.

**Insufficient — with every input exact, the term is still ~3.1–4.0x too small.** Measured
at **tier 3**: oracle `sha256:0d54c192…` (build 8, R 4.6.1 / mgcv 1.9.4), CI run
**31914818812**; identical to tier 1 (mgcv 1.9.1) at every digit printed.

| cell | `mean diag(Vc - Vp)` | `J V_rho J'` (mgcv's own `db.drho` and `sp.vcov`) | ratio |
|---|---:|---:|---:|
| `l2-free-sp` | 1.99864e-04 | 5.03937e-05 | **3.9661** |
| `l2-free-sp-factors` | 7.70782e-05 | 2.49805e-05 | **3.0855** |
| `l2-free-sp-kb` | 3.29745e-04 | 9.37175e-05 | **3.5185** |

Nothing here is approximated: `mgcv`'s Jacobian, `mgcv`'s `V_rho`, `mgcv`'s `lambda`,
compared against `mgcv`'s own `Vc - Vp`. **The delta-method term accounts for about 28–32%
of what `vcov(unconditional = TRUE)` returns.** The ratio is not constant across cells, so
it is not a scalar anyone mis-transcribed.

This is the same conclusion ADR-190 reached from a weaker starting point — there, the
Jacobian was a central difference and `V_rho` was `solve(hess)`. **Replacing both with
`mgcv`'s exact values moves the ratio from 4.07 / 3.16 / 3.55 to 3.97 / 3.09 / 3.52**, i.e.
by about 2%. The gap is structural.

## 4. Where each quantity lives in a fitted `gam` object

| symbol | attribute | note |
|---|---|---|
| `V_beta` | `fit$Vp` | conditional on `sp` |
| `V_beta_unconditional` | `fit$Vc` | what `vcov(fit, unconditional = TRUE)` returns |
| `V_rho` | `sp.vcov(fit)` | prefer the accessor; `outer.info$cov` is **not populated** on the fits this project uses, while `outer.info$hess` is |
| `J` | `fit$db.drho` | the exact `dbeta_hat/drho`; **verified equal to §2.2's closed form** |
| `rho` | `log(fit$sp)` | natural log |

`Vc` and the smoothing-parameter covariance exist only when `sp` was **estimated** — REML
or ML. On a fixed-`sp` fit they are absent, which is why level 4 of the conformance suite is
measured at independently selected `lambda` (ADR-189).

## 5. What is still missing — and a rank argument that bounds the search

**`Vc - Vp` is FULL RANK. `J V_rho J'` cannot be.** `J` has one column per smoothing
parameter — two here — so `J V_rho J'` has rank at most **2**, for *any* `V_rho`
whatsoever. Measured on the three cells, the numerical rank of `Vc - Vp` is
**42 / 42 / 50**.

    cell                  rank(Vc - Vp)   columns of J   best-possible 2x2 V_rho:
                                                          relative residual
    l2-free-sp                 42              2               0.6772
    l2-free-sp-factors         42              2               0.4533
    l2-free-sp-kb              50              2               0.6532

The last column is the least-squares fit of `Vc - Vp` onto the span of
`{J e_i e_j' J'}` — the **best any `V_rho` could possibly do**. It leaves 45-68% of the
Frobenius norm unexplained.

**This closes off an entire class of proposed fixes, permanently.** No rescaling of
`V_rho`, no swap between `V.sp`, `sp.vcov()` and `solve(outer.info$hess)`, no `lambda_j^2`
Jacobian/parameterisation correction, and no combination of them can reconcile the two
sides, because none of them changes the rank of a rank-2 object. **The correction `mgcv`
applies is not of the form `J V_rho J'`.** Any candidate that keeps that shape is refuted
before it is measured.

Three specific candidates were measured anyway, since they were proposed explicitly:

    variant                          ratio (actual / candidate), 3 cells
    J solve(outer.info$hess) J'      3.9521  3.0825  3.5051
    J sp.vcov(fit) J'                3.9661  3.0855  3.5185
    J V.sp J'                        5.1642  3.6276  4.6205   <- worse

and `Vp + J V.sp J'` differs from `Vc` by **1.24e-03** against a `max|Vc|` of 2.81e-03 —
44% of the matrix scale, not machine precision.

**Two factual corrections worth recording**, because both were offered as the explanation:

* `sp.vcov(fit)` is **not** on the lambda scale. It returns `4.74094` where
  `solve(outer.info$hess)` returns `4.76223`, on a cell with `lambda = 6524`. Were it
  `diag(lambda) V_rho diag(lambda)`, it would be larger by ~10^7.
* The observed 3.1-4.0x is **not** `lambda_j^2` for `lambda_j` near 1.8-2.0. The fitted
  smoothing parameters on these cells range from **226 to 27,052**.

### So what is needed

The **printed expression for `Vc` itself**, from Wood (2016) §3 / the book §6.10, verbatim.
The rank result says it must contain a term outside `J`'s column space — which is where a
bias or mean-shift component would sit, consistent with `Vc` being motivated by
across-the-function rather than pointwise coverage. That is an inference about *shape*, not
a derivation, and this document deliberately stops there.

**Do not implement from `mgcv`'s source** (ADR-190 decision 3). And note the rank test above
is cheap and decisive: any future candidate can be refuted or confirmed in about a minute
using `scripts/ks_formula_probe.R`'s extracted quantities, so **candidates should be
measured before they are written up**, not after.

## 6. What can be built today, and it is worth doing on its own

**Our `smoothing_uncertainty()` computes `J` by central differences** — nine penalized fits,
of which four exist only to difference `beta_hat`. §2.2 gives `J` in closed form from
quantities the converged fit already holds. That change is:

* **exact** rather than second-order accurate — our differenced `J` sits within
  `2.8e-04 – 3.9e-04` (max abs) of `mgcv`'s `db.drho`, small but not zero;
* **cheaper** — it removes four of the nine fits;
* **not a fix.** It moves the correction by ~2% and closes none of the 3.1–4.0x gap.

Worth shipping as its own change with its own measurement, precisely *because* it is not
the fix — landing it inside the eventual Wood implementation would conflate an exactness
improvement with a formula change, and make it impossible to attribute whichever movement
follows.
