# Session log — 2026-08-30 — Slice 5e: best-of-N multi-start for the outer search

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5e — `docs/PLAN_mgcv_parity_engine.md`, registered 2026-08-29 (ADR-211),
premise restated 2026-08-30 against ADR-212's merged fix. The routine's "next
unchecked slice" rule selected it (slice 5e precedes slice 6 in the PLAN's own
ordering; both were READY, but 5e is registered earlier).
**PR:** this branch (`claude/intelligent-hamilton-r4nada`), draft.
**ADR:** ADR-213.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle (tier 1): `apt-get install -y -qq
  r-base-core r-cran-mgcv r-cran-jsonlite` failed on stale package-index
  404s first (the same recurring transient prior sessions record);
  `apt-get update -qq` fixed it. Versions recorded: **R 4.3.3 / mgcv
  1.9.1** — matches the routine's expected apt versions exactly, no drift
  to flag. (Tier 1 is used only once in this session, to confirm the
  committed near-flat fixture's data draw is stable — see below; the
  slice's own measurement makes no mgcv comparison and needed no further R
  work.)
- `OPENBLAS_NUM_THREADS=1` exported for the initial full-suite baseline;
  the slice's own measurement pins threads per-run via `threadpoolctl`
  (tests) or a subprocess re-exec (the diagnostic script) instead, per the
  lesson `tests/test_analytics/test_gam_reml_optimize.py`'s
  `TestFiniteDiffStep` class already names — the env var alone does not
  reliably reach an already-imported OpenBLAS.
- `uv run pytest tests/ -q -m "not slow"` baseline (before any code
  change): **5 failed, 3483 passed, 22 skipped, 126 deselected** (499.71s).
  All 5 failures were `FileNotFoundError: Mortality table CSV not found`
  (`tests/test_synthetic_block.py::TestCalibratedPremiums`,
  `tests/test_analytics/test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface`)
  — the documented, one-time-per-environment "tables are generated, not
  committed" gap (CLAUDE.md §11), not a code regression: this is a fresh
  container with no prior `scripts/convert_soa_tables.py` run. Ran that
  script (`--source pymort --output-dir data/mortality_tables`); re-ran the
  5 affected tests — all 5 pass. **This is a NEW failure set relative to
  the last parity session's own baseline** (ADR-211/212 sessions: 0
  failed) in the routine's own step-4 sense, but the cause is an
  environment-setup gap already documented as a one-time step, not a
  changed or new code failure — PROCEEDED per the routine's "do not
  deadlock on known-standing failures" once the documented fix (also
  named directly in the test's own error message) resolved it, rather
  than treating it as a stop condition. Did not re-run the full ~500s
  suite a second time to get a fresh aggregate count (time budget); the
  specific 5 failing tests were individually confirmed passing, which is
  what mattered for "is this a code regression" (no).

## Gap Before

