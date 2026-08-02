# Dev Session Log — 2026-08-01

## Item Selected
- **Source:** `docs/CONTINUATION_perf_harness.md` — the in-progress perf epic
  (IMPORTANT #9 in `PRODUCT_DIRECTION_2026-07-24`), **Slice 3** (CLOSES the epic's
  mandatory scope).
- **Priority:** IMPORTANT (active in-flight epic; advanced before any fallback pick).
- **Title:** CI `perf` job — gate the merge on a head-vs-main structural regression.
- **Slice:** 3 of 3 mandatory (+1 optional Slice 4 = IMPORTANT #10).
- **Branch:** `claude/loving-gauss-7h7smy` (environment-designated).

## Selection Rationale
Step 5 found the perf epic as the single advanceable in-progress CONTINUATION.
Slice 2 (PR #178) — recorded as a draft in the prior session log — **merged to
main** at 2026-08-01T19:11Z (commit `750a6a7`), which is exactly what Slice 3
depended on. Per the ACTIVE-EPIC guardrail (advance the epic's next slice before
any fallback), Slice 3 is this session's deliverable. No Tier-B/C/D fallback was
picked. My branch was already at `origin/main` HEAD (`750a6a7`), so Slice 3
builds on a clean base with Slices 1+2 present.

**Ledger healing (step 4b).** `git fetch` confirmed the local `main`/`origin/main`
tracking ref was stale at `0342584` (#174) while my branch already carried
`750a6a7` (the #178 merge). No open PRs remain (`list_pull_requests state=open`
→ `[]`), so the ledger was otherwise healthy; I healed the two docs that still
described #178 as a draft — `CONTINUATION_perf_harness` (Slice 2 PR #178 draft →
**MERGED** `750a6a7`) and `PRODUCT_DIRECTION_2026-07-24` PD #9 (struck through as
SHIPPED now that Slice 3 closes it).

**Premise verification (step 7b).** Reproduced the gap before writing code:
`.github/workflows/ci.yml` had jobs `lint / test / docker / smoke / coverage` and
**no `perf` job** — the Slice-2 runner (`scripts/perfbench.py`) existed but nothing
ran it in CI. Then I ran the runner locally against `origin/main`
(`perfbench.py --ref origin/main`): it worked end-to-end (identical fingerprints,
wall-time ratio ~1.05×, `peak_mib` Δ 0, **no hard delta, exit 0**) and again with
`--no-fetch` after an explicit baseline fetch (the exact CI invocation) — exit 0.
The premise holds: the gate is genuinely unbuilt, and the runner it consumes is
green head-vs-main on an engine-unchanged branch.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Deterministic perf-probe core | ✅ Done | #171 (merged) |
| 2 | Head-vs-main driver + `perf.json` diff | ✅ Done | #178 (merged `750a6a7`) |
| 3 | CI perf job (closes IMPORTANT #9) | ✅ Done | #179 |
| 4 | `perf/history.jsonl` creep log (opt / #10) | 🔲 Planned (own epic) | — |

## What Was Done
Added a `perf` job to `.github/workflows/ci.yml`, mirroring the `smoke` job's
shape (`needs: lint`, one `ubuntu-latest` runner, no build matrix). The job is
**PR-only** (`if: github.event_name == 'pull_request'`) — on a push to `main`,
head and `origin/main` are the same commit, so a comparison is a no-op with a
fetch-race edge; gating to PR events removes both. It checks out with
`fetch-depth: 0` (full history for the git-worktree checkout), **explicitly
materializes the baseline** with `git fetch --no-tags origin
+refs/heads/main:refs/remotes/origin/main` so `refs/remotes/origin/main` resolves
regardless of the checkout action's default refspec, then runs `uv run python
scripts/perfbench.py --ref origin/main --no-fetch -o perf.json`. The job's
**non-zero exit gates the merge** — but only on a *structural hard delta*
(mismatched counts / output fingerprint); the wall-time ratio and peak-MiB delta
are advisory alerts printed to the step log that never fail the build (the
maintainer's non-negotiable rule, 2026-07-12: deterministic metrics gate, raw
wall-time only informs). `perf.json` is uploaded as an artifact (`if: always()`,
7-day retention) so a failing gate's evidence is inspectable. No
`convert_soa_tables` step — the probe uses the committed
`tests/fixtures/synthetic_select_ultimate.csv`, so the job is fast and
offline-safe (and no Dockerfile/`.dockerignore` change is needed, since no
test-referenced data file is added).

The two advisory thresholds the runner exposes — wall-time `band=1.5×` and
`mib_alert_delta=4 MiB` — were **confirmed by the maintainer (2026-07-31,
PR #178)** and are wired in as `perfbench.py`'s defaults (alert only, never a hard
gate). ADR-176 records the design. This closes the perf epic's mandatory scope
(Slices 1–3); `CONTINUATION_perf_harness` → COMPLETE. The optional Slice 4
(`perf/history.jsonl` creep log) is the standing IMPORTANT #10, now UNBLOCKED.

## Files Changed
- `.github/workflows/ci.yml` — new `perf` job (Job 5; former Job 5 coverage → Job 6).
- `tests/test_ci/__init__.py`, `tests/test_ci/test_workflow_perf_job.py` — new
  structural tests pinning the job wiring.
- `docs/DECISIONS.md` — ADR-176.
- `docs/PLAN_perf_harness.md` — status → COMPLETE (mandatory); Slice 3 SHIPPED;
  epic acceptance criteria all ✅.
- `docs/CONTINUATION_perf_harness.md` — Slice 2 healed to MERGED (#178); Slice 3
  DONE; Status IN PROGRESS → COMPLETE.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — PD #9 struck through as SHIPPED; PD #10
  annotated UNBLOCKED; harvest subsection (2026-08-01 Slice 3).
- `README.md`, `docs/QUICKSTART.md` — perf-gate note (how to read `perf.json` /
  reproduce locally).

## Tests Added
- `tests/test_ci/test_workflow_perf_job.py` (new, +10, fast — parses the workflow
  YAML, no engine): the `perf` job exists; `needs: lint`; single `ubuntu-latest`
  runner with no matrix; PR-only `if`; `fetch-depth: 0`; materializes
  `refs/remotes/origin/main`; runs `scripts/perfbench.py --ref origin/main
  -o perf.json`; **no** `convert_soa_tables` step; uploads `perf.json`
  (`if: always()`). Mirrors `tests/test_deploy/test_manifests.py`'s structural-lint
  style. The harness itself is exercised by `tests/perf/` and by running the
  script (per the PLAN — unit tests stay synthetic / gitless).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| CI job runs the Slice-2 head-vs-main harness on one runner | ✅ | `perf` job, `perfbench.py --ref origin/main --no-fetch` |
| Gates on structural deltas (non-zero exit = hard delta) | ✅ | job fails iff `perfbench.py` exits non-zero; structural-only |
| Wall-time / peak-MiB alerts non-blocking | ✅ | printed to the log; never change the exit status (structurally enforced by `diff_reports`) |
| `perf.json` uploaded as an artifact | ✅ | `actions/upload-artifact`, `if: always()`, 7-day retention |
| README/QUICKSTART note on reading `perf.json` | ✅ | both updated |
| Job wiring pinned by tests | ✅ | `tests/test_ci/test_workflow_perf_job.py` (10) |
| Goldens byte-identical | ✅ | `polaris price` flat: cedant $3,513,563.42 / reinsurer $45,386.44; `tests/qa/` 94 passed |
| Quality gate (ruff format+check `src/ tests/`, fast suite, qa) | ✅ | ruff clean; fast suite green; qa 104 (10 test_ci + 94 qa) |

## Post-Open CI Fix (2026-08-01, commit `ea684d5`)
The first CI run on PR #179 failed the **Docker build & test** job: the runtime
image runs the full test suite, and the new `tests/test_ci/` parses
`.github/workflows/ci.yml`, which the image did **not** contain (`.dockerignore`
excluded `.github/` and the Dockerfile never COPYed it) → `FileNotFoundError`.
This is exactly the Docker/data trap the routine encodes (#61/#66). Fixed in the
same PR: `Dockerfile` now `COPY .github/workflows/ ./.github/workflows/` (mirroring
the `deploy/` precedent), and `.dockerignore` allowlists `!.github/workflows/` +
`!.github/workflows/**` (mirroring the `data/qa/` pattern), shipping only the
workflows dir. Local fast suite + `tests/test_ci/` unaffected (they already read
the repo copy); the fix is Docker-context-only. Lesson re-confirmed: any test that
reads a repo file the image doesn't ship must be paired with a Dockerfile COPY +
`.dockerignore` allowlist in the same PR.

## Open Questions / Follow-ups
- **IMPORTANT #10 (`perf/history.jsonl` creep log) is now UNBLOCKED** and is the
  natural continuation of this epic's thread — the runner already emits the
  deterministic-first row shape it would append. It is the top candidate to
  constitute as a follow-on epic next session (the perf epic's optional Slice 4).
- **No active Tier-A epic remains.** With IMPORTANT #9 closed and
  `CONTINUATION_perf_harness` COMPLETE, the next run selects a new Epic per
  step 5b. `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is **>30 days old** as of
  2026-08-01, so the routine's step-6 rule requires **regenerating the viability
  review before the next Epic is chosen** (regen may itself be a session's
  deliverable). Flagged for the next run.
- **`scripts/` is not in the CI lint scope** — see "Parked Polish" below (parked,
  not promoted).

## Parked Polish
- **Bring `scripts/` under the CI lint scope.** `ruff check scripts/` reports 12
  **pre-existing** warnings in `scripts/` (incl. `perfbench.py` from #178);
  CLAUDE.md's quality gate and the CI `lint` job both deliberately scope to
  `src/ tests/`, so `scripts/` is unlinted by design and these are untouched by
  PR #179. Classified **ambient / not a descendant of the perf feature** (it is an
  incidental observation about repo-wide lint policy, not a follow-up of the
  planned work) → treated as **3rd-order-or-deeper for auto-promotion purposes:
  NOT promoted to PRODUCT_DIRECTION.** Widening the lint scope is a repo-policy
  decision (would surface inherited noise CLAUDE.md chose to exclude); revival is
  an explicit human decision, not the routine's. *(Recorded per PR #179 review
  [P2] — order-tag the observation rather than promote it.)*

ADR-176's out-of-scope items are all already-tracked epic work (IMPORTANT
#10, the pr-review perf-comment NICE-TO-HAVE, the `polaris perfbench` CLI
NICE-TO-HAVE harvested in Slice 2) — nothing reached 3rd-order.

## Impact on Golden Baselines
None. CI-only + tests + docs; no `src/` pricing code changed. `polaris price` on
`golden_config_flat.json` is byte-identical (cedant PV $3,513,563.42, reinsurer
PV $45,386.44); `tests/qa/` 94 passed. The engine is identical head-vs-`origin/main`
on this branch, so the new gate itself is green (exit 0), verified locally.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2774 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; SOA VBT /
CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline). This matches the prior log's end-state (Slice 2 added 16 tests, now on
main). No NEW or CHANGED failure, so the session PROCEEDED. This slice adds 10
fast structural tests (`tests/test_ci/`).
