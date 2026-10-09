# Dev session log — 2026-10-09 — GAM parity preview: Slice P5 (release the preview)

**Branch:** `claude/dreamy-galileo-k2tec2` (environment-designated); PR #262 (draft). **PR title class:** `feat(mgcv-parity)` for the guide-example prediction columns (INDEPENDENT); everything else in the PR is documentation, aggregation or tooling.
**Box vs repo:** the box names no epic; the repo's pointer named `PLAN_gam_parity_preview.md`, next slice P5. Repo followed; no conflict on fact.
**Perf:** one row appended (ADR-177): the PR edits `core/verification.py` and adds `gam/{example,guide_conformance}.py`, none exempt. Advisory wall-time ratio 2.2x on this box; MiB peak 33 -> 33, no structural creep.

## Baseline
No mortality tables here, so five environmental failures stand (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`). **Start of session** (`make test`, whole `tests/`, R installed): **5 failed, 4036 passed, 22 skipped, 145 deselected** — identical to the P4 log's "after". **After:** AFTER_COUNTS

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1, `LC_COLLATE=C`, `OPENBLAS_NUM_THREADS=1`. Tier 3 (every committed number): CI run **37924265628** (commit `ef5fb0b`), mgcv 1.9.4 / R 4.6.1, `LC_COLLATE=en_US.UTF-8`, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.

## Gap Before
No user documentation, no notebook, no single report: the preview's evidence was spread over four CI job summaries, hand-assembled in ADRs. The evidence headline said "one parity column" for a table with six. The guide's example did not exist as a compared cell.

## Gap After
`docs/GAM_USER_GUIDE.md`, `notebooks/gam_parity_preview.ipynb` and `docs/GAM_PARITY_REPORT.md` (generated, pinned to run 37924265628) exist; the guide's code blocks and the notebook cells are executed by tests. At tier 3: formula 15/15, summary + target-size 16/16, guide example 1/1, gauntlet 10/10, predict + `se.fit` 8/9 — the 1 is `gaussian_factor_by`, the rank-defect cell of ADR-249/250 (unchanged, refused by `gam()`).

## Hypotheses Tried
1. The guide's example, a new cell, meets the existing P1-P4 gates without new tolerance or solver work. HELD at tier 1 (first run) and tier 3, digits identical; no tolerance, constant or start strategy was touched.
2. Generating the report from the comparison scripts' own output (not retyping) is feasible within the CI `compare` job. HELD: refactor was `main` -> `build_report` returning `(text, agree, total)`; 14 s locally. The text is recovered from the job log (artifact download not needed).
No failed hypotheses to record; the one first-draft change was the example's data generator (interaction strength raised so `ti` is not on a plateau; before any oracle run).

## Provenance
- **Guide example prediction columns** (`GUIDE_CLAIM`, headline via `evidence_markdown`): left `predict_guide_example(fit: GamFit, newdata: GuideNewData)` — covariate keys only, projected at runtime (tested); right `predict.gam(m, newdata, se.fit=TRUE[, unconditional=TRUE])` on `gam(<same string>, method="REML")`. Link prediction, `se.fit` Vp, `se.fit` Vc, response + its `se.fit`: all **INDEPENDENT**. Gated: link (ADR-221 `eta`), `se.fit` Vp and Vc (ADR-250 relative); response reported.
- The same cell's fit/structure and `summary()` columns are `FORMULA_CLAIM` (6 INDEPENDENT) and `SUMMARY_CLAIM` (6 INDEPENDENT + `n` ECHO), already declared.
- **The report as a whole is an AGGREGATION** of those comparison modules' tables; its "N of M" counts their own `agrees` flags. It adds no compared quantity. The gauntlet section is the one-start Newton vs `mgcv` free-`sp` comparison (INDEPENDENT per its own claims).
- Tests in `tests/test_gam/test_guide.py` are executable-documentation / own-criterion tests; `test_compare_guide_predict_arithmetic_on_a_perturbed_reference` is a HARNESS test (Polaris vs itself, perturbed) and says so.

## Definition of done (PLAN P5)
- `docs/GAM_USER_GUIDE.md`: install, one worked example (fit, predict with SEs, summary), supported subset, refusal list: **MET** — `test_the_guide_code_blocks_run_in_order`, `test_every_refusal_in_the_guide_table_is_listed_and_refused`.
- `notebooks/gam_parity_preview.ipynb` running the same example: **MET** — `test_the_notebook_code_cells_run`.
- `scripts/gam_parity_report.py` -> `docs/GAM_PARITY_REPORT.md`, generated from the declared claims of P1-P4 plus the Wood gauntlet, headline by `evidence_markdown()`, pinned to its tier-3 run id and oracle digest: **MET** — run 37924265628; script refuses without `--run-id/--commit/--digest` (`test_the_report_refuses_to_run_without_a_digest`); missing probes print NOT MEASURED (`test_a_report_with_no_probes_says_not_measured_and_incomplete`). Note: the committed file is the run's log text, produced by the commit before the doc-only commits that followed it.
- `[judgement]` wording says "preview", names the subset, oracle version and tolerance, never an unqualified "mgcv-compatible": **MET (judgement)** — guide header, README section, `test_the_guide_says_preview_and_never_claims_general_compatibility`, `test_the_guide_states_the_tolerances_and_digest_the_report_uses` (pins the digest to the workflow's). For the maintainer to confirm.
- Exposure beyond Python put to the maintainer as a question with a recommendation: **MET** — CONTINUATION Q7, PR body.
- Epic-start commitment: P5 carries a user-facing deliverable and an INDEPENDENT comparison of its own: **MET** — the guide example (above).
- Q5 headline wording (maintainer-approved): **MET** — `evidence_headline` counts columns; `test_headline_counts_the_parity_columns_instead_of_saying_one`. Two existing assertions that pinned the old string were rewritten (listed in ADR-254 Decision 3).

## Maintainer questions
7 (exposure beyond Python — recommended: nothing yet, CLI first), 8 (Slice 9 before or after merge — recommended: merge as is, Slice 9 next; the checkpoint "before P5 states the limitation" was met by stating it as a refusal, size not re-measured), 9 (report as committed snapshot, refreshed by dispatch). Work that did not depend on them continued.

## Not done, and why
- Slice 9 (rank pivoting): one slice per session; registered, not run.
- The "second probe draw" for the factor-`by` limitation size: not run; the guide says the size was single-draw and is not re-measured. It would need R-side draws plus a tier-3 dispatch of a diagnostic and belongs with Slice 9.
