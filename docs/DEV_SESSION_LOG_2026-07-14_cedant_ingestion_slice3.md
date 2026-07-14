# Dev Session Log — 2026-07-14 (Cedant Ingestion, Slice 3 — epic COMPLETE)

## Item Selected
- **Source:** `CONTINUATION_cedant_ingestion.md` (active Tier-A epic A3'), Slice 3
  — the final slice. Backed by `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4
  Tier-A (A3').
- **Priority:** IMPORTANT / Tier-A (★★★★☆) — cedant-ingestion robustness.
- **Title:** Cedant Data-Ingestion Robustness (A3') — Slice 3: surfaces (CLI/API
  rejects file + richer report + thresholded exit/response).
- **Slice:** 3 of 3 — **closes the epic** (CONTINUATION IN PROGRESS → COMPLETE).
- **Branch:** `claude/loving-gauss-6fixu5` (designated remote-session branch;
  environment override per step 8). Cut from `origin/main` at `346ec83`, which
  includes the merged Slice-1 (#137) and Slice-2 (#138) PRs.

## Selection Rationale
Step 5 found an IN-PROGRESS CONTINUATION driving the active epic
(`CONTINUATION_cedant_ingestion`). Slice 2 (PR #138) is **merged** to main
(`git log` shows merge commit `346ec83`; `list_pull_requests --state open` returns
`[]`), so Slice 3 is unblocked. Per step 5c the CONTINUATION *is* the work
selection — no step-5b/step-6 fallback pick. The epic's next (and last) unchecked
slice is advanced this session, as the ACTIVE EPIC guardrail requires.

Ledger healing (step 4b): no open PRs and all merged A3' PRs (#136/#137/#138) are
already recorded in the CONTINUATION and prior session logs — the ledger is
healthy, no crossout needed.

## Premise Verified (step 7b)
Reproduced the gap before writing code. Ran the current `polaris ingest` on a
3-row messy extract (one negative-face row, faces in thousands, US `MM/DD/YYYY`
dates): it printed `✗ Non-positive face_amount found`, **exited 1, and wrote no
output** — the two good rows were lost with the one bad one, and even had it
passed, the un-coerced US dates would have crashed the later
`InforceBlock.from_csv`. Confirmed the CLI used `ingest_cedant_data →
validate_inforce_df` (frame-level abort) and never called `apply_value_coercion`
or `partition_inforce_rows`, and the API `/api/v1/ingest` had its own inline
pipeline that returned every row unpartitioned and uncoerced. Premise holds — the
surfacing gap is real.

## Decomposition Plan (active epic status)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Row-level quarantine + richer `DataQualityReport` | ✅ Done | #137 (merged) |
| 2 | Robust value coercion (mixed dates + unit/currency) | ✅ Done | #138 (merged) |
| 3 | Surfaces — CLI/API rejects file + report + thresholded exit | ✅ Done | this PR (draft) |

**Epic COMPLETE** — all three slices shipped; CONTINUATION flipped to COMPLETE.

## What Was Done
Shipped A3' Slice 3, the final surfacing slice — pure plumbing, no new
computation. Wired the completed Slice 1–2 library into both entry points via the
canonical pipeline `ingest → apply_value_coercion → partition_inforce_rows`.

**CLI `polaris ingest`.** After `ingest_cedant_data`, runs `apply_value_coercion`
then `partition_inforce_rows`. Writes the *clean* frame to `--output` and the
*rejects* frame (carrying its `_reject_reason` column) to `--rejects` (default:
`--output` with a `.rejects.csv` suffix), only when rows are rejected. The summary
now reports rows-examined / clean / rejected, a per-reason breakdown table, and
the coercion warnings. Default behaviour is **best-effort** (usable rows ingest,
exit 0 even with rejects); a new optional `--max-reject-pct` hard-fails (exit 1)
when the rejected fraction exceeds the threshold; an empty clean block (every row
rejected) remains a hard failure via the report's `errors`.

**API `/api/v1/ingest`.** `IngestColumnMapping` gains the coercion fields
(`unit_scale` / `premium_mode` / `currency` / `date_columns` / `date_formats`),
all defaulting to a no-op. `IngestResponse` gains `n_input` / `n_rejected` /
`reject_reasons` / `rejects` (defaults `0` / `{}` / `[]`); `policies` now returns
the clean block and `warnings` prepends the coercion warnings. The inline
rename/translate/defaults pipeline is retained (the API receives records, not a
file path) with coercion + partition appended after it.

Purely **additive and pricing-neutral**: for a clean block, partitioning returns
all rows clean with zero rejects and coercion is a config-gated no-op, so the
clean output is byte-identical, the API `policies` list is unchanged, and the new
response fields take their defaults. The pricing path is never touched — QA
goldens and the `polaris price` regression are byte-identical. The only behaviour
change is the intended one: a *messy* block that previously aborted now ingests
best-effort. Design recorded in **ADR-138**.

## Files Changed
- `src/polaris_re/cli.py` — `ingest` command: `apply_value_coercion` +
  `partition_inforce_rows` pipeline; `--rejects` and `--max-reject-pct` options;
  rows-examined/clean/rejected summary + reject-reason breakdown table; clean +
  rejects file writes.
- `src/polaris_re/api/main.py` — `IngestCurrency` model; coercion fields on
  `IngestColumnMapping`; `n_input`/`n_rejected`/`reject_reasons`/`rejects` on
  `IngestResponse`; `api_ingest` runs coercion + partition and returns the clean
  block + rejects.
- `tests/test_cli_ingest.py` — new file, 12 tests.
- `tests/test_api/test_main.py` — `TestIngestEndpoint` (8 tests).
- `docs/DECISIONS.md` — ADR-138.
- `docs/QUICKSTART.md` — §6 messy-file / rejects / API coercion documentation.
- `docs/PLAN_cedant_ingestion.md`, `docs/CONTINUATION_cedant_ingestion.md` —
  Slice 3 DONE, epic COMPLETE, reject-threshold open question resolved.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — three ADR-138 follow-ups promoted.

## Tests Added
- `tests/test_cli_ingest.py::TestIngestQuarantine` (8): messy file exits 0
  best-effort; clean output holds only the good rows; `unit_scale` scales face
  (500 in thousands → 500,000); US dates coerce to ISO; rejects file written with
  a per-row reason; report shows input/rejected counts + reason; `--rejects`
  honours a custom path.
- `TestIngestUnparseableDate` (1): an unparseable-date row is quarantined
  (`unparseable_issue_date`), not crashed.
- `TestIngestThreshold` (2): `--max-reject-pct` fails above / passes below the
  threshold.
- `TestIngestCleanFile` (2): a clean file writes no rejects file;
  `--validate-only` writes nothing.
- `tests/test_api/test_main.py::TestIngestEndpoint` (8): clean input is
  back-compatible (zero rejects, all policies returned); a bad row is quarantined
  with `_reject_reason`; `reject_reasons` breaks down by rule; unit-scale, ISO
  date coercion, currency conversion (with warning), and premium annualisation
  (with warning) apply to the clean policies.

All fixtures pin explicit dates (ADR-074 guard) — no test reads the wall clock.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Messy fixture ingests to a clean block + a rejects file + a report | ✅ | CLI `TestIngestQuarantine`; verified end-to-end on the repro file |
| Rejects file carries per-row `_reject_reason` | ✅ | `test_rejects_file_written_with_reason`; `A3 → "non_positive_face_amount; unparseable_issue_date"` |
| Report enumerates rows examined / clean / rejected + reasons | ✅ | summary + breakdown table (CLI); `n_input`/`n_rejected`/`reject_reasons` (API) |
| Coercion applied through the surface (unit/dates/currency/premium) | ✅ | face scaled, dates ISO, CAD conversion + premium annualisation warnings |
| Thresholded exit/response (`--max-reject-pct`) | ✅ | `TestIngestThreshold` |
| Backward compatible for clean inputs | ✅ | clean output byte-identical; API `policies` unchanged; new fields default |
| Goldens / QA byte-identical | ✅ | pricing path untouched; `polaris price` regression clean; QA suite green |
| ADR + QUICKSTART + PLAN + CONTINUATION | ✅ | ADR-138; QUICKSTART §6; both epic docs updated |

## Open Questions / Follow-ups
- **Reject thresholds:** RESOLVED this slice (best-effort default + optional
  `--max-reject-pct`). Recorded in ADR-138 and the CONTINUATION. (Not harvested.)
- Three 1st-order NICE-TO-HAVE follow-ups harvested from ADR-138 "Out of scope"
  (see Harvest below).

## Harvest (step 17)
This slice closes the `CONTINUATION_cedant_ingestion` epic (IN PROGRESS →
COMPLETE), so per step 17 every surviving follow-up is promoted before the status
transition:
- **CONTINUATION Refinement Backlog:** none (this CONTINUATION has no such
  section).
- **CONTINUATION Open Questions:** both (reject thresholds, ambiguous-date policy)
  are RESOLVED — nothing to promote.
- **ADR-138 "Out of scope":** three 1st-order follow-ups of the A3' epic, all
  NICE-TO-HAVE (they affect automation/scale, not common-path first-deal
  correctness), appended to `PRODUCT_DIRECTION_2026-06-18.md` (< 30 days old →
  append): (1) machine-readable ingestion report sidecar (`<output>.report.json`);
  (2) rejects-file format option (`--rejects-format` Parquet/JSON); (3) streaming
  ingestion for out-of-core files. Each carries `Source: ADR-138 Out of scope
  (1st-order)` provenance.
- ADR-136 / ADR-137 out-of-scope items were harvested by their own slice sessions
  (already in the same file's Promoted Follow-ups) — not re-promoted.

## Post-Review Refinement (PR #139 [P2])
The automated review approved the PR (zero P0) with one optional [P2]: a
`--max-reject-pct` breach raised `Exit(1)` *before* the file-write block, so an
operator triaging the failure got no rejects file to see which rows failed. Folded
into this PR: on a breach the command now **writes the rejects file** (pure
diagnostic) before exiting 1, but still **withholds the clean output** — a breach
means "the mapping is probably wrong, trust nothing", so no clean block is emitted
that a downstream step might consume. `--validate-only` still writes nothing even
on breach. Two new CLI tests pin this
(`test_max_reject_pct_breach_writes_rejects_but_not_clean`,
`test_max_reject_pct_breach_validate_only_writes_nothing`); ADR-138 + QUICKSTART §6
updated. CLI test count 12 → 14; slice total 20 → 22.

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups this session.)

## Impact on Golden Baselines
None. Slice 3 is a pure surfacing slice over the additive, config-gated Slice 1–2
library. For a clean block the clean output is byte-identical and coercion is a
no-op; the pricing path is untouched. QA golden suite is green and the
`polaris price` regression on `golden_config_flat.json` ran clean.

```
Baseline `make test` (this session, on main post-#138): 2172 passed, 3 skipped,
  110 deselected, 0 failures (matches the previous session log's post-Slice-2 set;
  tolerance-aware check: no new/changed failures).
After this slice: 2194 passed, 3 skipped, 110 deselected (+22 = 14 CLI + 8 API;
  includes the 2 post-review threshold-breach tests).
```
