# Product Direction — 2026-05-23

## Purpose

This is an interim update to PRODUCT_DIRECTION_2026-04-19.md after the
completion of Milestone 5.2 (portfolio aggregation, two slices). It
performs two jobs at once:

1. **Closes out** the items from PRODUCT_DIRECTION_2026-04-19.md that
   have shipped since the last assessment.
2. **Promotes follow-ups** harvested from the five COMPLETE
   `docs/CONTINUATION_*.md` files into this work queue, with explicit
   provenance to the originating ADR / CONTINUATION. Without this step
   the daily-dev routine has no way to see them (see
   `docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-05-23.md`).

The shape (BLOCKERs / IMPORTANT / NICE-TO-HAVE) mirrors the
2026-04-19 file so the daily-dev routine's selection logic is
unchanged. No reasonability re-assessment is performed here — that
remains the nightly QA / quarterly review cadence's job.

## What Has Shipped Since 2026-04-19

Cross-referenced against `git log main` and the five COMPLETE
CONTINUATION files. All five items below are removed from the active
queue.

| Item from 2026-04-19            | Tier      | Closed by                                |
|---------------------------------|-----------|------------------------------------------|
| WL expense handling bug         | BLOCKER   | ADR-040 (prior session)                  |
| Per-policy substandard rating   | BLOCKER   | CONTINUATION_substandard_rating — COMPLETE (ADR-042/043/044) |
| LICAT regulatory capital        | BLOCKER   | CONTINUATION_licat_capital — COMPLETE (ADR-047/048/049) |
| Deal-pricing Excel export       | BLOCKER   | CONTINUATION_deal_pricing_excel — COMPLETE (ADR-045/046) |
| IRR / `profit_margin` guardrails| IMPORTANT | ADR-041 (prior session)                  |
| Portfolio aggregation           | IMPORTANT | CONTINUATION_portfolio_aggregation — COMPLETE (ADR-057/058) |
| YRT rate schedule (age × duration) | IMPORTANT | CONTINUATION_yrt_rate_table — COMPLETE (ADR-050/051/052/053/054/055) |
| A/E dashboard page              | NICE-TO-HAVE | ADR-056                               |

## What Remains From 2026-04-19

### BLOCKERs

(none — all four BLOCKERs from 2026-04-19 have shipped)

### IMPORTANT

- **Reserve basis matching (cedant reproduction).** `core/projection.py`
  supports one reserve basis (net premium with terminal conditions per
  product). Reinsurers must reproduce the cedant's reserves — GAAP,
  STAT VM-20, CRVM, CIA net premium, or deficiency reserves. **Scope:**
  ~10 dev-days for a `ReserveBasis` enum + two concrete alternatives
  (CRVM, VM-20 PBR simplified). **Affected:** `core/projection.py`,
  all four products, new test suite vs published cedant filings.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **IFRS 17 period-to-period movement table.** Current implementation
  gives BEL / RA / CSM at initial recognition only. Production filers
  need opening → experience adjustments → unwinding → closing movement
  tables by annual cohort with locked-in discount rates. Roadmap Phase
  5.3. **Scope:** ~10 dev-days. **Affected:** `analytics/ifrs17.py`.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

### NICE-TO-HAVE

- **Premium sufficiency testing.** Does the cedant's premium cover
  expected claims + expenses + target margin? Useful for "is this deal
  pre-priced well" commentary. **Scope:** ~2 dev-days.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **Sliding-scale expense allowances / experience refunds.** Common in
  large YRT deals; currently not modelled. **Scope:** ~3 dev-days in
  new `reinsurance/expense_allowance.py`.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **Funds-withheld coinsurance variant.** Extension of Modco where the
  cedant withholds only part of the ceded reserve. Add an
  `FWCoinsuranceTreaty`. **Scope:** ~2 dev-days.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **Duration-specific select-period customisation on
  `MortalityTable`.** Policy-level override of select-period length to
  model cedant-specific underwriting durability. **Scope:** ~2 dev-days.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **Experience monitoring automation loop.** Roadmap Phase 6.1. Close
  the study → export → retrain loop. **Scope:** ~6 dev-days.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

- **Scale benchmarks at 100K policies.** Docstrings claim N=500K is
  supported by the (N, T) broadcast design; no published benchmark
  exists. **Scope:** ~1 dev-day to produce a published timing table.
  *Source: PRODUCT_DIRECTION_2026-04-19.*

## Promoted Follow-ups (from COMPLETE CONTINUATIONs)

These items were documented as out-of-scope in their originating ADRs
or CONTINUATIONs but never previously promoted to a work queue. The
daily-dev routine reads only PRODUCT_DIRECTION, so without this
promotion they remain invisible (see
`docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-05-23.md` for the routine
fix that prevents this in future).

### BLOCKERs

(none — every harvested follow-up is correctly scoped as IMPORTANT or
NICE-TO-HAVE; none of them block first-deal submission)

### IMPORTANT

