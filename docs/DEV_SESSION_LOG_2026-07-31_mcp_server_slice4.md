# Dev Session Log — 2026-07-31

## Item Selected
- **Source:** `docs/CONTINUATION_mcp_server.md` — the active Phase-7 Tier-A epic
  (MCP Server, maintainer-constituted 2026-07-27), **Slice 4 (CLOSES EPIC)**.
- **Priority:** Tier-A epic (active Epic track, step 5b — advanced before any
  fallback pick).
- **Title:** MCP evaluations, hardening, docs — closes the MCP-server epic.
- **Slice:** 4 of 5 (the final slice).
- **Branch:** `claude/loving-gauss-e0ucmm` (environment-designated).

## Selection Rationale
Step 5 found `CONTINUATION_mcp_server` IN PROGRESS with Slice 4 marked the only
remaining slice (PLANNED). Slice 3b (`PR #176`, the streamable-HTTP transport)
**merged to `main`** — confirmed via `git fetch origin main` (HEAD `e0f7765` = the
#176 merge; my designated branch was already at that commit, a clean continuation
point). Slice 4 depends only on Slice 3 (merged) and is independent of 3b, so it
was unblocked. Per the ACTIVE-EPIC guardrail the epic is advanced before any
fallback pick; the other IN PROGRESS CONTINUATIONs (`perf_harness`,
`expense_allowance_duration`) are fallback epics not touched this session.

**Ledger healing (step 4b).** PR #176 merged since the last session log, so the
CONTINUATION's Slice 3b was healed from "DONE (draft PR #176 — awaiting merge)" to
"DONE (merged 2026-07-31)". No other PRs merged since the 2026-07-30 log.

**Premise verification (step 7b).** Reproduced the two Slice-4 gaps with the live
engine before writing code: (a) there was no eval set / golden regression on the
MCP surface (no `mcp/evals.py`, no `tests/test_mcp/test_evals.py`); (b) an
out-of-range deal param on a block tool leaked a raw
`pydantic_core.ValidationError` — `polaris_price_block(valuation_date=…,
cession_pct=1.5)` raised `1 validation error for PriceRequest … For further
information visit https://errors.pydantic.dev/…` rather than an actionable
`ToolError`, because `build_*_request_from_block` constructs the request *outside*
the tool's `try/except`. Both premises confirmed.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Service-layer extraction (`run_price`) | ✅ Done | #173 (merged) |
| 2 | MCP server + core `polaris_price_block` tool (stdio) | ✅ Done | #174 (merged) |
| 3 | Scenario + UQ service extraction + MCP tools | ✅ Done | #175 (merged) |
| 3b | Streamable-HTTP transport | ✅ Done | #176 (merged) |
| 4 | Evals, hardening, docs (**closes epic**) | ✅ Done | #177 (draft) |

## What Was Done
Shipped `src/polaris_re/mcp/evals.py` — a committed, importable 10-question eval
set (`EVAL_SET`). Each question is an immutable `MCPEval` (the natural-language
question, the tool or resource to call, arguments, and the pinned answer expressed
as dotted-path expectations: `expected_numeric` compared with a relative tolerance
for floats, `expected_equals` exact for ints / strings / lists / `None`,
`summary_contains` for the one-line headline, and `expect_error_contains` for the
error question). `run_eval` / `run_eval_set` execute the set through the real
`mcp.call_tool` / `read_resource` path, so it doubles as a golden regression on the
MCP surface. The ten cover all four tools (`polaris_price_block` YRT / gross-only /
coinsurance / LICAT-capital / whole-life; `polaris_run_scenario` base-vs-mortality
shock; `polaris_run_uq` seeded band + seeded reproducibility), the
`polaris://capabilities` resource, and the actionable bad-path error. Every
question pins an explicit `valuation_date` (ADR-074).

Hardened the three block tools: `build_price_request_from_block` /
`build_scenario_request_from_block` / `build_uq_request_from_block` now wrap the
`*Request(...)` construction in `except ValidationError` and re-raise via a shared
`_actionable_param_error()` — a `ToolError` naming each offending field, the
constraint that was violated (which states the valid range), and the rejected
value, pointing at `polaris://capabilities`, with the `errors.pydantic.dev` URL
stripped. `polaris_price` (inline `PriceRequest`) needs no new guard — FastMCP
validates its schema before the body runs.

Docs: added ARCHITECTURE.md §8 "Service Layer & MCP Server (agent access)"
(renumbering the old §8 to §9); added ADR-174; finalized the README (Status line,
MCP row in the module table, a "Connect an AI agent (MCP)" example, `mcp/` in the
tree, ADR range → 174, test count → 2,730+); and finalized QUICKSTART §10 (an
"actionable errors" note + a "Step 5 — run the committed eval set" subsection).

Harvested to `PRODUCT_DIRECTION_2026-07-24` and **closed the CONTINUATION**
(IN PROGRESS → COMPLETE) after harvesting.

## Files Changed
- `src/polaris_re/mcp/evals.py` — new eval module (`MCPEval` / `EvalResult` /
  `run_eval` / `run_eval_set` / `EVAL_SET`).
- `src/polaris_re/mcp/server.py` — `ValidationError` import; `_actionable_param_error`;
  the three `build_*_request_from_block` helpers wrap request construction.
