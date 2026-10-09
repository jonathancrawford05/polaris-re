# Dev session log — 2026-10-09 — mgcv parity: Slice 9 (rank pivoting)

**Branch:** `claude/dreamy-galileo-ui7zhu` (the environment-designated branch; draft PR, not merged by this session). **PR title class:** `feat(mgcv-parity)` — every compared column is INDEPENDENT; two of them disagree (a result).
**Box vs repo:** the registered box names no epic; the repo's ACTIVE EPIC POINTER (CONTINUATION Q8) named parity-engine Slice 9. Repo followed; no conflict on fact. The box's DELIVER and the routine file's DELIVER were read and unioned (perf row, DoD checklist, Provenance section).
**Perf:** one row appended (ADR-177; the PR touches `analytics/gam_model.py`, `gam_vcov.py`, `gam_predict_conformance.py`, `gam/api.py` and adds `gam_rank_pivot.py`, so the amendment-1/2 exemptions do not apply). Verdict: no structural creep (peak 33 -> 33 MiB); wall-time recent/baseline 1.446x, advisory only — the GAM modules are outside the projection probe's import closure, so this is CI-machine variance, not this change.

## Baseline
No mortality tables here, so five environmental failures stand (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`), as in the previous log.
**Before (full suite, R installed, original commit `0ffc276`):** 5 failed, 4061 passed, 22 skipped, 145 deselected (793 s).
**After (full suite, this branch):** see "Baseline after" at the end of this log.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt, after `apt-get update`; as expected). Tier 3 (every committed number): CI run 37973792420, commit `fc507ce`, and the re-dispatch 37975638164 at `5eb2b79` (generator sentence only), oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1.

## Gap Before (tier 3, ADR-249/250/254, run 37938039877 same digest)
`gaussian_factor_by` (`s(x) + s(x, by=f)` via `ModelSpec`): `eta` 2.512e-02, `edf_total` +0.4579, not converged, covariance refused. Through `gam()`: refused by name. Tier 1 reading at session start (same code, local R): edf -1.54 (ADR-250).

## Hypotheses Tried (full detail in the ledger)
1. **Pivoting the unidentified coefficient out reproduces `mgcv`'s `eta`/`edf_total`.** HELD at tier 1 (eta 6.4e-05, edf +0.0037, converged) and at tier 3 (6.306e-05, +0.0036, converged; the second structure `f + s(x) + s(x, by=f)` 8.466e-05, +0.0037).
2. **`Vc` `se` of the pivoted fit matches `mgcv` within 2e-2.** REFUTED (tier 1 3.1e-02). Three follow-ups, each one change: (a) at `mgcv`'s own `sp` the gap stays 2.4e-02 -> not the smoothing parameters; (b) our profiled rho Hessian equals the Schur complement of `mgcv`'s 5x5 Hessian to the printed digits -> not the Hessian; (c) eliminating eight different columns moves `Vc` error 1.8e-02..9.5e-02 while `eta`, `edf` and `Vp` `se` do not move -> `Vc` is not pivot-invariant. No column was tuned to match; `Vc` is refused for pivoted fits. Three passes moved the finding from "gap" to "mechanism", per step 6.
3. **Per-term edf and REML score of a pivoted fit match `summary.gam`.** DISAGREES at tier 3 (per-term edf 1.002 on both cells, gate 1; REML -0.30). Unverified reading: the unidentified direction's edf is attributed to a different term depending on the eliminated coefficient. Recorded as a limitation; gate left unchanged (Q10).
No tolerance was widened or changed; no test assertion was changed to pass (tests that pinned the old REFUSAL were replaced because the behaviour change is the slice: `test_the_rank_deficient_smooth_plus_factor_by_is_refused_on_the_structure`, the predict-probe `gaussian_factor_by` branch, the guide refusal row, the expected-refusal cell). Mechanism class: (ii) criterion / rank handling — not the outer search, so no start strategy / solver work (chain cap not engaged).

## Gap After (tier 3, run 37973792420)
`gaussian_factor_by` and the two formula cells: `eta` <= 8.5e-05, `edf_total` <= +0.0037, converged, structure exact, `Vp` `se` 1.681e-04. Open and recorded: `Vc` refused; per-term edf differs by 1.002 (summary comparison 15 of 17). Section verdicts: predict 9/9, formula 16/16, summary 15/17.

## Provenance
All INDEPENDENT; headlines are `evidence_markdown()` of the existing `PREDICT_CLAIM`, `FORMULA_CLAIM`, `SUMMARY_CLAIM` (no hand-written headline). Left producer: `fit_polaris_gam` / `gam()` from the recipe + training columns + `y` + new covariates (signatures take no `mgcv` output; the existing mechanical tests still pass). Right producer: `gam(method='REML')`, `predict.gam`, `summary.gam` on the image. Per column: lpmatrix, `eta` (in/out of range), response, training-row `eta`, `edf_total`, `se.fit` under `Vp`, term structure, level order, `dev.expl`, scale, per-smooth edf, REML score, deviance, `log10(sp)` — INDEPENDENT; `n` — ECHO. Tier-1 diagnostics (Hessian, `sp`, pivot sweep) are MEASUREMENTS of this engine against a scratch oracle, labelled as such in the ledger, and appear in no tier-3-only location. `tests/test_analytics/test_gam_rank_pivot.py` are own-criterion closed forms, not parity.

## Definition of done (PLAN Slice 9)
- (1) rank detection + pivot elimination in the assembly, recorded in `ModelDesign`: **MET** — `gam_rank_pivot.py`, `pivot_design`, `kept_columns`/`full_width` (recorded on `ModelDesign`, not `TermState`; `predict_design` stays full width and `PolarisGAMFit.predict` applies the elimination — deviation, same effect). Tests `test_gam_rank_pivot.py`.
- (2) `predict_design` applies it: **MET via `PolarisGAMFit.predict`** (see above); lpmatrix comparison unchanged (< 1e-9).
- (3) lift the `vcov` refusal for pivoted designs: **MET for `Vp`** (`vcov()` full width, zero row); **NOT MET for `Vc`, because** it is not pivot-invariant (ADR-255 Decision 3) — refused instead.
- (4) INDEPENDENT tier-3 comparison on `gaussian_factor_by` and one more rank-deficient structure under ADR-221 and ADR-250: **MET for `eta`, `edf_total`, `Vp` `se`** (runs 37973792420 / 37975638164); **`se` under `Vc` NOT MET, because** refused; summary per-term edf **NOT MET (1.002 vs gate 1)**.
- (5) P3's structural refusal becomes "accepted when pivotable": **MET** (`test_the_rank_deficient_smooth_plus_factor_by_is_fitted_with_a_pivot`, guide and coverage updated).
- Exit criterion (`eta` < 2e-2, `|edf|` < 1, converges; ADR-250 `se` gate): **MET for `eta`/`edf`/`Vp` `se`; NOT MET for the `Vc` leg, because** of the measured pivot-dependence.
- `tests/qa/golden_outputs/` byte-identical: **MET** — `tests/qa/` passes in the full suite; no pricing path calls `fit_polaris_gam`.

## Follow-ups harvested
PRODUCT_DIRECTION addendum 2026-10-09 (1st/2nd/3rd-order as classified there). Maintainer questions Q10 (accept the two limitations; stop gating per-term edf for pivoted fits) and Q11 (`select=TRUE` + factor-`by`) are in the CONTINUATION with recommended answers. Nothing opened is merely filed: the limitations are recorded in the guide §7, coverage, ADR-255 and the ledger; no new slice is registered (PLAN-preview §4 rule 3; no user demand).
