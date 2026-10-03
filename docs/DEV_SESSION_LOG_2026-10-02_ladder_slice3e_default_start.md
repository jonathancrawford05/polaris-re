# Dev session log — 2026-10-02 — ladder slice 3e: default vs seeded start on every free-scale cell

**Branch:** `claude/intelligent-hamilton-6m31s5` (draft PR). **PR title class:** `feat(mgcv-parity)` — lands INDEPENDENT comparisons; one DISAGREES (a result, registered as slice 3f).

## Claim sentence (written before the code)
See ADR-240 / `DEFAULT_START_STUDY_CLAIM`.

## Routine notes
Box says epic "at ADR-207"; CONTINUATION shows the live frontier is the ladder; next = slice 3e (ADR-239). Box and ROUTINE file agree on fact. `apt-get update` needed before the R install.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt), `OPENBLAS_NUM_THREADS=1`. Tier 2: unavailable (no docker daemon). Tier 3: R 4.6.1 / mgcv 1.9.4, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 37071666519 (tier 1 identical at every printed digit).

## Baseline
`pytest tests/ -m "not slow"` with R installed and mortality tables converted (CIA tables unavailable in this environment): 3844 passed, 3 skipped, 0 failed. An earlier `-x` run stopped at `test_loaded_ilec_feeds_tensor_mi_surface`, a missing-table failure that reproduces on a clean stash.

## Gap Before
Seeded start agreed on 3b and 3c draws only; nothing known about the other free-scale cells. Default fails 3c (`eta` 0.2864).

## Hypotheses Tried
1. *Seeded start meets ADR-221 on every free-scale cell.* REFUTED: gaussian L1 `eta` 0.2107, `edf` -8.99, own score 180.84 vs 165.30, upper bound hit.
2. *Best of {centre, seeded} by own score agrees everywhere.* HELD on 6 draws (tier 1 and 3). Not shipped.
3. *The seeded L1 stall is premature convergence.* REFUTED at tier 1 only: restart from the endpoint does not move. `max_gtol_restarts` and the analytic gradient are unavailable for free scale, so mechanism untested.

## Gap After (tier 3)
Default: fails 3c (0.2864), agrees on the other five. Seeded: fails L1 (0.2107), agrees on the other five. Best-of-both: agrees on all six. Default unchanged.

## Provenance
| column | left | right | class |
|---|---|---|---|
| eta, edf_total per cell, per start | `fit_polaris_gam` (recipe only; start varied) | mgcv free-sp REML `m$linear.predictors` / `sum(m$edf)` | INDEPENDENT |
| log10(sp) diff, own REML score, at-bound | Polaris | mgcv sp / Polaris own | reported; score is within-side, not compared |
No ECHO or TRANSPORT columns. Headline derived with `evidence_markdown`.

## Follow-ups
Slice 3f registered (PLAN). No perf row: PR touches only `*_conformance.py` modules outside the perf import closure (ADR-177 amendment 2; check returned `[]`). Single draw per cell is a small sample.

## Maintainer decision (2026-10-03)
Keep both starts opt-in. Slices 3e/3f closed; no code change. Recorded in ADR-240 amendment 1.
