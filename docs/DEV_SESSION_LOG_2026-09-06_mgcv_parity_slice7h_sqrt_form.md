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

### Pass 5 — tier-3 confirmation (after commit and push)

Pushed to `claude/intelligent-hamilton-lo5adm`, dispatched
`mgcv-conformance.yml` via `workflow_dispatch`
([run 34034428064](https://github.com/jonathancrawford05/polaris-re/actions/runs/34034428064)).
Both jobs green (`mgcv reference (R)`: 41 steps, all success, ~40s;
`Compare against the Python reference`: ~6 minutes, dominated by the
free-`sp` searches slices 7b-7d already run). Required conformance levels
1-3 AGREE, level 5 AGREES, level 4 DISAGREES (unchanged, ADR-190) — no
regression on the gate. `SELECT_FREE_SP_MODEL_CLAIM` tier-3 table:

| search | nfev | max abs eta diff | log10(sp) diff | edf_total diff | agrees |
|---|---:|---:|---:|---:|---|
| single-start | 224 | 4.458e-01 | 4.4393 | +2.5309 | False |
| multistart=9 | 3440 | 5.428e-03 | 5.7851 | -0.2469 | **True** |
| single-start, analytic gradient | 61 | 5.803e-03 | 1.6363 | -0.3393 | **True** |
| multistart=9, analytic gradient | 525 | 5.444e-03 | 5.7950 | -0.2542 | **True** |

Production-recommended configurations agree at both tiers; single-start
disagrees at both. `multistart=9, analytic gradient`'s `5.444e-03` matches
ADR-220 amendment 2's own prior tier-3 reading of the identical cell
(`5.460e-03`) to within noise — a genuine "unmoved" reading, not a
coincidence. **`single-start, analytic gradient` flips verdict between
tiers** (tier 1: `False`, `eta=0.0632`; tier 3: `True`, `eta=0.00580`) —
checked against the epic's own prior findings rather than treated as new:
this is a single-start configuration on the by-term's weakly-identified
direction, and ADR-211/212/222 already established that single-start
searches on this class of surface are sensitive to environment (BLAS
threads there; here, the `mgcv` release that generated the fixture's own
reference fit — 1.9.1 tier 1 vs 1.9.4 tier 3, which can select a measurably
different `sp` on identical data even before any Python code runs). Not
chased further: the production-recommended path is unaffected, and
single-start was never this epic's own passing configuration at either
tier before or after this fix.

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
- Full suite, `-m "not slow"`, `OPENBLAS_NUM_THREADS=1`: **3637 passed, 3
  skipped, 126 deselected, 0 failed** (527s). Reconciles against the
  session's own baseline (3604 passed / 22 skipped / 7 failed, before
  mortality tables and this change): the 4 mortality-table failures resolved
  by the one-time environment step, the 3 remaining failures resolved by the
  documented, root-caused test updates above, and the new tests this session
  added are included and passing. **No new or changed failure.**
- `tests/qa/` (golden gate): byte-identical — included in the full-suite run
  above (`tests/qa/test_pipeline_golden.py` passed with the rest); `git
  status` on `tests/qa/golden_outputs/` empty.

## Definition of done

Recorded inline against `PLAN_mgcv_parity_engine.md` slice 7h:

- `[machine]` Score's cross-thread spread re-measured at all four spreads —
  **MET** (Pass 2 above; ADR-222 amendment 2's own diagnostic reproduced
  unchanged in Pass 1, since it doesn't call the production function).
- `[machine]` Square roots computed once per fit, not per evaluation —
  **MET** (wired in `select_lambdas_continuous`; cost measured, Pass 4).
- `[machine]` `SELECT_FREE_SP_MODEL_CLAIM` re-measured tier 1 AND tier 3 —
  **MET, both tiers.** Tier 1: Pass 3 above. **Tier 3 (Pass 5, below):** CI
  run
  [34034428064](https://github.com/jonathancrawford05/polaris-re/actions/runs/34034428064),
  R 4.6.1 / mgcv 1.9.4, pinned oracle digest
  `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.
  Required conformance levels 1-3 AGREE (no regression), level 5 AGREES,
  level 4 DISAGREES (unchanged, permanently expected). Production-recommended
  configurations (`multistart=9`, with/without analytic gradient) agree at
  tier 3 too, matching this epic's last tier-3 reading of the identical cell
  before this fix (`5.460e-03` then, `5.444e-03` now). Single-start alone
  disagrees at both tiers, unchanged. One cell (single-start + analytic
  gradient) reads a DIFFERENT verdict between tiers (`False` tier 1,
  `True` tier 3) — a pre-existing single-start cross-`mgcv`-release
  instability (ADR-211/212/222's own documented class), not a defect in this
  fix; the production path is unaffected. See ADR-223 amendment 1 for the
  full table.
- `[machine]` `tests/qa/golden_outputs/` byte-identical — **MET** (Quality
  gate section above).
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
drift from the routine's expected apt versions). Tier 3: R 4.6.1 / mgcv
1.9.4, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8, the same digest this epic has used throughout), CI run
[34034428064](https://github.com/jonathancrawford05/polaris-re/actions/runs/34034428064) — **CONFIRMED, both jobs green.**

## Follow-ups filed

- ~~**Tier-3 confirmation of `SELECT_FREE_SP_MODEL_CLAIM`'s post-7h table**~~
  — **DONE, same session, Pass 5 above.**
- ~~**The `_FINITE_DIFF_STEP` noise-floor interaction**~~ — **RE-TAGGED
  1st-order and REGISTERED as PLAN slice 7i**, per PR #229's automated
  review [P1] (see Post-review addendum below): this session's own original
  2nd-order tag was wrong — `TestFiniteDiffStep`'s two tests now assert the
  identical property on the identical fixture, so the production override
  ships with no test in which it changes any outcome, which is a direct,
  1st-order consequence of this slice's own measurement, not a general
  methodological note.
- **Slice 7g direction 1** (a robust inner PIRLS) is next per the PLAN's own
  sequencing note, unaffected by this slice's own scope.

Harvested into the latest `PRODUCT_DIRECTION` under this session's date,
order-tagged, per daily-dev's own convention.

## Perf History

`scripts/perf_history.py` run against this PR's HEAD (idempotent, per-commit
append). One row appended, no prior row edited or removed. Creep verdict:
`insufficient_data: false`, `peak_mib_delta 0.0`, `wall_time_ratio 1.119`
(inside the `1.25` band), no config drift — **no structural creep.**

## Post-review addendum — PR #229's automated review

Comment review (changes requested; the automation's own GitHub identity is
this PR's author, so a formal `REQUEST_CHANGES` event was not available to
it). Verified every reproduced number before acting — all matched
(`norm(grad) = 0.008491` against this log's `~8.5e-3`; the suite
reconciliation; the creep verdict).

**[P0] Withheld pending maintainer sign-off — not something this session
resolves.** The review's own standing guardrail withholds automated
approval, unconditionally, from any PR that changes an existing test's
assertion — documented or not. Both changes here (`TestFiniteDiffStep`'s
renamed/flipped test, `test_compare_select_free_sp_case_agrees_is_now_eta_edf_not_log10_sp`'s
forced `converged=True`) are named in the PR body, root-caused in this log,
and independently reproduced by the reviewer — the review says so
explicitly. Left as-is, awaiting the maintainer's own decision; not mine to
override by reverting a correctly-diagnosed test change back to asserting a
now-false premise.

**[P1] `_FINITE_DIFF_STEP` no longer discriminated by any test — FIXED,
by re-scoping.** Addressed above: re-tagged 1st-order, registered as PLAN
slice 7i with its own Definition of Done (a committed fixture where the
step still changes an outcome, or a re-derived value).

**[P1] No R-free test covers live convergence of `fit_select_free_sp_case`
— ACKNOWLEDGED, documented rather than built.** The review confirmed the
override is correctly scoped (the sibling tests don't read `agrees`, so
needed no change) and offered two remedies: a non-gating reported
observation, or stating the coverage gap explicitly in ADR-223. Took the
second — ADR-223 amendment 2 now states plainly that live single-start
convergence on `_small_recipe()` is environment-dependent (`False` in this
session, `True` in the reviewer's) and is no longer exercised outside the
R-gated `test_the_r_probe_runs_end_to_end` path.

**[P2] `penalty_block_square_roots` silently clipped a genuinely indefinite
block — FIXED.** Added the suggested magnitude guard (raises
`PolarisValidationError` when an eigenvalue is negative beyond
`_SQRT_RANK_RELTOL` relative to the block's own largest one) plus three new
tests: an all-zero block still yields a `(q, 0)` root without raising
(verified this doesn't collide with the new guard — an exact zero matrix
has no rounding noise in `eigh`, so both bounds are exactly `0.0`), a
genuinely indefinite block raises, and a noise-scale negative eigenvalue
(`-1e-16` against a `1.0` scale) is still clipped, not rejected.

**[P2] Exact float `==` in two new assertions — FIXED.** Both switched to
`np.testing.assert_array_equal`, matching the repo's existing bit-identity
convention the review cited (not treated as the tolerance-style P0
`REVIEW.md` names, correctly — the intent here is deliberate bit-identity).

**[P2] Missing Perf History section / creep verdict — FIXED.** Added above;
verdict matches the reviewer's own independent computation exactly.

**Re-verification after these fixes:** `uv run ruff format` / `ruff check`
clean on every touched file; `pytest tests/test_analytics/test_gam_reml.py
tests/test_analytics/test_gam_reml_optimize.py` — all passing including the
3 new guard/edge-case tests.

## Post-review addendum 2 — a second, independent automated review ("from the #227 side")

A second reviewer verified `ε_f` (`~5.2e-05 -> ~6.8e-13`, correctly located
at half the pre-fix `beta'Sbeta` thread spread), confirmed `agrees` is
unchanged at every configuration and both tiers, and confirmed the caching
is a net cost saving. No blocking findings, but two real gaps and one
forward-looking concern.

**[P1-1] `PROPOSAL_convergence_certificate.md` §6 still told a reader to
wait for a measurement this PR just produced — FIXED.** Slice 7h's own
DoD required recording `ε_f` before/after specifically so this document's
own deferral could be closed; the number existed in ADR-223 but the
document itself was never told. Amended §6 to state the post-fix `ε_f`
(`~6.8e-13`) directly and point at ADR-223/the ledger for the full
before/after table. The two thresholds `ε_rel` and the curvature-to-noise
ratio remain explicitly the maintainer's to set — this only removes the
document's own staleness about whether the measurement it was waiting for
exists.

**[P1-2] The `converged` flip is independent evidence for the convergence
proposal's OWN central claim, arriving from an unanticipated axis — added
as a third instance, not left as only a test-decoupling note.** The
reviewer's framing is sharper than the original session log's: a
formula-only fix (no search change, no thread-count change) flipping
`converged` on a fit that itself barely moved is a clean demonstration
that the flag tracks the optimiser's internal path, not fit quality —
alongside slice 7c's flat-direction reading and slice 7f's `ftol`
state-governed exit, both already in
`docs/PATTERN_resolvable_tolerances.md` §1. Added as Instance 3 there (with
the specific eta/edf/score deltas), and a short paragraph in
`PROPOSAL_convergence_certificate.md` §1 citing it as a third, unplanned
confirmation of the same diagnosis.

**[P2-1] The forced `converged=True` as a latent trap if the certificate is
later adopted — considered, NOT implemented as suggested, with reasons.**
The reviewer offered two remedies: build the fit synthetically instead of
running the live search, or pin the flip in its own small test. Attempted
the second first — and it would have been WRONG to ship: the reviewer's
own review already reports that the IDENTICAL live call on their machine
returned `converged=True` where this session's own environment returns
`False` for the SAME recipe. Asserting either specific value would make
the test pass or fail depending on which machine runs it — reintroducing,
inside a brand-new test, the exact environment-dependent-flag problem
ADR-211/212/218/222 spent four ADRs establishing must never be asserted on
directly. **Not fixed in this PR** — the documentation-only response in
ADR-223 amendment 2 (stating plainly that only the R-gated path still
covers live convergence here) is left as the answer; building the fit
synthetically (the reviewer's FIRST offered remedy, not attempted this
session) remains open if a future session wants gate-arithmetic tests that
never touch the live search at all.

**Re-verification:** `tests/test_analytics/test_gam_select_free_sp_conformance.py`
— 9 passed (unchanged count — no new test added, per the P2-1 finding
above), including the live R-gated round trip.
