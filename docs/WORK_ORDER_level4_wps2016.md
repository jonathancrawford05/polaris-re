# Level 4 — Wood, Pya & Säfken (2016) eq. (7): CHARACTERISED, NOT CLOSED

**Source:** Wood, S.N., Pya, N. & Säfken, B. (2016), "Smoothing Parameter and Model
Selection for General Smooth Models", *JASA* **111**(516), 1548–1563, DOI
`10.1080/01621459.2016.1180986`. Supplied by the maintainer 2026-08-22.
**Predecessors:** ADR-190 (the re-scoping), ADR-201 (`dw/drho`, the prerequisite).
**Status:** **the formula is implemented and the gap is localised to one specific
question. Level 4 is NOT closed.** Read §4 before citing any number here.

---

## 1. The formula, and why it is exactly ADR-190's missing piece

§4 eq. (7):

> `V'_β = V_β + V' + V''`,  where `V' = J Vρ Jᵀ` and
> `V''_jm = Σᵢ Σₗ Σₖ (∂Rᵢⱼ/∂ρₖ) Vρ,ₖₗ (∂Rᵢₘ/∂ρₗ)`

followed, verbatim, by:

> *"Dropping `V''` we have the Kass and Steffey (1989) approximation
> `β|y ∼ N(β̂ρ̂, V*β)` where `V*β = Vβ + J Vρ Jᵀ`."*

**That is ADR-190's finding stated by the authors.** ADR-190 measured that
`Vc ≠ Vb + J Vρ Jᵀ` and that the latter reproduces *our* number; the paper says
that expression is what you get by dropping `V''`. The two agree without either
having been derived from the other, which is about as good as corroboration gets.

`V''` needs `∂R/∂ρ` where `RᵀR = Vβ`, hence `dVβ/dρ`, hence `dw/dρ` — precisely the
ingredient ADR-190 named as missing and ADR-201 built.

## 2. What is implemented and verified

`src/polaris_re/analytics/gam_uncertainty.py`, additive (Anchor 7 — no production
path re-pointed):

| piece | status |
|---|---|
| `V'' = Σₖ Σₗ Vρ,ₖₗ (∂R/∂ρₖ)ᵀ(∂R/∂ρₗ)` | matches the paper's index form; the `i` sum is a column inner product |
| `cholesky_factor_derivative` | derived, not quoted; agrees with a central difference of a real factorisation to **1.8e-10** |
| `d_vbeta_d_rho` | `−Vβ(Xᵀ diag(dw/dρₖ)X + λₖSₖ)Vβ` |
| our `Vb` vs `mgcv`'s `vcov()` | **1.7e-14 / 4.3e-14** — the control holds, exactly |
| our ρ-Hessian vs `mgcv`'s `m$outer.info$hess` | eigenvalues match (1.5789, ~1.35e-4) — **`Vρ` is not the error** |

## 3. The measurement, and the one thing it turns on

Both sides at `mgcv`'s own selected λ, each computing its own `Vb`/`Vρ`/`J`:

| case | Vρ treatment | ours 1st-order | ours FULL | mgcv |
|---|---|---:|---:|---:|
| `poisson-log` | plain inverse | 1.0387x | 1.3563x | **1.1317x** |
| `poisson-log` | **drop flat direction** | 1.0386x | **1.1351x** | **1.1317x** |
| `binomial-logit` | plain inverse | 1.2298x | 4.1517x | **1.3650x** |
| `binomial-logit` | **drop flat direction** | 1.1459x | 1.2741x | **1.3650x** |

Two things follow, and only two:

1. **`V''` is real, large, and in the right direction.** The first-order term alone
   under-inflates against `mgcv` on both cells — reproducing ADR-190's standing
   finding — and adding `V''` moves it up. On `poisson-log` with the flat direction
   dropped it lands at **1.1351x against 1.1317x, a 0.3% miss**.
2. **The treatment of the near-null direction of the ρ Hessian is decisive**, and it
   is not a detail this session settled. `poisson-log` selected `λ₂ ≈ 1.06e+05` —
   effectively infinite — whose Hessian eigenvalue is ~1.35e-4, so a plain inverse
   hands that direction ~7400 of variance and `V''` inherits it. The paper
   anticipates exactly this:

   > *"it is necessary to substitute a Moore-Penrose pseudoinverse of the Hessian if
   > a smoothing parameter is effectively infinite, or otherwise to regularize the
   > inversion (which is equivalent to placing a Gaussian prior on ρ)."*

## 4. Two unknowns identified since — both by measurement, neither tuned

### 4.1 `mgcv` regularises the rho Hessian with a ridge of exactly 0.1

The paper names the mechanism but not the value: *"a Moore-Penrose pseudoinverse
of the Hessian if a smoothing parameter is effectively infinite, or otherwise to
regularize the inversion (which is equivalent to placing a Gaussian prior on rho)."*

`mgcv` publishes the result as **`m$V.sp`**, and

```
m$V.sp == solve(m$outer.info$hess + 0.1 * I)     residual 1.78e-15
```

