# Continuation: the GAM parity preview

**Plan:** `docs/PLAN_gam_parity_preview.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-06, epic-start session (ADR-249).
**Status:** **IN PROGRESS. P1 DONE (ADR-249 + HGAM held-out, ADR-250). P2 DONE (ADR-250). P3 DONE (ADR-251). P4 DONE (ADR-253). NEXT: P5 (guide, notebook, generated parity report, release).**

## Slice status

| slice | scope | status |
|---|---|---|
| **P1** | `predict` at new rows | **DONE** — `feat(mgcv-parity)`, INDEPENDENT (ADR-249; HGAM held-out closed in ADR-250) |
| **P2** | `vcov`, `predict(se_fit=True)` | **DONE** — `feat(mgcv-parity)`, INDEPENDENT, tier 3 run 37613368268 (ADR-250) |
| **P3** | `polaris_re.gam.gam(formula, ...)` + refusals | **DONE** — `feat(mgcv-parity)`, INDEPENDENT, tier 3 (ADR-251) |
| **P4** | `summary()`, 15-penalty target-size fit | **DONE** — `feat(mgcv-parity)`, INDEPENDENT, tier 3 run 37868934383 (ADR-253) |
| **P5** | guide, notebook, generated parity report | next |

## Staying on track — checkpoints (maintainer-agreed 2026-10-07)
The factor-`by` miss (`gaussian_factor_by`, ADR-249) is documented, not fixed: no solver work, no start strategy (PLAN §4 rules 3-4). It is revisited ONLY at these points, each owned by an existing slice:

| when | what happens | owner |
|---|---|---|
| ~~start of the next session~~ | DONE 2026-10-07: HGAM held-out MET at tier 3; P2 landed | P1 / P2 |
| ~~P3 (refusal list)~~ | DONE 2026-10-08 (ADR-251): refusal keyed on `structural_rank_deficiency`, bare `s(x)` refused, explicit bases accepted. Original note: decide: refuse `s(x)` + `s(x, by=f)` on one covariate — **ADR-250 sharpens this: key the refusal on the structural condition `rank(X) < p`, not only the syntax**, citing `MGCV_FEATURE_COVERAGE.md`; open maintainer question 2 (recommended: refuse). Bare `s(x)` stays refused until L7 `tp`, explicit bases accepted | P3 |
| **before P5 states the limitation's size** | a second probe draw (tier-1 vs tier-3 `edf` changed sign) | P5 |
| ~~P4 target-size fit~~ | DONE 2026-10-09: 15-penalty fit converged from one start at 0.885 x epsilon_rel; Slice 3b's release condition did NOT fire (ADR-253). `gaussian_factor_by` regression case therefore not re-run | P4 |
| **after P3, before P5 states the limitation** | run parity-engine Slice 9 (rank pivoting) — maintainer-registered 2026-10-07; relaxes P3's structural refusal | Slice 9 |
| **before P5 states the limitation** | held-out `en_US` collation check (PR #260 review P1-1): result in the ledger row 'held-out'; **held-out MATCHED at tier 3 (run 37811883360, ADR-251 §5); closed.** Original: until it MATCHES, the guide says "use a Polars `Enum`" for string levels with mixed case | P5 |
| **any time** | only on preview-user demand for factor-`by`, or evidence the plateau is precision not valley, and then via Slice 3b | maintainer |

Guardrails each session re-reads before acting: one slice per session; no splitting; a disagreement outside the target formula is a recorded limitation; every number carries tier + digest; every comparison declares provenance.

## Maintainer answers (2026-10-07)
1. P4/P5 unchanged: P5 stays a separate slice.
2. A bare `s(x)` stays refused until `tp` (L7) lands, provided the same model can be fitted with an explicit basis (`bs="cr"`, `bs="re"`, ...). P3 must therefore accept every explicit-basis form in the verified subset; a test pins a refused bare `s(x)` and its explicit equivalent.
Still open: the factor-`by` question below (not addressed by the answer above).

## Maintainer questions (as asked)
5. **ANSWERED 2026-10-09 (maintainer): approved — build the headline from the actual count; to be done in P5 (edit `evidence_headline` in `core/verification.py` + its test, e.g. "Parity comparison on N columns; harness only: ...").** Original: **(P4, new) `evidence_markdown` headline wording.** `core/verification.evidence_headline` prints "Harness check with one parity column — NOT basis parity" whenever ANY column is ECHO/TRANSPORT, even beside six INDEPENDENT ones (P4's table). The text is quoted verbatim as the routine requires; the "one" is hard-coded. Recommended: change to "with N parity columns" (core wording change, a tiny edit + its test) — not done here because `core/verification.py` is the ADR-193 contract and the change is the maintainer's to approve.
6. **ANSWERED 2026-10-09 (maintainer): `n` stays in the claim as ECHO.** Original: **(P4, new) `n` as ECHO.** Recommended: keep it in the claim as ECHO (it makes the headline say so honestly) rather than drop it.
4. **(P3, new) `select=TRUE` with `re`/parametric/factor-`by` terms. PARTLY RESOLVED (ADR-252): `re` and parametric are now accepted, tier-3 verified on one draw each; only factor-`by` remains refused (Slice 9). What is still open is the 13+-block target-size fit (P4).** Original: `gam()` refuses it because the free-`sp` search is verified only on `cr`/numeric-`by`/`ti` (PLAN §5 puts `select=TRUE` on `cr+re+ti` after this epic), yet P4's target-size fit needs exactly that. Recommended: P4 measures the target formula at tier 3 and lifts the refusal only if it meets ADR-221 from one Newton start; otherwise the preview ships the refusal and says so.
1. **Fold P5 into P4?** (PLAN header asks whether P5 is a polish tail.) Recommended: **no** — P5 carries the generated parity report, an aggregate of INDEPENDENT claims, so it is a deliverable. Keep five slices.
2. **Factor-`by` limitation.** `gaussian_factor_by` (s(x) + s(x, by=f), 3 levels) does not converge under Newton and misses ADR-221 at tier 3 (eta 2.5e-02, edf +0.458; ADR-249). Recommended: record as a limitation and make P3 refuse a factor-`by` smooth next to a bare `s(x)` of the same covariate unless the maintainer wants it investigated as an outer-search case (it would go to Slice 3b's release condition, not a new start strategy).

3. **ANSWERED 2026-10-07 (maintainer): support the rank restriction in P3, but `s(x) + s(x, by=f)` has a real use case, so the fix is on the roadmap — registered as `PLAN_mgcv_parity_engine.md` Slice 9 (pivot the unidentified coefficient out). One slice; tier-1 experiment: converged, edf +0.0037.** Original question: **Factor-`by` mechanism (ADR-250).** The miss is a RANK defect (`rank(X)` 22/29, one null direction in `X'WX+S`), not an outer-search plateau; `vcov`/`se_fit` refuse such a fit. Recommended: P3 refuses by the structural test and the guide lists it as a limitation; pivoted-rank handling (as `mgcv` does) is NOT taken as a slice unless preview users need `s(x) + s(x, by=f)`.

