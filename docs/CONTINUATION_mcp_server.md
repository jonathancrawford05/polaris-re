# Continuation: MCP Server — agent access to the pricing engine

**Source:** `docs/PLAN_mcp_server.md` — active **Phase-7 Tier-A epic**
(maintainer-constituted 2026-07-27; ends the routine's maintenance mode).
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~6–8 dev-days (4 mergeable slices)

## Overall Goal

Expose the polaris-re pricing engine to agent hosts (Claude Code / Claude
Desktop) as an in-process MCP server, so an actuary can drive the engine
conversationally ("price this block YRT 90%, then stress mortality +15% and show
me the reinsurer IRR delta"). The engine is an unusually clean MCP target: it is
deterministic and read-only, with typed Pydantic v2 request/response contracts.
The server calls the engine **in-process** (no HTTP proxy, no `uvicorn`
dependency), reusing the same contracts as the tool schemas. Read
`docs/PLAN_mcp_server.md` (the read-only spec) for the design anchors and the
five LOCKED decisions before each slice.

## Decomposition

### Slice 1: Service-layer extraction (engine-neutral refactor)
- **Status:** DONE
- **Branch:** `claude/loving-gauss-s03y22`
- **PR:** _(this PR — draft)_
- **What was done:** Created `src/polaris_re/services/pricing.py` owning
  `run_price(request: PriceRequest) -> PriceResponse` plus the request/response
  contracts (`PolicyInput` / `PriceRequest` / `PriceResponse`) and the
  engine-composition helpers, all moved verbatim out of the FastAPI
  `POST /api/v1/price` route body. The route is now a thin adapter that delegates
  to `run_price` and maps any error to HTTP 422. `api/main.py` re-imports the
  moved names, so every prior import path and the OpenAPI schema are unchanged.
  The module imports **no** `fastapi`; the two helpers that raised `HTTPException`
  now raise the domain `PolarisValidationError` (observably byte-identical — every
  caller already re-wrapped errors into 422). ADR-170. Golden configs + all four
  baselines byte-identical; new route/service-parity tests.
- **Key decisions (affect later slices):**
  - The service layer lives at `src/polaris_re/services/` and is the composition
    root every host calls. It must stay web-framework-free (a test enforces no
    `fastapi` symbol leaks into `services.pricing`).
  - `run_price` performs no HTTP concerns and raises domain exceptions; each host
    maps them to its own error surface. Slice 2's MCP tool will catch
    `PolarisValidationError` and return an actionable tool error.
  - `run_scenario` / `run_uq` are NOT yet extracted — the scenario/uq route
    bodies stay inline in `api/main.py`. Slice 3 extracts them the same way
    before wiring the scenario/uq MCP tools.

### Slice 2: MCP server + core `polaris_price_block` tool (stdio)
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Files to create/modify:** new `src/polaris_re/mcp/` package
  (`server.py`, `__init__.py`); a staged `[mcp]` extra in `pyproject.toml`
  (`mcp` / `fastmcp`, added in the slice that first imports it); a
  `polaris-mcp` console entry point (`[project.scripts]`); a committed
  project-scope `.mcp.json` at the repo root; QUICKSTART "Connect from Claude
  Code / Claude Desktop" section.
- **Tools to expose:** `polaris_price_block` (inforce file path **or** a built-in
  sample id like `"golden"` + high-level deal params, **valuation_date
  required**, `detail=false` default → structured `PriceResponse` + a compact
  text summary via `run_price`); `polaris_price` (full inline-`policies[]`);
  `polaris_capabilities` (a resource enumerating product / treaty / capital /
  reserve-basis enums). Read-only annotations
  (`readOnlyHint=true, idempotentHint=true, destructiveHint=false, openWorldHint=false`).
- **Tests to add:** in-process tests that each tool returns valid structured
  output for the sample block and that `polaris_price_block == run_price == the
  API` for the same inputs; schema/annotation assertions; dates pinned; a test
  that the committed `.mcp.json` is valid JSON and names the `polaris-mcp`
  command.
- **Acceptance criteria:**
  - `polaris-mcp` boots over stdio; an agent can price the sample block and get
    headline PVs/IRR.
  - The capabilities resource enumerates the enums.
  - The committed `.mcp.json` makes the server available after clone with no
    manual registration.
- **ADR:** MCP server architecture + tool/transport design.

### Slice 3: Scenario + UQ tools, and streamable-HTTP transport
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** first extract `run_scenario` / `run_uq` into `services/` (same
  pattern as Slice 1), then add `polaris_run_scenario` (standard stress set) and
  `polaris_run_uq` (Monte-Carlo bands) tools over them; add an optional
  streamable-HTTP (stateless JSON) transport reusing the existing
  `APIKeyAuthMiddleware` for the shared-deployment case (stdio stays default).
- **Tests:** scenario/uq tool parity with the API; HTTP-mode auth; deterministic
  UQ seed.
- **ADR:** scenario/uq service extraction + tools + HTTP transport + auth reuse.

### Slice 4: Evaluations, hardening, docs (CLOSES EPIC)
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
- **Scope:** a 10-question MCP eval set (realistic, read-only, verifiable pricing
  Q&A against the sample block); actionable error messages (bad file path →
  guidance; out-of-range param → the valid range); ARCHITECTURE.md MCP section;
  README/QUICKSTART finalized. HARVEST + close this CONTINUATION.
- **Acceptance:** eval set committed and green; docs complete; CONTINUATION
  COMPLETE with refinement backlog harvested to PRODUCT_DIRECTION.

## Context for Next Session

- **Merge cadence gates the epic.** The routine never merges its own PR, and each
  slice depends on `main`, so Slice 2 cannot start until this Slice-1 PR is
  merged. If the draft sits unmerged, the next routine run legitimately falls back
  to gated polish (step 5b/6). Merge promptly to keep the epic moving, or
  authorise stacked branches.
- **Byte-identical discipline holds through Slice 3.** No slice changes a pricing
  number until (if ever) a deliberately surfacing change; Slices 1–3 leave the
  goldens byte-identical. Slice 2/3 add a NEW surface, they do not alter the
  engine.
- **Read the `mcp-builder` skill before Slice 2** for the FastMCP patterns, and
  reuse the Pydantic contracts as the tool schemas (do not hand-copy).
- **`_build_components` currently constructs a synthetic flat-rate table** (demo
  mortality); the MCP sample-block tool should price the committed
  `data/qa/golden_inforce.csv` for a realistic headline, mirroring the CLI.
- **`.mcp.json` relative-path caveat:** confirm `--directory .` / `./data`
  resolve from the client's launch CWD during Slice 2; fall back to a documented
  absolute path in QUICKSTART if not.

## Open Questions (for human)

- None blocking. The five design decisions are LOCKED in `docs/PLAN_mcp_server.md`
  (maintainer sign-off 2026-07-27). Slice 2 should confirm the FastMCP version to
  pin in the `[mcp]` extra when it first imports `mcp` / `fastmcp`.
