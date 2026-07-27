# Dev Session Log — 2026-07-27

## Item Selected
- **Source:** `docs/CONTINUATION_expense_allowance_duration.md` (IN PROGRESS) —
  Slice 2. Backing item: `PRODUCT_DIRECTION_2026-07-24.md` IMPORTANT #3
  ("Engage block-aware first-year duration mapping when an `expense_allowance`
  is supplied via config"), promoted from ADR-122 Out of scope.
- **Priority:** IMPORTANT (production-correctness gap on the expense-allowance
  common quoting path)
- **Title:** Wire the deal-path callers to block-aware expense-allowance
  duration mapping
- **Slice:** 2 of 2 (mandatory scope; optional 2nd-order Slice 3 deferred)
- **Branch:** `claude/loving-gauss-aeq051` (environment-designated)

## Selection Rationale
Step 5 found exactly one IN PROGRESS CONTINUATION —
`expense_allowance_duration` — whose Slice 1 (engine layer, PR #168, ADR-166)
was already **merged to main** (`git log main` shows the #168 merge). Per step
5c the CONTINUATION *is* the work selection, so steps 5b/6 (fallback pick) are
skipped and this session advances the next slice. The only other IN PROGRESS
CONTINUATION, `reserve_basis_correctness`, is explicitly DEPRIORITISED/parked
(not the active epic). No fallback item was considered — the active feature
consumed the session.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Engine: decouple cession honouring from allowance mapping in `BaseTreaty.apply` (keyword-only `use_policy_cession`) | ✅ Done | #168 (merged) |
| 2 | Wire the deal-path callers (CLI price + scenario/uq parity dumps, REST `/api/v1/price`, dashboard) to pass `inforce` always | ✅ Done (draft PR) | this session |
| 3 | *(optional / 2nd-order)* scenario/uq/portfolio runner-internal parity | 🔲 Deferred → promoted NICE-TO-HAVE | — |

## What Was Done
Reproduced the premise first (step 7b) on the mid-duration golden block: a
Coinsurance treaty with a 40%/10% sliding-scale `expense_allowance` and
`use_policy_cession=false`, priced via `polaris price`, produced reinsurer
`pv_profits = −$37,147` on the buggy path (the CLI gated `inforce` to `None`
because the cession flag was false, so the allowance fell back to the
new-business first-year basis). The engine capability from Slice 1 was present
but never reached because every deal-path caller gated *whether `inforce` was
passed* on `use_policy_cession`.

The fix rewires three surfaces to pass `inforce` to `treaty.apply` **always**
(when a cohort inforce is available) and thread the deal's `use_policy_cession`
as the keyword flag: `cli.py` (`_price_single_cohort` + the scenario/uq
parity-diagnostic dumps), `api/main.py` (`/api/v1/price`), and
`dashboard/components/projection.py` (`run_treaty_projection`). After the fix
the same repro prices reinsurer `pv_profits = −$35,919` — a **+$1,228**
correction, entirely the first-year rate no longer charged on renewal business.
The API change is cession-neutral because `PolicyInput` carries no per-policy
cession override (`Policy` is built with `reinsurance_cession_pct=None`), so the
default `use_policy_cession=True` leaves existing responses byte-identical.

Verified byte-identical goldens (no golden config carries an `expense_allowance`)
via the full `tests/qa/` suite (94 passed) and `polaris price` on
`golden_config_flat.json`. Recorded ADR-167.

## Files Changed
- `src/polaris_re/cli.py` — `_price_single_cohort` treaty apply + the scenario /
  uq parity-dump applies now pass `inforce` always with `use_policy_cession`.
- `src/polaris_re/api/main.py` — `/api/v1/price` passes `inforce=inforce`
  unconditionally.
- `src/polaris_re/dashboard/components/projection.py` — `run_treaty_projection`
  passes `inforce` always with the caller's `use_policy_cession`.
- `docs/DECISIONS.md` — ADR-167.
- `docs/CONTINUATION_expense_allowance_duration.md` — Slice 2 → DONE; Slice 3
  clarified as optional/deferred; context + open questions updated.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — appended the Slice 3 NICE-TO-HAVE
  follow-up + an IMPORTANT #3 ledger note.

## Tests Added
- `tests/test_cli_allowance_duration_wiring.py` (5 tests) — drives the real CLI
  pricing path (`_price_single_cohort`) on a 10-year in-force block + allowance
  + `use_policy_cession=false`: asserts `ceded_cashflows` match the block-aware
  reference (renewal rate) and are strictly below the new-business basis; that
  cession stays flat when the flag is False even with a per-policy override
  present; byte-identical to the former `inforce=None` path when no allowance;
  new-business (duration 0) block unaffected.
- `tests/test_api/test_allowance_duration_wiring.py` (1 test) — a mid-duration
  block is charged a materially smaller allowance transfer than a matched
  new-business block via `/api/v1/price` (before Slice 2 both got the
  new-business basis).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Renewal block + allowance + `use_policy_cession=false` priced on the renewal rate via CLL / API | ✅ | CLI: `ceded_cashflows` == block-aware ref; API: mid-duration transfer < new-business |
| Per-policy cession overrides honoured iff `use_policy_cession` true (no silent cession change) | ✅ | `test_cli_cession_stays_flat_when_flag_false` |
| All four golden configs + `polaris price` byte-identical | ✅ | No golden carries an allowance; `tests/qa/` 94 passed |
| Quality gate (ruff format + check, pytest not-slow, qa) | ✅ | See "Impact"; full non-slow suite green |

## Open Questions / Follow-ups
- Whether to close `CONTINUATION_expense_allowance_duration` as COMPLETE (Slice 3
  deferred to the promoted NICE-TO-HAVE) once Slice 2's PR merges, or keep it IN
  PROGRESS to land Slice 3. Mandatory scope is done either way; left IN PROGRESS
  because Slice 2's PR is an unmerged draft. **Human decision.**
- IMPORTANT #3 in `PRODUCT_DIRECTION_2026-07-24` is fixed on the common path by
  this slice but left un-struck (PR unmerged). Morning ledger-healing (step 4b)
  should strike it once the Slice 2 PR merges.

## Parked Polish
None. The one out-of-scope item from ADR-167 (scenario/uq/portfolio
runner-internal parity) is 2nd-order and was promoted as NICE-TO-HAVE (not
parked), and it is also tracked as the optional Slice 3 in the CONTINUATION.

## Impact on Golden Baselines
None — no golden config carries an `expense_allowance`, and for an override-free
block the face-weighted cession equals the flat treaty default, so passing
`inforce` with the correct flag moves nothing on the goldens. Confirmed
byte-identical: `tests/qa/` 94 passed and `polaris price` on
`golden_config_flat.json` succeeded.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2603 passed, 3 skipped, 113 deselected**, 0 failures (tolerance-aware; SOA
VBT / CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the
standing baseline, matching the recorded prior-session baseline pattern). No new
or changed failures, so the session PROCEEDED.
