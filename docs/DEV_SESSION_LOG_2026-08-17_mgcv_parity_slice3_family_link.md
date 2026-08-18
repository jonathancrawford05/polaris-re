# Dev Session Log — 2026-08-17 (slice 3)

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 3 (families, links and weights) — **finished this session**, per
  `docs/PLAN_mgcv_parity_engine.md`. Slice 2 (`bs = "cr"`) was already DONE at the
  start of this session (2026-08-17, ADR-194).
- **Branch:** `claude/zealous-mendel-b64ugu`

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `apt-get update` (stale index, needed
  first), then `r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 / mgcv
  1.9.1** — matches the routine's documented expectation exactly, no version
  drift to log. `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- Read, in full: `docs/ROUTINE_MGCV_PARITY.md`, `docs/VERIFICATION_STANDARD.md`,
  `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`,
  `docs/CONFORMANCE_LEDGER.md`, CLAUDE.md, `docs/DECISIONS.md` (ADR-189 + both
  amendments, ADR-190, ADR-191, ADR-192, ADR-193, ADR-194),
  `docs/RUNBOOK_mgcv_conformance.md`.

## Baseline and end state

| | |
|---|---|
| Baseline (`make test`, before touching code, R present) | **3258 passed, 5 failed, 22 skipped, 126 deselected** |
| The 5 failures | Pre-existing `data/mortality_tables/*.csv`-absent root cause, unrelated to this epic — matches the prior parity session's stated baseline exactly on skip count and failure set; the +1 pass count over the last parity log (3257) is PR #201's own fix commit landing between sessions, not a regression. |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical. |
| End state (`make test`, after) | **3282 passed, 5 failed (same), 22 skipped (same), 126 deselected** — the 24-pass increase is exactly this session's new tests (17 in `test_gam_family.py`, 4 in `test_gam_fit.py`, 3 in `test_gam_family_conformance.py`). |
| Perf row | one row appended (`gam_family.py`/`gam_fit.py` are new modules, not docs-only, so ADR-177's exemption does not apply). **Creep verdict:** no structural creep — `peak_mib` 33 → 33 (delta 0). |

## Gap Before

Slice 3 was entirely unbuilt: the only penalized IRLS core in the codebase
(`experience_gam_penalized._penalized_irls`) is hardcoded to the Poisson
log-link with an offset, correct for the tensor MI surface and untouched per
Anchor 7. No family/link abstraction, no prior-weight support (as distinct from
an offset), no dispersion estimation existed anywhere for binomial or
quasi-Poisson.

**Stage A / Stage B, existing 10-cell suite** (unchanged, tier 3, oracle
`sha256:0d54c192…` build 8): level 1: AGREES, level 2: AGREES, level 3: AGREES,
level 4: DISAGREES (standing Kass-Steffey formula gap, ADR-190 — not this
slice's concern), level 5: DISAGREES (`gamma`, unsettled). Re-confirmed at
tier 3 this session (run 32057694949) — unchanged, no regression.

**Slice 3, specifically (the gap this session closes):** zero — no comparison
in the codebase had ever fit binomial, quasi-Poisson, or any family other than
Poisson-with-offset, against `mgcv`.

## Gap After

- **A general family/link abstraction: built.** `src/polaris_re/analytics/gam_family.py`
  — `Family`/`Link` for `poisson_log`, `binomial_logit`, `binomial_cloglog`,
  `quasipoisson_log`. Standard GLM IRLS theory (Wood, *GAMs: An Introduction with
  R*, 2nd ed., §3.1.2), not `mgcv`-internal machinery — unlike the `cr` basis,
  no R-source archaeology was needed to derive it.
- **A general penalized IRLS core: built.** `src/polaris_re/analytics/gam_fit.py`
  — `penalized_irls_general` (proven to reduce to the already-verified Poisson
  recursion bit-for-bit, both at `S = 0` and under a real penalty, before any R
  round trip was spent), `effective_degrees_of_freedom` (Anchor 4's `tr(F)`
  definition, generalized), `pearson_dispersion`.
- **The INDEPENDENT Stage-B comparison: built and confirmed.**
  `src/polaris_re/analytics/gam_family_conformance.py`'s `FAMILY_CLAIM` declares
  `eta`/`dispersion` `INDEPENDENT`; `fit_family_case` reads only the shared
  recipe off `scripts/gam_family_probe.R`'s payload, never the R side's own fit
  output — the mechanical test ADR-193 names. `require_parity_evidence` gates it.
- **Confirmed at tier 3, first measurement, no iteration:** all four
  family/link/weight combinations PLAN slice 3 names agree to float round-trip
  precision. See the Provenance section below for the table.
- **`docs/DECISIONS.md`: ADR-195** records the design decisions (a new module
  rather than widening the old one; the recursion is textbook, not `mgcv`
  machinery; `cloglog`'s non-canonical-link caveat; Anchor 2 restated for Stage
  B; the `tr(F)`-based dispersion derivation) and both tiers' measurements.
- **PLAN/CONTINUATION updated:** slice 3 marked DONE; slice 4 (the outer
  optimiser) marked NEXT.

## Hypotheses Tried

1. **The general working-weight/working-response IRLS recursion, generalized
   from the already-verified Poisson-only implementation, reproduces `mgcv`'s
   fit across binomial logit/cloglog with prior weights, quasi-Poisson, and
   Poisson with a log offset, once family/link/weights match (matching PLAN
   §6's registered-prediction spirit for slice 2, extended to slice 3).**
   - Before any R round trip: verified the generalisation is a provable
     superset of the already-verified Poisson case
     (`TestPoissonReducesToTheVerifiedRecursion`, bit-for-bit at `S=0` and
     under a real penalty), and cross-checked both binomial links against an
     independent `statsmodels` GLM implementation (never reading this
     module's own output) on unpenalized data.
   - **CONFIRMED at tier 1 on the first measurement** — all four cases agreed
     to ~1e-14 on `eta`; the quasi-Poisson dispersion diff was 9.671e-06.
   - **CONFIRMED at tier 3, same day, same numbers to the same order** — see
     the Provenance table. No iteration was needed; the hypothesis held on the
     first pass, the same shape of result ADR-194 recorded for the `cr` basis.
2. **`cloglog`'s non-canonical link would show a larger — or at least
   different-magnitude — disagreement than `logit`'s, since the strict-concavity
   argument ADR-189 makes does not automatically extend to it.**
   - **NOT observed this session**: `binomial-cloglog`'s `eta` diff (1.488e-14)
     was the same order as every canonical-link case, not larger. This is
     recorded as a live caveat (ADR-195 decision 3) rather than a refuted
     hypothesis — the shared design in this slice's probe is well-conditioned
     by construction (a Fourier basis with a moderate second-difference
     penalty), and a harder-conditioned future case could still disagree.
     Filed for the next session that builds a `cloglog` case on real term
     structure, not resolved here.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container),
  `OPENBLAS_NUM_THREADS=1`.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run
  [32057694949](https://github.com/jonathancrawford05/polaris-re/actions/runs/32057694949)
  on commit `90cbdba`, both jobs completed in ~52s (18:57:52 to 18:58:44 UTC).

## Provenance

Every quantity this session reported as a comparison, and what produced each
side (ADR-193):

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `eta` | `gam_fit.penalized_irls_general` (independent Python IRLS, reading only the shared recipe — `x`, `s`, `y`, `weights`, `offset`, `sp` — never `scripts/gam_family_probe.R`'s own fit) | `mgcv::predict(m, type='link')` on a `gam()` fit at the same fixed `sp` | **INDEPENDENT** |
| `dispersion` (quasipoisson-log only — the one case `mgcv` estimates it) | `gam_fit.pearson_dispersion`, using `gam_fit.effective_degrees_of_freedom`'s own `tr(F)` computation | `mgcv m$sig2` (mgcv's own Pearson dispersion estimate) | **INDEPENDENT** |
| `coef` | *(not compared — Anchor 2: never a Stage-B acceptance criterion)* | *(not compared)* | **N/A, deliberately** |

**Tier 3 measurement table** (read directly from job-log stdout via
`get_job_logs`, the same discipline slice 2's methodology fix established —
not inferred from a masked `continue-on-error` step conclusion):

| case | family | link | max abs `eta` diff | dispersion diff | agrees |
|---|---|---|---:|---:|---|
| `binomial-logit` | binomial | logit | 1.221e-15 | n/a | True |
| `binomial-cloglog` | binomial | cloglog | 1.488e-14 | n/a | True |
| `quasipoisson-log` | quasipoisson | log | 8.438e-15 | 9.671e-06 | True |
| `poisson-log-offset` | poisson | log | 9.326e-15 | n/a | True |

`FAMILY_CLAIM` (`gam_family_conformance.py`) declares both compared quantities
`INDEPENDENT`, gated by `require_parity_evidence` in
`tests/test_analytics/test_gam_family_conformance.py`. This is the epic's
first Stage-B parity table entitled to `CONFIRMED (parity)` outside the
already-verified Poisson case — contrast with the existing conformance suite's
levels 1-5 (also INDEPENDENT, but Poisson-only) and slice 2's `CR_BASIS_CLAIM`
(INDEPENDENT, but Stage A).

## What Was Done

1. `src/polaris_re/analytics/gam_family.py` — new module: `Link`, `Family`,
   `poisson_log`, `binomial_logit`, `binomial_cloglog`, `quasipoisson_log`,
   `validate_family_inputs`.
2. `src/polaris_re/analytics/gam_fit.py` — new module: `penalized_irls_general`,
   `effective_degrees_of_freedom`, `pearson_dispersion`, `GeneralIRLSFit`.
3. `src/polaris_re/analytics/gam_family_conformance.py` — new module:
   `FAMILY_CLAIM`, `fit_family_case`, `compare_family_case`, `FAMILY_BY_CASE`.
4. `scripts/gam_family_probe.R` — new probe script, following the
   `ks_formula_probe.R`/`smoothcon_lpmatrix_probe.R` pattern: builds its own
   deterministic shared `(X, S)` design (`set.seed`, ADR-074), fits it under
   four family/link/weight combinations at fixed `sp`, writes the recipe and
   its own fit to one JSON.
5. `.github/workflows/mgcv-conformance.yml` — new diagnostic probe step
   ("Fit the shared family/link design…") in the R job, new comparison step
   ("Compare the family/link Stage-B fits…") in the compare job — printing to
   stdout from the start (learning slice 2's methodology fix, not repeating
   the mistake it fixed).
6. `docs/DECISIONS.md` — **ADR-195**: the design decisions and both tiers'
   measurements.
7. `docs/CONFORMANCE_LEDGER.md` — two new rows: the tier-1 hypothesis and its
   tier-3 confirmation.
8. `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`
   — slice 3 marked DONE, slice 4 marked NEXT.
9. `docs/PRODUCT_DIRECTION_2026-07-24.md` — follow-ups harvested (below).
10. `perf/history.jsonl` — one row for this PR's initial open (ADR-177).

## Tests Added

- `tests/test_analytics/test_gam_family.py` — 17 tests: link algebra
  (`linkinv`/`mu_eta` closed-form/numerical-derivative checks, unit-interval
  bounds), the Poisson-reduces-to-the-verified-recursion proof (bit-for-bit at
  `S=0` and under a real penalty), binomial-vs-`statsmodels` cross-checks for
  both links, weights-are-not-an-offset (PLAN Anchor 5), quasi-Poisson
  coefficient identity with plain Poisson, Pearson dispersion sanity checks,
  input validation.
- `tests/test_analytics/test_gam_fit.py` — 4 tests: the `tr(F) == p` closed
  form at `S=0`, `tr(F) < p` under a real penalty, cross-check against
  `experience_gam_penalized`'s own edf formula on an identical problem,
  dispersion-near-one on well-specified binomial data.
- `tests/test_analytics/test_gam_family_conformance.py` — 3 tests: `FAMILY_CLAIM`
  is a genuine parity claim (`require_parity_evidence` does not raise), the
  mechanical-test signature check (`fit_family_case` takes no R fit output),
  and the R-gated end-to-end proof
  (`test_the_r_probe_runs_end_to_end_and_agrees`).

## Acceptance Criteria

| Criterion (from `docs/PLAN_mgcv_parity_engine.md` slice 3) | Status | Notes |
|---|---|---|
| At fixed `sp` on a shared design, `eta` matches for each family/link/weight combination | ✅ | all 4 cases, tier 3, ~1e-14 |
| `phi` matches where it is estimated | ✅ | quasi-Poisson, dispersion diff 9.671e-06 at tier 3 |
| The absolute and relative idioms of Anchor 5 both run, demonstrated rather than asserted | **Not this session** | each control (weights, offset) verified in isolation at the R-probe level, and together in a Python-only unit test (`TestWeightsAreNotAnOffset`); demonstrating the distinction on the target's real multi-term structure needs slice 4's optimiser first — named explicitly in PLAN rather than silently dropped |

**Slice 3 is complete for its own stated scope** (the first two criteria);
the third is deferred, with the deferral stated in the PLAN rather than
implied by silence.

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md`:

1. **`binomial`/`cloglog`'s non-canonical-link concavity gap** — did not bite
   this session's well-conditioned probe, but is not resolved in general.
   2nd-order, NICE-TO-HAVE — a documented caveat, not a work item unless a
   future measurement actually hits it.
2. **Anchor 5's absolute/relative idiom is not yet demonstrated end to end on
   the target's own term structure** — needs slice 4's optimiser and a
   multi-term model. 1st-order — a named, deferred piece of slice 3's own
   acceptance criteria.
3. **Slice 4 — the outer optimisation (N-dimensional (f)REML).** Now the
   epic's NEXT slice, and the largest remaining piece of work. 1st-order —
   the epic's own NEXT slice.

## Parked Polish

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens.
No `products/`, `reinsurance/` or CLI code moved.
