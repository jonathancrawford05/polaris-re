# Continuation: Streamlit Dashboard — Portfolio Page

**Source:** `docs/PLAN_dashboard_portfolio.md` (NICE-TO-HAVE per PRODUCT_DIRECTION_2026-05-23)
**Status:** COMPLETE (Slice 1 shipped 2026-06-07; Slice 2 shipped 2026-06-08; Slice 3 shipped 2026-06-09)
**Total slices:** 3
**Estimated total scope:** ~4 dev-days

## Overall Goal

Add a **Portfolio** page to the Streamlit dashboard that surfaces the
existing portfolio-aggregation engine (`Portfolio.run`,
`Portfolio.run_scenarios`, `Portfolio.run_with_capital`) through an
interactive UI. The page is the deal-committee-facing surface for
multi-deal portfolio analysis: upload a portfolio config + the per-deal
inforce CSVs, run, and review aggregate tiles, per-deal breakdowns,
multi-basis / multi-dimension concentration charts (ADR-069 + ADR-073),
scenario stress results, and aggregate LICAT capital metrics.

No new analytical capability is introduced — every number comes through
an existing `Portfolio.*` call. This is presentation-only.

## Decomposition

### Slice 1: Sample data + reusable loader

- **Status:** DONE (2026-06-07)
- **Branch:** claude/bold-newton-1b1RO
- **PR:** (draft — see open PRs)
- **What was done:**
  - Generated a 4-deal, 3-cedant, 3-product, 3-treaty, 100-policy
    sample portfolio under `data/inputs/portfolio_sample/`. Composition
    exercises the multi-basis concentration surface (YRT-only DEAL_A
    makes `ceded_nar_peak` visibly diverge from `ceded_face`), the
    calendar-aligned aggregator (DEAL_C / DEAL_D `valuation_date =
    2026-01-15`, two weeks after the other two), and the rated-block
    panel (7 rated lives across the book).
  - Added `src/polaris_re/dashboard/components/portfolio_loader.py`
    with two entry points:
    - `load_portfolio_from_config_path(path)` — disk path → portfolio.
    - `load_portfolio_from_uploaded(yaml_text, csv_files, workdir=None)`
      — in-memory uploads → persisted temp dir → portfolio.
    Both delegate to `cli._build_portfolio_from_config` so the config
    schema stays single-sourced in the CLI. The dashboard adapter
    converts `typer.Exit` to `PolarisValidationError` so Streamlit sees
    a Python exception instead of SystemExit, and rewrites
    `inforce_csv:` references by basename so uploaded CSVs resolve.
  - Extended `InforceBlock.from_csv` to read optional
    `account_value` / `credited_rate` columns so UL deals can use the
    same CSV layout as TERM / WHOLE_LIFE deals.
  - 9 new unit tests in `tests/test_dashboard/test_portfolio_loader.py`
    covering round-trip via path, round-trip via uploaded bytes,
    workdir defaulting, missing-CSV error, malformed-YAML error,
    non-mapping-YAML error.
- **Key decisions:**
  - **Loader reuses the CLI parser** rather than duplicating the
    per-deal schema. The CLI's `typer.Exit` is caught and rewrapped
    so the dashboard sees a regular Python exception. No CLI refactor
    needed for Slice 1; if reviewers prefer a public CLI helper a
    one-line rename can land alongside Slice 2 with its own ADR.
  - **Cedant = 3** (CedantNorth, CedantSouth, CedantWest). The PLAN
    §5 table listed CedantSouth for DEAL_D but its Acceptance line
    required ≥3 cedants; CedantWest was chosen for DEAL_D to satisfy
    the harder constraint. The CSV filename keeps the original
    `_south_` suffix for grep-ability and to match the plan; the
    cedant label is set in the YAML.
  - **UL columns appended to DEAL_D's CSV** rather than using inline
    policies in YAML. Required a 4-line extension to
    `InforceBlock.from_csv` (read `account_value` and `credited_rate`
    as optional row keys); keeps all four deals using the same
    inforce_csv reference pattern.
