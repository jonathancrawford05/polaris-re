# Work order — `dβ̂/dρ` and `dw/dρ` from Wood (2011)

**Source paper:** Wood, S.N. (2011), "Fast stable restricted maximum likelihood and
marginal likelihood estimation of semiparametric generalized linear models",
*JRSS-B* **73**(1), 3–36. DOI `10.1111/j.1467-9868.2010.00749.x`. Supplied by the
maintainer 2026-08-22.
**Epic:** `docs/PLAN_mgcv_parity_engine.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Predecessors:** ADR-190 (the level-4 re-scoping), ADR-196 (the same paper's §2 eq. 4).

---

## 0. Read this first: which paper this is, and what it does and does not unlock

The maintainer supplied this paper to unblock **level 4** — the Kass-Steffey /
`vcov(unconditional = TRUE)` under-inflation that has been the epic's standing
BLOCKER since ADR-188/190.

**This is Wood (2011), not Wood, Pya & Säfken (2016).** ADR-190 decision 1 names the
2016 paper as the one `mgcv` implements for `vcov(unconditional = TRUE)`. This is the
2011 REML paper — the same one that already resolved ADR-196 (the missing penalized
deviance term, §2 eq. 4).

**That does not make it the wrong paper to have.** ADR-190 decision 2 states the
blocker precisely:

> "It is no longer 'find the bug in our arithmetic' … but 'implement Wood (2016)'s
> correction'. That is a slice, not a fix: **it needs `dw/drho`, which nothing in the
> fitter currently computes.**"

**Wood (2011) derives `dw/dρ` in full.** Verified by reading, before this work order
was written:

| ingredient | where | form |
|---|---|---|
| `dβ̂/dρⱼ` | §3.4 | `−e^ρⱼ PPᵀ Sⱼ β̂`, and `(XᵀWX + S)⁻¹ = PPᵀ` (§3.3) |
| `dηᵢ/dρⱼ` | §3.4 | `X dβ̂/dρⱼ` |
| `dwᵢ/dηᵢ` | Appendix D | `(wᵢ/gᵢ′)(αᵢ′/αᵢ − Vᵢ′/Vᵢ − 2gᵢ″/gᵢ′)` |
| `dwᵢ/dρⱼ` | Appendix D, closing line | chain rule of the two above |
| `∂w/∂ρ` used in anger | §3.5.1 | `Tⱼ = diag((1/|wᵢ|) ∂wᵢ/∂ρⱼ)` |

**What it does NOT contain: the assembly.** Searched: the paper has **zero**
occurrences of "unconditional", "Vc", or smoothing-parameter-uncertainty covariance.
It derives `dw/dρ` because the *REML Newton iteration* needs it, not because it is
building a covariance correction. How `dw/dρ` enters `Vc` is the 2016 paper's own
contribution.

**Therefore this slice is the prerequisite, not the fix.** It builds and verifies the
ingredient ADR-190 named as missing. It does **not** close level 4, and nothing in it
may be reported as closing level 4. Closing level 4 still needs Wood, Pya & Säfken
(2016) for the assembly formula — and, per ADR-190 decision 3, that assembly must be
re-derived from that paper rather than read off `mgcv`'s GPL source.

Building this now is worth doing anyway, on its own merits: it is on level 4's
critical path by ADR-190's own statement of the blocker, it is independently
verifiable against `mgcv` today, and it is a real parity result whether or not the
2016 paper ever arrives.

---

## 1. The claim sentence, written before the code (ADR-193, provenance gate)

> `polaris_re.analytics.gam_derivatives` computes `dη/dρ` and `dw/dρ` analytically
> from Wood (2011) §3.4 and Appendix D, given a converged penalized fit and the
> shared `(X, {Sⱼ})`; `mgcv` computes the same quantities by **its own refits at
> perturbed smoothing parameters**, central-differenced; compared on `dη/dρ` (per
> penalty block, on the linear-predictor scale) and `dw/dρ`.

**Mechanical test applied to the signature, before the body.** The producing function
is `d_eta_d_rho(x, penalties, irls_weights, coef, log_lambda)` — plain arrays and the
shared spec. It takes no R payload and no mgcv output of any kind. The right-hand
operand is produced by `scripts/gam_deriv_probe.R` refitting `mgcv` at `ρ ± h` and
differencing **its own** `η`. Neither side reads the other. **INDEPENDENT**, and it
can genuinely disagree.

**Provenance, per compared quantity:**

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `d_eta_d_rho` | `gam_derivatives.d_eta_d_rho` (Wood §3.4, analytic) | central difference of `mgcv`'s own `predict(type="link")` at `ρ ± h` | **INDEPENDENT** |
| `dw_drho` | `gam_derivatives.dw_drho` (Wood App. D, analytic) | central difference of `mgcv`'s own `m$weights` at `ρ ± h` | **INDEPENDENT** |
| `eta` at base `ρ` | `gam_fit.penalized_irls_general` | `mgcv predict(type="link")` | INDEPENDENT (already-verified control, ADR-195) |

### Why `dη/dρ` and not `dβ̂/dρ`

PLAN **Anchor 2**, and the routine's own NEVER list: *"NEVER use coefficient
agreement as an acceptance criterion outside Stage A. `mgcv` reparameterises; `β` is
basis-dependent and `η` is not."* `dβ̂/dρ` is a coefficient-space quantity and would
be exactly that mistake. `dη/dρ = X dβ̂/dρ` is the basis-invariant image of it and is
what any downstream use (including the 2016 correction) actually needs. `dβ̂/dρ` is
computed internally and is *not* a compared quantity.

---

## 2. What is being built

New module `src/polaris_re/analytics/gam_derivatives.py`, additive — nothing existing
is modified (PLAN Anchor 7):

1. **`d_beta_d_rho`** — Wood §3.4. `dβ̂/dρⱼ = −λⱼ (XᵀWX + S)⁻¹ Sⱼ β̂`. The paper's
   `PPᵀ` factorisation is *numerical-stability machinery* for the ill-conditioned
   case, not additional mathematical content (§3.3: "`(XᵀWX + S)⁻¹ = PPᵀ`"); a direct
   solve is mathematically identical and is what this well-conditioned fixture needs.
   Recorded here so a later reader does not mistake the simplification for a
   deviation from the paper.
2. **`d_eta_d_rho`** — `X @ d_beta_d_rho`, the compared quantity.
3. **`d2mu_deta2` / `variance_deriv`** — the per-link/per-family analytic pieces
   Appendix D's `dw/dη` needs, which `gam_family.Link`/`Family` do not currently
   expose (they carry `linkinv`, `mu_eta`, `variance` only). Added here rather than
   onto those classes so the verified `gam_family` module is untouched.
4. **`dw_deta`** — Appendix D, at `α ≡ 1` (see §3 below).
5. **`dw_drho`** — the chain rule `dwᵢ/dρⱼ = (dwᵢ/dηᵢ)(dηᵢ/dρⱼ)`.

---

## 3. The Fisher/Newton subtlety, and the prediction it generates

Wood's `dβ̂/dρ` is derived by implicit differentiation of the penalized-deviance
stationarity condition (Appendix C), and the inverse appearing in it is
`[∂²Dp/∂β∂βᵀ]⁻¹ = PPᵀ/2` — the **Newton** Hessian, which is why the paper's `wᵢ`
carry the `αᵢ` factor.

**`gam_fit.penalized_irls_general` uses Fisher weights** — verified by reading:
`irls_weights = weights * deta_dmu**2 / variance(mu)`, with no `α` term. The paper
states the consequence directly: *"If a canonical link function is used then `αᵢ = 1
∀ i` and Newton's method and Fisher scoring coincide."*

So, **registered before measuring** (PLAN §6 discipline):

| cell | link | prediction |
|---|---|---|
| `poisson-log` | canonical | `dη/dρ` agrees to finite-difference truncation error (~1e-7 or better at `h=1e-4`) |
| `binomial-logit` | canonical | same |
| `binomial-cloglog` | **non-canonical** | **may disagree materially** — our Fisher `XᵀWX` is the *expected* Hessian where Wood's formula wants the observed one |

**If cloglog disagrees, that is a real result, not a bug**: it localises a known,
documented difference between our fitter and `mgcv`'s to a specific quantity, and it
tells a future level-4 slice that the correction needs Newton weights. **If it
agrees**, the expected/observed Hessian distinction does not bite at this fixture's
conditioning, which is also worth knowing and would be recorded as such.

Either outcome is a successful slice (Anchor 9).

---

## 4. Verification design

**Tier 1 to iterate, tier 3 to commit any number** (routine SETUP step 2).

**Step order matters — cheap internal checks before spending an R round trip:**

1. **Closed-form / internal, no R.** `d2mu_deta2` and `variance_deriv` are each
   checked against high-accuracy central differences of the *already-verified*
   `link.mu_eta` / `family.variance`. This is an internal consistency check, **not**
   parity evidence, and must be labelled so — it shares a producer.
2. **A zero-penalty control.** At `S = 0`, `dβ̂/dρ` is identically zero (the formula
   carries `Sⱼβ̂`). Cheap, exact, and catches a sign or scaling slip before R runs.
3. **The parity comparison.** `scripts/gam_deriv_probe.R` fits `mgcv` at a base `sp`
   and at `sp` perturbed one block at a time, exports `η` and `m$weights` at each,
   and the Python comparator central-differences the R side and compares against its
   own analytic value.

**The step size is a derived quantity, not a tuned one (Anchor 8).** Central
differences carry truncation `O(h²)` and round-off `O(ε/h)`; the balance is
`h ≈ ε^(1/3) ≈ 6e-6` in `ρ`. `h = 1e-4` is used, comfortably above the round-off
floor and giving truncation `~1e-8` — and the *tolerance* is therefore set by the
finite-difference error of the reference side, not by what makes the check pass. A
convergence check (halving `h` and confirming the residual falls ~4×) is the evidence
that the difference is truncation-limited rather than a real disagreement.

---

## 5. Acceptance criteria

Named with their provenance so a harness result cannot tick them (ADR-193 §3.5):

- [ ] **INDEPENDENT** comparison of `d_eta_d_rho` against `mgcv`'s own
      finite-differenced `η`, for both canonical-link cells, agreeing to the
      finite-difference floor established by the `h`-halving convergence check.
- [ ] **INDEPENDENT** comparison of `dw_drho` against `mgcv`'s own
      finite-differenced `m$weights`, same cells, same standard.
- [ ] The `binomial-cloglog` cell **measured and reported either way**, against the
      §3 prediction, with the Fisher/Newton reading recorded.
- [ ] The `S = 0` control returns exactly zero.
- [ ] Confirmed at **tier 3** on the pinned digest before any number enters
      `DECISIONS.md`.
- [ ] Required conformance levels 1-3 still agree — no regression.

**Explicitly NOT claimed by this slice**, and any report saying otherwise is wrong:

- Level 4 is **not** closed, or advanced past "its named prerequisite now exists".
- `Vc` / the unconditional covariance correction is **not** implemented — that needs
  Wood, Pya & Säfken (2016) §? for the assembly, which this paper does not contain.
- Nothing in `smoothing_uncertainty` or any production path is modified (Anchor 7).
