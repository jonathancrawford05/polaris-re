# Dev Session Log — 2026-06-20

## Item Selected
- **Source:** CONTINUATION_ifrs17_movement.md (Epic 2 / Tier-A A2 from
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md; ROADMAP Milestone 5.3)
- **Priority:** Tier A (IMPORTANT epic)
- **Title:** IFRS 17 period-to-period movement table
- **Slice:** 2 of 3 — `IFRS17MovementTable` (analysis of change)
- **Branch:** claude/awesome-bardeen-g9282o (environment-designated)

## Selection Rationale
`CONTINUATION_ifrs17_movement.md` is **IN PROGRESS** with Slice 1 (`IFRS17CohortManager`,
PR #87) **merged** to main (origin/main HEAD 371f57e includes it). Per the
routine (step 5 → "if merged: continue on a new branch from main"; step 5b → the
active Epic's next unchecked slice is advanced before any fallback pick), the
session's deliverable is **Slice 2**. No fallback work selected — the Epic
consumed the session. The latest commercial-viability review (2026-06-18, 2 days
old) is not stale; no regeneration needed.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `IFRS17CohortManager` + cohort grouping (annual issue-year, locked-in rate) | ✅ Done | #87 |
| 2 | `IFRS17MovementTable` (opening→…→closing analysis of change) + additivity test | ✅ Done | (this draft) |
| 3 | `POST /api/v1/ifrs17/movement` + Excel sheet + CLI surfacing | ⏳ Next | — |

## What Was Done
Advanced Epic 2 by shipping Slice 2 — the IFRS 17 **analysis of change**
(movement) table that rolls the Slice-1 cohort schedules forward.

Three new types in `analytics/ifrs17.py`: `IFRS17ComponentMovement` (one
component's `opening / new_business / interest_accretion / release / closing`,
with `footing_error()` and `__add__` for aggregation), `IFRS17MovementRow` (one
reporting period across BEL / RA / CSM with a derived `total` column), and
`IFRS17MovementTable` (the ordered rows + `max_footing_error()`). A module-level
`build_movement_table(result, locked_in_rate, *, months_per_period=12,
issue_year=None)` does the roll-forward; `IFRS17CohortManager` gained
`cohort_movement_tables()` and `aggregate_movement_table()`.

The decomposition **foots by construction**: within a month the BEL change is
`interest − FCF` and the CSM change is `accretion − release`, so summing the
per-month movements over a reporting period telescopes to `closing − opening`.
BEL unwinding uses the cohort's locked-in rate; CSM accretion and release come
straight from the engine's monthly roll-forward (so the CSM accretes at the
locked-in rate, not a global one); the simplified cost-of-capital RA carries no
finance line, so its whole period change is the risk release. Reporting periods
are annual by default; the cohort's first period opens at 0 and recognises the
initial balance as `new_business`, later periods open at the prior closing. The
slice is purely additive — nothing wired into pricing, so goldens are
byte-identical (verified). ADR-094.

## Files Changed
- `src/polaris_re/analytics/ifrs17.py` — added `IFRS17ComponentMovement`,
  `IFRS17MovementRow`, `IFRS17MovementTable`, `build_movement_table`, and the
  manager's `cohort_movement_tables()` / `aggregate_movement_table()`; widened
  `__all__`.
- `src/polaris_re/analytics/__init__.py` — re-export + `__all__` for the four new
  public names.
- `docs/PLAN_ifrs17_movement.md` — Slice 2 marked ✅ SHIPPED.
- `docs/CONTINUATION_ifrs17_movement.md` — Slice 2 DONE, Slice 3 NEXT; refreshed
  "Context for Next Session".
- `docs/DECISIONS.md` — ADR-094.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — harvested 3 follow-ups (Slice 3
  surfacing; mid-life in-force opening; explicit RA finance line).

## Tests Added
- `tests/test_analytics/test_ifrs17_movement.py` (new, 18 tests): additivity
  (every cohort table + aggregate foot, annual and monthly granularity);
  new-business only in period 0 == initial recognition; opening chains to prior
  closing; all components exhaust at expiry; total == BEL+RA+CSM; CSM accretes at
  the locked-in rate (0.08 > 0.03) and ties out to the engine arrays; per-cohort
  table preserves issue_year/locked_in_rate (aggregate carries None); aggregate
  == Σ cohorts field-by-field; reporting-period count parametrized; closed-form
  BEL release == −Σ FCF; returned-type/period-count check.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Structured movement table, per cohort and aggregate | ✅ | `cohort_movement_tables()` / `aggregate_movement_table()` |
| `opening + Σ movements == closing` (every component, every period) | ✅ | `max_footing_error()` == 0 (atol 1e-9), annual + monthly |
| CSM accretes at the cohort's locked-in rate | ✅ | from engine roll-forward; 0.08 > 0.03 test + tie-out |
| Annual reporting periods from monthly schedules | ✅ | `months_per_period=12` default; partial period handled |
| Aggregate movement == Σ cohort movements | ✅ | field-by-field test |
| Goldens byte-identical | ✅ | additive analytics; QA golden suite 72 passed |
| Surfaced on API/Excel/CLI | ⏳ | Slice 3 |

## Open Questions / Follow-ups
- **Slice 3 (surfacing)** is the remaining slice: `POST /api/v1/ifrs17/movement`,
  an Excel "IFRS 17 Movement" sheet, a CLI surface, and a `to_dict` serialiser on
  the movement types (none exists yet). The only slice that may move goldens.
- **Mid-life in-force opening variant.** The shipped table is a from-recognition
  roll-forward (period-0 opens at 0 + new business). A mid-life filing may want
  period-0 opening = the current in-force balance. Promoted NICE-TO-HAVE.
- **Explicit RA finance/unwinding line.** The simplified RA has none; the whole
  period RA change is risk release. Promoted NICE-TO-HAVE.
- Heterogeneous-term cohort calendar alignment and PAA/VFA cohort movement remain
  promoted from ADR-093 (Slice 1).

## Parked Polish
None. (All harvested follow-ups are 1st-order — direct follow-ups of the
originally-planned movement-table feature — so none hit the step-17 order cap.)

## Impact on Golden Baselines
None. Slice 2 is additive (new movement types + manager methods, not wired into
pricing); the golden CLI run reproduces the committed output and the QA golden
suite (72 passed) is unchanged. No rebaseline.

## Baseline Note
`make test` baseline this session: **1482 passed, 83 deselected** — matches the
recorded Slice-1 post-change baseline; no new/changed failures. (convert-soa-tables
left the 4 CIA tables MISSING as in prior sessions — source unreachable; SOA VBT /
2001 CSO converted OK; no CIA-dependent failures.) Post-change: analytics suite
**559 passed** (+18 new movement tests), QA suite **72 passed**. mypy not run
locally per routine (CI's job; ~207 inherited baseline errors).
