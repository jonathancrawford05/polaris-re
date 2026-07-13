# Continuation: Cedant Data-Ingestion Robustness (A3')

**Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4 Tier-A (A3'); PR #136 review [P1]
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~5–7 dev-days

## Overall Goal

Harden the existing cedant ingestion pipeline (`utils/ingestion.py`) for messy
real-world inforce extracts: quarantine unusable rows instead of failing the
whole block (Slice 1), coerce mixed date formats and normalise units/currency
(Slice 2), and surface a rejects file + richer diagnostics through the CLI/API
(Slice 3). Additive throughout — the pricing path is never touched and goldens
stay byte-identical.

This is the active epic per the checkpoint sequence (A1' and A2' shipped; A3' is
the next Tier-A "big rock"). See `PLAN_cedant_ingestion.md`.

## Decomposition

### Slice 1: Row-level quarantine + richer report
- **Status:** DONE
- **Branch:** `claude/loving-gauss-4gisb6` (designated remote-session branch)
- **PR:** #137 (draft)
- **What was done:** New `partition_inforce_rows(df) -> (clean, rejects, report)`
  in `utils/ingestion.py`. Rows failing any blocking rule (missing required cell,
  non-positive face/premium, negative age, attained-before-issue) are separated
  into a `rejects` frame carrying a `_reject_reason` column that lists every rule
  each row failed; the `clean` frame keeps the usable rows. `DataQualityReport`
  gains default-valued fields `n_input` / `n_rejected` / `reject_reasons`
  (per-rule counts) and a `has_rejects` property; its summary stats are computed
  on the clean rows (reusing `validate_inforce_df`). 12 tests. ADR-136.
- **Key decisions:**
  - **Additive, not a rewrite.** `validate_inforce_df` and the existing
    `DataQualityReport` fields are untouched; the new fields default so no
    existing caller or golden changes. `partition_inforce_rows` is a new,
    separate entry point.
  - **Rejects frame is returned, not stored on the report.** The report stays
    lightweight/serialisable (counts + reasons); the rejects rows travel in a
    separate frame. Slice 3 writes that frame to a rejects file.
  - **Per-row reason lists every failing rule** (`"; "`-joined); `reject_reasons`
    counts each rule independently, so its values can sum to more than
    `n_rejected` when a row fails multiple rules (documented).
  - **`is_valid` semantics preserved** — still "no frame-level errors on the
    clean block", so a partitioned block can be `is_valid` while `has_rejects`.

### Slice 2: Robust value coercion
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Files to modify:** `utils/ingestion.py` (date coercion + unit/currency
  normalisation step; `IngestConfig` gains `unit_scale` / `premium_mode` /
  `currency`), `tests/test_utils/test_ingestion.py`.
- **Acceptance criteria:**
  - Mixed date formats (ISO / US / EU / Excel serial) parse; ambiguous dates are
    flagged on the report; unparseable dates route the row to rejects.
  - `unit_scale` closed-form: face `500` in thousands → `500000`; `premium_mode`
    monthly → annual (×12). Default-off leaves current behaviour.

### Slice 3: Surfaces (CLI/API + rejects file)
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** `polaris ingest` CLI + `/api/v1/ingest` API emit the rejects file
  and the richer report; thresholded exit/response; QUICKSTART section; ADR.

## Context for Next Session

- **Blocking rules live in `_row_rules(columns)`** — a list of
  `(name, polars-bool-expr)` guarded by column presence. Slice 2's "unparseable
  date" reject is added here (a rule that fires when a date column failed to
  coerce), so the rejects machinery is reused rather than duplicated.
- **Order matters for Slice 2:** coerce/normalise values *before*
  `partition_inforce_rows`, so a value that fails coercion becomes a null (caught
  by `missing_required_field`) or an explicit unparseable-date reject — either
  way it lands in the rejects frame with a clear reason rather than crashing.
- `REJECT_REASON_COLUMN = "_reject_reason"` is the canonical rejects annotation;
  Slice 3's rejects file writes the rejects frame as-is (it already carries it).
- Goldens are byte-identical because nothing touches the pricing path and the new
  code is additive/opt-in. Keep that invariant through Slices 2–3 (only the final
  surfacing is user-visible, and even it doesn't change pricing outputs).

## Open Questions (for human)

- **Reject thresholds (Slice 3):** hard-fail above a reject fraction, or always
  best-effort + loud report? Leaning best-effort with an optional `--max-reject-pct`.
- **Ambiguous-date policy (Slice 2):** require an explicit `date_format` for a
  flagged-ambiguous column, or warn-and-assume-ISO? Leaning require-explicit.
