# Session log — 2026-09-06 — Slice 7h: the penalty quadratic form as a sum of squares, in production

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7h — `docs/PLAN_mgcv_parity_engine.md`, registered by ADR-222 amendment 2.
**Branch:** `claude/intelligent-hamilton-lo5adm` (environment-designated).
**ADR:** ADR-223.

**Gate reason:** scheduled routine run. `docs/PLAN_mgcv_parity_engine.md`'s next
unchecked slice was 7h, `REGISTERED, not started` — no fallback pick.

## Setup

- `uv sync --all-extras` — clean.
- Installed the tier-1 scratch oracle: `apt-get update -qq && apt-get install
  -y -qq r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 (2024-02-29) /
  mgcv 1.9.1** — the routine's expected apt versions, no drift.
- Read, in full, before writing code: `ROUTINE_MGCV_PARITY.md`,
  `PLAN_mgcv_parity_engine.md` (Anchors 1/2/8 and slice 7h's own section),
  `CONTINUATION_mgcv_parity_engine.md`'s status block and open questions,
  `CONFORMANCE_LEDGER.md`'s tail, `VERIFICATION_STANDARD.md`, `CLAUDE.md`,
  `DECISIONS.md` ADR-189/190/191/192/193 and the ADR-222 chain (amendments 1
  and 2, which registered this slice), `RUNBOOK_mgcv_conformance.md`.

## Baseline

`uv run pytest tests/ -m "not slow"` before any code change, R installed,
mortality tables generated (`scripts/convert_soa_tables.py --source pymort`,
a one-time environment step, unrelated to this slice): **3604 passed, 22
skipped, 126 deselected, 7 failed** — all 7 failures are either (a) the four
missing-mortality-table `FileNotFoundError`s (from before the tables were
generated; PROCEED — resolved by the one-time step, not a code issue) or (b)
the two tests this session's own change legitimately moves (see "Two
pre-existing tests, and why changing them was the correct call" below), or
(c) `test_gam_select_free_sp_conformance.py`'s gate-arithmetic test, likewise
addressed below. Verified against a clean stash: baseline WITHOUT this
session's changes shows only the four mortality-table failures — the other
three are new, and confirmed below to be a *consequence* of the change
rather than a defect in it, each with its own before/after measurement.

## Gap before

`gam_reml.reml_score_general` evaluated the penalized deviance's quadratic
term `beta^T S beta` as `coef @ (sum_j lambda_j penalty_blocks[j]) @ coef` —
forming the `lambda`-weighted sum first, then contracting. ADR-222 amendment
2 (previous session) measured that at this criterion's own selected
`lambda` spreads (thirteen decades on the target formula's N=7
`select=TRUE` structure) this cancels ~10 digits of `float64` precision,
carries `~1e-4` absolute error, and is DISCONTINUOUS in `coef` — so the
`~1e-15` differences `coef` acquires from BLAS thread-count/summation-order
move the score by `~1e-4` to `~1e-5`, and the outer optimiser's converged
point becomes environment-dependent. The candidate fix (`beta^T S_j beta =
||L_j^T beta||^2`, summed) was measured in a standalone diagnostic script
(`scripts/gam_penalty_sqrt_form_diagnostic.py`) but never wired into `src/`.

Production score thread-spread, measured this session before any change
(`penalized_fit_and_score`, freshly regenerated `probe7.json`,
`OPENBLAS_NUM_THREADS` {1,2,4} via `threadpool_limits`):

| point | max spread across 1/2/4 threads |
|---|---:|
| narrow (decade spread 2.0) | 1.364e-12 |
| wide (decade spread 11.0) | **5.183e-05** |
| `mgcv`'s own selected point (spread 12.9) | **7.250e-06** |

`SELECT_FREE_SP_MODEL_CLAIM` before (same fixture, 4 configurations):

| configuration | converged | agrees | max&#124;eta&#124; | edf_diff | max&#124;log10sp&#124; |
|---|---|---|---:|---:|---:|
| single-start | True | False | 0.4457 | 2.4216 | 5.1320 |
| multistart=9 | True | **True** | 0.00268 | -0.1106 | 1.4754 |
| single-start, analytic gradient | True | False | 0.0529 | 0.1904 | 1.7036 |
| multistart=9, analytic gradient | True | **True** | 0.00549 | -0.2583 | 5.1929 |

## Registered prediction (ADR-222 amendment 2's, carried into this slice)

*Evaluate `sum_j lambda_j ||L_j^T beta||^2` in production; expect ~9 orders of
cross-thread reproducibility on the dominant noise term, no accuracy gain
(slightly worse against `float128`), and every reading on a wide-`lambda`-
spread structure to move and need re-statement.*

## The one change

`gam_reml.penalty_block_square_roots(penalty_blocks)`: symmetric
eigendecomposition of each **individual, unscaled** block (never the
`lambda`-weighted sum), negative eigenvalues clipped, eigenvectors below
`1e-14` relative to the block's own largest eigenvalue dropped as that
block's own numerical null space. `reml_score_general` gained an optional
`penalty_sqrt_blocks` keyword (default `None` — computed fresh, so every
existing caller gets the corrected formula automatically) and now computes
the penalized deviance's quadratic term as `sum_j lambda_j *
sum((penalty_sqrt_blocks[j].T @ coef) ** 2)` instead of `coef @ penalty @
coef`. `log|X'WX+S|` is untouched (still built from the summed `penalty` —
ADR-222 amendment 2 measured this term thread-CLEAN already).

