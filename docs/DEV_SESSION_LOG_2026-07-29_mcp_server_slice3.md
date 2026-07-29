# Dev Session Log — 2026-07-29

## Item Selected
- **Source:** `docs/CONTINUATION_mcp_server.md` — the active Phase-7 Tier-A epic
  (MCP Server, maintainer-constituted 2026-07-27), **Slice 3**.
- **Priority:** Tier-A epic (active Epic track, step 5b — advanced before any
  fallback pick).
- **Title:** MCP scenario + UQ tools over an extended service layer.
- **Slice:** 3 of 5 (Slice 3 split into 3 + 3b this session — see below).
- **Branch:** `claude/loving-gauss-mlp5ki` (environment-designated).

## Selection Rationale
Step 5 found three IN PROGRESS CONTINUATIONs: `mcp_server`, `perf_harness`, and
`expense_allowance_duration` (only its optional 2nd-order Slice 3 remains,
promoted NICE-TO-HAVE), plus the parked `reserve_basis_correctness`. The **MCP
Server epic is the active Phase-7 Tier-A epic** (maintainer sign-off 2026-07-27,
`PLAN_mcp_server.md`), which outranks the `perf_harness` epic — that was a gated
*fallback* pick made during maintenance mode (see `DEV_SESSION_LOG_2026-07-28`),
before the MCP epic ended maintenance mode. Per the ACTIVE-EPIC guardrail, with
the MCP epic's next slice advanceable I advanced it and did not touch fallback
work.

