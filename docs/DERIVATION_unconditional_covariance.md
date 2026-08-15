# Derivation: the unconditional covariance of a penalized GAM

**Status:** the **delta-method term is derived and verified**. It is **not** what
`mgcv::vcov(unconditional = TRUE)` returns — it is the first-order part of it, and
reproduces roughly **28–32%** of `mgcv`'s correction. The remainder is not yet derived.

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

## 5. What is still missing, and the one place to look

The assumption flagged in §2.2 — that `W` and `z` do not depend on `rho` — is the leading
candidate for the entire remainder, for a reason independent of the arithmetic: **`mgcv`'s
own correction routine takes `dw`, the derivative of the IRLS weights with respect to
`rho`, as an argument.** A routine that needed only §2.4 would not ask for it.

That is a signature, not a derivation, and it is deliberately as far as this document goes.
**Do not implement from `mgcv`'s source** (ADR-190 decision 3). What is needed to finish:
the weight-derivative term written out from Wood (2016) §3 or the book's §6.10, at the same
level of detail as §2 above, at which point this becomes an ordinary implementation slice.

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
