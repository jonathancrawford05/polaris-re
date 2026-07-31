# Dev Session Log — 2026-07-30

## Item Selected
- **Source:** `docs/CONTINUATION_mcp_server.md` — the active Phase-7 Tier-A epic
  (MCP Server, maintainer-constituted 2026-07-27), **Slice 3b**.
- **Priority:** Tier-A epic (active Epic track, step 5b — advanced before any
  fallback pick).
- **Title:** Streamable-HTTP transport for the MCP server.
- **Slice:** 3b of 5 (the HTTP transport carved out of Slice 3 last session).
- **Branch:** `claude/loving-gauss-gnlw5y` (environment-designated).

## Selection Rationale
Step 5 found `CONTINUATION_mcp_server` IN PROGRESS with Slice 3b marked **NEXT**.
The MCP Server epic is the **active Phase-7 Tier-A epic** (maintainer sign-off
2026-07-27, `PLAN_mcp_server.md`), so per the ACTIVE-EPIC guardrail it is advanced
before any fallback pick. Slice 3 (`polaris_run_scenario` / `polaris_run_uq`) merged
as **PR #175** (2026-07-29) — confirmed on `main` via `git log` (HEAD = the #175
merge, `28ec5a6`) — so Slice 3b was unblocked. The other IN PROGRESS CONTINUATIONs
(`perf_harness`, `expense_allowance_duration`) are fallback epics that advance only
when the active MCP epic is blocked; neither was touched.

