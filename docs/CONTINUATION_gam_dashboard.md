# Continuation: GAM in the dashboard

**Plan:** `docs/PLAN_gam_dashboard.md` · **ADR:** ADR-262 · **Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Created:** 2026-10-22 (epic start + D1 in one session, as the pointer directed).
**Status:** **IN PROGRESS. D1 merged; D2 IMPLEMENTED 2026-11-07, awaiting merge and confirmation.** D3 is not started; its release condition is the maintainer's written go after D2 (PLAN §4).

| slice | status |
|---|---|
| D1 fit and display, read-only | implemented (ADR-262): section in the experience-improvement page; cost model `polaris_re.gam.cost_model`; tests `tests/test_gam/test_cost_model.py`, `tests/test_dashboard/test_gam_fit_section.py` |
| D2 HGAM-driven effects and improvement surface | IMPLEMENTED 2026-11-07 (ADR-263, checkpoints 1-6): `polaris_re/gam/effects.py`; tests `tests/test_gam/test_effects.py`, `test_improvement_truth.py`, `tests/test_dashboard/test_gam_fit_section.py`; report `scripts/gam_d2_truth_report.py`. Awaiting merge and the maintainer's confirmation of ADR-263 on the D2 PR |
| D3 CLI / MCP / API | PARKED 2026-11-08 (maintainer; ADR-264). The epic continues in `PLAN_gam_dashboard_stabilise_retire.md` |

**Merged-state note:** D1's DoD memory item stays PARTLY MET (gam peak RSS measured on one real cell only).

