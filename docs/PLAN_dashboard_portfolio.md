# Plan — Streamlit dashboard portfolio page

> **Audience.** A new Claude Code session that will build this feature end
> to end. Read this document fully before writing code, then read the
> linked CLAUDE.md / ARCHITECTURE.md / DECISIONS.md sections it points
> at. Update the CONTINUATION + DECISIONS + DEV_SESSION_LOG files at the
> end of every slice — this plan is the read-only spec, not the running
> log.
>
> **Status.** READY TO START. No prior code exists for this feature.
> Predecessor work (the multi-basis concentration capability the page
> will consume) shipped 2026-06-05 (ADR-069) and 2026-06-07 (ADR-073).

---

## 1. Goal

Add a **Portfolio** page to the Streamlit dashboard (`src/polaris_re/dashboard/`)
that exposes the existing portfolio-aggregation engine — `Portfolio.run`,
`Portfolio.run_scenarios`, `Portfolio.run_with_capital` — through an
interactive UI. The page is the deal-committee-facing surface for
multi-deal portfolio analysis: the analytical work is already shipped
on `analytics/portfolio.py`; this feature is the presentation layer that
makes it usable by a reinsurance pricing actuary without touching the
CLI.

The page should:

1. Let the user upload a portfolio config (the same YAML/JSON shape the
   `polaris portfolio run --config` CLI accepts), plus the inforce CSVs
   the config references.
2. Run the portfolio and cache the result in `st.session_state`.
3. Render an **Overview** section: aggregate tiles (deal count, total
   ceded face, total PV profits, IRR, profit margin, peak NAR) + a
   per-deal breakdown table.
4. Render a **Concentration** section that exercises the multi-basis
   concentration surface (ADR-069) and the dimension-outer transpose
   helper (ADR-073). The natural interaction is **"pick a dimension
   (cedant / product / treaty), see three side-by-side bar charts for
   face / NAR-peak / PV-premium weightings"** — that is exactly the
   access pattern `concentration_by_dimension()` exposes.
5. Render a **Scenarios** sub-section that fires `run_scenarios` for the
   standard six-scenario set and shows a PV / IRR comparison table.
6. Render a **Capital** sub-section that fires `run_with_capital` with
   a `LICATCapital.for_product_interim` factor schedule (ADR-072) and
   shows the aggregate capital tiles + RoC + capital-adjusted IRR.

The page must be **excluded from coverage** (matching the existing
`dashboard/app.py` precedent, ADR-032) but tested via
`streamlit.testing.v1.AppTest` in `tests/qa/test_dashboard_flows.py` so
regressions in widget wiring are caught.

## 2. Why this work, and what it does NOT do

**Why.** PRODUCT_DIRECTION_2026-05-23 lists three deferred Streamlit
dashboard items, two of which (portfolio runs, calendar-aligned
portfolio) collapse into "build the portfolio page" — the
calendar-aware view is just an `align="calendar"` option on the same
runner. ADR-073 explicitly scopes "dashboard surfacing" as deferred to
"the day the dashboard portfolio page lands"; that day is this
feature.

**Why now.** All BLOCKERs and IMPORTANTs from the 2026-04-19 and
2026-05-23 assessments have shipped. The NICE-TO-HAVE queue is the
backlog the routine is now pulling from. The dashboard page is the
single largest commercial-visibility lever left in the NICE-TO-HAVE
queue — the analytical engine is more advanced than the UI surface, so
each unit of UI work shows up immediately as committee-visible
capability.

**Does NOT.**

- This feature is **presentation only**. No new analytical capability,
  no new calculation, no new ADR for analytical decisions. Every number
  comes through an existing `Portfolio.*` call.
- It does **not** add a portfolio "scenario page" as a separate top-
  level navigation entry — the scenario view is a sub-section on the
  same page so the analyst doesn't need to re-upload the config to
  flip between Overview and Scenarios.
- It does **not** extend `Portfolio` itself. If a friction point
  emerges — e.g. a missing helper on `PortfolioResult` — log it as a
  follow-up in the session log and surface in PRODUCT_DIRECTION.
  Do not modify `analytics/portfolio.py` in this feature.

## 3. Prerequisites — read before writing code

