# Continuation: the Wood-shaped outer solver

**Plan:** `docs/PLAN_wood_outer_solver.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-03, by the epic-start session (ADR-241).
**Status:** **IN PROGRESS — ACTIVE EPIC. Slices 0-3 DONE. NEXT: Slice 4** (the gauntlet).
Slice 3 (ADR-244, tier 3 run 37167311644, `sha256:0d54c192…`): characterisation, `harness(mgcv-parity)` — nothing INDEPENDENT landed. Newton+exact Hessian is thread-reproducible with no reparameterisation (d eta 2.8e-07 vs 0.356 for multistart); the gradient's rounding noise (6.5e-05 at an 11-decade spread) was term 1 contracting the formed block, now a sum of squares (4.7e-08), same for the Hessian. Four transform hypotheses refuted.
Slice 2 (ADR-243): exact Hessian equals `mgcv`'s `outer.info$hess` to <= 6e-8 (scaled) on five family/link cases, INDEPENDENT, tier 3 run 37153229821 (`sha256:0d54c192…`); Newton with it needs 11/5/8 fits vs 92/37/52 differenced vs 790/65/75 L-BFGS-B; L1 now reads identically at tier 1 and tier 3.
Slice 1 (ADR-242): `fit_polaris_gam(outer="newton")` agrees with mgcv on gaussian L1, quasipoisson 3b and the 3c draw from one start, tier 3 run 37130685404 (`sha256:0d54c192…`), all stopping on the gradient test, accepted steps <= 2.171 decades. Caveat: L1's tier-3 gradient margin is 1.17e-4 vs 1.66e-4 and its tier-1 run stalled on the analytic gradient's precision floor (`cond(H) 3.6e11`) — Slice 3's territory.

## Slice status

| slice | scope | status |
|---|---|---|
| **0** | diagnose: barrier or early stop? | **DONE 2026-10-03 (ADR-241)** — `scripts/gam_outer_solver_landscape_probe.py`; two outer-search defects: L1's first ACCEPTED L-BFGS-B step is 11.8 decades onto the plateau; 3c has no barrier and stops non-stationary on the `factr` function-reduction test (its 7-decade trial was rejected) |
| **1** | free-scale analytic gradient; safeguarded Newton (step cap, halving, PD Hessian, converged-direction drop, gradient-based convergence test); `initial.spg` start | **DONE 2026-10-03 (ADR-242)** — tier 3, INDEPENDENT; opt-in `outer="newton"` |
| **2** | exact Hessian (Wood 2011 §3.4-3.5, App. D) | **DONE 2026-10-03 (ADR-243)** — `gam_reml_hessian.py`; INDEPENDENT vs `outer.info$hess`, tier 3; `newton_select_lambdas(hessian="exact")` default |
| **3** | §3.1 reparameterisation through fit + derivatives; thread-axis study first | **DONE 2026-10-04 (ADR-244)** as a characterisation; transform not wired; derivative-path quadratic forms fixed; 3b (QR-augmented solve) registered, not released |
| **4** | surface as `fit_polaris_gam`'s default; the gauntlet (PLAN §3 Slice 4) | **NEXT** |

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

## Added by slice 1 (2026-10-03)
- New code: `gam_reml_newton.py` (`newton_select_lambdas`), `reml_score_gradient_profiled`, `outer=` on `fit_polaris_gam`. Slice 2 replaces `_hessian` (central difference of the analytic gradient, `2 x free` fits/iteration) with the exact one.
- Newton is NOT start-free on a plateau (ADR-242 finding 3): keep `initial.spg`; the plateau case belongs to Slice 4's gauntlet.
- The `newton` constants are still tier-1 reads (mgcv 1.9.1); re-read on the 1.9.4 image before citing as settled.
- The CI report's headline reuses the L5/3b claims whose text names `select_lambdas_continuous`; a caveat line in the report says the search under test is Newton.

## Added by slice 2 (2026-10-03)
- New code: `gam_reml_hessian.py` (`reml_score_hessian[_profiled]`, `d2w_deta2_observed`, `d2log_det_s_plus_drho2`), `gam_hessian_conformance.py`, `scripts/gam_hessian_probe.R` + `gam_hessian_compare.py`. `newton_select_lambdas(hessian="exact"|"difference")`; exact is the default, `"difference"` is kept only for A/B.
- `mgcv`'s free-scale `outer.info$hess` is `(M+1)x(M+1)` over `(log sp, log phi)`; compare the Schur complement. Quasi families' `m$sig2` is NOT the REML profile's `phi_hat` — do not compare them (ADR-243).
- For Slice 3: the precision floor (`eps*cond(H)` 7.7e-5 on L1 at the stop) is the same at tier 1 and tier 3 now; the thread-axis study should be re-measured on the EXACT-Hessian search, since Slice 1's thread-sensitivity readings were taken on the differenced one.
- 2nd-order: level 4's new stack still takes `mgcv`'s Hessian as a shared input (`gam_uncertainty_conformance`); `reml_score_hessian` could replace it and remove that disclosure.

## Added by slice 3 (2026-10-04)
- New: `scripts/gam_precision_floor_probe.py` (thread axis, `float128`, ulp-perturbation floor; own criterion), `tests/test_analytics/test_gam_penalty_quadratic_forms.py`, one non-gating CI step. Changed arithmetic only: `gam_reml_gradient._gradient_at_scale` term 1, `gam_reml_hessian._hessian_at_scale` `A_j beta`/`q_j`.
- **Do not use a random orthogonal rotation as a reproducibility gate**: it also perturbs `S`'s representation, which carries an irreducible sensitivity (gradient up to 2.6e-05 at `mgcv`'s point). Perturb `X` only to isolate evaluation noise.
- **The 1.8e-4 `float128` "inaccuracy" of the sum-of-squares penalty (ADR-222 amendment 2) is a representation gap, not an evaluation error.** Do not re-open it.
- Slice 4 case 3 has a tier-1-only pre-reading (ledger, 2026-10-04): one start reaches the 523.645 basin. Re-read at tier 3; do not cite the tier-1 number.
- Slice 4 should cover the seed axis only for the diagnostics that still have a seed (multistart); Newton has none.