## Maintainer questions
1. **ANSWERED 2026-11-07 (PR #277 comment, tier L, one cell, one machine, MEASUREMENT): T1_mid (109,158 rows, ~78 coef) gam predicted 19.0 s (band 9.1-39.8) vs 13.5 s actual (page) / 13.48 s (headless); bam 0.3 s (0.1-0.7) vs 0.31 s; edf_total 62.68 vs 62.676, converged. Inside both bands; the model was fitted on this machine, so it is not a check elsewhere. The page also logged `slogdet` divide-by-zero/overflow warnings (fit converged); see the harvest.** *(Original question:)* Maintainer run of the cost model. The model is fitted on your M4 timings, but nothing has confirmed its predictions on a fresh fit there. *Recommended:* run the page on one ILEC `mid` cell with each engine and tell me predicted vs actual; I would record it (tier L) and widen the band if it misses.
2. **ANSWERED 2026-11-07: true partial effects, in D2.** (Was:) Profiles vs partial effects. D1 shows link profiles with others held at median/reference. *Recommended:* keep for D1; decide partial effects (and `ti`/`by` terms) when you specify D2.
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

4. **D2 (new, 2026-11-07).** Truth recovery passed every pre-registered bound on the first run (ADR-263 amendment 1). Two items need you: (i) confirm ADR-263 (PROPOSED -> ACCEPTED) on the D2 PR; (ii) run the page on one real ILEC cell with the new default formula (`ti` + `log_expected` offset) and say whether the surface and its band width look sane at the sparse edges (the open design risk). *Recommended:* one `mid` cell, `gam`, then the same with `bam`, and tell me the band widths at the youngest/oldest ages. Not done and recorded: the `amount` basis is not wired into the HGAM section.

## Open limits
`estimate_n_coef` is checked on one synthetic fit only. The sandbox memory sweep is off-range. `bam` has no `summary()` / `reml_score`.

D2: `slogdet` divide-by-zero warnings on the `gam` path (PRODUCT_DIRECTION 2026-11-07 follow-up) are still unexamined; the surface is trusted only as far as the truth-recovery draws (smooth bilinear truth, 496 cells, count data) show. `bam`'s `Vp` for a contrast was checked on 3 seeds only.

## 2026-11-08 - D2 merged; epic redirected (ADR-264 ACCEPTED)
D2 merged as PR #279 (UX batch #281 merged after it). Real-data runs on aggregated ILEC cells (tier L, MEASUREMENT) found basis saturation, uninformative edge cells shown as results, an unhelpful exposure<=0 refusal, and `slogdet` warnings with a larger basis. Maintainer direction: no D3; stabilise, then re-wire and deprecate the older model. Active plan: `PLAN_gam_dashboard_stabilise_retire.md` (S1-S3, R1-R3). **Answered 2026-11-08 (maintainer, PR #282): ADR-264 and the plan confirmed; order S1, then R1 in parallel, then S2/S3; saturation threshold 0.95.** **Still open:** ADR-263 is "IMPLEMENTED, awaiting confirmation" - say "ACCEPTED" to flip it.

## 2026-11-09 - S1 IMPLEMENTED (ADR-265, PROPOSED; harness/MEASUREMENT, not parity)
`polaris_re/gam/fit_report.py` (saturation flag, surface mask, exposure helpers), `GamSummary` prints a "Basis saturation" line, the page shows an edf/coefficients table + warning per saturated term, masks the MI surface (count stated, CSV blank + `mask_reason`), and refuses non-positive exposure by cause with a "Drop these rows" option (default off). Constants fixed in ADR-265 before the first run: saturation 0.95, mask multiple 5 x the median band. Tests: `tests/test_gam/test_fit_report.py`, `tests/test_dashboard/test_gam_fit_section.py`. Session log: `DEV_SESSION_LOG_2026-11-09_gam_dashboard_s1.md`.
**Next:** S2 and S3 are released once S1 merges; R1 (docs only) may run in parallel.
**Maintainer questions (S1).** (i) Confirm ADR-265 (PROPOSED -> ACCEPTED), in particular the mask multiple 5 (chosen from your 2026-11-08 descriptive band numbers; the first real-data look is yours: tell me how many cells it masks on a `mid` cell and whether that matches your eye). *Recommended:* accept; if the masked share looks wrong, that is a result to report, not a reason to retune in this slice. (ii) Non-positive `q_base` also makes the `log_expected` offset non-finite; S1 only handles exposure as the plan says. *Recommended:* fold a `q_base` check into S3 or leave it. (iii) ADR-263 is still awaiting an explicit "ACCEPTED".

### 2026-11-09 - S1 tier-L readings (PR #283; maintainer's cowork run, MEASUREMENT, own criterion, one machine; relayed text, not re-verified)
Files: aggregated ILEC `ilec_cells_agg` (965 rows) and `ilec_cells_agg_b` (5,659 rows; 86 with exposure <= 0 -> 5,573 fitted). Surface grid 121 ages x 7 years = 847 cells in every run.

| run | rows fitted | k (age/year) | s(age) edf/coef | s(year) edf/coef | ti edf/coef | REML | mask (of 847) | median band |
|---|---:|---|---|---|---|---:|---|---:|
| 1 | 965 | 8/5 | ~100%, flagged | ~97%, flagged | not read | not read | 14 (6 no exposure, 8 wide) | 0.013 |
| 2 | 965 | 20/7 | 99%, flagged | 98%, flagged | not read | 1321 | 11 (6, 5) | 0.0139 |
| 3 | 5,573 | 8/5 | 6.9986/7, flagged | 3.8992/4, flagged | 10.32/16 (65%) | 197,877 | 14 (6, 8) | 0.0128 |
| 4 | 5,573 | 20/7 | 18.85/19, flagged | 5.89/6, flagged | 10.42/16 (65%) | 196,316 | 11 (6, 5) | 0.0139 |

Confirmed: the saturation flag fires on both main smooths in all four runs, including at k=20/7 (the basis is still the binding constraint; `ti` is not saturated); the exposure gate flow (red error naming "86 of 5659 rows", no Run button, tick -> "Dropped 86 row(s) ... 5573 remain" -> Run button) works; the masked cells render blank.
**Open, not answered by the run:** (i) the requested eye test (are ages 0-20 and 120 blanked, 30-90 kept?) was not reported. (ii) Only 11-14 of 847 cells are masked (1.3-1.7%), yet the 2026-11-08 readings had bands of 0.4-1.2 at ages 0-20 and 120 (about 20+ ages x 7 years). Either those edges are not wide relative to 5 x the median here, or the earlier bands were on another model/scale. Per plan §5.6 this is a result, not a reason to retune 5; it needs the edge-band widths (youngest/oldest age, one year) read from the CSV. (iii) Runs 1 and 3 give the same 6 + 8 split on different files, and runs 2 and 4 the same 6 + 5: plausible if the masks are driven by the same grid edges, but worth confirming it is not a stale-display artefact. (iv) Runs 1-2 edf/REML were partly quoted from earlier sessions, not read in this run.

### 2026-11-09 - S1 edge-band reading from the Run 1 CSV (maintainer's cowork, tier L, MEASUREMENT; relayed text)
Run 1 (965-row file, default k=8/5), year 2016: band `mi_upper - mi_lower` is 0.0430 at age 0, 0.0415 at 1, 0.0399 at 2, ... 0.0243 at 118, 0.0253 at 119, 0.0264 at 120; median 0.01275, so the 5x cutoff is 0.0638. Edge ages at mid-years sit at about 2-4x the median (age 115-120 peaks at 4.1x in 2013), under the cutoff. The 8 wide-band cells are ages 0-5 in the first and last calendar years (2013, 2019); the 6 no-exposure cells are ages 118-120 in 2017-2018 (reported as seen in both files). Same corners drive the identical 6+8 / 6+5 splits across files, per the reporter.
**Reading:** the mask behaves as specified on these files; the 5x multiple was not tuned and the result does not call for it. **Unverified:** the reporter's explanation that the 2026-11-08 bands of 0.4-1.2 came from "a different model (likely the full frame with the larger bam surface)" is a guess, not a measurement; those numbers stay unreconciled with these ones. S1 is ready for the maintainer's ACCEPTED on ADR-265 (the 5 is now checked on two aggregated files; it has not been checked on row-level cells).