1. **`CLAUDE.md`** — coding conventions, session workflow, the
   mandatory `uv run ruff format / check` + `pytest` quality gate, the
   "never use `from __future__ import annotations`" / "never `Optional[X]`"
   rules.
2. **`ARCHITECTURE.md`** §5 (treaty layer) and §7 (analytics layer).
3. **`docs/DECISIONS.md`**:
   - ADR-032 — dashboard excluded from coverage; optional `[dashboard]`
     dependency.
   - ADR-057 / ADR-058 — `Portfolio` construction + per-deal breakdown.
   - ADR-061 / ADR-062 — calendar-aligned aggregation; `grid_origin`
     and `grid_offset`.
   - ADR-064 — `Portfolio.run_scenarios` and `PortfolioScenarioResult`.
   - ADR-066 — CLI surfacing of `portfolio scenarios`; matches the
     interaction model the dashboard scenario sub-section should mirror.
   - ADR-069 — `concentration_by_basis` / `hhi_by_basis` shape.
   - ADR-070 — `--concentration-basis` CLI flag; the basis-picker UX
     should match the CLI flag's three concrete bases plus an "all".
   - ADR-072 — `LICATCapital.for_product_interim` factor schedule for
     non-zero C-1 / C-3 placeholders in the capital sub-section.
   - ADR-073 — `concentration_by_dimension()` /
     `hhi_by_dimension()` helpers (the dimension-outer access pattern
     this page is the primary consumer of).
4. **`src/polaris_re/dashboard/`** — read the existing module layout
   to match conventions:
   - `app.py` — sidebar navigation; the new entry goes in
     `st.sidebar.radio(..., [...])` and the `if page == "Portfolio":`
     dispatch.
   - `views/pricing.py` — the closest analog (single-deal version of
     what this page does for portfolios).
   - `views/scenario.py` — the scenario rendering pattern.
   - `components/state.py` — session-state initialisation; add the
     portfolio result key here.
   - `components/charts.py` — chart helpers (matplotlib); add the
     concentration bar chart helper here.
5. **`src/polaris_re/cli.py`** §portfolio commands —
   `_build_portfolio_from_config` is the canonical YAML/JSON parser.
   The dashboard MUST reuse this to avoid drift; do not re-parse the
   config in the dashboard module.
6. **`data/configs/portfolio_demo.yaml`** — the in-tree single-tier
   sample. The page must work on this file unchanged.

## 4. Slice plan (3 slices, each independently mergeable)

This is a MEDIUM-scope feature per the daily-dev routine. Each slice
produces a green codebase and an independently mergeable PR. Create
`docs/CONTINUATION_dashboard_portfolio.md` after Slice 1 lands.

### Slice 1 — Sample data + reusable loader

**Scope.** Build the sample portfolio that every subsequent slice will
exercise, and the thin loader that wraps `_build_portfolio_from_config`
for dashboard consumption.

**Why first.** Slices 2 and 3 cannot be tested without sample data
that exercises the multi-basis / multi-dimension surface. Front-load
the data so the QA loop on later slices is tight.

**Files to add/modify.**

- `data/inputs/portfolio_sample/portfolio.yaml` — portfolio config
  referencing the four per-deal CSVs (see §5 for the spec).
- `data/inputs/portfolio_sample/deal_a_cedant_north_term_yrt.csv`
- `data/inputs/portfolio_sample/deal_b_cedant_north_wl_coinsurance.csv`
- `data/inputs/portfolio_sample/deal_c_cedant_south_term_coinsurance.csv`
- `data/inputs/portfolio_sample/deal_d_cedant_south_ul_modco.csv`
- `data/inputs/portfolio_sample/README.md` — explains the sample
  composition (3 cedants, 4 deals, 3 product types, 3 treaty types,
  mix of rated and standard policies, mix of new-issue and seasoned
  durations).
- `src/polaris_re/dashboard/components/portfolio_loader.py` —
  `load_portfolio_from_uploaded(...)` wrapper around
  `cli._build_portfolio_from_config`. Accept either an in-memory YAML
  string + a dict of `{csv_filename: bytes}`, or a path to a config on
  disk. Persist the uploaded files to a temp directory so the
  CLI-shared parser sees real paths (the CLI parser reads CSVs by
  path).
- `tests/test_dashboard/test_portfolio_loader.py` — unit tests for
  the loader (round-trips the sample config end-to-end, error on
  missing CSV reference, error on malformed YAML).

