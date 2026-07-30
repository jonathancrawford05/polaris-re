# Continuation: MCP Server — agent access to the pricing engine

**Source:** `docs/PLAN_mcp_server.md` — active **Phase-7 Tier-A epic**
(maintainer-constituted 2026-07-27; ends the routine's maintenance mode).
**Status:** IN PROGRESS
**Total slices:** 5 (Slice 3 split into 3 + 3b — see Decomposition)
**Estimated total scope:** ~6–8 dev-days (5 mergeable slices)

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
- **Status:** DONE (merged)
- **Branch:** `claude/loving-gauss-s03y22`
- **PR:** #173 (merged 2026-07-28)
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
- **Status:** DONE (merged)
- **Branch:** `claude/loving-gauss-m45k5w` (environment-designated)
- **PR:** #174 (merged 2026-07-28)
- **What was done:** Added `src/polaris_re/mcp/` (`server.py`, `__init__.py`)
  hosting a FastMCP stdio server (`mcp` official SDK, staged into a new `[mcp]`
  extra + the dev group). Three surfaces: `polaris_price_block` (inforce
  reference — the `"golden"` sample id or a CSV path — plus high-level deal
  params, **required `valuation_date`** that re-values the block, product-type
  filtered because a single `run_price` covers one engine); `polaris_price` (full
  inline `PriceRequest`, schema derived from the contract); and a
  `polaris://capabilities` resource enumerating the priceable enums + sample ids.
  Every pricing tool wraps `run_price` and returns a compact-by-default
  `PriceBlockResult` (`summary` + full `price`, per-year arrays gated on
  `detail`), with read-only annotations and actionable `ToolError`s. A
  `polaris-mcp` console entry point, a committed project-scope `.mcp.json`, a
  QUICKSTART §10 "Connect from Claude Code / Claude Desktop" section, and the
  `.mcp.json` COPY into the Dockerfile. ADR-171. Additive — golden configs +
  API suite byte-identical.
- **Key decisions (affect later slices):**
  - The `mcp` SDK (bundled FastMCP), not standalone `fastmcp`, is pinned in the
    `[mcp]` extra. Slice 3's scenario/uq tools reuse the same `FastMCP` instance
    (`polaris_re.mcp.server.mcp`).
  - Tools return the `PriceBlockResult` wrapper (`summary` + `price`) rather than a
    bare `PriceResponse`, because FastMCP's high-level decorator serialises one
    return value into both structured content and JSON text — the summary field +
    `detail` array-gating carry the compact-output intent. Slice 3's tools should
    follow the same wrapper shape for consistency.
  - `run_scenario` / `run_uq` are still inline in `api/main.py`; Slice 3 extracts
    them into `services/` first (same pattern as Slice 1) before wiring their tools.
- **Acceptance criteria:** ✅ `polaris-mcp` boots over stdio and prices the sample
  block (headline PVs/IRR via the `summary`); ✅ capabilities resource enumerates
  the enums; ✅ committed `.mcp.json` names `polaris-mcp` + sets `POLARIS_DATA_DIR`;
  ✅ `polaris_price_block == run_price == the API` (35 tests).
- **ADR:** ADR-171 (MCP server architecture + tool design).

### Slice 3: Scenario + UQ service extraction + MCP tools
- **Status:** DONE (merged)
- **Branch:** `claude/loving-gauss-mlp5ki` (environment-designated)
- **PR:** #175 (merged 2026-07-29)
- **What was done:** Extracted `run_scenario(ScenarioRequest) -> ScenarioResponse`
  and `run_uq(UQRequest) -> UQResponse` into `services/pricing.py` (moving the
  `Scenario*` / `UQ*` contracts and the `_resolve_perspective` helper out of
  `api/main.py` verbatim, same pattern as Slice 1). The `/api/v1/scenario` and
  `/api/v1/uq` routes are now thin adapters that delegate and map errors to 422;
  `api/main.py` re-imports the moved contracts so every prior import path + the
  OpenAPI schema are unchanged. Added `polaris_run_scenario` (standard stress set)
  and `polaris_run_uq` (Monte-Carlo bands) MCP tools over them — inforce-reference
  ergonomics via a shared `_load_block_policies` helper refactored out of the price
  tool, compact `ScenarioBlockResult` / `UQBlockResult` wrappers (summary +
  response), required `valuation_date`, UQ `seed`. ADR-172. Additive — golden
  configs + full API suite byte-identical.
- **Key decisions (affect later slices):**
  - **Streamable-HTTP transport split out to a new Slice 3b** (below) to keep this
    PR to the higher-value analytics tools and one reviewable byte-identical change.
    stdio remains the only transport, which is what Claude Code / Claude Desktop
    spawn. Slice 4 (evals) does not depend on HTTP, so 3b and 4 can be sequenced in
    either order.
  - `run_scenario` / `run_uq` now live in `services/pricing.py` alongside `run_price`
    (they share the private `_build_components` / `_build_treaty` /
    `_run_gross_projection` helpers); perspective resolution (ADR-078) is a shared
    service helper so CLI / API / MCP agree.
- **Acceptance criteria:** ✅ scenario/uq route↔service parity; ✅ MCP tool ↔ `run_*`
  ↔ REST parity (scenario + uq); ✅ UQ seed reproducibility; ✅ read-only annotations
  + structured-output schemas; ✅ actionable errors; ✅ goldens byte-identical.
- **ADR:** ADR-172 (scenario/uq service extraction + MCP tools).

### Slice 3b: Streamable-HTTP transport (split from Slice 3)
- **Status:** DONE (draft PR — awaiting merge)
- **Branch:** `claude/loving-gauss-gnlw5y` (environment-designated)
- **PR:** _(this session's draft)_
- **What was done:** Added an optional streamable-HTTP (stateless JSON) serving mode
  to the **same** `polaris_re.mcp.server.mcp` instance (a transport, not a proxy —
  LOCKED decision #1). `main()` gained an argparse front end: `--transport {stdio,http}`
  (over `$POLARIS_MCP_TRANSPORT`, default stdio) + `--host` / `--port`
  (over `$POLARIS_MCP_HOST` / `$POLARIS_MCP_PORT`, default `127.0.0.1:8000`);
  `resolve_transport()` normalises the value. `build_http_app()` returns the FastMCP
  `streamable_http_app()` configured stateless JSON and wrapped in the REST API's
  `APIKeyAuthMiddleware` (reusing `POLARIS_API_KEYS`; open when unset). DNS-rebinding
  protection is configured (not disabled) from `$POLARIS_MCP_ALLOWED_HOSTS` /
  `$POLARIS_MCP_ALLOWED_ORIGINS`, defaulting to loopback + bind host. The auth import
  is lazy so the stdio path never pulls in the `[api]` FastAPI stack. ADR-173.
  Additive — goldens byte-identical.
- **Key decisions:**
  - stdio remains the default and dependency-light; HTTP mode requires the `[api]`
    extra (documented in QUICKSTART §10) because it reuses the API auth middleware.
  - Stateless JSON (no session affinity) is the shape API-key auth expects, so any
    replica can answer any request.
- **Tests:** transport resolution (stdio default / HTTP aliases / flag-over-env /
  bad-value error); the HTTP app wraps `APIKeyAuthMiddleware` + is stateless JSON;
  allow-list default + env override; HTTP-mode auth (open when unset, 401 on
  missing/invalid, 200 on valid); HTTP↔stdio payload parity for price / scenario /
  uq(seeded) + identical `tools/list`. +23 tests.
- **ADR:** ADR-173 (HTTP transport + auth reuse).

### Slice 4: Evaluations, hardening, docs (CLOSES EPIC)
- **Status:** PLANNED
- **Depends on:** Slice 3 merged (independent of Slice 3b).
- **Scope:** a 10-question MCP eval set (realistic, read-only, verifiable pricing
  Q&A against the sample block); actionable error messages (bad file path →
  guidance; out-of-range param → the valid range); ARCHITECTURE.md MCP section;
  README/QUICKSTART finalized. HARVEST + close this CONTINUATION.
- **Acceptance:** eval set committed and green; docs complete; CONTINUATION
  COMPLETE with refinement backlog harvested to PRODUCT_DIRECTION.

## Context for Next Session

- **Slice 4 is the only remaining slice** (evals + hardening + docs — CLOSES the
  epic). It is independent of Slice 3b and depends only on Slice 3 (merged). It can
  start as soon as **this Slice-3b PR is merged** (each slice depends on `main`).
- **Merge cadence gates the epic.** The routine never merges its own PR, and each
  slice depends on `main`. If the Slice-3b draft sits unmerged, the next routine run
  legitimately falls back to gated polish (step 5b/6). Merge promptly to keep the
  epic moving, or authorise stacked branches.
- **Byte-identical discipline holds through Slice 3b.** No slice changes a pricing
  number until (if ever) a deliberately surfacing change; Slices 1–3b leave the
  goldens byte-identical (cedant $3,513,563.42 / reinsurer $45,386.44), and Slice 4
  (evals/docs) will too. Each slice adds a NEW surface, not an engine change.
- **HTTP transport needs the `[api]` extra.** `build_http_app()` reuses
  `api.auth.APIKeyAuthMiddleware`, whose import pulls in FastAPI. stdio does not.
  The Slice-4 docs pass should note this in the ARCHITECTURE MCP section.
- **`run_scenario` / `run_uq` now live in `services/pricing.py`** alongside
  `run_price`, reusing the private `_build_components` / `_build_treaty` /
  `_run_gross_projection` helpers. A future host reaches all three the same way.
- **Slice 3b transport switch.** Add HTTP as an alternate transport of the SAME
  `polaris_re.mcp.server.mcp` instance (env var / CLI flag), not a new server; reuse
  `api.auth.APIKeyAuthMiddleware`. stdio stays the default.

## Open Questions (for human)

- None blocking. The five design decisions are LOCKED in `docs/PLAN_mcp_server.md`
  (maintainer sign-off 2026-07-27). Slice 3 split the streamable-HTTP transport out
  to Slice 3b (see Decomposition) so this PR ships the higher-value scenario/UQ tools
  as one reviewable, byte-identical change; confirm that ordering is acceptable
  (3b and 4 are independent and can be sequenced either way).
