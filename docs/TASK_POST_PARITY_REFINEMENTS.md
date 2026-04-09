# Task: Post-Parity Refinements (Follow-up to CLI/Streamlit Alignment)

> **Parent PR:** #18 (CLI/Streamlit parity via shared pipeline builder)
> **Status:** Ready for follow-up PR after #18 merges
> **Priority order:** Items are listed roughly by user-impact / effort ratio.

---

## Context

PR #18 achieved numerical parity between the CLI and Streamlit dashboard by
extracting a shared pipeline builder (`core/pipeline.py`), wiring real SOA
VBT 2015 mortality into the CLI, sharing the default lapse curve, and fixing
the cession slider and valuation date handling. The two paths now produce
identical results on the same inputs.

This document captures refinements identified during parity validation that
were deferred to keep PR #18 focused on the core correctness fix.

---

## 1. Parity Debug Dump Not Writing Files

**Symptom:** `POLARIS_PARITY_DEBUG=1` produces `[parity-debug]` messages on
stderr but no CSV files appear in `/tmp/`.

**Root cause:** The code writes to `data/outputs/parity/` (a relative path
resolved from the working directory), not `/tmp/`. The instructions given to
the user referenced `/tmp/` incorrectly. Additionally, the Streamlit process
may have a different working directory than expected.

**Fix (small):**
- Use an absolute path: `Path(os.environ.get("POLARIS_PARITY_OUTPUT", "data/outputs/parity"))`.
  This lets the user override the output location and makes the path
  discoverable.
- Print the **absolute** resolved path in the stderr message so the user can
  always find the files regardless of working directory.
- Add a note in the CLI `--help` text documenting the env var.

**Effort:** ~30 minutes.

---

## 2. Product Type Dropdown — UX Signposting

**Current state:** The "Product Type" dropdown on the Assumptions page stores
a value in `deal_config["product_type"]`, but `get_product_engine()` determines
the actual engine from `inforce.policies[0].product_type` — the dropdown is
effectively cosmetic when an inforce CSV is loaded.

**Problem:** A user could select "Term Life" in the dropdown but load a CSV of
whole-life policies. The projection would correctly use WL, but the UI would
misleadingly display "Term Life" as the configured product type on the Pricing
page summary metrics row.

**Proposed fix (medium):**
1. When an inforce block is loaded, **auto-detect** the product type from
   `inforce.policies[0].product_type` and update the dropdown to match.
   Display a read-only info banner: *"Product type detected from inforce:
   Whole Life (2 policies)"*.
2. Make the dropdown **editable only on the synthetic-block path** (when no
   CSV is loaded and the user is configuring a generated block). In this mode
   it acts as the product type for synthetic policy generation.
3. If the dropdown value conflicts with loaded inforce data, show a warning:
   *"Product type override ignored — inforce block contains WHOLE_LIFE
   policies."*

**Design principle:** Inputs that are determined by data should be read-only
when data is loaded; inputs that are free choices should be editable. The
Product Type dropdown should clearly indicate which mode it is in.

**Effort:** ~2 hours.

---

## 3. Projection Horizon — Per-Policy vs Global

**Current state:** A single "Projection Horizon (years)" slider (5–30, default
20) applies uniformly to all policies. This is actuarially questionable:

- **Term policies** should project for at most `policy_term - duration_inforce`
  remaining years.
- **Whole life** should project to omega (age 121) minus current age, which
  varies per policy.
- **UL** should project to the later of maturity date and account-value
  exhaustion.

**Problem:** A 30-year global horizon applied to a Term-20 policy that has
been inforce for 5 years projects 15 years of zeros after the term expires.
For whole-life, 30 years may truncate a 49-year-old's projection too early
(should run ~72 years to age 121).

**Proposed design:**
1. **Policy-level projection term** — derive from `(product_type, issue_age,
   policy_term, current_duration)` per policy:
   - Term: `remaining = policy_term - duration_inforce_years`
   - WL: `remaining = (omega - current_age)`, omega = 121
   - UL: `remaining = max(maturity_term, account_value_runoff_estimate)`
2. The **global slider becomes a cap** rather than the term:
   *"Maximum projection horizon (years)"* — no policy projects beyond this,
   but policies with shorter remaining terms stop naturally.
3. On the **synthetic block path** (no CSV loaded), the slider remains the
   actual projection term since there's no policy-level data to derive from.
4. Display the effective projection range in the UI: *"Projecting 2 policies:
   30 years (WL to age 121), 15 years (Term-20, 5 years inforce)"*.

**Implementation notes:**
- This requires changes to `ProjectionConfig` to support per-policy horizons,
  or (simpler) the projection engines need to respect each policy's natural
  term even when the global horizon is longer. The engines already partly do
  this — `TermLife` zeros out cash flows after term expiry — but the arrays
  are still allocated to the full global horizon length.
- The WL truncation at 30 years is the most immediately visible issue.
  Consider raising the WL default to 50+ years or computing it from the
  inforce block.

**Effort:** ~4–6 hours (touches projection engines + UI + config).

