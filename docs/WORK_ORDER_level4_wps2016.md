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

## 4. Why this is NOT being called closed

**Dropping the flat direction is one reading of "regularize", not a derived rule.**
It nearly closes `poisson-log` and leaves `binomial-logit` at 1.2741x against
1.3650x — still ~7% out. Choosing a threshold that closes both would be **tuning a
constant until it matches `mgcv`**, which this routine forbids outright and which
would make the resulting agreement measure nothing.

So the honest state is: the formula is right and implemented, the ingredients are
verified against `mgcv` individually (`Vb` to 1e-14, `Vρ` against `mgcv`'s own
Hessian, `dw/dρ` to ~5e-11 in ADR-201), and **what remains is one specific,
answerable question** rather than an open-ended gap.

## 5. The named next step

**Determine `mgcv`'s actual regularisation of `Vρ` before it enters `Vc`, from the
2016 paper's online supplementary material (SA D is cited for the `O(Mp³)`
computation) — or by measurement, not by fitting a threshold.**

A clean localising experiment exists and is cheap: `mgcv` exposes
`m$outer.info$hess`, so a probe can compute `Vc − Vb − J Vρ Jᵀ` from `mgcv`'s own
quantities and compare it against our `V''` **element-wise** at a known `Vρ`
treatment. That separates "our `V''` formula is wrong" from "our `Vρ` regularisation
differs" definitively, in the same way ADR-190's own decisive probe separated its
three suspects. This session did not run it.

**Do not**, on the next pass: pick a threshold because it makes both cells agree;
report any number here as closing level 4; or re-point
`experience_gam_penalized.smoothing_uncertainty` at this module. Labelling any
resulting interval a 95% band remains maintainer-reserved (ADR-188).
