# Continuation: Tabular YRT Rate Schedule (Age × Sex × Smoker × Duration)

**Source:** PRODUCT_DIRECTION_2026-04-19.md — IMPORTANT (last item in
the IMPORTANT list, "YRT rate schedule by age × duration")
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~4 dev-days

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
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:**
  - `src/polaris_re/reinsurance/yrt.py` — add `yrt_rate_table:
    YRTRateTable | None = None` field. In `apply()`, when
    `yrt_rate_table` is set AND `inforce` is provided, compute
    per-policy YRT premiums using the table; otherwise fall back to
    the existing flat-rate logic. Add a clear precedence rule when
    both `flat_yrt_rate_per_1000` and `yrt_rate_table` are set
    (proposal: prefer the table; raise `PolarisValidationError` only
    if neither is set AND ceded premiums are requested).
  - `src/polaris_re/analytics/rate_schedule.py` — extend
    `YRTRateSchedule` to optionally solve a per-(age, duration) rate
    grid (the natural follow-on once the treaty consumes it). One
    option: add `generate_table(...)` that returns a `YRTRateTable`
    constructed from the brentq-solved cells.
- **Tests to add:**
  - Closed-form: with a constant-rate `YRTRateTable`, ceded premiums
    must match the flat-rate path within float tolerance (regression
    against the existing flat-rate calculation).
  - Age progression: with the synthetic age-increasing rate fixture,
    ceded premiums must rise monotonically with attained age over the
    block lifetime.
  - Additivity: `net + ceded == gross` for premiums and claims under
    tabular rates (same invariant as flat-rate YRT).
  - Backward compat: existing `flat_yrt_rate_per_1000` calls produce
    byte-identical output (no regression on QA goldens).
  - Validation: `apply()` with `yrt_rate_table` set but `inforce=None`
    raises a clear error explaining that tabular rates need policy-
    level ages.
- **Acceptance criteria:**
  - `YRTTreaty(..., yrt_rate_table=t).apply(gross, inforce)` returns a
    valid `(net, ceded)` tuple with non-zero ceded premiums.
  - Tabular ceded premium curve rises with attained age for an
    age-increasing rate fixture (the limitation called out in
    PRODUCT_DIRECTION_2026-04-19 is fixed).
  - Constant-rate table produces output equal to the equivalent
    flat-rate call within float tolerance.
  - Existing QA goldens unchanged (flat-rate path is untouched).
  - `YRTRateSchedule.generate_table(...)` returns a populated
    `YRTRateTable` whose round-trip back through the treaty
    reproduces the target IRR within tolerance (closed-loop check).
  - ADR-051 written.

### Slice 3: CLI / API / Excel / dashboard surfacing + CSV loader
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:**
  - `src/polaris_re/utils/table_io.py` — `load_yrt_rate_csv(path)`
    parser mirroring `load_mortality_csv` with the same schema (age
    column, dur_1..dur_N, ultimate). Filename convention
    `{label}_{sex}_{smoker}.csv`.
  - `YRTRateTable.load(path)` classmethod with a directory and a
    file_pattern, mirroring `MortalityTable.load`.
  - `polaris price --yrt-rate-table PATH` CLI flag (one flag accepts
    a directory of CSVs OR a single multi-sheet file — to be
    decided in Slice 3 ADR).
  - `polaris rate-schedule --table` flag to emit a tabular schedule
    Excel via `YRTRateSchedule.generate_table(...)`.
  - `api.main.PriceRequest.yrt_rate_table_path: str | None`
    optional field; the API resolves and loads from server-side
    storage (path is relative to a configured data directory, with
    safety against path traversal).
  - Excel deal-pricing workbook: add a `YRT Rate Table` sheet when
    the run uses tabular rates.
  - Dashboard pricing page: file-uploader for the rate table; render
    a heatmap preview of the loaded grid.
  - ADR-052 captures the CSV format and CLI ergonomics decisions.

## Context for Next Session

