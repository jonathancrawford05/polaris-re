# Claude Code Task: Streamlit Dashboard Rebuild — Phase A & B

## Pre-flight

1. Read these files in order before writing any code:
   - `CLAUDE.md` (full project conventions)
   - `ARCHITECTURE.md` (data flow)
   - `docs/DECISIONS.md` (ADR-032, ADR-034, ADR-036)
   - `docs/STREAMLIT_REBUILD_PLAN.md` (the full build plan — this is your primary spec)
   - `src/polaris_re/dashboard/app.py` (current implementation — reuse chart helpers)
   - `src/polaris_re/assumptions/mortality.py` (MortalityTable.load and _SOURCE_CONFIG)
   - `src/polaris_re/utils/table_io.py` (load_mortality_csv validation logic)
   - `src/polaris_re/core/inforce.py` (InforceBlock.from_csv, effective_cession_vec)
   - `scripts/generate_synthetic_block.py` (synthetic block generation)

2. Checkout a new branch: `feature/streamlit-dashboard-rebuild`

3. Run `make test` to confirm baseline (522+ tests pass, 0 failures).

---

## Scope: Phase A + B from STREAMLIT_REBUILD_PLAN.md

Complete Phase A (Foundation) and Phase B (Inforce & Assumptions pages) only.
Do NOT start Phases C-E in this task.

---

## Phase A — Foundation

### A1. Fix `load_mortality_csv` max_age validation

The current code in `utils/table_io.py` hardcodes expected `max_age` and rejects
valid tables when the CSV max age is lower (e.g., SOA VBT 2015 goes to 95, not 120).

**Required change:** Make `max_age` auto-detected from the CSV when loading.
- In `load_mortality_csv()`: remove the validation that raises
  `PolarisValidationError(f"Table max age {actual_max_age} < expected {max_age}.")`
- Instead, use the actual max age from the CSV as the table's max_age
- Print a confirmatory message: `f"Loaded {path.name}: ages {actual_min_age}-{actual_max_age}"`
- Update `_SOURCE_CONFIG` in `mortality.py` to remove hardcoded `max_age` or make
  it optional (None = auto-detect from file)
