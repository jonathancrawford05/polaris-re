# Continuation: Sliding-scale expense allowances & experience refunds

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier-B **B3**
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~3 dev-days
**Epic framing:** maintainer-confirmed (2026-06-29, PR #117 — "Option A: proceed").
B3 was promoted from a between-epics quick win to a 3-slice active epic because
the Tier-A ladder + C0 are exhausted and step 5b requires one active epic;
treat it as the blessed active epic until COMPLETE.

## Overall Goal

Give Polaris RE a real expense-allowance mechanism on its proportional
treaties: a per-treaty allowance quoted as a % of ceded premium with a
first-year vs renewal split and an optional sliding scale keyed to loss
experience, applied inside `CoinsuranceTreaty`/`YRTTreaty` as a
reinsurer→cedant transfer that preserves `net + ceded == gross`; plus an
experience-refund (profit-sharing) mechanism surfaced on the deal-pricing path.
Today the only allowance handling is `CoinsuranceTreaty.include_expense_allowance`,
a boolean that shares expenses proportionally — a crude approximation that
cannot reproduce any real large YRT/coinsurance treaty's cash flows.

## Decomposition

### Slice 1: `ExpenseAllowance` model + computation primitive
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-ckdfj4
- **PR:** (this draft)
- **ADR:** ADR-118
- **What was done:** Added `reinsurance/expense_allowance.py` with the
  `ExpenseAllowance` / `ExpenseAllowanceBand` Pydantic models and the pure
  `compute_allowance()` primitive (first-year vs renewal % of ceded premium,
  optional sliding scale selecting the renewal rate from realized-loss-ratio
  bands). Validated the scale is ascending / distinct / monotone non-increasing.
  26 unit + closed-form tests. Not wired into any treaty → goldens byte-identical.
- **Key decisions:**
  - The allowance is a fraction of **ceded premium**; first year = the first
    `months_per_year` periods.
  - Sliding scale keys off the realized loss ratio `claims.sum()/premiums.sum()`;
    the first band whose `max_loss_ratio` is not exceeded wins; above all bands →
    last (lowest) band.
  - The scale must be monotone non-increasing in loss ratio (better experience
    pays at least as much) — enforced by a `PolarisValidationError`.
  - The allowance will be applied (Slice 2) as a transfer folded into the
    existing `expenses` line — **no `CashFlowResult` contract change**.

### Slice 2: Wire into `CoinsuranceTreaty` + `YRTTreaty`
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-0elamx
- **PR:** (this draft)
- **ADR:** ADR-119
- **What was done:** Added `expense_allowance: ExpenseAllowance | None = None` to
  both `CoinsuranceTreaty` and `YRTTreaty` (default None → goldens byte-identical).
  When set, the allowance is computed on the treaty's own ceded premium stream and
  folded into the expense line (+A ceded, −A net) via the shared
  `BaseTreaty._expense_allowance_transfer()` helper, preserving
  `net + ceded == gross`. Implemented the P2 duration mapping: `ExpenseAllowance`
  gained `first_year_fraction_for_block()` (face-weighted fraction of the block in
  policy year one at each projection step) and `compute_allowance()` gained an
  optional `first_year_fraction` blend argument. New business recovers the default
  first-12-periods split; a mid-duration inforce block is charged the renewal rate
  throughout. 22 new tests (13 primitive + 9 treaty wiring).
- **Key decisions:**
  - Duration mapping chosen as option (a) — map projection month → policy duration
    from the seriatim durations on `InforceBlock`, aggregated to a face-weighted
    per-period first-year fraction. The fraction is face-weighted, not
    survivorship-weighted (deliberate first cut; exact at the all-new / all-renewal
    boundaries — see ADR-119 Out of scope).
  - Without an `InforceBlock`, the allowance falls back to the new-business
    projection-month basis (documented on `compute_allowance()`), rather than
    raising — aggregate/new-business use without a block is legitimate.
  - The legacy `CoinsuranceTreaty.include_expense_allowance` boolean and the new
    `expense_allowance` are independent, composable layers (test asserts the delta
    is identical with the proportional split on or off).
- **Depends on:** Slice 1 merged
- **Files to create/modify (original plan):**
  - `reinsurance/coinsurance.py`, `reinsurance/yrt.py` — add optional
    `expense_allowance: ExpenseAllowance | None = None` field (default None →
    current behaviour, goldens byte-identical).
  - When set, `allowance = expense_allowance.compute_allowance(ceded_premiums,
    ceded_claims)`; apply `ceded.expenses += allowance`, `net.expenses -= allowance`,
    and recompute both NCF lines so `verify_additivity` still passes.
  - `tests/test_reinsurance/` — closed-form + additivity tests.
- **Acceptance criteria:**
  - Default (no allowance) leaves every treaty output byte-identical → goldens
    unchanged.
  - With an allowance, `net + ceded == gross` still holds on premiums, claims,
    expenses, and NCF.
  - A hand-computed premium stream + known FY/renewal rates reproduces the
    expected per-period allowance and the shifted net/ceded NCF.
  - Document the interaction with `CoinsuranceTreaty.include_expense_allowance`
    (the boolean proportional path) — they are independent layers.
  - **Map projection periods → policy duration before applying the FY rate.**
    The Slice-1 primitive defines "first year" as the first `months_per_year`
    *projection* periods. That is correct only for new business projected from
    inception. The primary use case is an **inforce block** where most policies
    are mid-duration, so feeding a renewal-business stream starting at projection
    month 0 would wrongly apply the first-year rate. Slice 2 must either (a) map
    each policy's projection month to its actual policy duration (preferred, via
    the seriatim duration on `InforceBlock`), or (b) explicitly document and
    test a new-business-only assumption and guard against silent misuse on
    inforce blocks. This becomes load-bearing the moment the allowance touches
    the inforce projection. *(Source: PR #117 automated review, P2 Slice-2
    design note.)*

### Slice 3: Experience refund + CLI/API/Excel surfacing
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:** `ExperienceRefund` (refund % of accumulated favourable experience
  above a retention) computed from ceded cash flows; surface allowance + refund
  terms on `DealConfig` / CLI / API / Excel. Off by default → byte-identical
  unless supplied.

## Context for Next Session

- Additivity is the binding constraint. The allowance MUST net to zero across
  the (net, ceded) pair — it is a transfer between the two parties, not a new
  external cash flow. Folding it into the `expenses` line (+A ceded, −A net) is
  the design that keeps the invariant and avoids a contract change.
- `BaseTreaty.verify_additivity` checks premiums, claims, and NCF (not expenses
  directly), but NCF includes expenses, so the transfer is exercised by the NCF
  check. Slice 2 tests should additionally assert expense-line additivity
  explicitly.
- The sliding scale needs the ceded claims to pick the renewal rate; in Slice 2
  pass the treaty's own ceded claims array (the reinsurer's experience drives
  its allowance).

## Open Questions (for human)

- Should the sliding scale key off the **ceded** loss ratio (current plan) or
  the **gross** block loss ratio? Default is ceded; revisit if a cedant
  submission specifies the gross basis.
- Should a future slice add a dedicated allowance line to `CashFlowResult`
  (contract change) for cleaner reporting, or is folding into `expenses`
  sufficient long-term?
