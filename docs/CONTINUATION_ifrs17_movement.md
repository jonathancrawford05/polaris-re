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
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-g9282o (environment-designated)
- **PR:** (this session's draft)
- **What was done:** Added `IFRS17ComponentMovement` (one component's
  opening / new_business / interest_accretion / release / closing, with
  `footing_error()` + `__add__`), `IFRS17MovementRow` (one reporting period
  across BEL / RA / CSM with a derived `total` column), `IFRS17MovementTable`
  (ordered rows + `max_footing_error()`), and a module-level
  `build_movement_table(result, locked_in_rate, *, months_per_period=12,
  issue_year=None)`. The manager gained `cohort_movement_tables()` and
  `aggregate_movement_table()` (the per-period, per-component sum of the cohort
  tables). The roll-forward foots by construction (the per-month BEL/CSM change
  telescopes to `closing − opening`); CSM accretes at the cohort's locked-in
  rate. ADR-094. Goldens byte-identical (additive analytics, not wired into
  pricing).
- **Key decisions:**
  - **Annual reporting periods** (`months_per_period=12` default); a trailing
    partial period is handled and still foots.
  - **Period-0 new-business convention:** the cohort's first reporting period
    opens at 0 and carries the initial-recognition balance in `new_business`;
    later periods open at the prior closing. The mid-life in-force opening
    variant (period-0 opening = current in-force balance) is a promoted
    follow-up for Slice 3 / future.
  - **RA carries no finance line** under the simplified cost-of-capital RA; its
    whole period change is the risk release.

### Slice 3: Surface the movement table
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:** `POST /api/v1/ifrs17/movement`; an "IFRS 17 Movement" Excel sheet;
  CLI surfacing (flag on `polaris price` or a dedicated subcommand). This is the
  only slice that may move goldens, and only for runs that request the table.

## Context for Next Session

- **Slice 3 (surfacing) is NEXT.** The movement table is built and tested; Slice
  3 wires it to `POST /api/v1/ifrs17/movement`, an "IFRS 17 Movement" Excel
  sheet, and CLI (a `polaris price` opt-in flag or a `polaris ifrs17`
  subcommand — decide in the slice). This is the only slice that may move
  goldens, and only for runs that request the table.
- The data the surfacing layer consumes:
  `IFRS17CohortManager.cohort_movement_tables()` (per cohort, ordered by issue
  year) and `.aggregate_movement_table()` (the aggregate). Each
  `IFRS17MovementTable` has `.rows` (`IFRS17MovementRow`), and each row exposes
  `.bel/.ra/.csm/.total` as `IFRS17ComponentMovement`
  (`opening / new_business / interest_accretion / release / closing`). A
  `to_dict`/serialiser for the API/Excel does not yet exist — add it in Slice 3.
- Reporting periods are annual; `build_movement_table(..., months_per_period=N)`
  supports other groupings if the surface wants them.
- Open follow-up to weigh in Slice 3: the **mid-life in-force opening** variant
  (period-0 opening = current in-force balance rather than 0 + new business) —
  the from-recognition roll-forward shipped here is the natural fit for a
  cohort projected from inception; a mid-life filing may want the other opening.

## Open Questions (for human)

- Confirm annual reporting periods are the intended granularity for the movement
  table (IFRS 17 cohorts are annual; the underlying schedules are monthly).
- Heterogeneous-term cohort calendar alignment (different policy terms issued the
  same year) is deferred to a follow-up — confirm this is acceptable for the
  first filing-grade movement table.
