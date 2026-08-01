# Continuation: Block-aware expense-allowance duration mapping on the config path

**Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT #3 (carried into
PRODUCT_DIRECTION_2026-07-24 IMPORTANT #3); promoted from ADR-122 Out of scope.
**Status:** COMPLETE (mandatory Slices 1 + 2 shipped and MERGED — #168 / #169;
optional 2nd-order Slice 3 deferred to the NICE-TO-HAVE follow-up in
`PRODUCT_DIRECTION_2026-07-24` #3. Ledger-healed 2026-07-31, step 4b: Slice 2's
PR #169 was recorded as an unmerged draft but merged to main as commit `f9fc7aa`.)
**Total slices:** 2
**Estimated total scope:** ~1.5 dev-days

## Overall Goal

A sliding-scale `ExpenseAllowance` must charge its high first-year rate only on
business genuinely in policy year one. The engine already maps projection month
to actual policy duration (`ExpenseAllowance.first_year_fraction_for_block`)
**when an `InforceBlock` is passed to `treaty.apply`**. But the CLI / API /
dashboard only pass `inforce` when the deal's `use_policy_cession` flag is set,
because — before this feature — passing `inforce` also flipped cession
resolution to honour per-policy overrides. So a **renewal (mid-duration) block
priced with `use_policy_cession=False` and an allowance** wrongly gets the
new-business first-year basis (measured **+65% / +$1,767** ceded allowance on a
single 10-year in-force policy). This feature decouples the two roles `inforce`
plays so the block-aware mapping is active whenever an allowance is present,
independent of the cession flag.

## Decomposition

### Slice 1: Engine — decouple cession honouring from allowance mapping
- **Status:** DONE
- **Branch:** claude/loving-gauss-ubiesb
- **PR:** #168
- **ADR:** ADR-166
- **What was done:** Added a keyword-only `use_policy_cession: bool = True` to
  `BaseTreaty.apply` and every concrete override (YRT, Coinsurance, Modco,
  FWCoinsurance; StopLoss accepts-unused). `_resolve_cession` gates honouring
  per-policy overrides on the flag; `_expense_allowance_transfer` is unchanged
  (block-aware mapping stays keyed on `inforce` presence). Default `True` +
  untouched `inforce=None` call sites → all goldens byte-identical. Closed-form
  tests in `tests/test_reinsurance/test_cession_allowance_decoupling.py`.
- **Key decisions:** Flag is **keyword-only** (`*, use_policy_cession=...`) so no
  positional call site breaks. `face_weighted_cession` returns the flat treaty
  default on an override-free block, so passing `inforce` with the default flag
  is byte-identical to the flat path — this is what lets Slice 2 pass `inforce`
  unconditionally without moving any override-free golden.

### Slice 2: Wire the deal-path callers (DONE)
- **Status:** DONE
- **Branch:** claude/loving-gauss-aeq051
- **PR:** #169 (MERGED to main — commit `f9fc7aa`; ledger-healed 2026-07-31)
- **ADR:** ADR-167
- **What was done:** Rewired every deal-path caller to pass `inforce` to
  `treaty.apply` **always** (when a cohort inforce is available) and thread the
  deal's `use_policy_cession` as the keyword flag, instead of gating whether
  `inforce` is passed on that flag:
  - `cli.py` — `_price_single_cohort` (the priced apply) + the scenario / uq
    parity-diagnostic dumps. Tabular-YRT forcing of `use_policy_cession=True`
    is unchanged (flows through `_build_treaty_for_pipeline`).
  - `api/main.py` — `/api/v1/price` passes `inforce=inforce` unconditionally.
    Cession-neutral because `PolicyInput` has no per-policy cession override
    (`Policy` built with `reinsurance_cession_pct=None`).
  - `dashboard/components/projection.py` — `run_treaty_projection` passes
    `inforce` always with the caller's `use_policy_cession`.
  Reproduced the gap on the golden block first: reinsurer `pv_profits`
  −$37,147 (buggy) → −$35,919 (fixed) with a coinsurance allowance +
  `use_policy_cession=false`. All four goldens + `tests/qa/` byte-identical
  (no golden carries an allowance). Tests in
  `tests/test_cli_allowance_duration_wiring.py` +
  `tests/test_api/test_allowance_duration_wiring.py`.
- **Key decisions:** No golden config carries an `expense_allowance`, so the
  rewire moves nothing on the goldens — the byte-identical guarantee holds by
  inspection. The scenario / uq **parity dumps** are rewired, but the
  `ScenarioRunner` / `MonteCarloUQ` engines still apply the treaty on their own
  internal path — extending the fix there is the optional Slice 3.

- **Acceptance criteria (Slice 2 — all MET):**
  - ✅ A renewal block + allowance priced with `use_policy_cession=false` via
    CLI / API charges the renewal (not first-year) rate on mid-duration
    business (CLI: `ceded_cashflows` matches block-aware reference; API:
    mid-duration transfer strictly smaller than new-business).
  - ✅ Per-policy cession overrides are still honoured **iff**
    `use_policy_cession` is true (no silent cession change — pinned by
    `test_cli_cession_stays_flat_when_flag_false`).
  - ✅ All four golden configs + `polaris price` byte-identical (no golden
    carries an allowance; full `tests/qa/` 94 passed).

### Slice 3 (optional / 2nd-order — may fold or defer): scenario/uq/portfolio parity
- **Status:** PLANNED (optional). The common quoting-path correctness gap
  (IMPORTANT #3) is closed by Slice 2; Slice 3 is polish. Promoted to the latest
  PRODUCT_DIRECTION as NICE-TO-HAVE so it survives independently of this
  CONTINUATION.
- **Depends on:** Slice 2 merged
- **Scope:** Extend the same `inforce` + `use_policy_cession` threading to the
  `/api/v1/scenario`, `/api/v1/uq`, and portfolio treaty-apply paths **inside**
  `ScenarioRunner` / `MonteCarloUQ` / the portfolio pipeline (the CLI scenario /
  uq *parity dumps* are already rewired in Slice 2, but the runner engines apply
  the treaty on their own internal path). The 2nd-order companion to IMPORTANT
  #3, ADR-123. These DTOs also omit `reserve_basis` / `valuation_mortality` for
  the same "pricing surface first" reason, so this is genuinely optional polish,
  not a correctness gap on the common quoting path.

## Context for Next Session

- Slices 1 (engine) and 2 (caller wiring) are both DONE. The IMPORTANT #3
  correctness gap on the common quoting path (CLI `polaris price` / REST
  `/api/v1/price` / dashboard) is **closed**. Slice 3 is optional polish for the
  scenario / uq / portfolio runner-internal treaty applies only.
- Slice 2 was verified byte-identical by inspection (no golden config carries an
  `expense_allowance`) rather than by a new golden fixture. The regression is
  pinned at the CLI and API levels by
  `tests/test_cli_allowance_duration_wiring.py` and
  `tests/test_api/test_allowance_duration_wiring.py`. A dedicated golden/QA
  fixture with a renewal block + allowance remains a nice-to-have (would need
  the Dockerfile COPY + `.dockerignore` update if it adds a `data/` file — the
  #61/#66 trap) and is folded into the Slice 3 polish scope.
- To advance Slice 3, thread `inforce` + `use_policy_cession` into the treaty
  apply **inside** `ScenarioRunner` / `MonteCarloUQ` / the portfolio pipeline,
  not just the CLI parity dumps (already done in Slice 2).

## Open Questions (for human)

- Close this CONTINUATION as COMPLETE (Slice 3 deferred to the promoted
  NICE-TO-HAVE follow-up) once Slice 2's PR merges, OR keep it IN PROGRESS to
  land Slice 3? The mandatory scope is done either way. Left IN PROGRESS for now
  because Slice 2's PR is an unmerged draft.
