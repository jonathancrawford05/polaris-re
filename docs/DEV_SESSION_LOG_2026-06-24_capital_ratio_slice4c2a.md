# Dev Session Log — 2026-06-24 (Available-capital numerator on CLI + API, Epic 3 Slice 4c-2a)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 4c-2; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** Thread the `available_capital` solvency-ratio numerator through the
  CLI + API machine surfaces (the first half of ratio *surfacing*).
- **Slice:** 4c-2a of 4c-2 (Slice 4c-2 re-decomposed into 4c-2a / 4c-2b / 4c-2c)
- **Branch:** `claude/awesome-bardeen-yqv16z` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 4c-1 (PR #102) is merged to `main` (`origin/main`
HEAD `11dfe61` = the PR #102 merge; the designated branch already sits there), so
the next slice is unblocked. No open PRs to address first (`list_pull_requests
state=open` → empty); no fallback considered — the guardrail forbids falling back
while the active Epic's next slice can advance, and it can.

The planned Slice 4c-2 (ratio surfacing across CLI + API + Excel + dashboard, plus
a three-standard validation notebook) proved LARGE once read in detail: five
surfaces, two of them presentation rebuilds (an Excel ratio row, a dashboard
number-input + tile) and a notebook. Per the routine's allowance for a slice that
proves larger than expected (the same allowance under which 4 → 4a/4b/4c and
4c → 4c-1/4c-2 were split), 4c-2 was re-decomposed into **4c-2a — the CLI + API
machine surfaces** this session, **4c-2b — Excel ratio row + dashboard input/tile**
next, and **4c-2c — the validation notebook**. This mirrors the machine-then-
presentation split the epic already used at 4a (machine) / 4b (presentation).
4c-2a is the smaller, fully-pytest-testable half (no presentation rebuild, no
golden rebaseline) and unblocks the dashboard/Excel work.

## Verify Premise (step 7b)

Reproduced before writing code: `grep available_capital|capital_ratio
src/polaris_re/cli.py src/polaris_re/api/main.py` returned nothing on both files.
4c-1 (ADR-103) computes the ratio on `ProfitResultWithCapital`, but the CLI had
no `--available-capital` flag and never passed `available_capital` to
`run_with_capital`, and the API request had no field and the response had no
`capital_ratio`. The machine surfaces genuinely did not exist; the premise holds.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ✅ Done | #99 |
| 4a | CLI + API `--capital {licat,rbc,solvency2}` selector | ✅ Done | #100 |
| 4b | Dashboard selector + Excel jurisdiction label | ✅ Done | #101 |
| 4c-1 | Result-level capital-ratio core (protocol + `ProfitTester`) | ✅ Done | #102 |
| 4c-2a | CLI + API available-capital numerator + ratio surfacing | ✅ Done | (this PR) |
| 4c-2b | Excel ratio row + dashboard input/tile | ⏳ Next | — |
| 4c-2c | Three-standard validation notebook | 🔲 Planned | — |

## What Was Done

Threaded the `available_capital` solvency-ratio numerator (added to the analytics
in 4c-1) through the two machine surfaces so the ratio 4c-1 computes is finally
visible.

**CLI.** A new `polaris price --available-capital FLOAT` flag, validated eagerly:
it requires `--capital` (a ratio has no denominator without a jurisdiction) and
must be positive — either misuse exits 1 with a clear message rather than being
silently ignored. The numerator flows `price_cmd` → `_price_single_cohort` →
`_run_profit_tests` → both sides' `run_with_capital(..., available_capital=)`. The
JSON capital block (`_profit_test_to_dict`) gains the echoed `available_capital`
and `capital_ratio`, and the Rich capital table (`_append_capital_rows`) gains a
"Solvency Ratio" row, shown only when the numerator was supplied.

**API.** A new `PriceRequest.available_capital` field (`gt=0`) with a
`model_validator` that rejects (422) the field without `capital_model`. Threaded
into both `run_with_capital` calls; `_capital_block` and the response gain
`available_capital`, `capital_ratio` (cedant) and `reinsurer_capital_ratio`
(reinsurer).

The same supplied numerator is applied to **both** the cedant and reinsurer
perspectives, each dividing it by its own required-capital denominator (LICAT
total / RBC ACL / EU SCR), so the two ratios differ and are individually
meaningful. This is symmetric with how peak capital and RoC are already surfaced
for both sides from the same model, and it requires no assumption about how to
split capital between the parties. Recorded as ADR-104.

## Files Changed

- `src/polaris_re/cli.py` — `--available-capital` flag + eager validation;
  `available_capital` threaded through `_price_single_cohort` /
  `_run_profit_tests`; `capital_ratio` / `available_capital` in
  `_profit_test_to_dict`; "Solvency Ratio" row in `_append_capital_rows`.
- `src/polaris_re/api/main.py` — `PriceRequest.available_capital` field +
  `_available_capital_requires_capital_model` validator; `capital_ratio` /
  `reinsurer_capital_ratio` response fields; threaded into both
  `run_with_capital` calls; `_capital_block` extended.
- `docs/DECISIONS.md` — ADR-104.
- `docs/PLAN_cross_jurisdiction_capital.md`,
  `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 4c-2 re-decomposed
  into 4c-2a (DONE) / 4c-2b / 4c-2c.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — re-pointed the result-level ratio
  follow-up: machine surfaces shipped in 4c-2a, presentation → 4c-2b, notebook →
  4c-2c.
- `docs/DEV_SESSION_LOG_2026-06-24_capital_ratio_slice4c2a.md` — this log.

## Tests Added

- `tests/test_analytics/test_cli.py::TestPriceCommandAvailableCapital` (6):
  `capital_ratio` + echoed `available_capital` in JSON; ratio linear in the
  numerator (double available → double ratio, denominator fixed); "Solvency
  Ratio" console row; `--available-capital` without `--capital` exits 1;
  non-positive exits 1; `--capital` without the numerator leaves the ratio null.
- `tests/test_api/test_main.py` (5, in `TestPriceEndpoint`): ratio populated on
  both views; ratio linear in the numerator; 422 without `capital_model`; 422 on
  a non-positive numerator; null ratio when the numerator is omitted.

The ratio *computation* is closed-form tested at the analytics level in 4c-1
(`TestRunWithCapitalRatio`); these are surface-threading + linearity-property
tests (this slice adds no new analytics).

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| CLI `--available-capital` threads numerator into both sides | ✅ | JSON + Rich table |
| CLI emits `capital_ratio` + echoes `available_capital` | ✅ | `_profit_test_to_dict` |
| CLI "Solvency Ratio" console row | ✅ | `_append_capital_rows` |
| CLI rejects `--available-capital` without `--capital` / non-positive | ✅ | exit 1, clear message |
| API `available_capital` field threads into both sides | ✅ | `gt=0` |
| API emits `capital_ratio` + `reinsurer_capital_ratio` | ✅ | response + `_capital_block` |
| API rejects field without `capital_model` (422) | ✅ | `model_validator` |
| Default (no flag/field) → ratio null, byte-identical | ✅ | goldens unchanged |
| Own ADR | ✅ | ADR-104 |
| Excel ratio row + dashboard input/tile | ⏳ | deferred to Slice 4c-2b |
| Three-standard validation notebook | ⏳ | deferred to Slice 4c-2c |

## Open Questions / Follow-ups

- **Slice 4c-2b owns the presentation surfacing.** Render `result.capital_ratio`
  on the Excel capital block (a ratio row under the 4b jurisdiction header) and
  the dashboard (a number-input for available capital + a ratio tile), threading
  the numerator onto `DealPricingExport` / `CohortPricingData`. Its own ADR.
- **Held-capital basis (target multiple of ACL)** remains an open design question
  (carried from Slices 1–2); the natural companion to the dashboard input in
  4c-2b, since a target-multiple flag is one candidate form of the numerator
  (an alternative to the absolute figure 4c-2a accepts).

## Parked Polish

None. All out-of-scope items map to the planned Slices 4c-2b / 4c-2c, the
existing held-capital-multiple follow-up, or the C0 Asset/ALM calibration epic —
none are 3rd-order polish requiring parking.

## Impact on Golden Baselines

None. The CLI flag and the API field default to None → `capital_ratio` is None
and the two new fields are additive nulls; the `--capital`-only path (which
already emits the capital block) and the default no-capital path are
byte-identical to ADR-103. The golden `polaris price` run passes no `--capital`,
so it emits no capital block at all and is structurally unchanged. QA golden
suite (72) green. No baseline regenerated.

## Harvest (step 17)

ADR-104 "Out of scope" yields three items, **all already tracked** — none newly
promoted (same disposition as the Slice 3 / 4b / 4c-1 harvests):
- Excel ratio row + dashboard input/tile → tracked as Slice 4c-2b in the PLAN /
  CONTINUATION, and the result-level-ratio Promoted Follow-up in
  `PRODUCT_DIRECTION_2026-06-18` was re-pointed this session (machine surfaces
  shipped in 4c-2a, presentation → 4c-2b, notebook → 4c-2c).
- Three-standard validation notebook → tracked as Slice 4c-2c.
- Held-capital basis (target multiple of ACL) → already an Open Question in the
  CONTINUATION (carried from Slices 1–2).

**Post-session addendum (PR #103 review harvest).** The automated review of this
PR surfaced one P2 finding NOT introduced by #103: `data/qa/` ships four pricing
configs but `tests/qa/golden_outputs/` pins byte-level baselines for only two
(`flat`, `yrt`) — the `coins` and `policy_cession` pipeline paths are covered by
CLI smoke tests only, so a silent numeric regression in the coinsurance reserve
transfer or policy-cession weighting would pass the QA suite. Promoted to
`PRODUCT_DIRECTION_2026-06-18` Promoted Follow-ups as **IMPORTANT** with the
config-driven, drift-guarded fix plan (Option A) and provenance
*"Source: PR #103 automated review — P2 finding (1st-order)."* To be implemented
as its own dedicated test-infra PR off main (not in #103's scope).

Ledger healing (step 4b): PR #102 (Slice 4c-1) merged since the last session is
the Epic 3 parent slice (the epic stays IN PROGRESS, correctly un-struck); it is
not a discrete PRODUCT_DIRECTION queue entry to strike. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-yqv16z`, HEAD at `11dfe61` (PR #102 merge =
`origin/main`). Baseline fast suite (`pytest -m "not slow"`, exit 0): **1646
passed, 99 deselected** (CIA tables MISSING from pymort as usual; SOA + CSO
converted) — matches the prior session's recorded post-change count exactly, so
no NEW/CHANGED failures; proceeded per the tolerance-aware check. Post-change:
affected modules (test_cli + test_main + test_profit_test + test_capital +
test_rbc + test_solvency2) **298 passed** (+11 new tests), QA golden suite
**72 passed**.
