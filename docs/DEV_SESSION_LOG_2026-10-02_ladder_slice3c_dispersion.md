# Dev session log — 2026-10-02 — ladder slice 3c: exposed dispersion + two-stage workflow

**Branch:** `claude/intelligent-hamilton-saja59` (draft PR). **PR title class:** `feat(mgcv-parity)` — lands INDEPENDENT comparisons (one DISAGREES, registered as slice 3d).

## Claim sentence (written before the code)
See ADR-238 / `DISPERSION_TWO_STAGE_CLAIM_SENTENCE`.

## Routine notes
Box and ROUTINE file agree on fact. Box says epic "at ADR-207"; CONTINUATION shows the live frontier is the capability ladder (ADR-237 done), next = slice 3c per work-selection rule. apt install needed `apt-get update` first (first attempt 404'd).

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt), `OPENBLAS_NUM_THREADS=1`. Tier 2: unavailable (`docker` binary, no daemon). Tier 3: R 4.6.1 / mgcv 1.9.4, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 36950897107.

## Baseline
`make test` (R installed, run while I was editing — so contaminated): 6 failures. 5 are standing (missing mortality tables/ILEC loaders; reproduced on a clean stash). The 6th, `test_measurement_provenance::test_check_passes_on_the_current_repository`, was MY change: `gam_family.py` is in the unconditional-coverage study's closure. Re-stamped `--assert` with a note (additive accessor). After: 85 passed 9 skipped (`tests/qa`), non-slow suite green except the 5 standing.

## Gap Before
No dispersion exposed; no comparison existed. Slice 3b/7/7b agreed on other draws (tier 3).

## Hypotheses Tried
1. *`m$scale` is Fletcher, not Pearson/deviance.* HELD (tier 3 `9.1e-08` vs `9.5e-03`/`3.8e-03`).
2. *The default single-start joint free-scale fit agrees with mgcv on a fresh draw.* REFUTED: `eta` 0.2864, `edf` -5.614 (tier 1 and 3). Own-criterion scoring at both points: mgcv's lower.
3. *`multistart=True` reaches mgcv's basin.* HELD: `eta` 1.737e-06. No new constant.
4. *Two-stage chain reproduces mgcv's chain.* HELD: `2.29e-06` / `2.50e-06`.

## Gap After (tier 3)
Dispersion `9.136e-08`; stage-1 phi `1.866e-08`; stage-2 `eta` `2.292e-06`; joint multistart `1.737e-06`; **joint single start `0.2864` (open — slice 3d)**.

## Provenance
| column | left | right | class |
|---|---|---|---|
| joint eta/edf (multistart; single start) | `fit_polaris_gam(quasipoisson)` | mgcv free-sp REML `m$linear.predictors` | INDEPENDENT |
| dispersion Fletcher vs `m$scale` | Polaris formula on Polaris's own fit | mgcv's own `m$scale` | INDEPENDENT |
| Pearson / deviance | Polaris on its fit | probe formula on mgcv's fit | INDEPENDENT |
| stage-1 phi | Polaris Pearson on own poisson fit | probe Pearson on mgcv's poisson fit | INDEPENDENT |
| stage-2 eta/edf (own phi; supplied phi) | `fit_polaris_gam(poisson, gamma=phi)` | mgcv `quasipoisson(scale=phi)` | INDEPENDENT (phi a supplied input in the second row) |
| two-stage vs joint gap | within-side | within-side | reported, not compared |
Formula identification of Fletcher on mgcv's own fit: NOT parity evidence.

## Follow-ups
Slice 3d registered (PLAN). Optional: a blocking CI gate for this probe once a second tier-3 reading exists. perf row appended (production files touched).

## Addendum — slice 3d (same PR, user-directed)
Hypothesis supplied by the user from reading mgcv: mgcv uses one data-based start (`initial.spg`), not multistart. I re-read `initial.sp`/`initial.spg` locally, implemented `gam_initial_sp`, one change (`initial_sp_start` opt-in). Tier 1: slice-3c draw `eta` 9.0e-06; slice-3b draw `1.5e-05`. Tier 3 (run 37005713761, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`): `1.907e-06` / `4.543e-06`. **Provenance:** INDEPENDENT (start computed from data/design/penalties only). **Caveat:** the 3b draw already agreed with the centre start, so it is a no-regression check. **Not done:** default flip (slice 3e). Not tested: mgcv's log-scale-in-search and Newton safeguards.
