# Continuation: Reserve-basis matching (Epic 1 / Tier-A A1)

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier A, item A1
(also PRODUCT_DIRECTION_2026-04-19 IMPORTANT "reserve-basis matching").
**Plan:** docs/PLAN_reserve_basis.md
**Status:** IN PROGRESS
**Total slices:** 5 (Slice 2 split into 2a Term + 2b WL on 2026-06-19)
**Estimated total scope:** ~10 dev-days

## Overall Goal

Let a reinsurer reproduce the cedant's reserve on the cedant's own basis
(NET_PREMIUM / CRVM / VM-20 simplified / GAAP) via a single `reserve_basis`
selector on `ProjectionConfig`. The reserve drives YRT NAR, coinsurance/modco
reserve transfer, and the profit signature, so reproducing the cedant's basis
is the biggest remaining credibility gap (per the 2026-06-18 review). The
whole-life terminal-reserve artefact is folded in as a named acceptance test
(Slice 2).

## Decomposition

### Slice 1: ReserveBasis enum + plumbing
- **Status:** DONE
- **Branch:** claude/epic-euler-uiauq2
- **PR:** (this session's draft)
- **What was done:** Added `ReserveBasis` StrEnum (`core/reserve_basis.py`,
  exported from `polaris_re.core`); added `ProjectionConfig.reserve_basis`
  (default NET_PREMIUM); added `BaseProduct._supported_reserve_bases` +
  `_check_reserve_basis()` dispatch guard, called from every product's
  `compute_reserves()`. Non-default bases raise `PolarisComputationError`
  rather than silently returning a net-premium reserve. ADR-087.
- **Key decisions:**
  - Non-default bases **raise** (no silent fallback) so a run can never
    report a reserve on a basis the engine did not compute.
  - The guard lives on `BaseProduct` via a `_supported_reserve_bases`
    frozenset that concrete engines widen as bases land. Term / WL / UL / DI
    all currently support only NET_PREMIUM.
  - Default path is byte-identical — no golden rebaseline.

### Slice 2 — split into 2a (Term, DONE) + 2b (WL, NEXT)

Planned Slice 2 (CRVM for Term **and** WL, plus the WL terminal-reserve
acceptance test) was decomposed during the 2026-06-19 session: implementing the
WL pieces *correctly* entangles two separate hard problems — the prospective WL
terminal reserve to omega and the 20-pay expense-allowance cap — that the
truncated projection horizon makes non-trivial. Rather than guess on the
actuarially sensitive WL paths (CLAUDE.md: correctness above all), Term CRVM
ships as 2a and WL CRVM + the terminal-reserve artefact as 2b. Both keep the
NET_PREMIUM default byte-identical.

### Slice 2a: CRVM concrete basis (Term)
- **Status:** DONE
- **Branch:** claude/epic-euler-807ipt
- **PR:** (this session's draft)
- **What was done:** Implemented CRVM for `TermLife` as Full Preliminary Term
  (FPT) — exact CRVM for level term, since the renewal valuation premium never
  reaches the 20-pay expense-allowance cap. Split the valuation net premium into
  a first-year `alpha` and level renewal `beta` (each solved on the equivalence
  principle), reused the existing backward recursion deducting `alpha` in months
  0–11 and `beta` after. Widened `TermLife._supported_reserve_bases` to include
  CRVM; `compute_reserves()` now dispatches (NET_PREMIUM body extracted unchanged
  into `_compute_reserves_net_premium()`). ADR-088.
- **Key decisions:**
  - CRVM values on the **projection (best-estimate) mortality** for now; the
    distinct statutory valuation table (2001 CSO) is deferred to 2b / a
    follow-up rather than shipping a half-wired core-contract change.
  - FPT gives `0V = 0`, `12V = 0`, and CRVM ≤ NET_PREMIUM everywhere — verified
    by the equivalence principle, FPT identities, and an independent recursion.

### Slice 2b: CRVM for Whole Life + terminal-reserve artefact
- **Status:** DONE
- **Branch:** claude/epic-euler-oy7sfj
- **PR:** (this session's draft)
- **What was done:** Implemented WholeLife CRVM as Full Preliminary Term valued
  **prospectively to omega** (`_compute_reserves_crvm`,
  `_compute_crvm_modified_premiums`, `_build_valuation_mortality`,
  `_valuation_months_to_omega`). The to-omega valuation is independent of the
  projection horizon, so the reserve grades monotonically toward face and does
  not collapse at the horizon — closing the documented $7.18M (yr10) → $56k
  (yr20) net-premium artefact: under CRVM the golden-WL yr20 aggregate
  `reserve_balance` rises to ~$2.35M (>40×) and the per-survivor aggregate
  increases from yr10 to yr20. Widened `_supported_reserve_bases` to include
  CRVM; `compute_reserves()` dispatches (NET_PREMIUM body extracted unchanged
  into `_compute_reserves_net_premium()`). ADR-089.
- **Key decisions:**
  - The artefact is closed **under the CRVM basis only**; the NET_PREMIUM path
    (and its one-period terminal estimate) is left byte-identical to honour the
    epic's golden constraint. Closing it on NET_PREMIUM is a separate
    rebaseline-bearing change (promoted follow-up).
  - CRVM values on the **projection (best-estimate) mortality** (same decision
    as 2a); the to-omega grid is supplied by the projection table. The distinct
    2001 CSO valuation table remains a deferred controlled core-contract change.
  - The **20-pay expense-allowance cap** binds only for premium-paying periods
    **< 20 years**; for whole-life pay and limited-pay ≥ 20 years FPT is exact
    CRVM. Rather than ship a knowingly-uncapped reserve, short-pay WL **raises**
    `PolarisComputationError`. Implementing the cap is a promoted follow-up.

### Slice 3: VM-20 simplified (deterministic reserve / NPR floor)
- **Status:** NEXT
- **Depends on:** Slice 2b merged.
- **Scope:** deterministic reserve = max(NPR, modelled reserve) on prescribed
  valuation assumptions; NPR floor only, no stochastic scenarios. Closed-form
  test vs a worked simplified-PBR example.

### Slice 4: Surface the basis selector
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
- **Scope:** CLI `--reserve-basis`, API request schema, Excel reserve-sheet
  label, validation notebook comparing profit signature across bases. This is
  the only slice that may move goldens — and only for non-default basis runs;
  document any rebaseline.

## Context for Next Session

- The dispatch hook is `BaseProduct._check_reserve_basis()` — it returns the
  active basis so Slice 2 can branch on it inside `compute_reserves()`. The
  cleanest pattern: keep the existing net-premium body, add a
  `_compute_reserves_crvm()` private method, and dispatch on the returned
  basis. Widen `_supported_reserve_bases` on the engine when you add a basis.
- The **valuation mortality table** question is the one real design decision
  in Slice 2 (see PLAN §5). CRVM uses 2001 CSO, which is distinct from the
  best-estimate projection table. Adding a `valuation_mortality` slot to
  `AssumptionSet` (defaulting to the projection table) is the leading option;
  it is a controlled core-contract change → ADR + backward-compat default +
  flag in the PR per the guardrails.
- Treaty layer needs **no** changes: YRT NAR and coinsurance reserve transfer
  both consume `compute_reserves()` output, so basis selection reprices them
  automatically. Add an integration test in Slice 2 confirming a CRVM basis
  changes the YRT ceded premium (NAR moves).
- UL (reserve = account value) and DI (reserve = 0) deliberately only support
  NET_PREMIUM. Extending them to statutory bases is out of scope for this epic
  — leave the guard raising.

## Open Questions (for human)

- Confirm the intended VM-20 scope is the **deterministic reserve / NPR floor
  only** (no stochastic scenario reserve). The PLAN assumes so; stochastic
  VM-20 would be its own multi-session epic.
- Which worked CRVM example should be the closed-form anchor? (A cited
  textbook level-premium whole-life CRVM reserve is the plan's default.)
