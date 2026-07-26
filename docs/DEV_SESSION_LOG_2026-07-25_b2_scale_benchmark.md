# Dev Session Log — 2026-07-25 (B2 — Scale benchmark)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` → "Recommended Next Sprint" **S3**,
  item **B2** ("Scale benchmark at 100K–500K policies — publish a timing table;
  back the README perf claim").
- **Priority:** Tier-B (Sprint-0 quick win) — **gated fallback, maintenance mode.**
- **Title:** Scale benchmark — reproducible projection timings backing the
  "vectorized, no loops over policies" claim.
- **Slice:** complete (SMALL item — 1 session).
- **Branch:** `claude/loving-gauss-llczcz` (environment-designated `claude/*` branch;
  `feat/auto-*` default overridden).
- **PR:** #163 (draft) — https://github.com/jonathancrawford05/polaris-re/pull/163

## Selection Rationale
**Maintenance mode.** The entire written roadmap has shipped (A4′ experience-GAM
was the last unstarted Tier-A epic; `CONTINUATION_experience_gam` is COMPLETE).
Per `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7 and `PRODUCT_DIRECTION_2026-07-24`,
**no startable Tier-A epic remains** — the only Tier-A-scale items are
AXIS/Prophet reconciliation (reference-blocked) and a new Phase-7 frontier
(awaiting maintainer). The one IN PROGRESS CONTINUATION (`reserve_basis_correctness`)
is explicitly DEPRIORITISED/parked. So step 5b's always-on-Epic requirement has
nothing to constitute, and the routine correctly falls to gated Tier-B fallback
(the ACTIVE-EPIC guardrail's "no startable epic" branch).

The maintainer-directed post-A4′ sprint is **S1** (pipeline relocation — DONE,
`CONTINUATION_pipeline_relocation` COMPLETE), **S2** (MI dashboard page — DONE,
`CONTINUATION_mi_dashboard` COMPLETE), then **S3** = B1 → B2 → B4 (value-per-day
order). **B1** shipped last session (PR #162 / ADR-160). **B2** is next and is
self-contained, clearly scoped (publish a timing table), and pytest-testable. No
other fallback item was taken. This session log records maintenance mode, as the
07-24 direction file requires.

## Verify Premise (step 7b)
Reproduced, before writing code, that B2's premise holds:
- Searched for any existing scale/timing/throughput benchmark — none. `polaris
  benchmark` runs the **correctness** validation pack (`ValidationReport`,
  pass/fail vs actuarial references), not timing.
- The README made a qualitative vectorization claim ("NumPy `(N × T)` arrays
  throughout; no loops over policies") but published **no numbers**.
- Timing probes confirmed the engine is genuinely near-linear (throughput
  ~7.5K–17K policies/sec from 1K to 500K), so a published table is truthful
  evidence, not a claim to walk back. Premise holds.

## Baseline / Ledger / Housekeeping Note
- **Baseline** `make test` at session start (base `f69f638` = PR #162 = current
  `origin/main`): **2495 passed, 3 skipped, 112 deselected**, 0 failures — matches
  the standing tolerance-aware baseline (VBT/CSO tables OK; CIA 2014 MISSING →
  the 3 skips). No new/changed failures → proceeded. After this session:
  **2511 passed** (+16 non-slow) + 1 `@slow` scaling test (113 deselected);
  QA suite **88 passed**; ruff clean on `src/ tests/`.
- **Base-branch reconciliation (step 8 / guardrails).** The local `origin/main`
  ref was stale at PR #139; a fresh `git fetch origin main` showed `origin/main`
  is actually at **f69f638 (PR #162)** — the maintainer has merged the whole
  #141–#162 integration line into `main`. The designated branch
  `claude/loving-gauss-llczcz` already carried #162, so B2 was committed on top of
  it; the PR (base `main`) shows exactly the single B2 commit. No prior unmerged
  commits were discarded.
- **Ledger-heal (step 4b).** No un-crossed merged PRs: the last merged PR (#162 /
  B1) was already struck through in `PRODUCT_DIRECTION_2026-07-24.md` by the B1
  session, and `list_pull_requests state=open` → `[]` (no other drafts). This
  session strikes through **B2** with a SHIPPED (PR #163) footer.

## What Was Done
Shipped B2 as an additive analytics component plus published evidence:

- **`analytics/scale_benchmark.py`** — `run_scale_benchmark(sizes, assumptions,
  config)` times the **production** pricing path (`get_product_engine(...).project()`
  — the same call the CLI/API use) for each block size and returns a Pydantic
  `ScaleBenchmarkReport` of `ScaleBenchmarkRow`s (`n_policies`,
  `projection_months`, `projection_seconds`, `policies_per_second`,
  `cell_updates_per_second`, `peak_rss_mb`) with a `to_markdown()` renderer.
  `build_homogeneous_block(n, *, valuation_date, seed)` produces a deterministic,
  clock-pinned synthetic TERM block. Sizes must be strictly ascending, which makes
  each row's peak-RSS attribution exact (`ru_maxrss` is a process high-water mark,
  so each larger run's peak *is* that size's peak). Only `project()` is timed
  (build cost excluded).
- **`scripts/scale_benchmark.py`** — regenerates the committed table (prefers the
  real SOA VBT 2015 table, falls back to the committed synthetic fixture).
- **README *Performance & scale*** + **`docs/PERFORMANCE.md`** — the committed
  table (1K→500K over a 20-year monthly horizon) and methodology. Reading: 5× the
  policies (100K→500K) → ~5.8× the time — the signature of an O(N) vectorized
  engine, not O(N²).
- **ADR-161.** Additive-only — no pricing path, `Policy`/`CashFlowResult`/
  `InforceBlock` contract, treaty, CLI, or golden touched.

## Files Changed
- `src/polaris_re/analytics/scale_benchmark.py` — new harness + Pydantic models (+243).
- `src/polaris_re/analytics/__init__.py` — export the four new public names.
- `scripts/scale_benchmark.py` — new table regenerator (+104).
- `README.md` — new *Performance & scale* section with the committed table.
- `docs/PERFORMANCE.md` — new methodology/table/usage page (+83).
- `docs/DECISIONS.md` — ADR-161.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — B2 struck through SHIPPED (PR #163);
  harvested ADR-161 follow-ups.
- `docs/DEV_SESSION_LOG_2026-07-25_b2_scale_benchmark.md` — this log.

## Tests Added
`tests/test_analytics/test_scale_benchmark.py` (17), data-independent (committed
`synthetic_select_ultimate.csv` fixture):
- **Block builder:** deterministic for a given seed; different seeds change ages;
  `valuation_date` is caller-pinned (never `date.today()` — ADR-074 guard); ages
  within requested bounds; rejects non-positive size and inverted age bounds.
- **Harness (closed-form):** `policies_per_second == n / seconds` and
  `cell_updates_per_second == n × months / seconds` (the defining ratios);
  `projection_months == horizon_years × 12`.
- **Report:** records config; one row per ascending size; Markdown has the header
  columns + a rendered row per size; custom block builder honoured; Pydantic
  round-trip; memory-measurement toggle.
- **Validation:** empty / non-positive / non-ascending / duplicate sizes raise
  `PolarisValidationError`.
- **`@pytest.mark.slow` scaling invariant:** 4× the block takes < 6× the time —
  catches a reintroduced per-policy Python loop that would make `project()` O(N²).

## Acceptance Criteria
| Criterion (B2) | Status | Notes |
|----------------|--------|-------|
| Scale benchmark at 100K–500K policies | ✅ | Harness + committed table run to 500K (66 s, ~10 GB RSS) |
| Publish a timing table | ✅ | README *Performance & scale* + `docs/PERFORMANCE.md` |
| Back the README perf claim | ✅ | Linear-scaling evidence for "vectorized, no loops over policies" |
| Reproducible | ✅ | `scripts/scale_benchmark.py`; seeded, clock-pinned fixtures |
| Engine/goldens byte-identical | ✅ | Additive-only; golden `flat` `polaris price` exit 0, unchanged; QA guards green |

## Open Questions / Follow-ups
- **Phase-7 frontier decision remains open** (unchanged from the 07-24 direction
  file). Until the maintainer chooses a frontier, the routine stays in maintenance
  mode, drawing the Tier-B/C queue down one quick win at a time. Next fallback
  after B2 is **B4** (premium-deficiency reserve / loss recognition).
- ADR-161 out-of-scope items harvested to `PRODUCT_DIRECTION_2026-07-24.md`
  Promoted Follow-ups (see step 17 below): `polaris scale-benchmark` CLI
  subcommand; benchmark other product engines; CI perf-regression gate (overlaps
  the existing IMPORTANT CI-perf item).

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups surfaced this session — the three
harvested items are all 1st-order follow-ups of the planned Tier-B item B2.)

## Impact on Golden Baselines
None. Additive-only — a new `analytics/scale_benchmark.py` diagnostic harness,
a script, and docs; no pricing path, assumption/data contract, treaty, or CLI
pricing surface touched. Golden `polaris price` (`golden_inforce.csv` +
`golden_config_flat.json`): exit 0, unchanged; QA suite 88 passed (golden guards
included).
