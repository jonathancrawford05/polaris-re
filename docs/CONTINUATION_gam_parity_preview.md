# Continuation: the GAM parity preview

**Plan:** `docs/PLAN_gam_parity_preview.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-06, epic-start session (ADR-249).
**Status:** **IN PROGRESS. P1 landed (ADR-249); NEXT: P2 (standard errors).**

## Slice status

| slice | scope | status |
|---|---|---|
| **P1** | `predict` at new rows | **DONE 2026-10-06 (ADR-249)** — `feat(mgcv-parity)`, INDEPENDENT; HGAM comparison NOT MET (see ADR) |
| **P2** | `vcov`, `predict(se_fit=True)` | next |
| **P3** | `polaris_re.gam.gam(formula, ...)` + refusals | — |
| **P4** | `summary()`, 13+-block target-size fit | — |
| **P5** | guide, notebook, generated parity report | — |

## Maintainer questions
1. **Fold P5 into P4?** (PLAN header asks whether P5 is a polish tail.) Recommended: **no** — P5 carries the generated parity report, an aggregate of INDEPENDENT claims, so it is a deliverable. Keep five slices.
2. **Factor-`by` limitation.** `gaussian_factor_by` (s(x) + s(x, by=f), 3 levels) does not converge under Newton and misses ADR-221 at tier 3 (eta 2.5e-02, edf +0.458; ADR-249). Recommended: record as a limitation and make P3 refuse a factor-`by` smooth next to a bare `s(x)` of the same covariate unless the maintainer wants it investigated as an outer-search case (it would go to Slice 3b's release condition, not a new start strategy).

## What the next session needs to know
- `PolarisGAMFit.term_states` holds knots + absorbed constraints; `predict_design(model, states, newdata)` is the entry point for `se_fit` (P2): `se = sqrt(rowSums((X_new @ Vp) * X_new))`.
- `gam_predict_conformance.PREDICT_CLAIM` / `scripts/gam_predict_probe.R` / `scripts/gam_predict_compare.py` are wired into `mgcv-conformance.yml` (non-gating, `continue-on-error`). Extend the SAME probe for P2 (`predict(se.fit=TRUE)`, `vcov`) rather than adding a new one.
- `_cr_basis_raw` now extrapolates linearly (ADR-249 item 3).
- Local R needs `apt-get update` before `apt-get install r-base-core r-cran-mgcv r-cran-jsonlite`.
- Baseline here (no mortality tables): 5 environmental failures (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`), pre-existing.
