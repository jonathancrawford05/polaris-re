# Streamlit Dashboard Rebuild — Build Plan

> **Handoff document for Claude Code.** Read `CLAUDE.md`, `ARCHITECTURE.md`, and
> `docs/DECISIONS.md` (especially ADR-036) before starting. The current
> `src/polaris_re/dashboard/app.py` is the baseline — it works but uses flat
> synthetic assumptions that make most inputs mathematically degenerate.

---

## Context & Motivation

User testing of the Phase 4 Streamlit dashboard revealed critical usability gaps:

1. **Flat-rate mortality** (single slider) causes profit margin to be invariant to
   lapse rate, hurdle rate, and discount rate. With constant q_x across all ages,
   the lx factors cancel in the margin ratio. This makes the dashboard appear broken.
2. **No real table support** — SOA VBT 2015 and CIA 2014 tables exist in
   `data/mortality_tables/` but the dashboard constructs a synthetic flat table
   from a slider value instead of loading them.
3. **Single-policy archetype** — the dashboard builds N identical policies. Real
   reinsurance deals have heterogeneous blocks with age/sex/smoker distributions.
4. **No file input** — users cannot point to cedant inforce data or assumption files.
   Every run requires manual slider configuration.
5. **No ML comparison** — Phase 4 built `MLMortalityAssumption` and `MLLapseAssumption`
   but neither is wired into the dashboard.

The rebuild transforms the dashboard from a toy demo into a usable deal evaluation
tool that works on realistic data.

---

## Design Principles

- **File-first, sliders-second**: the primary workflow is uploading/pointing to data
  files, not configuring individual sliders. Sliders exist to override file-derived
  values, not to define them from scratch.
- **Block-level, not policy-level**: the dashboard evaluates a block of policies with
  a realistic distribution, not a single policy archetype.
- **Real assumptions by default**: SOA VBT 2015 is the default mortality basis. Flat
  synthetic rates are still available as a fallback but not the default.
- **Backward compatible**: existing `_build_assumptions()` and `_build_policy_block()`
  helpers remain as internal fallbacks. New code wraps them, not replaces them.

---

## Architecture

### Page Structure (sidebar navigation)

```
1. Inforce Block           ← NEW: data upload + demographic visualisation
2. Assumptions             ← NEW: table selection + ML toggle
3. Deal Pricing            ← REBUILT: uses inforce + assumptions from pages 1-2
4. Treaty Comparison       ← NEW: side-by-side YRT vs Coins vs Modco
5. Scenario Analysis       ← REBUILT: uses real assumptions
6. Monte Carlo UQ          ← REBUILT: uses real assumptions
7. IFRS 17                 ← NEW: BBA/PAA measurement from projection
```

### Session State Contract

All pages read from and write to `st.session_state`. The following keys are the
shared contract between pages:

```python
st.session_state["inforce_block"]       # InforceBlock | None
st.session_state["assumption_set"]      # AssumptionSet | None
st.session_state["projection_config"]   # ProjectionConfig | None
st.session_state["gross_result"]        # CashFlowResult | None (cached projection)
st.session_state["mortality_source"]    # str: "SOA_VBT_2015" | "CIA_2014" | "CSO_2001" | "FLAT"
st.session_state["lapse_source"]        # str: "SOA_LLAT" | "MANUAL" | "CSV"
st.session_state["ml_mortality_model"]  # MLMortalityAssumption | None
st.session_state["ml_lapse_model"]      # MLLapseAssumption | None
```

---

## Page Specifications

### Page 1: Inforce Block

**Purpose:** Load or configure the inforce block that all downstream pages use.

**Two modes:**

#### Mode A — File Upload (primary)

- `st.file_uploader` accepting `.csv` files matching the schema from
  `generate_synthetic_block.py` (columns: `policy_id`, `issue_age`, `attained_age`,
  `sex`, `smoker_status`, `face_amount`, `annual_premium`, `product_type`,
  `policy_term`, `duration_inforce`, `reinsurance_cession_pct`, `issue_date`,
  `valuation_date`).
- On upload, call `InforceBlock.from_csv(path)` to validate and load.
- Display summary statistics panel:
  - Total policies, total face amount, mean attained age
  - Sex split (pie chart or metric cards)
  - Smoker split
  - Product type breakdown
