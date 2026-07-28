# Dev Session Log — 2026-07-28 (MCP Server — Slice 2 of 4)

## Item Selected
- **Source:** `docs/CONTINUATION_mcp_server.md` (active Phase-7 Tier-A epic;
  `docs/PLAN_mcp_server.md`, maintainer sign-off 2026-07-27).
- **Priority:** Tier-A epic (advanced before any fallback per step 5b).
- **Title:** MCP server + core `polaris_price_block` tool (stdio).
- **Slice:** 2 of 4.
- **Branch:** `claude/loving-gauss-m45k5w` (environment-designated; at
  `origin/main` post-#173).

## Selection Rationale
Step 5 found the `CONTINUATION_mcp_server.md` epic IN PROGRESS with Slice 1
merged (**PR #173**, merged 2026-07-28), so per the continuation rule the session
continued the epic on a new branch from main — no fallback pick considered. Slice
2 is the epic's next unchecked slice and was unblocked (Slice 1 is on main). No
other CONTINUATION is IN PROGRESS that would compete; the epic is the always-on
Tier-A track (step 5b).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Service-layer extraction (`run_price`) | ✅ Done | #173 (merged) |
| 2 | MCP stdio server + `polaris_price_block` / `polaris_price` / capabilities | ✅ Done (this PR — draft) | — |
| 3 | Scenario + UQ tools + streamable-HTTP transport | ⏳ Next | — |
| 4 | Evals + hardening + docs (closes epic) | 🔲 Planned | — |

## VERIFY PREMISE (step 7b)
Reproduced the gap before writing code: `find src -path '*mcp*'` returned nothing
and `uv run python -c "import mcp"` → `ModuleNotFoundError`; no `.mcp.json`, no
`polaris-mcp` entry point. The MCP surface genuinely did not exist. Confirmed the
in-process path exists: `polaris_re.services.pricing.run_price` (Slice 1, ADR-170)
is importable and web-framework-free, so the tools can wrap it directly. Premise
holds — a real capability gap, not a no-op.

## What Was Done
Built the first agent-facing surface on top of the Slice-1 service layer: an
in-process stdio **MCP server** (`src/polaris_re/mcp/server.py`) using the `mcp`
SDK's bundled FastMCP, staged into a new `[mcp]` extra (and the dev group so the
suite imports it under plain `uv run`). Three surfaces, all wrapping `run_price`
so there is one engine path and no second mapping to drift:

- **`polaris_price_block`** — the headline workflow tool. Takes an *inforce
  reference* (the built-in `"golden"` sample id → `data/qa/golden_inforce.csv`, or
  a CSV path) plus high-level deal params, mirroring the CLI's `--inforce/--config`
  ergonomics. A **required `valuation_date`** re-values the block (each policy's
  `attained_age` / `duration_inforce` re-derived from its `issue_date` via
  `months_between`, keeping ADR-074 consistency and never defaulting to
  `date.today()`). Because a single `run_price` covers one product engine and the
  golden block mixes TERM + WHOLE_LIFE, the loader **filters to the policies whose
  `product_type` matches** (`n_policies` reflects the filtered count; a block with
  no match raises an actionable error naming the types present).
- **`polaris_price`** — the full inline-`PriceRequest` tool for programmatic
  callers; FastMCP derives its input schema straight from the Pydantic contract.
- **`polaris://capabilities`** — a resource enumerating the priceable product
  types (TERM / WHOLE_LIFE / UL — the dispatch registry, *not* the full enum, so
  DI/CI/ANNUITY are not advertised), treaty types, capital models, reserve bases,
  and sample-block ids.

Every pricing tool returns a compact-by-default `PriceBlockResult` (`summary`
headline + full typed `price`; the large per-year profit arrays are cleared unless
`detail=true`, at which point `price` is byte-identical to `run_price` and the
API), carries read-only annotations, and maps domain failures to actionable
`ToolError`s. Added the `polaris-mcp` console entry point, a committed
project-scope `.mcp.json` (with the `.mcp.json` COPY into the Dockerfile so the
in-image test suite finds it), and a QUICKSTART §10 "Connect from Claude Code /
Claude Desktop" walkthrough (pre-warm, Inspector smoke-test, `claude mcp add`,
verify, debug gotchas). ADR-171.

