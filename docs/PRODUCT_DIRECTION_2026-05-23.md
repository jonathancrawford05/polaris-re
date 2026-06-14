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

(Two harvested items previously listed here — Portfolio-level scenario
analysis and LICAT lapse-risk / morbidity-risk capital components —
have shipped since this file was first published. Both were promoted-
follow-up items from `CONTINUATION_portfolio_aggregation` and
`CONTINUATION_licat_capital`. **Closed by inspection:**
"Portfolio-level scenario analysis" via ADR-064 (PR #51, commit
8359a2b); "LICAT lapse-risk and morbidity-risk capital components"
via ADR-065 (PR #52, commit c88db82).)

- ~~**Reinsurer-vs-cedant profit-test convention in `scenario` / `uq`.**
  `ScenarioRunner` and `MonteCarloUQ` profit-test the cedant `net` position
  (`treaty.apply` returns `(net, ceded)`; both runners take `net`), whereas
  `polaris price` reports the *reinsurer* view (the ceded cash flow
  re-viewed as NET). For a reinsurer-facing tool the scenario / UQ PV and
  IRR figures therefore describe the cedant's retained book, not the
  reinsurer's — a likely surprise on the primary use case. Surfaced by
  ADR-076 (the tabular-YRT wiring made the two surfaces directly
  comparable and the mismatch visible). Decide whether the runners should
  report the reinsurer (ceded) view, expose both, or document the cedant
  convention explicitly. This is a behaviour question that may move
  published scenario / UQ numbers, so it needs its own ADR (and a golden /
  QA reference update if the convention changes). **Scope:** design ADR +
  ~1 dev-day. **Affected:** `analytics/scenario.py`, `analytics/uq.py`,
  `cli.py` (`scenario_cmd`, `uq_cmd`), tests/QA references.
  *Source: ADR-076 Out of scope.*~~ — **SHIPPED** (ADR-077): chose "expose
  both" — an additive `perspective` parameter on both runners (default
  `cedant`, byte-identical library behaviour, no existing test changed) plus
  a `--perspective` flag on the `scenario` / `uq` CLI **defaulting to
  `reinsurer`** so the product surface agrees with `price`. Closed-form
  reinsurer / cedant BASE identities to `rtol=1e-12`. **Premise confirmed:**
  reproduced an 80% coinsurance deal where the runner reported the cedant's
  5,716.78 vs the reinsurer's 22,867.13 (~4x). No golden moved (the suite
  pins only `price`). API + dashboard surfacing filed as follow-ups below.

- **Reinsurer-view perspective on the scenario / UQ API + dashboard surfaces.**
  ADR-077 added the `perspective` parameter to `ScenarioRunner` /
  `MonteCarloUQ` and defaulted the **CLI** `scenario` / `uq` commands to the
  reinsurer view, but the FastAPI endpoints (`POST /api/v1/scenario`,
  `/api/v1/uq`) and the Streamlit dashboard scenario / UQ views still report
  the cedant `net` view — the same primary-use-case correctness gap on the
  other product surfaces. The mechanism already exists: each just needs to
  pass `perspective="reinsurer"` (and, ideally, expose a selector). Deferred
  from ADR-077 to keep that PR to the harvested item's stated analytics + CLI
  scope. This is a behaviour change on those surfaces — check whether any
  API / dashboard QA test pins the current cedant numbers and update with
  rationale. **Scope:** ~1 dev-day. **Affected:** `api/main.py`
  (scenario + uq endpoints), `dashboard/views/scenario.py`,
  `dashboard/views/uq.py`, their tests. *Source: ADR-077 Out of scope #1.*

### NICE-TO-HAVE

- **Reinsurer-vs-cedant perspective on `Portfolio.run_scenarios`.** ADR-077
  resolved the perspective question for the single-deal `ScenarioRunner` /
  `MonteCarloUQ` runners, but `Portfolio.run_scenarios` (ADR-064) aggregates
  per-deal `net` positions and was untouched. Whether portfolio scenario
  output should also offer a reinsurer view is a separate design question
  (the aggregate ceded position would need to flow through
  `Portfolio.aggregate_cash_flow`). Lower priority than the per-deal CLI fix
  because portfolio scenario analysis is a later-stage workflow. **Scope:**
  design sketch + ~1 dev-day. **Affected:** `analytics/portfolio.py`,
  tests. *Source: ADR-077 Out of scope #2.*

