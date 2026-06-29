# Plan — Sliding-scale expense allowances & experience refunds (Tier-B B3)

> **Audience.** A new Claude Code session that will carry this epic across
> several daily-dev runs. Read this document fully before writing code, then
> read CLAUDE.md, ARCHITECTURE.md (§5 "Reinsurance Treaties"), and DECISIONS.md.
> This plan is the read-only spec; the running log lives in
> `docs/CONTINUATION_expense_allowance.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** IN PROGRESS — Slice 1 shipped 2026-06-29 (ADR-118: the
> `ExpenseAllowance` model + computation primitive, not yet wired into any
> treaty → goldens byte-identical). Running log:
> `docs/CONTINUATION_expense_allowance.md`.
>
> **Source.** `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-B item
> **B3** — "Sliding-scale expense allowances / experience refunds
> (`reinsurance/expense_allowance.py`) — standard in large YRT deals"
> (★★★★☆ value, ~3 dev-days, 1–2 phases). Selected as the active Epic for the
> 2026-06-29 run: the three Tier-A epics (A1 reserve-basis, A2 IFRS 17 movement,
> A3 cross-jurisdiction capital) and the post-ladder C0 Asset/ALM epic are all
> COMPLETE, so B3 is the highest value × effort epic-sized item remaining.

---

## 1. Goal

Give Polaris RE a real **expense-allowance** mechanism on its proportional
treaties. Today a coinsurance treaty carries only a boolean
`include_expense_allowance` that, when true, simply shares the cedant's
expenses proportionally (`ceded_expense_t = gross_expense_t × c`). That is a
crude approximation: in a real YRT or coinsurance treaty the reinsurer pays the
cedant a separately-negotiated **allowance** — typically a percentage of the
ceded premium, with a high **first-year** rate (to reimburse acquisition cost)
and a lower **renewal** rate, and frequently on a **sliding scale** where the
allowance rate rises as the cedant's loss experience improves. Large YRT deals
also carry an **experience refund** (profit-sharing): when accumulated
experience is favourable, the reinsurer refunds a share of the gain to the
cedant.

When complete the engine can:

- Model a per-treaty `ExpenseAllowance` (first-year %, renewal %, optional
  sliding scale keyed to loss ratio) and compute the period-by-period
  allowance the reinsurer pays the cedant.
- Apply that allowance inside `CoinsuranceTreaty` and `YRTTreaty` as an
  explicit reinsurer→cedant transfer that preserves the `net + ceded == gross`
  additivity invariant (allowance adds to ceded expense, nets out of cedant
  expense).
- Compute an **experience refund** from accumulated treaty experience and
  surface the allowance + refund on the CLI / API / Excel deal-pricing path.

## 2. Why this work, and what it does NOT do

**Why.** Expense allowances are the economic core of how a reinsurer competes
on a proportional deal — the allowance is the cedant's compensation for
originating and administering the business, and the sliding scale is the
standard mechanism for aligning both parties to good experience. Without it the
engine cannot reproduce the cash flows of any real large YRT/coinsurance treaty;
the boolean approximation systematically misstates both parties' net cash flow.

**Does NOT.**

- It does **not** change `CashFlowResult`'s contract. The allowance is folded
  into the existing `expenses` line as a reinsurer→cedant transfer (preserving
  additivity), not added as a new array field. A dedicated allowance line is a
  possible future refinement (it would be a contract change → its own ADR).
- It does **not** model reinsurance commissions distinct from expense
  allowances — in this engine they are the same `% of ceded premium` cash flow.
- It does **not** add stochastic/experience-driven *re-rating* of the allowance
  across scenarios; the sliding scale keys off the projected loss ratio of the
  base run.

## 3. Decomposition (data-model-first, then consumers — Pattern A)

### Slice 1 — `ExpenseAllowance` model + computation primitive (SHIPPED, ADR-118)
- New `reinsurance/expense_allowance.py`: `ExpenseAllowanceBand` +
  `ExpenseAllowance` Pydantic models and a pure `compute_allowance()` primitive.
- First-year vs renewal rate on `% of ceded premium`; optional sliding scale
  selecting the renewal rate from loss-ratio bands.
- Full unit + closed-form tests. **Not wired into any treaty** → all goldens
  byte-identical. (~250 lines + tests)

### Slice 2 — wire into `CoinsuranceTreaty` + `YRTTreaty` (NEXT)
- Add an optional `expense_allowance: ExpenseAllowance | None = None` field to
  both treaties (default `None` → current behaviour, goldens byte-identical).
- When set, compute the allowance off the ceded premium and apply it as a
  transfer: `ceded.expenses += allowance`, `net.expenses -= allowance`. The
  NCF additivity invariant (`verify_additivity`) must still pass.
- Closed-form tests: a known premium stream + known FY/renewal rates →
  hand-computed allowance; additivity holds; `include_expense_allowance`
  interaction documented. (~250 lines)

### Slice 3 — experience refund + CLI/API/Excel surfacing (PLANNED)
- `ExperienceRefund` (refund % of accumulated favourable experience above a
  retention) computed from the ceded cash flows.
- Surface allowance + refund terms on the deal-pricing path: `DealConfig` /
  CLI flag(s), API field(s), and an Excel line. (~250 lines)

Each slice leaves the suite green and is independently mergeable. Slices 1–2
are byte-identical on existing goldens; slice 3 is opt-in (default off) so it
is byte-identical unless the new terms are supplied.

## 4. Key design decisions

- **Allowance is a transfer, not a new external flow.** Additivity
  (`net + ceded == gross`) is the treaty invariant. A reinsurer→cedant
  allowance moves money between the two sides without changing the gross block,
  so it must net to zero across the (net, ceded) pair. Folding it into the
  `expenses` line (+A on ceded, −A on net) achieves this with no contract change.
- **First year = projection months 0–11** (duration year 1), renewal = months
  12+. `months_per_year` is configurable (default 12) for non-monthly grids.
- **Sliding scale is monotone non-increasing in loss ratio.** Better experience
  (lower loss ratio) must pay an allowance rate at least as high as worse
  experience. A validator enforces this so a mis-ordered scale fails loudly
  (`PolarisValidationError`) rather than silently inverting the incentive.

## 5. Open design questions (resolve as slices land)

- Should the sliding scale key off the **ceded** loss ratio or the **gross**
  block loss ratio? Slice 1 computes it from whatever claims/premiums the caller
  passes; Slice 2 will pass the **ceded** figures (the reinsurer's own
  experience drives its allowance). Revisit if a cedant submission specifies the
  gross basis.
- Experience-refund accumulation basis (with vs without interest) — deferred to
  Slice 3's ADR.
- **First-year mapping on inforce blocks.** Slice 1's primitive treats "first
  year" as the first `months_per_year` *projection* periods (correct for
  new business from inception). Slice 2 must map projection periods to each
  policy's actual duration — most inforce policies are mid-duration, so a naive
  application would wrongly grant the first-year rate to renewal business. See
  CONTINUATION Slice 2 acceptance criteria. *(Source: PR #117 review P2.)*
