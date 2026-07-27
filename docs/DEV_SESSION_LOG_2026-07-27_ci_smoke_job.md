# Dev Session Log — 2026-07-27

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — Promoted Follow-ups, **IMPORTANT #8**
  ("CI smoke-test job (real entry points)"). *Source: maintainer discussion
  2026-07-12 (CI perf/smoke thread), 1st-order.*
- **Priority:** IMPORTANT
- **Title:** CI smoke-test job — boot the real deployed entry points (uvicorn + `polaris` CLI)
- **Slice:** complete (SMALL item — 4 files + tests, no contract change)
- **Branch:** `claude/loving-gauss-9ibm60` (environment-designated)

## Selection Rationale
**Maintenance mode.** The entire written roadmap has shipped: the A4′
experience-GAM epic is COMPLETE, and the maintainer-directed post-A4′ Sprint 0
(S1 pipeline relocation, S2 MI dashboard, S3 = B1/B2/B4 quick wins) is fully
drawn down. No unstarted Tier-A "big rock" remains and no Phase-7 frontier has
been chosen (awaiting maintainer, `PRODUCT_DIRECTION_2026-07-24` "Decision
Surfaced"). Per the ACTIVE-EPIC guardrail, with no startable Tier-A epic the
session correctly falls to gated fallback and **flags maintenance mode**.

Step 5 found two IN PROGRESS CONTINUATIONs: `expense_allowance_duration` (its
mandatory Slice 2 merged as PR #169 this window; only the optional 2nd-order
Slice 3 remains, already promoted NICE-TO-HAVE — a human-decision to close, left
IN PROGRESS) and `reserve_basis_correctness` (explicitly parked). Neither is an
advanceable epic slice, so selection fell to the highest-value gated fallback:
the IMPORTANT tier of the latest PRODUCT_DIRECTION.

**Premise verification (step 7b) reshaped the pick.** The nominal top IMPORTANT
item, **#1 (statutory valuation mortality table for CRVM)**, does **not** hold:
the distinct `assumptions.valuation_mortality` slot already exists and CRVM /
VM-20 value on it (shipped in ADR-125, Reserve-Basis Exactness Slice 1, well
after the item's ADR-089 source). Following it literally would ship a no-op — so
it was **pruned** (struck SHIPPED by inspection, step 6) rather than
re-implemented. Of the surviving IMPORTANT items, #2 moves goldens (rebaseline
risk), #4 is the parked reserve-basis-correctness interest helper, #6/#7 need an
external shared backend (not in-process testable), #11 is a maintainer decision,
and #12/#3/#5 are shipped. **#8 (CI smoke-test job)** is the one remaining
IMPORTANT item that is self-contained, pytest-verifiable, and closes a genuine
deploy-safety gap — its premise was confirmed to hold (no `smoke` marker, no
`tests/smoke/`, no CI job boots a real server or the console script).

## What Was Done
Reproduced the gap first: the entire suite drives the app in-process
(`TestClient` for the API, direct function imports for the CLI), so a broken ASGI
lifespan, console-script packaging fault, import-time failure, or a crashing
`benchmark`/`price` entry point would ship green. Confirmed by hand that a real
`uvicorn polaris_re.api.main:app` boot + `polaris price` + `polaris benchmark
--pack closed-form` all work, then encoded that as a gated test layer.

Added `tests/smoke/test_smoke_entrypoints.py`: a module-scoped fixture spawns a
real `python -m uvicorn` server on an ephemeral port and polls `/health` (30 s
boot timeout, fails loudly with captured server output on death/timeout); tests
then hit the live server for `/health`, `/metrics` (Prometheus text), and a real
`POST /api/v1/price` (asserting priced output — `pv_profits`,
`reinsurer_pv_profits`, `premium_sufficiency`, `n_policies`). Two further tests
shell out to `python -m polaris_re.cli` for `price` on the golden deal (exit 0 +
valid JSON) and `benchmark --pack closed-form` (exit 0 → all reference cases
passed). All tagged `smoke` **and** `slow`, so the fast matrix (`make test` /
CI `-m "not slow"`) and the Docker job (`-m 'not slow'`) skip them; a dedicated
CI `smoke` job selects them via `-m smoke`. Whole suite runs in **~4.6 s**.

Design rule honoured (per the CI perf/smoke group): smoke assertions are
pass/fail on deterministic outcomes (boots? 200? cases passed?), never on
wall-clock latency. Recorded ADR-168.

## Files Changed
- `tests/smoke/__init__.py` — new smoke package (purpose docstring).
- `tests/smoke/test_smoke_entrypoints.py` — 5 smoke tests (new).
- `pyproject.toml` — registered the `smoke` pytest marker.
- `.github/workflows/ci.yml` — new `smoke` CI job (needs `lint`; uv sync + tables
  + `pytest tests/smoke -m smoke`); comment-renumbered the coverage job.
- `Makefile` — `make smoke` target + `.PHONY`.
- `docs/DECISIONS.md` — ADR-168.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — struck IMPORTANT #1 (pruned, ADR-125)
  and IMPORTANT #3 (PR #169 merged, step 4b); harvested ADR-168 out-of-scope
  follow-ups.

## Tests Added
- `tests/smoke/test_smoke_entrypoints.py` — `test_health_endpoint_live`,
  `test_metrics_endpoint_live`, `test_price_endpoint_live` (real uvicorn),
  `test_cli_price_entrypoint`, `test_cli_benchmark_entrypoint` (real console
  script). All `-m smoke`; 5 passed in 4.61 s.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Fast (<30 s) deterministic CI job boots the real entry points | ✅ | smoke suite ~4.6 s; dedicated `smoke` CI job |
| Boots uvicorn + curls `/health`, `/metrics`, real `/api/v1/price` | ✅ | live server fixture, 3 endpoint tests |
| Runs `polaris price` + `polaris benchmark --pack closed-form` | ✅ | 2 subprocess CLI tests, exit-0 + valid-JSON asserts |
| Gates merges | ✅ | `smoke` job added to CI (needs `lint`) |
| Excluded from the fast matrix + Docker job (no server-in-container) | ✅ | `slow`-tagged; both run `-m 'not slow'` |
| Goldens byte-identical | ✅ | test-/CI-/docs-only; no `src/` change; `polaris price` on `golden_config_flat.json` unchanged, `tests/qa/` 94 passed |
| Quality gate (ruff format + check, qa suite) | ✅ | ruff clean; qa 94 passed; ci.yml valid YAML |

## Open Questions / Follow-ups
- **Close `CONTINUATION_expense_allowance_duration` as COMPLETE?** Mandatory scope
  (Slice 2, PR #169) is merged; only the optional 2nd-order Slice 3 remains
  (already promoted NICE-TO-HAVE). Left IN PROGRESS pending the same human
  decision the prior session flagged — not closed autonomously.
- **Phase-7 frontier still unchosen.** The routine remains in maintenance mode;
  after this pick the next gated fallbacks are the remaining IMPORTANT infra items
  (#6/#7 shared backends, #9/#10 perf harness — the noise-normalized companion to
  this pass/fail smoke gate) and the Tier-C queue (C4/C5/C6).

## Parked Polish
None. ADR-168's out-of-scope items are all 1st-order follow-ups of the
originally-planned smoke job and were promoted as NICE-TO-HAVE (step 17), not
parked. The perf-verdict-in-CI note is the existing IMPORTANT #9/#10, not a new
3rd-order item.

## Impact on Golden Baselines
None. Test-, CI-, and docs-only — no `src/` code changed, so every golden config
and `polaris price` output is byte-identical by construction. Confirmed:
`polaris price` on `golden_config_flat.json` unchanged; `tests/qa/` 94 passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2609 passed, 3 skipped, 113 deselected**, 0 failures (tolerance-aware; SOA VBT
/ CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline, matching the recorded prior-session pattern of 2603 passed). No new or
changed failures, so the session PROCEEDED. The new smoke tests are `slow`-tagged
and so are not part of this fast-suite count (they run via `-m smoke`: 5 passed).