`gam_reml_optimize.select_lambdas_continuous` computes the square roots
**once**, before the search loop (`penalty_blocks` is fixed for the whole
search), and threads the result through every `penalized_fit_and_score`/
`penalized_fit_score_and_gradient` call: the finite-difference objective,
the analytic-gradient objective, the `max_gtol_restarts` residual probe, and
the final re-fit at the reported minimum. `penalized_fit_and_score` and
`penalized_fit_score_and_gradient` both gained the same optional keyword,
passed straight through. This is the module's own Definition of Done:
"computed once per fit, not per evaluation."

## Hypotheses tried

Only one — the registered prediction was tested directly, not approached by
elimination (the mechanism was already closed by ADR-222 amendment 2; this
slice ports the fix, it does not re-diagnose).

### Pass 1 — reproduce the diagnostic's own numbers, unaffected by this change

`scripts/gam_penalty_sqrt_form_diagnostic.py`, re-run against a freshly
regenerated `probe7.json` (same R script, tier 1): bit-identical in shape to
ADR-222 amendment 2's own table (this script re-implements both forms
itself and never calls `reml_score_general`, so it is unaffected by the
`src/` change — a useful cross-check that the fixture and oracle are
unchanged from the prior session):

```
point                      formed-S err   sqrt-form err   improvement
narrow (spread 2.0)           1.137e-13       5.627e-12          0.0x
wide (spread 11.0)            6.823e-05       1.989e-04          0.3x
mgcv point (12.9)             2.520e-05       5.447e-05          0.5x

And the thread axis on the same quantity:
point                       formed-S d    sqrt-form d
wide (spread 11.0)           1.037e-04      1.954e-13
mgcv point (12.9)            1.450e-05      1.137e-13
```

### Pass 2 — measure the actual production function, before vs after

`penalized_fit_and_score` (production), same fixture, same trial points,
thread spread:

| point | before | after | improvement |
|---|---:|---:|---:|
| narrow (2.0) | 1.364e-12 | 2.274e-13 | ~6x |
| wide (11.0) | **5.183e-05** | **6.821e-13** | ~76,000x |
| `mgcv` pt (12.9) | **7.250e-06** | **4.775e-12** | ~1,500x |

**Verdict: registered prediction HOLDS**, on the code that ships, not only
the isolated replica. `coef` is identical before/after at each thread count
(the IRLS fit does not depend on which score formula scores it — only the
scoring arithmetic changed), so this isolates the fix's own effect cleanly.

### Pass 3 — `SELECT_FREE_SP_MODEL_CLAIM`, before vs after (tier 1)

Same fixture, all four configurations `fit_select_free_sp_case`/
`compare_select_free_sp_case` exercise:

| configuration | before: conv / agrees / eta / edf | after: conv / agrees / eta / edf |
|---|---|---|
| single-start | True / False / 0.4457 / 2.42 | **False** / False / 0.4461 / 2.51 |
| multistart=9 | True / **True** / 0.00268 / -0.111 | True / **True** / 0.00547 / -0.261 |
| single-start, analytic gradient | True / False / 0.0529 / 0.190 | True / False / 0.0632 / 1.375 |
| multistart=9, analytic gradient | True / **True** / 0.00549 / -0.258 | True / **True** / 0.00545 / -0.255 |

