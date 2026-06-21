# Dev Session Log — 2026-06-21 (IFRS 17 movement table — CLI surface, Epic 2 Slice 3c)

## Item Selected
- **Source:** CONTINUATION_ifrs17_movement.md (active Epic 2, Tier-A A2) — Slice 3c
- **Priority:** IMPORTANT
- **Title:** Surface the IFRS 17 movement table on the `polaris price` CLI
- **Slice:** 3c of 3 (Slice 3 sub-sliced 3a/3b/3c) — **closes the epic**
- **Branch:** `claude/awesome-bardeen-p8n0cn` (environment-designated)

## Selection Rationale

Step 5 found `CONTINUATION_ifrs17_movement.md` IN PROGRESS, so the active Epic 2
is the work selection (routine step 5c — the CONTINUATION IS the selection; skip
fallback). The prior slice (3b, PR #90) is merged into the working branch
(`git log` shows `0f2bca7 Merge pull request #90 … Slice 3b`), so the NEXT slice,
3c, was unblocked and continued on the designated branch. No fallback item was
considered — the Epic's next slice could be advanced (routine guardrail: never
fall back while the active Epic can advance).

## Verify Premise (step 7b)

Reproduced before writing code. With the baseline suite green (1513 passed,
94 deselected), `polaris ifrs17 --help` exited non-zero (no such command) and
`polaris price --help` had no `ifrs17` / movement flag — the movement table was
unreachable from the CLI even though the REST API (3a) and the Excel writer (3b)
were ready. The gap is real; the slice is not a no-op.

## What Was Done

Added `polaris price --ifrs17-movement` (opt-in; off by default) with
`--ifrs17-ra-factor` (default 0.05, validated [0, 0.50]) and
`--ifrs17-months-per-period` (default 12, validated ≥ 1). When set, the movement
table is built **per product cohort** (`iter_cohorts`): the cohort's policies are
re-grouped into annual issue-year cohorts, each issue-year sub-block is projected
GROSS via the product dispatcher, and the groups feed `IFRS17CohortManager`
(`aggregate_movement_table` + `cohort_movement_tables`). This mirrors the REST
reference consumer (`POST /api/v1/ifrs17/movement`, ADR-095).

Per-product (not block-wide) is required for correctness: TERM and WHOLE_LIFE
project on different grids, so a block-wide aggregate would fail the cohort
manager's alignment check; per-product also matches the per-cohort Excel workbook
model (ADR-068). The locked-in discount rate is `config.discount_rate` for every
cohort (a per-issue-year override — already on the REST API — is a promoted
follow-up). The result is serialised to JSON in the REST-mirroring shape
(`{months_per_period, n_cohorts, max_footing_error, aggregate, cohorts}`, reusing
the 3a `to_dict()`), per cohort and (single-cohort case) at the top level;
rendered as two compact Rich tables (total-liability reconciliation + closing
balances by component); and — with `--excel-out` — populates
`DealPricingExport.ifrs17_movement` so the Slice-3b sheet appears on the same run.

Off by default, so the CLI JSON, terminal, and Excel outputs are byte-identical
to prior runs (golden CLI / pipeline tests unchanged, no rebaseline). ADR-097.
**This completes Epic 2 (IFRS 17 movement table).**

## Files Changed
- `src/polaris_re/cli.py` — three new `price` flags; `_build_ifrs17_movement_export`,
  `_ifrs17_movement_to_dict`, `_ifrs17_movement_max_footing_error`,
  `_render_ifrs17_movement` helpers; `ifrs17_movement` param on
  `_cohort_to_deal_pricing_export`; JSON / Rich / Excel wiring in `price_cmd`;
  eager flag validation; `Policy` import.
- `docs/DECISIONS.md` — ADR-097.
- `docs/CONTINUATION_ifrs17_movement.md` — Slice 3c DONE; Status → COMPLETE.
- `docs/PLAN_ifrs17_movement.md` — Status → COMPLETE; Slice 3c marked SHIPPED.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — ledger healing (Slice 3c + Slice 3
  parent struck through / SHIPPED); harvested follow-ups.

## Tests Added
- `tests/test_analytics/test_cli_ifrs17_movement.py` (15 tests): backward compat
  (no flag → no `ifrs17_movement` key, no Excel sheet); JSON shape mirrors REST
  keys; **headline footing property** (`max_footing_error < 1e-6` per cohort);
  cohorts grouped + ordered by issue year (golden TERM → [2021, 2026],
  WHOLE_LIFE → [2016, 2021, 2026]); aggregate null cohort metadata; locked-in
  rate = config discount rate; rows carry all components; annual default;
  `--ifrs17-months-per-period 6` doubles periods and still foots; out-of-range
  flag validation exits non-zero; `--excel-out` appends the sheet per cohort.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Movement table reachable from the CLI | ✅ | `polaris price --ifrs17-movement` |
| Reuses the Slice-3a serialiser | ✅ | `to_dict()` → JSON shape == REST |
| Populates Excel sheet on the same run | ✅ | `--excel-out` sets `ifrs17_movement` |
| Table foots (opening + Σ == closing) | ✅ | `max_footing_error < 1e-6` asserted |
| Goldens byte-identical when off | ✅ | golden CLI/pipeline tests green, no rebaseline |
| Full fast suite green | ✅ | 1528 passed, 94 deselected |

## Open Questions / Follow-ups
- **Per-issue-year locked-in-rate override on the CLI** — the REST API has the
  `locked_in_rates` map; the CLI uses one rate. Promoted NICE-TO-HAVE.
- **Dedicated `polaris ifrs17` movement-only subcommand** (no pricing). Promoted
  NICE-TO-HAVE.
- **Dashboard IFRS 17 movement view** — last surface without it. Promoted
  NICE-TO-HAVE.
- **Block-wide cross-product movement** on a common calendar grid — blocked on
  heterogeneous-term alignment (existing follow-up). Promoted NICE-TO-HAVE.
- **Human confirmation (carried from CONTINUATION):** annual reporting-period
  granularity is the intended default; heterogeneous-term cohort alignment is
  deferred. Not work items — confirmations.

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups surfaced this session.)

## Impact on Golden Baselines
None. The flag is off by default; with it off the CLI JSON, terminal, and Excel
outputs are byte-identical to prior runs. No baselines regenerated.