- **Portfolio-level scenario analysis (`Portfolio.run_scenarios`).**
  `ScenarioRunner` stresses a single deal at a time; reinsurers need
  to stress the whole book under correlated mortality / lapse /
  interest shocks. Open design question: correlated vs. independent
  stresses across cedants. **Scope:** ~3 dev-days. **Affected:**
  `analytics/portfolio.py`, `analytics/scenario.py`, tests.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #3.*

- **Per-duration solver in `YRTRateSchedule.generate_table()`.** The
  generator broadcasts a per-(age, sex, smoker) flat rate across every
  duration column. A real per-duration solver lights up `solved_mask`
  as a genuinely 2-D map and is what the schedule's storage contract
  was designed for. CLI / Excel / JSON / dashboard renderers already
  consume the 2-D solved_mask, so this lands without surface changes.
  **Scope:** ~3 dev-days. **Affected:** `analytics/rate_schedule.py`,
  tests.
  *Source: CONTINUATION_yrt_rate_table — "Out of scope per ADR-055"
  follow-up #1 + ADR-053.*

- **LICAT lapse-risk and morbidity-risk capital components.** LICAT
  2024 has separate factors for these; Slice 1 omitted them as a
  factor-model extension that doesn't change the `ProfitTester`
  integration surface. **Scope:** ~3 dev-days. **Affected:**
  `analytics/capital.py`, ADR for the factor sources, tests.
  *Source: CONTINUATION_licat_capital — Open Question #4 (deferred
  to a Phase 5.1.b ADR).*

### NICE-TO-HAVE

- **Streamlit dashboard page for portfolio runs.** Dashboard prices
  one deal at a time; a portfolio page would expose the same workflow
  with file upload + a per-deal table view + concentration heatmaps.
  **Scope:** ~3 dev-days. **Affected:** new
  `src/polaris_re/dashboard/views/portfolio.py`, navigation, tests.
  *Source: ADR-058 "Out of scope" + CONTINUATION_portfolio_aggregation.*

- **Deal-specific hurdle rates on `Portfolio`.** Open design question:
  PV profits at different discount rates do not sum, so
  `total_pv_profits` / `total_irr` need to distinguish "sum of per-deal
  PV at per-deal hurdles" from "PV of the aggregate at a common
  benchmark rate". This is a redesign of the aggregate `ProfitTester`
  pattern, not a parameter add. **Scope:** ~2 dev-days for design ADR
  + ~3 dev-days implementation.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #4.*

- **Weighted concentration variants on `PortfolioResult`.** The
  `_concentration` helper already takes generic `(label, weight)`
  pairs — NAR-weighted, PV-premium-weighted, and capital-weighted
  concentrations are structurally trivial. Surface as
  `concentration[dimension][weight_basis]`. **Scope:** ~1 dev-day.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #5.*

- **Parallel portfolio execution + `remove_deal` + per-deal result
  caching.** `_run_deal` is stateless and trivially parallelisable;
  the current loop is sequential and every `run()` is a full
  re-projection. Fine for small books; a 50+ deal portfolio needs
  caching. **Scope:** ~2 dev-days. **Affected:**
  `analytics/portfolio.py`.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #6.*

- **LICAT C-1 and C-3 capital components (interim).** Slice 1 stubs
  these at zero pending Phase 5.4's asset / ALM model and stochastic-
  rate integration. For deal-committee credibility before Phase 5.4
  lands, an interim C-3 factor (e.g. 1% of reserves) makes the capital
  number less visibly incomplete. **Scope:** ~1 dev-day for an interim
  flat-factor; full Phase 5.4 work tracked separately.
  *Source: CONTINUATION_licat_capital — Open Question #3.*

- **Annuity-product LICAT factor.** The C-2 factor model treats
  insurance risk as `factor × NAR`; annuities have no NAR. A correct
  factor needs a different exposure measure (reserve balance or
  similar) and re-calibrated factors. **Scope:** depends on shock-based
  Phase 5.4 engine; flag here so the gap is visible.
  *Source: CONTINUATION_licat_capital — Slice 1 design note.*

- **Gross / ceded cash flow sheets in deal-pricing Excel.** Slice 1
  deliberately omitted these — DTO fields exist but no sheets are
  written. If the deal committee needs a three-sheet Gross / Ceded /
  Net cash-flow section, add the writer; otherwise drop the unused DTO
  fields. **Scope:** ~1 dev-day.
  *Source: CONTINUATION_deal_pricing_excel — Open Question #2.*

- **Rated-block panel on the Excel Assumptions sheet.** `rated_block`
  is in the CLI JSON output; the workbook's Assumptions sheet does not
  yet include a block-rating panel (n_rated, % rated, face-weighted
  avg multiplier). **Scope:** ~0.5 dev-days.
  *Source: CONTINUATION_deal_pricing_excel — Open Question #3.*

- **`polaris price --with-sensitivity` inline scenarios.** The
  Sensitivity sheet of the deal-pricing workbook is empty on a bare
  `polaris price --excel-out` run because the CLI doesn't couple
  `price` to `scenario`. Add a `--with-sensitivity` flag that runs the
  standard scenarios inline. **Scope:** ~1 dev-day.
  *Source: CONTINUATION_deal_pricing_excel — Open Question #4
  (default option (a) — keep separate — was chosen for Slice 2).*

