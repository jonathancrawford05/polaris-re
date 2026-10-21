# Session log 2026-10-21 — R4 `tp` (ADR-261)

**Branch:** `claude/dreamy-galileo-29h141`. **PR class:** `feat(mgcv-parity)` (INDEPENDENT comparisons). The registered box and the repo agreed; the box names no slice, the repo's pointer named R4.

## Oracle Version
Tier 1 (scratch): R 4.3.3 / mgcv 1.9.1 (apt, after `apt-get update`), `OPENBLAS_NUM_THREADS=1`. Tier 3 (every committed number): run `39522244188`, digest `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, R 4.6.1 / mgcv 1.9.4. Docker has no daemon here (tier 2 unavailable).

## Baseline (full suite, `make test`)
Before: 5 failed, 4170 passed, 22 skipped, 145 deselected. After: 5 failed, 4199 passed, 22 skipped, 145 deselected (+29 tests). The same five fail in both: `test_experience_loaders::test_loaded_ilec_feeds_tensor_mi_surface` and four `test_synthetic_block::TestCalibratedPremiums` (missing generated mortality tables in this container). `tests/qa/` goldens untouched (no pricing path calls the GAM fitter).

## Gap Before
`s(x)` refused by name; `tp` absent from the engine (coverage row L7). No metric to state: nothing existed to compare.

## Hypotheses Tried
1. mgcv truncates `Z'EZ` (constrain, then truncate) — REFUTED: sine 0.10-0.17 from `smoothCon`; also mgcv's returned vectors are not eigenvectors of `Z'EZ` (residual 0.24-0.93).
2. mgcv truncates the full `E`, then constrains (`UZ` = "U times Z") — CONFIRMED to 1e-14 on the subspace; with column order (negatives ascending, positives descending), `sqrt(n)` column norms and `scale.penalty`, element-wise match up to column sign on 16 of 20 cases.
3. Element-wise agreement as the criterion — ABANDONED: on `age_18_100_k10`/`grid_61_k20` spans agree (1e-13) but columns differ (gauge). Moved to a gauge-free criterion.
4. Fixed tolerance — REPLACED: `dur26_10` differs 2.9e-8 because mgcv's Lanczos truncation is that inexact; measured against an exact R eigensolve and the tolerance derived from it. First derivation (coefficient-space distance) was wrong (not the compared space); redone in design space.
5. `k = nu` S mismatch (0.99) — `scale.penalty` is gauge-dependent (pure scalar 165); compared up to it.
6. `fit_polaris_gam` hit the lower `log10(sp)` bound: mgcv's own optimum is `sp = 4.9e-3`; domain widened to -8 for tp models.

## Gap After / Provenance
| comparison | left producer | right producer | classification |
|---|---|---|---|
| `X` column space, `S` in common basis, `rank` (17 cases) | `gam_basis_tp.tp_basis(x, k)` (signature takes no mgcv output) | `smoothCon(s(x,bs="tp",k),absorb.cons=TRUE)` | INDEPENDENT |
| `mgcv vs exact` slack | R `eigen()` on mgcv's `Xu` | mgcv's own result | REFERENCE_INTERNAL (sets slack only) |
| formula cells (24): eta, edf_total, per-smooth edf, labels, bs.dim | `gam(formula string)` | `mgcv::gam(same string)` | INDEPENDENT |
| predict cells (2): held-out eta, se.fit | `fit.predict` | `predict.gam` | INDEPENDENT; lpmatrix col-space REPORTED only |
| wrong-recipe control | Polaris Z'EZ-first variant | smoothCon | negative control (must disagree; it does, 0 of 16 agree) |

Tier 3 results: Stage A 17/17 (space dist 2.9e-15..2.9e-8, rank diff 0); Stage B 24/24 and 2/2, max eta 6.4e-4, max |edf diff| 0.0135. Gap is closed for the one-covariate construct; not claimed for anything refused.

## Other
- `perf/history.jsonl`: one row appended (PR touches non-conformance `src/` modules). Creep verdict: `has_structural_creep: False` (peak MiB 33 -> 33); wall-time ratio 1.26 on the `project` probe, advisory, present without this row and no projection code touched.
- Existing assertions changed on purpose (lifted refusal, ADR-261 decision 6): `test_formula.py` bare-smooth test and `bs="tp"` list entry; `test_guide.py` refusal table; `test_formula_conformance.py` stand-in refusal now `bs="ps"`.
- Maintainer questions: Q-R4a, Q-R4b in the CONTINUATION.
- Follow-ups harvested: tp with `by=`/`select=TRUE` and tp as a `ti` margin are 2nd-order (NICE-TO-HAVE, no real-data formula needs them: the trial formulas are `cr`); kept as Q-R4a. `select=TRUE` with tp is being measured next (maintainer request).
