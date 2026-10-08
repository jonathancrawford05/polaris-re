# Dev session log — 2026-10-07 — GAM parity preview: Slice P2 (standard errors) + P1's carried HGAM comparison

**Branch:** `claude/dreamy-galileo-wife66`. **PR title class:** `feat(mgcv-parity)` — every compared column is INDEPENDENT.
**Box vs repo:** the registered box names no epic; the repo's active-epic pointer named `PLAN_gam_parity_preview.md` (P1 carry, then P2). Repo followed; no conflict on fact.
**Perf:** one row appended (ADR-177; `perf_history` verdict: no structural creep, no wall-time creep, no config drift; peak 33 -> 33 MiB, wall-time recent/baseline 1.122x advisory): the PR touches `gam_model.py` and adds `gam_vcov.py`, neither a `*_conformance.py` module.

## Baseline
No mortality tables here, so five environmental failures stand (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`). **Before** (previous parity log, same environment): 3938 passed, 5 failed, 22 skipped, 145 deselected. My own pre-change run was contaminated by concurrent edits and is not used. **After:** **3952 passed, 5 failed, 22 skipped, 145 deselected** (`-m "not slow"`, whole `tests/`, incl. `tests/qa/` — goldens untouched). +14 passed = 12 new tests in `test_gam_vcov.py` + 2 new parametrised predict cells; the same five failures.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (after `apt-get update`). Tier 3 (every committed number): CI run 37613368268, commit `f9ffcfb`, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. Tier-1 and tier-3 readings identical at the printed digits.

## Gap Before
No covariance on `PolarisGAMFit`, no `se_fit`. P1's 4-term HGAM held-out comparison unmet. Starting gap for the new columns: none existed.

## Hypotheses Tried
1. The 4-term HGAM and a `select=TRUE` cell predict like `predict.gam`. HELD (tier 3).
2. `Vp` (Newton weights, Fletcher scale) and `Vc` (WPS eq. 7 with Polaris's OWN exact REML Hessian) reproduce `predict.gam(se.fit=TRUE[, unconditional=TRUE])` within a 2e-2 relative gate derived before the tier-3 run. HELD on 7 fitted cells (Vp <= 3.0e-03, Vc <= 1.2e-02).
3. `gaussian_factor_by` (ADR-249's miss) is a rank defect, not the outer search. HELD: `rank(X)` 22/29, min eig(`X'WX+S`) 7e-15. Mechanism corrected from class (iii) to (ii); covariance refused; no solver work, no slice.
No pass failed to move; no tolerance was touched.

## Gap After
Seven of seven covariance-bearing fitted cells agree on `se.fit` under `Vp` and `Vc`; scale <= 3.6e-03. HGAM held-out closed. Open: factor-`by` + bare-smooth fits are refused (limitation).

## Provenance
All columns INDEPENDENT (`PREDICT_CLAIM`; headline from `evidence_markdown`). Left producer: `fit_polaris_gam` + `vcov`/`predict(se_fit)` from `PredictRecipe` (training columns, `y`, new covariates — no mgcv output is a key, pinned by test). Right producer: `mgcv::gam(method="REML")` + `predict.gam(se.fit=TRUE)`, `m$Vp`, `m$Vc`, `m$scale` from its own fit. Polaris supplies mgcv nothing it reads back. Per column: se.fit Vp and Vc (INDEPENDENT, gated 2e-2), response-scale se, projected covariances, scale (INDEPENDENT, reported). The ADR-202 comparison borrowed mgcv's Hessian; this one does not. `test_gam_vcov.py` closed forms are MEASUREMENT (own criterion), not parity. The rank/eigenvalue reading is Polaris against itself (own criterion).

## Definition of done (PLAN P2)
- INDEPENDENT `[machine]` vcov / unconditional vcov / se.fit vs Polaris on six cells + HGAM: **MET** on 7 fitted cells (+ select=TRUE row); `gaussian_factor_by` **NOT MET, because** its covariance is refused (rank defect, ADR-250). Evidence: run 37613368268; `scripts/gam_predict_compare.py`.
- Tolerance derived and written before the first tier-3 run: **MET** — `_SE_REL_TOLERANCE` docstring, committed in `f9ffcfb` before the dispatch; ADR-250.
- `select=TRUE` reported separately: **MET** — `gaussian_select` row (5.3e-05 / 2.9e-04); the near-singular `V_rho` risk did not materialise on this draw.
- quasi-family scale convention stated and measured: **MET** — ADR-250 "Scale"; scale matches `m$scale` to 3.6e-03.

## Maintainer questions
3 (new): factor-`by` is a rank defect; recommended P3 refuses by `rank(X) < p`. **ANSWERED by the maintainer, 2026-10-07:** support the restriction, but `s(x) + s(x, by=f)` has a use case, so the fix is registered as `PLAN_mgcv_parity_engine.md` Slice 9 (one slice). See CONTINUATION.
