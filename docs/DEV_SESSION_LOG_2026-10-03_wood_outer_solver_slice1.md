# Dev session log — 2026-10-03 — outer-solver slice 1 (safeguarded Newton, free-scale analytic gradient)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (active epic `PLAN_wood_outer_solver.md`). **PR title class:** `feat(mgcv-parity)` — the slice lands an INDEPENDENT comparison.

## Baseline
`make test`-equivalent (`pytest tests/ -m "not slow"`): 3851 passed, 22 skipped, 5 failed — all 5 from missing generated mortality tables (`data/mortality_tables/*` not present in this container; `test_experience_loaders`, 4 x `test_synthetic_block`), unrelated to this change. `tests/qa/`: 85 passed, 9 skipped, goldens untouched.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt), `OPENBLAS_NUM_THREADS=1`. Tier 2 unavailable (no Docker daemon). Tier 3: CI run 37130685404, R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. Every number in ADR-242's table is tier 3.

## Gap Before (ADR-221 gate: eta<2e-2, |edf|<1)
Tier 1, reproducing ADR-241: gaussian L1 seeded start eta 2.131e-1 / edf -8.862 / score 180.848 (mgcv 165.30); quasipoisson 3c centre start eta 2.864e-1 / edf -5.614 / score 1642.326 (mgcv 1638.95). Other cells agree. (Stage-A and the other levels are unchanged by this slice.)

## Hypotheses Tried
1. Registered: the two ADR-241 defects (uncapped accepted step; non-stationary stop) are the search; a capped, safeguarded Newton with a gradient test from `initial.spg` reaches mgcv on both cells. **HELD** (tier 3).
2. Sub-hypothesis: free-scale gradient = known-scale gradient at `gamma := phi_hat` (envelope theorem). **HELD**, verified against central differences.
3. L1 tier-1 stall = analytic-gradient precision floor (`cond(H)=3.6e11`). **SUPPORTED at tier 1**, not closed — Slice 3.
4. Newton is start-free. **REFUTED** on a synthetic plateau (own criterion).

## Gap After
Tier 3: L1 eta 4.854e-6 / edf +0.001; 3b 4.048e-5 / -0.001; 3c 1.120e-5 / -0.000; all converged on the gradient test, one start, max accepted step 2.171 decades. (Tier 1 L1: eta 3.0e-6, edf 0.000, but `converged=False`.) The shipped L-BFGS-B path and its multistart are unchanged.

## Provenance
- eta, edf_total (and log10(sp), per-term edf, reported): INDEPENDENT — Polaris `fit_polaris_gam(outer="newton")` from a recipe excluding mgcv's eta/coef/sp/edf vs mgcv `gam(method="REML")`. Headline from `evidence_markdown` of the existing L5/3b claims (their text names `select_lambdas_continuous`; a caveat line says the search is Newton here).
- Newton columns (step size, gradient vs tolerance, eps*cond(H), fits, exit): Polaris-only MEASUREMENT (own criterion); no parity claim.
- Gradient-vs-central-difference tests: own criterion, no oracle.

## DoD (PLAN slice 1)
- [x] free-scale gradient == central difference, gaussian + quasipoisson, 3 points each incl. a `1e11` block — `tests/test_analytics/test_gam_reml_newton.py::test_profiled_gradient_matches_central_difference_of_the_score`
- [x] INDEPENDENT tier 3, L1 and 3c, single start — ADR-242, run 37130685404 (L1 margin thin; see finding 2)
- [x] probe-style reading on the Newton fit: accepted steps <= 2.17 decades and gradient-test stop — same run, `Newton outer search vs mgcv` step
- [x] `[judgement]` nothing patched with a start; the tier-1 L1 stall is characterised (precision floor)

## Open / follow-ups
Slice 2 NEXT; Slice 3 prioritised (PRODUCT_DIRECTION harvest). Mechanism class of this slice's gaps: (iii)/(iv) — handled inside the epic, no new slice registered. Perf row appended (touches non-conformance `src/` modules). Level 4 DISAGREES as standing.
