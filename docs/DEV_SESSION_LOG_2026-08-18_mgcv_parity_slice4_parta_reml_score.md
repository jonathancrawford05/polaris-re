# Dev Session Log — 2026-08-18 (slice 4, part A)

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 4 (the outer N-dimensional (f)REML optimiser) — the PLAN's next
  unchecked slice, and "the largest single piece of work in the epic." Slices 1
  through 3 were already DONE at the start of this session.
- **Scope decision, made explicit per the routine's own rule** ("if a slice
  proves larger than the PLAN assumed, say so and ship the part that stands
  alone"): slice 4 as PLAN §3 describes it is an N-dimensional Newton/quasi-Newton
  optimiser with Wood's exact derivatives — not a single-session undertaking done
  honestly. This session split it into **part A (the REML score itself,
  generalized to the target's family and to more than two penalty blocks, and
  measured against `mgcv`)** and **part B (the search itself)**, and did only
  part A. Building a search on top of a criterion not yet shown to match `mgcv`
  would not be a meaningful measurement — the score has to be right, or known to
  be wrong, before anything is built to optimise it.
- **Branch:** `claude/zealous-mendel-nlm70c`

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `apt-get update` (stale index, needed
  first — unrelated PPA 403s, main Ubuntu repos fine), then
  `r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 / mgcv 1.9.1 / jsonlite
  1.8.8** — matches the routine's documented expectation exactly, no version
  drift to log. `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- Read, in full: `docs/ROUTINE_MGCV_PARITY.md`, `docs/VERIFICATION_STANDARD.md`,
  `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`,
  `docs/CONFORMANCE_LEDGER.md`, CLAUDE.md, `docs/DECISIONS.md` (ADR-189 + both
  amendments, ADR-190, ADR-191, ADR-192, ADR-193, ADR-194, ADR-195),
  `docs/RUNBOOK_mgcv_conformance.md`.

## Baseline and end state

| | |
|---|---|
| Baseline (`pytest -m "not slow"`, before touching code, R present) | **3285 passed, 5 failed, 22 skipped, 126 deselected** |
| The 5 failures | Pre-existing `data/mortality_tables/*.csv`-absent root cause (the CSVs are not part of this checkout; generating them is a separate, unrelated setup step) — unrelated to this epic, and unrelated to R/mgcv. Not a code regression. |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical, both before and after. |
| End state (`pytest -m "not slow"`, after) | **3295 passed, 5 failed (same), 22 skipped (same), 126 deselected** — the 10-pass increase is exactly this session's new tests (7 in `test_gam_reml.py`, 3 in `test_gam_reml_conformance.py`). |
| `ruff format` / `ruff check` / `mypy` on new/changed files | Clean. |
| Perf row | one row appended (`gam_reml.py`/`gam_reml_conformance.py` are new modules, not docs-only, so ADR-177's exemption does not apply, matching slice 3's own reasoning). **Creep verdict:** no structural creep — `peak_mib` 33 → 33 (delta 0); wall-time ratio 1.343x is advisory only per the maintainer design rule and does not gate. |

## Gap Before

Slice 4 was entirely unbuilt. The only REML-score machinery in the codebase
(`experience_gam_penalized.reml_score`) is hardcoded to the Poisson log-link
with exactly two penalty blocks, and its own outer search
(`select_lambdas_reml`) is a deterministic 2-D grid — correct for the tensor
MI surface, but the target formula needs 13-21 independently-scaled penalty
blocks under a binomial family, where a naively-extended grid would need 4.8
million fits (PLAN §3). No REML score existed anywhere that (a) worked for a
family other than Poisson or (b) accepted more than two hardcoded blocks.

