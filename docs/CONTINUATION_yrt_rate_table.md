# Continuation: Tabular YRT Rate Schedule (Age × Sex × Smoker × Duration)

**Source:** PRODUCT_DIRECTION_2026-04-19.md — IMPORTANT (last item in
the IMPORTANT list, "YRT rate schedule by age × duration")
**Status:** IN PROGRESS — Slice 4a shipped 2026-04-30; Slice 4b
(dashboard upload + heatmap + per-duration solver) PLANNED
**Total slices:** 5 (re-decomposed: Slice 3 split into 3/4 in the
prior session; Slice 4 split into 4a/4b in this session because the
dashboard work is materially different in scope from the CLI flag)
**Estimated total scope:** ~5 dev-days

## Overall Goal

Replace the single-cell `YRTTreaty.flat_yrt_rate_per_1000` approximation
with a tabular YRT rate schedule indexed by (attained_age, sex,
smoker_status, duration_in_years). Production YRT treaties bill
premiums from such a table; the flat-rate approximation
systematically understates reinsurer cost on aging blocks (per the
PRODUCT_DIRECTION 2026-04-19 WL YRT analysis, which observed
declining ceded premium against rising attained-age claims). When this
feature is complete, the engine will price tabular-YRT deals end-to-end:
treaty consumption (Slice 2), schedule generation via brentq solver
(Slice 2), and CLI / API / Excel surfaces (Slice 3).

## Decomposition

### Slice 1: Standalone `YRTRateTable` data model
- **Status:** DONE (this session, 2026-04-27)
- **Branch:** `claude/lucid-hawking-FDgDd`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `src/polaris_re/reinsurance/yrt_rate_table.py` with two
    public symbols: `YRTRateTableArray` (storage class — 2-D float64
    array per (sex, smoker), shape `(n_ages, select_period + 1)`,
    indexed by `[age - min_age, min(duration_years, select_period)]`)
    and `YRTRateTable` (frozen Pydantic model wrapping the arrays
    keyed by `f"{sex.value}_{smoker.value}"`, with smoker-fallback to
    `UNKNOWN`).
  - Storage layout, validation, and lookup contract mirror
    `MortalityTable` / `MortalityTableArray`. Two intentional
    differences: (i) no upper bound on rate values (YRT rates routinely
    exceed `$50/$1,000` at advanced ages, where mortality probabilities
    are bounded at 1.0), and (ii) the rate is annual dollars per
    `$1,000` NAR, not a probability — consumers convert to monthly
    per-dollar form via `/12 / 1000` at the call site.
  - `reinsurance/__init__.py` re-exports `YRTRateTable` and
    `YRTRateTableArray` (alphabetised `__all__`).
  - ADR-050 added to `docs/DECISIONS.md`.
  - 34 tests added in `tests/test_reinsurance/test_yrt_rate_table.py`:
    `TestYRTRateTableArrayConstruction` (8),
    `TestYRTRateTableArrayLookup` (11),
    `TestYRTRateTableConstruction` (6),
    `TestYRTRateTableLookup` (7),
    `TestPublicExports` (2).
  - Full suite is now 827 non-slow (up from 793); QA suite unchanged
    at 33/33; golden baselines unchanged because the new module is not
    yet referenced by any existing pricing path.
- **Acceptance criteria:**
  - New module importable as `from polaris_re.reinsurance import
    YRTRateTable, YRTRateTableArray`. ✅
  - Closed-form scalar lookup matches the
    `base_rate + age_slope*i + duration_slope*j` formula on the
    synthetic fixture. ✅
  - Vector lookup matches scalar lookup element-wise. ✅
  - Smoker rates strictly higher than non-smoker rates at every cell
    in the synthetic fixture (economic invariant). ✅
  - Duration beyond `select_period` clamps to the ultimate column. ✅
  - Smoker-specific lookup falls back to aggregate (`UNKNOWN`) when
    no smoker-specific array is loaded. ✅
  - Negative / NaN / inconsistent-shape inputs raise
    `PolarisValidationError` at construction. ✅
  - Existing 793 non-slow tests still pass (purely additive slice). ✅
  - ADR-050 written. ✅
