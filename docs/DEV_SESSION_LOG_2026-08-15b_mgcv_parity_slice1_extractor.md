# Dev Session Log — 2026-08-15b

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — second scheduled firing of the parity
  routine, same calendar date as the first
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 1 (the Stage-A harness and a term spec to hang it on) — **finished this
  session**, continuing from `docs/DEV_SESSION_LOG_2026-08-15_mgcv_parity_slice1_referent.md`
- **Branch:** `claude/sharp-galileo-k0kf1x`

## Setup

- The branch's local history already contained slice 1's first half (term-spec
  dataclasses, the `smoothCon`/`lpmatrix` referent decision, PR #196 review fixes —
  immutable knots, raw-term validation, ADR-191) from a prior local session, merged
  but not yet pushed. Pushed it to establish the remote branch before continuing (PR
  #196 itself was closed without merging on GitHub — a `git merge` had already folded
  its content into this branch locally).
- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite` via
  apt (`apt-get update` needed first — stale index on the fresh container). **R 4.3.3 /
  mgcv 1.9.1**, matching the routine's documented expectation exactly.
- `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.

## Baseline and end state

| | |
|---|---|
| Baseline (this branch @ `1534b1f`, R present) | **3179 passed, 5 failed, 22 skipped, 126 deselected** |
| The 5 failures | All one root cause: `data/mortality_tables/*.csv` absent — a gitignored, generated directory (`scripts/convert_soa_tables.py`), not present in this fresh container. Pre-existing on `origin/main` (`tests/test_synthetic_block.py`, `tests/test_analytics/test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface` are unmodified by this or any recent mgcv-parity commit). **Not a regression** — an environment-provisioning gap orthogonal to this epic, per the routine's "do not deadlock on known-standing failures." Left unaddressed; out of this slice's scope. |
| The 22 skips | Also entirely `data/mortality_tables`-gated (verified: none reference `rscript_mgcv_available`) |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped (4 golden configs skip on the same missing-tables gap; `golden_flat` needs none and passes) — unmodified goldens |
| End state | 3179 + 19 new (`test_gam_stage_a.py`) = **3198 passed**, same 5 pre-existing failures, same 22 skips |
| Perf row | one row appended (this PR touches `src/polaris_re/analytics/gam_stage_a.py`, a new module under `src/`, so ADR-177's docs-only exemption does not apply) |

## Gap Before

Slice 1's remaining scope, per the prior session's `CONTINUATION_mgcv_parity_engine.md`
entry: the R-side per-term extractor and its Python comparator were not built, and
proving the harness on the existing verified `raw`/`paraPen` basis (Anchor 1's
"known-good basis first") was named as the next hypothesis rather than attempted.

**Stage A / Stage B, existing 10-cell suite** (unchanged from the prior session, tier 3,
oracle `sha256:0d54c192…` build 8): level 1: AGREES, level 2: AGREES, level 3: AGREES,
level 4: DISAGREES (the standing Kass-Steffey formula gap, ADR-190 — not this slice's
concern), level 5: DISAGREES (`gamma`, unsettled). Re-confirmed locally at tier 1 before
touching anything (`Rscript scripts/mgcv_conformance.R` + the Python comparator) —
identical verdict set, no drift.

**Primary metric (the MI contrast on the pinned grid, PLAN Anchor 2):** not yet
computable. The MI term and the outer optimiser (slices 4-5) do not exist; nothing in
this session changes that.

## Gap After

- **The R-side per-term extractor: built.** `scripts/gam_term_extract.R` — for the
  `raw`/`paraPen` basis, reads the exchange, refits at fixed `sp` (matching the
  `l1-interior` cell's `lambda_age=10, lambda_year=100`), and reads what `mgcv` actually
  fit — `m$paraPen$S`, `m$paraPen$rank`, `predict(type="lpmatrix")` — rather than
  re-echoing the exchange's own TSVs (which would prove nothing about `mgcv`'s
  bookkeeping). Emits one JSON per design: index range, design block, every `S_j`, rank,
  per term.
- **The Python comparator: built.** `src/polaris_re/analytics/gam_stage_a.py` —
  `TermExtract` (validated: index range width matches the design/penalty shapes, one
  rank per penalty), `raw_term_specs` (the tensor/factor decomposition the `raw` basis's
  own index ranges impose), `extract_raw_terms` (reads the already-fitted
  `DesignExport`, never re-derived — same discipline `build_design` itself follows),
  `compare_term_extract` (index range, design, every `S_j`, rank — field by field).
- **Proven on the existing verified basis, at both tiers.** Design `d1` (tensor only)
  and `d2` (tensor + factor block): index ranges agree, design diff at float
  round-trip noise (~5e-16, not a disagreement), `S` diff exactly `0.0`, rank diff `0`.
  Tier 1 locally; **tier 3** confirmed via CI dispatch (run 31915145674, both jobs
  green, 55s round trip) — the new R extraction step and the new Python comparison step
  both completed with `conclusion: success`, and required levels 1-3 of the existing
  suite still agree (no regression from the workflow edit).
- **A real bug, caught by the harness proving itself.** The R script's factor-term JSON
  key was the literal `"factor"` while the `label` field inside said `"factor:sex"` —
  the Python side keys by label, so the mismatch surfaced immediately as a set
  difference in the very first end-to-end test run. Fixed before any tier-3 dispatch.
  This is Anchor 1's argument made concrete: a harness bug found against a basis
  already verified to 5e-13 through the fitter is attributable to the harness, not to
  any arithmetic in question.
- **Slice 1 acceptance criteria (PLAN §3): all met.** "Stage A runs green on the
  existing basis" — yes (19/19 tests, including the R-gated end-to-end one). "The
  decision [on the referent] is recorded" — yes, ADR-191, prior session. "Nothing in
  `products/`, `reinsurance/` or the CLI moves; `tests/qa/` untouched" — yes.
  **`docs/CONTINUATION_mgcv_parity_engine.md` slice 1 is marked DONE; slice 2 (`bs =
  "cr"`) is NEXT.**
- **mgcv-native extraction (`cr`/`ti`/`sz`) is explicitly not built here.**
  `extract_raw_terms` raises on any non-`"raw"` term. That is slice 2's module, paired
  with the first Python basis construction that needs a referent — building it now,
  with nothing to verify it against, would be exactly the speculative work Anchor 8
  warns off.

## Hypotheses Tried

1. **The R-side extractor and Python comparator agree term by term on the existing
   verified `raw` basis (Anchor 1).**
   - **Tier 1** (R 4.3.3 / mgcv 1.9.1, local apt): wrote both scripts; first run found
     the factor-label key bug (a real disagreement — `{'tensor', 'factor:sex'}` vs
     `{'tensor', 'factor'}`); fixed; re-ran. **CONFIRMED at tier 1** — exact agreement,
     3 terms across 2 designs.
   - Per `ROUTINE_MGCV_PARITY.md` step 2, this is a structural claim about whether the
     extraction/serialization code reads a specific `mgcv` version's fitted object
     correctly — not a numeric value with an obvious magnitude exemption — so it needs
     tier 3 before entering `CONTINUATION_*.md` as settled. Wired both new CI steps
     (`continue-on-error: true`, same contract as the existing probes) and dispatched.
   - **Tier 3** (R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192…` build 8, CI run
     [31915145674](https://github.com/jonathancrawford05/polaris-re/actions/runs/31915145674),
     55s round trip, both jobs green): the R extraction step and the Python comparison
     step both completed with `conclusion: success`. Read from the step conclusion, not
     the per-metric job-summary table (artifact `9254708641` on that run) — the same
     honesty framing ADR-189 amendment 2 used for a run whose per-metric digits were
     not individually re-transcribed. **CONFIRMED at tier 3 — verdict promoted to
     settled**, recorded in `CONTINUATION_mgcv_parity_engine.md` and
     `docs/CONFORMANCE_LEDGER.md` (both readings, both tiers, both digests).

No failed hypotheses this session in the sense of a disagreement that stood — the one
genuine disagreement found (the JSON key bug) was a bug in this session's own new code,
fixed within the same tier-1 iteration before any tier-3 dispatch, exactly as the
routine's iterate-locally-verify-on-tier-3 loop is meant to work.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container), `OPENBLAS_NUM_THREADS=1`.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run 31915145674 on commit `d005061`.

## What Was Done

1. `scripts/gam_term_extract.R` — the R-side per-term extractor for the `raw` basis.
2. `src/polaris_re/analytics/gam_stage_a.py` — `TermExtract`, `raw_term_specs`,
   `extract_raw_terms`, `compare_term_extract`.
3. `.github/workflows/mgcv-conformance.yml` — wired both sides in as diagnostic steps
   (R extraction in job 1, Python comparison in job 2), same `continue-on-error`
   contract as the existing probes.
4. `docs/CONFORMANCE_LEDGER.md` — two new rows: the tier-1 hypothesis (including the
   caught-and-fixed bug) and its tier-3 confirmation.
5. `docs/CONTINUATION_mgcv_parity_engine.md` — slice 1 marked DONE; slice 2 marked NEXT.
6. `docs/PRODUCT_DIRECTION_2026-07-24.md` — struck through the "finish slice 1" BLOCKER
   as shipped; added this session's harvest entry.
7. `perf/history.jsonl` — one row for this PR's initial open (ADR-177).

## Tests Added

`tests/test_analytics/test_gam_stage_a.py` — 19 tests: `TermExtract` validation (index
range ordering, design/penalty shape agreement with the declared range, rank count
matching penalty count), `raw_term_specs` (with and without a factor term),
`extract_raw_terms` against the already-fitted `DesignExport` (both `d1` and `d2`, plus
refusals for a non-`raw` term and an unrecognised label), `compare_term_extract`
self-consistency (agrees with itself; catches a moved index range, a perturbed design
cell, a perturbed penalty cell, a rank disagreement; refuses a shape mismatch and a
penalty-count mismatch), and the R-gated end-to-end harness proof itself
(`test_the_r_extractor_agrees_with_the_python_side_on_every_design`, skipped wherever R
is absent, exactly as the existing `test_the_r_script_runs_end_to_end_and_agrees` is).

## Acceptance Criteria

| Criterion (from `docs/PLAN_mgcv_parity_engine.md` slice 1) | Status | Notes |
|---|---|---|
| R-side per-term extractor | ✅ | `scripts/gam_term_extract.R` |
| Python comparator | ✅ | `gam_stage_a.py` |
| Term-spec dataclasses (Anchor 3) | ✅ | prior session, `gam_term_spec.py` |
| Stage A proven on the existing verified basis first | ✅ | exact agreement, tier 1 and tier 3, both designs |
| The `smoothCon`/`lpmatrix` referent decided in writing | ✅ | prior session, ADR-191 |
| Nothing in `products/`, `reinsurance/` or the CLI moves | ✅ | |
| `tests/qa/` untouched | ✅ | 85/9, byte-identical goldens |

**Slice 1 is complete.**

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md` under "Harvested 2026-08-15b":

1. **Slice 2 — `bs = "cr"`, with supplied and default knots.** The natural next slice;
   `extract_raw_terms` and `TermExtract` are designed to extend to an mgcv-native code
   path (`smoothCon(..., absorb.cons=TRUE)$X`/`$S`/`$rank`, per ADR-191) without
   changing the `raw` path. 1st-order — the epic's own NEXT slice.
2. **The pre-existing `data/mortality_tables` environment gap** (5 test failures, some
   golden-config skips) is unrelated to this epic and was not fixed here — it needs
   `scripts/convert_soa_tables.py` run against a network-reachable `pymort` source,
   which this routine's scope does not cover. 2nd-order, NICE-TO-HAVE for whichever
   routine next needs those tables.

## Parked Polish

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens. No
`products/`, `reinsurance/` or CLI code moved.