**Acceptance.**

- `uv run polaris portfolio run --config data/inputs/portfolio_sample/portfolio.yaml`
  produces a successful run.
- The portfolio surfaces ≥3 cedants, ≥3 product types, ≥3 treaty
  types, a non-zero `peak_ceded_nar` (i.e. at least one YRT deal), and
  a non-empty `rated_block` panel in CLI output.
- New tests pass; existing 1212 tests + 40 QA tests stay green.
- `make format` + `make lint` clean.

**Quality gate.** Before commit, run `make format`, `make lint`,
`uv run pytest tests/ -m "not slow"`, `uv run pytest tests/qa/`, and
the golden regression: `uv run polaris price --inforce
data/qa/golden_inforce.csv --config data/qa/golden_config_flat.json -o
/tmp/dev_check.json`. None of these should change — Slice 1 adds files
under `data/inputs/` (not `data/qa/`) and a new loader module not yet
wired into `app.py`.

### Slice 2 — Portfolio page: Overview + per-deal breakdown

**Scope.** Add the page itself, wire it into navigation, render the
file-upload flow + aggregate tiles + per-deal table. No concentration
charts, no scenarios, no capital — those are Slice 3.

**Files to add/modify.**

- `src/polaris_re/dashboard/views/portfolio.py` — `page_portfolio()`
  entrypoint. Two side-by-side `st.file_uploader` widgets (one for
  the YAML/JSON, one multi-file for the referenced inforce CSVs), a
  "Run portfolio" `st.button`, and the rendered output panels.
- `src/polaris_re/dashboard/app.py` — add `"Portfolio"` to the
  `st.sidebar.radio` options list (immediately after "Deal Pricing"
  reads naturally) and the `elif page == "Portfolio": page_portfolio()`
  dispatch. Add the corresponding import.
- `src/polaris_re/dashboard/components/state.py` — add a
  `portfolio_result` session-state key initialised to `None` in
  `init_session_state`.