- **Treaty-level rated-YRT override (`yrt_rate × multiplier`).** Slice
  2 default: substandard mortality multipliers do NOT scale YRT rates
  (cedant bears the extra risk). If any cedant uses `yrt_rate ×
  multiplier`, add a treaty-level opt-in flag. **Scope:** ~1 dev-day.
  *Source: CONTINUATION_substandard_rating — Open Question #3.*

- **CI / DI substandard rating.** Mortality decrements on active lives
  in CI / DI products are not currently scaled by
  `mortality_multiplier`. ADR-043 documents the "skip until ingestion
  confirms" stance. **Scope:** ~1 dev-day once any cedant ingestion
  surface confirms a need.
  *Source: CONTINUATION_substandard_rating — Open Question #4.*

- **Flat-extra as a separate cash-flow line.** Slice 1 default: folded
  into aggregate `death_claims`. If the reinsurance committee wants it
  reported separately, split the output contract. **Scope:** ~1
  dev-day; touches `CashFlowResult` so plan a contract review.
  *Source: CONTINUATION_substandard_rating — Open Question #1.*

- **Ingestion strict-mode for unknown rating codes.** Cedant code →
  multiplier mapping silently defaults on unknown codes; a strict
  mode would refuse unknown codes. **Scope:** ~0.5 dev-day.
  *Source: CONTINUATION_substandard_rating — Slice 3 follow-up.*

- **`yrt_rate_table_path` field on `DealConfig` for CLI YAML configs.**
  Today the tabular YRT rate table is loaded via CLI flag /
  API field, not the YAML config schema, because there's no
  JSON-friendly representation. Adding a path field to `DealConfig`
  would let YAML configs reference a table directory. **Scope:** ~1
  dev-day. **Affected:** `core/pipeline.py:DealConfig`, CLI, tests.
  *Source: CONTINUATION_yrt_rate_table — "follow-up #2".*

- **Streamlit dashboard page for calendar-aligned portfolios.** The
  dashboard prices one deal at a time today. A portfolio page would
  consume the same `PortfolioResult.to_dict()` shape and surface
  `grid_origin` / per-deal `grid_offset` alongside the per-deal table.
  Distinct from the broader "Streamlit dashboard page for portfolio
  runs" entry above in that the calendar-aware view is the production
  workflow (mixed-inception books). **Scope:** ~3 dev-days. **Affected:**
  new `src/polaris_re/dashboard/views/portfolio.py`, navigation, tests.
  *Source: CONTINUATION_calendar_aligned_portfolio — Refinement Backlog #1
  + ADR-062 Out of scope.*

- **Sub-month / non-common day-of-month inception dates in calendar mode.**
  `align="calendar"` today requires every deal's valuation date to fall on
  the same day-of-month so the monthly grids line up. Supporting arbitrary
  inception days would require a finer (daily) grid or fractional-month
  discounting. **Scope:** design ADR + ~2 dev-days implementation.
  **Affected:** `analytics/portfolio.py:_grid_offsets`,
  `core/cashflow.py` if a sub-month time index is needed.
  *Source: CONTINUATION_calendar_aligned_portfolio — Refinement Backlog #2
  / ADR-061 Out of scope (carried forward in ADR-062).*

## Recommended Next Sprint

**Progress update (2026-05-31).** All three items in the prior sprint have
shipped:

- ~~Aggregate `CashFlowResult` claims / expenses / reserves on
  `Portfolio`~~ — **shipped 2026-05-27 (ADR-059, commit 8a3d5a5)**. Entry
  removed from the Promoted Follow-ups queue above.
- ~~Aggregate return-on-capital on `Portfolio`~~ — **shipped 2026-05-28
  (ADR-060, commit b133978)**. Entry removed from the Promoted Follow-ups
  queue above.
- ~~Calendar-aligned portfolio aggregation~~ — **shipped** (Slice 1
  2026-05-29 ADR-061; Slice 2 CLI + API 2026-05-31 ADR-062). The
  CONTINUATION is now COMPLETE; surviving refinement items have been
  promoted below.

Given that all BLOCKERs from 2026-04-19 have shipped and the
commercial-readiness gap is now production polish rather than
first-deal fundamentals, the remaining recommended priority is:

1. **Per-duration solver in `YRTRateSchedule.generate_table()`.** (3
   days, IMPORTANT) — the storage contract (`solved_mask`) and
   renderers are already in place; this lights them up.

2. **Portfolio-level scenario analysis (`Portfolio.run_scenarios`).**
   (IMPORTANT) — the remaining IMPORTANT portfolio follow-up after
   calendar alignment closed.

Reserve-basis matching and IFRS 17 movement table are larger (10
dev-days each); they are genuinely Phase 5.3+ work and should be scoped
as a dedicated roadmap entry rather than picked up mid-sprint.

## Comparison with Previous Assessment

PRODUCT_DIRECTION_2026-04-19.md remains the canonical reasonability
assessment for that date. This document is delta-only: it does not
re-run the reasonability checks. The next full reasonability review
should consume both this file and the 2026-04-19 file together (or
supersede this one entirely).