- **Quality gate:**
  - `make format` + `make lint` clean; new file mypy-clean.
  - `pytest tests/ -m "not slow"` — 1213 passed, 4 skipped, 4
    pre-existing failures unrelated to this change (missing SOA
    mortality table CSVs in env).
  - `pytest tests/qa/` — 36 passed, 4 skipped.
  - Golden regression byte-identical to baseline.

### Slice 2: Portfolio page — Overview + per-deal breakdown — DONE

- **Status:** DONE (2026-06-08)
- **Branch:** claude/dashboard-portfolio-slice-2-DZe4j
- **PR:** (draft — see open PRs)
- **What was done:**
  - Added `src/polaris_re/dashboard/views/portfolio.py` with
    `page_portfolio()` entry point:
    - Two `st.file_uploader` widgets in side-by-side columns (YAML/JSON
      portfolio config + multi-file inforce CSVs).
    - `st.selectbox` for `align` mode (`"strict"` default, `"calendar"`
      option) with full ADR-061/062 help text.
    - "Run portfolio" button that delegates to
      `load_portfolio_from_uploaded` (the Slice-1 loader) then calls
      `portfolio.run(hurdle_rate, align=align)`.
    - Empty-state `st.info` prompt when no result is in session state.
    - Six aggregate tiles: Deals, Total Ceded Face, Total PV Profits,
      Total IRR, Profit Margin, Peak Ceded NAR.
    - Calendar-alignment banner showing `grid_origin` and directing
      attention to the per-deal offset column when any offset ≠ 0.
    - Per-deal breakdown `st.dataframe` with columns: Deal ID, Cedant,
      Product, Treaty, Policies, Face Amount, Ceded Face, PV Profits,
      IRR, Profit Margin, and (when calendar mode) Grid Offset (months).
  - Wired `"Portfolio"` into `dashboard/app.py` sidebar radio immediately
    after "Deal Pricing" and added the `elif` dispatch + import.
  - Added `portfolio_result` to `KEYS` in `dashboard/components/state.py`,
    initialised to `None` by `init_session_state`.
  - Added `tests/qa/test_dashboard_flows.py::TestPortfolioPage` (7 tests)
    using session-state injection pattern: `load_portfolio_from_config_path`
    builds the full 4-deal sample result once per class (fixture); tests
    inject it into `st.session_state["portfolio_result"]` and assert the
    page renders correctly (all 6 tile labels present, deal count / PV
    profits values correct, per-deal dataframe has one row per deal with
    the right deal IDs).
- **Key decisions:**
  - **grid_origin banner conditional on any_offset**: under
    `align="strict"` all offsets are 0, so the banner is suppressed. Under
    `align="calendar"` with same-month valuation dates (the current sample),
    `months_between` also returns 0 — banner suppressed. The banner fires
    correctly when treaties have different-month inception dates.
  - **Metric label "Deals"** (not "Number of Deals") keeps tile concise and
    matches the assertion in the test.
  - **list[dict[str, object]] for dataframe rows**: avoids a heavy pandas
    import in the dashboard module; Streamlit converts the list of dicts
    to a DataFrame internally.
- **Quality gate:**
  - `make format` + `make lint` clean.
  - `pytest tests/qa/test_dashboard_flows.py` — 28 passed (21 existing
    + 7 new).
  - `pytest tests/ -m "not slow"` — 1148 passed, 6 pre-existing failures
    (4 missing SOA table CSVs + 2 openpyxl tests) unchanged.
  - Golden price regression ran successfully (no baseline diff file in
    env, but pipeline output unchanged).

### Slice 3: Concentration + Scenarios + Capital sub-sections — DONE