- **Key decisions that affect later slices:**
  - **Annual rate, dollars per `$1,000` NAR.** Slice 2 must convert
    via `monthly_per_dollar = annual_per_1000 / 12 / 1000` to match
    the existing flat-rate calculation in `YRTTreaty.apply`.
  - **`YRTTreaty` is unchanged.** Slice 2 adds the
    `yrt_rate_table: YRTRateTable | None = None` field to `YRTTreaty`
    and the consumption logic in `apply()`. Default `None` preserves
    backward compat with the flat-rate path.
  - **Storage shape is `(n_ages, select_period + 1)`.** Slice 2's
    consumption logic must compute `duration_years_t = duration_inforce
    // 12 + t // 12` per policy and per time step, then call
    `get_rate_vector(ages_t, sex, smoker, durations_years_t)` for
    each (sex, smoker) cohort. The clamping to `select_period` happens
    inside the array.
  - **Per-(sex, smoker) keying.** The `YRTTreaty.apply` consumer
    must split the inforce by (sex, smoker) before looking up rates,
    since the lookup signature accepts a single `sex` and `smoker`
    per call. This split is a one-time grouping at the start of
    `apply()` — vectorised within each cohort.
  - **No CSV loader yet.** All Slice 1 construction goes through
    `from_arrays(...)` with in-memory arrays. Slice 3 will add
    `YRTRateTable.load(path)` mirroring `MortalityTable.load(...)`,
    along with a CSV format spec written into `utils/table_io.py`.

### Slice 2: Wire `YRTRateTable` into `YRTTreaty.apply()`
- **Status:** DONE (this session, 2026-04-28)
- **Branch:** `claude/lucid-hawking-YY49U`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `yrt_rate_table: YRTRateTable | None = None` field to
    `YRTTreaty` and a `model_validator` that raises
    `PolarisValidationError` when both `flat_yrt_rate_per_1000` and
    `yrt_rate_table` are set (mutual-exclusion was RESOLVED in PR #36
    review — Open Question 2 in this file).
  - Extended `YRTTreaty.apply()` with a tabular branch:
    `_compute_tabular_premiums` → seriatim path
    (`_tabular_premiums_seriatim`) when `gross.seriatim_lx` and
    `gross.seriatim_reserves` are populated, otherwise fallback path
    (`_tabular_premiums_aggregate`) using a face-weighted average
    rate against the existing aggregate-runoff NAR. Inforce is split
    by (sex, smoker) cohort once at the start of `apply()` (mirrors
    `TermLife._build_rate_arrays`). Per-policy effective cession
    comes from `InforceBlock.effective_cession_vec(treaty_default)`
    (ADR-036 compatible). Ages outside the table range are clipped
    to `[min_age, max_age]`.
  - Tabular path requires `inforce`; when set with `inforce=None`,
    raises `PolarisComputationError` naming `InforceBlock`.
  - Existing flat-rate logic moved into `_compute_flat_premiums` —
    the path is byte-identical to the previous implementation.
  - Added `YRTRateSchedule.generate_table(...)` that solves the
    per-(age, sex, smoker) flat rate via the existing brentq solver
    and packs the result into a `YRTRateTable` with rates
    broadcast across the requested select columns. This is the
    closed-loop sanity check; a true per-duration solver is deferred
    to Slice 3.
  - ADR-051 added to `docs/DECISIONS.md`.
  - 12 new tests in `tests/test_reinsurance/test_yrt_tabular.py`
    (validation, flat-path-unchanged, constant-table-matches-flat,
    aging-vs-flat counterfactual, implied-rate monotonicity,
    seriatim-vs-aggregate fallback, smoker fallback to UNKNOWN).
  - 2 new tests in `tests/test_analytics/test_rate_schedule.py`
    (`TestGenerateTable`: returns populated `YRTRateTable`; round-
    trip through `YRTTreaty.apply()` produces a finite, non-zero
    ceded premium series).
  - Full suite is now 847 non-slow (up from 833); QA suite unchanged
    at 33/33; QA golden YRT and golden flat regressions both pass
    byte-identically because the tabular branch is opt-in.
