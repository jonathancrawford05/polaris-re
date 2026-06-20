# Continuation: IFRS 17 period-to-period movement table (Epic 2 / Tier-A A2)

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier A, item A2
(also PRODUCT_DIRECTION_2026-06-18 IMPORTANT "IFRS 17 period-to-period movement
table"; ROADMAP Milestone 5.3).
**Plan:** docs/PLAN_ifrs17_movement.md
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~10 dev-days

## Overall Goal

Let an IFRS 17 filer produce the IASB-style **analysis of change** (movement)
table — opening balance → new business → unwinding/accretion → expected
experience/release → closing balance, for BEL / RA / CSM — by **annual
issue-year cohort** with a **locked-in discount rate per cohort**, in aggregate
and per cohort. The existing `IFRS17Measurement` gives only point-in-time
schedules; the movement table IS the disclosure a filer must publish.

## Decomposition

### Slice 1: `IFRS17CohortManager` + cohort grouping
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-h7mn4m (environment-designated)
- **PR:** (this session's draft)
- **What was done:** Added `IFRS17ContractInput` (GROSS cashflows + issue_date +
  locked_in_rate + ra_factor), `IFRS17Cohort` (issue_year, locked_in_rate,
  ra_factor, n_contracts, aggregated cashflows, per-cohort `IFRS17Result`), and
  `IFRS17CohortManager`. The manager groups contracts into annual issue-year
  cohorts, aggregates the aligned GROSS cash flows within each cohort, measures
  each cohort **BBA at its own locked-in rate**, orders cohorts by issue year,
  and exposes aggregate balance-sheet schedules (Σ over cohorts of BEL / RA /
  CSM / insurance_liability). ADR-093.
- **Key decisions:**
  - All contracts must share projection alignment (`projection_months`,
    `valuation_date`, `time_index`) so the aggregate is calendar-consistent —
    an inforce block valued at a common date, cohorted by historical issue year,
    each cohort carrying its issue-era locked-in rate. Heterogeneous-term
    calendar alignment is a promoted follow-up (Slice 2 / future).
  - Contracts within one cohort must share `locked_in_rate` and `ra_factor`
    (the cohort is recognised together); mismatches raise
    `PolarisValidationError`.
  - The cohort layer **composes** `IFRS17Measurement.measure_bba()` rather than
    re-deriving the BEL/RA/CSM recursions. Goldens byte-identical (new types,
    nothing wired into pricing).

### Slice 2: `IFRS17MovementTable` (analysis of change)
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `analytics/ifrs17.py` (add `IFRS17MovementRow`,
  `IFRS17MovementTable`, a `build_movement_table()` on the manager);
  `tests/test_analytics/test_ifrs17_movement.py`.
- **Tests to add:** the **additivity** test (opening + Σ movements = closing for
  BEL / RA / CSM, every period); CSM exhaustion at contract expiry; locked-in
  rate preserved across periods; aggregate movement == Σ cohort movements.
- **Acceptance criteria:**
  - Per cohort and aggregate, a structured movement table whose components foot:
    `opening + Σ movements == closing` to `assert_allclose`.
  - CSM accretes at the cohort's locked-in rate (not a single global rate).
  - Annual reporting periods derived consistently from the monthly schedules.

### Slice 3: Surface the movement table
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:** `POST /api/v1/ifrs17/movement`; an "IFRS 17 Movement" Excel sheet;
  CLI surfacing (flag on `polaris price` or a dedicated subcommand). This is the
  only slice that may move goldens, and only for runs that request the table.

## Context for Next Session

- Slice 1's `IFRS17CohortManager.cohorts` is a list of `IFRS17Cohort`, each
  carrying its `result: IFRS17Result` and `locked_in_rate`. Slice 2 rolls each
  cohort's monthly schedules into annual reporting-period movements; the
  locked-in rate for CSM accretion is `cohort.locked_in_rate`.
- The aggregate schedules (`aggregate_bel()` etc.) already sum index-wise across
  cohorts because Slice 1 enforces a common projection grid — Slice 2's
  aggregate movement table is the sum of the per-cohort movement tables on the
  same grid.
- Reporting-period granularity (annual) is the one real design decision in
  Slice 2 — document the monthly→annual aggregation convention in ADR-094.

## Open Questions (for human)

- Confirm annual reporting periods are the intended granularity for the movement
  table (IFRS 17 cohorts are annual; the underlying schedules are monthly).
- Heterogeneous-term cohort calendar alignment (different policy terms issued the
  same year) is deferred to a follow-up — confirm this is acceptable for the
  first filing-grade movement table.
