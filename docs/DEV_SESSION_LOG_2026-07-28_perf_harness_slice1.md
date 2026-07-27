# Dev Session Log — 2026-07-28

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — Carried-Forward Promoted
  Follow-ups, **IMPORTANT #9** ("Performance harness with same-run head-vs-main
  baseline"). *Source: maintainer discussion 2026-07-12 (CI perf/smoke thread),
  1st-order.*
- **Priority:** IMPORTANT
- **Title:** Performance-regression harness — deterministic-first probe (perf epic)
- **Slice:** 1 of 3 (+1 optional follow-on = IMPORTANT #10)
- **Branch:** `claude/loving-gauss-ixouzo` (environment-designated)

## Selection Rationale
**Maintenance mode (still).** The entire written roadmap has shipped — the A4′
experience-GAM epic is COMPLETE and the maintainer-directed post-A4′ Sprint 0
(S1 pipeline relocation, S2 MI dashboard, S3 = B1/B2/B4 Tier-B quick wins) is
fully drawn down. No unstarted Tier-A "big rock" remains and no Phase-7 frontier
has been chosen (`PRODUCT_DIRECTION_2026-07-24` "Decision Surfaced"). Per the
ACTIVE-EPIC guardrail, with no startable Tier-A epic the session falls to gated
fallback and **flags maintenance mode**.

Step 5 found two IN PROGRESS CONTINUATIONs, neither an advanceable epic slice:
`expense_allowance_duration` (mandatory Slice 2 merged as PR #169; only the
optional 2nd-order Slice 3 remains, already promoted NICE-TO-HAVE) and
`reserve_basis_correctness` (explicitly parked). So selection fell to the
highest-value gated fallback.

**Why #9 over the alternatives.** Among the surviving IMPORTANT follow-ups: #2
(WL terminal-reserve) moves goldens → rebaseline risk; #4 is the parked
reserve-basis-correctness interest helper (Tier D); #6/#7 need an external
shared backend (not in-process testable); #11 is a maintainer decision; the new
ADR-160 LICAT-calibration item is a large ALM modelling task that flips capital
numbers; the new ADR-162 roll-forward item is blocked on a per-survivor
normalization design question. **#9 is the one remaining IMPORTANT item that is
self-contained, pytest-verifiable, goldens-byte-identical, and unblocked** — and
it is the explicit *deterministic companion* to the pass/fail smoke gate shipped
last session (IMPORTANT #8 / ADR-168), the next item the prior session's Open
Questions named. It also unblocks IMPORTANT #10 and NICE-TO-HAVE #62/#63. Tier-C
(C4/C5/C6) ranks below IMPORTANT and was not reached.

**Premise verification (step 7b).** Confirmed the gap holds: no `tests/perf/`,
no `perfbench`, no `perf.json`, no CI job comparing head vs main. B2's scale
benchmark (ADR-161) publishes a static committed timing *table* and one `slow`
scaling-shape test (4× block < 6× time) — it emits no machine-readable payload
and does no per-run head-vs-main comparison, so slow multi-month creep goes
uncaught. Premise confirmed.

The item is MEDIUM (harness core → head-vs-main driver → CI job across slices),
so it was decomposed into a PLAN + CONTINUATION and **Slice 1** shipped this
session.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Deterministic perf-probe core (`analytics/perf_harness.py` + `tests/perf/`) | ✅ Done | *(this PR)* |
| 2 | Head-vs-main same-job driver + `perf.json` diff/verdict | ⏳ Next | — |
| 3 | CI perf job (gates structural deltas, alerts on wall-time ratio) — closes #9 | 🔲 Planned | — |
| 4 | (optional / IMPORTANT #10) per-merge `perf/history.jsonl` + creep detection | 🔲 Planned | — |

## What Was Done
Scoped the design against evidence first (step 7b applied to the design, not
just the premise): a 3 000-policy × 240-month TERM projection repeated in-process
showed single-run wall-clock has ~2× local jitter (651 ms first call → ~290 ms
after), `tracemalloc` peak carries ~0.005% byte-level jitter but is stable at MiB
granularity, and the structural counts + a rounded output digest are exactly
reproducible. This confirmed the maintainer's non-negotiable rule empirically:
**deterministic / noise-normalized metrics may gate or alert; raw wall-time only
informs.**

Added `analytics/perf_harness.py` — `PerfProbe` (one hot-path row) + `PerfReport`
(container with `to_perf_dict()` / `to_json()` emitting the `perf.json` shape),
and `run_perf_probe(...)` timing a mapping of named hot-path callables (default:
the production `get_product_engine(...).project()` path) on a fixed synthetic
block reused from B2's `build_homogeneous_block`. Each probe splits its metrics
by consumption discipline — the model itself encodes the rule: `deterministic_metrics()`
returns exactly the hard-gate-safe set (`n_policies`, `projection_months`,
`n_cells`, `output_fingerprint`); `peak_mib` is coarse alert-grade; and
`best_of_k_seconds` (min over `k`, the stable estimator) + raw `samples_seconds`
are informational only. The `output_fingerprint` is a blake2b digest of the
rounded core `CashFlowResult` arrays — a correctness tripwire proving two
branches ran the same computation. Recorded **ADR-169**.

Tests split into a fast unit layer (fingerprint determinism, model helpers,
`perf.json` shape, input validation — no engine, stays in `-m "not slow"`) and a
`perf`+`slow` end-to-end layer whose load-bearing assertion is that two runs on
the same block yield byte-identical deterministic metrics (MiB-peak to within
±1). Registered a `perf` marker (also `slow`), a `make perf` target. Additive
only — no `src/` pricing path touched, goldens byte-identical by construction.

## Files Changed
- `src/polaris_re/analytics/perf_harness.py` — new deterministic perf-probe core.
- `src/polaris_re/analytics/__init__.py` — export `PerfProbe`, `PerfReport`,
  `run_perf_probe`, `output_fingerprint`, `default_hot_paths`.
- `tests/perf/__init__.py`, `tests/perf/test_perf_harness.py` — new `perf`+`slow`
  end-to-end reproducibility/invariant tests.
- `tests/test_analytics/test_perf_harness_units.py` — fast unit tests (no engine).
- `pyproject.toml` — registered the `perf` pytest marker.
- `Makefile` — `make perf` target + `.PHONY`.
- `docs/DECISIONS.md` — ADR-169.
- `docs/PLAN_perf_harness.md`, `docs/CONTINUATION_perf_harness.md` — epic plan +
  IN PROGRESS running log.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — struck IMPORTANT #8 (PR #170 merged,
  ledger-healing step 4b); harvested ADR-169 out-of-scope follow-ups.

## Tests Added
- `tests/test_analytics/test_perf_harness_units.py` — 12 fast tests (fingerprint
  determinism/perturbation/-0.0 normalization, `deterministic_metrics` subset,
  `perf.json` ordering, `to_json` validity, `default_hot_paths` freshness, three
  validation-error paths).
- `tests/perf/test_perf_harness.py` — 6 `perf`+`slow` tests (one-probe-per-path,
  structural self-consistency, **deterministic-metric reproducibility across two
  runs**, timing arithmetic invariants, custom multi-path probing, `perf.json`
  round-trip). All 18 pass.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `perf.json` machine-readable payload for engine hot paths | ✅ | `PerfReport.to_perf_dict()`/`to_json()`, deterministic-first |
| Deterministic structural metrics reproducible run-to-run | ✅ | `test_deterministic_metrics_are_reproducible` — byte-identical counts+fingerprint, MiB-peak ±1 |
| Metrics split so a future gate reads only deterministic ones | ✅ | `PerfProbe.deterministic_metrics()`; timing/raw-bytes excluded |
| Best-of-k min timing (stable estimator), never gates absolutely | ✅ | `best_of_k == min(samples)`; wall-time informational only |
| Goldens byte-identical | ✅ | additive module; `polaris price` on flat config exit 0; `tests/qa/` 94 passed |
| Quality gate (ruff format+check, fast suite, qa) | ✅ | ruff clean; qa 94 passed; new-module mypy clean |
| Head-vs-main comparison + CI job | ⏳ | Slice 2 / Slice 3 (out of scope this slice) |

## Open Questions / Follow-ups
- **Surface as `polaris perfbench`?** Slice 2 could expose the head-vs-main
  runner as a CLI subcommand or leave it a `scripts/` tool (B2's precedent:
  `scripts/scale_benchmark.py`, deliberately not a `polaris` subcommand). Defer
  to the maintainer's script-first precedent unless a CLI surface is requested.
- **Wall-time alert band.** The head/main ratio alert threshold (default proposal
  1.5×) is a policy choice; confirm before Slice 3 alerts CI on it (as an alert,
  never a hard gate).
- **Close `CONTINUATION_expense_allowance_duration` as COMPLETE?** Unchanged from
  the prior two sessions — mandatory scope (Slice 2, PR #169) merged; only the
  optional 2nd-order Slice 3 remains (already promoted NICE-TO-HAVE). Left IN
  PROGRESS pending the same human decision.

## Parked Polish
None. ADR-169's out-of-scope items are all 1st-order follow-ups of the
originally-planned perf epic and are tracked as the epic's own later slices
(Slice 2/3/4) in `CONTINUATION_perf_harness.md`, not promoted as loose
PRODUCT_DIRECTION items and not parked.

## Impact on Golden Baselines
None. A new self-contained diagnostic module off the import/pricing hot path
plus tests, one marker, one Makefile target, and docs — no `src/` pricing code
changed, so every golden config and `polaris price` output is byte-identical by
construction. Confirmed: `polaris price` on `golden_config_flat.json` exit 0;
`tests/qa/` 94 passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2609 passed, 3 skipped, 118 deselected**, 0 failures (tolerance-aware; SOA VBT
/ CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline, matching the recorded prior-session count of 2609 passed / 3 skipped;
the deselected count rose 113→118 only because the prior session's 5 smoke tests
are now `slow`-tagged). No new or changed failures, so the session PROCEEDED.
The 12 new fast perf-unit tests are added to the fast suite; the 6 new perf tests
are `perf`+`slow` and run via `-m perf` (18 perf tests pass).
