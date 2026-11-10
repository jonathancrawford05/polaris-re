# Dev session log — 2026-11-10 — GAM dashboard Slice S3 (amount basis, sharp truth, bam non-PD hint)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`. **Plan:** `docs/PLAN_gam_dashboard_stabilise_retire.md` (S3). **ADR:** ADR-267 (PROPOSED). **Branch used:** `claude/dreamy-galileo-vdnad3`.
**PR title class:** `harness(mgcv-parity): ...` — MEASUREMENT / closed-form truth only; no mgcv comparison.
**Box vs repo:** box names no epic; repo pointer: S2 done, next S3. Agree. (The box says to "install R + mgcv" at step 2; apt needed `apt-get update` first.)

## Provenance
Claim sentence: *The data generator computes `MI_x(y)` from a closed logistic step law in age; `improvement_surface` computes it from the HGAM fitted to a draw of that data; compared on MI per cell and band coverage.* Per column: `mi_age_year` INDEPENDENT (formula vs fit), `band_coverage` INDEPENDENT — closed-form truth, NOT `mgcv` parity. Amount-basis scale invariance: both sides Polaris, MEASUREMENT (own criterion). The one tier-1 `mgcv` run (apt R 4.3.3 / mgcv 1.9.1) is a structure hypothesis, not a number committed anywhere but the ledger, labelled.

## Gap Before / Gap After
Before: `amount` basis not wired; only a smooth bilinear truth tested; `bam` non-PD refusal unexplained to users. After: amount wired; sharp truth NOT recovered by the default formula and the saturation flag is silent about it (6 of 26 unflagged misses); non-PD hint added. No mgcv gap in scope.

## Hypotheses Tried (ledger rows 2026-11-10)
1. Default formula recovers a sharp step, or the flag says when not — FALSIFIED (pre-registered property fails). 2. Post-hoc: `ti` margins are the limit — SUPPORTED on 10 seeds (0 of 20 unflagged misses). 3. Amount basis scale-invariant to 1e-6 — bound MISSED (6.55e-5); mgcv tier 1 also not exactly invariant. A pre-registered se-ratio bound was an algebra error of mine (se is invariant, not x sqrt F) and was dropped.

## Oracle Version
Tier 1 local apt R: R 4.3.3 / mgcv 1.9.1 (as expected). No CI dispatch, no digest; no number committed from tier 1 beyond a labelled ledger hypothesis.

## Baseline (full suite, `pytest tests/ -m "not slow"`, no `-x`, with R installed, with this session's changes)
**5 failed, 4262 passed, 22 skipped, 152 deselected, 1 xfailed** in 13m12s. The 5 failures are the standing ones (missing `data/mortality_tables/*.csv`: 4 in `tests/test_synthetic_block.py`, 1 `test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface`), confirmed failing on the stashed tree too. `tests/qa/`: 85 passed, 9 skipped (goldens byte-identical).

## Perf / mypy
perf row appended (ADR-177; src touched, not a conformance-only change). mypy is CI's job.
