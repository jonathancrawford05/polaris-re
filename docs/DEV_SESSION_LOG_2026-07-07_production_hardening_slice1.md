# Dev Session Log — 2026-07-07

## Item Selected
- **Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4–§5 Tier-A (A2′);
  ROADMAP 6.2. New active epic — `PLAN_production_hardening.md` +
  `CONTINUATION_production_hardening.md` (constituted this session).
- **Priority:** IMPORTANT / Tier-A (★★★★☆) — the trust-and-deployment frontier;
  the review's #2 Tier-A "big rock" after A1′.
- **Title:** Production Hardening & Observability (A2′) — Slice 1: observability
  core (structured JSON access logging + correlation IDs + request duration).
- **Slice:** 1 of 3 — starts the epic (PLAN + Slice 1 = the deliverable per step 5b).
- **Branch:** `claude/loving-gauss-7nbcgj` (designated remote-session branch;
  environment override per step 8 — at origin/main, prior PR merged, restarted clean).

## Selection Rationale
Step 5 found no *other* IN-PROGRESS CONTINUATION to continue: the A1′ Validation
& Benchmark epic (`CONTINUATION_validation_benchmark`) closed COMPLETE last
session (Slice 3, ADR-132, merged as PR #132), and the only remaining IN-PROGRESS
CONTINUATION (`reserve_basis_correctness`) was explicitly **demoted to Tier-D /
NICE-TO-HAVE** by `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §3 and parked
pending the maintainer's redirect go/no-go — it is not the active epic. So per
step 5b(b) no epic was active and the session's job was to **start the next
Tier-A epic** (PLAN + Slice 1 as the sole deliverable; no fallback pick).

Per the review's recommended sequence (§5), A1′ was **not** reference-blocked, so
the fallback-lead (A2′ Production hardening) becomes the next epic outright: it is
the review's #2 Tier-A item (★★★★☆, ~8 d, 3 phases), fully specified in ROADMAP
6.2, and decomposes cleanly with no external dependency. A3′ (cedant-ingestion
robustness) is the review's #3 and follows A2′. The interest-exactness epic stays
parked open-but-deprioritised (exactly one active epic invariant preserved).

## Decomposition Plan (active epic status)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Observability core — JSON access log + correlation IDs + duration | ✅ Done | (this PR) |
| 2 | API-key auth + rate limiting (optional, default-off) | ⏳ Next | — |
| 3 | K8s/Helm manifests + Prometheus `/metrics` + Grafana compose | 🔲 Planned | — |

## Selection Rationale — premise verified (step 7b)
Reproduced the claimed gap before writing code: `grep` for
`middleware|getLogger|correlation|X-Request-ID|X-Correlation` in `api/main.py`
returned **0** — the FastAPI service had no request logging, no correlation IDs,
and no duration metric. ROADMAP 6.2's checkboxes are all unchecked. Premise holds;
the slice is real, not a no-op.

## What Was Done
Constituted the A2′ epic (PLAN + CONTINUATION) and shipped Slice 1. New
dependency-free module `polaris_re.api.observability`:

- `JsonLogFormatter` — renders each `LogRecord` as single-line JSON (timestamp,
  level, logger, message, correlation id, structured `extra`s), machine-parseable
  by a log aggregator.
- `RequestContextMiddleware` (Starlette `BaseHTTPMiddleware`) — assigns every
  request a correlation id (echoing an inbound `X-Request-ID` / `X-Correlation-ID`
  header for trace propagation, otherwise a uuid4 hex), times it on
  `time.perf_counter` (monotonic), emits a structured access-log record, and
  returns the correlation id and duration as the `X-Correlation-ID` /
  `X-Response-Time-Ms` response headers.
- `configure_api_logging` — idempotently attaches the JSON handler to a dedicated,
  non-propagating `polaris_re.api.access` logger.
- `correlation_id_var` (`ContextVar`) — publishes the id so any engine log during
  the request can be stamped with it; the formatter falls back to it.

Wired into `api/main.py` at app construction (`configure_api_logging()` +
`app.add_middleware(RequestContextMiddleware)`). ADR-133 + an ARCHITECTURE §7 note
and a design-decisions table row.

This is an **additive infrastructure** slice: it wraps the existing app and
touches no pricing-path code. Goldens are byte-identical (the 76-test QA golden
suite is green and the `polaris price` regression on `golden_config_flat.json`
exits 0 unchanged). No new `data/`/`deploy/` files and no new runtime dependency,
so no Dockerfile / `.dockerignore` change was needed this slice (Slice 3 will add
manifests and must update the allowlist then).

## Files Changed
- `src/polaris_re/api/observability.py` — **new** module
- `src/polaris_re/api/main.py` — import + `configure_api_logging()` +
  `add_middleware(RequestContextMiddleware)` at app construction
- `tests/test_api/test_observability.py` — **new** (12 tests)
- `docs/DECISIONS.md` — ADR-133
- `ARCHITECTURE.md` — API Observability paragraph (§7) + decisions-table row
- `docs/PLAN_production_hardening.md` — **new** (epic plan, Slice 1 DONE)
- `docs/CONTINUATION_production_hardening.md` — **new** (Status IN PROGRESS)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — ledger-heal (A2′ constituted, Slice 1
  shipped, under the productization direction item) + harvest (OpenTelemetry
  trace spans, NICE-TO-HAVE)

## Tests Added
- `tests/test_api/test_observability.py` (12): correlation id generated when
  absent and echoed from `X-Request-ID` / `X-Correlation-ID`; ids differ across
  requests; `X-Response-Time-Ms` is a non-negative float; the access-log record
  carries `method`/`status_code`/`correlation_id`/non-negative-float `duration_ms`
  (incl. a 404 with its real status); the JSON formatter emits intrinsic keys,
  honours an explicit `correlation_id`, falls back to the context var, and omits
  the key when unset; `configure_api_logging` is idempotent + non-propagating; the
  middleware is installed on the app. Clock-safe (durations asserted non-negative
  only; ids pinned via headers — ADR-074 guard).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Every request carries a correlation id (inbound echo or generated) | ✅ | `X-Correlation-ID` response header; uuid4 fallback |
| Structured JSON access log with method/path/status/duration/correlation | ✅ | `JsonLogFormatter` + `RequestContextMiddleware` |
| Per-request duration metric | ✅ | monotonic `perf_counter`; `X-Response-Time-Ms` header + `duration_ms` log field |
| No new runtime dependency | ✅ | standard library only (`logging`/`uuid`/`contextvars`) |
| Additive — existing API behaviour unchanged | ✅ | 152 API tests + 76 QA tests green, no assertion changes |
| Goldens / QA byte-identical | ✅ | QA golden suite green; `polaris price` regression unchanged |
| ADR + ARCHITECTURE note | ✅ | ADR-133; §7 paragraph + table row |
| Epic constituted (PLAN + CONTINUATION) | ✅ | both new; CONTINUATION IN PROGRESS |

## Open Questions / Follow-ups
- **Slice 2 auth model (for the maintainer):** static `X-API-Key` from an env
  var / secret (simple, no external service, default-off) vs. a heavier OIDC/JWT
  integration (separate larger epic)? Default next session: static API keys,
  env-driven, default-off. (Detail in the CONTINUATION Open Questions.)
- **Slice 2 rate-limit backend:** in-memory `slowapi` (single replica) vs. shared
  Redis (multi-replica). Default: in-memory; Redis noted as a follow-up.
- **Slice 3 metrics dependency:** dependency-free `/metrics` text vs. optional
  `prometheus-client` extra. Default: optional extra to keep the core install lean.
- **OpenTelemetry trace spans** — harvested to PRODUCT_DIRECTION as NICE-TO-HAVE
  (ADR-133 Out of scope); deeper span-level tracing beyond the per-request log.
- **Interest-exactness redirect go/no-go** still reserved for the maintainer
  (carried from last session); the epic stays parked (Tier-D).

## Parked Polish
None (no 3rd-order-or-deeper follow-ups surfaced this session).

## Impact on Golden Baselines
None. Slice 1 is additive API infrastructure — a middleware + logging module +
tests only. The pricing path is untouched; the QA golden suite is green and the
`polaris price` regression on `golden_config_flat.json` is unchanged.

```
Baseline `make test`: 2056 passed, 2 skipped, 110 deselected, 0 failures
  (prior session log baseline: 2056 passed — Slice 3's post-slice count, now on
  main via PR #132; no new/changed failures, tolerance-aware check passes).
After this slice: 2068 passed, 2 skipped, 110 deselected (+12 = the new
  observability tests).
```