- **Demographic distribution visualisation:**
  - Age distribution as a horizontal bar chart, one bar per 5-year age band
  - Each bar is split by gender (male/female stacked or side-by-side)
  - Sliders overlaid on or adjacent to each bar allow the user to adjust the
    count per age-band × gender cell
  - When the user adjusts a slider, the underlying `InforceBlock` is rebuilt
    by sampling/reweighting policies to match the target distribution
  - A "Reset to File" button restores the original uploaded distribution

#### Mode B — Synthetic Generator (fallback)

- Sliders for: total policies (10–10,000), mean age, age std dev, sex split %,
  smoker split %, face amount median, term mix (10/20/30 year weights)
- Calls `generate_synthetic_block()` internally (reuse the script logic)
- Same demographic visualisation as Mode A, but initialised from synthetic params

**Output:** Sets `st.session_state["inforce_block"]`.

**Implementation notes:**
- Use `st.tabs(["Upload File", "Generate Synthetic"])` for mode selection.
- For the age × gender bar chart with sliders, use `st.columns()` to create a
  row per age band. Each row has: age band label, male slider, female slider,
  horizontal bar showing current counts. Consider using Plotly for the
  interactive chart if matplotlib is too static.
- File upload should write to a temp path then call `InforceBlock.from_csv()`.
- After loading, store the block in session state and show a success banner.

---

### Page 2: Assumptions

**Purpose:** Configure mortality, lapse, and (optionally) ML assumption sources.

**Layout — three sections:**

#### Section 2a — Mortality Basis

- `st.selectbox("Mortality Table", ["SOA VBT 2015", "CIA 2014", "2001 CSO", "Flat Rate"])`
- When a real table is selected:
  - Call `MortalityTable.load(source, data_dir=Path("data"))` 
  - **IMPORTANT:** Before loading, patch `_SOURCE_CONFIG` max_age values:
    - SOA VBT 2015: `max_age=95`
    - CIA 2014: `max_age=90`
    - CSO 2001: keep `max_age=120`
  - Alternatively, implement the dynamic max_age detection fix in `load_mortality_csv()`
    (preferred — see user testing finding about over-restrictive validation)
  - Display a q_x curve chart: x-axis = attained age, y-axis = annual q_x,
    lines for Male NS, Male S, Female NS, Female S (whichever are available)
  - Optional mortality multiplier slider (0.50 to 2.00, default 1.00) for
    sensitivity — applies a scalar multiple to all loaded rates
- When "Flat Rate" is selected: show the existing q_x per-mille slider
- `st.checkbox("Use ML Mortality Model")` — when checked:
  - Show `st.file_uploader` for a joblib model file
  - Load via `MLMortalityAssumption.load(path)`
  - Display feature importance bar chart
  - Store in `st.session_state["ml_mortality_model"]`
  - When ML is active, it replaces the table-based mortality in the AssumptionSet

#### Section 2b — Lapse Basis

- `st.selectbox("Lapse Assumption", ["SOA LLAT 2014", "Manual Duration Table", "CSV Upload"])`
- SOA LLAT 2014: load from `data/lapse_tables/` via `LapseAssumption.load()` 
  (if lapse table ETL from Milestone 4.1 is complete; otherwise show placeholder)
- Manual: duration table sliders — year 1 through year 10 + ultimate
  (pre-populated with SOA-style curve: 6%, 5%, 4%, 3.5%, 3%, 2.5%, 2%, 2%, 2%, 2%, ultimate 1.5%)
- CSV Upload: `st.file_uploader` for lapse CSV matching the schema in `utils/table_io.py`
- Display lapse curve chart: x-axis = policy year, y-axis = annual lapse rate
- Optional lapse multiplier slider (0.50 to 2.00, default 1.00)
- `st.checkbox("Use ML Lapse Model")` — same pattern as ML mortality

#### Section 2c — Improvement Scale (optional)

- `st.selectbox("Mortality Improvement", ["None", "Scale AA", "MP-2020", "CPM-B"])`
- When selected, apply via `MortalityImprovement.apply_improvement()` during projection
- Display improvement rate by age chart

**Output:** Sets `st.session_state["assumption_set"]`, and optionally
`st.session_state["ml_mortality_model"]` and `st.session_state["ml_lapse_model"]`.

**Implementation notes:**
- Use `st.expander("Advanced: Mortality Improvement")` for the improvement section
  to keep the page clean.
- The `AssumptionSet` is constructed on-the-fly when the user clicks a
  "Save Assumptions" button, or auto-constructed when navigating to a pricing page.