on both cases, with a 1-D search over the ridge returning `0.1000000000`. So it is
a Gaussian prior on `rho` with variance 10, **read off `mgcv`'s own published
quantity**, not a constant chosen to make a comparison green (Anchor 8). Without
it the saturated direction (`lambda_2 ~ 1.06e+05`, Hessian eigenvalue ~1.35e-4)
carries ~7400 of variance and `V''` overshoots by 3-4x.

### 4.2 `V''` is not invariant to the choice of square root — and the factor is Wood (2011) §3.3's

`R_rho^T R_rho = V_beta` does **not** determine `dR/drho`. Measured: swapping a
plain Cholesky of `V_beta` for the symmetric square root moves `V''` by ~17% and
the element-wise residual from 26.7% to 21.2%. So the factor must be the specific
one `mgcv` builds.

The 2016 paper reuses Wood (2011) §3.3, which forms `A = X^T W X + S_lambda` and
works with `P = R^-1`, `V_beta = P P^T`. The factor with `G^T G = V_beta` is
therefore `G = L^-1` where `A = L L^T` — **lower** triangular, a genuinely
different square root from the upper Cholesky factor of `V_beta`.

**Using it drops `poisson-log`'s element-wise residual from 26.7% to 1.87%.**

## 5. RESOLVED — the two terms use different inverses of the rho Hessian

The binomial residual is explained. **`mgcv` does not use the same `Vrho` in both
terms of eq. (7):**

    V'  (first order)  uses the UNREGULARISED  H^-1
    V'' (second order) uses the RIDGED         (H + 0.1 I)^-1

### How it was found — localisation, not search

With a single ridged `Vrho`, `binomial-logit`'s element-wise residual against
`mgcv`'s own `Vc - Vp` was 31.8%, and that residual was **essentially rank-1**
(relative singular values 1.000, 0.084, 0.0006) — one missing direction, not
accumulated error. Projecting it:

- dominant direction vs `J[1]`: **|cos| = 0.9994**
- best multiple of `J[1] J[1]^T`: **3210**, leaving 12.3%
- unregularised `H^-1[1,1]` for that case: **3184**

A ~1% match between a fitted coefficient and an independently computed quantity
named the term and its treatment together. The four-way combination check then
confirmed it outright: `binomial-logit` went 31.8% -> **0.023%**.

### Validation on five held-out cases

None of these took part in identifying the rule; they vary seed, `n`, `p` and
family, and include a non-canonical link:

| case | family/link | element-wise residual | inflation rel err |
|---|---|---:|---:|
| `v-pois-a` | poisson/log | 0.730% | 0.071% |
| `v-pois-b` | poisson/log | 0.334% | 0.010% |
| `v-binom-a` | binomial/logit | 0.075% | **0.000%** |
| `v-binom-b` | binomial/logit | 0.076% | 0.007% |
| `v-cloglog-a` | binomial/cloglog | 0.219% | 0.002% |

And on the committed 3-case probe, end to end through the shipped function:
`poisson-log` 0.904%, `binomial-logit` 0.023%, `binomial-cloglog` 0.150%.

**ADR-190's blocker was: ours inflates 1.11-1.21x where `mgcv` inflates
1.49-1.87x. We now reproduce `mgcv`'s inflation to <0.1% and its full correction
matrix to <1% element-wise.**

## 6. What is closed, and what is deliberately not

**CLOSED: the level-4 FORMULA gap.** ADR-190 re-scoped level 4 from "find the bug
in our arithmetic" to "implement Wood, Pya & Säfken (2016)'s correction". That is
now done and verified against `mgcv` on eight cases in total.

**NOT closed, and not this slice's to close:**

- **The ten-cell conformance suite's level 4 will still DISAGREE.** It exercises
  `experience_gam_penalized.smoothing_uncertainty`, the shipped path, which this
  does not touch (Anchor 7). That is the correct outcome, not a contradiction.
- **Re-pointing production** at `gam_uncertainty` needs PLAN Anchor 7 sign-off and
  its own answer on determinism (ADR-186 chose the grid deliberately for
  reproducibility by construction).
- ~~**ADR-188's coverage gate.**~~ **RUN 2026-08-23 — ADR-203.** Eq. (7) moves
  coverage **up but not to the floor**: age-flat 0.7815 -> 0.8172, age-varying
  0.8090 -> 0.8359, against 0.9192. Confirmed in direction, refuted in
  sufficiency — the formula was *a* gap, not *the* gap, and a second cause
  remains that no covariance eq. (7) can form will reach. **Coverage does not
  supply the argument for re-pointing production**; ADR-202's parity is a
  separate case. Note the baseline in this bullet's earlier wording (0.8516 /
  0.8581) was **stale** — see ADR-203 finding 0.
- **Labelling any interval a 95% band** remains maintainer-reserved.

## 7. Two caveats worth carrying forward

**The residual is small but not float noise** (0.07–0.73% element-wise). Eq. (7)
comes from a first-order Taylor expansion whose remainder `r` the paper explicitly
drops, so exact agreement is not available in principle. The 2% tolerance is set
from the observed spread, under a factor of three of headroom (Anchor 8).

**Element-wise governs, not the inflation ratio.** The ratio averages diagonals:
mid-slice it read 0.39% while the element-wise residual was 26.7%, hiding a real
structural disagreement behind a green headline. The probe now exports full
`Vc`/`Vp` matrices, and the comparator reports both with the element-wise number
as the gate.