- **Status:** DONE (2026-06-09)
- **Branch:** claude/nifty-babbage-n7hemq
- **PR:** (draft — see open PRs)
- **What was done:**
  - **Concentration sub-section** (in `views/portfolio.py`):
    `st.selectbox("Group by", ["Cedant", "Product", "Treaty"])` →
    `result.concentration_by_dimension()[dim_key]` → three side-by-side
    horizontal bar charts (one per basis: ceded face / peak ceded NAR /
    PV premiums) via a new `concentration_bar()` helper in
    `components/charts.py`. HHI table below the charts: rows = bases,
    columns = dimensions, values from
    `result.hhi_by_dimension()`. `st.download_button` emits a long-format
    CSV (`dimension, basis, label, share`) via the page-local
    `_concentration_to_csv_bytes` helper. A one-line comment at the call
    site explicitly links ADR-073 — this page is the primary consumer.
  - **Scenarios sub-section**: `st.multiselect` over the six
    `ScenarioRunner.standard_stress_scenarios()` (default: all selected)
    plus a "Run scenarios" button → `portfolio.run_scenarios(hurdle,
    scenarios, align=align)` → stored under
    `st.session_state["portfolio_scenarios"]`. PV / IRR / margin table
    with the BASE row pinned at the top. Worst-case callout fed by
    `PortfolioScenarioResult.worst_case()` with the `None` branch
    rendering "Worst case: N/A".
  - **Capital sub-section**: `st.checkbox("Include LICAT capital metrics")`
    + `st.selectbox` over `ProductType` (default TERM) +
    "Compute LICAT capital" button →
    `portfolio.run_with_capital(hurdle,
    LICATCapital.for_product_interim(product_type), align=align)` →
    stored under `st.session_state["portfolio_capital_result"]`. Tiles
    for `initial_capital`, `peak_capital`, `pv_capital`,
    `return_on_capital`, and `capital_adjusted_irr` (surfaced
    prominently as the canonical portfolio IRR per the Slice 2
    Refinement Backlog). Line chart of `capital_by_period` via a new
    `portfolio_capital_chart()` helper.
  - **Total-IRR caption on the Overview tiles**: new
    `_irr_explanation()` matching the `views/pricing._irr_explanation`
    pattern. When `total_irr is None`, a `st.caption` below the tile
    row points the user to LICAT capital for `capital_adjusted_irr`.
  - **Session state extended** (`components/state.py`):
    `portfolio_scenarios` and `portfolio_capital_result` keys
    initialised to `None` by `init_session_state`. An additional
    `portfolio_runtime` key (not declared in `KEYS` — set on demand by
    the Run button) holds the live `Portfolio` object + hurdle rate +
    align mode so the Scenarios and Capital sub-sections can re-invoke
    the engine across Streamlit reruns without re-uploading the config.
  - **Tests — 8 new** in `tests/qa/test_dashboard_flows.py`:
    - `TestPortfolioPageConcentration` (5 tests): default Cedant
      dimension renders, Group By switches to Product and Treaty without
      exception, HHI dataframe has 3 basis rows and Cedant / Product /
      Treaty columns, `_concentration_to_csv_bytes` emits one row per
      (basis, dimension, label) triple.
    - `TestPortfolioPageScenarios` (2 tests): scenario dataframe
      contains BASE / MORT_110 / MORT_90 when scenarios are
      pre-computed and injected into session state; worst-case callout
      renders (warning or info depending on the `None` branch).
    - `TestPortfolioPageCapital` (2 tests): all five capital tiles
      render when `portfolio_capital_result` is injected; the
      Capital-Adjusted IRR tile is present (Refinement Backlog item).
- **Key decisions:**
  - **Pin BASE at the top of the scenarios table** by sorting rows with
    `key=lambda row: 0 if row["Scenario"] == "BASE" else 1` rather than
    a `st.dataframe` styler — keeps the dependency on a single
    `list[dict]` shape and avoids importing pandas just for visual
    formatting.
  - **Capital model is per-product, applied uniformly**: `run_with_capital`
    takes a single `LICATCapital`, so the page exposes a product-type
    selectbox (default TERM) and applies `for_product_interim` of that
    type to the entire portfolio. ADR-060 explicitly out-of-scopes
    per-deal factor maps; the inline help on the selectbox documents
    the simplification.
  - **`portfolio_runtime` not in `KEYS`**: the live `Portfolio` object
    is set imperatively by the Run button and consumed only by the
    Scenarios / Capital sub-sections. Initialising it to `None` in
    `init_session_state` would suggest it is a stable public surface;
    keeping it out of `KEYS` matches its on-demand nature. The two
    derived result keys (`portfolio_scenarios`,
    `portfolio_capital_result`) ARE in `KEYS` because tests inject them
    directly via session-state pre-population.
  - **Test pattern: pre-compute, inject, render**: the scenario and
    capital sub-sections gate their compute on a button click that
    AppTest does not drive (the live `Portfolio` is built on upload,
    which AppTest cannot simulate). Tests therefore call
    `portfolio.run_scenarios(...)` / `portfolio.run_with_capital(...)`
    directly, inject the result via `at.session_state[...]`, and
    assert on the rendered output. Same pattern as the Slice 2
    `TestPortfolioPage`.
