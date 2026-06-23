# Dev Session Log — 2026-06-23 (Dashboard + Excel jurisdiction surfacing, Epic 3 Slice 4b)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 4b; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** Surface the regulatory-capital jurisdiction selector on the
  dashboard + Excel (presentation surfaces)
- **Slice:** 4b of 4 (Slice 4 re-decomposed into 4a / 4b / 4c)
- **Branch:** `claude/awesome-bardeen-k05fxu` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 4a (PR #100, CLI + API jurisdiction selector)
is merged to `main` (`origin/main` HEAD `71d9802` = the PR #100 merge; the
designated branch already sits at that commit), so the next slice is unblocked.
No open PRs to address first; no fallback considered — the guardrail forbids
falling back while the active Epic's next slice can advance, and it can.

The planned Slice 4b (Excel + dashboard + notebook + result-level ratio) proved
LARGE once read in detail: four surfaces, one of them (`ProfitResultWithCapital`
ratio) a contract change needing a *new external input* (own-funds / TAC) the RoC
entry points do not hold. Per the routine's allowance for a slice that proves
larger than expected (the same allowance under which 4a was split out), 4b was
re-decomposed into **4b — presentation surfaces (dashboard + Excel)** this session
and **4c — result-level ratio surface + validation notebook** next. 4b mirrors 4a
(machine surfaces) exactly: route a presentation surface through the existing
`capital_model_for` registry, no new inputs, fully pytest-testable.

## Verify Premise (step 7b)

Reproduced before writing code (a tiny `inspect`/dataclass probe):
- `dashboard/views/pricing.py::_run_pricing_for_cohort` contained the hard-coded
  `if capital_model_id == "licat":` branch and did **not** reference
  `capital_model_for` — so any non-`licat` id (e.g. `rbc`) silently fell into the
  no-capital `else` branch and produced a plain `ProfitTestResult`. RBC / Solvency
  II were genuinely unreachable from the dashboard.
- `utils/excel_output.py::DealPricingExport` had **no** `capital_model_id` field —
  the capital block was labelled "LICAT" unconditionally regardless of the
  calculator that ran.
Both gaps are real; the premise holds. The fix surfaces both through the registry
without touching the default (no-capital) or LICAT paths.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ✅ Done | #99 |
| 4a | CLI + API `--capital {licat,rbc,solvency2}` selector | ✅ Done | #100 |
| 4b | Dashboard selector + Excel jurisdiction label | ✅ Done | #101 |
| 4c | Result-level ratio surface + three-standard validation notebook | ⏳ Next | — |

## What Was Done

Routed the two **presentation** surfaces through the same `capital_model_for`
registry Slice 4a established, so the dashboard and Excel now reach US RBC and EU
Solvency II rather than hard-coding LICAT.

**Dashboard.** The "Compute LICAT capital + RoC" checkbox became a "Regulatory
capital basis (RoC)" `selectbox` (None / LICAT (Canada) / US RBC / EU Solvency II)
mapping to a registry id via a new `_CAPITAL_MODEL_CHOICES`. The hard-coded
`_run_pricing_for_cohort` branch `if capital_model_id == "licat":` widened to
`if capital_model_id is not None:` resolving the model via `capital_model_for`
(so the LICAT path is byte-identical — `capital_model_for("licat", …)` *is*
`LICATCapital.for_product(…)`). The chosen id now rides on `CohortPricingData`,
and the cedant / reinsurer capital tiles caption the live jurisdiction and drop
the "LICAT" wording from their help text in favour of the live label.

**Excel.** `DealPricingExport` gained a `capital_model_id: str | None = None`
field (default preserves byte-identical pre-Slice-4b workbooks), and the Summary
capital block gained a "Regulatory Capital — {label}" header row directly above
the metrics. The CLI threads its `--capital` id onto the export.

**Shared labelling.** A `CAPITAL_MODEL_LABELS` dict + `capital_model_label()`
helper in `analytics/capital_base.py` is the single labelling site (co-located
with the `capital_model_for` factory it mirrors), so dashboard and Excel cannot
drift; `None` defaults to LICAT because every pre-ADR-098 capital schedule was
LICAT by construction, and an unknown id is upper-cased rather than raised
(labels are display, not a validation boundary). Recorded as ADR-102.

## Files Changed

- `src/polaris_re/analytics/capital_base.py` — `CAPITAL_MODEL_LABELS`,
  `capital_model_label()`, `__all__` additions.
- `src/polaris_re/dashboard/views/pricing.py` — `_CAPITAL_MODEL_CHOICES`,
  shared-label import, selectbox, registry-routed capital branch,
  `CohortPricingData.capital_model_id`, jurisdiction-aware tile captions/help.
- `src/polaris_re/utils/excel_output.py` — `DealPricingExport.capital_model_id`,
  capital-block jurisdiction header row.
- `src/polaris_re/cli.py` — thread `capital_model_id` onto the export builder.
- `docs/DECISIONS.md` — ADR-102.
- `docs/PLAN_cross_jurisdiction_capital.md`,
  `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 4b DONE, 4c NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — re-pointed the result-level ratio
  follow-up to Slice 4c.
- `docs/DEV_SESSION_LOG_2026-06-23_capital_jurisdiction_slice4b.md` — this log.

## Tests Added

- `tests/test_dashboard/test_pricing_capital_jurisdiction.py` (6): the choices
  map to the three registry ids + None; no-selection runs a plain profit test;
  each of licat/rbc/solvency2 yields a `ProfitResultWithCapital` with positive
  peak capital (the bug fix — RBC/Solvency II were unreachable); the three
  standards give pairwise-distinct peak capital on the same block (a guard against
  a silent collapse to one calculator — the dashboard analogue of 4a's CLI test).
- `tests/test_analytics/test_capital_base.py` — `TestCapitalModelLabels` (4):
  every supported id has a label; known/normalised ids map correctly;
  `None → LICAT`; an unknown id is upper-cased not raised.
- `tests/test_utils/test_excel_output.py` — `TestCapitalJurisdictionHeader` (5):
  header text per jurisdiction, position directly above "Peak Capital",
  `None → LICAT` default, and absence when no capital ran.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Dashboard can select LICAT / US RBC / EU Solvency II | ✅ | selectbox → `capital_model_for` |
| Dashboard RBC/Solvency II actually produce capital | ✅ | each yields `ProfitResultWithCapital` |
| Dashboard tiles name the live jurisdiction | ✅ | caption + help text from `CAPITAL_MODEL_LABELS` |
| Excel capital block names the regulatory standard | ✅ | "Regulatory Capital — {label}" header |
| Shared label map (no dashboard/Excel drift) | ✅ | `CAPITAL_MODEL_LABELS` in `capital_base.py` |
| Own ADR | ✅ | ADR-102 |
| Default + LICAT paths byte-identical | ✅ | new field defaults None; no-capital unchanged |
| Result-level ratio surface | ⏳ | deferred to Slice 4c (needs new external input) |

## Open Questions / Follow-ups

- **Slice 4c owns the result-level ratio surface.** The RBC ratio (TAC / ACL) and
  the EU solvency ratio (own funds / SCR) both need an external own-funds /
  target-multiple input the RoC entry points do not hold. 4c introduces that input
  (CLI flag + API field + dashboard number-input) and surfaces both ratios on the
  result, the Excel capital block, and the dashboard tiles.
- **Slice 4c also owns the three-standard validation notebook** comparing LICAT /
  RBC / Solvency II on the golden block (and demonstrating the ratio).
- **Held-capital basis (target multiple of ACL)** remains an open design question
  (carried from Slices 1–2); natural to resolve in 4c with the own-funds input.

## Parked Polish

None. All out-of-scope items map to the planned Slice 4c, the existing
held-capital-multiple follow-up, or the C0 Asset/ALM calibration epic — none are
3rd-order polish requiring parking.

## Impact on Golden Baselines

None. The new `DealPricingExport.capital_model_id` defaults to `None`, so existing
exports are byte-identical; the dashboard default is "None" (no capital); the
LICAT capital path resolves to the same `LICATCapital.for_product` as before. The
`polaris price` golden run (no `--capital`) is structurally unchanged and emits no
capital header. QA golden suite green. No baseline regenerated.

## Harvest (step 17)

ADR-102 "Out of scope" yields three items, **all already tracked** — none newly
promoted (same disposition as the Slice 3 harvest):
- Result-level ratio surface → already a Promoted Follow-up in
  `PRODUCT_DIRECTION_2026-06-18` (re-pointed this session from "Slice 4" to the
  explicit "Slice 4c").
- Three-standard validation notebook → tracked as Slice 4c in the PLAN /
  CONTINUATION.
- Shock-based factor calibration → the C0 Asset/ALM epic (CVR Tier C).
Ledger healing (step 4b): PR #100 (Slice 4a) merged since the last session is the
Epic 3 parent slice (the epic stays IN PROGRESS, correctly un-struck); it is not a
discrete PRODUCT_DIRECTION queue entry to strike. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-k05fxu`, HEAD at `71d9802` (PR #100 merge =
`origin/main`). Baseline fast suite (`make test`, exit 0): **1616 passed, 99
deselected** (CIA tables MISSING from pymort as usual; SOA + CSO converted) —
matches the prior session's recorded post-change count, so no NEW/CHANGED
failures; proceeded per the tolerance-aware check. Post-change: **1634 passed**
(+18 new tests).
