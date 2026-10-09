# Dev session log — 2026-10-09 — GAM parity preview: Slice P4 (summary, target-size fit)

**Branch:** `claude/dreamy-galileo-iyz1mm` (the environment-designated branch). **PR title class:** `feat(mgcv-parity)` — six compared columns are INDEPENDENT (`n` is ECHO and is labelled so).
**Box vs repo:** the registered box names no epic; the repo's active-epic pointer named `PLAN_gam_parity_preview.md`, next slice P4. Repo followed; no conflict on fact. One wording note: the box says the routine DELIVER section is "restated"; I took the union with the repo file.
**Perf:** one row appended (ADR-177): the PR adds `src/polaris_re/gam/{summary,summary_conformance}.py` and edits `gam_model.py`, none exempt.

## Baseline
No mortality tables here, so five environmental failures stand (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`). **Start of session** (R installed, my small additive edits to `gam_model.py` present when the run began): **5 failed, 4026 passed, 22 skipped, 145 deselected** (`make test`, whole `tests/` incl. `tests/qa/`, goldens untouched). **After:** **5 failed, 4036 passed, 22 skipped, 145 deselected** (same five failures; +10 = `tests/test_gam/test_summary.py`). Previous parity log: 4025 passed, 5 failed (P3 baseline; the reviewer's later run 4157/0 had tables).

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1, `LC_COLLATE=C`, `OPENBLAS_NUM_THREADS=1`. Tier 3 (every committed number): CI run 37868934383 (commit `fe4c2a5`), mgcv 1.9.4 / R 4.6.1, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. A first dispatch (37866561963, commit `bcf8a4d`) was cancelled: it ran the degenerate first draft of the target-size cell (see Hypotheses 4).

## Gap Before
`GamFit` had no summary: `edf_per_term`, `log_lambda`, `dispersion`, `reml_score` existed as fields, nothing assembled them, nothing computed deviance explained, and the Newton iteration count and final gradient were discarded by `fit_polaris_gam`. No fit existed at ≥13 penalty blocks through `gam()`.

## Gap After
`GamFit.summary()` exists and every gated column agrees with `summary.gam(m)` on all 13 formula cells and the target-size cell (tier 3, run 37868934383): dev.expl diff ≤ 2.1e-05, scale rel ≤ 7.8e-06, per-smooth edf ≤ 6.4e-03 (2.9e-02 on the target cell). The 15-penalty `select=TRUE` quasi-Poisson fit converged from one Newton start (9 iterations, 0.885 × `epsilon_rel`), 4.4 s vs mgcv 15.6 s. Open: `log10(sp)` up to 1.73 decades on the target cell and 0.94 on select/HGAM plateau rows (reported only, `eta`-insensitive plateau); the REML score is not comparable across packages for non-Gaussian/weighted fits.

## Hypotheses Tried
1. The summary quantities are implied by ADR-221's slack, so a derived bound (not a chosen tolerance) will contain the observed differences. HELD: bounds 1.3e-02..6.8e-02 (dev.expl) and 3.7e-02..1.5e-01 (scale) vs observed ≤ 2e-05 / 8e-06.
2. An intercept-only fit with the offset, solved from the score by root-finding, reproduces `m$null.deviance`. HELD to 2.6e-15 relative on every cell including offsets.
3. The weighted-Gaussian REML offset is `½ Σ log w`. HELD (89.966 vs +89.97), not acted on (reported column).
4. A 30,000-row plain `gam()` REML cell is a usable oracle cell. REFUTED: local mgcv did not finish in 15 min, nor at 1,000 rows in 280 s — the draw had almost-all-zero counts (exposure 0.5–4). Redesigned (exposure 200–4000, 5,000 rows); tier 1 then 93 s, tier 3 15.6 s. No solver change was made; the Wood 3b condition was never in play.
No tolerance was changed after reading a result; no solver, start strategy or constant was touched.

## Provenance
`SUMMARY_CLAIM` (headline via `evidence_markdown`, quoted verbatim in the CI report). Left producer: `fit_summary_case(recipe: FormulaRecipe)` → `gam(...).summary()`: signature takes formula, family, data only (pinned by test). Right producer: `summary.gam(mgcv::gam(<same string>, method="REML"))`, `m$gcv.ubre`, `m$deviance`, `m$null.deviance`. Per column: deviance explained, scale, per-smooth edf, REML score, deviance/null deviance, `log10(sp)` — INDEPENDENT; `n` — ECHO (row count of the shared data). Gated: deviance explained and scale (ADR-221-implied bound computed from Polaris's own fit), per-smooth edf (ADR-221 edf gate), `n` exact. Reported only: REML, deviance components, `log10(sp)`. The Newton convergence table is a MEASUREMENT of Polaris against its own `epsilon_rel`, outside the claim. `tests/test_gam/test_summary.py` is closed-form/own-criterion, not parity. The library headline reads "Harness check with one parity column" because one column is ECHO (wording defect noted, Q5).

## Definition of done (PLAN P4)
- `summary()` — per-term edf, `log10(sp)`, scale, REML score, deviance explained, n, convergence (iterations, final relative projected gradient vs `epsilon_rel = 1e-6`), no p-values, footer says so: **MET** — `tests/test_gam/test_summary.py::test_the_text_report_names_what_it_omits_and_what_it_found`, `test_a_fixed_scale_family_reports_scale_one_and_the_newton_report`.
- INDEPENDENT `[machine]`: per-term edf, `sp`, scale, dev.expl vs `summary.gam(m)` on the gauntlet formulas: **MET on the 13 formula cells** (the P3 probe cells, not the Wood gauntlet's ten rows verbatim); `sp` is compared as `log10(sp)` and **reported, not gated** (ADR-221/248) — so "sp agrees" is NOT claimed. Run 37868934383, ADR-253 Result.
- Scale `[machine]`: target formula (`cr`+`re`+`ti`+parametric+MI `by`, quasi-Poisson, `select=TRUE`, ≥13 blocks), synthetic, production-like size, one Newton start, tier 3, ADR-221 gate; wall time and fit count recorded: **MET for 15 blocks and 5,000 rows**; **NOT MET as stated** for "production-like size" (30,000 rows: the plain-`gam()` oracle cell was not usable, ADR-253 Decision 3) and for the `sz` terms (not in the verified subset). Wall 4.4 s, 10 fits.
- If it fails within 2× of tolerance, run Wood 3b: **did not fire** (0.885 × `epsilon_rel`, converged).

## Maintainer questions
5 (headline wording "one parity column") and 6 (keep `n` as ECHO) — in the CONTINUATION with recommendations. Work that did not depend on them continued.

## PR #261 review response (approved; five P2 nits, no P0/P1)
- P2-1 float sentinel and P2-2 `assert`/`ValueError` fixed (branch on `scale_estimated`; `PolarisValidationError`).
- P2-4 run, not filed (ROUTINE step 12): **Polaris alone, 30,000 rows, same 15-penalty cell, one Newton start — MEASUREMENT (own criterion), NOT parity, tier-1 box, no oracle:** converged, 10 iterations, 12 penalised fits, relative projected gradient 0.868 x `epsilon_rel`, 39.9 s wall, dev.expl 0.0906, scale 1.288. It shows Polaris reaches its own criterion at the plan's row count; it does NOT make the "production-like size" DoD item met (no `mgcv` side exists at that size: plain `gam()` did not finish; `bam(discrete=TRUE)` is outside the verified subset).
- P2-5 perf: CI "Perf (head-vs-main regression)" green per the reviewer; the appended row is for a commit with no hot-path change (new modules only plus three optional dataclass fields), so no creep is expected or claimed beyond that CI result.
- P2-3 (per-term edf gate is ADR-221's `edf_total` gate of 1): accepted, not built — a derived per-term bound is a candidate for P5's report; observed 6.4e-03 / 2.9e-02.
