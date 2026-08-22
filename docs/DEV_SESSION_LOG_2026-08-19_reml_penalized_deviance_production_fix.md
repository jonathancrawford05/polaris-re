# Dev Session Log — 2026-08-19 (production REML score, RESOLVED — maintainer-authorized fix)

## Item Selected

- **Source:** maintainer direction, 2026-08-19, explicitly authorizing ADR-197 decision
  2's recommendation, in these words: "Proceed to fix
  `experience_gam_penalized.reml_score` the same way ADR-196 fixed
  `gam_reml.reml_score_general` (add the missing term)."
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`. This session
  closes the one item PLAN Anchor 7 reserved for the maintainer — everything else in
  Anchor 7's general protection of `experience_gam_penalized.py` is unaffected.
- **Scope:** the one-line score fix (`penalized_deviance = deviance + coef @ penalty @
  coef`, used in place of plain `deviance`); regenerate
  `data/mgcv_exchange/synthetic/python_reference.json` via its own codebase regeneration
  path; update the 3 tests ADR-197 named plus 4 more discovered as a direct,
  faithful consequence of the same fix; re-run the ten-cell `mgcv` conformance suite,
  tier 1 and tier 3; confirm `tests/qa/golden_outputs/` stays byte-identical.
- **Branch:** `claude/zealous-mendel-j0huik` (PR #204, draft).

## Setup

- `git fetch`/`checkout`/`pull` on `claude/zealous-mendel-j0huik`, confirmed head at
  `c18bf26` (on top of `138683b`, `70b9846`, `a713f18`).
- R already present: R 4.3.3 / mgcv 1.9.1 (local apt, matches the routine's documented
  expectation — no install needed this session).
- Read, in full: `docs/DECISIONS.md` ADR-196 and ADR-197 (including its 2026-08-19 PR
  #204 review amendment), `src/polaris_re/analytics/gam_reml.py` (the fixed pattern,
  lines ~136-161), `src/polaris_re/analytics/experience_gam_penalized.py::reml_score`,
  `docs/WORK_ORDER_reml_penalized_deviance_production_check.md` §2, and
  `tests/test_analytics/test_experience_mgcv_conformance.py`'s regeneration/comparison
  test (`test_the_committed_reference_is_what_this_code_computes`).

## Baseline and end state

| | |
|---|---|
| Baseline (`pytest -m "not slow"`, before touching code) | **3309 passed, 5 failed, 22 skipped, 126 deselected** (matches PR #204's own last-known baseline exactly) |
| The 5 failures | Pre-existing `data/mortality_tables/*.csv`-absent root cause — unrelated to this epic, unchanged from every prior session in this epic's log. |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, `git diff tests/qa/` empty, both before and after. |
| End state (`pytest -m "not slow"`, after) | **3309 passed, 5 failed (same), 22 skipped (same), 126 deselected (same)** — zero regressions, zero new failures. The 6 rewritten tests changed WHAT some already-passing tests assert, not the pass/fail count (2 tests renamed in `test_gam_reml.py`, 1 renamed in `test_gam_reml_production_check.py`, so the total count is unchanged even though their content moved). |
| `ruff format` / `ruff check` on `src/`, `tests/` | Clean. |

## Gap Before

ADR-197 measured, but PLAN Anchor 7 blocked fixing, `experience_gam_penalized.reml_score`
— the production tensor-MI 2-D grid selector's own score, confirmed to carry the
identical missing-penalized-deviance-term bug ADR-196 found and fixed in
`gam_reml.reml_score_general`. The fix was recommended (§3.2's registered prediction held
on all three free-sp cells tested) but explicitly not applied, pending the maintainer's
own sign-off on re-baselining the committed `python_reference.json`.

## Gap After

**Fixed and re-baselined.** `experience_gam_penalized.reml_score` now computes the
penalized deviance (`Dp = D(β̂) + β̂ᵀSβ̂`, Wood 2011 §2 eq. 4) the identical way
`gam_reml.reml_score_general` does — verified bit-for-bit identical on every fixture
tested, not merely close. `data/mgcv_exchange/synthetic/python_reference.json`
regenerated via `scripts/export_mgcv_case.py` (the same path
`test_the_committed_exchange_is_what_this_code_exports`/
`test_the_committed_reference_is_what_this_code_computes` name for staleness — never
hand-edited). The delta matches §3.2's registered prediction to the printed digit on
`l2-free-sp`, `l2-free-sp-factors`, `l2-free-sp-kb` (the three cells §3.2 named), plus
`l5-gamma` (not one of those three, but the identical mechanism). Full ten-cell
conformance suite re-run against the fixed module and re-baselined reference: required
levels 1-3 still AGREE (no regression); level 5 (Wood's `gamma`, PLAN Anchor 9, previously
UNSETTLED) moves from DISAGREES to AGREES — an improvement beyond what §3.2 alone
measured. Level 4 (Kass-Steffey covariance) is unchanged in kind, ADR-190's separate,
already-tracked `dw/drho` gap. `tests/qa/golden_outputs/` reconfirmed byte-identical.

## Hypotheses Tried

1. **The fix reproduces §3.2's predicted `python_reference.json` delta exactly.**
   **CONFIRMED** — `l2-free-sp` λ_age 3162.2776601683795 → 5623.413251903491, λ_year
   unchanged at 1000.0; `edf_total` 8.211423 → 7.661360. `l2-free-sp-factors` and
   `l2-free-sp-kb` match §3.2's "corrected" column and the [P1] amendment's EDF table to
   every printed digit — three structurally different routes (a maintainer-run local
   patch, a from-scratch diagnostic replica, and now the real production fix) landing on
   the identical numbers is strong internal evidence the fix is exactly the one measured.
2. **The re-baselined reference regresses none of levels 1-3.** **CONFIRMED** — tier 1,
   before vs after: `level 1: AGREES / level 2: AGREES / level 3: AGREES` unchanged both
   sides.
3. **Fixing the score materially improves level 2's free-sp metrics and (untested by
   ADR-197) level 5's gamma metrics.** **CONFIRMED, and level 5 more than expected** —
   `max_abs_log10_sp_diff` on the three free-sp cells: 0.3145/0.1709/0.4322 →
   0.0645/0.0791/0.1048. `l5-gamma`: `max_abs_log10_sp_diff_gamma` 0.6724 (FAIL, tol 0.5)
   → 0.0776 (PASS); `abs_edf_total_diff_gamma` 1.1270 (FAIL, tol 1.0) → -0.0024 (PASS).
   Level 5 moving from DISAGREES to AGREES was not predicted by ADR-197 (which measured
   only the three plain free-sp cells) — a genuine additional result this session found.
4. **The fix does not disturb level 4.** **CONFIRMED, as §3.3 already predicted it
   would not be material** — `rel_unconditional_inflation_diff` still fails on
   `l2-free-sp` (-0.322, was -0.361) and `l2-free-sp-kb` (-0.334, was -0.350); same small
   direction of movement §3.3 already characterized as immaterial to ADR-190's separately
   derived 3.2-4.1x gap.
5. **`tests/qa/golden_outputs/` stays untouched by the real fix, not just the prior
   diagnostic patch.** **CONFIRMED** — `git diff tests/qa/` is empty after the actual
   code change and reference re-baseline, reconfirming rather than merely re-citing
   ADR-196's resolution section and the work order §5's claim.
6. **Exactly the 3 tests the work order named need updating, and no others.**
   **REFUTED — 4 more tests broke as a direct, faithful consequence of the same fix**,
   not new bugs: `test_gam_reml.py::TestRelationshipToTheExistingPoissonScore` (2 tests)
   and `test_gam_reml_production_check.py::TestCorrectedReMLScore`/
   `TestSelectLambdasCorrected::test_current_criterion_reproduces_the_shipped_selection_
   on_l2_free_sp` (2 tests) all asserted a nonzero gap between the (now-identical) old and
   corrected formulas, or a stale shipped-selection value. All 7 (3 named + 4 found) were
   updated to the new, verified-correct expectations — see ADR-197's 2026-08-19 amendment
   for the full reasoning on each, including the one (`test_the_smoothing_variance_
   matches_the_measured_lambda_spread`) whose fixture legitimately moved to a
   search-bound optimum post-fix, retiring one axis of its own comparison rather than
   forcing a pass.

No hypothesis required more than one pass — each measured once at tier 1, confirmed at
tier 3.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1, local apt (already present), this session, before
  pushing.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, jsonlite 2.0.0, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8, same digest as every prior measurement in this epic), CI run
  [32204739991](https://github.com/jonathancrawford05/polaris-re/actions/runs/32204739991),
  commit `ce0b9f1`. Both jobs completed in ~63s (`mgcv reference (R)`: 34s;
  `Compare against the Python reference`: 29s). Every number read from the job-log
  stdout — `max_abs_log10_sp_diff` (0.0645/0.0791/0.1048 on the three free-sp cells),
  `abs_edf_total_diff_free_sp` (0.1013/-0.0262/0.0109), `max_abs_log10_sp_diff_gamma`
  (0.0776, PASS), `abs_edf_total_diff_gamma` (-0.0024, PASS),
  `rel_unconditional_inflation_diff` (-0.322/-0.334, still FAIL, level 4 unaffected), and
  the level verdicts (`1 AGREES 2 AGREES 3 AGREES 4 DISAGREES 5 AGREES`) — is IDENTICAL to
  the tier-1 reading at every printed digit. §3.1/§3.2/§3.3 of the work-order diagnostic
  step (also re-run in this same CI job) show `current` and `corrected` now computing
  the SAME numbers everywhere, confirming the production fix is live end to end, not
  just locally.

## Files changed

- `src/polaris_re/analytics/experience_gam_penalized.py` — the fix (`reml_score`, ~7
  lines: the `penalized_deviance` term and its citing comment, and the return
  expression's substitution).
- `src/polaris_re/analytics/gam_reml_production_check.py` — module docstring updated to
  record that the diagnostic module's "current vs corrected" comparisons now legitimately
  return zero difference (no functional change — Anchor 7 protects the production
  module, not this read-only diagnostic).
- `data/mgcv_exchange/synthetic/python_reference.json` — re-baselined (regenerated, not
  hand-edited). Exchange hash unchanged
  (`sha256:78dc8914de78b3f7d3e987427d5224692afc1f136f91cd79518efd2610db71e5`).
- `tests/test_analytics/test_gam_reml.py`,
  `tests/test_analytics/test_gam_reml_production_check.py`,
  `tests/test_analytics/test_experience_gam_penalized.py` — the 7 tests described above.
- `docs/DECISIONS.md` — ADR-197 2026-08-19 resolution amendment.
- `docs/CONFORMANCE_LEDGER.md` — two new rows (tier 1, tier 3).
- `docs/CONTINUATION_mgcv_parity_engine.md`, `docs/PRODUCT_DIRECTION_2026-07-24.md` —
  status updated to RESOLVED/FIXED.
- This file.

## What this does not claim

Level 4 (Kass-Steffey unconditional covariance under-inflation, ADR-190's `dw/drho` gap)
is unaffected by this session, as §3.3 already predicted — it is a different, separately
derived and separately tracked BLOCKER, not touched here. Slice 4 part B (the
N-dimensional outer search) is not started in this session — it was already unblocked in
principle before this session ran (ADR-197 decision 3) and remains a separate, later
piece of work.