## Files Changed
- `src/polaris_re/mcp/__init__.py` (new — package API)
- `src/polaris_re/mcp/server.py` (new — FastMCP server, tools, resource, `main`)
- `.mcp.json` (new — committed project-scope MCP registration)
- `pyproject.toml` (`[mcp]` extra + dev-group `mcp`; `polaris-mcp` console script)
- `uv.lock` (mcp 1.28.1 resolved; `uv lock --check` clean for CI `--frozen`)
- `Dockerfile` (COPY `.mcp.json` into the runtime image)
- `docs/DECISIONS.md` (ADR-171)
- `docs/QUICKSTART.md` (§10 MCP section + TOC entry)
- `docs/CONTINUATION_mcp_server.md` (Slice 1 → merged #173; Slice 2 → Done; Slice 3 → NEXT)
- `docs/PRODUCT_DIRECTION_2026-07-24.md` (Promoted Follow-ups — harvest)
- `docs/DEV_SESSION_LOG_2026-07-28_mcp_server_slice2.md` (this file)

## Tests Added
- `tests/test_mcp/__init__.py` (new package)
- `tests/test_mcp/test_server.py` (new — 35 tests): tool registration +
  read-only annotations + structured-output schemas + `valuation_date` required;
  `polaris_price_block` / `polaris_price` `detail=true` parity with `run_price`
  **and** the REST API across treaty / capital / product variants;
  compact-by-default (`detail=false` clears per-year arrays; summary present;
  manager `call_tool` yields text + structured); sample-block loading + product
  filtering + re-valuation age/duration derivation + explicit file path;
  actionable errors (unknown sample/file, unknown product type, no matching
  product, unknown treaty → ToolError with guidance); capabilities enumeration
  (incl. not advertising DI/ANNUITY); `.mcp.json` valid JSON / names `polaris-mcp`
  / sets `POLARIS_DATA_DIR`; `main` entry point callable. All dates pinned.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `polaris-mcp` boots over stdio; agent prices the sample block for headline PVs/IRR | ✅ | `main()` → `mcp.run()` (stdio default); `summary` carries the headline |
| Capabilities resource enumerates the enums | ✅ | `polaris://capabilities`; priceable product types only |
| Committed `.mcp.json` makes the server available after clone, no manual registration | ✅ | valid JSON, `uv run --directory . polaris-mcp`, `POLARIS_DATA_DIR=./data` |
| `polaris_price_block == run_price == the API` for the same inputs | ✅ | parametrized parity tests (detail=true) |
| Read-only annotations on both pricing tools | ✅ | `readOnly/idempotent=True`, `destructive/openWorld=False` |
| Reuse Pydantic contracts as schemas (no hand-copied schema) | ✅ | `polaris_price` input schema derived from `PriceRequest` |
| ADR added | ✅ | ADR-171 |

## Open Questions / Follow-ups
- **Compact text vs structured content.** FastMCP's high-level decorator
  serialises one return value into *both* structured content and JSON text, so the
  "short text summary" intent is carried by the `PriceBlockResult.summary` field +
  `detail` array-gating rather than a separate hand-built text content block. If a
  genuinely distinct compact text block is wanted, Slice 4 could drop to the
  lower-level `CallToolResult`. (1st-order follow-up of a planned feature.)
- **`.mcp.json` relative-path resolution.** Uses `--directory .` / `./data`;
  whether these resolve from an arbitrary client launch CWD is untested in a real
  Claude Code launch (QUICKSTART documents the absolute-path `claude mcp add`
  fallback). Confirm on a real host during Slice 4 hardening.
- **Product-type filtering of a mixed sample block.** `polaris_price_block` prices
  only the policies matching `product_type` (transparent via `n_policies`); a
  future named-block registry (a locked design deferral) or a per-product headline
  could price all cohorts. (1st-order.)

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced.

## Impact on Golden Baselines
None. Purely additive — a new optional package behind the `[mcp]` extra, a new
console script, a new `.mcp.json`, and docs. No engine code changed. `polaris
price` on `golden_config_flat.json` reproduces the committed cedant PV profits
(`$3,513,563` present in the output, matching the ADR-170 baseline); the four
golden configs and the full API suite are byte-identical.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start on
`claude/loving-gauss-m45k5w` (= `origin/main` @ `2361e9e`, post-#173):
**2632 passed, 3 skipped, 124 deselected**, 0 failures. The 3 skips are the absent
CIA-2014 tables (pymort could not reach source in step 2) — the standing
tolerance-aware baseline (prior log recorded 2621 passed post-#172; the higher
count reflects the intervening #173 merge). No new/changed failures → proceeded.
After this slice: **2667 passed** (+35 new MCP tests), 3 skipped, 0 failures;
ruff format/check clean; `polaris price` golden run byte-identical.