- The `min_age` validation can stay (it's correct to require coverage from age 18)
- Update existing tests if they assert on the old max_age validation error

**Verify:** After this fix, the following should work without monkey-patching:
```python
mortality = MortalityTable.load(
    source=MortalityTableSource.SOA_VBT_2015,
    data_dir=Path("data"),
)
```

The SOA VBT 2015 CSVs in `data/mortality_tables/` have max age 95.
The CIA 2014 CSVs have max age 90. Both must load cleanly.

### A2. Refactor dashboard into multi-file structure

Create this structure:
```
src/polaris_re/dashboard/
├── __init__.py          (update exports)
├── app.py               (main entry: page config, sidebar nav, session state init)
├── pages/
│   ├── __init__.py
│   ├── inforce.py       (Page 1: inforce block upload + synthetic generator)
│   ├── assumptions.py   (Page 2: mortality/lapse table selection)
│   ├── pricing.py       (Page 3: deal pricing — migrate from current app.py)
│   ├── scenario.py      (Page 5: scenario analysis — migrate from current app.py)
│   └── uq.py            (Page 6: Monte Carlo UQ — migrate from current app.py)
└── components/
    ├── __init__.py
    ├── charts.py         (move _cashflow_waterfall, _uq_histogram, _scenario_tornado here)
    └── state.py          (session state init, validation helpers)
```

- `app.py` becomes the entry point with sidebar navigation calling page functions
- Move the three chart helpers to `components/charts.py`
- Create `components/state.py` with session state initialization:
  ```python
  KEYS = ["inforce_block", "assumption_set", "projection_config",
          "gross_result", "mortality_source", "lapse_source",
          "ml_mortality_model", "ml_lapse_model"]

  def init_session_state():
      for key in KEYS:
          if key not in st.session_state:
              st.session_state[key] = None
  ```
- Pages 3, 5, 6 are migrated from current `_page_pricing`, `_page_scenario`,
  `_page_uq` — keep them working with the existing flat-rate fallback for now.
  They will be rebuilt in Phase C/D to use session state.

**Verify:** `uv run streamlit run src/polaris_re/dashboard/app.py` still works,
all three existing pages render and produce results.

---

## Phase B — Inforce & Assumptions Pages

### B1. Page 1: Inforce Block (pages/inforce.py)

Two tabs: "Upload File" and "Generate Synthetic"

**Upload File tab:**
- `st.file_uploader("Upload inforce CSV", type=["csv"])` 
- On upload: write to temp file, call `InforceBlock.from_csv(path)`, store in
  `st.session_state["inforce_block"]`
- Display summary panel with `st.metrics`:
  - Total policies, total face amount, mean attained age
- Display sex split and smoker split (use `st.columns` with metric cards)
- **Age × Gender distribution chart:**
  - Compute 5-year age bands from the block (20-24, 25-29, ..., 65-69, 70+)
  - Count policies per age_band × sex
  - Display as horizontal grouped bar chart (Plotly preferred for interactivity,
    matplotlib acceptable). Male bars in one color, female in another.
  - Below or beside each age band: number input or slider showing count per gender
  - When user adjusts counts, rebuild the InforceBlock by resampling/duplicating
    policies to match target distribution. Store updated block in session state.
  - "Reset to File" button restores original uploaded distribution

**Generate Synthetic tab:**
- Sliders: n_policies (10-10000, default 1000), mean_age (30-60, default 40),
  age_std (5-15, default 8), male_pct (0-100, default 60),
  smoker_pct (0-100, default 15), face_median ($100k-$2M, default $500k),
  term_mix_10yr/20yr/30yr (three sliders summing to 100)
- "Generate" button calls the logic from `scripts/generate_synthetic_block.py`
  (import `generate_synthetic_block` function, write to temp CSV, load via
  `InforceBlock.from_csv`)
- Same summary panel and demographic chart as Upload tab
- Store in `st.session_state["inforce_block"]`

**Test:** Upload `data/synthetic_block.csv` (generate it first with
`make synthetic-block` if it doesn't exist). Verify summary stats display
and chart renders.

### B2. Page 2: Assumptions (pages/assumptions.py)

Three sections using `st.subheader`:

**Section: Mortality Basis**
- `st.selectbox("Mortality Table", ["SOA VBT 2015", "CIA 2014", "2001 CSO", "Flat Rate"])`
- Real tables: call `MortalityTable.load(source, data_dir=Path(os.environ.get("POLARIS_DATA_DIR", "data")))` 
- Display q_x curve: x=attained age, y=annual q_x. Plot available sex/smoker
  combos as separate lines. Use Plotly or matplotlib.
- Mortality multiplier slider (0.50-2.00, default 1.00) — will be applied during
  projection via ScenarioAdjustment pattern
- Flat Rate fallback: show q_x per-mille slider (existing behaviour)
- Store selected source in `st.session_state["mortality_source"]`

**Section: Lapse Basis**
- `st.selectbox("Lapse Assumption", ["Manual Duration Table", "CSV Upload"])`
  (SOA LLAT option only if lapse tables exist in data/lapse_tables/)
- Manual: 11 sliders — Year 1 through Year 10 + Ultimate
  - Pre-populate with realistic curve: 6%, 5%, 4%, 3.5%, 3%, 2.5%, 2%, 2%, 2%, 2%, ult 1.5%
  - Build via `LapseAssumption.from_duration_table({1: val1, ..., "ultimate": ult})`
- CSV Upload: file_uploader for lapse CSV, load via `load_lapse_csv()` then
  construct `LapseAssumption` from the `LapseTableArray`
- Display lapse curve chart: x=policy year, y=annual lapse rate
- Lapse multiplier slider (0.50-2.00, default 1.00)
- Store in `st.session_state["lapse_source"]`

**Section: Improvement Scale (in expander)**
- `st.selectbox("Mortality Improvement", ["None", "Scale AA", "MP-2020", "CPM-B"])`
- Informational display only for now — improvement will be applied during projection

**"Save Assumptions" button:**
- Constructs `AssumptionSet` from selected mortality + lapse
- Stores in `st.session_state["assumption_set"]`
- Shows success banner with assumption version string

**Test:** Select SOA VBT 2015, verify q_x curves render for Male NS and Male Smoker.
Select manual lapse, adjust year-1 from 6% to 15%, verify curve updates.
Click Save Assumptions, verify session state populated.

---

## Quality Requirements

- Run `make test` — all existing tests must still pass (no regressions)
- Run `uv run ruff check src/ tests/` — zero violations
- Run `uv run ruff format src/ tests/` — all files formatted
- Dashboard is excluded from coverage (ADR-032) — visual testing only
- Add `plotly>=5.20` to `[project.optional-dependencies] dashboard` and to
  `[dependency-groups] dev` if using Plotly for charts
- Update `uv.lock` if dependencies change

---

## Do NOT

- Touch any files outside `src/polaris_re/dashboard/`, `pyproject.toml`, and `uv.lock`
  unless fixing a bug discovered during testing (e.g., the max_age fix in
  `utils/table_io.py` and `assumptions/mortality.py` IS in scope)
- Rebuild Pages 3, 5, 6 to use session state — that's Phase C/D (separate task)
- Add ML model upload — that's Phase E (separate task)
- Add new test files for dashboard code (excluded from coverage per ADR-032)
- Use `from __future__ import annotations` (Python 3.12 — not needed)
