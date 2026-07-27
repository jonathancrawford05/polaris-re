# Continuation: Block-aware expense-allowance duration mapping on the config path

**Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT #3 (carried into
PRODUCT_DIRECTION_2026-07-24 IMPORTANT #3); promoted from ADR-122 Out of scope.
**Status:** IN PROGRESS
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

### Slice 2: Wire the deal-path callers (NEXT)
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:**
  - `src/polaris_re/cli.py` — the 3 `inforce_arg = ... if use_policy_cession
    else None` sites (~561, ~2263, ~2494): pass `inforce` **always** (when a
    cohort inforce is available) plus `use_policy_cession=deal.use_policy_cession`
    to `treaty.apply`. Keep the YRT-rate-table forcing of `use_policy_cession=True`.
  - `src/polaris_re/api/main.py` — the `treaty.apply(gross, inforce=inforce if
    yrt_rate_table is not None else None)` site (~1200): pass `inforce` when an
    allowance (or rate table) is present, with the correct `use_policy_cession`.
  - `src/polaris_re/dashboard/components/projection.py` (~254) — same pattern.
- **Tests to add:**
  - CLI flow: a config with a mid-duration inforce block + `expense_allowance`
    + `use_policy_cession=false` prices the allowance on the renewal rate
    (assert the JSON summary's ceded allowance / expense line matches the
    block-aware value, strictly below the new-business value).
  - Byte-identical guard: a config **without** an allowance is unchanged by the
    caller rewire (the four golden configs already cover this; add an explicit
    parity assertion).
  - API `/api/v1/price` analogue.
- **Acceptance criteria:**
  - A renewal block + allowance priced with `use_policy_cession=false` via CLI /
    API charges the renewal (not first-year) rate on mid-duration business.
  - Per-policy cession overrides are still honoured **iff** `use_policy_cession`
    is true (no silent cession change).
  - All four golden configs + `polaris price` byte-identical.

### Slice 3 (optional / 2nd-order — may fold into Slice 2 or defer): scenario/uq/portfolio parity
- **Status:** PLANNED
- **Scope:** Extend the same `inforce` + `use_policy_cession` threading to
  `/api/v1/scenario`, `/api/v1/uq`, and the portfolio path (the 2nd-order
  companion to IMPORTANT #3, ADR-123). These DTOs currently also omit
  `reserve_basis` / `valuation_mortality` for the same "pricing surface first"
  reason, so this is genuinely optional polish, not a correctness gap on the
  common quoting path.

## Context for Next Session

- The engine capability is complete and tested; Slice 2 is **pure caller
  wiring** — no new engine logic. The risk is entirely "does a golden move?",
  and the answer is no for any config without a mid-duration inforce block +
  allowance (which none of the goldens have).
- The subtle correctness point for Slice 2: pass `inforce` to `apply` **always**
  (when available), and thread the deal's `use_policy_cession` as the flag —
  do NOT keep gating whether `inforce` is passed. That is the whole fix.
- Consider adding a golden/QA fixture that exercises a renewal block + allowance
  so the fix is regression-pinned at the CLI level (not just unit level). If you
  add a data file under `data/`, update the Dockerfile COPY + `.dockerignore`
  allowlist in the same PR (the #61/#66 trap).

## Open Questions (for human)

- None blocking. Slice 2 is mechanical and low-risk; it can ship next session
  once Slice 1 is merged.
