# Continuation: a penalized tensor MI surface (P-splines, REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` (2026-08-08c), promoted from the
spline-diagnostics epic.
**Plan:** `docs/PLAN_penalized_mi_surface.md`
**Predecessors:** ADR-182, **ADR-184 + amendments 1-3**
**Status:** **SLICES 1-2 DONE (2026-08-08)** — ADR-185, ADR-186. Slice 3 is NEXT.
**Total slices:** 5 (1-4 autonomous, 5 one maintainer run)
**Estimated scope:** ~4-6 dev-days autonomous + one maintainer run

## Overall goal

Make model complexity data-driven instead of a hand choice. `df` currently sets
basis dimension *and* wiggliness with one integer, and two hand adjustments
(`year_df` 4→3, then `df==degree` 3→2) each moved a published ILEC finding with
nothing in the fit selecting them.

**Not the goal: fixing age 45.** ADR-184 amendment 2 showed that climb survives
removing a whole polynomial order. PLAN §1 rules the framing out in writing.

## Slices

1. ~~**Penalized fitter core at fixed λ**~~ **DONE** — `experience_gam_penalized.py`,
   15 tests, ADR-185. Both limits verified. **Two plan premises were falsified**,
   and slice 2 must start from the corrected ones (see below).
2. ~~**REML λ selection**~~ **DONE** — ADR-186. Deterministic grid, so Anchor 3 is
   resolved by construction. Anchor 4's EDF fix landed with it.
   Slice 1 sharpened that risk rather than reducing it: the penalised directions are
   exactly where the numerical noise lives, which is why the coefficient convergence
   criterion failed there.
3. **Bayesian bands** — **NEXT** — `Vb = (XᵀWX + S)⁻¹φ` through the *unchanged*
   extractor (Anchor 2), plus the first coverage test this project has run on either
   estimator. Note slice 2's lesson before writing its fixtures: a graded ladder must
   be **representable in the basis**, or the test measures the basis instead.
4. **Harness integration** — `--penalized` off by default (Anchor 6), `edf` and λ
   reported (Anchor 4).
5. **Real data** — against the four predictions PLAN §6 registers in advance.

## Context for the next session

- **Read PLAN §2 (the six anchors) and §6 (the predictions) before writing code.**
  §6 exists because the diagnostics epic's pre-registered table came back against
  its own hypothesis and was trustworthy for exactly that reason.
- **Anchor 1 is AMENDED — do not start from the version in PLAN §2.** λ=0
  reproduces `TensorMIModel` exactly only in the **`knots="clamped"`** scheme, which
  is oracle-testing only. The production scheme is `knots="uniform"`, where it
  deliberately does not hold, because **patsy cannot build a P-spline basis at
  all**: it always clamps boundary knots, and a difference penalty over a clamped
  basis does not annihilate linear trends (step spread 5.6e-01 against 8.9e-16 on an
  extended uniform sequence from scipy). Slice 1 found this the hard way — the
  λ→∞ limit kept a 3.0-point span instead of collapsing to constant MI.
- **IRLS converges on deviance, not on coefficients.** At a saturating λ the
  coefficients rattle at round-off in the penalised directions indefinitely while
  the deviance settles within 8 iterations. This matters for slice 2 because the
  optimiser will sit on top of exactly those directions.
- **The EDF reporting changes in slice 2 — do not build on slice 1's fields.**
  Slice 1's `edf_age` / `edf_year` are `tr(H) - tr(H|λⱼ=∞)`, which is well-defined
  (the first implementation was inert, and eleven tests passed over it because all
  asserted on `edf_total`) but **non-additive**: the two overlap and do not sum to
  `edf_total`, while their names invite exactly that addition. Per the amended
  Anchor 4, slice 2 replaces them with **`tr(F)` over the tensor block** as the
  headline per-term EDF — the quantity `mgcv` reports, and one that *closes*
  against the factor block — plus per-penalty **shrinkages**, renamed to say
  *dimensions removed* rather than implying *spent*.
  **The `mgcv`-consistency claim is adopted, not verified** (PLAN §7); nothing in
  this container can check it.
- **`fit_reml()` is the entry point, not `select_lambdas_reml()`.** Added in the
  #188 review round. Selection returns a bare `(λ_age, λ_year, score)` tuple and
  fitting is a separate call, so a caller that wires the two by hand gets a fit with
  `reml_score` and `lambda_grid_step` left `None` — which was the shipped defect.
  `fit_reml()` does both and populates them, and it is the fit slice 3 should take
  `Vb` from. Use `select_lambdas_reml()` only when the search is wanted without the
  fit.
- **The oracle already exists.** `TensorMIModel` at λ=0 is the correctness spec and
  it is already tested. Do not build a new one.
- **statsmodels cannot supply the tensor.** `GLMGam` + `BSplines` penalize but the
  smooths are additive-only (verified on 0.14.6). The Kronecker design and penalty
  are hand-built; the family and link can still come from statsmodels.
- **`k` is an upper bound, not a knob** (Anchor 5). ILEC's eight calendar years
  cannot support `k=10`; HMD's thirty years support 10-15.
- **A slice-5 run that contradicts the thesis is a successful run.**

## Open questions (for human)

- Single global λ per margin, or does slice 5 promote the adaptive-penalty epic?
- Does the `mgcv` cross-check (ADR-151) happen? It needs R and an R-equipped
  machine, and real-data penalized fitting is when it is worth most.
- Should the penalized path ever become the default? Not decidable before slice 5;
  flipping it means re-deriving every committed report, which carries its own
  `DATA_LICENSING.md` §5c implications.
