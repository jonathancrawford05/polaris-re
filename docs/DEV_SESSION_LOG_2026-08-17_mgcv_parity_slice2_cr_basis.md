# Dev Session Log — 2026-08-17

> **Amended same day (PR #201 review [P1]).** The Provenance table below
> originally tagged `knots` as `INDEPENDENT` alongside `design_X`/`penalty_S`/
> `rank`. That overstated 3 of the 5 cases: when knots are supplied, neither
> side computes them — both relay the same hand-declared literal (`ECHO`), and
> only the two default-knot cases are a genuine independent computation.
> `knots` was removed from `CR_BASIS_CLAIM` rather than mistagged (still
> checked, just outside the formal parity claim); the table below is corrected
> to match. See ADR-194's own amendment for the full explanation.

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 2 (`bs = "cr"`, supplied and default knots) — **finished this session**,
  per `docs/PLAN_mgcv_parity_engine.md`
- **Branch:** `claude/zealous-mendel-e3a738`

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `apt-get update` (stale index, needed first),
  then `r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 / mgcv 1.9.1**, matching
  the routine's documented expectation exactly — no version drift to log.
  `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- `docker info` not checked this session — CI (tier 3) was the actual round trip used;
  tier 2 was never attempted.
- Read `docs/PLAN_mgcv_parity_engine.md` (slice 2's own section and Anchors 1/2/4),
  `docs/CONTINUATION_mgcv_parity_engine.md`, `docs/CONFORMANCE_LEDGER.md`,
  `docs/VERIFICATION_STANDARD.md`, CLAUDE.md, `docs/DECISIONS.md` (ADR-189 + both
  amendments, ADR-190, ADR-191, ADR-192, ADR-193), `docs/RUNBOOK_mgcv_conformance.md`.

## Baseline and end state

| | |
|---|---|
| Baseline (`make test`, before touching code, R present) | **3231 passed, 5 failed, 25 skipped, 126 deselected** |
| The 5 failures | Same pre-existing `data/mortality_tables/*.csv`-absent root cause (2nd-order NICE-TO-HAVE, orthogonal to this epic, unaddressed here). |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical. |
| End state (`make test`, after) | **3257 passed, 5 failed (same), 22 skipped, 126 deselected** — the 26-test increase is the new `test_gam_basis_cr.py` (17) plus new/extended tests in `test_gam_stage_a.py`; the 3-skip decrease is R-gated tests (including two new ones this session) flipping from skip to pass now that R is installed. |
| Perf row | one row appended (`gam_basis_cr.py`/`gam_stage_a.py` touched, so ADR-177's docs-only exemption does not apply). **Creep verdict:** no structural creep — `peak_mib` 33 → 33 (delta 0). Wall-time recent/baseline ratio 1.198x is advisory-only cross-machine noise. |

## Gap Before

Slice 2 was entirely unbuilt: no Python `cr` basis existed anywhere in the codebase
(the shipped fitter builds a B-spline/P-spline tensor, a different construction —
`experience_gam_penalized._basis`). Both existing Stage-A paths were honestly
harness, not parity: slice 1's `design_X`/`penalty_S` are ECHO (Python supplies them
to mgcv and reads them back), slice 1b's columns are all TRANSPORT (`extract_smooth_terms`
parses the R payload and is compared against that same payload). Neither could
demonstrate — or refute — basis agreement.

**Stage A / Stage B, existing 10-cell suite** (unchanged, tier 3, oracle
`sha256:0d54c192…` build 8): level 1: AGREES, level 2: AGREES, level 3: AGREES,
level 4: DISAGREES (standing Kass-Steffey formula gap, ADR-190 — not this slice's
concern), level 5: DISAGREES (`gamma`, unsettled). Re-confirmed at tier 3 this
session (run 32033738454) — unchanged, no regression.

**Primary metric (the MI contrast on the pinned grid):** still not computable —
slices 4-5 (the outer optimiser, the MI term) do not exist yet. Unchanged.

**Basis parity, specifically (the gap this slice closes):** zero — no comparison in
the codebase had ever compared a Python-computed basis against an mgcv-computed one.

## Gap After

- **The Python `cr` basis: built.** `src/polaris_re/analytics/gam_basis_cr.py` —
  Wood's natural-cubic-spline construction (`cr_basis`), `mgcv`'s own default knot
  placement (`cr_default_knots`), and the `colMeans`-QR identifiability constraint
  (`absorb_sum_to_zero_constraint`). Every non-textbook detail — default knots,
  which vector the constraint absorbs, the `scale.penalty` rescale — was read
  directly out of `mgcv`'s own R source (`deparse()` on the installed tier-1
  package), not guessed, per CLAUDE.md's rule against guessing a penalty
  derivation.
