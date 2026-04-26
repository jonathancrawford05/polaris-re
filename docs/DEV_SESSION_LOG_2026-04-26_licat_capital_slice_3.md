# Dev Session Log — 2026-04-26 (LICAT capital, Slice 3 of 3)

## Item Selected

- **Source:** `docs/CONTINUATION_licat_capital.md` (originally
  PRODUCT_DIRECTION_2026-04-19.md — BLOCKER #5)
- **Priority:** BLOCKER
- **Title:** LICAT regulatory capital — CLI / API / Excel / dashboard
  surfacing of return-on-capital
- **Slice:** 3 of 3 (final slice; feature now COMPLETE)

## Selection Rationale

PR-#34 (Slice 2) merged earlier today, leaving Slice 3 — the
user-facing surfacing of the capital metric — as the natural next
step. Without Slice 3 the metric exists internally but is not
queryable from any production surface, so the routine's check for an
`IN PROGRESS` CONTINUATION pointed straight at this work. No
independent BLOCKER from the latest PRODUCT_DIRECTION competes for
priority because the other two BLOCKERs (substandard rating, deal-
pricing Excel export) are already shipped and merged.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Standalone `LICATCapital` calculator + factor model | ✅ Done | #33 (merged) |
| 2 | `ProfitTester.run_with_capital` + RoC + ADR-048 | ✅ Done | #34 (merged) |
| 3 | CLI `--capital licat`, API field, Excel rows, dashboard tile (this PR) | ✅ Done | (draft) |

## What Was Done

Wired the `LICATCapital` / `ProfitTester.run_with_capital` machinery
through every production surface so a pricing actuary can ask "what
RoC does this deal generate?" from the CLI, API, Excel workbook, or
dashboard. The integration is opt-in everywhere — when the user does
not supply `--capital licat` (CLI), `capital_model="licat"` (API),
or check the dashboard box, every existing consumer sees a
byte-identical contract.

Added `derive_capital_nar` to `polaris_re.core.pipeline` as the
canonical NAR derivation helper. It mirrors the inforce-ratio
approximation that `YRTTreaty.apply` already uses
(`gross.gross_premiums / gross.gross_premiums[0]`) so the LICAT NAR
for non-YRT runs is comparable to the YRT NAR. The cedant /
reinsurer face-share split is a single keyword arg
(`is_reinsurer`), per the PR-#34 reviewer's guidance: cedant face
share = `(1 - cession_pct)`, reinsurer face share = `cession_pct`.
The same formula handles YRT, coinsurance, modco, and the
no-treaty case.

ADR-049 captures the design choices: single helper for four call
sites, opt-in everywhere, Pydantic `Literal` for the API enum to
reject typos with 422, conditional `isinstance` detection in the
Excel writer to keep the `DealPricingExport` DTO stable.

## Files Changed

- `src/polaris_re/core/pipeline.py` — add `derive_capital_nar`;
  re-sort `__all__`.
- `src/polaris_re/cli.py` — add `--capital` flag, `_run_profit_tests`
  helper, `_append_capital_rows` Rich rendering, capital block in
  `_profit_test_to_dict`.
- `src/polaris_re/api/main.py` — `PriceRequest.capital_model`
  field, optional capital fields on `PriceResponse`, capital
  branching in `/api/v1/price` endpoint, `_capital_block` helper.
- `src/polaris_re/utils/excel_output.py` — `_CAPITAL_METRICS`
  rows on Summary sheet, `_write_capital_cell` helper, conditional
  rendering via `isinstance(..., ProfitResultWithCapital)`.
- `src/polaris_re/dashboard/views/pricing.py` — "Compute LICAT
  capital + RoC" checkbox, capital tiles in cedant + reinsurer
  views, capital-aware path in `_run_pricing_for_cohort`.
- `docs/DECISIONS.md` — ADR-049 appended.
- `docs/CONTINUATION_licat_capital.md` — Slice 3 marked DONE;
  status flipped to COMPLETE.
- `docs/DEV_SESSION_LOG_2026-04-26_licat_capital_slice_3.md` — NEW
  (this file).

## Tests Added

- `tests/test_core/test_pipeline_capital_nar.py` (15) — basics,
  inforce-ratio scaling, cession-aware splits (parameterised
  cession sweep), reserve subtraction.
- `tests/test_analytics/test_cli.py::TestPriceCommandCapital` (4) —
  JSON capital block, omitted when off, invalid value exits 1,
  Rich console rendering.
- `tests/test_api/test_main.py::TestPriceEndpoint` (4 added) —
  capital fields null when omitted; numeric and positive when
  `capital_model="licat"`; invalid value rejected with 422;
  cession sensitivity (higher cession → larger reinsurer capital).
- `tests/test_utils/test_excel_output.py::TestSummarySheetCapitalBlock`
  (7) — capital rows absent without capital, present with capital
  result; cedant RoC and reinsurer PV capital values match;
  advisory PV Capital Strain present; RoC None renders as N/A;
  mixed cedant/reinsurer renders other side as N/A.

Total: 30 new tests. Full non-slow suite is now 793 (up from
771 baseline). QA suite 33/33 green. `ruff format` and `ruff check`
both clean.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `polaris price --capital licat` JSON has `return_on_capital` per cohort | ✅ | Verified end-to-end against `data/qa/golden_inforce.csv`. |
| `POST /api/v1/price` with `capital_model="licat"` returns `return_on_capital` | ✅ | `test_price_capital_model_licat_populates_capital_block` |
| Excel Summary sheet shows RoC, Peak Capital, advisory `pv_capital_strain` | ✅ | `TestSummarySheetCapitalBlock` |
| Coinsurance/modco NET use cession-aware NAR; YRT inherits the same helper | ✅ | `derive_capital_nar` is unconditional; cession scaling applies to all treaty types. |
| Golden baselines unchanged when `--capital` is not supplied | ✅ | QA suite (`TestGoldenFlat`, `TestGoldenYRT`) green; JSON schema unchanged. |
| ADR-049 written | ✅ | Documents the canonical NAR helper, opt-in surfacing, and `Literal` enum. |
| Ruff format / check clean | ✅ | |

## Open Questions / Follow-ups

1. **Lapse/morbidity capital factors.** Still deferred per ADR-047 /
   ADR-049 "out of scope". Phase 5.1.b.

## Tracked future-routine items (not blocking this PR)

PR-#35 reviewer (jonathancrawford05, 2026-04-26) confirmed the
following dispositions and asked that they live as tracked
follow-ups rather than untracked open questions on the PR:

1. **Mixed-cohort RoC aggregation (next LICAT follow-up).** The CLI
   mixed-cohort summary table still reports total cedant / reinsurer
   PV profits only — it does NOT aggregate RoC across cohorts. The
   reviewer-confirmed proposed formula is
   `Σ(pv_profits) / Σ(pv_capital)` across cohorts (capital-weighted
   implicitly), surfaced as a one-liner addition to the mixed-cohort
   summary table. Implementation gated on a separate ADR that
   captures the weighting choice. **Action for next routine:** open
   an ADR proposal + implementation slice; expected scope ≤ 1
   session.
2. **Dashboard tile help-text quantitative anchor.** Reviewer NACK
   on the original PR-#35 text — addressed in this same PR by
   appending the "360 monthly balances are discounted; PV Capital
   is substantially larger than Peak Capital" sentence to the RoC
   tile tooltips (cedant + reinsurer). No separate follow-up.
3. **NAR `is_reinsurer` keyword vs separate functions.** Reviewer
   confirmed the single-helper design. No follow-up; will reconsider
   only if a fifth external-facing call site appears.

## Impact on Golden Baselines

None. The `--capital` flag is opt-in; the QA `golden_outputs/`
fixtures continue to match exactly (verified via the unchanged
`tests/qa/test_pipeline_golden.py` results and a manual run of
`polaris price --inforce data/qa/golden_inforce.csv --config
data/qa/golden_config_flat.json` which reproduced
`Total PV Profits (Cedant) = $3,513,563` and
`Total PV Profits (Reinsurer) = $45,386` byte-for-byte).
