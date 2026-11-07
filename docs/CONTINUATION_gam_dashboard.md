# Continuation: GAM in the dashboard

**Plan:** `docs/PLAN_gam_dashboard.md` · **ADR:** ADR-262 · **Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-22 (epic start + D1 in one session, as the pointer directed).
**Status:** **IN PROGRESS. D1 IMPLEMENTED 2026-10-22, awaiting merge and the maintainer's use of it.** D2 and D3 are not started; release conditions in the PLAN §4.

| slice | status |
|---|---|
| D1 fit and display, read-only | implemented (ADR-262): section in the experience-improvement page; cost model `polaris_re.gam.cost_model`; tests `tests/test_gam/test_cost_model.py`, `tests/test_dashboard/test_gam_fit_section.py` |
| D2 fit as input to A/E / improvement views | NOT STARTED. Release: the maintainer's use of D1 and a written go |
| D3 CLI / MCP / API | NOT STARTED. Release: written go after D2 |

**Merged-state note:** D1's DoD memory item stays PARTLY MET (gam peak RSS measured on one real cell only).

## Maintainer questions
1. **ANSWERED 2026-11-07 (PR #277 comment, tier L, one cell, one machine, MEASUREMENT): T1_mid (109,158 rows, ~78 coef) gam predicted 19.0 s (band 9.1-39.8) vs 13.5 s actual (page) / 13.48 s (headless); bam 0.3 s (0.1-0.7) vs 0.31 s; edf_total 62.68 vs 62.676, converged. Inside both bands; the model was fitted on this machine, so it is not a check elsewhere. The page also logged `slogdet` divide-by-zero/overflow warnings (fit converged); see the harvest.** *(Original question:)* Maintainer run of the cost model. The model is fitted on your M4 timings, but nothing has confirmed its predictions on a fresh fit there. *Recommended:* run the page on one ILEC `mid` cell with each engine and tell me predicted vs actual; I would record it (tier L) and widen the band if it misses.
2. **Profiles vs partial effects.** D1 shows link profiles with others held at median/reference. *Recommended:* keep for D1; decide partial effects (and `ti`/`by` terms) when you specify D2.
3. **Corrected fact:** R2 did record `gam` peak RSS, but only as a process high-water (upper bound). See ADR-262.

**Tier-L readings, 2026-11-07 (PR #277 comments; maintainer M4, 24 GB, 1 thread; MEASUREMENT, own criterion, one machine).** All six fits inside the stated bands; every gam fit converged and logged `slogdet` divide-by-zero/overflow warnings (the bam path logged none). Caveats: the T2 subsamples reuse a formula the model was fitted on, so they test row count more than formula novelty; the T2_full bam memory (6.82 GB) is inside the band but at its low edge (the model over-predicts, the safe direction); the gam 12x memory assumption held on the one cell with a measured peak (T1_mid: 530 MB measured vs about 0.8 GB at 78 coefficients; the comment's "~12 coefficients / 0.3 GB" looks mislabelled).

| cell | engine | rows | predicted (band) | actual | peak RSS (actual) |
|---|---|---:|---|---|---|
| T1_mid | gam | 109,158 | 19.0 s (9.1-39.8) | 13.5 s | 530.5 MB (script) |
| T2_coarse subsample | gam | 300,000 | 1.7 min (47.5 s-3.5 min) | 70.9 s | not measured |
| T2_coarse subsample | gam (extrapolated, flagged) | 15,000 | 4.3 s (2.0-9.0) | 2.7 s | not measured |
| T1_mid | bam | 109,158 | 0.3 s (0.1-0.7) | 0.31 s | not measured |
| T2_coarse subsample | bam | 300,000 | 1.0 s (0.5-2.3) | 1.4 s | not measured |
| T2_full | bam | 3,015,224 | 16.0 s (7.1-36.0) | 16.35 s | 6.82 GB vs 8.5 +/- 1.9 GB predicted |

## Open limits
`estimate_n_coef` is checked on one synthetic fit only. The sandbox memory sweep is off-range. `bam` has no `summary()` / `reml_score`.
