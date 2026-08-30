# Session log — 2026-08-29 — Slice 5d: the free-sp residual is optimiser convergence

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5d — `docs/PLAN_mgcv_parity_engine.md`, registered 2026-08-29 (ADR-210,
same day). The routine's "next unchecked slice" rule selected it — slice 6 stays
blocked until 5d resolves.
**PR:** this branch (`claude/intelligent-hamilton-jj8yco`), draft.
**ADR:** ADR-211.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle: `apt-get install r-base-core r-cran-mgcv
  r-cran-jsonlite` failed on stale package-index 404s first (the same
  recurring transient prior sessions record); `apt-get update -qq` fixed it.
  Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the routine's expected
  apt versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for R invocations, per the routine's
  existing convention.
- Regenerated `data/mortality_tables/*.csv` (`scripts/convert_soa_tables.py`)
  — the standing, generated-not-committed environment gap prior sessions also
  hit; CIA 2014 tables remain unavailable via `pymort`, a known standing gap
  unrelated to this session.
- `uv run pytest tests/ -q -m "not slow"` baseline (before any code change,
  after the mortality-table regen): **3499 passed, 8 skipped, 126 deselected,
  0 failed** (567.79s). Compared against the last parity session's baseline
  (ADR-210, 2026-08-29: 3495 passed, 3 skipped) — the delta (+4 passed, +5
  skipped) is consistent with intervening merges (`f96a52c` added
  `test_gam_reml_optimize_conformance.py`); no new or changed failure, so
  PROCEED per the routine's own rule.

## Gap Before

PLAN slice 5d's own registered gap, measured directly rather than only
inferred from ADR-210's stored figures — this is itself where the session's
first finding came from:

- ADR-210's own free-`sp` N=4 residual: `max_abs_log10_sp_diff` = **0.7560**
  (tier 1) / **1.0996** (tier 3) — the SAME measurement, two different
  readings.
- ADR-210's own discriminating check (tier 1 only): our own criterion scores
  Python's own optimum WORSE than `mgcv`'s point (`612.6630` vs `612.6108`,
  delta `+0.0523`) — an optimiser-convergence signature, not re-confirmed at
  tier 3 in that session.
- Two live hypotheses registered: (1) optimiser convergence precision on a
  weakly-identified `lambda`; (2) a genuinely multi-modal surface where
  `mgcv`'s own Newton-based optimiser reaches somewhere ours cannot.

**Tier and digest:** ADR-210's numbers above are tier 1 (R 4.3.3/mgcv 1.9.1,
local apt) and tier 3 (oracle `sha256:0d54c192…` build 8, CI run 33267879635).

## The cheap first step, and what it actually found

Slice 5d named a cheap first step: re-run the discriminator at tier 3, since
ADR-210's own reading was tier 1 only. Doing that first required re-drawing
the fixture fresh (tier 1, local), which surfaced something the slice did not
anticipate before any R dispatch was spent:

1. Re-drew `gam_multiterm_free_sp_probe.R`'s fixture fresh: `mgcv`'s own
   selection reproduced ADR-208/210's own reading to the printed digit
   (`log10(sp) = [6.696, 9.872, 3.292, 3.029]`) — the data draw is perfectly
   stable across sessions.
2. Ran `fit_free_sp_case` on that SAME fixture three times (separate process
   invocations, `OPENBLAS_NUM_THREADS` unset): bit-identical every time
   (`log10(sp)=[6.996, 8.773, 3.280, 3.053]`, `score=612.6759596253515`).
   Not run-to-run randomness — the search has none.
3. Varied `OPENBLAS_NUM_THREADS` on the identical fixture: **1 thread →
   `log10(sp)[by-term]=9.116`, score `612.663047`** (reproduces ADR-210's own
   tier-1 reading to the digit); **2 threads → `8.519`**; **4 threads (this
   container's unset default) → `8.773`, score `612.675960`** (reproduces a
   `max_abs_log10_sp_diff` of `1.0996` — ADR-210's own tier-3 reading — without
   touching R at all).
4. Control: `penalized_fit_and_score` at `mgcv`'s own FIXED `log10(sp)` (no
   search) across the same thread counts: `612.6107604228214` (1 thread) vs
   `612.6107604232177` (4 threads) — `~4e-10`, consistent with ADR-210's
   float-precision fixed-`sp` finding. **The criterion is thread-independent;
   the search is not.**

This fully explains ADR-210's own tier-1-vs-tier-3 inconsistency: those two
readings were taken in environments with different effective BLAS thread
counts, not a data-draw or criterion difference.

## The decisive discriminator: warm-starting at mgcv's own point

Wrote `scripts/gam_free_sp_warmstart_diagnostic.py` — re-run
`select_lambdas_continuous` a second time with `x0` = `mgcv`'s own selected
`log10(sp)`, and compare against the existing blind (bounds-centre) start.

**Tier 1** (`OPENBLAS_NUM_THREADS=1`):

