# Plan — Reserve-basis matching (Epic 1 / Tier-A A1)

> **Audience.** A new Claude Code session that will carry this epic across
> several daily-dev runs. Read this document fully before writing code, then
> read the linked CLAUDE.md / ARCHITECTURE.md (§4 "Reserve Calculation") /
> DECISIONS.md sections it points at. This plan is the read-only spec; the
> running log lives in `docs/CONTINUATION_reserve_basis.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** ✅ COMPLETE — all slices shipped (Slice 1 ReserveBasis enum +
> plumbing; Slices 2a/2b + 3a/3b reserve calc for Term + WL; Slice 4 surfaced
> the selector on CLI / API / Excel / validation notebook, 2026-06-19). No prior
> reserve-basis code existed before this epic. Running log:
> `docs/CONTINUATION_reserve_basis.md`.
>
> **Source.** `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A item
> **A1** (★★★★★ value, ~10 dev-days, the top-ranked unstarted epic) and
> `docs/PRODUCT_DIRECTION_2026-04-19.md` IMPORTANT "reserve-basis matching".

---

## 1. Goal

Let a reinsurer reproduce the **cedant's** reserve, not just the engine's
single net-premium reserve. The reserve drives the Net Amount at Risk (YRT
ceded premium), the proportional reserve transfer (coinsurance / modco), and
the profit signature — so a reinsurer that cannot reproduce the cedant's
statutory/accounting reserve basis cannot trust the profit number. This is
the single biggest *credibility* gap identified in the 2026-06-18 review.

When complete the engine can value reserves on any of:

- **NET_PREMIUM** — the classic net level premium reserve (today's behaviour,
  the default).
- **CRVM** — Commissioners Reserve Valuation Method (US statutory), with the
  first-year expense-allowance modification.
- **VM20** — VM-20 simplified principle-based reserve (deterministic /
  net-premium-reserve floor).
- **GAAP** — US GAAP (FAS 60) net-premium benefit reserve with locked-in
  best-estimate assumptions + provision for adverse deviation.

The basis is a single selector on `ProjectionConfig` (`reserve_basis`), so a
deal can be priced under each candidate basis without touching projection
logic.

### Folded-in acceptance test — WL prospective terminal reserve

The 2026-06-18 review folds the **whole-life terminal-reserve artefact** into
this epic as a named acceptance test: on the golden WL block the reserve
declines from $7.18M (yr 10) to $56k (yr 20) on a $25M permanent block — an
ARCHITECTURE §4 horizon-edge limitation a deal-committee actuary would query.
A true prospective / cedant-reproduced WL reserve basis should close the
artefact. This is an acceptance test **inside this epic**, not a standalone
item. It is exercised in Slice 2 (the first concrete actuarial basis touches
the WL terminal-reserve path).

## 2. Why this work, and what it does NOT do

**Why.** Both PRODUCT_DIRECTION files have carried reserve-basis matching as
IMPORTANT for two months without progress; the 2026-06-18 review ranks it the
#1 Tier-A epic and the epic-driven routine mandates advancing it before any
fallback polish.

**Does NOT.**

- It does **not** change the default reserve number. NET_PREMIUM stays the
  default; goldens are byte-identical until the final surfacing slice, and
  even then only when a non-default basis is explicitly selected.
- It does **not** add asset/ALM modelling (that is Tier-C / C0, scheduled
  after the three Tier-A epics). Reserves here are liability-side only.
- It does **not** attempt stochastic VM-20 (scenario-based reserve). Only the
  deterministic / NPR floor is in scope ("VM-20 simplified").
- It does **not** rework UL or DI reserves. UL's reserve stays the account
  value and DI stays zero; selecting a non-NET_PREMIUM basis on those engines
  raises `PolarisComputationError` until/unless a later epic addresses them.

## 3. Decomposition (3–4 slices)

Each slice leaves all tests green, is independently mergeable, and keeps the
goldens byte-identical until the final surfacing slice.

### Slice 1 — `ReserveBasis` enum + plumbing  ✅ SHIPPED
- `core/reserve_basis.py`: `ReserveBasis` StrEnum (NET_PREMIUM / CRVM / VM20 /
  GAAP), exported from `polaris_re.core`.
- `ProjectionConfig.reserve_basis` field, default NET_PREMIUM.
- `BaseProduct._supported_reserve_bases` + `_check_reserve_basis()` dispatch
  guard; called from every product's `compute_reserves()`. Non-default bases
  raise `PolarisComputationError` (never a silent fallback).
- Tests: enum, config plumbing, serialization round-trip, default==explicit
  NET_PREMIUM byte-identical, unimplemented bases raise.
- ADR-087. Goldens byte-identical (default path untouched).

### Slice 2 — CRVM concrete basis (Term + WL)
- Implement the CRVM modified reserve: the first-year expense allowance graded
  in via the modified net premiums (β/α split), with the valuation mortality
  table (2001 CSO) and statutory valuation rate.
- `_supported_reserve_bases` on TermLife / WholeLife gains CRVM; dispatch in
  `compute_reserves()` picks the CRVM recursion.
- **Closed-form test** vs a worked CRVM example (a textbook level-premium
  whole-life CRVM reserve), plus the **WL terminal-reserve acceptance test**.
- Decide (ADR) how the valuation table is supplied — likely a
  `reserve_assumptions` slot on `AssumptionSet` or a `valuation_mortality`
  hook on `ProjectionConfig`. Keep NET_PREMIUM default byte-identical.

### Slice 3 — VM-20 simplified (deterministic reserve / NPR floor)
- VM-20 simplified PBR: deterministic reserve = max(NPR, modelled reserve
  floor) on prescribed valuation assumptions. Scope is the NPR floor +
  deterministic reserve only (no stochastic scenarios).
- Closed-form / regression test against a worked simplified-PBR example.

### Slice 4 — Surface the basis selector
- CLI (`--reserve-basis`), API request schema, Excel workbook (label the
  reserve sheet with the basis), and the validation notebook comparing the
  profit signature across bases on the golden block.
- This is the slice that *can* move goldens — and only for runs that select a
  non-default basis. Document any regenerated baselines with the reason.

## 4. Key constraints (from CLAUDE.md / ARCHITECTURE.md)

- Vectorised: reserve recursions stay `(N, T)` numpy, no per-policy loops over
  the block (the existing month loop is fine — it is over T, not N).
- Every actuarial basis gets a closed-form verification test.
- No `Optional` / `List`; Python 3.12 typing. `float64` for monetary arrays.
- Do not hardcode valuation assumptions in product code — they flow through
  the assumption/config layer (CLAUDE.md §10 "Never hardcode assumptions").
- Treaty layer (YRT NAR, coinsurance reserve transfer) consumes whatever
  `compute_reserves()` returns, so switching basis automatically reprices the
  treaty — no treaty-layer changes needed.

## 5. Open design questions (resolve in Slice 2)

- Where does the **valuation mortality table** (2001 CSO for CRVM) live? It is
  distinct from the *projection* (best-estimate) mortality. Candidate: a
  `valuation_mortality` field on `AssumptionSet`, defaulting to the projection
  table when absent. This is a controlled core-contract change → needs an ADR
  and a CONTINUATION note, with a default preserving backward compatibility.
- CRVM expense-allowance cap (the 20-pay-whole-life expense-allowance limit) —
  confirm the formula against a cited source before coding; mark TODO if
  uncertain rather than guessing.
