# Continuation: Production Hardening & Observability (A2′)

**Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4 Tier-A (A2′); ROADMAP 6.2
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~8 dev-days

## Overall Goal

Harden the REST API and its deployment story to a production-operable standard
(ROADMAP 6.2): structured correlated request logging with per-request duration
(Slice 1), optional API-key auth + rate limiting (Slice 2), and Kubernetes/Helm
manifests plus a Prometheus/Grafana metrics stack (Slice 3). Additive throughout
— the pricing path is never touched and goldens stay byte-identical.

This is the active epic per the checkpoint sequence (A1′ Validation & Benchmark
shipped; A2′ is the next Tier-A "big rock"). See `PLAN_production_hardening.md`.

## Decomposition

### Slice 1: Observability core
- **Status:** DONE
- **Branch:** `claude/loving-gauss-7nbcgj` (designated remote-session branch)
- **PR:** #133 (draft)
- **What was done:** New `polaris_re.api.observability` module — `JsonLogFormatter`,
  `RequestContextMiddleware` (correlation id + monotonic-clock duration + JSON
  access log + `X-Correlation-ID`/`X-Response-Time-Ms` response headers),
  idempotent `configure_api_logging`, and a `correlation_id_var` context var.
  Wired into `api/main.py` at app construction. 12 new tests; 152 API + 76 QA
  tests stay green; goldens byte-identical. ADR-133.
- **Key decisions:**
  - Standard-library only (no new runtime dep) — keeps the `api` extra lean and
    defers OpenTelemetry to a later, optional slice.
  - Dedicated **non-propagating** access logger (`polaris_re.api.access`) so JSON
    access lines don't double up with the app's own handlers or pytest's caplog.
  - Inbound `X-Request-ID` / `X-Correlation-ID` is echoed (trace propagation);
    otherwise a uuid4 hex is generated. Canonical response header is
    `X-Correlation-ID`.
  - `configure_api_logging` is idempotent (adds a JSON handler only if none
    present) so import-time + test-time calls don't stack handlers.
  - Durations use `time.perf_counter` (monotonic); tests assert non-negativity
    only (ADR-074 clock-safety guard).

### Slice 2: API security — API-key auth + rate limiting
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Files to create/modify:** `api/auth.py` (new); `api/main.py` (wire
  middleware); `pyproject.toml` (optional `slowapi` extra); tests.
- **Tests to add:** authorised / unauthorised / absent-config auth paths; probe
  endpoints exempt; rate-limit 429; auth-failure log carries the correlation id.
- **Acceptance criteria:**
  - Keys configured → request without a valid `X-API-Key` returns 401 with a
    logged, correlation-stamped auth failure.
  - No keys configured → API behaves exactly as today (all existing tests pass).
  - Requests past the configured threshold return 429.

### Slice 3: Deployment & metrics surfaces
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** K8s manifests + Helm chart under `deploy/`, a Prometheus `/metrics`
  endpoint (request count + duration histogram), `docker-compose.yml`
  `prometheus`+`grafana` services, QUICKSTART deployment guide. Dockerfile /
  `.dockerignore` allowlist updated for any referenced files in the same PR.

## Context for Next Session

- Slice 1's `correlation_id_var` is deliberately exported so Slice 2's auth
  middleware (and any engine logging) can stamp the same correlation id onto its
  own log records — reuse it rather than threading the id through call args.
- **RULE — any nested `correlation_id_var` write MUST be token-scoped
  (`tok = correlation_id_var.set(...)` / `correlation_id_var.reset(tok)`), never a
  bare `set()` without a matching `reset()`.** Two channels carry the correlation
  id and they must not diverge: the `RequestContextMiddleware` summary log and the
  `X-Correlation-ID` response header both read the request's **local** id (aligned
  by construction, immune to any context-var mutation), while *distant* engine
  logs have only the **ambient** `correlation_id_var` to read. That ambient channel
  stays consistent with the header only while every writer restores the prior value
  on exit. A bare `set()` (e.g. an auth sub-context or a future span/child id) that
  forgets to reset would leave later engine logs stamped with the wrong id while the
  header/summary still show the real one — a silent misalignment that is the worst
  failure mode for a correlation feature. Scoped set/reset makes this correct by
  rule rather than by luck. (Rationale: PR #133 review discussion — the explicit
  pass protects the summary line + header; the ambient channel's alignment rests on
  this discipline.)
- `RequestContextMiddleware` is a `BaseHTTPMiddleware`; add the auth middleware
  with `app.add_middleware` too. Note Starlette runs middleware in **reverse**
  registration order (last-added is outermost). Decide ordering deliberately:
  auth should run inside the request-context middleware so an auth failure is
  still logged with a correlation id — i.e. add auth **before** (so it is inner)
  the context middleware, or have auth read the already-set `correlation_id_var`.
- Keep the security surface **default-off** (no keys configured ⇒ no-op) so the
  152 existing API tests keep passing without modification. This is the same
  backward-compat pattern the modeling epics used (default values preserve
  behaviour).

## Open Questions (for human)

- **Auth model:** static `X-API-Key` from an env var / secret (simple, no
  external service) vs. a heavier OIDC/JWT integration (separate larger epic)?
  Default next session: static API keys, env-driven, default-off.
- **Rate-limit backend:** in-memory per-process (fine for one replica) vs. a
  shared Redis backend for multi-replica. Default: in-memory; Redis noted as a
  Slice-3/follow-up option.
- **Metrics dependency:** dependency-free `/metrics` text exposition vs. optional
  `prometheus-client` extra. Default: optional extra so the core install stays
  lean.