- **The independent producer: wired in.** `build_python_cr_term` (`gam_stage_a.py`)
  builds a `TermExtract` from `x` and a `TermSpec` alone — never from the R
  payload — and `CR_BASIS_CLAIM` declares `design_X`/`penalty_S`/`rank`/`knots` all
  `INDEPENDENT`. `gam_term_extract.R` now also exports the covariate `x` (shared
  recipe context, not a compared quantity) so Python can evaluate its own basis at
  the same points R's RNG drew.
- **Verified against the target formula's own knots, not a stand-in.** Extended the
  harness's original 3 cases (default k=8/k=13, supplied k=8) with 2 more using PLAN
  §1's literal `AttdAge` (k=13) and `PolYear` (k=6) knot vectors, so acceptance
  criterion #1's "for the target's own knot vectors ... at both k=13 and k=6" is
  satisfied against the real numbers, not a proxy. `extract_smooth_one` gained an
  `x_range` parameter so both new cases draw `x` from inside `[knots[0], knots[-1]]`
  — extrapolation is explicitly unverified (module docstring) and these cases must
  not exercise it.
- **Confirmed at both tiers, and tier 3 with real numbers this time.** Tier 1: all 5
  cases exact — diffs ~1e-14 (float round-trip noise). Tier 3 (CI run 32033738454,
  ~56s round trip): same, ~1e-14, read directly from job-log stdout. This closes a
  real limitation slice 1b's tier-3 row hit — see "A methodology fix" below.
- **A methodology fix, not just a slice.** The existing per-term comparison step is
  `continue-on-error: true` and writes only to the job-summary file, which lives
  behind a blob-storage host this environment's egress policy has blocked before
  (confirmed again this session: `curl` to the presigned URL got `CONNECT tunnel
  failed, response 403`). That left slice 1b's tier-3 confirmation unable to go past
  "the step didn't raise an exception" — a real but weak reading. This session added
  one line — `print(report)` alongside the existing file write — so the identical
  report lands in plain job-log text, retrievable via the ordinary `get_job_logs`
  API. Verified working: the second CI dispatch's job-log output is the actual
  per-metric table, not a masked conclusion. This fix benefits every later slice's
  tier-3 reading, not only this one.
- **Slice 2 acceptance criteria (PLAN): all met** — see the table below.
  `docs/PLAN_mgcv_parity_engine.md` and `docs/CONTINUATION_mgcv_parity_engine.md`
  updated to DONE; slice 3 (families/links/weights) is genuinely unblocked and
  marked NEXT.

## Hypotheses Tried