- The Slice 1 module is **completely standalone**: it imports only
  from `polaris_re.core.base`, `polaris_re.core.exceptions`, and
  `polaris_re.core.policy`. It does not import `YRTTreaty`,
  `CashFlowResult`, or any pipeline machinery. Slice 2's integration
  boundary is `YRTTreaty.apply()`.
- The lookup contract is **annual dollars per $1,000 NAR**. Slice 2
  must convert with `/12 / 1000` to match the units of the existing
  flat-rate calculation. The current flat-rate code at
  `reinsurance/yrt.py:120` is the canonical reference: `monthly_rate_per_dollar = self.flat_yrt_rate_per_1000 / 12.0 / 1000.0`.
- The `(sex, smoker)` grouping for lookup means Slice 2 needs an
  inforce split. The pattern is already used in product engines (see
  `TermLife._build_rate_arrays`), where the inforce is split by
  (sex, smoker) before calling `MortalityTable.get_qx_vector`. Slice
  2 can borrow that pattern verbatim.
- The current YRT aggregate-NAR approximation is
  `total_face_t = total_face_amount * inforce_ratio_t` where
  `inforce_ratio_t = gross.gross_premiums[t] / gross.gross_premiums[0]`
  (see `reinsurance/yrt.py:106-114`). For per-policy tabular rates,
  Slice 2 needs a per-policy in-force factor. Two options:
  (a) project per-policy `lx[p, t]` via the product engine's seriatim
  output (requires `gross.seriatim_premiums is not None`), or
  (b) approximate per-policy inforce by scaling each policy's
  initial face by the same aggregate runoff ratio. Option (a) is more
  accurate but requires the product engine to populate the seriatim
  arrays; option (b) is a wash on aggregate but loses per-policy age
  drift. The Slice 2 ADR should pick one and document the trade-off.
- The synthetic fixture pattern in Slice 1 tests
  (`base_rate + age_slope * i + duration_slope * j`) is reused
  across many tests — refactor into a fixture if Slice 2 needs more
  than two new test files.
- The `arrays` field on `YRTRateTable` is `exclude=True` so it does
  not serialize via `model_dump()` (matching the `MortalityTable`
  convention — large numpy arrays are not JSON-friendly). When Slice
  3 wires the API, the request will carry a path or rate-table-id,
  not the array values themselves.

## Open Questions (for human)

1. **Slice 2 per-policy inforce projection: seriatim vs aggregate
   approximation?** The flat-rate path uses the aggregate-runoff-
   ratio approximation, which is fine for a single rate but
   under-specifies rate progression for tabular rates (every policy
   ages at the same per-month rate, but the LX-weighted average age
   drifts upward as younger / healthier policies persist). Option
   (a) seriatim is more accurate; option (b) aggregate-runoff
   preserves the existing approximation but doesn't fully resolve the
   PRODUCT_DIRECTION concern. Default for Slice 2: **(a) seriatim**,
   with a fallback to (b) when seriatim arrays are absent. ADR-051
   to document.
2. **Precedence when both `flat_yrt_rate_per_1000` and
   `yrt_rate_table` are set on the same `YRTTreaty`?**
   **RESOLVED — raise `PolarisValidationError` if both are set**
   (PR #36 reviewer, 2026-04-27). The reviewer flagged that
   silent table-wins could mask a copy-paste error in deal
   configuration, so Slice 2 must enforce mutual exclusion at
   `YRTTreaty` model-validator time. The validator should produce
   a clear error message naming both fields. ADR-051 will
   document the choice.
3. **CSV format for the YRT rate table** (Slice 3) — mirror the
   mortality CSV (one file per (sex, smoker)) or a single CSV with
   sex/smoker columns? Default: mirror mortality format for
   consistency with the existing actuarial CSV ecosystem.
4. **`YRTRateSchedule.generate_table(...)` axis grid** — which
   ages, sexes, smokers, and durations to solve over by default?
   Default proposal for Slice 2: ages 25..85 step 5, both sexes,
   both smoker statuses, durations 0..30 (matches the typical
   industry rate-table cell count of ~600 cells, brentq-feasible
   in seconds).

When all slices are DONE, update Status to COMPLETE.
