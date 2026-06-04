# Dev Session Log — 2026-06-04

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-05-23.md (Promoted Follow-ups)
- **Priority:** NICE-TO-HAVE
- **Title:** CLI surfacing of `--solve-mode` on `polaris rate-schedule --table`
- **Slice:** complete (SMALL — single session, 3 files, ~330 lines)

## Selection Rationale

All four BLOCKERs from PRODUCT_DIRECTION_2026-04-19 have shipped. The two
surviving IMPORTANT items (reserve-basis matching, IFRS 17 period-to-period
movement table) are 10 dev-days each — explicitly flagged in the latest
PRODUCT_DIRECTION as too large for a single session. The recommended
fallback is the NICE-TO-HAVE queue.

Selected `--solve-mode` CLI surfacing because it is:
- **Self-contained.** Internal helper (`generate_table(solve_mode=...)`)
  already shipped under ADR-063; only the CLI plumbing was missing.
- **Clearly scoped.** PRODUCT_DIRECTION acceptance criterion: "a
  `--solve-mode {flat,per_duration}` flag would light up the per-duration
  solver from the command line". Single command, single flag.
- **No contract changes.** Pure surfacing — `generate_table()` signature
  unchanged, no new analytics types, no new JSON shape.
- **Easily testable.** Typer CliRunner pattern is already established in
  `tests/test_analytics/test_cli_rate_schedule_table.py`.
- **Right-sized.** ~1 dev-day per the source PRODUCT_DIRECTION estimate.

Skipped:
- "Reserve basis matching" / "IFRS 17 period-to-period movement table" —
  10 dev-days each, would require a CONTINUATION decomposition.
- "Streamlit dashboard pages" — each ~3 dev-days, MEDIUM scope. Could be
  decomposed but the CLI flag is a strictly smaller, lower-risk pick for
  the daily-dev slot.

## What Was Done

Added `--solve-mode {flat,per_duration}` as a Typer option to
`polaris rate-schedule`. The flag is typed via
`Annotated[Literal["flat", "per_duration"], typer.Option(...)]` so
Typer's auto-derived choice validation rejects unknown values before any
projection runs (Click usage error, exit code 2).

The option is only meaningful with `--table`. Passing `--solve-mode
per_duration` without `--table` exits with code 1 and a Rich-rendered
error message; the default `"flat"` is a no-op without `--table` so
existing flat-schedule invocations are unchanged. When `--table` is set,
the value is threaded directly into
`scheduler.generate_table(solve_mode=...)`.

The `--select-period` help text was tightened to reflect that the
per-duration solver is now reachable from the CLI (previously the help
text said "until the per-duration solver lands" — stale since ADR-063
shipped).

ADR-067 documents the decision (Typer `Literal` over `click.Choice`,
upfront rejection vs. silent ignore, no analytics-layer changes).

## Files Changed
- `src/polaris_re/cli.py` (+25 lines net: `Literal` import,
  `--solve-mode` option on `rate_schedule_cmd`, upfront-rejection guard,
  pass-through to `generate_table`, tightened `--select-period` help)
- `tests/test_analytics/test_cli_rate_schedule_table.py` (+198 lines:
  `TestSolveModeFlagValidation` (3 fast tests) +
  `TestSolveModePerDurationCLI` (4 slow end-to-end tests))
- `docs/DECISIONS.md` (+97 lines: ADR-067)

## Tests Added
- `TestSolveModeFlagValidation::test_invalid_solve_mode_value_rejected`
  — Typer Choice validation rejects unknown values
- `TestSolveModeFlagValidation::test_per_duration_without_table_rejected`
  — `--solve-mode per_duration` without `--table` exits 1 with clear msg
- `TestSolveModeFlagValidation::test_flat_solve_mode_without_table_runs_unchanged`
  — `--solve-mode flat` (default) is a no-op without `--table`
- `TestSolveModePerDurationCLI::test_per_duration_table_name_carries_suffix`
  — generated `table_name` ends with `_per_duration`
- `TestSolveModePerDurationCLI::test_flat_table_name_carries_flat_suffix`
  — default mode tags `table_name` with `_flat`
- `TestSolveModePerDurationCLI::test_per_duration_produces_per_cell_rates`
  — per-duration mode produces non-uniform rows (flat mode is row-uniform)
- `TestSolveModePerDurationCLI::test_per_duration_solved_mask_is_per_cell`
  — `solved_mask` is genuinely 2-D under per_duration (matching the
  analytics-layer `test_per_duration_sparse_ages_mark_only_solved_cells`)

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `--solve-mode {flat,per_duration}` flag exists on `polaris rate-schedule` | ✅ | Typer `Literal` annotation |
| Lights up the per-duration solver from the CLI | ✅ | passed through to `generate_table(solve_mode=...)` |
| Generated `table_name` discloses which mode produced it | ✅ | already encoded by ADR-063 (`_flat` / `_per_duration` suffix) — verified by tests |
| Backward compatible with existing flat-schedule invocations | ✅ | default `"flat"`; existing `test_no_table_default_runs_unchanged` passes unchanged |
| Unknown values are rejected up front | ✅ | Typer Choice validation, exit code 2 |
| `--solve-mode per_duration` without `--table` is a clear error | ✅ | exit 1 with Rich message |

## Open Questions / Follow-ups

None for this slice — both ADR-063 out-of-scope items already promoted
to PRODUCT_DIRECTION as separate NICE-TO-HAVEs are unaffected:

- Per-duration cell-failure interpolation
- Warm-start `brentq` across adjacent per-duration cells

These remain valid future-session pickups.

## Impact on Golden Baselines

None. `polaris price` and the deal-pricing pipeline do not call
`rate-schedule`. The default `"flat"` behaviour of
`rate-schedule --table` is byte-identical to the prior implementation
— existing CLI tests (`test_table_emits_xlsx`,
`test_table_json_emits_cohort_dict`, etc.) pass without modification.
Verified by running
`uv run polaris price --inforce data/qa/golden_inforce.csv
--config data/qa/golden_config_flat.json -o /tmp/dev_check.json` — JSON
written, cohort PV profits match prior values (Cedant $3,513,563,
Reinsurer $45,386).
