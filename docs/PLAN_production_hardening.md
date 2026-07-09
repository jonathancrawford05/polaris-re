# PLAN: Production Hardening & Observability (A2′)

**Status:** IN PROGRESS — constituted 2026-07-07 as the active epic. Slice 1
(observability core: structured JSON access logging + correlation IDs +
per-request duration, ADR-133) is **DONE**. Slices 2–3 PLANNED.

**Source / derivation.** With the modeling roadmap complete (ROADMAP Phases 1–5;
all 2026-06-18 Tier-A epics, C0 Asset/ALM, B3 expense-allowance) and the
Validation & Benchmark pack (A1′) shipped, `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`
§4 ranks the remaining Tier-A "big rocks" as **A1′ (done) → A2′ Production
hardening → A3′ Cedant-ingestion robustness**. A1′ was not reference-blocked, so
the review's recommended-sequence fallback (lead with A2′) becomes the next epic
outright: A2′ is the review's #2 Tier-A item (★★★★☆, ~8 d, 3 phases), is fully
specified in ROADMAP 6.2, and decomposes cleanly with no external dependency.

**Why this epic now.** The engine models correctly and a buyer can *validate* the
numbers (A1′). The remaining frontier is *deployability*: can an IT/ops
organisation run the FastAPI service in production with the observability,
security, and deployment surfaces they expect. Nothing here touches the pricing
path — goldens stay byte-identical across the whole epic.

## Overall Goal

Harden the REST API (`polaris_re.api`) and its deployment story to a
production-operable standard per ROADMAP 6.2: structured, correlated,
duration-instrumented request logging; optional API-key authentication and rate
limiting; and Kubernetes/Helm manifests plus a Prometheus/Grafana metrics stack.
The deliverable an ops team can adopt: "point your log aggregator, secret store,
ingress, and metrics dashboard at it and run it."

## Design Anchors

- **Additive and pricing-neutral.** The observability/security surfaces wrap the
  existing app; the pricing pipeline is never touched. QA goldens and the
  `polaris price` regression stay byte-identical for the entire epic.
- **Dependency-light, opt-in.** Slice 1 uses only the standard library
  (`logging`, `uuid`, `contextvars`). Later optional capabilities (rate limiting
  via `slowapi`, OpenTelemetry) go behind optional-dependency extras and default
  to off, so the core `api` extra keeps installing with no new required deps.
- **Clock-safe tests (ADR-074 guard).** Durations use `time.perf_counter`
  (monotonic) and are only ever asserted non-negative; correlation IDs are pinned
  via request headers wherever an exact value is checked. No test reads the wall
  clock.
- **Data/Docker allowlist discipline.** Any files added under `deploy/` or `data/`
  that the test suite or runtime image references are added to the Dockerfile
  `COPY` / `.dockerignore` allowlist in the same slice (recurring trap, PR #61/#66).

## Decomposition

### Slice 1: Observability core — DONE (2026-07-07, ADR-133)
`polaris_re.api.observability`: `JsonLogFormatter` (single-line JSON records),
`RequestContextMiddleware` (assigns a correlation id — echoing an inbound
`X-Request-ID` / `X-Correlation-ID` header else a generated uuid4 — times the
request on a monotonic clock, emits a structured access-log record, and returns
the correlation id + duration as `X-Correlation-ID` / `X-Response-Time-Ms`
response headers), `configure_api_logging` (idempotent, non-propagating access
logger), and a `correlation_id_var` context var the formatter falls back to.
Wired into `api/main.py` at app construction. 12 tests in
`tests/test_api/test_observability.py`. Goldens byte-identical; the 152 existing
API tests and the 76 QA tests stay green.

### Slice 2: API security — API-key auth + rate limiting — NEXT
- **Depends on:** Slice 1 merged.
- Optional API-key authentication middleware (`api/auth.py`): when a configured
  key set is present (env-driven), require a matching `X-API-Key` (or
  `Authorization: Bearer`) header on the pricing/analytics endpoints; the
  system endpoints (`/health`, `/version`, `/docs`, `/openapi.json`) stay open
  for probes. When no keys are configured the middleware is a no-op (backward
  compatible; all existing tests pass unchanged).
- Rate limiting via `slowapi` behind a new optional-dependency extra
  (`api-security` or fold into `api`), default-off, configurable per-route.
- Tests: authorised/unauthorised/absent-config paths; rate-limit trip; probe
  endpoints exempt. Correlation id from Slice 1 stamped on the auth-failure log.
- **Acceptance:** with keys configured, a request without a valid key → 401 and
  a logged auth-failure carrying the correlation id; with no keys configured the
  API behaves exactly as today; rate-limit returns 429 past the threshold.

### Slice 3: Deployment & metrics surfaces — PLANNED
- **Depends on:** Slice 2 merged.
- Kubernetes manifests (`deploy/k8s/deployment.yaml`, `service.yaml`,
  `configmap.yaml`), a Helm chart (`deploy/helm/polaris-re/`), a Prometheus
  metrics endpoint (`/metrics`, request count + duration histogram, dependency-
  light or via an optional exporter), and `docker-compose.yml` `prometheus` +
  `grafana` services for a local dashboard. Update the Dockerfile/`.dockerignore`
  allowlist for any referenced files; QUICKSTART deployment guide.
- Tests: `/metrics` shape/labels; manifest lint/parse (YAML loads, required keys
  present); Helm `template` renders (guarded/skippable if `helm` absent in CI).
- **Acceptance:** `/metrics` exposes request-count/duration series; manifests and
  chart parse; ROADMAP 6.2 checkboxes closed; goldens byte-identical.

## Open Questions (for human)

- **Auth model for Slice 2:** static API keys from an env var / secret is the
  simplest production-credible default and needs no external service. Confirm
  that's acceptable versus a heavier OIDC/JWT integration (which would be a
  separate, larger epic). Default taken next session unless told otherwise:
  static `X-API-Key`, keys from env, default-off.
- **Rate-limit backend:** in-memory (per-process) `slowapi` is fine for a single
  replica; a multi-replica deployment wants a shared Redis backend. Default:
  in-memory, with the Redis backend noted as a Slice-3/follow-up option.
- **Metrics dependency:** prefer a hand-rolled dependency-free `/metrics` text
  exposition, or pull `prometheus-client` in behind an optional extra? Default:
  optional `prometheus-client` extra so the core install stays lean.