PLAN slice 5e's own registered question, restated 2026-08-30 against
ADR-212's merged fix (`CONTINUATION_mgcv_parity_engine.md`): ADR-212 closed
the SCORE gap at N=4 (post-fix, the production default lands in a
`612.6101`-`612.6116` band across thread counts, essentially tied with
`mgcv`'s own `612.6108`) but left two things open — the by-term's own
`log10(sp)` COORDINATE still moves with thread count, and **"does one
start still suffice at N > 4 blocks?"**, never measured at all before this
session, since no N>4 design existed anywhere in the codebase. ADR-211's
own pre-fix blind multi-start check (bounds-centre + 8 uniform-random
draws, N=4 only) reached `612.6149` at best against the single default
start's `612.6630`, with 2 of 9 far-corner starts failing to converge —
suggestive that multi-start helps, but taken against a baseline (the
pre-`_FINITE_DIFF_STEP`-fix single start) the slice's own premise
explicitly says is no longer valid to compare against.

**Tier and digest:** N/A for this slice's own measurement — see
"No mgcv comparison" below. ADR-211's own PRE-fix numbers quoted above are
tier 1 (R 4.3.3/mgcv 1.9.1, local apt) and are cited for context only, not
as this session's baseline.

## Hypotheses tried

1. **Reuse `AttdAge`/`PolYear` under additional `by`-scalings to build an
   N=8 structure quickly (tried first, REJECTED).** A `TermSpec` list
   adding `s(PolYear, by=StudyYear_C)`, `s(AttdAge, by=PolYear_C)` and
   `ti(PolYear, StudyYear_C)` on top of the existing three terms produced
   a design whose selected point's own `effective_degrees_of_freedom` call
   raised `numpy.linalg.LinAlgError: Singular matrix` (`gam_fit.py:155`) —
   real column-span overlap between the reused-covariate terms, not a
   numerical near-miss. **Verdict: rejected**, no further diagnosis spent
   (Anchor 8: don't paper over with a smaller step or a looser tolerance;
   change the construction instead). Recorded here so slice 5f does not
   re-try the identical construction blind.
2. **Duplicate the N=4 shape onto an independent, covariate-decoupled
   second draw (adopted).** `ref`+`by`+`ti` on `(AttdAge, PolYear,
   StudyYear_C)` plus the identical shape on a fresh
   `(AttdAge2, PolYear2, StudyYear_C2)` draw
   (`numpy.random.default_rng(20260830)`, pinned) — 8 blocks total, no
   shared covariates between the two copies, so no rank-deficiency.
   **Verdict: worked** — see Measurement below. Explicitly NOT a claim that
   this is representative of the target formula's own 13-21-block
   structure, which mostly SHARES covariates across terms — that is why
   slice 5f exists.
3. **Best-of-N multi-start as the production robustness mechanism
   (adopted, PLAN's own candidate 1 of three named).** Built as a new,
   reusable function (`select_lambdas_continuous_multistart`) rather than
   a one-off script, deterministic starts via a pinned
   `numpy.random.default_rng` seed — not tried against candidates 2
   (analytic gradient) or 3 (a different search algorithm), both left as
   named alternatives in the PLAN, not attempted this session (one slice,
   the cheapest and PLAN's own "natural next thing to measure" tried
   first; PLAN §5's "NEVER burn the whole session on hypothesis 1" cuts
   the other way here — the first candidate worked well enough on both
   measured points that there was no forced move to try a second).

## No mgcv comparison in this slice

Stated explicitly, per `docs/VERIFICATION_STANDARD.md` §3.2: the claim
sentence for either measurement below cannot be filled in with two
distinct computations — `select_lambdas_continuous_multistart` is compared
against `select_lambdas_continuous` (the single-start default), which is
Polaris's own code, not a second, independent producer. There is nothing
for ADR-193's mechanical test to apply to (no `right_producer` exists), so
no `VerificationClaim` is declared anywhere in this slice — declaring one
with a fabricated second side would be exactly the kind of table
`docs/VERIFICATION_STANDARD.md` §1 warns travels as parity evidence even
with an accurate caption. `docs/CONFORMANCE_LEDGER.md`'s new row says the
same thing in its own verdict column. This is the same class of
internal-only measurement ADR-211's own OpenBLAS-thread-count table
already was.

## What was built

- `select_lambdas_continuous_multistart` (`gam_reml_optimize.py`) —
  best-of-`n_starts` (default 9) independent `select_lambdas_continuous`
  calls; the first start is always the bounds-centre (so it reproduces the
  single-start default's own result exactly), the rest are drawn by
  `numpy.random.default_rng(seed=20260830)` — pinned per ADR-074, and
  deterministic regardless of platform or BLAS thread count (only each
  start's own CONVERGED SCORE can still move with thread count, for the
  identical reason a single search's own score does, per ADR-211 — this
  function does not and cannot remove that per-fit noise; it gives the
  search several independent attempts to escape wherever the noise stalls
  it). No new fitting or scoring formula. 7 new tests
  (`TestSelectLambdasContinuousMultistart`), including a replay of
  ADR-211's own near-flat-fixture check through the new function.
- `scripts/gam_multistart_robustness_diagnostic.py` — the measurement
  below. Re-execs itself per `OPENBLAS_NUM_THREADS` value (the reliable
  way to pin OpenBLAS across a fresh process, matching
  `TestFiniteDiffStep`'s own lesson for `threadpoolctl` inside one
  process). PART 1 replays ADR-211's own N=4 check through the new
  function; PART 2 builds the synthetic N=8 duplicate.

## Measurement

All three thread counts read directly from the diagnostic script's own
JSON output (`--worker N`), no post-processing beyond formatting. The
2-thread reading was added in response to PR #218 review [P2]: the
script's own `_THREAD_SWEEP` already declares `{1, 2, 4}`, but the
initial PR open reported only 1 and 4.

**PART 1 — N=4 (`tests/fixtures/gam_reml_optimize_near_flat_direction.json`,
the identical recipe `scripts/gam_multiterm_free_sp_probe.R` draws):**

| threads | single score | single converged | multi (best-of-9) score | multi total evals |
|---:|---:|:---:|---:|---:|
| 1 | 612.610092 | True | 612.610032 | 2190 |
| 2 | 612.611575 | True | 612.610032 | 2270 |
| 4 | 612.611509 | **False** | 612.610038 | 1935 |

**Spread across all three threads: single-start `0.001483`, best-of-9
`0.000006` — a ~247x tighter reproducibility band.** At 1 thread the two
are already close (gap `6e-5`). At 2 threads single-start reports
`converged=True` but lands at its own WORST reading of the three — a
"successful" termination is not itself evidence of a good point on this
surface. At 4 threads the single bounds-centre start fails SciPy's own
convergence check outright and lands `0.0015` worse; best-of-9 finds the
same converged, better point at every one of the three thread counts
(agreeing to the fifth decimal). This is the reproducible improvement the
slice's acceptance criterion asked for, on the exact structure the slice
was registered against.

**PART 2 — synthetic N=8** (PART 1's own shape duplicated onto an
independent draw, hypothesis 2 above):

| threads | single score | single converged | multi (best-of-9) score | multi total evals |
|---:|---:|:---:|---:|---:|
| 1 | 621.069367 | True | 621.069367 (identical to printed digit) | 5886 |
| 2 | 621.069125 | True | 621.069125 (identical to printed digit) | 5346 |
| 4 | 621.070305 | True | 621.070290 | 8874 |

Single-start converged at all three thread counts; multi-start matches it
exactly at two of three and beats it by `1.5e-5` at the third. **Spread
across threads: single-start `0.001180`, best-of-9 `0.001165` — essentially
the SAME spread**, unlike N=4's 247x gap (an earlier two-point reading of
this same measurement called it "an order of magnitude tighter"; the third
point corrects that — both searches are tracking the same thread-dependent
movement here, not one recovering from a failure the other has). **On this
specific stress structure, one start already suffices, at every thread
count tested.**

**Cost.** Best-of-9 costs `~8-21x` a single search's own function
evaluations across all three thread counts (not a fixed multiple: harder
starts iterate longer). Reported because the slice's own acceptance
criterion asks for it stated, not hidden.

## Gap After

PLAN slice 5e's own question — does one start still suffice past N=4 — is
ANSWERED with evidence for the one structure tested (yes, on a
covariate-decoupled N=8 stress case), while a reusable mitigation
(best-of-9) is separately shown to recover a real N=4 convergence failure.
**What remains, registered as PLAN slice 5f (not blocking slice 6/7):** a
covariate-SHARING N>4 structure — closer to the target formula's own
13-21-block shape than two decoupled copies are — is untested, and
hypothesis 1 above (the first, rejected construction attempt) is left as
a documented dead end so a future session does not repeat it blind.

## Provenance (ADR-193)

No comparison against `mgcv` is made anywhere in this session. Both
measurements above compare `select_lambdas_continuous_multistart`'s own
output against `select_lambdas_continuous`'s own output — the SAME
producer family, Polaris's own search, never a second independent
implementation, an `mgcv` fit, or any external reference. Per
`docs/VERIFICATION_STANDARD.md` §2's mechanical test, this is not
INDEPENDENT, ECHO or TRANSPORT — those three exhaust the relationships a
comparison *against a second producer* can have, and there is no second
producer here at all, so none of the three labels applies. No
`VerificationClaim` is declared (there is nothing to declare — declaring
one would require inventing a `right_producer`), and
`docs/CONFORMANCE_LEDGER.md`'s new row states this in its own verdict
column rather than leaving it to be inferred. The one place tier-1 R was
used this session (confirming, though not depended upon by the final
measurement, that `tests/fixtures/gam_reml_optimize_near_flat_direction.json`'s
own data draw is stable — matching ADR-211/212's own prior reading) is
also not a comparison: it reads `mgcv`'s own recipe-drawing determinism,
not a quantity Polaris computes.

## Oracle version

R 4.3.3 / mgcv 1.9.1 (local apt, tier 1) — used only for the fixture-draw
stability check named above, not for any quantity in this session's own
measurement or ADR. No tier-3 (CI/pinned-image) dispatch was made this
session: nothing measured here has an `mgcv` side to verify against a
pinned digest.

## Quality gate

- `uv run ruff format src/ tests/ scripts/gam_multistart_robustness_diagnostic.py`
  — clean.
- `uv run ruff check src/ tests/ scripts/gam_multistart_robustness_diagnostic.py --fix`
  — clean.
- `uv run pytest tests/test_analytics/test_gam_reml_optimize.py -q` (the
  changed module's own suite, `OPENBLAS_NUM_THREADS=1`): **22 passed**
  (40.33s, after the PR #218 review round — 1 new test added, see below).
- `uv run pytest tests/ -q -m "not slow"` (full suite, `OPENBLAS_NUM_THREADS=1`,
  after `scripts/convert_soa_tables.py`): **3515 passed, 3 skipped, 126
  deselected, 0 failed** (495.68s) — no regression against the pre-session
  baseline once the environment gap (see Setup) is accounted for.
- `uv run pytest tests/qa/ -q`: **94 passed** (68.58s), goldens
  byte-identical.
- `uv run python scripts/perf_history.py`: no structural creep (peak MiB
  33 → 33).

## Definition of done (PLAN slice 5e's own acceptance, restated)

**Restated 2026-08-30 (PR #218 review [P1]):** the original wording below
("a measured, reproducible improvement **at N > 4 blocks**") presupposes
the answer, and this session's own N=8 measurement refutes that
presupposition (single-start already sufficed) — so "MET" is the wrong
word for a criterion whose premise the measurement overturned. See
`docs/PLAN_mgcv_parity_engine.md` slice 5e's own restated-acceptance
addendum for the full correction. Reproduced here with the corrected
verdict rather than the original (inaccurate) one:

- [~] "A measured, reproducible (thread-count-pinned) improvement at N > 4
      blocks... stated against a freshly-taken POST-FIX baseline... with
      the chosen approach's own cost... stated." **AMENDED — the criterion
      became "answer whether one start suffices past N=4", which this
      session does (yes, on the one covariate-decoupled structure tested)
      — not "demonstrate an improvement there", which the N=8 measurement
      itself refutes as the finding.** The reproducible improvement that
      WAS measured is at N=4 (recovering a real 4-thread convergence
      failure), the structure the slice's premise was restated against;
      it is not evidence about N>4. Cost stated: ~9-17x function
      evaluations.
- [x] "Not a claim that `max_abs_log10_sp_diff` reaches zero." Not made —
      this slice never compares against `mgcv` at all, so that metric does
      not appear in this session's own measurement.

## PR #218 review response (2026-08-30)

An automated review (posted as a comment on the PR's own author account,
since GitHub forbids a formal changes-requested review on one's own PR)
found one [P0] and several P1/P2 findings. Addressed:

- **[P0]** `scripts/gam_multistart_robustness_diagnostic.py` carried
  `from __future__ import annotations` — on CLAUDE.md's Never list (Python
  3.12, not needed) and unused by any annotation in the file. Removed.
- **[P1]** The DoD's first box read "MET" on a criterion the measurement's
  own N=8 finding refuted the premise of. Restated above and in the PLAN
  as AMENDED, with the criterion's own new meaning spelled out.
- **[P1]** `test_best_is_never_worse_than_the_single_default_start`'s
  docstring claimed a general guarantee (`best` is never worse than the
  single-start default) that the code does not provide — `best` minimises
  only over CONVERGED runs, so a non-converged single-start reading with a
  numerically lower score is correctly NOT preferred, and the test only
  exercises the case both converge. Docstring corrected to state that
  precondition explicitly (and assert it); a new test,
  `test_best_prefers_a_converged_run_over_a_lower_scoring_non_converged_one`,
  exercises the actual guarantee directly via a faked
  `select_lambdas_continuous`.
- **[P2]** `docs/PRODUCT_DIRECTION_2026-07-24.md`'s two harvested items
  gained the house-style `(2nd-order)` tag (NICE-TO-HAVE), matching how
  they were already classified.
- **[P2]** The diagnostic's own `_THREAD_SWEEP = (1, 2, 4)` published only
  the 1/4 readings. Re-ran `--worker 2`; the 2-thread row is now in both
  PART 1/PART 2 tables (ADR-213, this log, the ledger row, the PR body).
- **[P2]** This section's own placeholder ("[to be run before opening the
  PR]") is filled in above with the actual final gate numbers.
- **[P2]** `data8["AttdAge2"]` and its two siblings now carry an explicit
  `.astype(np.float64)` (CLAUDE.md §5).
- **[P2]** The table printer's `(x or float("nan"))` pattern would have
  rendered a legitimate `0.0` score as `nan` (unreachable at these
  magnitudes, but a latent bug). Replaced with an explicit `is not None`
  check.
- **[P2]** `select_lambdas_continuous_multistart`'s "every start rejected
  every trial point" error message overstated what the function itself
  observes (a per-start `PolarisComputationError`, not a claim about each
  start's own internal trial-point bookkeeping). Reworded.

## Follow-ups filed

- PLAN slice 5f (this file, "Gap After" above) — covariate-sharing N>4
  robustness, not blocking.
- `gam_fixed_sp_score_probe.R`/`gam_multiterm_sp_delta_probe.R`'s stale
  `python_opt_log10` refresh (named in slice 5e's own text) — NOT done
  this session (neither script is used by a comparison this slice makes);
  left open, unregistered as its own slice since it is bookkeeping for a
  different measurement's own baseline, not a gap this session opened.
- Whether `fit_polaris_gam` should expose multi-start as an opt-in
  parameter — a small, uncontroversial follow-up (ADR-213 Consequences),
  not filed as its own slice.