- `src/polaris_re/mcp/__init__.py` — export the eval surfaces.
- `docs/DECISIONS.md` — ADR-174.
- `ARCHITECTURE.md` — new §8 (Service Layer & MCP Server); old §8 → §9.
- `README.md` — Status + module table + MCP example + tree + ADR range + test count.
- `docs/QUICKSTART.md` — §10 actionable-errors note + Step 5 (eval set).
- `docs/CONTINUATION_mcp_server.md` — Slice 3b healed to merged; Slice 4 DONE;
  Status → COMPLETE (epic closed).
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — Slice-4 harvest subsection.

## Tests Added
- `tests/test_mcp/test_evals.py` (new, +20): the set's shape (10 questions, unique
  ids, exactly-one-surface, all four tools + the resource covered, an error
  question, every price eval pins a date); every eval runs green through the live
  engine (parametrized); runner tamper-detection (a wrong pinned value fails; a
  never-raised error fails); the `expected_equals` float guard (a float there fails;
  the shipped `EVAL_SET` never uses one) — **the +2 added by the PR-review [P2]
  follow-up**.
- `tests/test_mcp/test_server.py` (+10): out-of-range param → actionable `ToolError`
  on `polaris_price_block` (cession / discount / horizon — field named, valid range
  shown, no pydantic URL) and on `polaris_run_scenario` / `polaris_run_uq`.
- MCP suite 81 → 111; MCP + qa together **205 passed**, 0 failures (the feature
  commit was 109 / 203; the [P2] follow-up added +2 eval tests).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| 10-question eval set committed and green | ✅ | `EVAL_SET` (10); `test_evals.py` green through `mcp.call_tool` |
| Eval set covers all tools + resource + error path | ✅ | 4 tools, `polaris://capabilities`, seeded-UQ reproducibility, bad-path error |
| Actionable out-of-range param errors | ✅ | all three block tools; field + valid range + value; no pydantic URL |
| Bad file path → actionable guidance | ✅ | already Slice-2; asserted by the error eval |
| ARCHITECTURE.md MCP section | ✅ | new §8 "Service Layer & MCP Server" |
| README/QUICKSTART finalized | ✅ | README MCP example + module row; QUICKSTART §10 Step 5 |
| CONTINUATION COMPLETE, backlog harvested | ✅ | harvested first (step 17), then IN PROGRESS → COMPLETE |
| Goldens byte-identical | ✅ | `polaris price` flat: cedant $3,513,563 / reinsurer $45,386; `tests/qa/` 94 passed |
| Quality gate (ruff format+check, fast suite, qa) | ✅ | ruff clean; MCP 111 + qa 94 = 205 passed |

## Open Questions / Follow-ups
- **MCP eval CLI + CI gate + rendered report.** `EVAL_SET` is importable and green
  in CI via pytest, but there is no headless `polaris mcp-eval` runner /
  Markdown-report / non-zero-exit gate (the `polaris benchmark` pattern). Harvested
  NICE-TO-HAVE (ADR-174 Out of scope, 1st-order).
- **`.mcp.json` relative-path resolution unverified end-to-end.** The Slice-2
  follow-up asked to verify `--directory .` / `./data` on a real Claude Code host
  during Slice-4 hardening; the CI sandbox cannot spawn one, so it remains
  unverified (the absolute-path `claude mcp add` fallback is documented). Already
  promoted — status note only, no re-promotion.
- **`perf_harness` / `expense_allowance_duration` still IN PROGRESS** — unchanged
  fallback epics, not touched (the active MCP epic consumed the session). With the
  MCP epic now COMPLETE, the next routine run has no active Tier-A epic and step 5b
  will either advance one of these fallback CONTINUATIONs or start the next epic
  from the latest COMMERCIAL_VIABILITY_REVIEW.

## Parked Polish
None. ADR-174's out-of-scope items are 1st-order follow-ups of the (planned) eval
set / hardening, harvested normally; the other out-of-scope items (fold HTTP auth
into `[mcp]`, post-epic tool surface, store-authoring, prompts, MCPB) were already
harvested by earlier slices and are not re-promoted.

## Impact on Golden Baselines
None. Purely additive — a new eval module + config helpers + error-wrapping; no
`src/` pricing code changed. `polaris price` on `golden_config_flat.json` is
byte-identical (cedant PV $3,513,563.42, reinsurer PV $45,386.44); `tests/qa/` 94
passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2733 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; SOA VBT /
CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline). The prior log (`DEV_SESSION_LOG_2026-07-30`) recorded 2728 after
Slice 3b; the +5 delta is PR #176's post-merge review-fix commit (`4819bb5`, "accept
every transport spelling"), now on `main` — no NEW or CHANGED failure, so the
session PROCEEDED. This slice adds 30 fast tests (20 eval + 10 hardening; the eval
count is 18 from the feature commit + 2 from the [P2] follow-up below).

## Post-Review Follow-up (PR #177)
The automated PR-review routine returned **APPROVE — no blockers** on the feature
commit (`b4c61e1`; CI run #598 green: 2756 passed, 3 skipped, 0 failures), with one
non-blocking **[P2]**: guard `run_eval`'s `expected_equals` path against a float
`==` (CLAUDE.md forbids float `==`). Addressed in `6cfa0ee` — `run_eval` now flags a
float in `expected_equals` as a failure directing the author to `expected_numeric`
(`math.isclose`); the `MCPEval.expected_equals` field docstring records the
constraint; two tests lock it in (a float in `expected_equals` fails; the shipped
`EVAL_SET` never uses one). Additive, no pricing code touched, goldens byte-identical.
Replied on the PR thread. The count/quality-gate figures above are updated to the
post-follow-up totals (eval 20, MCP 111, MCP+qa 205).
