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
- **Status:** DONE
- **Branch:** `claude/loving-gauss-xmn386` (designated remote-session branch)
- **PR:** #134 (draft)
- **Depends on:** Slice 1 merged.
- **What was done:** New `polaris_re.api.auth` module — two **default-off**
  Starlette middlewares wired *inside* `RequestContextMiddleware`:
  `APIKeyAuthMiddleware` (env `POLARIS_API_KEYS`; `X-API-Key` or
  `Authorization: Bearer`; 401 + correlation-stamped log; probes exempt) and
  `RateLimitMiddleware` (env `POLARIS_API_RATE_LIMIT` e.g. `100/minute`; 429 +
  `Retry-After`; backed by a hand-rolled `SlidingWindowRateLimiter` with an
  injectable clock). Config read per-request ⇒ unset env is a true no-op. 34 new
  tests; the 152 existing API tests + 76 QA tests stay green; goldens
  byte-identical. ADR-134.
- **Key decisions:**
  - **Dependency-free rate limiter** (deliberate deviation from this plan's
    `slowapi` suggestion): `slowapi` is not installed and would add a runtime
    dependency, whereas Slice 1 stayed stdlib-only and the epic anchor is
    "dependency-light". The hand-rolled limiter's injectable clock makes
    window behaviour testable without the wall clock (ADR-074 guard).
  - Middleware order: `RequestContext` (outer) → `RateLimit` → `Auth` (inner),
    so a 401/429 is logged with the correlation id and the rejection response
    carries `X-Correlation-ID`. (Followed the CONTINUATION guidance: auth runs
    inside the context middleware and reads the already-set `correlation_id_var`
    — no nested `correlation_id_var.set()`, so the token-scoping rule is moot
    here.)
  - Rate limit is per client host, in-process (single-replica correct); Redis
    backend + per-route/per-key tiers harvested as follow-ups.
- **Acceptance criteria:** ALL MET
  - Keys configured → request without a valid `X-API-Key` returns 401 with a
    logged, correlation-stamped auth failure. ✅
  - No keys configured → API behaves exactly as today (all existing tests pass). ✅
  - Requests past the configured threshold return 429. ✅

### Slice 3: Deployment & metrics surfaces
- **Status:** NEXT
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

## Context for Slice 3 (metrics & deployment)

- Slice 2 settled the auth/rate-limit surfaces: static env-driven `X-API-Key`
  (default-off) and an **in-process** sliding-window limiter. Redis backend and
  per-route/per-key tiers were harvested to PRODUCT_DIRECTION as follow-ups, not
  built. Slice 3 does not need to revisit them.
- `EXEMPT_PATHS` in `api/auth.py` (`/health`, `/version`, `/docs`, `/redoc`,
  `/openapi.json`) is the canonical probe/doc set. If Slice 3 adds a `/metrics`
  endpoint that a Prometheus scraper hits, decide whether it too should be
  exempt from auth/rate-limiting (a scraper cannot present a key) — likely yes;
  add it to `EXEMPT_PATHS`.
- Reuse Slice 1's per-request `duration_ms` + `status_code` for the metrics
  histogram/counter rather than re-instrumenting; a metrics middleware can sit
  alongside the existing stack (mind the reverse registration order).
- **Data/Docker allowlist discipline (recurring trap, PR #61/#66):** Slice 3
  adds files under `deploy/`; update the Dockerfile `COPY` / `.dockerignore`
  allowlist in the SAME PR if the runtime image or tests reference them.

## Open Questions (for human)

- **Metrics dependency (Slice 3):** dependency-free `/metrics` text exposition
  vs. optional `prometheus-client` extra. Default: dependency-free text
  exposition to keep the zero-new-runtime-dep property the whole epic has held.
- **Rate-limit backend for multi-replica:** the shipped limiter is in-process
  (single-replica correct). A shared Redis backend is a harvested follow-up
  (IMPORTANT) — confirm whether multi-replica is an early deployment target.
- **Auth model beyond static keys:** static `X-API-Key` (shipped) vs. a heavier
  OIDC/JWT integration (harvested as a separate larger-epic follow-up).
