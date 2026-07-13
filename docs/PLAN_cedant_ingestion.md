# PLAN: Cedant Data-Ingestion Robustness (A3')

**Status:** IN PROGRESS — constituted 2026-07-13 as the active epic. Slice 1
(row-level quarantine + richer `DataQualityReport`, ADR-136) is **DONE**.

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

### Slice 2: Robust value coercion — NEXT
- **Depends on:** Slice 1 merged.
- Mixed **date formats**: infer per-column format across candidates (ISO, US
  `MM/DD/YYYY`, EU `DD/MM/YYYY`, Excel serial); coerce; flag genuinely ambiguous
  dates (e.g. `03/04/2024`) on the report; unparseable dates route the row to the
  rejects frame via the Slice-1 machinery.
- **Unit/currency normalisation**: `IngestConfig` gains `unit_scale` (e.g. face
  in thousands → ×1000), `premium_mode` (monthly → annual), and a `currency` +
  conversion hook; a normalisation step with report summaries. Default-off → no
  behaviour change.
- Tests: parametrised date-format matrix; unit-scale closed-form (face `500` in
  thousands → `500000`); ambiguity flagged; unparseable → reject.

### Slice 3: Surfaces — PLANNED
- **Depends on:** Slice 2 merged.
- Wire into the `polaris ingest` CLI and `/api/v1/ingest` API: write the
  **rejects file** alongside the clean output, print/return the richer report,
  thresholded exit / response. QUICKSTART section; ADR.
- Tests: CLI + API integration; rejects-file round-trip.
- **Acceptance:** a messy fixture ingests to a clean block + a rejects file + a
  report enumerating what was dropped and why; goldens byte-identical.

## Open Questions (for human)

- **Reject thresholds (Slice 3):** should a high reject fraction (e.g. > X% of
  rows) be a hard failure, or always best-effort with a loud report? Default
  taken next: best-effort + report, with an optional `--max-reject-pct` gate.
- **Ambiguous-date policy (Slice 2):** when a column is genuinely ambiguous
  (all values ≤ 12 in both day/month positions), warn-and-assume-ISO vs. require
  an explicit `date_format`. Default taken next: require explicit format for a
  flagged-ambiguous column, else warn.