- If ML models are active, the `AssumptionSet.mortality` field should hold the
  ML model (duck typing — see ADR-034).

---

### Page 3: Deal Pricing (rebuilt)

**Purpose:** Run the full pricing pipeline on the configured inforce + assumptions.

**Prerequisites check:** On page load, verify `st.session_state["inforce_block"]`
and `st.session_state["assumption_set"]` are populated. If not, show a warning
with links to Pages 1 and 2.

**Inputs (sidebar or top panel):**

- Treaty type: `st.selectbox(["YRT", "Coinsurance", "Modco", "None (Gross)"])`
- Treaty parameters (conditional on type):
  - YRT: cession %, flat YRT rate per $1000 (optional), retention limit
  - Coinsurance: cession %, include expense allowance toggle
  - Modco: cession %, modco interest rate
- Projection horizon (years): slider, default = max policy term in block
- Discount rate: slider (2–12%, default 6%)
- Hurdle rate: slider (5–20%, default 10%)
- `st.checkbox("Pass inforce for policy-level cession overrides")` — when checked,
  passes `inforce=block` to `treaty.apply()` (ADR-036). Explain in a tooltip that
  this uses per-policy `reinsurance_cession_pct` values from the inforce data.

**Run button → outputs:**

- Metric cards: PV Profits, Profit Margin, IRR, Break-even Year
- Annual Profit Waterfall chart (existing `_cashflow_waterfall`)
- Cash flow decomposition chart: stacked area of premiums, claims, reserves, NCF
- Reserve balance over time chart
- Tabular summary: annual premiums, claims, NCF, cumulative NCF

**Implementation notes:**
- Cache the gross projection in `st.session_state["gross_result"]` so treaty
  comparison (Page 4) can reuse it without re-running the product engine.
- Handle `irr=None` gracefully (display "N/A" — already fixed in current code).
- Use `st.columns(4)` for metric cards as in the current implementation.

---

### Page 4: Treaty Comparison (new)

**Purpose:** Side-by-side comparison of the same block under different treaty structures.

**Inputs:**
- Automatically uses the cached gross projection from Page 3
- If no gross result, runs the projection automatically
- Multi-select: which treaties to compare (YRT, Coinsurance, Modco, Gross)

**Outputs:**
- Comparison table: rows = metrics (PV Profit, IRR, Margin, Break-even),
  columns = treaty types
- Overlay chart: NCF over time for each treaty on the same axes
- Reserve transfer comparison: bar chart of total ceded reserves by treaty type

---

### Page 5: Scenario Analysis (rebuilt)

**Purpose:** Stress test using real assumptions from Page 2.

**Changes from current:**
- Remove hardcoded flat assumptions — use `st.session_state["assumption_set"]`
- Remove hardcoded policy block — use `st.session_state["inforce_block"]`
- Add custom scenario builder: user can add rows specifying mortality multiplier
  and lapse multiplier beyond the 6 standard scenarios
