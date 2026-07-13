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
- **Status:** DONE
- **Branch:** `claude/loving-gauss-1wcw10` (designated remote-session branch)
- **PR:** #138 (draft)
- **What was done:** New `apply_value_coercion(df, config) -> (df, warnings)` in
  `utils/ingestion.py`, a config-gated stage that runs between
  `ingest_cedant_data` and `partition_inforce_rows`. (1) **Date coercion** for
  `IngestConfig.date_columns`: infers ISO / US `%m/%d/%Y` / EU `%d/%m/%Y` /
  `%Y/%m/%d` / Excel-serial format per column, rewrites parseable cells to
  canonical ISO, flags genuinely ambiguous columns (assume US + warn; explicit
  `date_formats[col]` overrides), and leaves unparseable cells in place for
  quarantine. (2) **Unit/premium/currency scaling**: `unit_scale` (per-column
  multiplier), `premium_mode` annualisation (monthly/quarterly/semiannual), and a
  static `CurrencyConfig(code, rate)` on the monetary columns — composed
  multiplicatively in one pass. A new `_date_reject_rules` adds an
  `unparseable_<col>` reason to the Slice-1 rejects machinery, and
  `partition_inforce_rows` now runs `_row_rules + _date_reject_rules`. 22 tests
  (20 in `TestApplyValueCoercion` + 2 partition). ADR-137.
- **Key decisions:**
  - **Design Y — coercion is a distinct stage, not folded into
    `ingest_cedant_data`.** `ingest_cedant_data` is left byte-identical (zero risk
    to its callers). The documented pipeline is
    ingest → `apply_value_coercion` → `partition_inforce_rows`; Slice 3 wires it.
  - **Default-off ⇒ byte-identical.** Every new `IngestConfig` field defaults to a
    no-op; a config that does not opt in returns the frame unchanged, so goldens
    are byte-identical (the pricing path is never touched).
  - **Unparseable dates land in rejects with an explicit reason.** Coercion leaves
    an unparseable non-empty cell as its original string; `_date_reject_rules`
    then quarantines it as `unparseable_<col>` — reusing Slice-1 machinery rather
    than duplicating it. Empty/null cells fall to `missing_required_field`.
  - **Ambiguous-date policy resolved: assume US + warn** (not hard-fail), keeping
    ingestion best-effort and loud. An explicit `date_formats[col]` suppresses the
    warning. (See Open Questions — this is the taken default.)
  - **Currency is a single static rate** (`reporting = source x rate`); a live-FX
    or per-cohort rate is deliberately out of scope (harvested follow-up).

### Slice 3: Surfaces (CLI/API + rejects file)
- **Status:** NEXT
- **Depends on:** Slice 2 merged.
- **Scope:** `polaris ingest` CLI + `/api/v1/ingest` API emit the rejects file
  and the richer report; thresholded exit/response; QUICKSTART section; ADR.
  Reads the `apply_value_coercion` `warnings` and the partition `report`; wires
  the config's coercion fields through the CLI/API request schema.
- **Acceptance:** a messy fixture (mixed dates, face in thousands, a bad row)
  ingests to a clean block + a rejects file + a report enumerating what was
  dropped and why; goldens byte-identical.

## Context for Next Session

- **Slice 3 is a pure surfacing slice.** The library is complete:
  `apply_value_coercion(df, config) -> (df, warnings)` returns human-readable
  coercion diagnostics, and `partition_inforce_rows(df) -> (clean, rejects,
  report)` returns the rejects frame + report. Slice 3 wires those into the
  `polaris ingest` CLI and `/api/v1/ingest` API — it should NOT add new
  computation, only plumb config in and diagnostics/rejects out.
- **The canonical pipeline order is** ingest → `apply_value_coercion` →
  `partition_inforce_rows`. Coercion runs first so a bad value becomes a null
  (→ `missing_required_field`) or is left in place (→ `unparseable_<col>`) — both
  quarantined by the Slice-1 machinery, never crashing downstream.
- **Blocking rules:** `_row_rules(columns)` (Slice 1) + `_date_reject_rules(df)`
  (Slice 2, `unparseable_<col>` for string date columns). `REJECT_REASON_COLUMN
  = "_reject_reason"` is the canonical rejects annotation; Slice 3's rejects file
  writes the rejects frame as-is (it already carries it).
- **Config surface Slice 3 must expose:** `unit_scale`, `premium_mode`,
  `currency` (code + rate), `date_columns`, `date_formats`. All default to a
  no-op; the CLI/API request schema should accept them optionally.
- Goldens are byte-identical because nothing touches the pricing path and the new
  code is additive/opt-in. Keep that invariant through Slice 3 (surfacing is
  user-visible but does not change pricing outputs).

## Open Questions (for human)

- **Reject thresholds (Slice 3):** hard-fail above a reject fraction, or always
  best-effort + loud report? Leaning best-effort with an optional `--max-reject-pct`.
- **Ambiguous-date policy (Slice 2):** ~~require an explicit `date_format` for a
  flagged-ambiguous column, or warn-and-assume-ISO?~~ **RESOLVED (Slice 2):**
  assume US (`MM/DD/YYYY`) and emit a loud warning naming the column and telling
  the user to set `date_formats[col]`; an explicit format suppresses the warning.
  Chosen over hard-fail to keep ingestion best-effort (a whole file shouldn't be
  rejected on a formatting nicety). Revisit if a cedant base is predominantly EU.