```
mgcv's own log10(sp):        [6.695961 9.87212  3.291837 3.029185]
blind (default-start) fit:  log10(sp)=[6.912784 9.116095 3.359102 2.972364]  score=612.663047  converged=True
warm (start-at-mgcv) fit:   log10(sp)=[6.69596  9.872119 3.291836 3.029185]  score=612.610760  converged=True

SCORE GAP (blind - warm):        +0.052286
MAX ABS (warm log10(sp) - mgcv): 0.000001
```

**Tier 3** (CI run 33279913273, oracle `sha256:0d54c192…` build 8, R 4.6.1 /
mgcv 1.9.4, same thread pin):

```
mgcv's own log10(sp):        [6.695961 9.87212  3.291837 3.029185]
blind (default-start) fit:  log10(sp)=[6.565093 8.71847  3.287554 3.012677]  score=612.641622  converged=False
warm (start-at-mgcv) fit:   log10(sp)=[6.696071 9.872214 3.291849 3.029269]  score=612.610760  converged=True

SCORE GAP (blind - warm):        +0.030862
MAX ABS (warm log10(sp) - mgcv): 0.000109
```

**Reading, confirmed at both tiers:**

1. **Hypothesis 2 REFUTED.** Started at `mgcv`'s own point, our optimiser
   stays there (within `1e-6` tier 1 / `1.09e-4` tier 3) at a score better
   than the blind start reaches. `mgcv`'s point is a genuine, reachable
   optimum of our own (ADR-210-corrected) criterion — not somewhere
   structurally unreachable.
2. **Hypothesis 1 CONFIRMED**, with a mechanism, not just an inference. The
   blind default start's own converged point moves substantially with
   nothing but the environment's BLAS thread count, and at tier 3 — a
   different host than this session's own container, at the SAME pinned
   thread count — it reaches yet a THIRD point that fails SciPy's own
   convergence check outright. Two independent hosts landing in two
   different places (one non-converging) on the identical algorithm and
   pinned thread count is a second, independent confirmation, not a
   weakening of the finding.

A blind, non-cheating multi-start check (bounds-centre + 8 uniform-random
starts in `[-2,11]^4`, tier 1, `OPENBLAS_NUM_THREADS=1`, no information from
`mgcv`) reached as low as `612.6149` in 9 tries — closer than the single
blind default's `612.6630` but short of `mgcv`'s reachable `612.6108`, and 2
of 9 far-corner starts failed to converge outright (`~636.7`, at a search
bound). A few extra starts help; they do not by themselves guarantee the true
optimum within a small, fixed budget.

## Provenance (ADR-193)

**Claim sentence:** `select_lambdas_continuous` computes its own converged
`log10(lambda)` and REML score from a supplied starting point, on the
design/penalty blocks `gam_model.assemble_model_design` builds; the
warm-start variant differs only in `x0`, read from `mgcv`'s own free-`sp`
selection; compared on `log10(sp)` and the REML score, both Python-computed.

**Per-quantity classification:**

| Quantity | Producer(s) | Provenance |
|---|---|---|
| Blind-start `log10(sp)`/score (`FREE_SP_MODEL_CLAIM`, unchanged) | `select_lambdas_continuous` (blind) vs `mgcv`'s own free-sp `gam()` fit | **INDEPENDENT** (unchanged from ADR-208/210) |
| Warm-start `log10(sp)`/score | `select_lambdas_continuous`, `x0` = `mgcv`'s own selection | **TRANSPORT-adjacent / DIAGNOSTIC** — the mechanical test fails on sight (`mgcv`'s own output is an input to this call). Never folded into `FREE_SP_MODEL_CLAIM`. Same status as `gam_multiterm_sp_delta_probe.R`. |
| BLAS-thread-count table | `select_lambdas_continuous`/`penalized_fit_and_score` at varying `OPENBLAS_NUM_THREADS`, no `mgcv` involved | Not a comparison against `mgcv` at all — an internal reproducibility measurement of our own code. |

A gap stated without provenance is not a gap statement (routine's own DELIVER
requirement): the warm-start reading is real, useful evidence about our own
criterion's landscape, but it is diagnostic, never parity evidence, and the
docs above say so explicitly everywhere it is cited.

## Gap After

- The free-`sp` N=4 gap is now **localised and mechanized**, not merely
  re-measured: it is `select_lambdas_continuous`'s own default single-start
  convergence precision on a weakly-identified direction (the by-term's own
  `lambda`), not a remaining criterion defect (already closed to float
  precision at fixed `sp`, ADR-210) and not an unreachable `mgcv` optimum.
- The official `FREE_SP_MODEL_CLAIM` comparison itself still reads
  `max_abs_log10_sp_diff=1.1536` at tier 3 this run (with threads now
  pinned) — **this is not a new, worse number to chase**; it is the same
  already-diagnosed blind-start artifact (the same blind fit read by both
  the official comparison and the warm-start diagnostic in this run,
  cross-checked to agree).