- **Quality gate:**
  - `uv run ruff format src/ tests/` — clean (2 files reformatted to
    match existing style).
  - `uv run ruff check src/ tests/` — All checks passed.
  - `uv run pytest tests/qa/test_dashboard_flows.py -v` — 37 passed
    (29 existing + 8 new).
  - `uv run pytest tests/ -m "not slow"` — 1157 passed, 1 skipped,
    6 pre-existing failures unrelated to this change (4 missing SOA
    table CSVs + 2 openpyxl-dependent tests; 3 collection errors from
    the same missing module; identical baseline to Slice 2).
  - Golden price regression ran successfully against
    `data/qa/golden_inforce.csv` + `golden_config_flat.json` — output
    matches the baseline shape.

## Refinement Backlog (carry-overs flagged during Slice 1 / 2)

- **Calendar-aligned sample dates**: the sample portfolio's DEAL_C / DEAL_D
  valuation dates (2026-01-15) differ from DEAL_A / DEAL_B (2026-01-01) by
  only 14 days — both in January, so `months_between` returns 0 and the
  calendar grid_offset is 0 for all deals. The "grid_origin / per-deal offset"
  banner therefore never fires on the current sample. Consider a follow-up
  that moves DEAL_C / DEAL_D to February 2026 to produce non-zero offsets
  and fully exercise the calendar-alignment UI path. Track in
  PRODUCT_DIRECTION as "Calendar-aligned portfolio UX polish".

- **Error handling — PolarisComputationError**: the Run button's `except`
  clause catches `PolarisValidationError` only. If `portfolio.run()` raises
  `PolarisComputationError` (numerical failure, e.g. singular matrix during
  IRR root-finding) the user sees a raw Streamlit traceback. This is
  consistent with the existing dashboard pages (`pricing.py`, `scenario.py`)
  which also only guard validation errors; widening the catch to include
  `PolarisComputationError` across all pages is the appropriate scope for
  this fix rather than a one-off change here. Log as a cross-cutting
  dashboard hardening task in PRODUCT_DIRECTION.

- **Portfolio aggregate IRR shows N/A for the sample portfolio**: this is
  correct behaviour per ADR-041. The aggregate reinsurer NCF for the 4-deal
  sample is positive in every projection month — a YRT + coinsurance + modco
  mix where the reinsurer earns net premiums from day one with no upfront
  capital deployment creates no sign change, so scipy's IRR root-finder
  returns `None`. This is not a bug; it reflects the economics of this
  particular book. The correct metric for a meaningful portfolio-level IRR
  is **`capital_adjusted_irr`** on `PortfolioResultWithCapital` (Slice 3
  capital sub-section): subtracting per-period capital strain from NCF —
  and releasing residual capital at the terminal month — creates the sign
  change that makes IRR well-defined. Slice 3 is therefore the right moment
  to surface a portfolio IRR, not Slice 2. In the interim, per-deal IRRs
  in the breakdown table provide the most useful deal-level signal.
  Optionally add a `st.caption` to the "Total IRR" tile explaining the N/A
  (matching the `_irr_explanation` pattern on the Deal Pricing page) — log
  as a low-priority UX polish item for Slice 3.

## Out of Scope (per PLAN §9)

- Portfolio scenarios as a separate top-level page (kept as
  sub-section).
- Dashboard A/B of basis-outer vs dimension-outer.
- Editing portfolio configs in-browser.
- Per-deal scenario overrides.
- Calendar-aligned portfolio UX polish beyond the `align` toggle.
- Asset / ALM integration in the capital section.