## What the next session needs to know
- **P4 done (ADR-253):** `GamFit.summary()` -> `GamSummary` (`polaris_re.gam.summary`); `print(fit.summary())` renders it; no p-values. Comparison: `polaris_re.gam.summary_conformance` (`SUMMARY_CLAIM`: six INDEPENDENT columns + `n` ECHO), `scripts/gam_summary_compare.py`, probes `gam_formula_probe.R` (now also exports `summary.gam`) and `gam_target_size_probe.R`. Tolerances are the ADR-221-implied bounds (`implied_gates`). **P5 should quote `SUMMARY_CLAIM` through `evidence_markdown`, never retype it.**
- **Target-size cell is 5,000 rows, 15 blocks, verified-subset terms only** (no `sz`, not 30,000-row `bam`). The guide must say so. mgcv `gam()` at that size: 15.6 s (CI); Polaris 4.4 s.
- **REML score is not comparable across packages for non-Gaussian / weighted fits** (ADR-231 constant; weighted Gaussian differs by `0.5 sum log w`). The guide must not tell users to compare REML scores with R's.
- Local `mgcv` hangs on near-all-zero count data (any size); use exposures that give counts signal when writing new probe cells.
- **P3 done (ADR-251):** `polaris_re.gam.gam(formula, df, family)` -> `GamFit` (a `PolarisGAMFit`; `predict` takes a DataFrame). `GamFit.smooth_labels` / `smooth_bs_dim` / `n_parametric` / `factor_levels` / `edf_per_term` / `dispersion` / `converged` are what `summary()` (P4) reads. Probe: `scripts/gam_formula_probe.R` + `gam_formula_compare.py`; claim `polaris_re.gam.formula_conformance.FORMULA_CLAIM`.
- **`select=TRUE` scope (ADR-252):** `gam()` accepts it with `cr`/numeric-`by`/`ti`/`re`/parametric; only factor-`by` is refused. P4's job is the 13+-block SIZE, not the structure.
- Oracle collation is `en_US.UTF-8`; the `en_US` rule in `r_factor_levels` was fitted on one 8-string sample and matched a 13-string held-out set (tier 3) only.
- P2 done: `PolarisGAMFit.vcov`, `predict(se_fit=, unconditional=)`; `gam_vcov.py`; the SAME probe/compare script carry the `se.fit` columns (`_SE_REL_TOLERANCE = 2e-2`). P3 should call these, not re-derive them.
- `PolarisGAMFit.term_states` holds knots + absorbed constraints; `predict_design(model, states, newdata)` is the entry point for `se_fit` (P2): `se = sqrt(rowSums((X_new @ Vp) * X_new))`.
- `gam_predict_conformance.PREDICT_CLAIM` / `scripts/gam_predict_probe.R` / `scripts/gam_predict_compare.py` are wired into `mgcv-conformance.yml` (non-gating, `continue-on-error`). Extend the SAME probe for P2 (`predict(se.fit=TRUE)`, `vcov`) rather than adding a new one.
- `_cr_basis_raw` now extrapolates linearly (ADR-249 item 3).
- Local R needs `apt-get update` before `apt-get install r-base-core r-cran-mgcv r-cran-jsonlite`.
- Baseline here (no mortality tables): 5 environmental failures (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`), pre-existing.