- **Slice 6 is unblocked.**

## Hypotheses tried (including what did not pan out)

1. **BLAS thread count as the explanation for the tier-1/tier-3
   inconsistency** — CONFIRMED on the first check (varying
   `OPENBLAS_NUM_THREADS` alone reproduces both ADR-210 readings exactly).
2. **Warm start at `mgcv`'s point as the decisive hypothesis-1-vs-2
   discriminator** — CONFIRMED at both tiers on the first attempt; no
   dead ends to record here.
3. **Blind multi-start (9 starts) as a practical fix** — TRIED, partial:
   improves on the single default start but does not close the gap in 9
   tries, and 2 of 9 starts fail outright. Recorded as a data point for
   slice 5e, not adopted as a fix in this session.

No hypothesis in this session was tried and abandoned without result — both
of slice 5d's own registered hypotheses resolved on the first or second
measurement, which is itself worth naming honestly rather than padding with
additional untried ideas.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt). Tier 3: R 4.6.1 / mgcv 1.9.4,
oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8), CI run [33279913273](https://github.com/jonathancrawford05/polaris-re/actions/runs/33279913273).

## What was built

- `scripts/gam_free_sp_warmstart_diagnostic.py` — new, diagnostic script (see
  Provenance). No new production code. **Round 2 review [P1-1]:** initially
  declared its own DIAGNOSTIC status in prose only (five places); now
  declares `WARM_START_CLAIM` (`ComparedQuantity` per quantity, TRANSPORT
  provenance) and prints `evidence_markdown(WARM_START_CLAIM)` instead of a
  hand-written headline, matching `scripts/reml_continuous_optimizer_probe.py`'s
  own precedent.
- `.github/workflows/mgcv-conformance.yml`: `OPENBLAS_NUM_THREADS: "1"` added,
  scoped to the `compare` job's own `env:` (round 1 [P2-2] moved this from an
  initial workflow-level placement — the R oracle's own job runs inside
  `docker run`, which does not inherit host env, so a workflow-level pin
  there would be a no-op; the R oracle side has pinned this since ADR-189
  amendment 2, nothing pinned the Python side); a new step running the
  diagnostic against job 1's existing `gam_multiterm_free_sp_probe.json`
  artefact (no new R script); the new script's path added to the workflow's
  own path-filter list.

## Quality gate

- `uv run ruff format src/ tests/ scripts/` — no changes needed to touched
  files (`scripts/gam_free_sp_warmstart_diagnostic.py` only).
- `uv run ruff check src/ tests/ scripts/` — 12 pre-existing errors in two
  unrelated files (`scripts/train_ml_assumptions.py`,
  `scripts/validate_tables.py`), confirmed pre-existing (present with no
  local changes applied) and out of this session's scope; the new file
  itself is clean.
- `uv run pytest tests/ -q -m "not slow"` — **3499 passed, 8 skipped, 126
  deselected, 0 failed** (567.79s, `OPENBLAS_NUM_THREADS=1`) — same as the
  baseline above; no regression from this session's changes (docs + one new
  diagnostic script + one workflow edit — no production module touched).
- `uv run pytest tests/qa/ -v --tb=short` — **94 passed** (102.43s).
  `tests/qa/golden_outputs/` byte-identical (no production code changed).
- Tier-3 CI dispatch (`mgcv-conformance.yml`, run 33279913273): **completed,
  conclusion success**, both jobs. Required levels 1-3 of the ten-cell suite
  still agree (no regression from the new step or the thread-count pin).

## Deliver

- Commit `9c9010b` — the ADR-211 change set (docs + new script + workflow
  edit), pushed to `claude/intelligent-hamilton-jj8yco` before the tier-3
  dispatch (a docs-and-diagnostic-only change, safe to land ahead of the
  full local suite finishing).
- This session log; `docs/DECISIONS.md` ADR-211; `docs/CONFORMANCE_LEDGER.md`
  four new rows; `docs/CONTINUATION_mgcv_parity_engine.md` status block and
  Open Questions updated; `docs/PLAN_mgcv_parity_engine.md` slice 5d marked
  DONE, slice 5e registered, slice 6 marked UNBLOCKED;
  `docs/PRODUCT_DIRECTION_2026-07-24.md` harvest entry appended (1st-order:
  the mgcv-parity epic's own critical path; the `OPENBLAS_NUM_THREADS` pin
  and slice 5e registration).
- `perf/history.jsonl` row appended in a separate, small commit (ADR-177) —
  see that commit for the reading.
- PR title: `feat(mgcv-parity): slice 5d — the free-sp residual is optimiser
  convergence, not criterion or reachability; slice 6 unblocked` — an
  INDEPENDENT comparison (the warm-start discriminator's REFUTATION of
  hypothesis 2, and the BLAS-thread-count table, both genuine findings about
  our own code) landed this slice, so `feat`, not `harness`.