- **Acceptance criteria:**
  - `YRTTreaty(..., yrt_rate_table=t).apply(gross, inforce)` returns
    a valid `(net, ceded)` tuple with non-zero ceded premiums. ✅
  - Tabular ceded premium under an aging table is strictly greater
    than under a flat table at the same year-1 rate (the
    PRODUCT_DIRECTION_2026-04-19 declining-premium concern is
    fixed); the implied per-$1,000 rate (back-solved from prem /
    NAR) rises monotonically across early policy years. ✅
  - Constant-rate table reproduces the flat-rate output within
    `1e-6` relative tolerance. ✅
  - Existing QA goldens unchanged (the flat-rate path is untouched
    by the tabular branch). ✅
  - `YRTRateSchedule.generate_table(...)` returns a populated
    `YRTRateTable` whose round-trip through the treaty produces a
    finite, non-zero ceded premium series. ✅
  - ADR-051 written. ✅
- **Key decisions that affect Slice 3:**
  - **Seriatim is the default consumption path.** When gross was
    produced with `project(seriatim=True)`, per-policy `lx[i, t]`
    and per-policy reserves `V[i, t]` drive the premium calculation
    exactly. When seriatim is absent, the engine falls back to a
    face-weighted average rate against aggregate-runoff NAR. Slice 3
    should likely flip the CLI demo flows to seriatim when a tabular
    table is supplied, so the PRODUCT_DIRECTION concern is fully
    resolved end-to-end.
  - **`generate_table()` is age-flat across duration columns.** The
    Slice 2 implementation broadcasts the per-age flat rate into
    every duration column. A real per-duration solver (and a CSV
    schema that supports duration-specific columns) is the natural
    Slice 3 follow-on alongside the CLI / API surfaces.
  - **NAR series carried on the ceded result is in-force-weighted**
    in the seriatim path (`(lx * NAR_per_policy).sum(axis=0)`) so it
    matches the basis on which the rates were applied. The flat
    path's NAR series is unchanged. Slice 3's Excel / dashboard
    surfaces should display the seriatim NAR series when tabular
    rates are used.

### Slice 3: CSV loader + CLI / API / Excel surfacing
- **Status:** DONE (this session, 2026-04-29)
- **Branch:** `claude/lucid-hawking-Gb00h`
- **PR:** (draft; opened by this session)
- **What was done:**
  - `src/polaris_re/utils/table_io.py` — `load_yrt_rate_csv(path,
    select_period, ...)` parser mirroring `load_mortality_csv`. The
    YRT loader does NOT enforce the `[0, 1]` rate cap (rates are
    $/$1,000 NAR, not probabilities); the non-negative + finite
    checks are delegated to `YRTRateTableArray.__init__`. Module
    docstring extended with the YRT CSV schema. New symbol
    re-exported from `__all__`.
  - `YRTRateTable.load(directory, select_period, table_name, ...)`
    classmethod added to `reinsurance/yrt_rate_table.py`. Mirrors
    `MortalityTable.load` — iterates over (sex × smoker) cohorts,
    formats per-cohort filenames via a `file_pattern` template
    (default `{label}_{sex}_{smoker}.csv`), and packs the result
    through `YRTRateTable.from_arrays`. Smoker-distinct and
    aggregate-only modes are both supported.
  - CLI: `polaris price --yrt-rate-table DIR` plus three tuning
    flags (`--yrt-rate-table-select-period`,
    `--yrt-rate-table-label`,
    `--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate`).
    When set: load the table once, force `seriatim=True` on the
    gross projection, force `inforce` to be passed to
    `YRTTreaty.apply()`, and construct `YRTTreaty` directly with
    `yrt_rate_table=...` so the existing `build_treaty` factory's
    flat-rate path is bypassed.
  - API: `PriceRequest.yrt_rate_table_path: str | None` field
    plus the same three tuning fields. The path is resolved
    server-side relative to `POLARIS_DATA_DIR`, with rejection of
    `..` traversal (HTTP 400) and missing-directory (HTTP 404).
    `_run_gross_projection` now accepts `seriatim`. The legacy
    per-policy `reinsurance_cession_pct=0.0` hardcoded by
    `_build_components` was switched to `None` so the tabular
    seriatim path falls back to the request-level `cession_pct`
    (the flat path never observed this default since it didn't
    pass `inforce` to `apply()`); all 38 existing API tests pass
    byte-identically.
  - Excel: optional `YRT Rate Table` sheet appended to the
    deal-pricing workbook when `DealPricingExport.yrt_rate_table`
    is populated. One block per (sex, smoker) cohort, rendered as
    `[age, dur_1, ..., dur_N, ultimate]`. Workbook is byte-
    identical to pre-Slice-3 when the table is None.
  - Sample fixtures in `tests/fixtures/yrt_rate_tables/` (M/F × NS/SM,
    ages 25-35) for the loader tests; CLI / API tests build their
    own larger fixtures in `tmp_path`.
  - ADR-052 added to `docs/DECISIONS.md`.
  - 44 new tests (26 loader + 7 CLI + 7 API + 4 Excel). Full suite
    is now 892 non-slow (up from 848); QA suite unchanged at 33/33.

