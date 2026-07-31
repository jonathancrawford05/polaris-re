# PLAN: MCP Server — agent access to the pricing engine

> **Audience.** A future Claude Code session (or human) that will build an MCP
> (Model Context Protocol) server exposing the polaris-re pricing engine to
> agent hosts (primarily Claude Code / Claude Desktop; a local ollama-backed host
> is a nice-to-have, not a design driver). Read this document fully, then read
> CLAUDE.md (conventions, `[extra]` staging), ARCHITECTURE.md (module layering),
> the FastAPI surface (`src/polaris_re/api/main.py`), and the `mcp-builder` skill
> before writing code. This is the read-only spec, not the running log — the
> running log is `CONTINUATION_mcp_server.md` (opened when Slice 1 starts).

**Status:** ✅ COMPLETE — all five slices shipped (Slices 1/2/3/3b merged as PRs
#173–#176; Slice 4 — evals, hardening, docs — shipped 2026-07-31 as draft PR #177,
ADR-174, closing `CONTINUATION_mcp_server.md`). Maintainer signed off 2026-07-27 on
the Phase-7 framing and all five Open Decisions (see "Decisions — LOCKED" below).
This was the active Phase-7 Tier-A epic; with it complete the routine has no active
epic and the next run selects one per step 5b. Running log:
`docs/CONTINUATION_mcp_server.md` (now COMPLETE).

