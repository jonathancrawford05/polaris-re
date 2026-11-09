# Dev session log — 2026-11-09 — GAM dashboard Slice S2 (the `slogdet` warnings)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`. **Active plan:** `docs/PLAN_gam_dashboard_stabilise_retire.md` (S2). **ADR:** ADR-266 (PROPOSED). **Branch used:** `claude/dreamy-galileo-7vtr0s`.
**PR title class:** `harness(mgcv-parity): ...` — MEASUREMENT only, no mgcv comparison.
**Box vs repo:** box names no epic; the repo's pointer says S1 merged, next S2/S3; S2 taken (plan order). No disagreement.

## What was built
`scripts/gam_slogdet_warning_study.py` (reproduction grid, `wide` argument for sparse tails), `scripts/gam_slogdet_locate.py` (maintainer-run locator, derived scalars only), ADR-266, ledger rows, CONTINUATION entry. No `src/` change, so no `perf/history.jsonl` row (ADR-177 amendment 1).

## Provenance
Claim sentence: *Polaris records every `slogdet` call and warning during its own fit; no second producer.* Every column (warnings, calls, sign, logdet, condition number) is MEASUREMENT (own criterion). Not INDEPENDENT, ECHO or TRANSPORT. No tier: no mgcv.

## Gap Before / Gap After
Before: two disagreeing records (warnings on every row-level `gam` fit; none on aggregated at default k). After: neither reproduced on synthetic data. No mgcv gap exists in this slice.

## Hypotheses Tried (all recorded in the ledger)
1. Default vs large k x row-level vs aggregated triggers them: 24 fits, 0 warnings. FALSIFIED as a sufficient cause on this generator.
2. Sparse tails (ages 0-120, exposure ~0 at edges): 24 fits, 0 warnings. FALSIFIED.
Pre-registered outcome applied: "not reproduced"; page unchanged; locator supplied for the maintainer's data. Stopped at two passes: further guesses (zero-weight blocks, duplicates, non-finite offsets) would be untested speculation about data the cloud does not have.
Side finding: `bam` non-PD refusals, 5 of 24 `bam` fits (see ADR-266).

## Oracle Version
Tier 1 local apt R installed (R 4.3.3 / mgcv 1.9.1; `apt-get update` needed first). **Not used.** No CI dispatch, no digest.

## Baseline (full suite, `pytest tests/ -m "not slow"`, no `-x`)
Full run on the pre-change tree (docs and scripts only were added afterwards): **5 failed, 4255 passed, 22 skipped, 147 deselected** in 10m31s, with R installed. The same 5 failures as the S1 log (`FileNotFoundError: Mortality table CSV not found`; environmental): `test_loaded_ilec_feeds_tensor_mi_surface` and four `test_synthetic_block.py::TestCalibratedPremiums` tests. Passed count is above S1's 4238 by the tests S1 added. `tests/qa/` is inside this run; no golden file touched (`git status` shows no change under `tests/qa/golden_outputs/`). The session adds no tests, so there was nothing to re-run after the change.