**Stage A / Stage B, existing 10-cell suite** (unchanged, tier 3, oracle
`sha256:0d54c192…` build 8): level 1: AGREES, level 2: AGREES, level 3: AGREES,
level 4: DISAGREES (standing Kass-Steffey formula gap, ADR-190 — not this
slice's concern), level 5: DISAGREES (`gamma`, unsettled). Re-confirmed at
tier 3 this session (run 32086738495) — unchanged, no regression.

**Slice 4, specifically (the gap this session addresses):** zero prior
measurement of any kind — no REML score generalization existed, and no
comparison against `mgcv`'s own multi-block REML criterion had ever been
attempted.

## Gap After

- **The generalized score: built.** `src/polaris_re/analytics/gam_reml.py` —
  `reml_score_general`, a structural generalization of
  `experience_gam_penalized.reml_score` onto `gam_fit`'s general IRLS core.
  Proven a strict superset by three bit-for-bit regression tests. Known-scale
  families only (a deliberate, target-motivated cut — the target's own family,
  binomial, is known-scale).
- **The Stage-C comparison: built and run.**
  `src/polaris_re/analytics/gam_reml_conformance.py`'s `REML_SCORE_CLAIM`
  declares `reml_score_pairwise_diff` INDEPENDENT; `score_reml_point`'s
  signature takes no R-payload-shaped argument at all. `require_parity_evidence`
  gates it (`tests/test_analytics/test_gam_reml_conformance.py`).
- **Measured, tier 1 and tier 3 identical: DISAGREES.** The fit itself is
  correct — a committed, INDEPENDENT `deviance` comparison
  (`compare_reml_deviance`, added in review response — see below) matches
  `mgcv`'s to ~1e-11 at every point; the score's dependence on `(sp1, sp2)`
  does not. **All three** pairwise score differences miss the declared 1e-6
  tolerance after differencing out any additive convention offset (two by
  ~0.74, one by ~9.3e-4 — smaller, but still ~935x the tolerance, not
  agreement) — five orders of magnitude above BLAS/version noise, so this is
  a real formula gap, not an artifact of the tier or the oracle build.
- **`docs/DECISIONS.md`: ADR-196** records the design decisions, both tiers'
  measurements, why this is a genuine INDEPENDENT result rather than a harness
  defect, and a named next hypothesis (corrected in review response after the
  original localizing argument was found circular — see below).
- **PLAN/CONTINUATION updated:** slice 4 marked IN PROGRESS, part A DONE, part
  B (the search itself) explicitly NOT STARTED and why.

## Hypotheses Tried

1. **The naive structural generalization of the already-verified Poisson REML
   score — same formula shape, only the deviance and IRLS working weight
   swapped for a general `Family` — reproduces `mgcv`'s REML criterion once
   more than one independently-scaled penalty block is in play (matching PLAN
   §6's registered-prediction spirit for slices 2-3, extended to slice 4).**
   - Before any R round trip: verified the generalization is a provable
     superset of the existing Poisson score (bit-for-bit at `gamma=1`, at
     `gamma=1.4` with an offset, and at zero penalty).
   - **PARTIALLY REFUTED at tier 1 on the first measurement**: the fit
     (deviance) matches to float precision, but the score's pairwise
     differences do not — all three pairs miss the declared tolerance (two by
     ~0.74, one by ~9.3e-4).
   - **CONFIRMED unchanged at tier 3, identical to every printed digit** — not
     a tier-1/BLAS artifact.
2. **The residual is a purely additive convention offset (like the one ADR-189
   amendment 1 found for the single-block Poisson case), and differencing
   pairwise cancels it.**
   - **REFUTED.** If it were a constant offset, ALL pairwise differences would
     be numerically equal (not necessarily zero, but equal to each other)
     once differenced — they are not: two residuals are ~0.74 and the third
     is ~800x smaller (~9.3e-4). The offset is not constant — it is a real
     function of `(sp1, sp2)`.
3. **The naive combined-penalty generalized log-determinant (`log|S_lambda|_+`,
   sum the blocks then eigendecompose) is where the gap concentrates.**
   - **Original session reasoning was circular — caught same-day in PR #203
     review [P1-3].** The original argument: "`(1,1)` and `(5,0.2)` share the
     same naive `logdet_s` (both blocks are rank-1 second-difference
     penalties, so `logdet_s` depends only on the product `sp1*sp2`, which is
     1 at both points), yet that pair carries the largest residual — so the
     naive `logdet_s` is not the culprit." That does not follow: the measured
     *residual* between two points equals `½·(logdet_mgcv(A) −
     logdet_mgcv(B))` if the naive `logdet_s` were the sole error source,
     and that vanishes only if `mgcv`'s OWN `logdet_s` is *also* a function
     of `sp1*sp2` alone at those points — which is exactly the fact in
     question, not something established independently. Second: this
     fixture's two blocks have disjoint column supports (verified on the
     matrices), so their null spaces never interact — a fixture built that
     way cannot test the hypothesis "`mgcv` treats interacting null spaces
     differently" either way. **Not concluded which term is actually
     wrong** — CLAUDE.md forbids guessing a derivation past what was
     measured. Corrected next hypothesis: build a fixture with genuinely
     overlapping/interacting penalty blocks, then read `mgcv`'s multi-penalty
     treatment from Wood 2011 directly (ADR-190 decision 3's GPL/MIT
     precedent) rather than iterating on the naive formula's constants
     (Anchor 8: derive, do not tune).

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container),
  `OPENBLAS_NUM_THREADS=1`.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run
  [32086738495](https://github.com/jonathancrawford05/polaris-re/actions/runs/32086738495)
  on commit `6564b79`, both jobs completed in ~57s (01:02:04 to 01:03:02 UTC).

## Provenance

Every quantity this session reported as a comparison, and what produced each
side (ADR-193):

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `reml_score_pairwise_diff` | `gam_reml.reml_score_general`, evaluated at coefficients from an independently-converged `gam_fit.penalized_irls_general` fit — `score_reml_point`'s signature takes only plain arrays and the `sp` setting itself, no R-payload-shaped argument at all | `mgcv gam(..., method='REML')$gcv.ubre` at the same fixed `sp` point | **INDEPENDENT** |
| `deviance` | `gam_reml_conformance.deviance_reml_point`/`compare_reml_deviance`, using the SAME independent fit `score_reml_point` scores — added in review response (PR #203 review [P1-1]) after the original session cited this comparison in prose with no committed producer | `mgcv m$deviance` at the same fixed `sp` point | **INDEPENDENT** — declared as the second `ComparedQuantity` on `REML_SCORE_CLAIM`, not a diagnostic aside; it is what licenses reading the score disagreement as a formula gap rather than a fit bug or a rescaled-penalty artifact |
| `coef` | *(not compared — Anchor 2)* | *(not compared)* | **N/A, deliberately** |

**Tier 3 measurement table** (read directly from job-log stdout via
`get_job_logs`, the same discipline slice 2's methodology fix established —
not inferred from a masked `continue-on-error` step conclusion):

| point A | point B | python diff | r diff | residual | agrees (tol 1e-6) |
|---|---|---:|---:|---:|---|
| `(1, 1)` | `(5, 0.2)` | -0.469596 | 0.271677 | -0.741273 | False |
| `(1, 1)` | `(0.5, 8)` | -0.0072338 | -0.00816837 | 0.000934569 | False |
| `(5, 0.2)` | `(0.5, 8)` | 0.462363 | -0.279845 | 0.742208 | False |

Identical at every printed digit between tier 1 and tier 3.
`REML_SCORE_CLAIM` (`gam_reml_conformance.py`) declares
`reml_score_pairwise_diff` `INDEPENDENT`, gated by `require_parity_evidence`
in `tests/test_analytics/test_gam_reml_conformance.py`. This is the epic's
first Stage-C REML-score comparison of any kind — and, per ADR-193's own
standard, an INDEPENDENT comparison that DISAGREES is a real result, not a
failed session: the two-block REML criterion is now known, with evidence, not
to match `mgcv`, where before this session nothing had ever measured it.

## Review Response (PR #203, automated review)

The automated PR review found 5 [P1]s and 2 [P2]s, all about the accuracy and
reproducibility of the record rather than shipped code (zero [P0]s, zero test
failures). All 5 [P1]s and one [P2] were fixed; the second [P2] (a variable
name inversion already present on `main` in `gam_fit.py`) was left, per the
review's own recommendation, for a future one-line sweep rather than expanded
in this PR.

- **[P1-1] The `deviance` agreement had no committed producer.** Fixed:
  `deviance_reml_point`/`compare_reml_deviance` added to
  `gam_reml_conformance.py`, `deviance` declared as a second `ComparedQuantity`
  on `REML_SCORE_CLAIM`, printed in the CI job summary, and asserted (not just
  printed) in `test_the_r_probe_runs_end_to_end`.
- **[P1-2] "2 of 3 pairs disagree" contradicted the declared 1e-6 tolerance —
  all three do.** Fixed throughout: this log, ADR-196, `CONTINUATION`,
  `PRODUCT_DIRECTION`, and the ledger rows now say "all three pairwise
  differences disagree (two by ~0.74, one by ~9.3e-4 — ~935x the tolerance,
  smaller but not agreement)."
- **[P1-3] ADR-196's localizing inference about `logdet_s` did not follow, and
  the fixture cannot test the hypothesis it named.** The argument assumed
  `mgcv`'s own `logdet_s` behaves like the naive one at the two matching
  points, which is exactly what was in question; separately, this fixture's
  two blocks have disjoint column supports, so a hypothesis about interacting
  null spaces cannot be tested by it either way. Fixed: ADR-196 §"What is NOT
  concluded" rewritten with the correction stated in place (no measured
  number changed), and every downstream doc that repeated the original
  inference updated to match.
- **[P1-4] `PRODUCT_DIRECTION` carried the same item as both open (original
  entry) and closed (a second, struck-through harvest entry).** Fixed: the
  original entry is now struck and points at the harvest section instead of
  duplicating it.
- **[P1-5] The quasi-Poisson 3rd-order item was written into
  `PRODUCT_DIRECTION` instead of this log's Parked Polish** — the order cap's
  first 3rd-order item, and the rule is that 3rd-order-or-deeper items are
  logged once in Parked Polish, not promoted. Fixed: moved below.
- **[P2-1] The block-summing test was tautological and its docstring
  overclaimed.** Fixed: docstring corrected to state what the test actually
  shows (determinism/purity) rather than "licenses N-block support," which is
  a fact about the function's type signature, not something the test
  demonstrates empirically.
- **[P2-2] `deta_dmu` names `dmu/deta`** (`gam_reml.py:107`, matching the same
  inversion already on `main` in `gam_fit.py`). Not fixed here — the review
  recommended a future one-line sweep across all sites rather than expanding
  this PR's diff for a naming issue with no numeric effect.

No committed number changed as a result of this review round — the tier-1
and tier-3 score-disagreement figures are exactly as first measured. What
changed is: a new, committed `deviance` comparison (previously cited only in
prose); corrected prose describing an unchanged tolerance evaluation; and a
corrected (not retracted) inference about where to look next. Re-confirmed at
tier 3 on the fix commit — see Oracle Version / Provenance above, updated
after the fix.

## What Was Done

1. `src/polaris_re/analytics/gam_reml.py` — new module: `reml_score_general`,
   generalizing `experience_gam_penalized.reml_score` onto `gam_fit`'s general
   IRLS core, known-scale families only.
2. `src/polaris_re/analytics/gam_reml_conformance.py` — new module:
   `REML_SCORE_CLAIM`, `score_reml_point`, `compare_reml_points`,
   `deviance_reml_point`, `compare_reml_deviance` (the latter two added in
   review response, [P1-1]).
3. `scripts/gam_reml_probe.R` — new probe script, following the
   `gam_family_probe.R` pattern: a shared two-block binomial/logit design,
   fitted at three fixed `(sp1,sp2)` points via `paraPen` with
   `method="REML"`.
4. `.github/workflows/mgcv-conformance.yml` — new diagnostic probe step ("Fit
   the shared two-block binomial design…") in the R job, new comparison step
   ("Compare the two-block REML score…") in the compare job — printing to
   stdout from the start.
5. `docs/DECISIONS.md` — **ADR-196**: the design decisions, both tiers'
   measurements, and the named next hypothesis.
6. `docs/CONFORMANCE_LEDGER.md` — two new rows: the tier-1 hypothesis and its
   tier-3 confirmation.
7. `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`
   — slice 4 marked IN PROGRESS, part A DONE, part B explicitly NOT STARTED.
8. `docs/PRODUCT_DIRECTION_2026-07-24.md` — follow-ups harvested (below).
9. `perf/history.jsonl` — one row for this PR's initial open (ADR-177).

## Tests Added

- `tests/test_analytics/test_gam_reml.py` — 7 tests: three bit-for-bit
  regression tests against the already-verified Poisson score (`gamma=1`,
  `gamma=1.4` with an offset, zero penalty), a binomial-logit finiteness
  check, a block-summing determinism test (docstring corrected in review
  response, [P2-1], to state what it actually shows), and two
  input-validation tests (rejects estimated-dispersion families, rejects
  non-positive `gamma`).
- `tests/test_analytics/test_gam_reml_conformance.py` — 4 tests (was 3;
  [P1-1] added one): the score claim is a genuine parity claim
  (`require_parity_evidence` does not raise), the mechanical-test signature
  checks for both `score_reml_point` and `deviance_reml_point` (neither takes
  an R-payload-shaped argument), and the R-gated end-to-end machinery test —
  which now ASSERTS `deviance` agreement directly (a real, reproducible
  result) while still deliberately NOT asserting score agreement (see its
  docstring for why).

## Acceptance Criteria

Slice 4 has no PLAN-stated acceptance criteria yet — this session's own
scope split (part A / part B) is not yet reflected as formal PLAN criteria,
since the PLAN pre-dates this session's discovery that the score itself needs
to be verified before the search. Recorded as a self-imposed standard instead:

| Self-imposed criterion (this session) | Status | Notes |
|---|---|---|
| The generalized score reduces bit-for-bit to the existing verified Poisson score | ✅ | 3 regression tests |
| The fit itself (deviance) matches `mgcv`'s | ✅ | ~1e-11 at every point, all 3 points, tier 1 and tier 3 identical — committed comparison (`compare_reml_deviance`) |
| The generalized score's dependence on `(sp1,sp2)` reproduces `mgcv`'s, for the target's own family (binomial), across more than one penalty block | ❌ | All 3 pairs disagree against the declared 1e-6 tolerance (two by ~0.74, one by ~9.3e-4), tier 1 and tier 3 identical — a genuine, characterized finding (ADR-196), not resolved this session |
| The outer N-dimensional search itself | **Not attempted** | Deliberately deferred — see the scope decision above |

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md`:

1. **The multi-block REML score formula gap (ADR-196)** — the named next
   hypothesis, corrected in review response ([P1-3]): build a fixture with
   genuinely overlapping/interacting penalty blocks (this session's has
   disjoint supports, so it cannot settle the question), then read `mgcv`'s
   actual multi-penalty treatment from Wood 2011 directly. 1st-order — blocks
   everything downstream of slice 4.
2. **Slice 4 part B — the N-dimensional search itself.** Cannot proceed
   meaningfully until part A's formula gap is closed or the search's design is
   re-scoped around a criterion known to disagree. 1st-order — the epic's own
   next concrete step, but gated on (1).

Not harvested into `PRODUCT_DIRECTION` — see Parked Polish below instead
(PR #203 review [P1-5]: 3rd-order-or-deeper items are logged once here, not
promoted into the harvest, per the order-classification cap).

## Parked Polish

1. **Quasi-Poisson's estimated-dispersion REML criterion.** `reml_score_general`
   raises on `dispersion_fixed=False` families rather than silently reusing a
   formula not derived for an estimated-dispersion criterion — `mgcv` profiles
   `phi` out of the marginal likelihood rather than treating it as fixed, a
   materially different derivation. The target formula's own family
   (binomial) never needs it. Only worth building if a future model form
   actually needs quasi-Poisson under REML selection — no known need today.
   3rd-order, PARKED — this repo's first item to reach 3rd-order (PR #203
   review [P1-5] caught an earlier revision of this session's harvest writing
   it into `PRODUCT_DIRECTION` instead of here; fixed in review response).
2. **`deta_dmu` names `dmu/deta`** in `gam_reml.py:107` — used correctly
   (as `(dmu/deta)^2/V(mu)`), only the name is inverted, matching the same
   pre-existing inversion in `gam_fit.py:106,151` on `main`. A future
   one-line sweep across all three sites, not urgent (PR #203 review
   [P2-2]).

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens.
No `products/`, `reinsurance/` or CLI code moved.