- **Acceptance criteria:**
  - `from polaris_re.utils.table_io import load_yrt_rate_csv`
    parses the four shipped fixtures into a `YRTRateTableArray`. ✅
  - `YRTRateTable.load(...)` builds a four-cohort table from the
    fixtures directory and round-trips through `YRTTreaty.apply()`. ✅
  - `polaris price --yrt-rate-table` runs the demo and produces a
    non-zero reinsurer view (verified with custom inforce CSV
    overriding the demo's `reinsurance_cession_pct=0.00` quirk). ✅
  - API `POST /api/v1/price` with `yrt_rate_table_path` returns 200
    and a non-zero reinsurer pv_profits. ✅
  - API rejects path-traversal with HTTP 400 / 422. ✅
  - Deal-pricing Excel workbook gains a `YRT Rate Table` sheet
    when tabular rates were used. ✅
  - All 848 pre-existing non-slow tests still pass. ✅
  - ADR-052 written. ✅

- **Key decisions that affect Slice 4:**
  - **CSV schema is locked** at `age,dur_1,...,dur_N,ultimate`
    with the 1-based user-facing `dur_k` column convention
    (matches `load_mortality_csv`). Slice 4's dashboard
    file-uploader and `polaris rate-schedule --table` should
    consume the same schema verbatim.
  - **API path-resolution gates on `POLARIS_DATA_DIR`.** Slice 4's
    dashboard uploader will need a different code path because the
    file lives in browser-uploaded memory, not on the server's data
    directory. Use `YRTRateTable.from_arrays(...)` after parsing
    the uploaded CSV bytes in-process.
  - **Default per-policy cession on the API is now `None`.** This
    is now the canonical default; Slice 4 / future API additions
    must not regress to `0.0` (would break the tabular path again).

### Slice 4a: `polaris rate-schedule --table` flag + standalone Excel writer
- **Status:** DONE (this session, 2026-04-30)
- **Branch:** `claude/lucid-hawking-4aujD`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `--table/--no-table` and `--select-period N` flags to
    `polaris rate-schedule`. When `--table` is set, the command
    calls `YRTRateSchedule.generate_table(...)` instead of
    `generate(...)` and renders one Rich `Table` per cohort
    (sorted by cohort key) with rates formatted as `{:.4f}`.
  - Added `write_yrt_rate_table_excel(table, path)` to
    `src/polaris_re/utils/excel_output.py`. Internally delegates the
    rate-grid block to the existing `_write_yrt_rate_table_sheet`
    helper so the workbook is byte-identical to the deal-pricing
    workbook's appended sheet (ADR-052). A `Summary` sheet is added
    in front carrying the table name, age range, select-period,
    cohort count, and total rate-cell count.
  - `-o NAME.xlsx` writes via the new function. `-o NAME.csv` is
    rejected with exit code 1 because CSV does not preserve the
    cohort-keyed 2-D layout. `--json PATH` emits a structured dict
    (`table_name` / `min_age` / `max_age` / `select_period_years` /
    `cohorts` map keyed by `f"{sex}_{smoker}"`) via the new
    `_yrt_rate_table_to_dict` helper that round-trips through
    `json.dumps`.
  - ADR-053 added to `docs/DECISIONS.md`.
  - 8 new fast tests + 5 new slow tests:
    - `tests/test_utils/test_excel_output.py::TestWriteYrtRateTableExcel`
      (5 fast) — workbook created, has Summary + YRT Rate Table
      sheets, Summary carries cohort count + table name, rate
      values appear, default empty Sheet removed.
    - `tests/test_analytics/test_cli_rate_schedule_table.py`
      `TestYrtRateTableJsonHelper` (3 fast) — top-level shape,
      cohort dict round-trip, JSON-serialisable.
    - `tests/test_analytics/test_cli_rate_schedule_table.py`
      `TestRateScheduleTableCLI` (5 slow) — flat path
      backward-compat, `--table -o .xlsx` emits workbook,
      `--table -o .csv` rejected with exit 1, `--table --json`
      emits cohort dict, `--select-period N` produces N+1 columns
      and the per-row rate is constant (broadcast — ADR-051 "Out
      of scope" until per-duration solver lands in Slice 4b).
  - Full suite is now 886 non-slow (up from 878); QA suite
    unchanged at 33/33; golden flat regression byte-identical
    (numbers unchanged).
- **Acceptance criteria:**
  - `polaris rate-schedule --table -o out.xlsx` writes a workbook
    with both `Summary` and `YRT Rate Table` sheets. ✅
  - `polaris rate-schedule --table -o out.csv` exits 1 with a
    user-facing message pointing to `.xlsx`. ✅
  - `polaris rate-schedule --table --json out.json` writes the
    cohort dict shape per ADR-053. ✅
  - `polaris rate-schedule` (no flag) is byte-identical to the
    pre-Slice-4a behaviour. ✅
  - `--select-period N` produces `N+1` duration columns per cohort
    (rates broadcast across columns until the per-duration solver
    lands in Slice 4b). ✅
  - Existing `TestYRTRateSchedule` / `TestExcelOutput` /
    `TestGenerateTable` / `TestYRTRateTableSheet` tests remain
    green unchanged. ✅
  - ADR-053 written. ✅
- **Key decisions that affect Slice 4b:**
  - **`write_yrt_rate_table_excel` is the canonical writer.** Slice
    4b's dashboard download button can call it directly (after
    parsing the uploaded CSV bytes via
    `YRTRateTable.from_arrays`). No duplication needed.
  - **`_yrt_rate_table_to_dict`** is the canonical JSON helper.
    Slice 4b can reuse it to emit the loaded table to the browser
    (e.g. as a `st.json` preview) without duplicating the
    serialisation logic. Both helpers live in `cli.py` for now;
    if Slice 4b needs them outside the CLI, lift them into
    `utils/yrt_rate_table_io.py` (or extend `utils/table_io.py`).
  - **Console rendering uses one Rich `Table` per cohort.** Slice
    4b's heatmap can mirror this layout (one matplotlib axis per
    cohort) so the visual mental model is consistent.
  - **Per-duration solver is still deferred.** The current
    broadcast-along-rows behaviour is documented in ADR-053
    "Out of scope" and is the same as ADR-051. Slice 4b's heatmap
    will be visually flat-along-rows until this lands; an interim
    note in the dashboard caption is acceptable.

