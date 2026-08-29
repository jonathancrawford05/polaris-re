# Session log — 2026-08-29 — Slice 5c: Wood (2011) Appendix B

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5c — `docs/PLAN_mgcv_parity_engine.md`, registered 2026-08-25
(`cecd5ce`) and scoped further by three follow-up sessions
(`a4907f9`, `bd0d624`, `018ac1b`, `4608f16`, `1bd1358`, `2431d7e`) before this
one wrote any production code. The routine's "next unchecked slice" rule
selected it — slice 6 stays BLOCKED until 5c closes or restates.
**PR:** this branch (`claude/intelligent-hamilton-bvll60`), draft.
**ADR:** ADR-210.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite`.
  `apt-get install` failed on stale package-index 404s first (the same
  recurring transient prior sessions' logs record); `apt-get update -qq`
  fixed it. Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the
  routine's expected apt versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for every R invocation.
- `uv run pytest tests/ -m "not slow"` baseline (before any code change):
  3449 passed, 22 skipped, 126 deselected, **5 failed** — the 5 failures
  were `FileNotFoundError` on `data/mortality_tables/*.csv`, the same
  recurring environment-setup gap (generated files, not committed).
  Regenerated via `uv run python scripts/convert_soa_tables.py --source
  pymort --output-dir data/mortality_tables`; re-run clean, 3454 passed, 0
  failed. Confirmed the R-gated test (`test_the_r_script_runs_end_to_end_and_agrees`)
  passes with R installed.

## Gap Before

Measured directly (not inferred from a stored figure), reproducing
`RECALIBRATION_mgcv_parity_2026-08-25.md`'s tier-1 diagnosis independently
before writing any code:

`scripts/gam_fixed_sp_score_probe.R` + `gam_fixed_sp_score_compare.py`
(existing, run for the first time by this session — the workflow step to
dispatch them at tier 3 did not exist yet, per the PLAN's own sequencing
note):

```
point          spread     raw diff (ours - mgcv)
mgcv_opt         6.84    -1734.81581
python_opt       6.04    -1735.66183
flat_2           0.00    -1734.82043
flat_4           0.00    -1734.82219
flat_6           0.00    -1734.82229
mixed_lo_hi      6.00    -1738.72658
mixed_hi_lo      6.00    -1736.41732
mid              2.00    -1734.81997

SPREAD, shipped cut 1e-10: 3.910776
```

`scripts/gam_spread_lambda_probe.R`/`compare.py` (existing) confirmed the
fitter and `log|X'WX+S|` are NOT implicated at up to 12 decades of `lambda`
spread — `max|d eta|` stays at 1e-9 to 1e-12, `logdet gap` stays tiny even
as `cond(H)` reaches 4e11 — isolating the defect to `log|S|+`'s rank
determination alone, exactly as the recalibration note found.

`scripts/gam_hessian_weight_probe.py` (existing) confirmed a SECOND,
independent defect at tier 1: applying only the null-space correction
leaves a residual of 0.003281; applying the observed-Hessian correction
too collapses it to 0.000098 — a ~40x further reduction the finite-difference
weight cannot close further (its own step error sits at that level).

**Tier and provenance, stated per the routine's rule:** all of the above is
TIER 1 (R 4.3.3/mgcv 1.9.1, local apt), and every quantity is DIAGNOSTIC —
`ours` reads `mgcv`'s own `gcv.ubre`/`eta` at the SAME fixed `sp`, so no
column here is committed parity evidence (same status as
`gam_multiterm_sp_delta_probe.R`, ADR-208's amendment).

## Provenance gate (ADR-193), applied before writing code

**Claim sentence:** `gam_reml_appendix_b.appendix_b_transform` computes
`log|S|+`'s rank and value from the individual penalty blocks and their
`lambda`s via Wood (2011) Appendix B's similarity-transform iteration and a
pivoted-QR determinant; `mgcv` computes the equivalent quantity internally
via its own C implementation (never called or read here — this is a
from-the-paper reimplementation, not a transcription, per Anchor 8's
licensing companion); compared via R-FREE unit tests against hand-known
synthetic ranks and invariants (orthogonal invariance, agreement with a
naive computation where the naive computation is reliable), never against
`mgcv`'s own internal state. `Family.observed_information_weight` computes
Wood §3.2's `alpha_i`-scaled weight from `y`/`eta`/`weights` and the
family's own `V'`/`d2mu_deta2`; verified against the textbook canonical-link
identity (`alpha_i == 1` exactly) and a central-difference of the weight's
own definition — again never against `mgcv`. The FIXED-`sp` REML SCORE
comparison (the actual parity claim) reuses ADR-196's existing
`REML_SCORE_CLAIM`/`score_reml_point` machinery unchanged: `reml_score_general`
(now carrying both fixes) evaluated at an independently-converged
`penalized_irls_general` fit vs `mgcv`'s own `gcv.ubre` at the same fixed
`sp`; compared on the pairwise score difference across 8 points (this
session's own extension of the existing 3-point fixture to the N=4 structure).

**Mechanical test, applied to the signature:** neither `appendix_b_transform`
nor `observed_information_weight` accepts any `mgcv`-shaped payload — both
take plain arrays (blocks/lambdas; y/eta/weights) with no R-payload key at
all, structurally unable to read `mgcv`'s own state even by accident.

**Classification, per column:**

| quantity | producer(s) | provenance |
|---|---|---|
| `log\|S\|+`, `rank` (Appendix B) | Python only — R-free unit tests against hand-derived synthetic ground truth | Not a comparison against `mgcv` at all; the parity claim is downstream (the fixed-`sp` score) |
| `alpha_i` / observed weight | Python only — canonical-link identity (derived, not measured) plus a central-difference cross-check of the same definition | Not a comparison against `mgcv`; internal consistency |
| fixed-`sp` REML score (8 points) | `reml_score_general` (independently converged fit) vs `mgcv`'s own `gcv.ubre` at the same fixed `sp` | **INDEPENDENT** — unchanged in kind from ADR-196's own `REML_SCORE_CLAIM`, now measured with the fixed formula |
| free-`sp` selection (N=4) | `gam_model_conformance.fit_free_sp_case`/`compare_free_sp_case` (unchanged code, now scored by the fixed criterion) vs `mgcv`'s own free-`sp` REML selection | **INDEPENDENT** — `sp` itself is a compared quantity here, unchanged classification from ADR-208 |
| "our criterion at mgcv's point vs at our own optimum" | reads `mgcv`'s own selected `log10(sp)` as an INPUT to our own (already-independently-verified) scorer | **DIAGNOSTIC, not parity** — same status as `gam_multiterm_sp_delta_probe.R`; it is the discriminating measurement that separates a criterion defect from an optimiser one, and its whole value is in reading mgcv's OWN point, so it can never be independent by construction |

## The loop

1. **Hypothesis:** Wood's Appendix B, implemented whole and wired into
   `log|S|+` only, closes the fixed-`sp` gap that three prior sessions'
   diagnosis (recalibration note, PR #213 Defect B discovery) already
   localised to two specific, named defects.
2. **The one change (in two parts, both registered in advance as one
   slice):** (a) `gam_reml_appendix_b.py`, new module, wired into
   `reml_score_general`'s `log|S|+` term; (b)
   `Family.observed_information_weight`, wired into the same function's
   `log|X'WX+S|` term. Both were changed together because the PLAN's own
   Defect-B section states fixing A alone leaves a residual B accounts for
   almost exactly — testing them separately first (which this session also
   did, informally, via the manual replication in the "gap after" section
   below) confirmed that relationship before committing the combined fix.
3. **Re-measure:** see Gap After.
4. **Ledger rows:** `docs/CONFORMANCE_LEDGER.md`, two new rows (2026-08-29),
   both tiers.

No dead ends to record from this pass — the two-defect diagnosis from prior
sessions held exactly as characterised, and both defects closed together on
the first implementation attempt (mutation-tested afterward, see below).
The one genuine dead end was in TEST CONSTRUCTION, not the implementation:
two hand-built fixtures for mutation 6 (the transposed `Q_s`) passed
silently before a third, built from the real target model's own blocks,
caught it — recorded in full in ADR-210's mutation table rather than here,
since it is evidence about test coverage, not about the algorithm.

## Gap After

**Fixed-`sp`, tier 1** (manual replication using the actual production
`reml_score_general`, before the workflow step existed):

```
SPREAD (production reml_score_general, both defects fixed): 4.2708006731118076e-07
```

**Fixed-`sp`, tier 3** (`gam_fixed_sp_score_compare.py`'s own "raw diff"
column, CI runs 33267701996 then 33267879635 after a workflow-visibility
fix — see below):

```
SPREAD, shipped cut 1e-10: 0.000000
```

Identical at both tiers to the precision each can show — a ~9.2-million-times
reduction from the 3.910776 gap-before figure.

**Free-`sp`, N=4 (tier 1):** `max_abs_log10_sp_diff = 0.7560` (barely moved
from the pre-fix 0.7766). **Free-`sp`, N=4 (tier 3): 1.0996** — WORSE than
the pre-fix tier-3 reading of 0.6398, and the two tiers disagree with each
other more than either agrees with its own pre-fix reading, which is itself
informative (see below).

**The discriminating measurement (tier 1)** — score `mgcv`'s own selected
point and our optimiser's own converged point under our OWN, now-fixed
criterion:

```
our criterion at PYTHON's own optimum: 612.6630
our criterion at MGCV's own optimum:   612.6108
delta (python - mgcv):                 +0.0523
```

`mgcv`'s point scores BETTER under our own corrected criterion than our own
optimiser's converged point does. **Conclusion: the criterion is no longer
the suspect — `select_lambdas_continuous`'s own convergence on this specific
landscape is.** Per-block, the disagreement concentrates in the by-term's
own `lambda` (python `9.116` vs mgcv `9.872`), matching ADR-208's own
localisation, now under a corrected criterion instead of a suspect one.

**Why the tier-3 free-`sp` residual is WORSE, not just "still present," and
why that does not weaken the diagnosis:** the two tiers ran the R probe's
own `set.seed(20260825)` under different R/BLAS (4.3.3/apt-libblas vs
4.6.1/OpenBLAS), which redraws the same-seeded synthetic data slightly
differently across versions in general (not guaranteed bit-identical RNG
streams across R releases). A criterion-FORMULA bug would be expected to
produce a stable, reproducible error on a fixed problem; an OPTIMISER
convergence problem on a landscape where a criterion is provably correct but
one block's `lambda` is weakly identified is exactly the kind of thing that
CAN swing between two similar-but-not-identical draws. This is consistent
with, not contrary to, the optimiser diagnosis — but it is not proof of it
either, which is why slice 5d's first named action is re-running the
discriminating measurement itself at tier 3, not assuming the tier-1 result
transfers.

## Mutation protocol (full table in ADR-210)

Six mutations applied one at a time (each fully reverted before the next,
verified against a snapshot of the clean file). Two caught by dedicated
tests (skip the pre-step; transpose the accumulated similarity transform).
Four NOT caught by any fixture attempted — including the target model's own
real four-block penalty structure at its own measured `sp`. Recorded
honestly in ADR-210 rather than manufacturing coverage: the four constants
those mutations touch (the null-space truncation itself, QR vs plain
`slogdet`, cube-root vs machine epsilon, `1e-10` vs `eps^0.8`) only matter
in a regime — a dominant block's OWN near-zero eigenvalues corrupted by
genuine floating-point roundoff from an ill-conditioned matrix PRODUCT, not
a clean algebraic null space — that no fixture built by hand or drawn from
this repository's own real models currently exercises.

## Quality Gate

- `uv run ruff format src/ tests/` — clean (2 files reformatted on the first
  pass, both this session's own new files; unchanged on re-run).
- `uv run ruff check src/ tests/ --fix` — clean.
- `uv run pytest tests/ -q -m "not slow"` — **3494 passed, 3 skipped, 126
  deselected, 1 failed** on first run after the code change:
  `test_check_passes_on_the_current_repository`
  (`tests/test_utils/test_measurement_provenance.py`) — `docs/MEASUREMENT_
  unconditional_coverage.md`'s stamp drifted because its transitive import
  closure touched `gam_family.py` (this document's producer,
  `unconditional_coverage_study.py`, imports `gam_uncertainty_mi.wps_correction`,
  which imports `gam_family.poisson_log` — but never calls
  `observed_information_weight` or Appendix B). **Diagnosed as an inert
  edit** (the exact ADR-204 case (c) gap `CONTINUATION_mgcv_parity_engine.md`
  already names as an unfixed schema question) and, rather than asserting
  that judgement, **actually regenerated** the document
  (`uv run python scripts/measurement_stamp.py stamp
  docs/MEASUREMENT_unconditional_coverage.md --run`, ~90s): the reported
  coverage figures (0.7435/0.7815/0.7781/0.8090) are byte-for-byte identical
  to the pre-regeneration document — only the stamp footer changed — which
  is the empirical confirmation the inertness judgement predicted, not an
  assumption standing in for one. Re-run clean after: 3495 passed, 3
  skipped, 126 deselected, 0 failed.
- `uv run pytest tests/qa/ -v --tb=short` — **94 passed.** `tests/qa/golden_outputs/`
  byte-identical (no golden moved).
- `scripts/measurement_stamp.py check` — clean (5 ok, 1 unstamped — the
  pre-existing, not-regenerable `MEASUREMENT_engine_recursion_prework.md`,
  unaffected by this session — 0 drifted).

## Tier-3 dispatch

Two dispatches, same branch, both `workflow_dispatch` on
`mgcv-conformance.yml`:

- **Run 33267701996** (commit `4c178e2`): completed successfully, but the
  new fixed-`sp` compare step's output was redirected ONLY into
  `$GITHUB_STEP_SUMMARY`, invisible to `get_job_logs` — the exact
  "continue-on-error job-summary-artifact limitation"
  `CONTINUATION_mgcv_parity_engine.md`'s backlog names for
  `ks_formula_probe.R`/`smoothcon_lpmatrix_probe.R`, self-inflicted this
  time. Caught before treating the run as sufficient confirmation.
- **Fixed** (`58f0cdb`): `tee`'d the compare script's output to a file
  before the summary redirect, matching the pattern the adjacent
  free-sp/multi-term steps already use.
- **Run 33267879635** (commit `58f0cdb`): completed successfully, both jobs,
  ~80s end to end. Fixed-`sp` spread and free-`sp` `max_abs_log10_sp_diff`
  both read directly from job-log stdout (`get_job_logs`), not inferred from
  a `continue-on-error` step's conclusion — see Gap After above and ADR-210
  for the full tables. Required levels 1-3 of the ten-cell suite still
  agree on both dispatches (no regression). The production module's own
  same-defect check (`Check the production REML score for the same missing
  term`) reads `max abs Hessian diff` of `0.000000e+00`/`4.29e-13`/`5.15e-13`
  across all three free-sp cells — bit-identical, confirming at tier 3 what
  tier 1 already found: no material change for
  `experience_gam_penalized.reml_score`'s own well-conditioned fixture.

Oracle: `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8), R 4.6.1 / mgcv 1.9.4.

## Follow-ups harvested

1st-order (on the epic's critical path):

- **PLAN slice 5d** (registered in this session, in the PLAN itself): localise
  the free-`sp` optimiser-convergence residual on the N=4 structure. Two
  named hypotheses (finite-difference gradient precision on a weakly-identified
  `lambda`; genuine multi-modality), a cheap tier-3 discriminator named
  before either needs new code. Unblocks slice 6.
- **Escalated to the maintainer** (`CONTINUATION`'s "Open questions"): the
  registered prediction's third-branch outcome reopens the epic's cost
  estimate for the free-`sp`/slice-6 path; not a routine's call to size.

2nd-order (nice-to-have, not blocking):

- **The mutation-protocol gap (mutations 1-4 not caught by any fixture
  tried)**, filed in ADR-210. Closing it needs a fixture with a genuinely
  ill-conditioned matrix PRODUCT (not a clean algebraic null space) —
  harder to construct than the two that succeeded, and not attempted
  further this session per the wall-clock guardrail.
- ~~**`scripts/gam_fixed_sp_score_compare.py`'s "tighter cut" column is now
  stale**~~ **FIXED in round 2 below**, not merely filed.

## Round 2 — PR #215 automated review response

The review (2026-08-29, same day) found zero P0s and zero test failures but
held the PR to Changes Requested on one guardrail trip and two P1s. Fixed
all three, plus every P2:

- **[P1-1] Provenance mislabelling, four different ways in four documents.**
  The fixed-`sp` comparison IS INDEPENDENT (the reviewer's own mechanical
  test on `penalized_fit_and_score`'s signature confirmed it), but nothing
  declared a `VerificationClaim` for its actual producer — the ledger cited
  `REML_SCORE_CLAIM`, which covers a DIFFERENT fixture (2-block,
  binomial-logit, `paraPen`-supplied via `score_reml_point`) than this
  session's own (4-block, binomial-cloglog, formula-built via
  `penalized_fit_and_score`). Fixed: declared
  `gam_reml_optimize_conformance.FIXED_SP_MULTITERM_REML_CLAIM` — two
  quantities (the score spread, and a `deviance` companion mirroring
  `REML_SCORE_CLAIM`'s own `scalePenalty`-artifact rebuttal) — on the
  correct producer, `compare_fixed_sp_multiterm_case`. Added `mgcv_deviance`
  to `gam_fixed_sp_score_probe.R`'s payload (was score-only). Corrected the
  now-contradictory "DIAGNOSTIC ONLY" language in the R probe's own header
  comment and both `mgcv-conformance.yml` step comments (three places, all
  written before ADR-210 fixed the criterion and never revisited).
- **[P1-2] `evidence_markdown()` bypassed on a table this PR newly
  publishes to CI.** Fixed as a consequence of P1-1: `gam_fixed_sp_score_compare.py`
  now prints `evidence_markdown(FIXED_SP_MULTITERM_REML_CLAIM)` as its
  headline instead of a hand-written `f"SPREAD, shipped cut ...`. This also
  retired the stale "tighter cut" column (was double-correcting an
  already-fixed score, per this log's own follow-up list above) rather than
  leaving it as a separate cleanup — the rewrite replaced the whole
  comparison loop with a call to `compare_fixed_sp_multiterm_case`, so
  there was no cheaper place to stop.
- **[P1-3] The guardrail trip: an existing test lost its independent
  re-derivation.** `test_score_equals_the_explicit_dp_formula` had started
  calling `observed_information_weight`/`logdet_s_plus` directly — "the
  implementation's own helpers, the same two calls `reml_score_general`
  makes" — which the reviewer flagged as compounding with mutations 1-4
  going uncaught in exactly that code. Fixed: split into two tests, both
  inlining formulas rather than calling the two helpers.
  `..._canonical_link` inlines the plain Fisher weight (valid as "expected"
  only because `binomial_logit` is canonical, `alpha_i == 1` exactly — a
  textbook identity, not a call to the method that asserts it) and the
  naive eigenvalue cut (valid only because this fixture is a single
  well-conditioned block, where Appendix B and the naive cut necessarily
  agree). `..._noncanonical_link` (new) uses `binomial_cloglog` and inlines
  Wood's own `alpha_i = 1 + (y-mu)(V'/V + g''/g')` formula from the paper,
  with a `assert not np.allclose(alpha, 1.0)` sanity check that this
  fixture actually exercises the non-canonical branch Defect B fixes — the
  case `binomial_logit` alone structurally cannot exercise.
- **[P2-1]** `reml_score_general`'s `Raises:` doc was aspirational, not
  accurate — inconsistent `penalty_blocks`/`lambdas` raised a bare
  `IndexError`/`ValueError` before ever reaching
  `appendix_b_transform`'s own (correct) validation. Fixed the CODE, not
  just the doc: two explicit checks now raise `PolarisValidationError`
  before either failure mode can occur.
- **[P2-2]** Added `dtype=np.float64` to the three `np.zeros`/`np.zeros_like`
  calls that omitted it (`gam_reml.py`, `gam_reml_appendix_b.py`),
  consistent with every other array construction in both modules.
- **[P2-3]** Dropped the dead `rng`/`del rng` in
  `test_spread_lambda_stays_close_to_the_flat_baseline_prediction` and
  converted its manual loop to `pytest.mark.parametrize`, per the review's
  own suggestion.
- **[P2-5]** `perf/history.jsonl`'s creep verdict, omitted from round 1:
  `{'has_structural_creep': False, 'has_wall_time_creep': False,
  'has_config_drift': False}` — peak MiB 33 -> 33, no creep.
- **[P2-4]** (order-cap placement) not changed — the 3rd-order
  job-summary-limitation item's `PRODUCT_DIRECTION` placement is correct
  per the reviewer's own reading ("the tag is correct... the item is a
  completed-work record"); this log has no "Parked Polish" section to move
  it to and adding one for a single already-resolved item did not seem
  worth the churn. Noted here instead.

New test coverage added in round 2, all passing:
`tests/test_analytics/test_gam_reml_optimize_conformance.py` (4 tests: the
new comparison function against a self-consistent "mgcv" comparand, a
deliberately-wrong deviance artifact, a length-mismatch rejection, and the
claim's own provenance gate); `test_gam_reml.py`'s split canonical/
non-canonical tests (above). Full suite re-run clean after all fixes:
`tests/test_analytics/` unaffected files unchanged; every touched test file
green.

## Provenance summary (routine requirement)

Every comparison this session reports, restated in one place per
`ROUTINE_MGCV_PARITY.md`'s DELIVER requirement — corrected in round 2 per
[P1-1] above:

- Fixed-`sp` REML score AND deviance (8 points, both tiers): **INDEPENDENT**
  — `gam_reml_optimize_conformance.FIXED_SP_MULTITERM_REML_CLAIM`, declared
  in round 2 for this session's own 4-block/cloglog producer
  (`gam_reml_optimize.penalized_fit_and_score`), NOT a reuse of ADR-196's
  `REML_SCORE_CLAIM` (a different fixture/producer — round 1's session log
  said "unchanged in kind," which was imprecise in exactly the way [P1-1]
  named).
- Free-`sp` selection (N=4, both tiers): **INDEPENDENT** — unchanged in kind
  from ADR-208's own claim (`FREE_SP_MODEL_CLAIM`, same producer).
- "Our criterion at mgcv's point vs ours" (tier 1 only): **DIAGNOSTIC** —
  reads `mgcv`'s own selected point as an input; never claimed as parity
  evidence, exists solely to discriminate a criterion defect from an
  optimiser one.
- Appendix B's `log|S|+`/rank, and the observed-information weight: **not a
  comparison against `mgcv` at all** — R-free unit tests against hand-derived
  synthetic ground truth and a textbook canonical-link identity.
- `experience_gam_penalized.reml_score`'s own same-defect check (both
  tiers): **Python-vs-Python**, current vs corrected formula on the same
  fit — not a claim against `mgcv`, same treatment as ADR-197's own §3.3.

A gap stated without provenance is not a gap statement; this section exists
so that rule is checked, not merely cited.