**Recommendation:** This is a significant modeling change. Implement in two
stages:
  - **Stage A (quick win):** Auto-compute a sensible default from the loaded
    inforce block (e.g. `max(omega - min_age, max_remaining_term)`) and
    pre-populate the slider. Keep the slider editable as an override.
  - **Stage B (full):** Per-policy projection horizons in the engine.

---

## 4. Valuation Date — UI Override with Fallback Chain

**Current state (after PR #18):** The dashboard uses the first policy's
`valuation_date` from the loaded inforce block, falling back to `date.today()`
when no block is loaded. There is no UI input for the valuation date.

**Proposed design:**
1. Add a **date picker** widget on the Assumptions page (or in the top
   config bar).
2. **Fallback chain:** UI override > policy-level valuation date > today.
3. When an inforce block is loaded, pre-populate the date picker with the
   block's valuation date and show an info message: *"Valuation date set from
   inforce: 2026-04-06"*.
4. If the user changes the date picker, display a warning: *"Overriding
   policy valuation date (2026-04-06) with manual date (2026-04-09). All
   durations will be recalculated."*

**Design question:** Does changing the valuation date require recalculating
`duration_inforce` for each policy? Currently `duration_inforce` is a fixed
field on the policy record. If the valuation date changes, conceptually the
duration should change too — but the CSV has the duration baked in. For now
the simplest approach is: valuation date override only affects the projection
start point and discount factors, not policy durations. Document this
limitation.

**Impact on policy-level valuation dates:** The `InforceBlock` model validator
already enforces that all policies share the same `valuation_date`. Supporting
per-policy valuation dates would require relaxing this constraint and would be
a much larger change (each policy's projection would start at a different
point). This is out of scope — note as a future enhancement.

**Effort:** ~1–2 hours for the date picker + fallback logic.

---

## 5. Remaining Task Doc Items Not Yet Addressed

These items from `TASK_CLI_STREAMLIT_PARITY.md` were noted as in-scope but
are lower priority now that numerical parity is achieved:

### 5a. ML Mortality / Lapse Model Loading in CLI

The dashboard exposes `ml_mortality_model` and `ml_lapse_model` session
state keys for scikit-learn/XGBoost model overlays. The CLI has no equivalent
config surface. Add `ml_mortality_path` and `ml_lapse_path` fields to
`MortalityConfig` and `LapseConfig` respectively, loading joblib models when
specified.

**Effort:** ~3 hours. Needs its own ADR for the joblib-over-CLI UX.

### 5b. Mortality Improvement in CLI

The dashboard supports mortality improvement scales (Scale AA, MP-2020,
CPM-B). The CLI config schema has no field for this. Add
`improvement_scale` to `MortalityConfig` and wire through `build_assumption_set`.

**Effort:** ~1 hour.

### 5c. YAML Config Support

The CLI currently only accepts JSON configs. YAML is more human-friendly for
hand-editing. Add optional YAML parsing (detect by file extension).

**Effort:** ~1 hour.

### 5d. `polaris ifrs17` CLI Command

The dashboard's IFRS 17 BBA page has no CLI equivalent. Expose as a new
subcommand once parity is proven stable.

**Effort:** ~4 hours.

### 5e. Tighter Acceptance Tolerance

The parity test currently uses +-$1.5M bands. Once the pipeline is stable,
tighten to +-$250K as specified in the original task doc's acceptance
criteria (criterion 2).

**Effort:** ~30 minutes (just adjusting test bounds).

---

## 6. Minor Polish

### 6a. Debug Dump Gitignore

`data/outputs/` should be gitignored (it currently is via the top-level
`data/` ignore). Confirm that `data/outputs/parity/*.csv` files don't
accidentally get committed.

### 6b. CLI Demo Mode Discoverability

`polaris price` with no arguments uses `data/configs/demo.json` +
`data/inputs/demo.csv`. This should be documented in `--help` and in the
README's quickstart section.

### 6c. Treaty Name Convention

CLI uses treaty names like `"YRT-CLI"`, `"COINS-CLI"`, `"MODCO-CLI"` while
the dashboard uses `"YRT"`, `"Coinsurance"`, `"ModCo"`. These should be
unified — the treaty name appears in output metadata and should be consistent
regardless of entry point.

---

## Recommended PR Sequence

1. **PR A (quick wins):** Items 1, 2, 6a–6c — debug dump path fix, product
   type signposting, minor polish. ~Half day.
2. **PR B (valuation date):** Item 4 — date picker with fallback chain. ~1–2
   hours.
3. **PR C (projection horizon):** Item 3 Stage A — auto-compute default from
   inforce. ~2–3 hours.
4. **PR D (CLI feature parity):** Items 5a, 5b, 5c — ML models, improvement
   scales, YAML. ~1 day.
5. **PR E (projection horizon full):** Item 3 Stage B — per-policy horizons.
   Larger effort, depends on engine changes.
6. **PR F (IFRS 17 CLI):** Item 5d — new subcommand.