1. **My best recollection of Wood's natural-cubic-spline formula (interior
   second-derivative system, per-interval Hermite basis) reproduces `mgcv`'s
   `smoothCon(bs="cr", absorb.cons=FALSE)$X`/`$S` once the knot vector matches
   (PLAN §6's registered prediction).**
   - Verified the **unconstrained** design (`design_X`) matched to ~1e-14 on the
     first attempt — the recursion itself needed no correction.
   - The **unconstrained** penalty (`penalty_S`) did NOT match on the first attempt
     — off by a constant multiple (ratio identical across every matrix entry,
     0.12734390967447237 for the `default-knots-k8` case). **CONFIRMED as a missed
     rescale, not a wrong recursion**: `mgcv`'s `smoothCon` has its own
     `scale.penalty` argument (default `TRUE`, unrelated to the `gam.control
     (scalePenalty=)` this repo's `raw` path already uses) that divides `S` by
     `norm_1(S)/norm_inf(X)²`. Read from `smoothCon`'s own source (`deparse()`),
     applied, and the ratio closed to ~1e-14. **Hypothesis 1 CONFIRMED at tier 1.**
2. **The identifiability constraint `absorb.cons=TRUE` absorbs is `colMeans(X)`
   (not `colSums`), and the null space is computed via a full QR of the
   constraint's transpose, with `numpy.linalg.qr(mode="complete")` reproducing
   R's `qr()`/`qr.Q()` bit-for-bit on a single-column input.**
   - Read `smoothCon`'s source directly: confirmed `C <- matrix(colMeans(sm$X), 1,
     ncol(sm$X))` for this case (no `by`, no factor, no `g.index`), and the
     null-space construction via `qr(t(sm$C))` / `qr.qty`.
   - Measured the Householder sign convention numerically: R's `qr()`/`qr.Q(...,
     complete=TRUE)` on a test vector gave `R[1,1] = -4.527693`, matching
     `alpha = -sign(x[0])·‖x‖` exactly; `numpy.linalg.qr(..., mode="complete")` on
     the identical vector gave a bit-identical `Q`. **CONFIRMED at tier 1** — the
     constrained `design_X`/`penalty_S` matched `smoothCon(absorb.cons=TRUE)` to
     ~1e-14 using this exact construction, no rotation-of-the-null-space mismatch.
3. **Default knot placement is `quantile(unique(x), seq(0, 1, length = k))`, R's
   type-7 quantile, and `numpy.quantile(..., method="linear")` reproduces it.**
   - Read directly from `mgcv:::smooth.construct.cr.smooth.spec`'s source. **CONFIRMED
     at tier 1** — knot diffs ~1e-14 to ~7e-15 across the default-knot cases.
4. **The full construction (1-3 together) reproduces `smoothCon(bs="cr",
   absorb.cons=TRUE)` on the target formula's own `AttdAge`(k=13)/`PolYear`(k=6)
   knot vectors, not just the harness's original synthetic cases.**
   - Extended `gam_term_extract.R` with two more cases using the literal target
     knots (an `x_range` parameter added so `x` stays inside the knot span,
     avoiding the unverified extrapolation case). **CONFIRMED at tier 1** — diffs
     ~1.5e-14 / ~3.6e-15 to ~8.0e-15, same order as the other three cases.
   - **Re-measured at tier 3** (CI run 32033738454, oracle `sha256:0d54c192…` build
     8): all 5 cases agree to the same order (~1e-14), read directly from job-log
     stdout after the methodology fix. **CONFIRMED at tier 3 — settled.**

No hypothesis stood refuted this session. The one genuine correction needed
(hypothesis 1's missing penalty rescale) was found and fixed within the same
tier-1 iteration, before any tier-3 dispatch — exactly how the iterate-locally,
verify-on-tier-3 loop is meant to work.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container), `OPENBLAS_NUM_THREADS=1`.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run [32033738454](https://github.com/jonathancrawford05/polaris-re/actions/runs/32033738454)
  on commit `7408ecc` (the first dispatch, on `6e619ce`, hit the job-summary
  artifact limitation and was superseded by this one after the stdout-print fix).

## Provenance

Every quantity this session reported as a comparison, and what produced each side
(ADR-193):

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `design_X` | `gam_basis_cr.cr_basis` + `absorb_sum_to_zero_constraint` (Wood's construction, from `x` and a knot vector, never reading mgcv's output) | `mgcv smoothCon(s(x, bs="cr", k), absorb.cons=TRUE)$X` | **INDEPENDENT** |
| `penalty_S` | `gam_basis_cr.cr_basis` (Wood's integrated-squared-second-derivative penalty, `mgcv`'s own `scale.penalty` rescale reproduced from source) | `mgcv smoothCon(...)$S` | **INDEPENDENT** |
| `rank` | `numpy.linalg.matrix_rank` on the Python-constrained penalty block | `mgcv smoothCon(...)$rank` (mgcv's own rank determination) | **INDEPENDENT** |
| `knots` (default-knot cases only) | `gam_basis_cr.cr_default_knots` (own quantile computation) | `mgcv smoothCon(...)$xp` | **INDEPENDENT** |
| `knots` (supplied-knot cases) | the same hand-declared literal, relayed unchanged | `mgcv smoothCon(...)$xp` — echoes what it was handed | **ECHO, not INDEPENDENT — excluded from `CR_BASIS_CLAIM`** |

This is the epic's first table with `design_X`/`penalty_S`/`rank` all `INDEPENDENT`
— `CR_BASIS_CLAIM` (`src/polaris_re/analytics/gam_stage_a.py`), gated by
`require_parity_evidence` in both the new pytest coverage and the R-gated
end-to-end test. `knots` is checked (and agrees on all 5 cases) but is not part of
the claim, for the reason the amendment above states. Contrast with the
existing `RAW_PATH_CLAIM` (ECHO on `design_X`/`penalty_S`, INDEPENDENT only on
`rank`) and `SMOOTH_PATH_CLAIM` (TRANSPORT on everything) — both unchanged by this
session, both still used as the harness/reference machinery slice 2's comparison
runs against.

## What Was Done

1. `src/polaris_re/analytics/gam_basis_cr.py` — new module: `cr_default_knots`,
   `cr_basis`, `absorb_sum_to_zero_constraint`.
2. `src/polaris_re/analytics/gam_stage_a.py` — `CR_BASIS_CLAIM`,
   `build_python_cr_term`; module docstring updated to reflect slice 2 landing.
3. `scripts/gam_term_extract.R` — `extract_smooth_one` now also exports the
   covariate `x` and takes an `x_range` parameter; two new cases
   (`target-attdage-k13`, `target-polyear-k6`) added alongside the original three.
4. `.github/workflows/mgcv-conformance.yml` — extended the per-term comparison step
   to also build and compare the Python `cr` basis (slice 2's table), and to
   `print()` the full report to stdout (the methodology fix).
5. `docs/DECISIONS.md` — **ADR-194**: the construction decisions, both tiers'
   measurements, and the methodology fix.
6. `docs/CONFORMANCE_LEDGER.md` — two new rows: the tier-1 hypothesis (design
   agreed immediately, penalty needed the `scale.penalty` fix) and its tier-3
   confirmation (with the methodology-fix note).
7. `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md` —
   slice 2 marked DONE, slice 3 marked NEXT.
8. `perf/history.jsonl` — one row for this PR's initial open (ADR-177).

## Tests Added

- `tests/test_analytics/test_gam_basis_cr.py` — 17 new tests: `cr_default_knots`
  (span, uniqueness handling, refusals), `cr_basis` closed-form invariants
  (reproduces a linear function exactly; penalty is exactly zero on a linear
  function and positive on a curved one; penalty is symmetric; penalty rank is
  `k-2`; evaluating at a knot gives a unit row; refusals), `absorb_sum_to_zero_constraint`
  (drops one dimension; constrained design's column means are zero; penalty stays
  symmetric; refusals).
- `tests/test_analytics/test_gam_stage_a.py` — `build_python_cr_term` unit tests
  (supplied knots; default knots; refuses non-`cr`; refuses more than one
  variable), a provenance test (`CR_BASIS_CLAIM` declares everything
  `INDEPENDENT`), and the R-gated end-to-end proof
  (`test_the_python_cr_basis_agrees_with_smoothcon_on_every_smooth_design`) —
  the epic's first test that can genuinely fail on real numbers, not just a
  round trip.

## Acceptance Criteria

| Criterion (from `docs/PLAN_mgcv_parity_engine.md` slice 2) | Status | Notes |
|---|---|---|
| INDEPENDENT `design_X` comparison, `<1e-9`, target's own knots AND default placement, k=13 and k=6 | ✅ | 5 cases incl. `target-attdage-k13`/`target-polyear-k6`; diffs ~1e-14 |
| INDEPENDENT `penalty_S` comparison, same tolerance, same cases | ✅ | same table |
| A disagreement reported with which of basis/penalty drifted | N/A this session | no disagreement occurred; the one gap found (penalty rescale) was closed before any comparison ran, not reported as a drift |
| Python producer takes no R payload as input; knots come from the recipe | ✅ | `build_python_cr_term(x, term)` — `x` is shared recipe context (module docstring), not the R payload |
| `VerificationClaim` declares INDEPENDENT; `require_parity_evidence` gates | ✅ | `CR_BASIS_CLAIM`, tested |
| Confirmed at tier 3 | ✅ | real per-metric numbers, not a masked conclusion (methodology fix) |

**Slice 2 is complete.**

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md`:

1. **Extrapolation beyond the knot range is unverified.** Needed before real-data
   knots that don't span the data range (the target formula's own `AttdAge`/
   `PolYear` knots against real experience). 1st-order — blocks a specific,
   foreseeable future use of this basis, not hypothetical.
2. **Slice 3 — families, links and weights.** Now genuinely unblocked. 1st-order —
   the epic's own NEXT slice, independent of slice 2.
3. **The `continue-on-error` job-summary-artifact limitation likely affects other
   diagnostic steps in this workflow** (the ADR-190 and ADR-191 probes) — only
   slice 1/1b/2's per-term step was fixed this session. 2nd-order, NICE-TO-HAVE —
   worth the same one-line fix if a future session needs to read one of those.
4. **The pre-existing `data/mortality_tables` environment gap** — unchanged from
   prior sessions, still unaddressed here. 2nd-order, NICE-TO-HAVE.

## Parked Polish

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens. No
`products/`, `reinsurance/` or CLI code moved.
