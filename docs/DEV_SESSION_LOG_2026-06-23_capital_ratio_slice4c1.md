# Dev Session Log — 2026-06-23 (Result-level capital-ratio core, Epic 3 Slice 4c-1)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 4c; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** Result-level regulatory solvency-ratio surface (the core: protocol
  method + `ProfitTester` integration)
- **Slice:** 4c-1 of 4c (Slice 4c re-decomposed into 4c-1 / 4c-2)
- **Branch:** `claude/awesome-bardeen-bsrsuk` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 4b (PR #101) is merged to `main` (`origin/main`
HEAD `b00cbc7` = the PR #101 merge; the designated branch already sits there), so
the next slice is unblocked. No open PRs to address first (`list_pull_requests
state=open` → empty); no fallback considered — the guardrail forbids falling back
while the active Epic's next slice can advance, and it can.

The planned Slice 4c (result-level ratio surface across the result + CLI + API +
Excel + dashboard, plus a three-standard validation notebook) proved LARGE once
read in detail: a contract change to the `CapitalSchedule` protocol + the result,
threaded through four consumers, plus a notebook. Per the routine's allowance for
a slice that proves larger than expected (the same allowance under which 4a/4b/4c
were split), 4c was re-decomposed into **4c-1 — the result-level ratio CORE (data
model first)** this session and **4c-2 — ratio surfacing (CLI/API/Excel/dashboard)
+ validation notebook** next. 4c-1 is the actuarially-sensitive, riskiest piece
(the per-jurisdiction ratio definitions); shipping it first as a focused,
closed-form-tested, byte-identical-goldens PR unblocks all the surfacing.

## Verify Premise (step 7b)

Reproduced before writing code (a `dataclasses.fields` / `inspect.signature`
probe): `ProfitResultWithCapital` carried no ratio field and
`ProfitTester.run_with_capital(self, capital_model, *, nar=None)` had no
available-capital input. `RBCResult.rbc_ratio(tac)` existed on the raw schedule
but was unreachable from the jurisdiction-agnostic result, and no
`capital_ratio` / `solvency_ratio` / `available_capital` existed anywhere in
`src/`. The result-level ratio surface genuinely did not exist; the premise holds.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ✅ Done | #99 |
| 4a | CLI + API `--capital {licat,rbc,solvency2}` selector | ✅ Done | #100 |
| 4b | Dashboard selector + Excel jurisdiction label | ✅ Done | #101 |
| 4c-1 | Result-level capital-ratio core (protocol + `ProfitTester`) | ✅ Done | _(this PR)_ |
| 4c-2 | Ratio surfacing (CLI/API/Excel/dashboard) + validation notebook | ⏳ Next | — |

## What Was Done

Added the regulatory solvency ratio as a jurisdiction-agnostic surface and
threaded a single optional input through the return-on-capital entry point,
keeping the per-jurisdiction denominator encapsulated on each result class.

**Protocol.** `CapitalSchedule` gained a `capital_ratio(available_capital) ->
float` method — the standard's solvency ratio at issue, `available_capital /
denominator₀`, as a multiple.

**Three result classes.** Each implements `capital_ratio` with its own
denominator: `CapitalResult` (LICAT) and `SolvencyIIResult` divide by
`capital_by_period[0]` (required capital / SCR); `RBCResult` divides by
`authorized_control_level[0]` (ACL = ½ the Company Action Level it holds). All
three raise `PolarisComputationError` on a non-positive t=0 denominator (an
all-stub factor set). `RBCResult.rbc_ratio` became a thin RBC-named alias of
`capital_ratio`, so existing callers/tests are unaffected.

**Integration.** `ProfitTester.run_with_capital` gained an optional
`available_capital: float | None = None` keyword; when supplied, the ratio is
computed via `capital.capital_ratio(...)` and surfaced on the two new
`ProfitResultWithCapital` fields `available_capital` / `capital_ratio` (both
default `None`). When omitted (the default and every current caller), both fields
are `None` and the entire RoC path is byte-identical. Recorded as ADR-103.

The choice of a protocol *method* over a `ratio_denominator` *attribute* is
deliberate: the numerator (available capital) is uniform across jurisdictions,
but the denominator is the genuine jurisdictional difference (ACL is half the
held capital for RBC; the held capital itself for LICAT / Solvency II).
Encapsulating the whole ratio behind one method keeps "RBC divides by half" in
the result class that owns it, out of the consumer.

## Files Changed

- `src/polaris_re/analytics/capital_base.py` — `CapitalSchedule.capital_ratio`
  protocol method.
- `src/polaris_re/analytics/capital.py` — `CapitalResult.capital_ratio` (LICAT
  total ratio).
- `src/polaris_re/analytics/rbc.py` — `RBCResult.capital_ratio`; `rbc_ratio`
  became an alias.
- `src/polaris_re/analytics/solvency2.py` — `SolvencyIIResult.capital_ratio` (EU
  solvency ratio).
- `src/polaris_re/analytics/profit_test.py` — `run_with_capital(...,
  available_capital=...)`; `ProfitResultWithCapital.available_capital` /
  `.capital_ratio` fields.
- `docs/DECISIONS.md` — ADR-103.
- `docs/PLAN_cross_jurisdiction_capital.md`,
  `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 4c re-decomposed,
  4c-1 DONE, 4c-2 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — re-pointed the result-level ratio
  follow-up: core shipped in 4c-1, surfacing → 4c-2.
- `docs/DEV_SESSION_LOG_2026-06-23_capital_ratio_slice4c1.md` — this log.

## Tests Added

- `tests/test_analytics/test_profit_test.py::TestRunWithCapitalRatio` (6): ratio
  None when `available_capital` omitted (backward compat); LICAT total ratio =
  available / required₀; RBC ratio = TAC / ACL₀; EU solvency ratio = own funds /
  SCR₀; supplying `available_capital` disturbs none of the RoC / base fields; a
  zero-capital model raises on the ratio.
- `tests/test_analytics/test_capital.py::TestCapitalResult` (2): LICAT ratio
  closed form + zero-required-capital raise.
- `tests/test_analytics/test_rbc.py::TestRBCResultHelpers` (2): `capital_ratio`
  == `rbc_ratio` (alias) + ACL-zero raise.
- `tests/test_analytics/test_solvency2.py::TestSolvencyRatio` (2): own-funds/SCR
  closed form + SCR-zero raise.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Jurisdiction-agnostic ratio on the schedule protocol | ✅ | `CapitalSchedule.capital_ratio` |
| LICAT total ratio = available / required₀ | ✅ | closed-form test |
| RBC ratio = TAC / ACL₀ | ✅ | closed-form test; `rbc_ratio` alias |
| EU solvency ratio = own funds / SCR₀ | ✅ | closed-form test |
| Ratio surfaced on `ProfitResultWithCapital` | ✅ | `available_capital` / `capital_ratio` |
| Optional input, default None → byte-identical | ✅ | RoC/base fields unchanged when omitted |
| Zero-denominator raises (not a silent 0/0) | ✅ | per-jurisdiction raise tests |
| Own ADR | ✅ | ADR-103 |
| Ratio *surfacing* (CLI/API/Excel/dashboard) + notebook | ⏳ | deferred to Slice 4c-2 |

## Open Questions / Follow-ups

- **Slice 4c-2 owns the ratio surfacing.** Thread `available_capital` in from the
  CLI (`--available-capital` or a target-multiple flag), the API request field,
  and the dashboard number-input, and render `result.capital_ratio` on the Excel
  capital block (a ratio row under the 4b jurisdiction header) and the dashboard
  tiles. ADR-104. The ratio computation is done — 4c-2 is collection + display
  only, no further analytics.
- **Held-capital basis (target multiple of ACL)** remains an open design question
  (carried from Slices 1–2); natural to resolve in 4c-2 alongside the CLI input,
  since a target-multiple flag is one candidate form of the `available_capital`
  numerator.

## Parked Polish

None. All out-of-scope items map to the planned Slice 4c-2, the existing
held-capital-multiple follow-up, or the C0 Asset/ALM calibration epic — none are
3rd-order polish requiring parking.

## Impact on Golden Baselines

None. The new `run_with_capital` keyword defaults to `None`, the two new
`ProfitResultWithCapital` fields default to `None`, and no consumer supplies
`available_capital` yet (that is Slice 4c-2). Every existing call site and the
entire RoC path are byte-identical. The `polaris price` golden run is
structurally unchanged and emits no ratio. QA golden suite (72) green. No baseline
regenerated.

## Harvest (step 17)

ADR-103 "Out of scope" yields three items, **all already tracked** — none newly
promoted (same disposition as the Slice 3 / 4b harvests):
- Ratio surfacing (CLI/API/Excel/dashboard) + validation notebook → tracked as
  Slice 4c-2 in the PLAN / CONTINUATION, and the result-level-ratio Promoted
  Follow-up in `PRODUCT_DIRECTION_2026-06-18` was re-pointed this session (core
  shipped in 4c-1, surfacing → 4c-2).
- Held-capital basis (target multiple of ACL vs CAL) → already an Open Question in
  the CONTINUATION (carried from Slices 1–2).
- Shock-based factor calibration → the C0 Asset/ALM epic (CVR Tier C).
Ledger healing (step 4b): PR #101 (Slice 4b) merged since the last session is the
Epic 3 parent slice (the epic stays IN PROGRESS, correctly un-struck); it is not a
discrete PRODUCT_DIRECTION queue entry to strike. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-bsrsuk`, HEAD at `b00cbc7` (PR #101 merge =
`origin/main`). Baseline fast suite (`make test`, exit 0): **1634 passed, 99
deselected** (CIA tables MISSING from pymort as usual; SOA + CSO converted) —
matches the prior session's recorded post-change count exactly, so no NEW/CHANGED
failures; proceeded per the tolerance-aware check. Post-change: **1646 passed**
(+12 new tests), QA golden suite **72 passed**.