**Ledger healing (step 4b).** The CONTINUATION still showed Slice 3 as "draft PR #175
— awaiting merge" (stale). PR #175's `merged_at` is populated (merged 2026-07-29), so
Slice 3 was healed to "merged (PR #175)". All other recently-merged PRs (#168–#174)
were already struck/recorded by their own session logs.

**Premise verification (step 7b).** Confirmed the gap holds: before this slice
`main()` was `def main(): mcp.run()` — stdio only, no transport switch, no
`build_http_app`. Reproduced with a prototype that (a) built `mcp.streamable_http_app()`
wrapped in `APIKeyAuthMiddleware` and drove it with a `TestClient`, observing the
auth boundary work (no keys → 200, keys set + no key → 401, valid key → 200), and
(b) confirmed `mcp.settings.transport_security` defaults to an empty `allowed_hosts`
that rejects every request with 421 unless configured — which is exactly why the
transport needs explicit host allow-listing. Premise confirmed; approach validated
before writing final code.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Service-layer extraction (`run_price`) | ✅ Done | #173 |
| 2 | MCP server + core `polaris_price_block` tool (stdio) | ✅ Done | #174 |
| 3 | Scenario + UQ service extraction + MCP tools | ✅ Done | #175 |
| 3b | Streamable-HTTP transport (this session) | ✅ Done | #176 (draft) |
| 4 | Evals, hardening, docs (closes epic) | ⏳ Next | — |

## What Was Done
Added an optional streamable-HTTP (stateless JSON) serving mode to the **same**
`polaris_re.mcp.server.mcp` FastMCP instance — a transport of the one in-process
server, not a proxy to the REST API (LOCKED decision #1). `main()` gained an argparse
front end: `--transport {stdio,http}` (overriding `$POLARIS_MCP_TRANSPORT`, default
stdio) plus `--host` / `--port` (overriding `$POLARIS_MCP_HOST` / `$POLARIS_MCP_PORT`,
default `127.0.0.1:8000`). A new `resolve_transport()` normalises the value (accepting
`http` / `streamable-http`) and raises an actionable error on an unknown transport;
the stdio path (`mcp.run()`) is unchanged.

`build_http_app()` returns the FastMCP `streamable_http_app()` for the same `mcp`,
configured **stateless JSON** (`stateless_http=True`, `json_response=True`) so any
replica answers any request without session affinity — the shape API-key auth expects
— and wrapped in the REST API's `APIKeyAuthMiddleware`. HTTP mode therefore
authenticates with the same `POLARIS_API_KEYS` as the API (401 on missing/invalid key
when configured; open when unset, exactly like stdio), added outermost so an
unauthenticated request is rejected before the transport-security check or the MCP
handler. FastMCP's DNS-rebinding Host allow-list (empty by default → rejects all) is
**configured, not disabled**, from `$POLARIS_MCP_ALLOWED_HOSTS` /
`$POLARIS_MCP_ALLOWED_ORIGINS`, defaulting to loopback + the bind host (each as a bare
name and a `name:*` wildcard-port pattern). The `APIKeyAuthMiddleware` import is
**lazy** (inside `build_http_app`) so the default stdio path — what Claude Code /
Claude Desktop spawn — never pulls in the `[api]` FastAPI stack. Recorded **ADR-173**.

## Files Changed
- `src/polaris_re/mcp/server.py` — transport config constants; `resolve_transport`;
  `_csv_env` / `_configured_allowed_hosts`; `build_http_app`; argparse `main(argv)`;
  imports (`argparse`, `TransportSecuritySettings`, `Starlette`); updated `__all__`.
- `src/polaris_re/mcp/__init__.py` — export `build_http_app`, `resolve_transport`.
- `docs/DECISIONS.md` — ADR-173.
- `docs/QUICKSTART.md` — §10: 4-tool list corrected; new "Serve over HTTP" subsection
  (flags/env table, auth, DNS-rebinding note).
- `docs/CONTINUATION_mcp_server.md` — Slice 3 healed to merged (#175); Slice 3b DONE;
  Context updated (Slice 4 next).
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — Slice-3b harvest (3 NICE-TO-HAVE follow-ups).

## Tests Added
- `tests/test_mcp/test_server.py` (+23):
  - `TestTransportResolution` (8) — stdio variants, HTTP aliases, env default,
    env-selects-http, flag-over-env, actionable bad-value error.
  - `TestHttpAppConstruction` (4) — app wraps `APIKeyAuthMiddleware`; allow-list
    default covers loopback; explicit env allow-list honoured; stateless JSON.
  - `TestHttpAuth` (4) — open when unset; 401 missing; 401 invalid; 200 valid.
  - `TestHttpStdioParity` (4) — price / scenario / uq(seeded) payloads byte-identical
    over HTTP vs stdio `call_tool`; identical `tools/list`.
- No existing assertion changed. MCP suite 58 → 81; full fast suite 2705 → 2728.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| HTTP transport of the same in-process server (not a proxy) | ✅ | `build_http_app()` serves `streamable_http_app()` of the one `mcp` |
| Transport switch (env + CLI flag), stdio default | ✅ | `--transport` / `$POLARIS_MCP_TRANSPORT`; `resolve_transport` |
| Reuse `APIKeyAuthMiddleware` (missing key rejected when keys set; open when unset) | ✅ | `TestHttpAuth` — 200/401/401/200 |
| Tools return same payloads over HTTP as over stdio | ✅ | `TestHttpStdioParity` — price/scenario/uq byte-identical + `tools/list` |
| DNS-rebinding protection configured (not disabled) | ✅ | `TransportSecuritySettings` from env; loopback default |
| stdio path stays dependency-light | ✅ | auth import is lazy; stdio never imports `[api]` |
| Goldens byte-identical | ✅ | `polaris price` flat exit 0 (cedant $3,513,563.42 / reinsurer $45,386.44); `tests/qa/` 94 passed |
| Quality gate (ruff format+check, fast suite, qa) | ✅ | ruff clean; MCP suite 81 passed; qa 94 passed |

## Open Questions / Follow-ups
- **Slice 3b split acceptable / ordering?** Slice 3b (HTTP transport) and Slice 4
  (evals/docs) are independent and can be sequenced either way; Slice 4 is the only
  remaining slice and CLOSES the epic. Carried in the CONTINUATION's Open Questions.
- **HTTP mode requires the `[api]` extra** (auth-stack coupling via
  `api.auth` → `api/__init__` → FastAPI). Harvested as a NICE-TO-HAVE follow-up;
  the Slice-4 ARCHITECTURE docs pass should note it.
- **`perf_harness` / `expense_allowance_duration` still IN PROGRESS** — unchanged
  fallback epics, not touched (the active MCP epic consumed the session).

## Parked Polish
None. ADR-173's out-of-scope items are 1st-order follow-ups of the (originally-planned)
HTTP transport and were harvested to PRODUCT_DIRECTION as NICE-TO-HAVE; Slice 4 is
tracked as the epic's own remaining slice, not a loose item.

## Impact on Golden Baselines
None. A purely additive new serving mode + config helpers; no `src/` pricing code
changed, so every golden config and `polaris price` output is byte-identical.
Confirmed: `polaris price` on `golden_config_flat.json` exit 0 (cedant PV
$3,513,563.42, reinsurer PV $45,386.44, both unchanged); `tests/qa/` 94 passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2705 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; SOA VBT /
CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline). Matches the recorded baseline in `DEV_SESSION_LOG_2026-07-29`
(post-Slice-3), so the session PROCEEDED. This slice adds 23 fast tests; full fast
suite after: **2728 passed, 3 skipped, 124 deselected**, 0 failures.