### Slice 4b: Dashboard file-uploader + heatmap (+ optional per-duration solver)
- **Status:** PLANNED
- **Depends on:** Slice 4a merged
- **Scope:**
  - Streamlit dashboard pricing page: file-uploader for the rate
    table directory or zip; render a heatmap preview of the loaded
    grid (matplotlib `imshow` per cohort), backed by either the
    uploaded payload or a server-side path.
  - Choose UX between (a) zip-only, (b) one-file-per-cohort with a
    form selector, or (c) a single multi-cohort CSV with
    `sex` / `smoker` columns. ADR-052 deliberately left this open;
    Slice 4b's ADR-054 documents the pick.
  - Optional: a true per-duration solver in
    `YRTRateSchedule.generate_table()` (currently broadcasts the
    per-age flat rate across every duration column).
  - Wire the loaded table through the dashboard pricing flow so
    users can run a deal end-to-end with an uploaded table.
  - **Fix `generate_table()` fill-in transparency.** The current
    implementation expands the solved age grid to a contiguous
    `[min_age, max_age]` array and forward/back-fills unsolved rows
    silently. `_render_yrt_rate_table` renders filled rows
    identically to solved rows, so a reviewer cannot distinguish
    brentq-solved rates from interpolated fill-in (observed on
    `--ages 30,40 --select-period 3`: ages 31–39 all show 1.8365,
    a flat extrapolation from age 30). ADR-054 must pick one of:
    (a) mark filled rows in the console/Excel output with a visual
    flag, or (b) restrict the generated table's age range to only
    the requested ages and let consumption-side clipping handle
    out-of-range lookup. The current behaviour must not be
    presented as a production deliverable without disclosure. See
    PR #39 review (Comment 5) for the full discussion.

