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
  correct (deviance matches `mgcv`'s to ~1e-11 at every point); the score's
  dependence on `(sp1, sp2)` does not. 2 of 3 pairwise score differences
  disagree by ~0.74 after differencing out any additive convention offset —
  five orders of magnitude above BLAS/version noise, so this is a real formula
  gap, not an artifact of the tier or the oracle build.
- **`docs/DECISIONS.md`: ADR-196** records the design decisions, both tiers'
  measurements, why this is a genuine INDEPENDENT result rather than a harness
  defect, and the named next hypothesis (the naive "sum blocks, eigendecompose
  the sum" `logdet_s` is not, on this evidence, where the gap concentrates).
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
     differences do not — 2 of 3 pairs disagree by ~0.74.
   - **CONFIRMED unchanged at tier 3, identical to every printed digit** — not
     a tier-1/BLAS artifact.
2. **The residual is a purely additive convention offset (like the one ADR-189
   amendment 1 found for the single-block Poisson case), and differencing
   pairwise cancels it.**
   - **REFUTED.** If it were a constant offset, ALL pairwise differences would
     agree once differenced. Only 1 of 3 pairs agrees (`(1,1)-(0.5,8)`,
     residual 0.000935); the other two disagree by ~0.74. The offset is not
     constant — it is a real function of `(sp1, sp2)`.
3. **The naive combined-penalty generalized log-determinant (`log|S_lambda|_+`,
   sum the blocks then eigendecompose) is where the gap concentrates.**
   - **Evidence points away from it, not conclusively resolved.** By this
     fixture's construction, `(1,1)` and `(5,0.2)` share the same naive
     `logdet_s` (both blocks are rank-1 second-difference penalties, so
     `logdet_s` depends only on the product `sp1*sp2`, which is 1 at both
     points) — yet that pair carries the LARGEST residual of the three. If the
     naive `logdet_s` were the sole culprit, these two points would agree.
     They do not. **Not concluded which term is actually wrong** — CLAUDE.md
     forbids guessing a derivation past what was measured. Named as the next
     session's starting hypothesis (read `mgcv`'s multi-penalty treatment from
     Wood 2011 directly, per ADR-190 decision 3's GPL/MIT precedent) rather
     than iterated on further this session (Anchor 8: derive, do not tune).

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
| `deviance` (diagnostic, not part of `REML_SCORE_CLAIM`) | the same independently-converged Python fit's own `family.deviance(y, mu, weights)` | `mgcv m$deviance` | **INDEPENDENT** — used this session to isolate the fit from the score, not compared as a slice-4 acceptance criterion |
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

## What Was Done

1. `src/polaris_re/analytics/gam_reml.py` — new module: `reml_score_general`,
   generalizing `experience_gam_penalized.reml_score` onto `gam_fit`'s general
   IRLS core, known-scale families only.
2. `src/polaris_re/analytics/gam_reml_conformance.py` — new module:
   `REML_SCORE_CLAIM`, `score_reml_point`, `compare_reml_points`.
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
  check, an N-block-equals-pre-summed-penalty equivalence test, and two
  input-validation tests (rejects estimated-dispersion families, rejects
  non-positive `gamma`).
- `tests/test_analytics/test_gam_reml_conformance.py` — 3 tests: the claim is
  a genuine parity claim (`require_parity_evidence` does not raise), the
  mechanical-test signature check (`score_reml_point` takes no R-payload-shaped
  argument), and the R-gated end-to-end machinery test (deliberately does NOT
  assert agreement — see its docstring for why).

## Acceptance Criteria

Slice 4 has no PLAN-stated acceptance criteria yet — this session's own
scope split (part A / part B) is not yet reflected as formal PLAN criteria,
since the PLAN pre-dates this session's discovery that the score itself needs
to be verified before the search. Recorded as a self-imposed standard instead:

| Self-imposed criterion (this session) | Status | Notes |
|---|---|---|
| The generalized score reduces bit-for-bit to the existing verified Poisson score | ✅ | 3 regression tests |
| The generalized score's dependence on `(sp1,sp2)` reproduces `mgcv`'s, for the target's own family (binomial), across more than one penalty block | ❌ | 2 of 3 pairs disagree by ~0.74, tier 1 and tier 3 identical — a genuine, characterized finding (ADR-196), not resolved this session |
| The outer N-dimensional search itself | **Not attempted** | Deliberately deferred — see the scope decision above |

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md`:

1. **The multi-block REML score formula gap (ADR-196)** — the named next
   hypothesis (read `mgcv`'s actual multi-penalty treatment from Wood 2011
   directly, since the naive combined-eigendecomposition `logdet_s` is not,
   on this evidence, where the gap concentrates). 1st-order — blocks
   everything downstream of slice 4.
2. **Quasi-Poisson's estimated-dispersion REML criterion** — explicitly out
   of `reml_score_general`'s scope, and the target formula never needs it.
   3rd-order, PARKED.
3. **Slice 4 part B — the N-dimensional search itself.** Cannot proceed
   meaningfully until part A's formula gap is closed or the search's design is
   re-scoped around a criterion known to disagree. 1st-order — the epic's own
   next concrete step, but gated on (1).

## Parked Polish

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens.
No `products/`, `reinsurance/` or CLI code moved.
