# Continuation: the GAM parity preview

**Plan:** `docs/PLAN_gam_parity_preview.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-06, epic-start session (ADR-249).
**Status:** **IN PROGRESS. P1 DONE (ADR-249 + HGAM held-out, ADR-250). P2 DONE (ADR-250). NEXT: P3 (formula front end).**

## Slice status

| slice | scope | status |
|---|---|---|
| **P1** | `predict` at new rows | **DONE** — `feat(mgcv-parity)`, INDEPENDENT (ADR-249; HGAM held-out closed in ADR-250) |
| **P2** | `vcov`, `predict(se_fit=True)` | **DONE** — `feat(mgcv-parity)`, INDEPENDENT, tier 3 run 37613368268 (ADR-250) |
| **P3** | `polaris_re.gam.gam(formula, ...)` + refusals | next |
| **P4** | `summary()`, 13+-block target-size fit | — |
| **P5** | guide, notebook, generated parity report | — |

## Staying on track — checkpoints (maintainer-agreed 2026-10-07)
The factor-`by` miss (`gaussian_factor_by`, ADR-249) is documented, not fixed: no solver work, no start strategy (PLAN §4 rules 3-4). It is revisited ONLY at these points, each owned by an existing slice:

| when | what happens | owner |
|---|---|---|
| ~~start of the next session~~ | DONE 2026-10-07: HGAM held-out MET at tier 3; P2 landed | P1 / P2 |
| **P3 (refusal list)** | decide: refuse `s(x)` + `s(x, by=f)` on one covariate — **ADR-250 sharpens this: key the refusal on the structural condition `rank(X) < p`, not only the syntax**, citing `MGCV_FEATURE_COVERAGE.md`; open maintainer question 2 (recommended: refuse). Bare `s(x)` stays refused until L7 `tp`, explicit bases accepted | P3 |
| **before P5 states the limitation's size** | a second probe draw (tier-1 vs tier-3 `edf` changed sign) | P5 |
| **P4 target-size fit** | if it fails on gradient precision, Slice 3b's release condition fires; re-run `gaussian_factor_by` as a regression case then | P4 |
| **after P3, before P5 states the limitation** | run parity-engine Slice 9 (rank pivoting) — maintainer-registered 2026-10-07; relaxes P3's structural refusal | Slice 9 |
| **any time** | only on preview-user demand for factor-`by`, or evidence the plateau is precision not valley, and then via Slice 3b | maintainer |

Guardrails each session re-reads before acting: one slice per session; no splitting; a disagreement outside the target formula is a recorded limitation; every number carries tier + digest; every comparison declares provenance.

## Maintainer answers (2026-10-07)
1. P4/P5 unchanged: P5 stays a separate slice.
2. A bare `s(x)` stays refused until `tp` (L7) lands, provided the same model can be fitted with an explicit basis (`bs="cr"`, `bs="re"`, ...). P3 must therefore accept every explicit-basis form in the verified subset; a test pins a refused bare `s(x)` and its explicit equivalent.
Still open: the factor-`by` question below (not addressed by the answer above).

## Maintainer questions (as asked)
1. **Fold P5 into P4?** (PLAN header asks whether P5 is a polish tail.) Recommended: **no** — P5 carries the generated parity report, an aggregate of INDEPENDENT claims, so it is a deliverable. Keep five slices.
2. **Factor-`by` limitation.** `gaussian_factor_by` (s(x) + s(x, by=f), 3 levels) does not converge under Newton and misses ADR-221 at tier 3 (eta 2.5e-02, edf +0.458; ADR-249). Recommended: record as a limitation and make P3 refuse a factor-`by` smooth next to a bare `s(x)` of the same covariate unless the maintainer wants it investigated as an outer-search case (it would go to Slice 3b's release condition, not a new start strategy).

3. **ANSWERED 2026-10-07 (maintainer): support the rank restriction in P3, but `s(x) + s(x, by=f)` has a real use case, so the fix is on the roadmap — registered as `PLAN_mgcv_parity_engine.md` Slice 9 (pivot the unidentified coefficient out). One slice; tier-1 experiment: converged, edf +0.0037.** Original question: **Factor-`by` mechanism (ADR-250).** The miss is a RANK defect (`rank(X)` 22/29, one null direction in `X'WX+S`), not an outer-search plateau; `vcov`/`se_fit` refuse such a fit. Recommended: P3 refuses by the structural test and the guide lists it as a limitation; pivoted-rank handling (as `mgcv` does) is NOT taken as a slice unless preview users need `s(x) + s(x, by=f)`.

## What the next session needs to know
- P2 done: `PolarisGAMFit.vcov`, `predict(se_fit=, unconditional=)`; `gam_vcov.py`; the SAME probe/compare script carry the `se.fit` columns (`_SE_REL_TOLERANCE = 2e-2`). P3 should call these, not re-derive them.
- `PolarisGAMFit.term_states` holds knots + absorbed constraints; `predict_design(model, states, newdata)` is the entry point for `se_fit` (P2): `se = sqrt(rowSums((X_new @ Vp) * X_new))`.
- `gam_predict_conformance.PREDICT_CLAIM` / `scripts/gam_predict_probe.R` / `scripts/gam_predict_compare.py` are wired into `mgcv-conformance.yml` (non-gating, `continue-on-error`). Extend the SAME probe for P2 (`predict(se.fit=TRUE)`, `vcov`) rather than adding a new one.
- `_cr_basis_raw` now extrapolates linearly (ADR-249 item 3).
- Local R needs `apt-get update` before `apt-get install r-base-core r-cran-mgcv r-cran-jsonlite`.
- Baseline here (no mortality tables): 5 environmental failures (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`), pre-existing.
