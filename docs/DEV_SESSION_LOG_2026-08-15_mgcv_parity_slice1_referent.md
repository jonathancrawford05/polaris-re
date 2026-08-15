# Dev Session Log — 2026-08-15

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — first scheduled firing of the parity routine
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 1 (the Stage-A harness and a term spec to hang it on) — **partially built**,
  not complete
- **Branch:** `claude/sharp-galileo-hxklz3`

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite` via apt
  (first attempt hit a stale mirror index — `apt-get update` fixed it). **R 4.3.3 / mgcv
  1.9.1**, matching the routine's documented expectation exactly.
- `data/mortality_tables/` was absent in this fresh container (not a code regression —
  the CSVs are generated, not committed). Ran `scripts/convert_soa_tables.py --source
  pymort` per `CLAUDE.md`'s quickstart to unblock the baseline; this is environment setup,
  not a change to `src/` or `tests/`.

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `e2531ab`, R present) | **3178 passed, 3 skipped, 126 deselected** — matches `ROUTINE_MGCV_PARITY.md` step 4's stated projection for post-PR#195 exactly ("3178/3 with R") |
| `tests/qa/` (94 tests) | **all pass, unmodified goldens** |
| End state | 3178 passed + 22 new tests (`test_gam_term_spec.py`) = **3200 passed, 3 skipped** locally; no failures, no regressions |
| Perf row | one row appended (this PR touches `src/polaris_re/analytics/gam_term_spec.py`, so ADR-177 amendment 1's docs-only exemption does not apply) |

## Gap Before

Slice 1 had not started: no term-spec dataclasses, no per-term extractor, and PLAN §5.1's
one named risk (`smoothCon()` vs `lpmatrix` as Stage A's referent) was unresolved — the
PLAN's own fallback for "neither works" was the only recorded outcome.

The routine's step-5 metric set (per-term Stage-A metrics, Stage-B at fixed `sp`, the MI
contrast, each with tier and digest) is not stated here as numbers, and that is a
consequence of scope rather than an omission: those metrics are produced by the Stage-A
harness this slice builds, which does not exist yet, so there is nothing to compute them
from. What this session can and does state with tier and digest is the one quantity that
*was* measured (PR #196 review [P2]).

## Gap After

- **Term-spec dataclasses (Anchor 3): built.** `TermSpec` / `ModelSpec` in the new
  `src/polaris_re/analytics/gam_term_spec.py`, covering all three new basis classes
  (`cr`, `ti`, `sz`) plus `raw` for the existing paraPen-supplied tensor, with the
  basis-specific arities the target formula actually uses (`sz` takes one `k` for two
  variables — a factor and a smoothed margin — not one per variable; `ti` needs at least
  two margins). 22 tests, `ruff` and `mypy` clean.
- **The one named risk: settled, not deferred.** `smoothCon(..., absorb.cons=TRUE)$X`
  reproduces `predict(gam(...), type="lpmatrix")`'s smooth-term block **bit-exactly**
  (`max_abs_diff = 0.0`) across three `bs="cr"` cases (default knots at two `k`, and
  supplied knots) — confirmed identical at tier 1 and tier 3 to the last printed digit.
  **Decision: Stage A's referent is `smoothCon(..., absorb.cons=TRUE)`.** It needs no
  fitted model, which is what makes an isolated-term harness possible without a synthetic
  response for every case.
- **Not done, and named as the next hypothesis:** the R-side per-term extractor and its
  Python comparator (the actual Stage-A harness slice 1 is named for), and proving it on
  the existing verified tensor basis. That basis reaches `mgcv` through `paraPen` rather
  than a smooth class, so it needs its own bridging code to exercise the new schema — a
  genuinely separate piece of work from the referent question, and this session ran out
  of scope to reach it after the setup, the baseline, and settling the risk properly
  (tier 1 then tier 3, per the routine's own rule).

## Hypotheses Tried

1. **`smoothCon(absorb.cons=TRUE)$X` and `predict(type="lpmatrix")`'s smooth block are the
   same referent, not two competing choices (PLAN §5.1).**
   - **Tier 1** (R 4.3.3 / mgcv 1.9.1, local apt): built `scripts/smoothcon_lpmatrix_probe.R`,
     three `bs="cr"` cases. Result: `max_abs_diff_lpmatrix_vs_smoothcon_x = 0.0` and
     `max_abs_diff_gam_smooth_S_vs_smoothcon_S = 0.0` in all three. **CONFIRMED at tier 1.**
   - Per `ROUTINE_MGCV_PARITY.md` step 2, a tier-1 number may not be committed to
     `CONTINUATION_*.md` — and this specific claim (which mgcv function calls which
     internally) is exactly the "a version change is different code, not noise" case the
     routine names, so it earns no magnitude exemption either. Wired the probe into
     `mgcv-conformance.yml` as a diagnostic step (`continue-on-error: true`, same contract
     as ADR-190's `ks_formula_probe.R`) and dispatched it via `workflow_dispatch` on the
     pushed branch.
   - **Tier 3** (R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192…` build 8, CI run
     [31907362222](https://github.com/jonathancrawford05/polaris-re/actions/runs/31907362222),
     round trip 51 s, `created_at` to `completed_at`): **identical result, `0.0` at every
     printed digit, all three cases.**
     Required levels 1-3 of the existing conformance suite also agreed on this run — no
     regression from the workflow edit. **CONFIRMED at tier 3 — verdict promoted to
     settled**, recorded in `CONTINUATION_mgcv_parity_engine.md` and
     `docs/CONFORMANCE_LEDGER.md` (both readings, both tiers, both digests).

