# Continuation: Streamlit Dashboard — Portfolio Page

**Source:** `docs/PLAN_dashboard_portfolio.md` (NICE-TO-HAVE per PRODUCT_DIRECTION_2026-05-23)
**Status:** IN PROGRESS (Slice 1 shipped 2026-06-07; Slice 2 NEXT)
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

### Slice 2: Portfolio page — Overview + per-deal breakdown (NEXT)

- **Status:** PLANNED
- **Scope (from PLAN §4):**
  - `dashboard/views/portfolio.py` with `page_portfolio()`: two
    `st.file_uploader` widgets (YAML config + multi-CSV), a "Run
    portfolio" button, aggregate tiles + per-deal table, an
    `st.selectbox` for `align="strict" | "calendar"`.
  - Wire `"Portfolio"` into `dashboard/app.py`'s sidebar radio.
  - Add `portfolio_result` to `components/state.py`.
  - AppTest smoke tests in
    `tests/qa/test_dashboard_flows.py::TestPortfolioPage` driving via
    session-state injection (file_uploader cannot be driven directly
    by AppTest — pattern documented in the test module).
- **Acceptance (from PLAN §4):** Portfolio entry visible in sidebar;
  upload + Run populates tiles / table; `align="calendar"` surfaces
  `grid_origin` + per-deal `grid_offset`. AppTest suite green.

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
    + capital-by-period line chart.
- **Acceptance:** Dimension picker drives the bar charts through
  `concentration_by_dimension()`. HHI matrix uses
  `hhi_by_dimension()`. Scenarios sub-section reproduces the shape
  emitted by `polaris portfolio scenarios`. Capital sub-section
  reproduces `PortfolioResultWithCapital.to_dict()["capital"]`.

## Refinement Backlog (carry-overs flagged during Slice 1)

- **None yet.** Slice 1 was tight to the PLAN; any follow-ups will be
  recorded here as Slice 2 and Slice 3 land.

## Out of Scope (per PLAN §9)

- Portfolio scenarios as a separate top-level page (kept as
  sub-section).
- Dashboard A/B of basis-outer vs dimension-outer.
- Editing portfolio configs in-browser.
- Per-deal scenario overrides.
- Calendar-aligned portfolio UX polish beyond the `align` toggle.
- Asset / ALM integration in the capital section.
