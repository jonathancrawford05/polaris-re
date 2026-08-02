# Dev Session Log — 2026-08-02

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — **IMPORTANT #10** (per-merge
  `perf/history.jsonl` creep log). Backed by `PLAN_perf_harness.md` §3 Slice 4
  (the perf epic's optional follow-on, UNBLOCKED 2026-08-01 when #9 closed).
- **Priority:** IMPORTANT.
- **Title:** Per-merge performance history log + long-baseline creep detection.
- **Slice:** Complete (single session — the record + creep-detection capability;
  see "Selection Rationale" for why the CI-on-main auto-append is a harvested
  follow-up, not slice 2 of an in-progress CONTINUATION).
- **Branch:** `claude/loving-gauss-apv1b2` (environment-designated).

## Selection Rationale
**No active Tier-A epic; maintenance mode.** Step 5 found only one IN PROGRESS
CONTINUATION (`reserve_basis_correctness`), which is explicitly *parked /
deprioritised* (not the active epic), so it was not continued. Step 5b: the
entire written roadmap has shipped — the A4′ experience-GAM epic
(`CONTINUATION_experience_gam` COMPLETE) was the last unstarted Tier-A "big
rock," and the perf-harness epic closed **this morning** (PR #179 merged
2026-08-02T10:45Z; my branch == `origin/main` at `eb3eef9`). Per
`COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7 and `PRODUCT_DIRECTION_2026-07-24`
("Decision Surfaced"), with no Phase-7 frontier chosen and the AXIS/Prophet
reconciliation reference-blocked, **there is no startable Tier-A epic** and the
routine correctly falls to gated Tier-B/C fallback in **maintenance mode**.

**Review is NOT stale (correcting the prior log).** The prior session log
(2026-08-01) stated `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is ">30 days old as
of 2026-08-01" and that a regen was due. That is an **arithmetic error** — 2026-07-15
to 2026-08-02 is **18 days**, well inside the ~30-day trigger. So no viability-review
regeneration was performed; the 18-day-old review remains authoritative, and it
already prescribes the exact post-A4′ autonomous default (§7): harvest the
Tier-B/C fallback queue while flagging maintenance mode.

**Why #10 over the other fallback candidates.** Among the surviving open items in
`PRODUCT_DIRECTION_2026-07-24`, IMPORTANT #10 is the strongest maintenance-mode
pick: it is **self-contained** (builds only on the just-shipped, now-on-main perf
harness), **clearly scoped** (`PLAN_perf_harness.md` §3 Slice 4), **testable** by
pytest, **byte-identical** on goldens (a sibling diagnostic, never touches the
pricing path), and was explicitly teed up by the prior session as "the top
candidate to constitute as a follow-on" now that #9 closed. Other IMPORTANT items
were rejected: #2 (WL NET_PREMIUM terminal-reserve) moves goldens → needs a human
rebaseline authorization; #4 is Tier-D interest-exactness parked as NICE-TO-HAVE;
#6/#7 (shared multi-replica rate-limit / metrics backend) need an external
backend (Redis) and are larger; #11 needs a maintainer confirmation, not code.

**Why complete-in-one-session, no CONTINUATION.** By line count (~570 new LOC
across 3 new code files) this sits at the SMALL/MEDIUM boundary, but the shipped
unit is *cohesive and independently mergeable* — the full record + creep-detection
capability — not a partial feature. The natural next pieces are genuinely separate
and one needs human authorization: (a) an automatic per-merge CI job that commits
a row back to `main` needs `contents: write` and a bot-commit-to-`main` decision
(infra/authorization, not autonomous); (b) the one-off historical backfill is the
pre-existing NICE-TO-HAVE #63. Opening an IN PROGRESS CONTINUATION whose "slice 2"
cannot advance autonomously would create exactly the kind of stuck-open
CONTINUATION the routine already carries in `reserve_basis_correctness`. So I ship
the capability complete and **harvest** the two follow-ups (below), mirroring the
B2 precedent (ADR-161 shipped the scale-benchmark harness+script as one complete
unit; its CI gate was a separate follow-up).

## Verify Premise (step 7b)
Confirmed by inspection that the feature is genuinely absent: no `perf/` dir, no
`perf/history.jsonl`, and no creep-detection code anywhere (`grep -rl
history.jsonl` hit only docs). The documented gap holds: the ADR-176 perf CI job
is **PR-only, head-vs-`origin/main`** — its baseline is always the moving `main`
tip, so it structurally cannot see cumulative multi-month drift (each PR moves
little; `main` moves with it). That blind spot is precisely #10's rationale.

## What Was Done
Added `analytics/perf_history.py` — a sibling diagnostic to `analytics/perf_harness.py`,
off the pricing/import hot path — with `PerfHistoryRow` (a compact,
deterministic-first projection of a `PerfReport` + the commit it was recorded
for), `append_history_row` / `load_history` (exact JSONL round-trip; missing file
= empty series; blank lines skipped), and `detect_creep` → `CreepVerdict`. Creep
detection groups the series by probe and compares the **median** `peak_mib` (and
median best-of-k wall-time) of the earliest `window` rows against the latest
`window` rows; a probe needs `2*window` rows or it is omitted (young log →
`insufficient_data`, no false alarm). Honouring the maintainer rule (2026-07-12) —
and more so across a series recorded on *different* CI machines — **only the
machine-portable MiB-peak gates** (`has_structural_creep`, when the median rise
exceeds `mib_creep_delta`); the wall-time recent/baseline ratio (`band`) and any
input `config_drift` are advisory-only and never change the exit status.