**Verdict: every configuration's `agrees` outcome is UNCHANGED.** Individual
readings moved — `eta` by up to ~2x within the same tolerance band,
`log10(sp)` by whole decades on the already-known weakly-identified
direction, single-start's own `converged` flag flipped True→False — exactly
the "every committed reading… moves and must be RE-STATED, not assumed
stable" the routine anticipated, with nothing this epic relies on for
`agrees` reversing.

### Pass 4 — cost of caching (the module's own DoD line item)

200 repeated `penalized_fit_and_score` calls, N=7 structure, 1 BLAS thread:
precomputed-and-reused `12.95 ms/eval`; recomputed-every-call `15.20 ms/eval`
— `~2.24 ms/eval` (`~15%`) avoided per evaluation by caching at the search
level. A single-start search on this structure runs ~300-350 evaluations, so
caching saves on the order of a second of wall clock per search — a minor
win, reported because the DoD asks for it, not the slice's point.

## Two pre-existing tests, and why changing them was the correct call

**`tests/test_analytics/test_gam_reml_optimize.py::TestFiniteDiffStep`.**
`test_default_step_reports_spurious_convergence_on_the_near_flat_fixture`
asserted `norm(central-difference gradient at SciPy's default-step reported
minimum) > 0.1` — ADR-212's own defect demonstration. Post-fix, re-measured
(deterministic, re-run twice, bit-identical): `0.00849`. **Root-caused, not
merely observed:** ADR-212's own mechanism was noise in `beta^T S beta`
leaking into `coef` and, through it, the score — the identical cancellation
this slice removes, on a fixture whose own `lambda` search reaches a
comparable decade spread. Renamed to
`test_default_step_no_longer_needed_on_the_near_flat_fixture`, docstring
states the mechanism and cites this slice, assertion flipped to `< 0.05`
(matching the adjacent `test_finite_diff_step_default_avoids_the_spurious_convergence`,
which already asserted this shape for the production default step and still
passes unchanged). `_FINITE_DIFF_STEP` itself is untouched — out of scope;
PR #216's own review found it costs a digit of accuracy on a *different*,
well-conditioned fixture, so revisiting the production default needs its
own across-fixture measurement.

