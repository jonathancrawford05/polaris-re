# Session log — 2026-08-22 — Level 4 closed (ADR-202)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Spec:** `docs/WORK_ORDER_level4_wps2016.md`  **ADR:** ADR-202
**Predecessors:** ADR-190 (the re-scoping), ADR-201 (`dw/drho`, the prerequisite).

## Gap Before

ADR-190, standing since ADR-188: ours inflates **1.11-1.21x** where `mgcv`
inflates **1.49-1.87x**, ratio of `mgcv`'s correction to `J Vrho Jᵀ` non-constant
at 3.2-4.1x. Re-scoped to "implement Wood, Pya & Säfken (2016)'s correction".

Ten-cell suite entering: `1 AGREES 2 AGREES 3 AGREES 4 DISAGREES 5 AGREES`.

## Hypotheses Tried — three unknowns, all measured

The paper's eq. (7) gave the form; three things it does not state had to be found.

**H1 — the `Vrho` regularisation.** The paper says only *"equivalent to placing a
Gaussian prior on rho"*. `mgcv` publishes `m$V.sp`; measured
`m$V.sp == solve(H + 0.1·I)` to **1.78e-15** on two fits, 1-D search returning
`0.1000000000`. **CONFIRMED.** Fixed the wild overshoot (binomial 4.15x → 1.27x).

**H2 — `Vrho` is the whole story.** **REFUTED by measurement**: our own
finite-difference Hessian matches `mgcv`'s `m$outer.info$hess` (eigenvalues
1.5789, ~1.35e-4), and substituting `mgcv`'s own Hessian changed nothing. Also
refuted a Vρ *scale* error on structural grounds — both `V'` and `V''` are linear
in `Vrho`, so their ratio is invariant to any rescaling.

**H3 — the choice of square root matters.** `RᵀR = Vβ` does not determine
`∂R/∂ρ`. Measured: symmetric root vs Cholesky moves `V''` ~17%. The 2016 paper
reuses Wood (2011) §3.3, where `Vβ = PPᵀ` with `P = R⁻¹` — so the factor is
`G = L⁻¹`, **lower** triangular. **CONFIRMED**: poisson 26.7% → **1.87%**.

**H4 — the remaining binomial residual.** Found by localisation, not search. The
residual was **rank-1** (rel. singular values 1.000, 0.084, 0.0006), dominant
direction `|cos| = 0.9994` with `J[1]`, best multiple of `J₁J₁ᵀ` = **3210** against
an unregularised `H⁻¹[1,1]` of **3184** — a ~1% match naming term and treatment
together. **CONFIRMED**: the two terms use *different* inverses — `V'` the
unregularised, `V''` the ridged. binomial 31.8% → **0.023%**.

## Gap After

| case | element-wise | ours | mgcv | rel |
|---|---:|---:|---:|---:|
| `poisson-log` | 0.904% | 1.1319x | 1.1317x | 0.015% |
| `binomial-logit` | 0.023% | 1.3650x | 1.3650x | 0.000% |
| `binomial-cloglog` | 0.150% | 1.2310x | 1.2312x | 0.022% |

**Validated on five HELD-OUT cases** (different seeds/`n`/`p`, incl. non-canonical
`cloglog`) that played no part in deriving the rule — worst residual 0.730%. Two
cases can fit a rule; five independent ones testing it is what makes it an
identification.

Ten-cell suite unchanged — level 4 still `DISAGREES`, correctly (shipped path).

## Oracle Version

Tier 1: R 4.3.3 / mgcv 1.9.1. **Tier 3: R 4.6.1 / mgcv 1.9.4**, oracle
`sha256:0d54c192…` build 8, run
[32589501512](https://github.com/jonathancrawford05/polaris-re/actions/runs/32589501512),
re-verified after the workflow fix by
[32589815895](https://github.com/jonathancrawford05/polaris-re/actions/runs/32589815895).
Identical to tier 1 at every printed digit.

## Provenance

| comparison | left | right | provenance |
|---|---|---|---|
| `unconditional_correction` (element-wise) | `gam_uncertainty.unconditional_covariance` | `mgcv vcov(unconditional=TRUE) - vcov()` | **INDEPENDENT** |
| `inflation_ratio` | ours throughout | `mgcv` Vc/Vp | **INDEPENDENT** |
| `V_beta` vs `vcov()`, `J`, rho Hessian | ours | `mgcv` | INDEPENDENT controls — 1.7e-14, 0.000%, eigenvalues match |
| the rho Hessian as an *input* | — | `mgcv outer.info$hess` | shared INPUT, not an answer: our own FD Hessian reproduces it |

## Two things I got wrong and corrected

**The scalar metric was flattering.** Mid-slice the inflation ratio read 0.39%
while the element-wise residual was 26.7% — averaging diagonals hid a real
structural disagreement. The probe now exports full `Vc`/`Vp` and the comparator
gates element-wise. **Recorded as an epic-wide lesson**: any remaining comparison
gating on a scalar summary has the same exposure.

**A workflow bug I introduced.** A string replace matched inside the `docker run`
command as well as the artifact list, leaving a stray line that exited 127 in the
Wood-derivatives step, plus a duplicate artifact entry. CI stayed green because
the step is `continue-on-error` — precisely the masking hazard PR #206's review
flagged. Caught while reading tier-3 logs, fixed, and re-verified: that step now
prints one line and no job reports a non-zero exit.

## Quality gate

`ruff format`/`check` clean · `mypy` clean on both new modules · 15 R-free tests
in the **gating** job (incl. one pinning the two-inverse asymmetry, since making
both terms use the same inverse silently regresses ~30% on one family) ·
`tests/test_analytics/` 1465 passed, 1 pre-existing data-file failure · ten-cell
conformance unchanged.

## What remains — and it is not the formula

1. **Re-point production** at `gam_uncertainty` — Anchor 7 sign-off, plus its own
   determinism answer (ADR-186 chose the grid for reproducibility by construction).
2. **Re-run ADR-188's coverage gate.** ADR-190 decision 4 registered, in advance,
   that a larger correction should move coverage toward the 0.9192 floor. That
   prediction is now testable and **has not been run.** It is the natural next
   measurement and it can still refute decision 1.
3. **Labelling any interval a 95% band** — maintainer-reserved regardless.
