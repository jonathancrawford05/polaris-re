# Continuation: Streamlit Dashboard — Portfolio Page

**Source:** `docs/PLAN_dashboard_portfolio.md` (NICE-TO-HAVE per PRODUCT_DIRECTION_2026-05-23)
**Status:** IN PROGRESS (Slice 1 shipped 2026-06-07; Slice 2 shipped 2026-06-08; Slice 3 NEXT)
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

### Slice 3: Concentration + Scenarios + Capital sub-sections (PLANNED)

- **Status:** PLANNED
- **Scope (from PLAN §4):**
  - **Concentration:** `st.selectbox` over Cedant / Product / Treaty
    drives `result.concentration_by_dimension()[dim]` → three side-by-
    side bar charts (face / NAR-peak / PV-premium). HHI matrix table.
    CSV export (long format: dimension, basis, label, share).
  - **Scenarios:** `st.multiselect` of standard six-scenario set →
    `portfolio.run_scenarios(hurdle, scenarios)` → PV / IRR / margin
    table with BASE pinned. Worst-case callout.
  - **Capital:** `st.checkbox` toggle →
    `portfolio.run_with_capital(hurdle, LICATCapital.for_product_interim(...))`
    → initial / peak / PV capital + RoC + capital-adjusted IRR tiles
    + capital-by-period line chart. `capital_adjusted_irr` is also the
    canonical portfolio IRR (see Refinement Backlog note on Total IRR
    N/A); surface it prominently alongside the other capital tiles.
  - **IRR caption on the Overview tiles**: when `total_irr` is `None`,
    add a `st.caption` below the tile row explaining why (matching the
    `_irr_explanation` pattern from `views/pricing.py`) and directing
    the user to enable LICAT capital for `capital_adjusted_irr`.
- **Acceptance:** Dimension picker drives the bar charts through
  `concentration_by_dimension()`. HHI matrix uses
  `hhi_by_dimension()`. Scenarios sub-section reproduces the shape
  emitted by `polaris portfolio scenarios`. Capital sub-section
  reproduces `PortfolioResultWithCapital.to_dict()["capital"]`.

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