Added the runner `scripts/perf_history.py`: it records HEAD's probe on the
committed `tests/fixtures/synthetic_select_ultimate.csv` (the same fixture
`perfbench.py` uses, so both harnesses measure the same hot path), takes the
commit date from the commit itself (`git show -s --format=%cI` — never
`date.today()`, ADR-074), appends a row, then re-analyses the whole series and
exits non-zero iff structural creep. It is **idempotent**: re-running on an
already-recorded commit skips the append (per-commit, append-once) so a CI re-run
cannot double-count a commit in a window. Seeded `perf/history.jsonl` with one row
for the current `main` tip at the default probe config (`n_policies=3000`, `k=5`)
so future default per-merge runs are apples-to-apples with the baseline. ADR-177
records the design.

## Files Changed
- `src/polaris_re/analytics/perf_history.py` — **new** module (row model, append/
  load, `detect_creep`).
- `scripts/perf_history.py` — **new** runner (record HEAD + creep check;
  idempotent; offline-safe).
- `perf/history.jsonl` — **new** committed append-only log, seeded with the current
  `main`-tip row.
- `src/polaris_re/analytics/__init__.py` — export the 7 new public names.
- `tests/perf/test_perf_history.py` — **new** (21 tests; see below).
- `.gitignore` — ignore the transient `perf_history.json` verdict output (like
  `perf.json`); note that `perf/history.jsonl` is intentionally NOT ignored.
- `docs/DECISIONS.md` — ADR-177.
- `README.md`, `docs/QUICKSTART.md` — "long-baseline creep log" note.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — PD #10 struck through SHIPPED; harvest
  subsection (2026-08-02).

## Tests Added
- `tests/perf/test_perf_history.py` (21): 20 fast closed-form tests (no engine) —
  append creates file+parent; append/load round-trip in order; missing file =
  empty; blank lines skipped; `from_report` projects the deterministic-first
  fields; `insufficient_data` below `2*window`; flat series = no creep; a
  sustained MiB rise gates (median 67→80, Δ13 > 4); a 3-MiB rise does not; a
  doubled wall-time alerts but never gates; a zero-baseline wall-time → `None`
  ratio, no alert; config drift flagged advisory; median ignores a single
  200-MiB outlier; multi-probe with one creeping probe gates only that probe;
  `to_verdict_dict` leads with the verdict block; input validation
  (window/mib_creep_delta/band). Plus 1 slow (`perf`+`slow`) end-to-end that runs
  the real probe → record → load → analyse and asserts the fingerprint round-trips
  and a single row stays `insufficient_data` (no false creep).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Append-only per-merge `perf/history.jsonl` with one deterministic-first row per commit | ✅ | `append_history_row` + seeded committed log; `PerfHistoryRow` is deterministic-first |
| Creep detection over the series | ✅ | `detect_creep` — earliest-window vs recent-window median |
| Deterministic (MiB-peak) creep gates; wall-time only informs | ✅ | `has_structural_creep` = MiB only; wall-time/config-drift advisory (structurally enforced) |
| Dates pinned to the commit, never the wall clock (ADR-074) | ✅ | `git show -s --format=%cI`; every test fixture pins commit dates |
| Runner records HEAD + checks the series, exits non-zero on structural creep | ✅ | `scripts/perf_history.py`; idempotent per-commit |
| Goldens byte-identical | ✅ | additive-only; `polaris price` flat: cedant $3,513,563 / reinsurer $45,386; `tests/qa/` green |
| Quality gate (ruff format+check `src/ tests/`, fast suite, qa) | ✅ | ruff clean on `src/ tests/`; suites green (see Baseline) |

## Open Questions / Follow-ups
- **Automatic per-merge CI append (harvested IMPORTANT).** The capability ships,
  but nothing yet *runs* it per-merge and commits the row back to `main`. That
  needs a CI job with `contents: write` committing to `main` — an
  infra/authorization decision for the maintainer (a bot writing to `main`), so
  it is deliberately NOT done autonomously. Harvested to PRODUCT_DIRECTION as
  IMPORTANT with that caveat.
- **Backfill (NICE-TO-HAVE #63) is unblocked.** The existing "seed
  `perf/history.jsonl` by backfilling ~10–15 engine-touching merges on one
  machine" now has its target format and mechanism; creep detection is a no-op
  (`insufficient_data`) until the log has `2*window` rows.
- **pr-review perf-verdict comment (#62)** could fold in the creep verdict too;
  noted, overlaps the existing NICE-TO-HAVE.
- **Phase-7 frontier still unchosen.** The routine remains in **maintenance mode,
  not growth mode** (per `PRODUCT_DIRECTION_2026-07-24` "Decision Surfaced"). No
  Tier-A epic is startable until the maintainer charts a frontier.

## Parked Polish
- None reaching 3rd-order. ADR-177's out-of-scope items are all 1st-order
  follow-ups of this planned feature (CI auto-append) or pre-existing tracked
  items (#63 backfill, #62 pr-review comment), promoted normally below.

## Impact on Golden Baselines
None. Additive-only — a new analytics module, a new script, and a new committed
data file; no `src/` pricing code changed. `polaris price` on
`golden_config_flat.json` is byte-identical (cedant PV $3,513,563, reinsurer PV
$45,386); `tests/qa/` green.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2784 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; the 3
skips are the standing absent-CIA-2014-tables skips). Matches the prior log's
end-state exactly. No NEW or CHANGED failure → the session PROCEEDED. This slice
adds 20 fast tests (+1 slow), so the fast suite is expected at **2804 passed, 3
skipped**.
