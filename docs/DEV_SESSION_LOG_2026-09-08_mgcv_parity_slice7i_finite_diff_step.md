# Dev session log — 2026-09-08 — mgcv-parity slice 7i (`_FINITE_DIFF_STEP` re-justification)

**Routine:** `ROUTINE_MGCV_PARITY.md`, scheduled trigger.

**Branch:** `claude/intelligent-hamilton-3a8h5c`, already at `origin/main`'s HEAD
(`0a4834e`, PR #230 merged) — no restart needed.

## Setup

- `uv sync --all-extras` — installed `statsmodels`/`patsy`/`openpyxl`/`et-xmlfile`
  (dev extras), no other changes.
- R installed fresh in this container (`apt-get install r-base-core r-cran-mgcv
  r-cran-jsonlite`): `R version 4.3.3 (2024-02-29)`, `mgcv 1.9.1` — matches the
  routine's expected tier-1 versions exactly. `OPENBLAS_NUM_THREADS=1` exported
  for every local R/Python invocation this session.
- Read `docs/ROUTINE_MGCV_PARITY.md`, `docs/PLAN_mgcv_parity_engine.md` (Anchors
  1, 2, 8 and slice 7i), `docs/CONTINUATION_mgcv_parity_engine.md`'s status block
  (through ADR-224/slice 7g), `docs/CONFORMANCE_LEDGER.md`'s tail,
  `docs/VERIFICATION_STANDARD.md`, `CLAUDE.md`, `docs/DECISIONS.md` ADR-189
  (+amendments), ADR-190/191/192/193, ADR-223 + amendments 1-2, ADR-224.
- **Work selection**: PLAN's next unchecked, no-fallback slice. Slices 1
  through 7h are DONE; slice 7i ("re-justify `_FINITE_DIFF_STEP`, or retire
  it") is REGISTERED, not started, and comes before slice 8 in PLAN order —
  selected per the routine's own rule.
- Baseline `uv run pytest tests/ -m "not slow"`: initial run showed **5 failed,
  3620 passed, 22 skipped** — all 5 failures and the extra skips traced to
  missing `data/mortality_tables/*.csv` (a fresh container that had never run
  `scripts/convert_soa_tables.py`, per `CLAUDE.md` §11), NOT a code regression —
  none of the failing tests touch anything in this slice's scope
  (`gam_reml_optimize.py`, mortality-table loading, synthetic-block premium
  calibration). Ran the documented setup step
  (`uv run python scripts/convert_soa_tables.py --source pymort --output-dir
  data/mortality_tables`); re-ran the 5 affected files — all pass. Full-suite
  baseline after that: **3644 passed, 3 skipped, 126 deselected, 0 failed**
  (819s) — confirmed by re-running the identical command on the untouched
  branch tip (`git stash` of this session's own changes, re-run, `git stash
  pop`) later in the session: `--collect-only` gave `3647/3773` (3644 + 3
  skipped) both times, no drift.

## Gap Before

This slice makes no `mgcv` comparison anywhere (PLAN slice 7i's own scope is
entirely internal: a SciPy optimizer step-size constant), so there is no
parity gap to state in the routine's usual sense. The gap this slice closes is
a TEST-COVERAGE one, named by PR #229's automated review (ADR-223 amendment
2, [P1]): after slice 7h's fix, `_FINITE_DIFF_STEP = 1e-5`'s two historical
discriminating tests
(`test_default_step_no_longer_needed_on_the_near_flat_fixture`,
`test_finite_diff_step_default_avoids_the_spurious_convergence`) assert the
IDENTICAL property on the IDENTICAL fixture, differing only in `eps` — the
production override ships with no committed test in which it changes any
outcome. PR #216's own (uncommitted) review finding that `1e-5` costs a digit
of accuracy on a well-conditioned problem is the only surviving justification
for keeping it, and that finding was never pinned by a test either.

## Provenance gate (ADR-193)

Every comparison this slice makes is `MEASUREMENT (own criterion)`
(`VERIFICATION_STANDARD.md` §2.1): a forward-difference estimate of Polaris's
own REML score, measured against Polaris's own analytic gradient
(`gam_reml_gradient.reml_score_gradient`, slice 7d) at the same point.
Removing `mgcv` from every script this session wrote leaves every number
unchanged — there is no second producer for the two-producer rule to apply
to, so no `VerificationClaim` is declared and nothing here is reported as
parity or agreement evidence. R is used only to have originally generated the
covariates in the pre-existing committed fixture
(`tests/fixtures/gam_reml_optimize_near_flat_direction.json`); no new R
invocation was needed this session for the measurements that landed.

## The loop

1. **Hypothesis:** re-running ADR-223's own sqrt-form thread-sweep
   methodology (`gam_penalty_sqrt_form_diagnostic.py`, built for the N=7
   `select=TRUE` structure) on the N=4 (non-`select`) structure
   `_FINITE_DIFF_STEP` was actually derived on will reproduce the same order
   of magnitude of thread-reproducibility gain.
   **Change:** wrote `scripts/gam_penalty_sqrt_form_diagnostic_n4.py`,
   regenerated a fresh N=4 fixture (`Rscript scripts/gam_multiterm_free_sp_probe.R`)
   for an `mgcv`-selected evaluation point.
   **Result:** CONFIRMED — wide point `1.475e-04 -> 1.099e-12` (~134,000x),
   fresh mgcv point `3.092e-09 -> 3.434e-12` (~900x). The sum-of-squares fix
   generalises to N=4, not only the N=7 structure ADR-223's own session
   measured.

2. **Hypothesis:** a direct forward-difference step scan at the production
   search's own converged point on the committed near-flat fixture — the
   exact methodology ADR-212 used to derive `1e-5` — will show the stable
   region has WIDENED post-7h (the registered prediction).
   **Change:** none to the code — `select_lambdas_continuous` run once to
   find the production default's own converged point (post-7h, true gradient
   norm `3.49e-3` by central difference), then forward differences at
   `h = 1e-1` through `1e-10`.
   **Result:** REFUTED. ADR-212's own pre-fix reading: stable `1e-1` to
   `1e-6`, broken by `1e-9`. This session's post-fix reading at THIS (much
   better-converged) point: stable to roughly `1e-5`, drifting by `1e-6`,
   clearly broken by `1e-7` — the stable region is narrower, not wider. Slice
   7h fixed the score's cross-thread REPRODUCIBILITY; the forward-difference
   NOISE FLOOR this constant guards against is a different property and did
   not move the same way.

3. **Hypothesis:** measuring the finite-difference gradient's error against
   the ANALYTIC gradient (available since slice 7d, not used in ADR-212's
   original derivation) at both a well-conditioned toy and the N=4 fixture's
   own wide-spread point will make PR #216's previously-uncommitted trade-off
   claim precise and reproducible.
   **Change:** wrote `scripts/gam_finite_diff_step_tradeoff_diagnostic.py`.
   **Result:** CONFIRMED, precisely, in both directions:
   - Well-conditioned toy (n=200, p=6, single block): SciPy default
     (`1.49e-8`) error `1.33e-6`; production (`1e-5`) error `1.45e-5` — ~11x
     worse. A second point (`log10(lambda)=3.0`): `4.83e-7` vs `1.81e-5`,
     ~37x.
   - N=4 fixture, own converged point (true grad norm `3.49e-3`): SciPy
     default error `5.61` (1600x the signal); production error `6.51e-3`
     (comparable to the signal, expected near a stationary point); the
     TRUE optimum is `h=1e-4` (`6.23e-4`), not `1e-5`.
   - N=4 fixture, wide (11-decade) synthetic spread (true grad norm
     `14.14`): SciPy default error `31.1` — EXCEEDS the signal, direction-
     destroying; production error `4.73e-2` — under `0.4%` of it.

4. **Decision:** `_FINITE_DIFF_STEP` is RE-CONFIRMED, unchanged. Moving it
   toward SciPy's default would reopen ADR-212's original spurious-
   convergence failure mode on badly-scaled points (measurement 3, N=4 wide
   point). Moving it toward the locally-optimal `1e-4` measured at the N=4
   own-converged point would cost another order of magnitude on well-
   conditioned problems (measurement 3, toy) for a marginal gain the
   module's own search robustness (`multistart`, `step_halving`) already
   covers more directly than a single global constant can. Two new,
   deterministic, committed tests
   (`test_scipy_default_step_is_less_accurate_than_production_on_a_well_conditioned_toy`,
   `test_scipy_default_step_is_catastrophically_wrong_on_a_wide_lambda_spread`)
   restore the discrimination PR #229's review found missing, referenced
   against the analytic gradient rather than only a central-difference
   cross-check. `_FINITE_DIFF_STEP`'s own docstring updated to record this
   measurement.

## Gap After

No `mgcv` parity gap exists in this slice's own scope (see Gap Before). The
TEST-COVERAGE gap PR #229's review named is closed: `_FINITE_DIFF_STEP` now
has two committed, deterministic tests in which varying it changes a measured
outcome, in both directions of the trade-off, referenced against an
independent (analytic) computation rather than only a central-difference
self-check.

## Mutation protocol

Not applicable — no new formula module, no new production code path. The two
new tests ARE the discriminating check this slice's own DoD asked for; they
were verified to actually discriminate by running them against both step
choices during authoring (see the loop above), not merely asserted.

## Quality gate

- **Caught here, not after merge**: a full-suite run with
  `OPENBLAS_NUM_THREADS=1` exported for the whole process (set before
  launch, so it reaches OpenBLAS before first import) passed cleanly
  including both new tests. But re-running just
  `test_gam_reml_optimize.py` in a **separate shell invocation that did not
  re-export the env var** (this harness's shell state does not persist
  across tool calls) reproduced a real, distinct failure:
  `test_scipy_default_step_is_catastrophically_wrong_on_a_wide_lambda_spread`
  FAILED with `scipy_default_err=13.55 < true_norm=14.14` — under an
  unpinned, multi-threaded BLAS the wide-point measurement moved enough to
  flip the very comparison it exists to make. Root cause: that test's first
  draft did not wrap its BLAS-heavy calls in `threadpool_limits(1, "blas")`,
  unlike every other test in `TestFiniteDiffStep` — exactly the
  env-var-does-not-reliably-reach-an-already-imported-OpenBLAS mechanism
  PR #217/ADR-211 already documented for this class (an env var set before
  process launch reaches it; one relied on implicitly via shell state that
  may or may not persist does not). Fixed by pinning
  `threadpool_limits(1, "blas")` explicitly inside the test itself, per the
  class's own stated convention (see ADR-225), rather than relying on the
  caller's environment. Re-ran the file three times pinned and three times
  unpinned afterward — 45/45 pass every time, deterministically.
- A separate, purely arithmetic confusion during this session (worth
  recording since it cost real time): this session's own true baseline is
  **3644 passed, 3 skipped** (confirmed by `git stash` + a clean re-run, see
  Setup), not `3646` as first assumed from a misremembered prior session's
  count — `3646` after this slice's `+2` tests is therefore CORRECT, not a
  sign the new tests failed to register. No code defect here, just a
  bookkeeping error caught by re-deriving the baseline directly rather than
  trusting recalled numbers.
- `uv run ruff format src/ tests/` — reformatted after the threadpool fix
  (multi-line `with` block).
- `uv run ruff check src/ tests/ --fix` — all checks passed.
- `uv run pytest tests/ -m "not slow"` — **3646 passed, 3 skipped, 126
  deselected, 0 failed**. Reconciles exactly against the true baseline
  (3644/3/0, see Setup): +2 for the two new tests, everything else
  unchanged.
- `uv run pytest tests/qa/` — **94 passed**, `tests/qa/golden_outputs/`
  byte-identical.
- Targeted: `test_gam_reml_optimize.py`, `test_gam_reml.py`,
  `test_gam_model.py`, `test_gam_reml_gradient.py` — 90 passed.
- Ten-cell conformance suite (tier 1, R 4.3.3/mgcv 1.9.1, local apt): levels
  1-3 AGREE, level 4 DISAGREES (ADR-190, permanently expected), level 5
  AGREES — identical verdict to the pre-slice baseline, as expected for a
  change with no `mgcv` comparison anywhere in its own scope. No tier-3
  dispatch made — nothing in this slice is a parity claim needing tier-3
  confirmation (ADR-193: tier answers "which `mgcv` produced the reference",
  and there is no reference here at all).

## Provenance summary

| comparison | left producer | right producer | classification |
|---|---|---|---|
| forward-diff gradient error, well-conditioned toy and N=4 fixture, both regimes | `penalized_fit_and_score` finite-difference estimate at varying `h` | `gam_reml_gradient.reml_score_gradient` (analytic, same criterion) | `MEASUREMENT (own criterion)` (ADR-193 §2.1) — both operands are Polaris's own; no `mgcv` quantity anywhere |
| N=4 sqrt-form thread sweep | `penalized_fit_and_score` at `OPENBLAS_NUM_THREADS` {1,2,4} | same function, different thread count | `MEASUREMENT (own criterion)` |
| forward-diff step scan at the production converged point | `penalized_fit_and_score` at varying `h` | itself, at other `h` | `MEASUREMENT (own criterion)` |
| ten-cell conformance suite (re-run, no-regression check) | `compare_mgcv_conformance.py` | `mgcv`'s own fit | pre-existing INDEPENDENT comparisons, unaffected by this slice's own scope, re-run per routine practice for a slice touching a shared component's docstring (no formula change) |

## Follow-ups harvested

None registered as new PLAN slices — this slice's own DoD is fully met by
re-confirmation, and no new gap is opened (`ROUTINE_MGCV_PARITY.md` step 10).
Slice 8 (the Wood-shaped outer solver) is next. The pre-existing follow-up
(tier-3 confirmation of the `SELECT_FREE_SP_MODEL_CLAIM`/`FREE_SP_MODEL_CLAIM`
re-measurement tables, registered by ADR-224) remains open and is unaffected
by this slice, which makes no such comparison.

## Perf history

`docs/DECISIONS.md` ADR-177 amendment 1 exempts a PR that modifies nothing
under `src/polaris_re/` — this PR does (a docstring update in
`gam_reml_optimize.py`), so a row was appended per the standing rule, even
though no fitter/basis/assembly path changed:
`uv run python scripts/perf_history.py` — **no structural creep**
(`peak_mib` unchanged, `33 -> 33`); wall-time recent/baseline ratio `1.258x`,
marginally above the `1.25` advisory band — informational only, does not
gate (ADR-177). Committed as a separate follow-up commit, per convention.
