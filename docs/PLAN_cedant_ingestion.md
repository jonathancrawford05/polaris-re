# PLAN: Cedant Data-Ingestion Robustness (A3')

**Status:** COMPLETE — constituted 2026-07-13 as the active epic. Slice 1
(row-level quarantine + richer `DataQualityReport`, ADR-136), Slice 2 (robust
value coercion — dates + unit/currency, ADR-137), and Slice 3 (CLI/API surfaces +
rejects file + thresholded exit, ADR-138) are all **DONE** (2026-07-14). The epic
is fully surfaced through `polaris ingest` and `/api/v1/ingest`.

**Source / derivation.** With A1' (Validation & Benchmark) and A2' (Production
Hardening & Observability, PRs #133–135) shipped, `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`
§4 ranks the remaining Tier-A "big rocks" as A1' (done) → A2' (done) → **A3'
Cedant data-ingestion robustness** (★★★★☆, ~5–7 d, 2–3 phases). Both remaining
big rocks were market-access / deployability gates; with A2' done, A3' is the
next Tier-A item outright. It was flagged as the direction to take by the PR #136
review [P1] (no active epic; stop harvesting Tier-B polish and constitute the
next Tier-A epic).

**Why this epic now.** The engine models correctly, a buyer can validate the
numbers (A1'), and an ops team can deploy the service (A2'). The remaining
frontier is the *first thing a real deal throws at the engine*: a messy cedant
inforce extract. The existing pipeline (`utils/ingestion.py`) was built against
clean sample data — it maps columns, translates codes, applies defaults, and
**hard-fails the whole block** if a required column is missing. It has no defense
against messy *rows* (a handful of bad records in a 100k-policy file) or messy
*values* (mixed date formats, face in thousands, foreign currency). A3' hardens
it so real files ingest with actionable diagnostics instead of an all-or-nothing
failure.

## Design Anchors

- **Additive and pricing-neutral.** New capabilities are new functions / opt-in
  config; the existing `ingest_cedant_data` / `validate_inforce_df` behaviour is
  never changed. QA goldens and the `polaris price` regression stay byte-identical
  across the whole epic (nothing here touches the pricing path).
- **Quarantine, don't abort.** The core shift is from block-level pass/fail to
  **row-level partitioning**: usable rows are priced, unusable rows are separated
  into a rejects frame/file with a per-row reason, and the `DataQualityReport`
  carries an actionable breakdown.
- **Config-gated coercion.** Robust date parsing and unit/currency normalisation
  are driven by `IngestConfig` and default to today's behaviour when unset.
- **Clock-safe tests (ADR-074 guard).** Date-coercion tests pin explicit input
  strings and expected parsed values; no test reads the wall clock.

## Decomposition

### Slice 1: Row-level quarantine + richer report — DONE (2026-07-13, ADR-136)
`utils/ingestion.py`: new `partition_inforce_rows(df) -> (clean, rejects, report)`
that separates rows failing any blocking rule (missing required cell,
non-positive face/premium, negative age, attained-before-issue) into a rejects
frame carrying a `_reject_reason` column, and returns a `DataQualityReport`
enriched with `n_input` / `n_rejected` / `reject_reasons` (per-rule counts) plus
`has_rejects`. Summary stats are computed on the clean rows (reusing
`validate_inforce_df`). Additive throughout — `DataQualityReport` gains
default-valued fields and the existing frame-level `validate_inforce_df` is
untouched, so goldens stay byte-identical. 12 tests in
`tests/test_utils/test_ingestion.py::TestPartitionInforceRows`.

### Slice 2: Robust value coercion — DONE (2026-07-13, ADR-137)
`utils/ingestion.py`: new `apply_value_coercion(df, config) -> (df, warnings)`,
a config-gated stage between `ingest_cedant_data` and `partition_inforce_rows`.
Date coercion (`date_columns` / `date_formats`) infers ISO / US `%m/%d/%Y` / EU
`%d/%m/%Y` / `%Y/%m/%d` / Excel-serial format per column, rewrites parseable
cells to canonical ISO, flags ambiguous columns (assume US + warn), and leaves
unparseable cells for the new `_date_reject_rules` (`unparseable_<col>`) to
quarantine. Unit/currency normalisation (`unit_scale`, `premium_mode`,
`CurrencyConfig`) scales the monetary columns multiplicatively. All new
`IngestConfig` fields default to a no-op, so goldens stay byte-identical. 22 tests
in `TestApplyValueCoercion` (20) + `TestPartitionInforceRows` (2 date rejects).

### Slice 3: Surfaces — DONE (2026-07-14, ADR-138)
Wired the completed library into both surfaces via
`ingest → apply_value_coercion → partition_inforce_rows`. `polaris ingest` writes
the clean frame to `--output` and the rejects frame (with `_reject_reason`) to
`--rejects` (default `<output>.rejects.csv`), reports rows-examined / clean /
rejected with a per-reason breakdown and coercion warnings, and is best-effort
(exit 0) with an optional `--max-reject-pct` hard-fail gate. `/api/v1/ingest`
accepts the coercion fields in its `mapping` and returns `n_input` / `n_rejected` /
`reject_reasons` / `rejects` alongside the clean `policies` (defaults preserve the
old response shape). QUICKSTART §6 updated. 22 tests (14 CLI in
`tests/test_cli_ingest.py` + 8 API in `TestIngestEndpoint`). Reject-threshold open
question resolved (best-effort + optional gate). Goldens byte-identical.

## Open Questions (for human)

- **Reject thresholds (Slice 3):** should a high reject fraction (e.g. > X% of
  rows) be a hard failure, or always best-effort with a loud report? Default
  taken next: best-effort + report, with an optional `--max-reject-pct` gate.
- **Ambiguous-date policy (Slice 2):** when a column is genuinely ambiguous
  (all values ≤ 12 in both day/month positions), warn-and-assume-ISO vs. require
  an explicit `date_format`. Default taken next: require explicit format for a
  flagged-ambiguous column, else warn.
