# Dev Session Log — 2026-06-22 (Cross-jurisdiction capital selector — CLI + API, Epic 3 Slice 4a)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 4; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** Surface the jurisdiction selector — CLI `--capital {licat,rbc,solvency2}`
  + API `capital_model` field (Slice 4a of the planned Slice 4)
- **Slice:** 4a of 4 (Slice 4 re-decomposed into 4a machine surfaces + 4b
  presentation surfaces — see Decomposition Plan)
- **Branch:** `claude/awesome-bardeen-e4ana9` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 3 (PR #99, EU Solvency II SCR module) is merged
to `main` (`git log` shows merge commit `2344e04`, the branch HEAD), so the NEXT
slice (4) is unblocked. No open PRs to address first; no fallback considered — the
guardrail forbids falling back while the active Epic's next slice can advance, and
it can.

Slice 4 as planned (CLI + API + Excel + dashboard + validation notebook +
result-level ratio surface) is LARGE. Per the routine's allowance for a slice that
proves larger than expected once selected, it was re-decomposed into **4a** (the
two *machine* surfaces — CLI and REST API, shipped this session) and **4b** (the
*presentation* surfaces — Excel / dashboard / notebook — plus the result-level
ratio surface, which needs an external own-funds / TAC input). 4a is the highest
value-per-unit piece: it is what actually lets a reinsurer price a US or EU deal on
a return-on-capital basis from the command line or HTTP API — the calculators
existed (Slices 1–3) but no surface would select them.

## Verify Premise (step 7b)

Reproduced before writing code: `uv run polaris price --capital rbc` exits 1 with
`Error: Unknown --capital value 'rbc'. Only 'licat' is supported.`, and the API
field is typed `Literal["licat"]` (so `rbc`/`solvency2` 422). The three
calculators all exist and satisfy `CapitalModel`, but neither machine surface
would route to them. The premise holds: the gap is purely the selector, not the
calculators.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ✅ Done | #99 |
| 4a | CLI + API `--capital {licat,rbc,solvency2}` selector (shared registry) | ✅ Done | (this PR) |
| 4b | Excel / dashboard / notebook + result-level solvency/RBC-ratio surface | ⏳ Next | — |

## What Was Done

Added a single shared jurisdiction registry in `analytics/capital_base.py` —
`SUPPORTED_CAPITAL_MODELS = ("licat", "rbc", "solvency2")`, a `CapitalModelId`
literal type alias, and `capital_model_for(model_id, product_type) -> CapitalModel`
— and routed BOTH machine surfaces through it. The factory normalises the id
(strip + lower-case) then constructs the matching calculator via its `for_product`;
the concrete-calculator imports are deferred to call time because `rbc` / `capital`
/ `solvency2` already import `capital_base` for `discount_stream` / `strain_of`, so
a module-level import here would be circular.

The CLI `--capital` validation widened from `!= "licat"` to
`not in SUPPORTED_CAPITAL_MODELS` (error message now lists the supported ids), and
`_run_profit_tests` resolves the model via `capital_model_for` instead of
constructing `LICATCapital` directly. The API `capital_model` field type widened
from `Literal["licat"]` to the shared `CapitalModelId`, and the price handler
resolves via the same factory; `LICATCapital`'s now-unused import was dropped. The
capital output block (RoC, peak capital, PV strain, capital-adjusted IRR) is
already jurisdiction-agnostic — it reads only the `CapitalSchedule` surface — so no
output-shaping code changed; RBC and Solvency II render through the same JSON /
console / API path LICAT already used. Recorded as ADR-101.

Because the default and `--capital licat` code paths are untouched, goldens are
byte-identical; only runs that explicitly request `--capital rbc` / `solvency2`
(previously an error) now produce a priced result. The two pre-existing rejection
tests used `solvency2` as the *unknown* value — now that it is valid, they move to
a still-unknown id (`bogus`); this is the one place the surface contract
legitimately changed an existing assertion, flagged by the Slice 3 session.

## Files Changed

- `src/polaris_re/analytics/capital_base.py` — `SUPPORTED_CAPITAL_MODELS`,
  `CapitalModelId`, `capital_model_for` (+ `__all__`).
- `src/polaris_re/analytics/__init__.py` — export the three new symbols.
- `src/polaris_re/cli.py` — `--capital` validation + `_run_profit_tests`
  resolution via the registry; help text + docstrings widened to the three ids.
- `src/polaris_re/api/main.py` — `capital_model` field type widened to
  `CapitalModelId`; handler resolves via the registry; dropped unused
  `LICATCapital` import; comments widened.
- `docs/DECISIONS.md` — ADR-101.
- `docs/PLAN_cross_jurisdiction_capital.md`,
  `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 4 re-decomposed
  (4a DONE, 4b NEXT).
- `docs/DEV_SESSION_LOG_2026-06-22_capital_selector_cli_api.md` — this log.

## Tests Added

- `tests/test_analytics/test_capital_base.py` (13, new): registry is exactly the
  three jurisdictions; each id resolves to its calculator class and satisfies the
  `CapitalModel` protocol; id is case-insensitive / whitespace-tolerant; unknown
  id raises `ValueError` listing the supported ids; product type drives the
  per-product factor defaults.
- `tests/test_analytics/test_cli.py`: parametrised `rbc`/`solvency2` end-to-end
  JSON tests; a three-way "distinct peak capital" test proving the selector routes
  to a genuinely different calculator (not a silent LICAT fallback); invalid-value
  test re-pointed to `bogus`.
- `tests/test_api/test_main.py`: parametrised `rbc`/`solvency2` acceptance tests;
  invalid-value 422 test re-pointed to `bogus`.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| CLI `--capital {licat,rbc,solvency2}` prices each jurisdiction | ✅ | end-to-end JSON tests, distinct peak capital |
| API `capital_model` accepts `rbc` / `solvency2` | ✅ | parametrised acceptance tests, 200 + numeric block |
| Unknown id still rejected (CLI exit 1 / API 422) | ✅ | re-pointed to `bogus` |
| Single shared registry (one place to add a jurisdiction) | ✅ | `capital_model_for` drives both surfaces |
| Default / `licat` path byte-identical | ✅ | QA golden suite 72 green, no rebaseline |
| Own ADR | ✅ | ADR-101 |
| Excel / dashboard / notebook + ratio surface | ⏳ | deferred to Slice 4b (this PR's "What This Does NOT Do") |

## Open Questions / Follow-ups

- **Slice 4b carries the result-level ratio surface.** The solvency/RBC ratio
  (own funds ÷ SCR; TAC ÷ ACL) needs an external own-funds / target-multiple input
  the RoC entry points do not hold; it lands in 4b alongside the
  Excel/dashboard/notebook surfacing. Already tracked in the CONTINUATION Slice 4b
  scope and the ADR-100/101 out-of-scope notes — not re-promoted.
- **Held-capital basis (target multiple of ACL)** and **factor calibration
  sign-off** remain open in the CONTINUATION "Open Questions (for human)" —
  unchanged this session.

## Parked Polish

None. All out-of-scope items map to the planned Slice 4b or the existing C0
Asset/ALM epic — none are 3rd-order polish requiring parking.

## Impact on Golden Baselines

None. The default (no `--capital`) and `--capital licat` code paths are untouched;
only explicit `--capital rbc` / `--capital solvency2` runs (previously errors) now
produce output. The golden `polaris price` run reproduced byte-identical and the QA
golden suite (72) passed. No baseline regenerated.

## Harvest (step 17)

ADR-101 "Out of scope" items — Excel/dashboard/notebook surfacing and the
result-level ratio surface — map to the planned Slice 4b (tracked in the
CONTINUATION), and the shock-based factor calibration maps to the existing C0
Asset/ALM epic. All are already tracked, so nothing genuinely new is promoted to
`PRODUCT_DIRECTION_2026-06-18` this session (mirroring the Slice 3 disposition).
Ledger healing (step 4b): the only PR merged since the last session log is #99
(Slice 3), the Epic 3 parent, which stays IN PROGRESS (correctly un-struck) — it
is not a discrete PRODUCT_DIRECTION queue entry to strike. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-e4ana9`, HEAD at `2344e04` (PR #99 merge).
Baseline fast suite: **1603 passed, 94 deselected** — matches the prior session's
recorded post-change count, so no NEW/CHANGED failures; proceeded per the
tolerance-aware check (CIA tables MISSING from pymort as usual; SOA + CSO
converted). Post-change: **1616 passed, 99 deselected** (+13 resolver unit tests
not-slow; +5 CLI/API capital tests slow → deselected here). QA golden suite 72
green.
