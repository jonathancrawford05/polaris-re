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

## 5. Where it stands — one cell effectively closed, one with a rank-1 residual

All inputs verified against `mgcv` individually, so nothing below is attributable
to an ingredient:

| quantity | ours vs `mgcv` |
|---|---|
| `coef` | 6.4e-15 / 9.4e-15 |
| `J = dbeta/drho` | **0.000%** (2.5e-11 / 5.5e-11 absolute) |
| `V_beta` vs `vcov()` | 1.7e-14 / 4.3e-14 |
| `V_rho` vs `m$V.sp` | 1.78e-15 |

Element-wise against `mgcv`'s own `Vc - Vp`, with the ridge and the Wood factor:

| case | first-order only | + `V''` | inflation ours vs `mgcv` |
|---|---:|---:|---|
| `poisson-log` | 75.3% | **1.87%** | 1.1296x vs 1.1317x |
| `binomial-logit` | 56.7% | **31.8%** | 1.2721x vs 1.3650x |

**`poisson-log` is effectively closed.** `binomial-logit` is not, and its residual
is **essentially rank-1** (singular values 1.000, 0.084, 0.0006 relative) — a
single missing direction, not diffuse error.

## 6. Why this is still NOT called closed, and the named next step

One cell at ~2% and one at ~32% is not parity, and the honest reading is that
something binomial-specific is still missing. **The residual's rank-1 structure is
the handle**: a diffuse residual would suggest an accumulation of small errors,
where rank-1 points at one omitted term.

**Next step, concretely.** Identify the rank-1 direction — project the residual
onto the columns of `X`, onto `J`'s two rows, and onto the eigenvectors of
`V_beta` — and see which it aligns with. That says whether the missing piece is a
`rho`-direction term (suggesting the `M=2` sum is incomplete), a scale-parameter
term (binomial with prior weights is where a dispersion term would differ from
Poisson), or something in the prior-weight handling. The 2016 paper's online
supplementary **SA D** is cited for the `O(Mp^3)` computation of `V''` and is the
place to check for a term the main text compresses.

**Do not**, on the next pass: fit a scalar to close `binomial-logit` (the best
scalar is 1.1767 and leaves 30.8%, so it is not a scale error anyway); re-point
`experience_gam_penalized.smoothing_uncertainty`; or report level 4 as closed.
Labelling any interval a 95% band remains maintainer-reserved (ADR-188).