- `tests/qa/test_dashboard_flows.py::TestPortfolioPage` — AppTest-based
  smoke tests:
  - Page renders without exception when no upload has happened.
  - Page renders correctly when `st.session_state.portfolio_result` is
    pre-populated with a known result (avoid the file-upload widget,
    which AppTest cannot drive directly — inject via session state per
    the existing pattern documented in the test module's docstring).
  - Per-deal table contains every `deal_id` from the injected result.
  - Aggregate tiles display the correct `total_pv_profits` and
    `n_deals` values.

**Acceptance.**

- New "Portfolio" entry visible in the sidebar; renders an empty-state
  prompt when no upload has happened.
- Upload + Run → aggregate tiles and per-deal table populate from
  `result = portfolio.run(hurdle_rate, align=...)`.
- An `st.selectbox` exposes the align mode (`"strict"` default,
  `"calendar"` option). When set to `"calendar"`, the rendered grid
  origin is the earliest deal's `valuation_date` and per-deal
  `grid_offset` is shown in the table.
- AppTest suite green.

**Quality gate.** Same as Slice 1, plus
`uv run pytest tests/qa/test_dashboard_flows.py -v` must pass cleanly
including the new test class. Coverage report should show
`dashboard/views/portfolio.py` excluded (verify by adding it to the
`omit` list in `pyproject.toml` if needed; check the existing
`dashboard/app.py` omit rule).

### Slice 3 — Concentration + Scenarios + Capital sub-sections

**Scope.** The interactive sections that exercise the multi-basis
concentration helpers (ADR-069 + ADR-073), the scenario runner
(ADR-064), and the capital module (ADR-072).

**Files to add/modify.**

- `src/polaris_re/dashboard/views/portfolio.py` — extend with three
  `st.expander` (or `st.tabs`) sub-sections after the Overview:

  **Concentration sub-section.**
  - `st.selectbox("Group by:", ["Cedant", "Product", "Treaty"])` →
    pick a dimension.
  - Use `result.concentration_by_dimension()[dim_key]` to get
    `{basis: {label: share}}` and render three side-by-side bar charts
    (`st.bar_chart` is fine, or a matplotlib helper in
    `components/charts.py` if a richer style is wanted).
  - Below the charts, render an HHI table — rows: bases, columns:
    dimensions, values: `result.hhi_by_dimension()[dim][basis]`.
  - Add an "Export concentration as CSV" `st.download_button` that
    flattens the dimension-outer view into a long-format DataFrame
    (`dimension, basis, label, share`).

  **Scenarios sub-section.**
  - `st.multiselect` over the standard six-scenario set (default: all).
  - "Run scenarios" button → fires `portfolio.run_scenarios(hurdle,
    scenarios)`; render a PV / IRR / margin table indexed by scenario
    name, with the BASE row pinned at the top and visually distinct.
  - Add a small "worst case" callout fed by
    `PortfolioScenarioResult.worst_case()` (handle the `None` return
    when no scenario has a comparable IRR — show "Worst case: N/A").

  **Capital sub-section.**
  - `st.checkbox("Include LICAT capital metrics")`. When checked,
    `portfolio.run_with_capital(hurdle,
    LICATCapital.for_product_interim(product_type))`. Note: the
    capital model is product-specific; for a mixed-product portfolio,
    explain in the UI that the interim factors are looked up per deal
    by product type — implement this by passing the chosen factor
    schedule down through the existing `run_with_capital` interface
    (read the ADR-060 / ADR-072 wiring before implementing — do NOT
    invent a new combination if a per-deal factor map is required).
  - Render `initial_capital`, `peak_capital`, `pv_capital`,
    `return_on_capital`, `capital_adjusted_irr` as tiles.
  - Render a line chart of `capital_by_period` over time.

- `src/polaris_re/dashboard/components/charts.py` — add helpers as
  needed; keep matplotlib over Plotly to match the existing dashboard
  style.
- `tests/qa/test_dashboard_flows.py::TestPortfolioPageConcentration` —
  AppTest smoke tests:
  - Dimension selector changes render the right set of bars.
  - HHI table contains 3 bases × 3 dimensions.
  - Concentration CSV download contains every (basis, dimension,
    label) row.
- `tests/qa/test_dashboard_flows.py::TestPortfolioPageScenarios` —
  AppTest smoke tests:
  - Scenarios run without exception against the sample portfolio.
  - Worst-case callout renders.
- `tests/qa/test_dashboard_flows.py::TestPortfolioPageCapital` —
  AppTest smoke tests on the capital sub-section.

**Acceptance.**

- Dimension picker drives the bar chart rendering through
  `concentration_by_dimension()` (the page is the primary consumer of
  ADR-073 — explicitly link the ADR in a one-line comment near the
  call site).
- HHI matrix uses `hhi_by_dimension()`.
- Scenarios sub-section reproduces the same shape `polaris portfolio
  scenarios` emits — same metric names, same scenario ordering.
- Capital sub-section reproduces the shape of
  `PortfolioResultWithCapital.to_dict()["capital"]`.
- Coverage stays ≥ 90% (dashboard excluded; the analytics + loader
  layers stay covered).

**Quality gate.** Same as Slices 1 and 2. The full AppTest suite must
pass: `uv run pytest tests/qa/test_dashboard_flows.py -v` should show
the new test classes green alongside the existing ones.

## 5. Sample-data specification (Slice 1)

**Target shape.** 4 deals across 3 cedants, 3 product types, 3 treaty
types, ~25 policies per deal (100 policies total). Mix of new-issue
and seasoned durations. Include 4–8 rated policies across the book so
the rated-block panel (ADR-068) renders non-empty.

**Per-deal composition.**

| Deal ID    | Cedant       | Product | Treaty       | Cession | YRT loading | Policies | Notes |
|------------|--------------|---------|--------------|---------|-------------|----------|-------|
| DEAL_A     | CedantNorth  | TERM    | YRT          | 80%     | 10%         | ~25      | Mix of 20-yr and 30-yr terms, ages 30–55, include 2–3 rated lives |
| DEAL_B     | CedantNorth  | WHOLE_LIFE | Coinsurance | 50%   | n/a         | ~25      | Permanent product, ages 40–65, include 1–2 rated lives |
| DEAL_C     | CedantSouth  | TERM    | Coinsurance  | 60%     | n/a         | ~25      | 10-yr and 20-yr terms, mostly new-issue, all standard |
| DEAL_D     | CedantSouth  | UNIVERSAL_LIFE | Modco | 70%     | n/a         | ~25      | UL needs `account_value` and `credited_rate`; small rated cluster |

**Why this composition exercises the page.**

- **3 cedants** → cedant-dimension concentration has ≥2 labels (North
  contributes A+B, South contributes C+D); HHI is interesting.
- **3 products** → product-dimension concentration has 3 labels.
- **3 treaties** → treaty-dimension has 3 labels.
- **YRT + non-YRT mix** → `ceded_nar_peak` basis differs from
  `ceded_face` (only DEAL_A contributes peak NAR). This is the
  scenario that motivates the multi-basis view — the dashboard's
  concentration charts should visibly differ across the three bases.
- **Mix of new-issue (`duration_inforce=0`) and seasoned policies** →
  exercises the ADR-040 acquisition-cost gate (only new-issue policies
  incur the per-policy acquisition expense).
- **Rated policies** → exercises ADR-068 rated-block panel; ensures
  `rated_block.n_rated > 0` in CLI output.
- **Calendar alignment** → set DEAL_C and DEAL_D `valuation_date` to a
  later date in the same month so `align="calendar"` produces non-zero
  `grid_offset` for those two deals.

**Required CSV columns (in this order):**

```
policy_id, issue_age, attained_age, sex, smoker_status, underwriting_class,
face_amount, annual_premium, product_type, policy_term, duration_inforce,
reinsurance_cession_pct, issue_date, valuation_date, mortality_multiplier,
flat_extra_per_1000
```

For UNIVERSAL_LIFE policies (DEAL_D), also include:

```
account_value, credited_rate
```

(Check `InforceBlock.from_csv` for the optional-column handling; the
two UL columns may need to be appended only for DEAL_D's CSV, or the
loader may already gracefully ignore missing-but-allowed columns.
Verify before writing.)

**Where to put the files.**

```
data/inputs/portfolio_sample/
├── portfolio.yaml
├── deal_a_cedant_north_term_yrt.csv
├── deal_b_cedant_north_wl_coinsurance.csv
├── deal_c_cedant_south_term_coinsurance.csv
├── deal_d_cedant_south_ul_modco.csv
└── README.md
```

`portfolio.yaml` references each CSV via the `inforce_csv:` key (the
CLI parser already handles this — see `cli.py:1876` and
`data/configs/portfolio_demo.yaml` for the inline-policies style, then
use the `inforce_csv` variant for path references).

**Optional QA promotion.** If the sample portfolio is stable and the
ingestion pipeline produces deterministic output, the
`data/qa/golden_inforce.csv` + `golden_config_*.json` family can grow
a `golden_portfolio.yaml` + per-deal CSVs that mirror the sample
shape, so the QA suite has a portfolio golden baseline. Treat this as
a follow-up after Slice 3 lands — promoting to `data/qa/` requires
regenerating baselines and is its own scope.

## 6. Documentation expectations

The daily-dev routine's session workflow applies to every slice. The
short checklist:

1. **Before Slice 1:** read CLAUDE.md, this PLAN, ARCHITECTURE.md, the
   listed ADRs.
2. **During each slice:** TDD (write the test, see it fail, implement).
3. **After Slice 1:** create
   `docs/CONTINUATION_dashboard_portfolio.md` with the slice tracker
   (status: IN PROGRESS, slice 1: DONE, slice 2: NEXT, slice 3:
   PLANNED). Format mirrors `docs/CONTINUATION_portfolio_aggregation.md`.
4. **After each slice:** write
   `docs/DEV_SESSION_LOG_{date}_dashboard_portfolio_s{N}.md`.
   Reference the format used by recent logs (e.g.
   `DEV_SESSION_LOG_2026-06-07_concentration_by_dimension.md`).
5. **For any design choice non-obvious from the code:** add an ADR to
   `docs/DECISIONS.md`. Likely candidates:
   - ADR for "dashboard portfolio loader reuses the CLI parser"
     (if the implementation requires a public helper in `cli.py` to
     avoid importing a private function — read the CLI module before
     deciding).
   - ADR for the concentration page UX (basis-first vs dimension-first
     dropdown; the recommendation here is dimension-first, but if the
     implementer chooses differently the rationale belongs in
     DECISIONS.md).
6. **When all three slices land:**
   - Run the HARVEST FOLLOW-UPS step before flipping the CONTINUATION
     to COMPLETE — promote any out-of-scope refinements (calendar-
     aligned portfolio dashboard polish, capital-weighted concentration
     basis UX, etc.) to the latest `docs/PRODUCT_DIRECTION_*.md`.
   - Then mark the CONTINUATION COMPLETE.
   - Cross out the corresponding entries in
     `PRODUCT_DIRECTION_2026-05-23.md` ("Streamlit dashboard page for
     portfolio runs" / "...for calendar-aligned portfolios" /
     "Dashboard surfacing of `concentration_by_basis`").
7. **Keep PRODUCT_DIRECTION in sync.** After each slice's PR is
   merged, cross out the item there too — the file is the daily-dev
   routine's source of truth for what is shippable.

## 7. Quality gates (mandatory before every commit)

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix
uv run pytest tests/ -v --tb=short -m "not slow"
uv run pytest tests/qa/ -v --tb=short
uv run polaris price \
  --inforce data/qa/golden_inforce.csv \
  --config data/qa/golden_config_flat.json \
  -o /tmp/dev_check.json
```

The golden regression must produce byte-identical output to the
current main baseline at every slice boundary. If it changes,
something has leaked from the dashboard layer into core — investigate
and revert before commit.

## 8. Guardrails

- **NEVER** modify `analytics/portfolio.py` in this feature. If you
  need a helper that does not exist, log it as a follow-up.
- **NEVER** duplicate the CLI's portfolio config parser. Import from
  `polaris_re.cli` (or, if `_build_portfolio_from_config` is private,
  refactor to expose a public helper as a one-line change inside an
  ADR-documented commit).
- **NEVER** regenerate `data/qa/golden_*.json` as part of this
  feature. The dashboard is a separate consumer of the same pipeline;
  it must not move golden outputs.
- **NEVER** merge your own PR. Draft only.
- **If uncertain about a Streamlit pattern** (e.g. how to drive
  `st.file_uploader` from `AppTest`), check the existing
  `tests/qa/test_dashboard_flows.py` patterns and the comments at its
  module docstring — there are documented workarounds (session-state
  injection) already in place.

## 9. Out of scope (do NOT attempt in this feature)

- **Portfolio scenarios as a separate top-level page.** Keep it as a
  sub-section on the Portfolio page.
- **Dashboard A/B testing of basis-outer vs dimension-outer.** The
  recommendation is dimension-outer (ADR-073 motivation). If
  reviewers push back, log it and let the human decide; do not ship
  both views.
- **Editing portfolio configs in-browser.** Upload only.
- **Per-deal scenario overrides** (PRODUCT_DIRECTION promoted
  follow-up). Surface only the uniform-stress `Portfolio.run_scenarios`
  pattern.
- **Calendar-aligned portfolio UX polish** beyond the `align` toggle.
  PRODUCT_DIRECTION has a separate ~3 dev-day entry for that; flag any
  rough edges to that entry rather than addressing them inline.
- **Asset / ALM integration** for the capital section. Use the
  interim factor schedule (ADR-072) only.

---

## Appendix: kickoff prompt for the new session

Paste this into a fresh Claude Code session in the polaris-re repo:

> Build the Streamlit dashboard portfolio page per `docs/PLAN_dashboard_portfolio.md`.
>
> Read the plan in full before writing any code. Start with Slice 1
> (sample data + loader). Follow the daily-dev routine's session
> workflow: TDD, mandatory `make format` + `make lint` + `pytest`
> quality gates before commit, draft PR only.
>
> When Slice 1 lands, create
> `docs/CONTINUATION_dashboard_portfolio.md` with the slice tracker
> and write
> `docs/DEV_SESSION_LOG_{today}_dashboard_portfolio_s1.md`. Update
> `docs/PRODUCT_DIRECTION_2026-05-23.md` to cross out the relevant
> items only after the corresponding slice's PR is merged.
>
> The plan's §3 lists every prerequisite ADR — read those sections of
> `docs/DECISIONS.md` before touching any matching surface. The plan's
> §8 lists the guardrails; respect them.
>
> Open a draft PR titled `feat(dashboard): portfolio page slice 1 —
> sample data + loader` (or s2 / s3 as appropriate) with the standard
> What / Why / Changes / Tests / Acceptance / Out-of-scope sections
> the routine documents.