No failed hypotheses this session — the one tested came back true at both tiers, with no
disagreement to characterise.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container).
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run 31907362222 on commit `173d186`.

## What Was Done

1. `src/polaris_re/analytics/gam_term_spec.py` — `TermSpec` / `ModelSpec` (Anchor 3),
   with validation matching the target formula's own basis vocabulary and irregular `sz`
   arity, `raw` for the existing paraPen route.
2. `scripts/smoothcon_lpmatrix_probe.R` — the slice-1-risk diagnostic probe, self-contained
   (no exchange dependency, so it runs even before slice 2 ships a real `cr` basis).
3. `.github/workflows/mgcv-conformance.yml` — wired the probe in as a diagnostic step,
   alongside ADR-190's `ks_formula_probe.R`.
4. `docs/CONFORMANCE_LEDGER.md` — **new**, first two rows: the tier-1 hypothesis and its
   tier-3 confirmation for this session's finding.
5. `docs/CONTINUATION_mgcv_parity_engine.md` — slice 1 status updated: what is built, what
   is settled (with the tier-3 evidence), what remains.
6. `docs/PRODUCT_DIRECTION_2026-07-24.md` — closed the "schedule the routine" BLOCKER (this
   run is the proof), harvested the remaining slice-1 scope as the next 1st-order item.

## Tests Added

`tests/test_analytics/test_gam_term_spec.py` — 22 tests: well-formed construction for
every basis kind, every validation refusal (empty label, no variables, unknown basis,
`k`/`variables` arity mismatches including `sz`'s and `ti`'s irregular ones, unknown-variable
knots, `by`+`factor` conflict, `raw` carrying `k`), and `ModelSpec`'s own validation
(empty family/link, no terms, duplicate labels).

## Acceptance Criteria

| Criterion (from `docs/PLAN_mgcv_parity_engine.md` slice 1) | Status | Notes |
|---|---|---|
| R-side per-term extractor | ❌ Not built | named as the next session's hypothesis |
| Python comparator | ❌ Not built | depends on the extractor |
| Term-spec dataclasses (Anchor 3) | ✅ | `gam_term_spec.py`, 22 tests |
| Stage A proven on the existing verified basis first | ❌ Not built | needs bridging code — the existing basis has no `smoothCon()` equivalent |
| The `smoothCon`/`lpmatrix` referent decided in writing | ✅ | settled at tier 3, in `CONTINUATION_mgcv_parity_engine.md` |
| Nothing in `products/`, `reinsurance/` or the CLI moves | ✅ | |
| `tests/qa/` untouched | ✅ | 94/94 pass, byte-identical |

**Slice 1 is not complete.** Per the routine's stop conditions, this is a legitimate
stopping point — the gap (the referent risk) is closed with a derivation, and the
remaining gap (the extractor and comparator) is characterised with a named next
hypothesis — but it is honestly reported as partial rather than as the slice finishing.

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md` under "Harvested 2026-08-15":

1. **Finish slice 1** — the R-side per-term extractor and Python comparator, plus proving
   Stage A on the existing tensor basis. 1st-order, BLOCKER (same standing blocker as the
   epic).
2. **The extractor should build on `smoothCon()` directly, not fit a full `gam()` per
   term** — this session's finding is what makes that the right design, since
   `smoothCon()` needs only covariate values, not a well-posed regression per isolated
   term. 1st-order design note for the next session.

## Parked Polish

None — every follow-up is first-order, a direct consequence of slice 1 being partially
built.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 94/94 pass byte-identical. No `products/`, `reinsurance/` or
CLI code moved.
