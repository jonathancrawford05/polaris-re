# Continuation: a penalized tensor MI surface (P-splines, REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` (2026-08-08c), promoted from the
spline-diagnostics epic.
**Plan:** `docs/PLAN_penalized_mi_surface.md`
**Predecessors:** ADR-182, **ADR-184 + amendments 1-3**
**Status:** **NOT STARTED** — scoped 2026-08-08, to begin on a fresh branch after
PR #186 merges.
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

1. **Penalized fitter core at fixed λ** — Kronecker design and difference
   penalties, penalized IRLS. Anchor 1: λ=0 must reproduce `TensorMIModel` exactly.
2. **REML λ selection** — and the determinism it threatens (Anchor 3).
3. **Bayesian bands** — `Vb = (XᵀWX + S)⁻¹φ` through the *unchanged* extractor
   (Anchor 2), plus the first coverage test this project has run on either
   estimator.
4. **Harness integration** — `--penalized` off by default (Anchor 6), `edf` and λ
   reported (Anchor 4).
5. **Real data** — against the four predictions PLAN §6 registers in advance.

## Context for the next session

- **Read PLAN §2 (the six anchors) and §6 (the predictions) before writing code.**
  §6 exists because the diagnostics epic's pre-registered table came back against
  its own hypothesis and was trustworthy for exactly that reason.
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
