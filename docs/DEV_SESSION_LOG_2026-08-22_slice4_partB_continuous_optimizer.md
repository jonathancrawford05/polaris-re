# Dev Session Log — 2026-08-22 (slice 4, part B — the continuous outer search)

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine.
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`. Backlog item 3,
  "Slice 4 part B — the N-dimensional outer search," named as the epic's next piece of
  work since ADR-197's resolution, and ADR-198 (2026-08-21) registered the decisive test
  this slice runs.
- **Scope decision:** ADR-198 named two tests to discriminate grid quantisation from a
  remaining criterion gap; test 2 ("the continuous optimiser itself") is what PLAN slice 4
  part B has always specified building. This session built and ran it. Not attempted:
  extending the search to more than 2 penalty blocks (needs a multi-term mgcv-native
  model, slice 5 onward), and the maintainer-reserved cheaper pre-test (re-run the grid at
  `refine_step=0.05`) — the decisive test made the pre-test redundant once it confirmed
  the hypothesis directly.
- **Branch:** `claude/zealous-mendel-n6v2p0`.

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `apt-get update` (stale index, needed first —
  unrelated `deadsnakes`/`ondrej` PPA 403s through the environment's proxy, main Ubuntu
  archive fine), then `r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 / mgcv 1.9.1**
  — matches the routine's documented expectation exactly, no version drift to log.
  `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- Read, in full: `docs/ROUTINE_MGCV_PARITY.md`, `docs/VERIFICATION_STANDARD.md`,
  `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`,
  `docs/CONFORMANCE_LEDGER.md`, CLAUDE.md, `docs/DECISIONS.md` (ADR-189 + both
  amendments, ADR-190, ADR-191, ADR-192, ADR-193, and ADR-196/197/198 for slice-4
  context), `docs/RUNBOOK_mgcv_conformance.md`.
- Environment note: the designated branch (`claude/zealous-mendel-n6v2p0`) was cut fresh
  from `main` after PR #204 merged (confirmed via the GitHub API: PR #204 `merged: true`,
  `merged_at: 2026-08-22T01:21:21Z`, and `origin/main` and this branch's HEAD are the
  identical commit `0ffb963`) — no "already-merged designated branch" handling needed,
  this is simply a fresh start.

## Baseline and end state

| | |
|---|---|
| Baseline (`pytest -m "not slow"`, before touching code, R present) | **3309 passed, 5 failed, 22 skipped, 126 deselected** — matches PR #204's own last-known baseline exactly |
| The 5 failures | Pre-existing `data/mortality_tables/*.csv`-absent root cause, unrelated to this epic |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical, both before and after |
| End state (`pytest -m "not slow"`, after) | **3319 passed, 5 failed (same), 22 skipped (same), 126 deselected** — the 10-pass increase is exactly this session's new tests (`test_gam_reml_optimize.py`) |
| `ruff format` / `ruff check` on new/changed files | Clean |
| `mypy` on new files | One pre-existing baseline warning (`scipy.optimize`/`scipy.linalg` missing stubs — identical to `gam_fit.py`'s own existing warning), no new errors |

## Gap Before

Slice 4 part A (the REML criterion) was DONE and verified; no search over that criterion
existed anywhere. `experience_gam_penalized.select_lambdas_reml`'s 0.25-decade grid is the
only outer search in the codebase, and it is deliberately 2-D (ADR-186). ADR-198
(2026-08-21) measured, on the ten-cell suite's four free-`sp` cells, that the post-fix
residual against `mgcv`'s own selection sits everywhere inside half the grid's own
refinement step:

| cell | `max_abs_log10_sp_diff` (tier 3, post ADR-197 fix) |
|---|---:|
| `l2-free-sp` | 0.0645 |
| `l2-free-sp-factors` | 0.0791 |
| `l2-free-sp-kb` | 0.1048 |
| `l5-gamma` | 0.0776 |

against a half grid-step of 0.125 — a hypothesis ("this is grid quantisation"), not a
result, with the continuous search named as the decisive test. This is the number this
session is judged against.

**Tier and digest:** tier 3, R 4.6.1 / mgcv 1.9.4, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8` (build 8), run
32204739991 (ADR-197's resolution confirmation — the last tier-3 measurement of these four
cells, unchanged since; this session ran nothing that would move them).

## Iterate

**Hypothesis 1 (ADR-198's own, tested directly):** a continuous (quasi-Newton) search on
the identical criterion, with no grid to round to, will drive `max_abs_log10_sp_diff`
toward its own convergence tolerance rather than leaving it near 0.1.

**The one change:** built `gam_reml_optimize.select_lambdas_continuous` (SciPy L-BFGS-B,
finite-difference gradient, on `gam_fit.penalized_irls_general` +
`gam_reml.reml_score_general` — no new fitting or scoring formula) and ran it on the same
four cells, `gtol=1e-8`.

**Re-measured (tier 1):**

| cell | grid (tier 3, ADR-198) | continuous (tier 1, this session) |
|---|---:|---:|
| `l2-free-sp` | 0.0645 | 5.002e-04 |
| `l2-free-sp-factors` | 0.0791 | 4.393e-05 |
| `l2-free-sp-kb` | 0.1048 | 5.429e-04 |
| `l5-gamma` | 0.0776 | 7.283e-04 |

**Verdict: HYPOTHESIS CONFIRMED, decisively, on the first pass — no further hypotheses
needed.** Every cell's continuous residual is 2-3 orders of magnitude smaller than the
grid's, `converged=True` on all four (27-48 SciPy function evaluations), landing at the
search's own convergence floor rather than anywhere near 0.1. Recorded as ADR-199,
`docs/CONFORMANCE_LEDGER.md`.

**Stop condition reached:** "the gap closed, with a derivation for why the fix is right"
— ADR-198's own registered mechanism (grid quantisation) is exactly what a continuous
search removing the grid should fix, and it did, on every cell, by the predicted order of
magnitude.

## Gap After

**Tier 1** (R 4.3.3 / mgcv 1.9.1, this session): `max_abs_log10_sp_diff` (continuous)
5.002e-04 / 4.393e-05 / 5.429e-04 / 7.283e-04, all four `converged=True`.

**Tier 3: not yet measured as of this log's initial commit.** Per the routine's
no-magnitude-carve-out rule (ADR-190 decision 5), the size of this reduction does not
exempt it from tier-3 confirmation — dispatched via `workflow_dispatch` on this session's
push; see the follow-up commit/PR update for the run ID and whether the tier-1 reading
holds identically, the pattern every other measurement in this epic has followed.

Levels 1-3 and 5 of the ten-cell suite are unaffected by this session (no production code
changed) and were not re-run; level 4 is untouched and unrelated (ADR-190's separate
`dw/drho` gap).

## Provenance (ADR-193)

One new `VerificationClaim`, `CONTINUOUS_LAMBDA_CLAIM`
(`gam_reml_optimize_conformance.py`):

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `max_abs_log10_sp_diff` (continuous search) | `gam_reml_optimize.select_lambdas_continuous` — takes a design and penalty blocks, never an `mgcv`-payload-shaped argument, never called with `mgcv`'s own coefficients/score/selection at any point in the search | `mgcv`'s own free-`sp` selection, read from `mgcv_reference.json` — `mgcv`'s own continuous REML optimiser (`gam(..., method="REML")` with free `sp`) | INDEPENDENT |
| `edf_total` (continuous search) | `gam_fit.effective_degrees_of_freedom` at `select_lambdas_continuous`'s own selected `log_lambda` | `mgcv`'s `edf.total` at its own free-`sp` REML fit | INDEPENDENT |

The mechanical test applied to the producer's signature: `select_lambdas_continuous(y, x,
family, penalty_blocks, ...)` accepts no R-payload-shaped argument, and nothing in its
search loop reads `mgcv`'s output — the optimizer converges purely against
`reml_score_general`, which is itself independently built on `y`/`x`/`family`/`penalty`.
`mgcv`'s side is read from the ten-cell suite's already-committed `mgcv_reference.json`,
the identical source the suite's own already-INDEPENDENT `max_abs_log10_sp_diff` metric
reads (`docs/VERIFICATION_STANDARD.md` §5). This is a genuine INDEPENDENT parity
comparison, the same class as levels 1-5 and slice 4 part A's `REML_SCORE_CLAIM` — not a
harness slice.

The grid's own `max_abs_log10_sp_diff` figures quoted in the tables above are **read from
the already-committed `python_reference.json`/ADR-198**, not recomputed by this session —
context for the comparison, not a new measurement.

## Hypotheses Tried

Only one — it held on the first pass, so no further hypotheses were needed (the routine's
own "never burn the whole session on hypothesis 1" guidance did not apply; the opposite
situation, a hypothesis confirmed decisively and immediately, is an equally valid stop
condition).

## Oracle Version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt) — matches the routine's documented expectation,
no drift. Tier 3: pending as of this log's initial commit; oracle digest
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8` (build 8), the
same digest every measurement in this epic has used since ADR-189 amendment 2.