## Context for Next Session

- **`write_yrt_rate_table_excel` is the canonical writer for Slice 4b.**
  The dashboard download button should call it directly after parsing
  uploaded CSV bytes in-process via `YRTRateTable.from_arrays(...)`. No
  duplication needed.
- **`_yrt_rate_table_to_dict` lives in `cli.py` for now.** If Slice 4b's
  dashboard preview needs the JSON helper, lift it (and
  `_render_yrt_rate_table`) into `utils/yrt_rate_table_io.py` before
  introducing a second call site.
- **Dashboard upload UX is the primary ADR-054 decision.** Streamlit
  `st.file_uploader` does not natively accept directories; choose one of:
  (a) zip upload unzipped in-process, (b) per-cohort multi-file selector,
  (c) single multi-cohort CSV with `sex`/`smoker` columns. The ADR-052
  CSV schema is locked at `age,dur_1,...,dur_N,ultimate` per cohort file;
  option (c) would require a new format and a new loader.
- **`generate_table()` fill-in transparency must be resolved before the
  CLI output can be used as a deliverable.** See Slice 4b scope above and
  ADR-053 "Out of scope". The fix is either visual disclosure (Option A)
  or restricting the table to requested ages (Option B); the trade-off
  is whether to preserve the contiguous storage model or adjust the
  consumption-side clipping assumption.
- **Per-duration solver is still deferred.** The heatmap in Slice 4b will
  be visually flat-along-rows (broadcast from generate_table). An interim
  caption — "Rates are age-banded; per-duration variation requires a
  CSV-loaded table" — is acceptable for the Slice 4b dashboard.
- **Column-width fix landed in PR #39 (Slice 4a P1 review).**
  `_write_yrt_rate_table_sheet` now uses
  `openpyxl.utils.get_column_letter(col_offset + 2)` instead of
  `chr(ord("B") + col_offset)`, so wide select periods (>= 25) render
  correctly. Slice 4b's per-duration solver will commonly produce
  longer select periods — no further action needed here.

## Open Questions (for human) — all resolved as of Slice 4a

1. **Slice 2 per-policy inforce projection: seriatim vs aggregate
   approximation?**
   **RESOLVED — seriatim default with aggregate fallback, ADR-051
   (2026-04-28).** Seriatim is the default when `gross.seriatim_lx`
   and `gross.seriatim_reserves` are populated; aggregate
   face-weighted fallback when they are absent. The CLI forces
   `seriatim=True` for any tabular run (Slice 3, ADR-052), so the
   degraded aggregate path is not reachable from the standard user
   workflow.
2. **Precedence when both `flat_yrt_rate_per_1000` and
   `yrt_rate_table` are set on the same `YRTTreaty`?**
   **RESOLVED — raise `PolarisValidationError` if both are set**
   (PR #36 reviewer, 2026-04-27). The reviewer flagged that
   silent table-wins could mask a copy-paste error in deal
   configuration, so Slice 2 enforces mutual exclusion at
   `YRTTreaty` model-validator time. ADR-051 documents the choice.
3. **CSV format for the YRT rate table** (Slice 3).
   **RESOLVED — one file per (sex, smoker), schema locked in
   ADR-052 (2026-04-29).** `age,dur_1,...,dur_N,ultimate` per
   cohort file, mirroring the mortality CSV convention.
4. **`YRTRateSchedule.generate_table(...)` axis grid.**
   **RESOLVED — ADR-051/053 (2026-04-28/30).** `generate_table()`
   defaults to ages 25..85 step 5, both sexes, both smoker statuses,
   `select_period_years=0`. The CLI `--ages` flag overrides the age
   list and `--select-period` overrides the select period. Note: the
   `polaris rate-schedule --ages` CLI default (25,30,...,65) is the
   demo subset — intentionally narrower than the `generate_table()`
   full grid (25..85). Both are configurable.

When all slices are DONE, update Status to COMPLETE. With Slice 4a
shipped, the actuary-deliverable production path is complete: a
tabular schedule can be generated end-to-end from
`polaris rate-schedule --table` and consumed via `polaris price
--yrt-rate-table` (Slice 3). Slice 4b (dashboard upload + heatmap +
optional per-duration solver) remains.