**`tests/test_analytics/test_gam_select_free_sp_conformance.py::test_compare_select_free_sp_case_agrees_is_now_eta_edf_not_log10_sp`.**
Its own live call to `fit_select_free_sp_case(recipe)` (a genuine outer
search, on a fixed small recipe, single-start default) went from
`converged=True` to `converged=False` post-fix — `agrees` requires
`both_converged`, so the test's own hand-built `close_payload` scenario
(designed to prove `agrees` reads eta/edf, not `log10(sp)`) failed on the
`converged` precondition alone, not on the gate arithmetic the test exists
to check. Confirmed this is the SAME environment/path-sensitivity class
ADR-211/212/218/222 already documented (SciPy's own line-search bookkeeping,
not fit quality: `eta` moved only 0.44561→0.44612, `edf` only by 0.1, the
score by 0.0045) — triggered here by an unrelated, correct formula change
rather than a thread-count change, and neither `multistart=True` nor
`analytic_gradient=True` converges cleanly either (both land at a
notably worse score with a block at the search bound — checked, not
assumed). The test's own docstring already states its purpose is "gate
arithmetic in isolation from the search"; `dataclasses.replace(fit,
converged=True)` decouples that precondition from the live search's known-
fragile flag, with a docstring explaining why, mirroring how ADR-197 treated
a baseline that moved for a derived, documented reason rather than being
silently widened.

Neither change touches `agrees`/`agrees_log10_sp`'s own definitions in
`gam_select_free_sp_conformance.py`, and neither weakens what either test
verifies — both are documented, root-caused, and reproducible.

## Quality gate

- `uv run ruff format` / `ruff check --fix` on every file this session
  touched — clean. (Running `ruff format` project-wide reformatted six
  unrelated, previously-unformatted diagnostic scripts from a prior
  session; reverted — out of scope for this slice.)
- `uv run pytest tests/test_analytics/test_gam_reml.py
  tests/test_analytics/test_gam_reml_optimize.py
  tests/test_analytics/test_gam_reml_gradient.py
  tests/test_analytics/test_gam_reml_appendix_b.py
  tests/test_analytics/test_gam_reml_optimize_conformance.py
  tests/test_analytics/test_gam_reml_conformance.py
  tests/test_analytics/test_gam_reml_production_check.py
  tests/test_analytics/test_gam_model.py
  tests/test_analytics/test_gam_model_conformance.py
  tests/test_analytics/test_gam_uncertainty.py
  tests/test_analytics/test_gam_select_free_sp_conformance.py` — **153
  passed**, R-gated end-to-end tests included and passing live.
- Full suite, `-m "not slow"`, `OPENBLAS_NUM_THREADS=1`: **[PENDING —
  running as this log is written; see addendum below for final counts.]**
- `tests/qa/` (golden gate): **[PENDING — see addendum.]**

## Definition of done

Recorded inline against `PLAN_mgcv_parity_engine.md` slice 7h:

- `[machine]` Score's cross-thread spread re-measured at all four spreads —
  **MET** (Pass 2 above; ADR-222 amendment 2's own diagnostic reproduced
  unchanged in Pass 1, since it doesn't call the production function).
- `[machine]` Square roots computed once per fit, not per evaluation —
  **MET** (wired in `select_lambdas_continuous`; cost measured, Pass 4).
- `[machine]` `SELECT_FREE_SP_MODEL_CLAIM` re-measured tier 1 AND tier 3 —
  **TIER 1 MET** (Pass 3). **TIER 3 NOT YET RUN** — registered as this
  session's own follow-up (see below); per `ROUTINE_MGCV_PARITY.md` the
  tier-1 table above is a hypothesis, not a committable number, until
  confirmed on the pinned digest.
- `[machine]` `tests/qa/golden_outputs/` byte-identical — **[PENDING, see
  addendum]**.
- `[judgement]` Reported as a REPRODUCIBILITY fix, never an accuracy one —
  **MET** (stated in the module docstring, the ADR, and here; the
  `float128` accuracy table is unchanged and slightly worse for the new
  form, exactly as ADR-222 amendment 2 measured).
- `[machine]` Noise floor `ε_f` recorded before AND after — **MET**: before
  `~5.2e-05` (wide spread, worst reading), after `~6.8e-13` — nine orders,
  matching ADR-222 amendment 2's own component-level reading. Both numbers
  are in ADR-223 for `PROPOSAL_convergence_certificate.md` §6 to draw on.

## Provenance (ADR-193)

Every reproducibility measurement in this session (Passes 1, 2, 4) is
`MEASUREMENT (own criterion)`: Polaris measured against itself across BLAS
thread counts, or against a `float128` evaluation of its own formula. No
`mgcv` quantity is an operand. `mgcv` enters only as the generator of the
fixture's recipe (`probe7.json`, via `gam_select_multiterm_free_sp_probe.R`)
— the same asymmetry `SELECT_FREE_SP_MODEL_CLAIM` already documents.

Pass 3 (`SELECT_FREE_SP_MODEL_CLAIM`) is the pre-existing **INDEPENDENT**
comparison `SELECT_FREE_SP_MODEL_CLAIM` already declares (`gam_model.
fit_polaris_gam` computes `eta`/`log10(sp)`/`edf_total`/per-term edf from
the shared recipe; `mgcv gam(select=TRUE, method="REML")` computes the
identical formula independently; neither reads the other's fit) — re-run,
not re-declared, since this slice changes neither producer's signature nor
what each computes from, only the numerical stability of one producer's own
internal criterion.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt, this session's own install — no
drift from the routine's expected apt versions). Tier 3: **not yet
dispatched** — registered as a follow-up below.

## Follow-ups filed

- **Tier-3 confirmation of `SELECT_FREE_SP_MODEL_CLAIM`'s post-7h table** —
  dispatch `mgcv-conformance.yml` on this branch/PR and read the job
  summary. *1st-order, should run before this PR leaves draft if the CI
  round trip is available in this session.*
- **The `_FINITE_DIFF_STEP` noise-floor interaction** (this slice's
  incidental finding: the ADR-212 defect no longer reproduces on its own
  fixture post-7h) — named, not chased. Revisiting the production default
  needs its own across-fixture measurement (PR #216's own review already
  found the opposite trade-off on a different, well-conditioned fixture).
  *2nd-order — a methodological note, not a work item; explicitly not
  registered as a slice, since no acceptance criterion or production
  default is proposed to change.*
- **Slice 7g direction 1** (a robust inner PIRLS) is next per the PLAN's own
  sequencing note, unaffected by this slice's own scope.

Harvested into the latest `PRODUCT_DIRECTION` under this session's date,
order-tagged, per daily-dev's own convention.
