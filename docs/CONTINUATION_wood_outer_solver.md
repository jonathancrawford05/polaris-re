# Continuation: the Wood-shaped outer solver

**Plan:** `docs/PLAN_wood_outer_solver.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-03, by the epic-start session (ADR-241).
**Status:** **IN PROGRESS — ACTIVE EPIC. Slices 0-3, 4a and 4b DONE; 4c part 1 DONE. NEXT: Slice 4c (remaining).**
4c part 1 (ADR-247, tier 3 run 37232079212, `sha256:0d54c192…`): `harness(mgcv-parity)` — nothing INDEPENDENT. The gate's exit path is unit-tested; gauntlet case 5's thread axis (Polaris vs itself, no mgcv side) reads worst d eta 3.6e-08 over nine cases, `select=TRUE` d log10(sp) 7.3e-04. Still owed: `epsilon_rel` to the maintainer, INDEPENDENT `log10(sp)` on `select=TRUE`, the default flip.
Slice 4b (ADR-246, tier 3 run 37213172762, `sha256:0d54c192…`): `feat(mgcv-parity)`, INDEPENDENT — case 4, ADR-227's 4-term HGAM, one Newton start: eta 5.212e-05, edf_total +0.0048, 8 fits, agrees; the nine 4a rows unchanged. The quasipoisson fixed-scale rows are now a blocking CI step (`--gate`). Default NOT flipped; case 5 not run.
Slice 4a (ADR-245, tier 3 run 37204039328, `sha256:0d54c192…`): `feat(mgcv-parity)`, INDEPENDENT — one Newton start meets ADR-221 on all nine rows (six free-scale cells, fixed scale 2 and 6, `select=TRUE` N=7); `scripts/gam_newton_gauntlet.py`. Default NOT flipped; cases 4-5 not run.
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
| **4a** | gauntlet cases 1-3 | **DONE 2026-10-04 (ADR-245)** — tier 3, INDEPENDENT |
| **4b** | case 2 blocking CI step; case 4 HGAM | **DONE 2026-10-04 (ADR-246)** — tier 3, INDEPENDENT |
| **4c** | gate exit-path unit test (DONE); case 5 thread axis (DONE, ADR-247); `epsilon_rel` question; `log10(sp)` on `select=TRUE`; default flip | **part 1 DONE; remainder NEXT** |

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

## Added by slice 4a (2026-10-04)
- New: `gam_newton_gauntlet_conformance.py` (`run_gauntlet`, `gauntlet_claims`, `require_gauntlet_parity_evidence`), `scripts/gam_newton_gauntlet.py`, one non-gating CI step. `outer=` now reaches every free-sp fit helper; the fixed-scale Newton branch is one fit per scale (no unit-gamma seed).
- Case 3's earlier tier-1 pre-reading is superseded by the tier-3 row (eta 5.671e-05, edf +0.0038, 20 fits).
- Slice 4b must also read the `log10(sp)` column on `select=TRUE` (two plateau blocks differed by 0.25-0.3 decades in the pre-reading) before any "reliable" wording; ADR-221 does not gate it.
- No perf row: every touched `src/` file is a `*_conformance.py` outside the probe closure (ADR-177 amendment 2; `sys.modules` check returned `[]`).

## Added by slice 4b (2026-10-04)
- New: `outer=` on `fit_production_mi_case` (pass `multistart=False` with it); `PRODUCTION_MI_NEWTON_CLAIM` (its own claim, two columns — do NOT run `newton_variant` over the multistart claim, its replacement garbles the text); `gate_failures`, `REQUIRED_CASE_PREFIXES`; `gam_newton_gauntlet.py --gate`; one blocking CI step. No perf row (`sys.modules` closure check returned `[]`).
- The gate is separate from the report step on purpose: the report step is `continue-on-error`, which would swallow the exit code. Widening `REQUIRED_CASE_PREFIXES` is the reviewable edit if the maintainer wants more rows blocking.
- The gate has unit tests (missing/disagreeing/unconverged/error rows) but has never been seen failing in CI.
- Slice 4c still owes: `log10(sp)` on `select=TRUE` before any "reliable" wording; `epsilon_rel` put to the maintainer; case 5 thread axis (seed axis has no operand for Newton).
- Mid-session CI timing: a full `mgcv-conformance.yml` dispatch took ~7 minutes, not ~1; the "~1 minute" in the routine file is the R-reference job alone.

## Slice 4c inputs from PR #255 review and maintainer decisions (2026-10-04)
- **1st-order, do first: a unit test for the gate's exit path** (maintainer comment on PR #255). `gate_failures` is tested; the script's `--gate` branch is not. Monkeypatch `run_gauntlet` and `payloads_from_probe_dir` as imported by `scripts/gam_newton_gauntlet.py`; return a `quasipoisson fixed scale=6` row with `agrees=False`; assert `pytest.raises(SystemExit)` with code 1. Add the mirror case: a passing fixed-scale pair returns normally. Needs no R and no CI dispatch.
- **`select=TRUE` N=7 is not stable to the printed digit across CI runs** (review P2-1). Same oracle `sha256:0d54c192…` and identical `src/`: run 37213172762 and ADR-245 read 5.671e-05 / +0.0038, the head run 37213760199 reads 5.674e-05 / +0.0039. Far inside ADR-221, but it is the fixture case 5 (thread axis) and the `log10(sp)` plateau reading will examine. "Unchanged at every printed digit" (ADR-246) holds for the other rows in the compared run, not as a general property.
- Test-assertion amendments (row count 8 to 9; `outer` in the signature pin) APPROVED by the maintainer.
- The `--gate` step re-fits all ten cases to gate two rows (review P2-2). Kept deliberately: simpler, and the gate stays independent of the `continue-on-error` report step. Persisting the report step's readings as JSON for the gate to read is the alternative if the cost matters.

## Added by slice 4c part 1 (2026-10-04)
- New: `run_thread_axis` / `ThreadAxisReading` / `THREAD_AXIS_CASES`, `scripts/gam_newton_thread_axis.py`, one non-gating CI step, 3 gate-exit tests. No perf row.
- The thread axis is NOT parity evidence (no mgcv side). Do not cite it as "reliable"; seed axis has no operand.
- CI step output lives in the job summary; `gh run view --log` is blocked by the proxy, but the GitHub MCP `get_job_logs` with `return_content` and a large `tail_lines` saves the log to a file you can grep.
- Remaining 4c: `epsilon_rel` / curvature-to-noise to the maintainer; INDEPENDENT `log10(sp)` reading vs mgcv on `select=TRUE`; default flip; `evidence_markdown` DoD table.
