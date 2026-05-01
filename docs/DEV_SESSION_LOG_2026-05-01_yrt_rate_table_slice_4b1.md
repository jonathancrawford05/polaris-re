# Dev Session Log — 2026-05-01

## Item Selected
- **Source:** `docs/CONTINUATION_yrt_rate_table.md` (IN PROGRESS — Slice 4b
  PLANNED)
- **Priority:** IMPORTANT (PRODUCT_DIRECTION_2026-04-19 — "YRT rate
  schedule by age × duration"); Slice 4b-1 within it is a deliverable
  blocker per CONTINUATION
- **Title:** YRT rate table — Slice 4b-1 — `generate_table()` fill-in
  transparency disclosure (ADR-054)
- **Slice:** 4b-1 of 6 (re-decomposed from prior 5-slice plan; Slice 4b
  was further split into 4b-1 and 4b-2 because the disclosure problem is
  independent of the dashboard-upload work)

## Selection Rationale

The CONTINUATION file showed Slice 4b as PLANNED with a scope spanning
four logically separable work-streams: (i) fix
`generate_table()` fill-in transparency, (ii) Streamlit dashboard
file-uploader, (iii) matplotlib heatmap preview, (iv) optional
per-duration solver. Doing all four in one session would have crossed
the routine's MEDIUM/LARGE size threshold and packed three independently
mergeable changes into one PR. The CONTINUATION explicitly flagged the
fill-in transparency fix as a deliverable blocker ("must not be
presented as a production deliverable without disclosure"), so I split
Slice 4b into:

- **Slice 4b-1 (this session):** disclosure of forward/back-filled cells
  via an optional `solved_mask` on `YRTRateTableArray`, surfaced in CLI
  / Excel / JSON renderers. Self-contained, no contract change to
  consumers, ~250 lines of impl + ~250 lines of tests + ADR-054.
- **Slice 4b-2 (next session, PLANNED):** dashboard file-uploader, heatmap
  preview, optional per-duration solver, ADR-055.

PRODUCT_DIRECTION items 1–5 all map to BLOCKER / IMPORTANT entries that
are already shipped (per the merged-PR list in `git log`); the only
in-progress feature is the YRT rate table. Step 5b of the routine
("address the review feedback on the existing branch instead of starting
the next slice") did not apply because PR #39 was merged — so I
proceeded on a new branch from main.

## Decomposition Plan (multi-session)

Per `docs/CONTINUATION_yrt_rate_table.md` (updated this session):

| Slice | Scope                                                         | Status | PR |
|-------|---------------------------------------------------------------|--------|----|
| 1     | Standalone `YRTRateTable` data model                          | ✅ Done | #36 |
| 2     | Wire `YRTRateTable` into `YRTTreaty.apply()`                  | ✅ Done | #37 |
| 3     | CSV loader + CLI / API / Excel surfacing                      | ✅ Done | #38 |
| 4a    | `polaris rate-schedule --table` flag + standalone Excel writer | ✅ Done | #39 |
| 4b-1  | `generate_table()` fill-in transparency (ADR-054)             | ✅ Done | (this session) |
| 4b-2  | Dashboard file-uploader + heatmap (+ optional per-duration solver) | ⏳ Planned | — |

## What Was Done

Picked **Option A** from the prior CONTINUATION's two candidate fixes
(visual disclosure via an optional `solved_mask` field) over Option B
(restricting the table range to only requested ages). Option A is fully
backward compatible — the `YRTRateTable` storage contract is unchanged,
`YRTTreaty.apply()` consumption code does not branch on the new field,
and CSV-loaded tables render byte-identically to pre-ADR-054 output.
Option B would have required either a new sparse-storage contract or a
consumer-side clipping change, both of which would have broken Slice 2's
seriatim consumption path.

The change adds an optional `solved_mask: np.ndarray | None = None`
parameter to `YRTRateTableArray.__init__`, plus an `is_fully_solved`
convenience property. The mask is shape-validated against `rates`,
defensive-copied, and integer dtypes are coerced to bool.
`YRTRateSchedule.generate_table()` now constructs the mask in parallel
with the rates matrix, marking only the brentq-solved cells True. Mask
broadcasts uniformly across the select-period columns to match the
per-row rate broadcast contract from ADR-051 / ADR-053.

Three renderers consume the mask. The CLI `_render_yrt_rate_table()`
appends `*` to filled rate strings and prints a per-cohort caption when
any cell is filled. The CLI `_yrt_rate_table_to_dict()` includes the
mask per cohort when set; CSV-loaded tables omit the field. The Excel
`_write_yrt_rate_table_sheet()` styles filled cells with italic +
`#EEEEEE` `PatternFill`, and inserts a NOTE row at row 3 explaining
the convention. The standalone-workbook
`write_yrt_rate_table_excel()` Summary sheet adds `Solved cells: N` /
`Filled cells: M` rows plus an italic explanatory note when any cohort
carries a mask.

## Files Changed

- `src/polaris_re/reinsurance/yrt_rate_table.py` — added optional
  `solved_mask` to `YRTRateTableArray`, plus `is_fully_solved` property
  (~30 lines).
- `src/polaris_re/analytics/rate_schedule.py` — `generate_table` now
  builds and passes through the mask alongside rates (~15 lines).
- `src/polaris_re/cli.py` — `_render_yrt_rate_table` marks filled cells
  with `*` and prints a caption; `_yrt_rate_table_to_dict` includes
  `solved_mask` per cohort when present (~30 lines).
- `src/polaris_re/utils/excel_output.py` —
  `_write_yrt_rate_table_sheet` styles filled cells (italic +
  `#EEEEEE` `PatternFill`) and conditionally inserts the NOTE row;
  `write_yrt_rate_table_excel` Summary sheet adds Solved / Filled
  count rows when any cohort has a mask (~50 lines).
- `docs/DECISIONS.md` — ADR-054 (~150 lines).
- `docs/CONTINUATION_yrt_rate_table.md` — Slice 4b → 4b-1 + 4b-2
  re-decomposition; Slice 4b-1 marked DONE.

## Tests Added

| File | Class | Count | Notes |
|------|-------|-------|-------|
| `tests/test_reinsurance/test_yrt_rate_table.py` | `TestYRTRateTableArraySolvedMask` | 6 | default-None construction, round-trip, all-True is fully solved, shape mismatch raises, int→bool coercion, defensive copy |
| `tests/test_analytics/test_rate_schedule.py` | `TestGenerateTableSolvedMask` | 3 | dense grid fully solved, sparse grid marks intermediate rows False, mask broadcasts uniformly across select-period columns |
| `tests/test_analytics/test_cli_rate_schedule_table.py` | `TestSolvedMaskDisclosure` | 5 | render `*` + caption for filled cells, render unchanged when mask is None, JSON includes/omits per provenance, JSON is `json.dumps`-clean |
| `tests/test_analytics/test_cli_rate_schedule_table.py` | `TestSolvedMaskCLIIntegration` | 1 (slow) | end-to-end `polaris rate-schedule --table --ages 30,40 --json` writes `solved_mask` with True at indices 0 / 10 and False at 1..9 |
| `tests/test_utils/test_excel_output.py` | `TestSolvedMaskDisclosureExcel` | 5 | italic font on filled cells, `#EEEEEE` `PatternFill` on filled cells, NOTE row at row 3 contains the disclosure text, Summary records solved/filled counts, no-mask path is byte-identical |

**Totals:** 19 new fast tests + 1 new slow test. Full suite is now
909 non-slow (up from 890 baseline). QA suite unchanged at 33/33.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `polaris rate-schedule --table --ages 30,40 --json out.json` produces JSON `cohorts.M_U.solved_mask` with True at indices 0 / 10 and False at 1..9 | ✅ | `test_sparse_ages_disclose_filled_rows_in_json` |
| `_render_yrt_rate_table` prints `1.5000*` for filled cells and `1.0000` for solved cells | ✅ | `test_render_marks_filled_cells_with_asterisk` |
| Disclosure caption printed once per cohort when any cell is filled, never when all cells are solved | ✅ | `test_render_marks_filled_cells_with_asterisk` + `test_render_no_mask_is_unchanged` |
| Excel cells styled with italic + `#EEEEEE` `PatternFill` for filled cells; NOTE row at row 3 explains the convention | ✅ | `test_filled_cell_is_italic`, `test_filled_cell_has_grey_fill`, `test_disclosure_note_row_present` |
| `write_yrt_rate_table_excel` Summary sheet records Solved/Filled cell counts when a mask is present | ✅ | `test_summary_carries_solved_filled_counts` |
| CSV-loaded tables (mask `None`) render exactly as pre-ADR-054 output | ✅ | `test_render_no_mask_is_unchanged`, `test_no_mask_renders_unchanged` |
| `YRTRateTableArray` defensive-copies the mask | ✅ | `test_mask_caller_mutation_does_not_corrupt_stored_mask` |
| All 890 pre-existing non-slow tests still pass | ✅ | 909 total non-slow, 33 QA, all green |
| ADR-054 written | ✅ | `docs/DECISIONS.md` |
| Golden flat regression byte-identical | ✅ | `test_flat_golden_regression PASSED` |

## Open Questions / Follow-ups

- **Slice 4b-2's dashboard heatmap should consume `solved_mask`.** A
  hatched overlay or reduced alpha on filled cells in the matplotlib
  axis would be the natural visual analogue of the CLI `*` and the
  Excel italic+grey-fill. Suggested but not specified — leaves room
  for the Slice 4b-2 author to design the visual.
- **Per-duration solver still deferred to Slice 4b-2 (or later).** The
  current `generate_table()` broadcasts the per-age flat rate across
  every duration column, so the mask is uniform-along-rows. When the
  per-duration solver lands, the mask becomes genuinely 2-D and the
  existing renderers surface the finer-grained provenance with no
  further work.
- **No JSON-side back-compat shim needed.** The JSON `solved_mask`
  field was not present before this slice, so adding it is purely
  additive for machine consumers. Any consumer that decoded the
  pre-ADR-054 JSON shape will continue to work because `solved_mask`
  is a new optional key, not a rename.

## Impact on Golden Baselines

**None — golden baselines unchanged.**

The `solved_mask` field defaults to `None` everywhere in the existing
codebase. The deal-pricing Excel workbook
(`write_deal_pricing_excel`'s appended `YRT Rate Table` sheet, ADR-052)
is byte-identical when the attached `yrt_rate_table` has no mask. The
QA `golden_flat` and `golden_yrt` regression tests both pass
unchanged.
