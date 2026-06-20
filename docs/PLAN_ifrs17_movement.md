# Plan — IFRS 17 period-to-period movement table (Epic 2 / Tier-A A2)

> **Audience.** A new Claude Code session carrying this epic across several
> daily-dev runs. Read this document fully before writing code, then read the
> linked CLAUDE.md / ARCHITECTURE.md (§ IFRS 17) / DECISIONS.md (ADR-035/036 on
> the existing point-in-time IFRS 17 measurement) sections. This plan is the
> read-only spec; the running log lives in
> `docs/CONTINUATION_ifrs17_movement.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** IN PROGRESS — Slice 1 shipped (`IFRS17CohortManager` + cohort
> grouping by issue year with per-cohort locked-in rate).
>
> **Source.** `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A item
> **A2** (★★★★★ value, ~10 dev-days, the #2 unstarted epic, started after A1
> Reserve-basis matching shipped) and `docs/ROADMAP.md` Milestone 5.3, and
> `docs/PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT "IFRS 17 period-to-period
> movement table".

---

## 1. Goal

`analytics/ifrs17.py` today computes BEL / RA / CSM **at a single point in
time** (initial recognition, with prospective schedules) for one block. A real
IFRS 17 filer must publish, every reporting period, an **analysis of change**
(movement) table that reconciles the *opening* insurance-liability balance to
the *closing* balance through named movements:

```
            BEL                RA                 CSM
opening     opening BEL        opening RA         opening CSM
+ new business
+ unwinding (interest)         accretion at the locked-in rate
- expected experience / release
± changes in estimate
closing     closing BEL        closing RA         closing CSM
```

The two production-grade requirements the point-in-time model does not meet:

1. **Annual issue-year cohorts** with a **locked-in discount rate per cohort**
   (IFRS 17 requires the CSM to accrete at the rate locked in at the cohort's
   initial recognition; cohorts cannot be netted against each other — the
   onerous-contract grouping rule).
2. **Opening + Σ movements = closing** additivity for *each* component, in
   *every* reporting period, so the table foots to the balance sheet.

When complete, the engine can produce an IASB-style movement table by cohort
and in aggregate, surfaced on the API / Excel / CLI.

## 2. Why this work, and what it does NOT do

**Why.** Both PRODUCT_DIRECTION files have carried the IFRS 17 movement table
as IMPORTANT for two months; the 2026-06-18 review ranks it the #2 Tier-A epic
(after Reserve-basis matching, now shipped). A filer that can only produce a
point-in-time BEL/CSM cannot file — the movement table IS the disclosure.

**Does NOT.**

- It does **not** change the existing point-in-time `IFRS17Measurement` /
  `IFRS17Result` API or any default numbers; the movement layer is **additive**
  and goldens stay byte-identical until the final surfacing slice (and even
  then only for runs that request a movement table).
- It does **not** add the full IFRS 17 disclosure suite (reconciliation of the
  LRC/LIC split for PAA, the insurance-finance-income/OCI option, transition
  approaches). Scope is the BBA analysis-of-change for BEL / RA / CSM.
- It does **not** re-derive the BEL/RA/CSM schedules — it rolls forward the
  schedules `IFRS17Measurement` already produces, per cohort.

## 3. Decomposition (3 slices)

Each slice leaves all tests green, is independently mergeable, and keeps the
goldens byte-identical until the final surfacing slice.

### Slice 1 — `IFRS17CohortManager` + cohort grouping  ✅ SHIPPED
- `analytics/ifrs17.py`: `IFRS17ContractInput` (GROSS cashflows + issue_date +
  locked_in_rate + ra_factor), `IFRS17Cohort` (issue_year, locked_in_rate,
  n_contracts, the per-cohort `IFRS17Result`), `IFRS17CohortManager`.
- The manager groups contracts into **annual issue-year cohorts**, aggregates
  the aligned GROSS cash flows within each cohort, measures each cohort **BBA at
  its own locked-in rate**, and exposes the cohorts (ordered by issue year) plus
  aggregate balance-sheet schedules (Σ over cohorts of BEL / RA / CSM /
  insurance_liability at each period).
- Tests: grouping (same year → one cohort, different years → distinct cohorts);
  locked-in rate preserved per cohort; aggregate == Σ cohorts; a single-cohort
  manager reproduces a direct `IFRS17Measurement.measure_bba()`; alignment /
  basis / empty-input validation; cohorts ordered by issue year.
- ADR-093. Goldens byte-identical (new types, nothing wired into pricing).

### Slice 2 — `IFRS17MovementTable` (analysis of change)
- For each cohort and each annual reporting period, decompose the change in
  BEL / RA / CSM into named movements: opening, new business (period 0 only),
  unwinding / CSM accretion at the **locked-in** rate, expected experience /
  release, closing. CSM accretion uses the cohort's locked-in rate (already
  carried by Slice 1).
- `IFRS17MovementRow` / `IFRS17MovementTable` dataclasses: structured output
  matching the IASB reconciliation layout, per cohort and aggregate.
- **Additivity test** (the headline acceptance test): for every component and
  every period, `opening + Σ movements == closing` to `assert_allclose`.
  Plus: CSM exhaustion at contract expiry; locked-in rate preserved across
  periods; aggregate movement == Σ cohort movements.
- ADR-094. Goldens byte-identical (additive analytics, not wired into pricing).

### Slice 3 — Surface the movement table
- `api/main.py`: `POST /api/v1/ifrs17/movement` returning the per-cohort and
  aggregate movement rows.
- Excel: a "IFRS 17 Movement" sheet in the deal-pricing workbook.
- CLI: a movement summary on `polaris price` (opt-in flag) or a dedicated
  `polaris ifrs17` subcommand — decide in the slice.
- This is the slice that *can* move goldens, and only for runs that request the
  movement table. Document any regenerated baselines with the reason.

## 4. Key constraints (from CLAUDE.md / ARCHITECTURE.md)

- Vectorised: roll-forwards stay numpy `(T,)` per cohort, no per-policy loops.
  The per-period loop (over T) and the per-cohort loop (over a handful of issue
  years) are both fine — they are not loops over the seriatim block.
- Every actuarial roll-forward gets a closed-form / additivity verification test
  (CLAUDE.md §5). The movement table's defining property is additivity.
- No `Optional` / `List`; Python 3.12 typing. `float64` for monetary arrays.
- Do not hardcode the discount rate in the cohort layer — the locked-in rate
  flows in per contract/cohort (CLAUDE.md §10 "Never hardcode assumptions").
- The point-in-time `IFRS17Measurement` is the engine; the cohort/movement
  layer composes it. Do not duplicate the BEL/RA/CSM recursions.

## 5. Open design questions (resolve as the epic proceeds)

- **Reporting-period granularity.** The roll-forward is naturally annual (IFRS
  17 cohorts are annual), but the underlying schedules are monthly. Slice 2 must
  pick the reporting period (annual) and aggregate the monthly schedules into
  it consistently (opening = start-of-year balance, movements summed over the 12
  months). Document the convention in ADR-094.
- **Cohort cash-flow alignment.** Slice 1 requires contracts within a cohort to
  share projection alignment (`projection_months`, `valuation_date`,
  `time_index`) so the aggregate cash flow is well defined. Heterogeneous-term
  cohorts (different policy terms issued the same year) need a common calendar
  grid — promoted as a follow-up, not blocking the movement table.
- **New-business vs in-force opening.** The first reporting period of a cohort
  is all "new business" (opening balance 0 → recognition); later periods open at
  the prior closing. Slice 2 must handle the period-0 new-business row distinctly
  from the steady-state unwinding rows.