Slice 2 (`polaris_price_block` / `polaris_price`) merged as **PR #174**
(2026-07-28) — confirmed on `main` via `git log` — so Slice 3 was unblocked. The
CONTINUATION still showed Slice 2 "awaiting merge" (stale); healed to "merged
(PR #174)" this session (ledger-healing, step 4b).

**Premise verification (step 7b).** Confirmed the gap holds: before this slice,
`run_scenario` / `run_uq` did **not** exist — the scenario and UQ engine logic
lived inline in the FastAPI `POST /api/v1/scenario` and `/api/v1/uq` route bodies
(read directly), so the MCP server had no shared path to wrap. `mcp.list_tools()`
returned only the two Slice-2 pricing tools. Premise confirmed.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Service-layer extraction (`run_price`) | ✅ Done | #173 |
| 2 | MCP server + core `polaris_price_block` tool (stdio) | ✅ Done | #174 |
| 3 | Scenario + UQ service extraction + MCP tools | ✅ Done | #175 (draft) |
| 3b | Streamable-HTTP transport (split from Slice 3) | ⏳ Next | — |
| 4 | Evals, hardening, docs (closes epic) | 🔲 Planned | — |

**Slice 3 was split.** The plan bundled the streamable-HTTP transport into
Slice 3. To keep this PR to one reviewable, byte-identical change centred on the
higher-value analytics tools (stress a block, read the profit band), the HTTP
transport was carved out to an epic-internal **Slice 3b** (still tracked in the
CONTINUATION, still LOCKED decision #1: a transport of the same in-process server,
not a proxy). stdio remains the only transport — which is what Claude Code /
Claude Desktop spawn — so the split loses no shipped capability.

## What Was Done
Extended the service layer the same way Slice 1 extracted `run_price`: moved the
`ScenarioRequest` / `ScenarioSummary` / `ScenarioResponse` / `UQRequest` /
`UQResponse` contracts and the perspective-resolution helper (`_resolve_perspective`,
ADR-078) out of `api/main.py` into `services/pricing.py`, and added
`run_scenario(ScenarioRequest) -> ScenarioResponse` and
`run_uq(UQRequest) -> UQResponse` holding the verbatim engine logic (build
components → gross projection → treaty → `ScenarioRunner` / `MonteCarloUQ`). The
`/api/v1/scenario` and `/api/v1/uq` routes are now thin adapters that delegate and
map any domain error to HTTP 422 — observably byte-identical, since the prior
inline bodies already re-wrapped every error into 422. `api/main.py` re-imports
the moved contracts, so every prior import path (e.g.
`from polaris_re.api.main import ScenarioRequest, UQRequest`, used by the existing
perspective tests) and the OpenAPI schema are unchanged; the now-unused top-level
`ScenarioRunner` / `MonteCarloUQ` / `UQParameters` / `YRTTreaty` / `_derive_yrt_rate`
imports were removed.

Added two MCP tools mirroring the Slice-2 pattern: `polaris_run_scenario`
(standard stress set) and `polaris_run_uq` (Monte-Carlo bands), each taking an
inforce reference + high-level deal params. A shared `_load_block_policies` helper
(refactored out of `build_price_request_from_block`) resolves, filters, and
re-values the block once for all three tools so their loading semantics cannot
drift. Each tool returns a compact wrapper (`ScenarioBlockResult` /
`UQBlockResult`: a `summary` headline + the full typed response); the scenario /
UQ responses are already compact (a summary list / scalar percentiles), so no
array gating is needed. Required `valuation_date` on both (ADR-074) and a `seed`
on UQ make quotes reproducible. Recorded **ADR-172**.

## Files Changed
- `src/polaris_re/services/pricing.py` — added `Scenario*` / `UQ*` contracts,
  `_resolve_perspective`, `run_scenario`, `run_uq`; updated `__all__` + docstring.
- `src/polaris_re/services/__init__.py` — export the new contracts + run functions.
- `src/polaris_re/api/main.py` — removed the duplicate contract classes +
  `_resolve_api_perspective`; scenario/uq routes now delegate to the service;
  re-import moved contracts; dropped now-unused imports.
- `src/polaris_re/mcp/server.py` — `_load_block_policies` refactor;
  `build_scenario_request_from_block` / `build_uq_request_from_block`;
  `ScenarioBlockResult` / `UQBlockResult`; `polaris_run_scenario` /
  `polaris_run_uq` tools; scenario/uq summariser helpers; updated instructions +
  `__all__` + docstring.
- `src/polaris_re/mcp/__init__.py` — export the new builders + result wrappers.
- `docs/DECISIONS.md` — ADR-172.
- `docs/CONTINUATION_mcp_server.md` — Slice 2 healed to merged (PR #174); Slice 3
  DONE; new Slice 3b (HTTP transport split); total slices 4 → 5.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — Slice-3 harvest note (no new loose
  items; HTTP transport / evals tracked as epic slices, not promoted).

## Tests Added
- `tests/test_services/test_pricing.py` — `TestRunScenarioContract` (3),
  `TestRunUQContract` (3, incl. seed reproducibility), and
  `TestScenarioUQRouteServiceParity` (9 incl. parametrized route↔service parity +
  422 mapping). +15.
- `tests/test_mcp/test_server.py` — `TestScenarioUQRegistration` (7),
  `TestScenarioToolParity` (7), `TestUQToolParity` (6, incl. seed reproducibility),
  `TestScenarioUQActionableErrors` (3). +23.
- +38 fast tests total; no existing assertion changed.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `run_scenario` / `run_uq` extracted into the web-framework-free service | ✅ | `services/pricing.py`; scenario/uq routes are thin 422-mapping adapters |
| Scenario/uq route ↔ service parity | ✅ | `TestScenarioUQRouteServiceParity` — route JSON == direct `run_*` JSON |
| `polaris_run_scenario` / `polaris_run_uq` MCP tools | ✅ | registered; read-only annotations; structured-output schemas |
| MCP tool ↔ `run_*` ↔ REST parity | ✅ | scenario + uq parametrized parity tests |
| UQ seed reproducibility (ADR-074) | ✅ | two same-seed runs byte-identical (service + tool) |
| Reinsurer→cedant perspective downgrade without treaty (ADR-078) | ✅ | service + tool tests |
| Actionable errors (bad treaty / product) | ✅ | domain error → `ToolError` with guidance |
| Goldens byte-identical | ✅ | `polaris price` flat config exit 0 ($45,386 reinsurer PV); `tests/qa/` 94 passed |
| Quality gate (ruff format+check, fast suite, qa) | ✅ | ruff clean; qa 94 passed |
| Streamable-HTTP transport + eval set | ⏳ | Slice 3b / Slice 4 (out of scope this slice) |

## Open Questions / Follow-ups
- **Slice 3 split acceptable?** The plan bundled the streamable-HTTP transport
  into Slice 3; this session split it to an epic-internal Slice 3b to keep the PR
  to the higher-value analytics tools as one byte-identical change. 3b and Slice 4
  are independent and can be sequenced either way. Flagged in the CONTINUATION's
  Open Questions for the maintainer.
- **`CONTINUATION_expense_allowance_duration` / `perf_harness` still IN PROGRESS.**
  Unchanged carry-forward: the expense-allowance-duration epic has only its
  optional 2nd-order Slice 3 left (already NICE-TO-HAVE); the perf-harness epic
  (Slices 2–4) is a fallback epic that advances only when the MCP epic is blocked.
  Neither was touched this session (the active MCP epic consumed it).

## Parked Polish
None. ADR-172's out-of-scope items are all 1st-order follow-ups of the active MCP
epic and are tracked as the epic's own later slices (3b, 4) in
`CONTINUATION_mcp_server.md`, or were already harvested as post-epic follow-ups
from ADR-171 (ifrs17/ingest/portfolio tools, MCPB packaging) — not promoted as
loose PRODUCT_DIRECTION items and not parked.

## Impact on Golden Baselines
None. An engine-neutral service extraction (verbatim move; the routes still
produce the identical `ScenarioResponse` / `UQResponse`) plus two new additive MCP
tools off the pricing path. No `src/` pricing code changed, so every golden config
and `polaris price` output is byte-identical. Confirmed: `polaris price` on
`golden_config_flat.json` exit 0 (reinsurer PV $45,386, unchanged); `tests/qa/`
94 passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2667 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; SOA VBT /
CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline). The passed count rose 2609 → 2667 vs the prior session log because MCP
Slices 1–2 (PRs #173/#174) merged in between, adding their tests. No new or changed
failures, so the session PROCEEDED. This slice adds 38 fast tests (15 service +
23 MCP); full fast suite after: **2705 passed, 3 skipped, 124 deselected**, 0
failures.