**Source / derivation.** Maintainer-requested 2026-07-27 (this session). The
routine is in the post-roadmap maintenance inflection (`PRODUCT_DIRECTION_2026-07-24`
§"Decision Surfaced"; `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7) with **no
startable Tier-A epic**. An MCP integration layer is a legitimate **Phase-7
"integration / multi-user" frontier** candidate — it re-establishes a Tier-A
ladder rather than being maintenance polish. It is *not* a modeling, validation,
or deployment gap; it is a new **access surface** on top of the shipped engine.

**Why this now.** The differentiating thesis (CLAUDE.md §1) is an ML-native,
Git-versioned, Python-native reinsurance engine. Letting an actuary drive that
engine conversationally from an agent — "price this block YRT 90%, then stress
mortality +15% and show me the reinsurer IRR delta" — is the natural expression
of that thesis and something the incumbents (AXIS/Prophet) structurally do not
offer. The engine is an unusually clean MCP target: it is **deterministic and
read-only** (no state mutation; `valuation_date` pinned per ADR-074), and it
already has typed Pydantic v2 request/response contracts and a shared
`_build_components()` factory that every API endpoint funnels through.

---

## Design Anchors

- **In-process via a shared service layer — NOT an HTTP proxy** (pending Open
  Decision #1). Extract the post-`_build_components` logic from each FastAPI
  route into `src/polaris_re/services/`. The FastAPI route **and** the MCP tool
  both call the same `run_price(req: PriceRequest) -> PriceResponse`. One
  engine-invocation path (DRY — no second mapping to drift), no `uvicorn`
  dependency at runtime, works fully offline. This is the same composition-root
  cleanup ADR-156 began.
- **Reuse the Pydantic contracts as the tool schemas.** FastMCP derives tool
  input/output schemas from the existing `PriceRequest` / `PriceResponse` (and
  the scenario/uq models). The API field descriptions and endpoint docstrings
  become the tool descriptions — single source of truth, no hand-copied schema.
- **Python + FastMCP, staged into a new `[mcp]` extra.** Deliberate deviation
  from the `mcp-builder` skill's general TypeScript preference: this repo is
  Pydantic/uv/Ruff/mypy Python, and in-process reuse of the models + engine is
  only possible in-language. `pymc`-style discipline — the `mcp` dep is added in
  the slice that first imports it, mirroring `[api]`/`[ml]`.
- **stdio transport first; streamable-HTTP (stateless JSON) as a later slice.**
  stdio is what Claude Code / Claude Desktop and local hosts spawn. HTTP reuses
  the existing `APIKeyAuthMiddleware` for the shared-deployment case.
- **Workflow tools, not a raw endpoint dump.** The raw `PriceRequest` needs a
  full `policies[]` array (25+ fields) — poor ergonomics for an agent. The
  headline tool takes an **inforce reference** (file path, or a built-in sample
  block id) + high-level deal params, mirroring the CLI's `--inforce X.csv
  --config Y.json`. A full inline-policies tool remains for programmatic callers.
- **Compact-by-default output for context safety.** Every tool returns
  `structuredContent` (the full typed response) **plus** a short text summary
  (headline cedant/reinsurer PV profits + IRR, peak capital). The large
  `profit_by_year` / per-cohort arrays are behind an explicit `detail=true` — the
  CLI `-o` dump is large and would flood an agent's context.
- **Read-only annotations.** Every pricing tool:
  `readOnlyHint=true, idempotentHint=true, destructiveHint=false, openWorldHint=false`.
  This tells the client the tools are safe to call freely — true because the
  engine mutates nothing.
- **Explicit `valuation_date` (ADR-074 guard).** Tool inputs require an explicit
  valuation date; the server never defaults to `date.today()`. A drifting date
  would make quotes non-reproducible. Evals and tests pin dates.
- **Byte-identical engine behaviour.** The service extraction must leave
  `polaris price` and all four golden configs + the API responses byte-identical.
  No slice changes a pricing number.

---

## Decomposition

Four slices, each independently mergeable and green. Slices 1–2 deliver a usable
MCP server for the core `price` workflow; 3 adds stress/UQ + HTTP; 4 hardens with
evals + docs and closes the epic.

### Slice 1 — Service-layer extraction (engine-neutral refactor)
- **Status:** ✅ DONE (2026-07-28, ADR-170)
- **Scope.** Create `src/polaris_re/services/pricing.py` with `run_price(req:
  PriceRequest) -> PriceResponse` (and stubs/plan for `run_scenario`, `run_uq`),
  extracting the logic currently inline in the `/api/v1/price` route body after
  its `_build_components()` call (project → apply treaty → ProfitTester →
  assemble `PriceResponse`). Rewrite the FastAPI route to call it. No new
  behaviour; no MCP dependency yet.
- **Tests.** The existing API tests must pass unchanged (they now exercise the
  service via the route). Add direct `run_price` unit tests (a golden request →
  the same `PriceResponse`). `polaris price` + 4 goldens byte-identical.
- **Acceptance.** `/api/v1/price` behaviour byte-identical; `run_price` importable
  and covered; no `mcp` dependency added.
- **ADR.** Service-layer extraction (composition-root, follows ADR-156).

### Slice 2 — MCP server + core `polaris_price_block` tool (stdio)
- **Status:** PLANNED
- **Depends on:** Slice 1 merged.
- **Scope.** New `src/polaris_re/mcp/` package (staged `[mcp]` extra: `mcp` /
  `fastmcp`). A stdio FastMCP server exposing:
  - `polaris_price_block` — inputs: `inforce` (file path **or** a built-in sample
    id, e.g. `"golden"` → `data/qa/golden_inforce.csv`), plus high-level deal
    params (product_type, treaty_type, cession_pct, discount/hurdle, reserve
    basis, capital_model, **valuation_date required**). Builds a `PriceRequest`
    and calls `run_price`. Returns structured `PriceResponse` + a compact text
    summary; `detail=false` default.
  - `polaris_price` — the full inline-`policies[]` version (programmatic callers).
  - `polaris_capabilities` — a **resource** listing valid product types, treaty
    types, capital models, reserve bases (the enums), so the agent discovers
    them instead of guessing.
  - A console entry point `polaris-mcp` (pyproject `[project.scripts]`, e.g.
    `polaris-mcp = "polaris_re.mcp.server:main"` — mirrors the existing
    `polaris = "polaris_re.cli:app"`).
  - **A committed project-scope `.mcp.json`** at the repo root so the server is
    one-command usable after `git clone` (no manual `claude mcp add`). It
    registers the stdio server via `uv run polaris-mcp` with `--directory` and
    the `POLARIS_DATA_DIR` env, e.g.:
    ```jsonc
    {
      "mcpServers": {
        "polaris": {
          "command": "uv",
          "args": ["run", "--directory", ".", "polaris-mcp"],
          "env": { "POLARIS_DATA_DIR": "./data" }
        }
      }
    }
    ```
    (Confirm whether relative `--directory .` / `./data` resolve correctly from
    the client's launch CWD during Slice 2; fall back to a documented absolute
    path in QUICKSTART if not.)
- **Tests.** In-process tests that each tool returns valid structured output for
  the sample block and that `polaris_price_block` == `run_price` == the API for
  the same inputs. Schema/annotation assertions (readOnly etc.). Dates pinned. A
  test that the committed `.mcp.json` is valid JSON and names the `polaris-mcp`
  command (guards against the config rotting).
- **Acceptance.** `polaris-mcp` boots over stdio; an agent can price the sample
  block and get headline PVs/IRR; capabilities resource enumerates the enums;
  the committed `.mcp.json` makes the server available after clone with no manual
  registration.
- **ADR.** MCP server architecture + tool/transport design.
- **Docs — QUICKSTART "Connect from Claude Code / Claude Desktop"** must include,
  concretely:
  1. **Pre-warm the venv** so first launch beats the 30 s startup timeout:
     `uv sync --extra mcp`.
  2. **Standalone smoke-test with the MCP Inspector** (no Claude Code — browser
     UI to call each tool and see raw JSON):
     `npx @modelcontextprotocol/inspector -- uv run polaris-mcp`.
  3. **Register with Claude Code** — the exact `claude mcp add` line (note the
     `--` separates Claude's flags from the launch command, and the server name
     must NOT sit directly after `--env`; keep `--scope` between them):
     `claude mcp add --env POLARIS_DATA_DIR=/abs/path/to/polaris-re/data --scope local polaris -- uv run --directory /abs/path/to/polaris-re polaris-mcp`
     — plus a note that committing/using the project-scope `.mcp.json` above is
     the zero-config alternative for anyone who clones the repo.
  4. **Verify + use**: `claude mcp list` / `claude mcp get polaris` and the
     in-session `/mcp` panel to confirm it connected and lists the tools; then a
     sample prompt ("price the `golden` sample block YRT 90% cession at 6%
     discount, valuation 2025-01-01 — reinsurer IRR?").
  5. **Debug + reload gotchas**: run `uv run polaris-mcp` directly to see stderr;
     `MCP_TIMEOUT=60000 claude` for a slow cold start; stdio servers are **not**
     hot-reloaded — exit and restart the session after changing server code.

### Slice 3 — Scenario + UQ tools, and streamable-HTTP transport
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope.** `polaris_run_scenario` (standard stress set) and `polaris_run_uq`
  (Monte-Carlo bands) over `run_scenario` / `run_uq`. Add an optional
  streamable-HTTP (stateless JSON) transport mode reusing the existing
  `APIKeyAuthMiddleware` for the shared-deployment case; stdio stays the default.
- **Tests.** Scenario/UQ tool parity with the API; HTTP-mode auth (missing key →
  rejected when `POLARIS_API_KEYS` set; open when unset). Deterministic UQ seed.
- **Acceptance.** An agent can stress a priced block and read the IRR delta; the
  server runs over HTTP with API-key auth when configured.
- **ADR.** Scenario/UQ tools + HTTP transport + auth reuse.

### Slice 4 — Evaluations, hardening, docs (CLOSES EPIC)
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
- **Scope.** A 10-question MCP eval set per the `mcp-builder` Phase-4 guide
  (realistic, read-only, verifiable pricing Q&A against the sample block — e.g.
  "price `golden` YRT 90% cession at 6% discount, valuation 2025-01-01 — what is
  the reinsurer IRR to 2 dp?"). Actionable error messages (bad file path →
  guidance; out-of-range param → the valid range). ARCHITECTURE.md MCP section;
  README/QUICKSTART finalized. HARVEST + close `CONTINUATION_mcp_server.md`.
- **Acceptance.** Eval set committed and green; docs complete; CONTINUATION
  COMPLETE with refinement backlog harvested to PRODUCT_DIRECTION.

---

## Out of Scope (harvest to PRODUCT_DIRECTION as follow-ups)

- **Store-authoring / write tools.** The engine is read-only; the MCP server
  authors nothing (no version-store writes, no file mutation). A create/freeze
  flow would be a separate, carefully-annotated (`destructiveHint`) feature.
- **IFRS 17 / ingest / rate-schedule / portfolio tools.** Slices 1–4 cover the
  price/scenario/uq core. The remaining endpoints are a natural follow-up once
  the pattern is proven (each is another `run_*` service fn + a thin tool).
- **MCPB / desktop-extension packaging** and a published server registry entry.
- **Prompts** (MCP prompt templates for common deal-pricing flows).
- **ollama / local-model tuning.** Non-primary; a one-line compatibility note in
  the QUICKSTART (MCP support lives in the host, not the model — a local model
  runs the server only through an MCP-capable host).

---

## Decisions — LOCKED (maintainer sign-off 2026-07-27)

All five resolved as recommended; the plan above reflects them.

1. **In-process, NOT an HTTP proxy.** ✅ The MCP tool calls `run_price` → engine
   in the same process; no deployed/`uvicorn` API is required to run the engine.
   The optional streamable-HTTP **transport** of this same in-process server
   (Slice 3) covers the "remote, shared" case — it is a transport, not a proxy to
   a separate API service. Rationale captured in the "Two runtime models"
   discussion: the engine is always a same-process library call (CLI, FastAPI
   route, or MCP tool all invoke it in-process).
2. **Inforce reference = file path + built-in sample ids + inline policies.** ✅
   No named block-registry in v1 (Claude Code has local filesystem access, so a
   path is natural; the golden CSV is the built-in sample). A registry is a
   possible later follow-up, not v1.
3. **v1 surface = price + scenario + uq.** ✅ ifrs17 / ingest / rate-schedule /
   portfolio deferred to a post-epic follow-up (each is another `run_*` service
   fn + a thin tool once the pattern is proven).
4. **In-repo `[mcp]` extra.** ✅ Matches `[api]`/`[ml]`; keeps the tool schemas in
   lockstep with the Pydantic models. No separate `polaris-re-mcp` package.
5. **Constituted as the active Phase-7 Tier-A epic.** ✅ Ends the routine's
   maintenance mode; `PRODUCT_DIRECTION` / `COMMERCIAL_VIABILITY_REVIEW` should
   record MCP integration as the chosen Phase-7 frontier.
