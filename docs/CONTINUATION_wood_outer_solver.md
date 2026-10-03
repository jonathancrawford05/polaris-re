# Continuation: the Wood-shaped outer solver

**Plan:** `docs/PLAN_wood_outer_solver.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-03, by the epic-start session (ADR-241).
**Status:** **IN PROGRESS — ACTIVE EPIC. Slice 0 DONE. NEXT: Slice 1** (free-scale
analytic gradient + safeguarded Newton loop, `initial.spg` start).

## Slice status

| slice | scope | status |
|---|---|---|
| **0** | diagnose: barrier or early stop? | **DONE 2026-10-03 (ADR-241)** — `scripts/gam_outer_solver_landscape_probe.py`; two outer-search defects: L1's first ACCEPTED L-BFGS-B step is 11.8 decades onto the plateau; 3c has no barrier and stops non-stationary on the `factr` function-reduction test (its 7-decade trial was rejected) |
| **1** | free-scale analytic gradient; safeguarded Newton (step cap, halving, PD Hessian, converged-direction drop, gradient-based convergence test); `initial.spg` start | **NEXT** |
| **2** | exact Hessian (Wood 2011 §3.4-3.5, App. D) | registered |
| **3** | §3.1 reparameterisation through fit + derivatives; thread-axis study first | registered |
| **4** | surface as `fit_polaris_gam`'s default; the gauntlet (PLAN §3 Slice 4) | registered |

## What the next session needs to know

- **Do not add a start strategy.** Multistart, two-start, seeded start and
  best-of-both all exist and all stay opt-in. The defects are the search's step
  and its stopping rule, not the start (PLAN §1). A disagreement found mid-slice goes into Slice 4's gauntlet
  as a case (ROUTINE "MECHANISM BEFORE SLICE"), never into a new slice.
- **The probe is the instrument.** Re-run `gam_outer_solver_landscape_probe.py`
  on any new disagreement before forming a hypothesis: it says in one run
  whether the search overshot (accepted iterates),
  stopped early (SciPy's exit message, gradient at the stop), or met a barrier.
- **What already exists and is verified:** known-scale analytic gradient
  (`gam_reml_gradient`, ADR-220); `d beta/d rho` and `dw/drho`
  (`gam_derivatives`); Appendix B transform and stable root
  (`gam_reml_appendix_b`, wired to `log|S|+` only); inner step-halving
  (`step_halving=True`, ADR-224); `initial.spg` start
  (`gam_initial_sp`, ADR-239); per-direction identifiability
  (`gam_sp_identifiability`, ADR-219).
- **`mgcv`'s Newton controls** (`gam.control()$newton`, 1.9.1, tier 1):
  `conv.tol = 1e-6`, `maxNstep = 5`, `maxSstep = 2`, `maxHalf = 30`. Re-read
  them on tier 3 (the 1.9.4 image) before citing them in an ADR as settled.
