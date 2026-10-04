# Dev session log — 2026-10-03 — outer-solver slice 2 (exact REML Hessian)

**Branch:** `claude/intelligent-hamilton-9yq3rk`. **Routine:** `docs/ROUTINE_MGCV_PARITY.md` (active epic `PLAN_wood_outer_solver.md`). **PR title class:** `feat(mgcv-parity)` — the slice lands an INDEPENDENT comparison (`rho_hessian` vs `mgcv`'s `outer.info$hess`).
**Perf verdict (ADR-177):** row appended (touches non-conformance `src/` modules `gam_reml_hessian.py`, `gam_reml_newton.py`).

## Baseline
`pytest tests/ -m "not slow"` with R installed: 3882 passed, 22 skipped, 5 failed — the same 5 standing failures as the Slice 1 log (generated mortality tables absent: `test_experience_loaders` ×1, `test_synthetic_block::TestCalibratedPremiums` ×4). Passed count = Slice 1's 3851 + this slice's 30 new tests + R's flip of one skip (installing R enables `test_the_r_script_runs_end_to_end_and_agrees`). `tests/qa/` (goldens) passed untouched.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt, after `apt-get update`), `OPENBLAS_NUM_THREADS=1`. Tier 2 unavailable (docker CLI, no daemon reachable for this use). Tier 3: CI run 37153229821, R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. Every number in ADR-243's tables is tier 3; tier-1 readings appear here and in the ledger only, labelled.

## Gap Before
Slice 1's state (ADR-242, tier 3): Newton agrees with `mgcv` on L1/3b/3c but pays `2 x free` extra penalized fits per iteration for a differenced Hessian (92/37/52 fits; L-BFGS-B 790/65/75), and L1's tier-1 run stalled with `converged=False` (grad 6.1e-4 vs 1.7e-4) while tier 3 passed thinly and non-reproducibly. No analytic Hessian existed; the only Hessian comparison to `mgcv` was a finite-difference one reported inside level 4.

## Hypotheses Tried
1. Registered: the exact Hessian — `dg_j/drho_k` differentiated term by term from Wood 2011, with `w''` from series arithmetic and a Schur term for the profiled scale — equals `mgcv`'s own `outer.info$hess`. **HELD** at tier 1 first try (≤ 6e-8 scaled on five cases) and at tier 3.
2. Sub-hypothesis: the free-scale profile Hessian is the known-scale one at `phi_hat` minus `q_j q_k / (2 phi² (n-Mp))`. **HELD** (central-difference tests; `mgcv`'s Schur complement).
3. Sub-hypothesis: replacing the differenced Hessian keeps Slice 1's verdicts. **HELD**; fits 92→11, 37→5, 52→8.
4. Sub-hypothesis (from Slice 1 finding 2): L1's tier-1 stall was Hessian noise as well as the gradient's precision floor. **PARTLY SUPPORTED**: tier 1 now converges and equals tier 3 to the printed digits; the `cond(H)` floor itself is untouched.
5. Considered and rejected: comparing quasi families' `m$sig2` to `phi_hat`. It differs 16.6% (tier 1) while the Hessians agree to 6e-8 — different estimator (Pearson-type reporting estimate vs REML profile). Excluded by construction rather than reported as a disagreement.
No hypothesis failed; no ledger dead end this session.

## Gap After
`rho_hessian` vs `outer.info$hess`, tier 3: ≤ 1.7e-10 scaled on the three known-scale cases (incl. non-canonical cloglog), 6.0e-8 quasipoisson, 1.3e-9 gaussian (+ `scale_hat` 5.0e-8). Newton eta/edf vs `mgcv`: L1 3.674e-06/+0.000, 3b 4.048e-05/-0.001, 3c 1.120e-05/-0.000, all gradient-test stops. This is **agreement**, not a residual gap, within the five cases and at `mgcv`'s own `sp`.

## Provenance
- `rho_hessian` — INDEPENDENT. Left: `gam_reml_hessian.reml_score_hessian[_profiled]` on a Polaris `penalized_irls_general` fit, from `RHessianRecipe` (design, penalty blocks, `y`, prior weights, `selected_sp`; **no** `outer_hessian`/`scale`/gradient key; a test shows the output is invariant to the payload's reference Hessian). Right: `mgcv` `gam(method="REML")$outer.info$hess`, Schur-reduced over `log phi` when scale is estimated. Shared input disclosed: `selected_sp` is the POINT OF EVALUATION (a Hessian is a function of rho), not an operand.
- `scale_hat` (gaussian only) — INDEPENDENT: `phi_hat = Dp/(n-Mp)` from Polaris's fit vs `m$sig2`.
- Newton eta/edf_total/log10(sp)/per-term edf — INDEPENDENT (existing L5/3b claims, headline from `evidence_markdown(newton_variant(...))`; recipe excludes `mgcv`'s eta/coef/sp/edf).
- Fits per search, step size, gradient vs tolerance, `eps*cond(H)` — Polaris-only MEASUREMENTS (own criterion), no parity claim.
- Analytic Hessian vs central difference of the analytic gradient — own criterion, no oracle (derivation check).
- No ECHO or TRANSPORT column is reported as evidence.

## DoD (PLAN Slice 2, verbatim, with evidence)
- [x] `[machine]` analytic Hessian equals a central difference of the analytic gradient on all three family/link combinations, before composition — `tests/test_analytics/test_gam_reml_hessian.py::test_hessian_matches_a_central_difference_of_the_analytic_gradient` (5 family/links × 3 points incl. `1e11`; mutation-checked)
- [x] `[machine]` Slice 1's two cells re-run at tier 3, readings unchanged in verdict — ADR-243, run 37153229821
- [x] `[machine]` function evaluations per fit reported beside L-BFGS-B's — ADR-243 table, `scripts/gam_newton_outer_check.py`

## Open / follow-ups
Slice 3 NEXT (thread-axis study first, on the exact-Hessian search). Mechanism class of everything touched: (iii); no new slice registered, no start strategy added. 2nd-order: level 4 could use this Hessian instead of `mgcv`'s as a shared input. Level 4 still DISAGREES on the shipped path (standing). Tolerance caveat recorded in ADR-243: 1e-6 was fixed from `mgcv`'s `conv.tol` after seeing tier-1 readings.
