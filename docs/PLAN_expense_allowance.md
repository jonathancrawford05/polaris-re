# Plan — Sliding-scale expense allowances & experience refunds (Tier-B B3)

> **Audience.** A new Claude Code session that will carry this epic across
> several daily-dev runs. Read this document fully before writing code, then
> read CLAUDE.md, ARCHITECTURE.md (§5 "Reinsurance Treaties"), and DECISIONS.md.
> This plan is the read-only spec; the running log lives in
> `docs/CONTINUATION_expense_allowance.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** IN PROGRESS — Slices 1, 2, 3a, and 3b-1 shipped; Slice 3b-2 NEXT.
> - Slice 1 (2026-06-29, ADR-118): `ExpenseAllowance` model + computation
>   primitive; not wired → goldens byte-identical.
> - Slice 2 (2026-06-29, ADR-119, PR #118 merged): wired into
>   `CoinsuranceTreaty` + `YRTTreaty` with the projection-month → policy-duration
>   first-year mapping; default `None` → goldens byte-identical.
> - Slice 3 was split data-model-first (the Slice-1 precedent) because surfacing
>   across four consumers is a session of its own:
>   - Slice 3a (2026-06-30, ADR-120): `ExperienceRefund` model + computation
>     primitive; not wired → goldens byte-identical.
>   - Slice 3b was further split once the surfacing path was surveyed (neither the
>     allowance nor the refund is on the deal path yet):
>     - Slice 3b-1 (2026-06-30, ADR-121): wired `ExperienceRefund` into
>       `CoinsuranceTreaty` + `YRTTreaty` as a terminal transfer; default `None` →
>       goldens byte-identical.
>     - Slice 3b-2 (NEXT): surface allowance + refund terms on `DealConfig` / CLI /
>       API / Excel.
>
> Running log: `docs/CONTINUATION_expense_allowance.md`.
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

### Slice 2 — wire into `CoinsuranceTreaty` + `YRTTreaty` (SHIPPED, ADR-119)
- Add an optional `expense_allowance: ExpenseAllowance | None = None` field to
  both treaties (default `None` → current behaviour, goldens byte-identical).
- When set, compute the allowance off the ceded premium and apply it as a
  transfer: `ceded.expenses += allowance`, `net.expenses -= allowance`. The
  NCF additivity invariant (`verify_additivity`) must still pass.
- Closed-form tests: a known premium stream + known FY/renewal rates →
  hand-computed allowance; additivity holds; `include_expense_allowance`
  interaction documented. (~250 lines)

### Slice 3a — `ExperienceRefund` model + computation primitive (SHIPPED, ADR-120)
- New `reinsurance/experience_refund.py`: `ExperienceRefund` Pydantic model +
  pure `experience_balance()` / `compute_refund()` primitives. The refund is
  `refund_pct · max(0, balance − retention)` of an experience account
  (`premium − claims − allowance − reinsurer_margin_pct·premium`), optionally
  accumulated at interest (default off). **Not wired into any treaty** → goldens
  byte-identical. Full unit + closed-form tests (25). (~190 lines + tests)

### Slice 3b-1 — wire refund into `CoinsuranceTreaty` + `YRTTreaty` (SHIPPED, ADR-121)
- Added `experience_refund: ExperienceRefund | None = None` to both treaties.
  When set, the refund is a single terminal reinsurer→cedant transfer at the
  final projection period (`BaseTreaty._experience_refund_transfer()`), folded
  into the expense line (+R ceded, −R net) so `net + ceded == gross`. Computed
  net of the expense allowance already paid. Default `None` → goldens
  byte-identical. 13 tests. (~70 lines + tests)

### Slice 3b-2 — surface allowance + refund on the deal-pricing path (NEXT)
- Surface allowance + refund terms on the deal-pricing path: `DealConfig` /
  CLI flag(s), API field(s), and an Excel line. Off by default → byte-identical
  unless the new terms are supplied. Surveyed surfaces: `core/pipeline.py`
  (~L567), `api/main.py` (~L790 + request model), `cli.py` config schema, and
  the deal-pricing Excel writer. (~250 lines)

Each slice leaves the suite green and is independently mergeable. Slices 1–3b-1
are byte-identical on existing goldens; slice 3b-2 is opt-in (default off) so it
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

- ~~Should the sliding scale key off the **ceded** loss ratio or the **gross**
  block loss ratio?~~ **RESOLVED (Slice 2, ADR-119):** Slice 2 passes the
  **ceded** figures (the reinsurer's own experience drives its allowance). A
  gross-basis option remains a promoted NICE-TO-HAVE follow-up — revisit if a
  cedant submission specifies the gross basis.
- ~~Experience-refund accumulation basis (with vs without interest).~~
  **RESOLVED (Slice 3a, ADR-120):** optional flat interest, default off
  (`interest_rate = 0` → simple undiscounted sum); otherwise each contribution
  accumulates forward to the settlement period at `(1 + interest_rate)^(1 /
  months_per_year)`.
- **First-year mapping on inforce blocks.** Slice 1's primitive treats "first
  year" as the first `months_per_year` *projection* periods (correct for
  new business from inception). Slice 2 must map projection periods to each
  policy's actual duration — most inforce policies are mid-duration, so a naive
  application would wrongly grant the first-year rate to renewal business. See
  CONTINUATION Slice 2 acceptance criteria. *(Source: PR #117 review P2.)*
