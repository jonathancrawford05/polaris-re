# Continuation: IFRS 17 period-to-period movement table (Epic 2 / Tier-A A2)

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier A, item A2
(also PRODUCT_DIRECTION_2026-06-18 IMPORTANT "IFRS 17 period-to-period movement
table"; ROADMAP Milestone 5.3).
**Plan:** docs/PLAN_ifrs17_movement.md
**Status:** COMPLETE (Slice 1 #87, Slice 2 #88, Slice 3a #89, Slice 3b #90,
Slice 3c shipped this draft)
**Total slices:** 3 (Slice 3 sub-sliced 3a/3b/3c)
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
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-g66b30 (environment-designated)
- **PR:** (this session's draft)
- **What was done:** Added `IFRS17MovementExport` (frozen dataclass bundling the
  `aggregate` + per-cohort `IFRS17MovementTable`s) and an
  `ifrs17_movement: IFRS17MovementExport | None = None` field on
  `DealPricingExport`. `write_deal_pricing_excel` now appends an
  "IFRS 17 Movement" sheet **last** when the field is populated: the aggregate
  block first, then one block per issue-year cohort (titled with its locked-in
  rate), each rendering BEL / RA / CSM / total as a Year x movement-line
  sub-table (Opening / New Business / Interest Accretion / Release / Closing) and
  printing its `max_footing_error`. `None` (the default, and every current
  `polaris price` run) suppresses the sheet → goldens byte-identical. ADR-096.
- **Key decisions:**
  - The export carries the **typed** `IFRS17MovementTable` objects, matching the
    `DealPricingExport` precedent (`PremiumSufficiencyResult` ADR-083,
    `YRTRateTable` ADR-052 are likewise typed objects), giving the writer
    type-safe field access. The rendered fields are exactly those the 3a
    `to_dict()` serialiser exposes, so Excel and JSON agree.
  - The sheet is **appended last** so every other sheet position is unchanged.
  - The CLI does NOT populate `ifrs17_movement` yet — that is Slice 3c, which
    decides the cohorting inputs (issue-year grouping + per-year locked-in rates)
    for the `polaris price` path.

#### Slice 3c: CLI surface
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-p8n0cn (environment-designated)
- **PR:** (this session's draft)
- **What was done:** Added `polaris price --ifrs17-movement` (with
  `--ifrs17-ra-factor` default 0.05 and `--ifrs17-months-per-period` default 12).
  When set, the movement table is built **per product cohort** (`iter_cohorts`):
  each cohort's policies are re-grouped into annual issue-year cohorts, each
  issue-year sub-block is projected GROSS via the product dispatcher, and the
  groups feed `IFRS17CohortManager`. The result is added to the JSON output in the
  REST-mirroring shape (`{months_per_period, n_cohorts, max_footing_error,
  aggregate, cohorts}`, reusing the 3a `to_dict()`), per cohort and (single-cohort
  case) at the top level; rendered as two compact Rich tables; and — with
  `--excel-out` — populates `DealPricingExport.ifrs17_movement` so the Slice-3b
  sheet appears on the same run. Off by default → goldens byte-identical. ADR-097.
- **Key decisions:**
  - **Per-product-cohort, not block-wide.** TERM and WHOLE_LIFE project on
    different grids, so a block-wide aggregate fails the cohort manager's
    alignment check. Per-product also matches the per-cohort Excel workbook model
    (ADR-068). A cross-product common-grid aggregate is a promoted follow-up.
  - **Locked-in rate = `config.discount_rate`** for every cohort; a per-issue-year
    override (the REST API's `locked_in_rates` map) is a promoted CLI follow-up.
  - Chose the `price` opt-in flag over a dedicated subcommand because `price`
    owns `--excel-out`, so one run surfaces JSON + Rich + the Excel sheet.

## Context for Next Session

- **Slice 3c (CLI) is NEXT.** Slices 3a (API) and 3b (Excel) are merged-pending;
  the CLI is the last surface. The Excel sheet (3b) is wired to the writer but
  is only emitted when `DealPricingExport.ifrs17_movement` is populated — nothing
  populates it yet, so Slice 3c must build the cohort manager from the priced
  block and set that field (and/or emit a JSON/Rich movement table directly).
- The data the surfacing layer consumes:
  `IFRS17CohortManager.cohort_movement_tables()` (per cohort, ordered by issue
  year) and `.aggregate_movement_table()` (the aggregate). The API endpoint
  `POST /api/v1/ifrs17/movement` is the reference consumer: it groups policies by
  `issue_date.year`, projects each group GROSS, and feeds `IFRS17CohortManager`.
  The CLI should mirror that cohorting.
- The serialiser (`IFRS17MovementTable.to_dict()` and friends, ADR-095) is the
  shared JSON contract — table metadata (`months_per_period`, `issue_year`,
  `locked_in_rate`, `n_periods`, `max_footing_error`) plus `rows`, each row
  carrying `bel/ra/csm/total` as
  `{opening, new_business, interest_accretion, release, closing, footing_error}`.
- Reporting periods are annual; `build_movement_table(..., months_per_period=N)`
  supports other groupings if the surface wants them.
- Open follow-up to weigh in Slice 3c: the **mid-life in-force opening**
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