- Keep the tornado chart (it's good)
- Add a scenario comparison table with IRR and margin columns

---

### Page 6: Monte Carlo UQ (rebuilt)

**Purpose:** Distribution of deal outcomes under assumption uncertainty.

**Changes from current:**
- Use session state inforce and assumptions (not hardcoded)
- Add scenario count slider and parameter controls (already partially there)
- Add distribution overlay: show base, P5, P50, P95 on the waterfall chart
- Add convergence diagnostic: running mean of PV profits vs scenario count

---

### Page 7: IFRS 17 (new)

**Purpose:** IFRS 17 BBA/PAA measurement on the projected cash flows.

**Inputs:**
- Measurement approach: BBA or PAA
- Risk-free discount rate (for BEL)
- RA factor (cost-of-capital %)
- Uses gross projection from session state

**Outputs:**
- Initial recognition: BEL, RA, CSM metric cards
- CSM amortisation schedule chart
- Insurance liability over time
- P&L: insurance revenue and insurance service result

---

## Implementation Sequence

### Phase A — Foundation (do first)

1. **Fix `load_mortality_csv` max_age validation** — detect actual max_age from CSV
   instead of hardcoding. Print a confirmatory message showing detected range.
   This unblocks all real-table usage. Modify `_SOURCE_CONFIG` entries to remove
   `max_age` or make it optional with auto-detection as fallback.

2. **Refactor `app.py` into multi-file structure:**
   ```
   src/polaris_re/dashboard/
   ├── __init__.py
   ├── app.py              ← main entry point, sidebar nav, session state init
   ├── pages/
   │   ├── __init__.py
   │   ├── inforce.py      ← Page 1
   │   ├── assumptions.py  ← Page 2
   │   ├── pricing.py      ← Page 3
   │   ├── treaty_compare.py ← Page 4
   │   ├── scenario.py     ← Page 5
   │   ├── uq.py           ← Page 6
   │   └── ifrs17.py       ← Page 7
   └── components/
       ├── __init__.py
       ├── charts.py        ← chart helpers (waterfall, tornado, histogram, etc.)
       └── state.py         ← session state helpers and validation
   ```

3. **Session state initialisation** in `app.py`:
   ```python
   for key in ["inforce_block", "assumption_set", "projection_config",
               "gross_result", "mortality_source", "lapse_source",
               "ml_mortality_model", "ml_lapse_model"]:
       if key not in st.session_state:
           st.session_state[key] = None
   ```

### Phase B — Inforce & Assumptions (Pages 1-2)

4. Implement Page 1 (Inforce Block) with file upload and synthetic generator.
5. Implement Page 2 (Assumptions) with real table loading and manual lapse curve.
6. Add demographic distribution visualisation (age × gender bar chart with sliders).

### Phase C — Pricing & Treaties (Pages 3-4)

7. Rebuild Page 3 (Deal Pricing) to consume session state.
8. Implement Page 4 (Treaty Comparison).

### Phase D — Analytics (Pages 5-7)

9. Rebuild Page 5 (Scenario Analysis) on session state.
10. Rebuild Page 6 (Monte Carlo UQ) on session state.
11. Implement Page 7 (IFRS 17).

### Phase E — ML Integration

12. Wire ML mortality/lapse model upload on Page 2.
13. Add "Table vs ML" comparison chart on Page 3.

---

## Key Files to Read Before Starting

| File | Why |
|---|---|
| `CLAUDE.md` | Full project conventions, typing rules, naming |
| `ARCHITECTURE.md` | Data flow: InforceBlock → AssumptionSet → Product → Treaty → Analytics |
| `docs/DECISIONS.md` | ADR-036 (cession override), ADR-034 (ML protocol), ADR-032 (dashboard excluded from coverage) |
| `src/polaris_re/dashboard/app.py` | Current implementation — reuse chart helpers |
| `src/polaris_re/assumptions/mortality.py` | `MortalityTable.load()` and `_SOURCE_CONFIG` |
| `src/polaris_re/assumptions/ml_mortality.py` | ML assumption interface |
| `src/polaris_re/core/inforce.py` | `InforceBlock.from_csv()`, `effective_cession_vec()` |
| `scripts/generate_synthetic_block.py` | Synthetic block generation logic to reuse |
| `tests/fixtures/` | Synthetic CSV fixtures for testing |

---

## Testing Notes

- Dashboard code is excluded from pytest coverage (ADR-032). Visual testing only.
- However, any new helper functions in `components/charts.py` or `components/state.py`
  that contain business logic should be testable and covered.
- Test the full workflow: upload synthetic block → select SOA VBT 2015 → price with
  YRT → run scenarios → run UQ. Verify that changing lapse rate from 5% to 15%
  produces a visible change in PV profits and margin (the flat-rate degeneracy bug).

---

## Open Questions for Developer

1. **Plotly vs Matplotlib:** The current charts use matplotlib. Plotly integrates
   better with Streamlit (native `st.plotly_chart` with hover tooltips, zoom, etc.).
   Consider migrating charts to Plotly for the rebuild. Decision: developer's choice,
   but if using Plotly, add `plotly>=5.20` to the `[dashboard]` optional extra.

2. **Real-time vs button-click:** The current "Run Pricing" button pattern requires
   re-clicking after every parameter change. Consider using `st.session_state`
   callbacks or `st.form` to auto-run on parameter change for lightweight operations
   (assumption loading, demographic charts) while keeping the button for expensive
   operations (full projection, Monte Carlo).

3. **File paths in Codespaces:** The dashboard needs access to `data/mortality_tables/`
   and `data/lapse_tables/`. In Codespaces, `POLARIS_DATA_DIR` is set to
   `/workspaces/polaris-re/data`. Ensure file pickers default to this path.
