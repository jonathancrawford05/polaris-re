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
Decomposed into three sub-slices (repo sub-slicing convention). Goldens stay
byte-identical for 3a (additive API); 3b/3c may move goldens only for runs that
request the table.

#### Slice 3a: REST API + serialiser
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-rv9uuj (environment-designated)
- **PR:** (this session's draft)
- **What was done:** Added `to_dict()` to `IFRS17ComponentMovement`,
  `IFRS17MovementRow`, `IFRS17MovementTable` (plain-Python / JSON-serialisable,
  carrying the footing residual). Added `POST /api/v1/ifrs17/movement`
  (`IFRS17MovementRequest` → `IFRS17MovementResponse`): groups the request's
  policies into annual issue-year cohorts, projects each group GROSS, builds one
  `IFRS17ContractInput` per cohort at its own locked-in rate (optional
  `locked_in_rates` override map; `months_per_period` annual default), and
  returns the aggregate + per-cohort serialised tables plus the worst footing
  residual. ADR-095. Goldens byte-identical (additive route).
- **Key decisions:** the serialiser is shared by all three 3x surfaces;
  per-cohort locked-in rate defaults to the request `discount_rate`; mixed
  valuation dates surface the cohort manager's alignment error as HTTP 422.

#### Slice 3b: Excel "IFRS 17 Movement" sheet
- **Status:** NEXT
- **Depends on:** Slice 3a merged
- **Scope:** an "IFRS 17 Movement" sheet in the deal-pricing workbook
  (`utils/excel_output.py`), consuming the `to_dict()` serialiser shipped in 3a.
- May move goldens only for runs that request the movement sheet.

#### Slice 3c: CLI surface
- **Status:** PLANNED
- **Depends on:** Slice 3b merged
- **Scope:** a `polaris price` opt-in flag or a dedicated `polaris ifrs17`
  subcommand emitting the movement table (JSON / Rich), reusing the 3a serialiser.

## Context for Next Session

- **Slice 3b (Excel) is NEXT.** The serialiser (`IFRS17MovementTable.to_dict()`
  and friends) shipped in 3a is the data source — it returns table metadata
  (`months_per_period`, `issue_year`, `locked_in_rate`, `n_periods`,
  `max_footing_error`) plus `rows`, each row carrying `bel/ra/csm/total` as
  `{opening, new_business, interest_accretion, release, closing, footing_error}`.
- The API endpoint `POST /api/v1/ifrs17/movement` is the reference consumer:
  it groups policies by `issue_date.year`, projects each group, and feeds
  `IFRS17CohortManager`. The Excel/CLI surfaces should mirror that cohorting.
- The data the surfacing layer consumes:
  `IFRS17CohortManager.cohort_movement_tables()` (per cohort, ordered by issue
  year) and `.aggregate_movement_table()` (the aggregate).
- Reporting periods are annual; `build_movement_table(..., months_per_period=N)`
  supports other groupings if the surface wants them.
- Open follow-up to weigh in Slice 3b/3c: the **mid-life in-force opening**
  variant (period-0 opening = current in-force balance rather than 0 + new
  business) — the from-recognition roll-forward shipped here is the natural fit
  for a cohort projected from inception; a mid-life filing may want the other
  opening.

## Open Questions (for human)

- Confirm annual reporting periods are the intended granularity for the movement
  table (IFRS 17 cohorts are annual; the underlying schedules are monthly).
- Heterogeneous-term cohort calendar alignment (different policy terms issued the
  same year) is deferred to a follow-up — confirm this is acceptable for the
  first filing-grade movement table.