- ~~**Streamlit dashboard page for portfolio runs.** Dashboard prices
  one deal at a time; a portfolio page would expose the same workflow
  with file upload + a per-deal table view + concentration heatmaps.
  **Scope:** ~3 dev-days. **Affected:** new
  `src/polaris_re/dashboard/views/portfolio.py`, navigation, tests.
  *Source: ADR-058 "Out of scope" + CONTINUATION_portfolio_aggregation.*~~
  — **SHIPPED** (PR #61 + PR #62 + PR #63 — all three slices merged 2026-06-07/08/09)

- **Deal-specific hurdle rates on `Portfolio`.** Open design question:
  PV profits at different discount rates do not sum, so
  `total_pv_profits` / `total_irr` need to distinguish "sum of per-deal
  PV at per-deal hurdles" from "PV of the aggregate at a common
  benchmark rate". This is a redesign of the aggregate `ProfitTester`
  pattern, not a parameter add. **Scope:** ~2 dev-days for design ADR
  + ~3 dev-days implementation.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #4.*

- ~~**Weighted concentration variants on `PortfolioResult`.**~~ —
  **in flight on PR #56 (ADR-069 — awaiting merge)** as
  `concentration_by_basis` and `hhi_by_basis` fields on
  `PortfolioResult` keyed `{basis: {dimension: {label: share}}}` with
  three weight bases (`ceded_face`, `ceded_nar_peak`, `pv_premium`).
  The flat `concentration_by_*` / `hhi` fields are now derived from
  the `ceded_face` basis by construction, so the two surfaces cannot
  drift. Capital-weighted basis deliberately deferred (see new
  promoted follow-up below). *Source: CONTINUATION_portfolio_aggregation
  — Refinement Backlog #5.*

- ~~**Dashboard surfacing of `concentration_by_basis`.** The CLI half of
  this item shipped 2026-06-05 (ADR-070) as a `--concentration-basis
  {ceded_face,ceded_nar_peak,pv_premium,all}` flag on both
  `polaris portfolio run` and `polaris portfolio report`. The Streamlit
  dashboard portfolio view does not yet exist (see "Streamlit dashboard
  page for portfolio runs" / "...for calendar-aligned portfolios" below);
  the basis selector should ride along with whichever lands first.
  **Scope:** rolls into the dashboard portfolio view work; ~0.5 dev-day
  on top of that.
  *Source: ADR-069 Out of scope; CLI half closed by ADR-070.*~~ —
  **SHIPPED** (PR #63, Slice 3): the dashboard portfolio page surfaces
  all three bases via dimension-first `concentration_by_dimension()`
  bar charts plus an HHI matrix and long-format CSV export.

- **Capital-weighted concentration basis on
  `PortfolioResultWithCapital`.** ADR-069 deliberately omitted a
  capital-weighted basis because capital weights only exist on the
  `PortfolioResultWithCapital` subclass — they require a per-deal
  `LICATCapital` call. Adding a fourth basis means either threading
  the capital model into `run()` or restricting the field to the
  subclass. The dict-of-dicts shape already accommodates the
  extension without a contract change. **Scope:** ~1-2 dev-days.
  **Status:** PR #56 merged 2026-06-05 → now AVAILABLE for selection.
  *Source: ADR-069 Out of scope.*

- ~~**Dimension-outer transposed view on `concentration_by_basis`.**~~ —
  **shipped 2026-06-07 (ADR-073, PR #60)** as
  `PortfolioResult.concentration_by_dimension()` and
  `hhi_by_dimension()` helpers backed by a generic
  `_transpose_basis_outer` swap. The basis-outer storage stays the
  single source of truth; the helpers return the dimension-outer view
  by reference (no storage duplication). `to_dict()` is intentionally
  unchanged so the JSON surface is byte-identical. Primary downstream
  consumer is the deferred Streamlit dashboard portfolio page (see
  `docs/PLAN_dashboard_portfolio.md`). *Source: ADR-069 Open Question /
  DEV_SESSION_LOG_2026-06-05 follow-up.*

- **Parallel portfolio execution + `remove_deal` + per-deal result
  caching.** `_run_deal` is stateless and trivially parallelisable;
  the current loop is sequential and every `run()` is a full
  re-projection. Fine for small books; a 50+ deal portfolio needs
  caching. **Scope:** ~2 dev-days. **Affected:**
  `analytics/portfolio.py`.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #6.*

- ~~**LICAT C-1 and C-3 capital components (interim).**~~ — **shipped
  2026-06-07 (ADR-072)** as a `LICATCapital.for_product_interim(product_type)`
  opt-in classmethod that populates all five LICAT factors with
  conservative committee-stage placeholders (uniform C-1 = 0.5% of
  reserves; C-3 scales with effective reserve duration, ANNUITY 2.0%
  → TERM 0.5%). The existing `for_product` / `for_product_extended`
  constructors keep C-1 / C-3 at zero so CLI / API / dashboard / Excel
  capital tiles are byte-identical; opting the standard surfaces over
  to `for_product_interim` is a follow-up that requires golden
  baseline regeneration. **Phase 5.4 will replace these placeholders
  with shock-based asset / ALM modelling.**
  *Source: CONTINUATION_licat_capital — Open Question #3.*

- **Switch standard capital surfaces from `for_product` to
  `for_product_interim`.** ADR-072 left the CLI `--capital licat`,
  FastAPI `capital_model="licat"`, dashboard checkbox, and Excel
  `_CAPITAL_METRICS` rows wired to `for_product(...)` so the capital
  tile stayed byte-identical. Switching to `for_product_interim(...)`
  surfaces the interim C-1 / C-3 placeholders to every consumer
  without requiring an explicit opt-in. **This is a behaviour change:**
  every capital tile and every golden capital number moves. Needs its
  own ADR (calibration justification + dashboard / Excel labelling so
  the placeholder status remains visible), explicit golden baseline
  regeneration with rationale, and a coordinated update to QA
  reference numbers. **Scope:** ~1-2 dev-days including baseline
  regeneration. **Affected:** `src/polaris_re/cli.py`,
  `src/polaris_re/api/main.py`, `src/polaris_re/dashboard/`,
  `src/polaris_re/utils/excel_output.py`, `tests/qa/`.
  *Source: ADR-072 Out of scope.*

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

- ~~**Rated-block panel on the Excel Assumptions sheet.**~~ —
  **shipped 2026-06-05 (ADR-068)** as an optional `RatedBlockExport`
  bundle on `DealPricingExport`. When populated and `n_rated > 0`,
  `_write_assumptions_sheet` appends a "Rated Block" section with the
  six labelled rows from `rating_composition` (policies rated,
  % rated by count / by face, face-weighted avg multiplier, max
  multiplier, max flat-extra). All-standard blocks remain byte-
  identical to pre-ADR-068 output. *Source: CONTINUATION_deal_pricing_excel
  — Open Question #3.*

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

- ~~**Ingestion strict-mode for unknown rating codes.**~~ — **shipped
  2026-06-06 (ADR-071, PR #58, commit b470ff4)** as a `strict: bool =
  False` field on `RatingCodeMap`; when `True`, `_apply_rating_code_map`
  raises `PolarisValidationError` listing every distinct unknown code
  with up to five example `policy_id`s. The default-`False` preserves
  byte-identical behaviour for every existing ingestion path.
  *Source: CONTINUATION_substandard_rating — Slice 3 follow-up.*

- ~~**`yrt_rate_table_path` field on `DealConfig` for CLI YAML configs.**
  Today the tabular YRT rate table is loaded via CLI flag /
  API field, not the YAML config schema, because there's no
  JSON-friendly representation. Adding a path field to `DealConfig`
  would let YAML configs reference a table directory. **Scope:** ~1
  dev-day. **Affected:** `core/pipeline.py:DealConfig`, CLI, tests.
  *Source: CONTINUATION_yrt_rate_table — "follow-up #2".*~~ —
  **SHIPPED** (PR #67, ADR-075): four optional `yrt_rate_table_*` fields on
  `DealConfig` parsed from the nested `deal` block; a shared
  `_load_yrt_rate_table_from_dir` helper serves both the `--yrt-rate-table`
  flag (precedence) and the config field. Path used as-is
  (`MortalityConfig.data_dir` precedent). Closed-form test asserts
  config-driven pricing is byte-identical to the flag.

- ~~**`deal.yrt_rate_table_path` on `scenario` / `uq` CLI commands.** ADR-075
  wired the config-driven tabular YRT table into `polaris price` only —
  the only command that consumes a tabular table today. `scenario` and
  `uq` parse the same `deal` config block but have no table-loading wiring,
  so a config with `yrt_rate_table_path` is silently ignored there. Add
  the same `_load_yrt_rate_table_from_dir` resolution to those commands if
  scenario / UQ analysis on a tabular YRT basis is wanted. **Scope:** ~1
  dev-day. **Affected:** `cli.py` (`scenario_cmd`, `uq_cmd`), tests.
  *Source: ADR-075 Out of scope.*~~ — **SHIPPED** (ADR-076): both commands
  resolve `deal.yrt_rate_table_path` through a shared
  `_resolve_config_yrt_rate_table` helper, and `ScenarioRunner` /
  `MonteCarloUQ` now project seriatim + pass the `InforceBlock` to
  `YRTTreaty.apply` when the treaty is tabular (flat/proportional path
  byte-identical). **Scope correction:** the original "Affected" line was
  wrong — the fix also required `analytics/scenario.py` + `analytics/uq.py`,
  not `cli.py` alone (the tabular path needs seriatim projection). Closed-form
  BASE / base-case identity verified to `rtol=1e-12`.

- **Relative-to-config path resolution for `yrt_rate_table_path`.** ADR-075
  uses the configured path as-is (cwd-relative), matching the
  `MortalityConfig.data_dir` precedent. A portable config bundle (config +
  table dir shipped together) would benefit from resolving relative paths
  against the config file's parent directory. This is a cross-cutting
  decision (it would ideally also cover `mortality.data_dir`), so it needs
  its own small ADR. **Scope:** ~0.5–1 dev-day. **Affected:** `cli.py`
  config parsing, tests. *Source: ADR-075 Out of scope.*

- **Dashboard upload-flow key for a tabular YRT table.** The Streamlit
  dashboard manages its own table-upload state and does not read
  `deal.yrt_rate_table_path` (deliberately omitted from
  `DealConfig.to_dict()`, which backs the dashboard `DEFAULTS`). If config
  import/export on the dashboard should round-trip a referenced table
  directory, add the corresponding upload-flow wiring. **Scope:** ~1
  dev-day. **Affected:** `dashboard/` config import/export, tests.
  *Source: ADR-075 Out of scope.*

- **`--yrt-rate-table` CLI flag on `scenario` / `uq`.** ADR-076 wired the
  config field (`deal.yrt_rate_table_path`) into both commands but, unlike
  `price`, neither exposes the ad-hoc `--yrt-rate-table DIR` flag. Adding it
  (with the same flag-over-config precedence `price` uses) would give the
  three commands a uniform table-loading surface. Config-only was the
  minimal scope that closed the silent-drop gap; the flag is purely
  additive. **Scope:** ~0.5 dev-day. **Affected:** `cli.py`
  (`scenario_cmd`, `uq_cmd` options), tests.
  *Source: ADR-076 Out of scope.*

- ~~**Streamlit dashboard page for calendar-aligned portfolios.** The
  dashboard prices one deal at a time today. A portfolio page would
  consume the same `PortfolioResult.to_dict()` shape and surface
  `grid_origin` / per-deal `grid_offset` alongside the per-deal table.
  Distinct from the broader "Streamlit dashboard page for portfolio
  runs" entry above in that the calendar-aware view is the production
  workflow (mixed-inception books). **Scope:** ~3 dev-days. **Affected:**
  new `src/polaris_re/dashboard/views/portfolio.py`, navigation, tests.
  *Source: CONTINUATION_calendar_aligned_portfolio — Refinement Backlog #1
  + ADR-062 Out of scope.*~~
  — **SHIPPED** (PR #61 + PR #62 + PR #63 — all three slices merged; `align`
  selectbox live; UX polish promoted as its own NICE-TO-HAVE follow-up below)

- **Sub-month / non-common day-of-month inception dates in calendar mode.**
  `align="calendar"` today requires every deal's valuation date to fall on
  the same day-of-month so the monthly grids line up. Supporting arbitrary
  inception days would require a finer (daily) grid or fractional-month
  discounting. **Scope:** design ADR + ~2 dev-days implementation.
  **Affected:** `analytics/portfolio.py:_grid_offsets`,
  `core/cashflow.py` if a sub-month time index is needed.
  *Source: CONTINUATION_calendar_aligned_portfolio — Refinement Backlog #2
  / ADR-061 Out of scope (carried forward in ADR-062).*

- **Per-deal scenario overrides (heterogeneous stresses across cedants).**
  `Portfolio.run_scenarios` (ADR-064) applies the same `ScenarioAdjustment`
  uniformly to every deal — the conservative correlated-stress baseline.
  Some deal committees want differentiated stresses (Cedant A at +20%
  mortality, Cedant B at +5%) to model book-specific risk concentrations.
  Open design question: a `ScenarioAdjustmentMap` keyed by `deal_id`,
  versus a `Portfolio.run_scenarios(per_deal=...)` parameter, versus a
  per-deal scenario set on `add_deal`. Touches the result shape since the
  scenario "name" no longer applies uniformly. **Scope:** design ADR +
  ~3 dev-days implementation. **Affected:** `analytics/portfolio.py`,
  `analytics/scenario.py`, tests.
  *Source: CONTINUATION_portfolio_aggregation — Refinement Backlog #3 /
  ADR-064 Out of scope.*

- ~~**`polaris portfolio --scenarios` CLI + `POST /api/v1/portfolio/scenarios`
  API surfacing.**~~ — **shipped 2026-06-03 (ADR-066)** as a
  `polaris portfolio scenarios` subcommand + `POST
  /api/v1/portfolio/scenarios` endpoint; both consume the standard six-
  scenario set by default and accept comma-separated / list filters
  drawn from it. Both surfaces return the flat
  `PortfolioScenarioResult.to_dict()` shape. The Streamlit dashboard
  scenario page below remains open. *Source: ADR-064 Out of scope.*

- **Streamlit dashboard page for portfolio scenario results.** A
  scenario view consuming `PortfolioScenarioResult.to_dict()`: per-scenario
  PV / IRR / capital table, a waterfall chart from BASE to worst case,
  and the worst-case per-deal breakdown. Distinct from the "Streamlit
  dashboard page for portfolio runs" entry above in that this view is
  scenario-pivoted, not deal-pivoted. **Scope:** ~3 dev-days. **Affected:**
  new `src/polaris_re/dashboard/views/portfolio_scenarios.py`, navigation,
  tests.
  *Source: ADR-064 Out of scope.*

- **Parallel `run_scenarios` execution.** Sequential by default — wall-
  clock cost is `len(scenarios) × cost(Portfolio.run)`. Overlaps with
  the existing "Parallel portfolio execution" backlog item but is
  particularly impactful for the default six-scenario set (6x today).
  **Scope:** rolls into the existing parallel-execution work; not a
  separate dev-day estimate.
  *Source: ADR-064 Out of scope + CONTINUATION_portfolio_aggregation
  Refinement Backlog #6.*

- ~~**CLI surfacing of `--solve-mode` on `polaris rate-schedule --table`.**~~ —
  **shipped 2026-06-04 (ADR-067)** as a Typer `Literal["flat",
  "per_duration"]` option on `polaris rate-schedule`. Default `"flat"`
  preserves prior behaviour; `--solve-mode per_duration` requires
  `--table` and exits 1 with a clear error otherwise. The generated
  `table_name` suffix (already encoded by ADR-063) discloses the mode in
  the JSON / Excel output. *Source: ADR-063 Out of scope.*

- **Per-duration cell-failure interpolation.** `generate_table(solve_mode=
  "per_duration")` falls back to column-wise forward/back-fill when an
  individual `(age, duration)` cell fails to solve. A richer interpolator
  (e.g. linear across the duration axis for an interior column failure)
  would be a quality improvement but is not needed for the dense-grid
  case the test suite covers. `solved_mask` already discloses which
  cells came from a fill rather than a direct solve. **Scope:** ~1
  dev-day. **Affected:** `analytics/rate_schedule.py`, tests.
  *Source: ADR-063 Out of scope.*

- **Warm-start `brentq` across adjacent per-duration cells.** Per-
  duration mode runs the solver `select_period_years + 1` times per
  `(age, sex, smoker)`. Warm-starting from the adjacent column's
  solution would cut wall-clock cost meaningfully on long select
  periods (typical 15-25 year selects); pure performance, no contract
  change. **Scope:** ~1 dev-day. **Affected:**
  `analytics/rate_schedule.py`.
  *Source: ADR-063 Out of scope.*

- ~~**Dashboard error handling — widen exception catches to
  `PolarisComputationError`.** Every dashboard page's Run button
  (`views/pricing.py`, `views/scenario.py`, `views/portfolio.py`, etc.)
  catches `PolarisValidationError` only. If the engine raises
  `PolarisComputationError` (numerical failure, e.g. singular matrix
  during IRR root-finding) the user sees a raw Streamlit traceback
  instead of a friendly error tile. The right scope is a cross-cutting
  pass over every dashboard page rather than a one-off widen on the
  Portfolio page. **Scope:** ~0.5 dev-day. **Affected:** every
  `dashboard/views/*.py` Run button, no analytics changes.
  *Source: CONTINUATION_dashboard_portfolio — Refinement Backlog (Slice 2/3).*~~
  — **SHIPPED** (PR #65): every Run button now catches
  `(PolarisValidationError, PolarisComputationError)` and renders a
  friendly `st.error` tile; regression-tested per page in
  `tests/qa/test_dashboard_flows.py::TestDashboardComputationErrorHandling`.

- ~~**Calendar-aligned portfolio UX polish — non-zero grid offsets in
  the sample.** The dashboard portfolio page's `align="calendar"`
  banner ("Grid origin: ... per-deal offsets shown in the table below")
  is suppressed on the in-tree sample because DEAL_C / DEAL_D
  `valuation_date = 2026-01-15` sits in the same calendar month as
  DEAL_A / DEAL_B's 2026-01-01, so `months_between` returns 0 for
  every deal. Moving DEAL_C / DEAL_D to 2026-02-15 (or adding a
  second sample portfolio) would let the calendar-alignment UI path
  light up end-to-end and exercise the per-deal `grid_offset` column.
  **Scope:** ~0.5 dev-day. **Affected:**
  `data/inputs/portfolio_sample/portfolio.yaml`, the four per-deal
  CSV `valuation_date` columns, the loader's test fixtures if any
  assertion pins the current dates.
  *Source: CONTINUATION_dashboard_portfolio — Refinement Backlog (Slice 2/3).*~~
  — **SHIPPED** (PR #66): second sample
  `data/inputs/portfolio_staggered_sample/` with explicit per-deal YAML
  dates two months apart (grid offsets 0/0/2/2) exercises the
  calendar-mode UI path end to end; the investigation also exposed and
  fixed the wall-clock valuation-date fallback (ADR-074 — note the
  entry's premise was partly wrong: grid placement is YAML/block-driven,
  not CSV-column-driven).

- **ANB vs ALB attained-age convention.**
  `InforceBlock.attained_age_vec_at` derives age as
  `issue_age + months_between // 12` (age-last-birthday-flavoured),
  while the `Policy` docstring describes attained age as
  age-nearest-birthday. The ADR-074 consistency guard's ±1 year
  tolerance absorbs the discrepancy at load time, but the engine
  should commit to one convention, document it, and align the
  docstring, the derivation, and any mortality-table expectations
  (industry tables are published on a stated ANB/ALB basis).
  **Scope:** ~0.5–1 dev-day (decision ADR + docstring/derivation
  alignment; check table loaders for basis assumptions).
  **Affected:** `core/inforce.py`, `core/policy.py` docstring,
  possibly `assumptions/mortality.py` documentation.
  *Source: ADR-074 Out of scope.*

- **As-of re-valuation workflow.** Projecting a block at a date other
  than its own valuation date remains supported via explicit config
  (`deal.valuation_date` / `--valuation-date`-style overrides), but
  there is no dedicated UX: re-derived ages/durations are not surfaced
  to the user, and the ADR-074 guard validates only internal
  consistency at the block's own date. A first-class "re-value as of"
  flow would show the re-derived seasoning next to the stored values
  and warn when the override moves policies across select-period or
  term boundaries. If large-cedant load profiling ever flags the
  per-policy consistency guard, vectorise it in the same pass
  (PR #66 review P2 — currently negligible next to per-row Policy
  construction). **Scope:** design sketch + ~1–2 dev-days.
  **Affected:** dashboard Assumptions/Pricing pages, CLI flag
  surface, `core/inforce.py`.
  *Source: ADR-074 Out of scope.*

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
first-deal fundamentals, the recommended priority list has been
worked down to:

1. ~~**Per-duration solver in `YRTRateSchedule.generate_table()`.**~~ —
   **shipped 2026-06-01 (ADR-063, commit efd2b58)**. Entry removed from
   the Promoted Follow-ups queue above; three derived NICE-TO-HAVE
   follow-ups (CLI surfacing of `--solve-mode`, per-duration cell-failure
   interpolation, warm-start `brentq` across adjacent cells) have been
   promoted below.

2. ~~**Portfolio-level scenario analysis (`Portfolio.run_scenarios`).**~~ —
   **shipped 2026-06-01 (ADR-064, PR #51)**. The correlated-stress
   baseline is in place; four derived follow-ups (per-deal scenario
   overrides for heterogeneous stresses across cedants, `polaris
   portfolio --scenarios` CLI + API surfacing, dashboard scenario page,
   parallel `run_scenarios` execution) have been promoted below.

3. ~~**LICAT lapse-risk and morbidity-risk capital components.**~~ —
   **shipped 2026-06-02 (ADR-065, PR #52)**. Entry removed from the
   Promoted Follow-ups queue above.

4. ~~**`polaris portfolio --scenarios` CLI + `POST
   /api/v1/portfolio/scenarios` API surfacing.**~~ — **shipped 2026-06-03
   (ADR-066)** as a `polaris portfolio scenarios` subcommand plus a
   sibling FastAPI endpoint. Both consume the standard six-scenario set
   by default and return the flat `PortfolioScenarioResult.to_dict()`
   shape. The corresponding entry under Promoted Follow-ups above has
   been crossed out.

**Update (2026-06-05).** The "Weighted concentration variants on
`PortfolioResult`" follow-up is in flight on PR #56 (ADR-069) and is
NOT available for re-selection until merged. Three derived follow-ups
have been promoted above (CLI / dashboard surfacing of the new bases,
capital-weighted basis, dimension-outer transposed view); all three
**depend on PR #56 merge** and should be skipped by the next session
until that lands on `main`.

**Update (2026-06-07).** PR #56 (ADR-069) merged 2026-06-05; both
ADR-069-derived follow-ups (capital-weighted concentration basis,
dimension-outer transposed view) are now AVAILABLE for selection —
their entries have been re-marked from "Depends on" to "Status:
... AVAILABLE for selection" above. ADR-070 has since closed the CLI
half of "Dashboard surfacing of `concentration_by_basis`" so only the
dashboard-view half remains open there. Two NICE-TO-HAVE items shipped
since 2026-06-05: ADR-071 (Ingestion strict-mode, PR #58, commit
b470ff4) and ADR-072 (LICAT C-1 / C-3 interim factor, PR #59) — both
crossed out above. A new derived follow-up has been added to the
queue: "Switch standard capital surfaces from `for_product` to
`for_product_interim`" (source: ADR-072 Out of scope) — flagged as a
behaviour change requiring golden baseline regeneration.

**What the next session should consider.** With the four prior-sprint
IMPORTANT items shipped and the concentration variants follow-up in
flight, the active queue is:

- No IMPORTANT item remains that fits a single session. The two
  surviving IMPORTANT items — **Reserve-basis matching** and **IFRS 17
  period-to-period movement table** — are 10 dev-days each. They are
  genuinely Phase 5.3+ work and should be scoped as a dedicated roadmap
  entry rather than picked up mid-sprint.
- The NICE-TO-HAVE queue is well-stocked with sub-day to 3-day items
  spanning portfolio dashboard, scenario dashboard page, YRT table
  refinements, LICAT extensions, Excel polish, and so on; any of these
  is a valid fallback for a session that needs an isolated, low-risk
  pick.

**Update (2026-06-07, end of day).** Candidate pick #1 (Dimension-outer
transposed view on `concentration_by_basis`) shipped today as ADR-073
/ PR #60 — entry crossed out under Promoted Follow-ups above.

A multi-session plan for the Streamlit dashboard portfolio page
(previously deferred as the largest commercial-visibility lever in
the NICE-TO-HAVE queue, and the primary consumer of ADR-073) was
authored: `docs/PLAN_dashboard_portfolio.md`. The plan decomposes the
work into 3 slices (sample data + loader → page + per-deal table →
concentration / scenarios / capital sub-sections) and folds together
the three formerly-separate dashboard items ("portfolio runs",
"calendar-aligned portfolio", "Dashboard surfacing of
`concentration_by_basis`"). The next session should follow that plan
rather than re-decompose the work; subsequent daily-dev runs should
continue against `CONTINUATION_dashboard_portfolio.md` once Slice 1
lands.

**Candidate pick list for the 2026-06-08 session.** Cross-checked
against `git log main` and `gh pr list --state open` on 2026-06-07.
Items are grouped by approximate session fit:

*Multi-session MEDIUM pick (recommended next focus):*
0. **Streamlit dashboard portfolio page** — plan in
   `docs/PLAN_dashboard_portfolio.md`. 3 slices, ~3 dev-days total.
   Primary downstream consumer of ADR-073 / ADR-069 / ADR-064 /
   ADR-072. *Sources: ADR-073 Out of scope (immediate); promoted
   follow-ups "Streamlit dashboard page for portfolio runs", "...for
   calendar-aligned portfolios", "Dashboard surfacing of
   `concentration_by_basis`" (rolled together).*

*Single-session SMALL picks (≤1 dev-day, no contract changes, no
unmerged-PR dependency):*
1. **Per-duration cell-failure interpolation** (~1 dev-day). Pure
   quality improvement to `analytics/rate_schedule.py`; the
   `solved_mask` already surfaces which cells came from a fill. No
   contract change. *Source: ADR-063 Out of scope.*
2. **Warm-start `brentq` across adjacent per-duration cells**
   (~1 dev-day). Pure performance optimisation in
   `analytics/rate_schedule.py`. No contract change. *Source:
   ADR-063 Out of scope.*
3. **`yrt_rate_table_path` field on `DealConfig` for CLI YAML
   configs** (~1 dev-day). Adds a path field to the YAML schema;
   touches `core/pipeline.py`, CLI, tests. *Source:
   CONTINUATION_yrt_rate_table — follow-up #2.*
4. **Gross / ceded cash flow sheets in deal-pricing Excel**
   (~1 dev-day). Writes the three-sheet section from DTO fields
   that already exist. *Source: CONTINUATION_deal_pricing_excel —
   Open Question #2.*
5. **`polaris price --with-sensitivity` inline scenarios**
   (~1 dev-day). Couples `price` to the standard scenarios so the
   Excel Sensitivity sheet populates on a bare `--excel-out` run.
   *Source: CONTINUATION_deal_pricing_excel — Open Question #4.*
6. **Treaty-level rated-YRT override (`yrt_rate × multiplier`)**
   (~1 dev-day). Optional flag on YRT treaty for cedants that scale
   YRT rates by mortality multiplier. *Source:
   CONTINUATION_substandard_rating — Open Question #3.*

*Single-session SMALL picks with a behaviour-change caveat:*
7. **Switch standard capital surfaces to `for_product_interim`**
   (~1-2 dev-days incl. baseline regeneration). Surfaces today's
   ADR-072 interim factors to every consumer; needs its own ADR
   plus coordinated golden baseline regeneration. *Source: ADR-072
   Out of scope.*
8. **Capital-weighted concentration basis on
   `PortfolioResultWithCapital`** (~1-2 dev-days). Adds a fourth
   basis to `concentration_by_basis` for the with-capital subclass.
   PR #56 merged; AVAILABLE. *Source: ADR-069 Out of scope.*

*Deferred (out of scope for a single session):*
- **CI / DI substandard rating** — defer until any cedant ingestion
  surface confirms a need. *Source: CONTINUATION_substandard_rating
  — Open Question #4.*
- **Flat-extra as a separate cash-flow line** — touches
  `CashFlowResult` contract; needs a contract review.

Recommended next focus: item #0 (dashboard portfolio page) — biggest
commercial-visibility lever in the queue, plan already written. If a
session is constrained to a single-shot pick, items #4 / #5 are the
most directly deal-committee-visible (Excel deliverables).

## Comparison with Previous Assessment

PRODUCT_DIRECTION_2026-04-19.md remains the canonical reasonability
assessment for that date. This document is delta-only: it does not
re-run the reasonability checks. The next full reasonability review
should consume both this file and the 2026-04-19 file together (or
supersede this one entirely).
