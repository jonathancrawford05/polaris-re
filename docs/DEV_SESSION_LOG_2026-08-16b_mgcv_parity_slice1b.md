# Dev Session Log — 2026-08-16b

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`
- **Slice:** 1b (mgcv-native per-term extraction) — **finished this session**, per
  `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md` §§1-5 and 8-9
- **Branch:** `claude/sharp-galileo-vn9bnf`

## Setup

- The designated branch already carried 27 unmerged commits (PR #195-#197's work,
  merged into this branch rather than into `main`, no PR yet opened for it). A first
  pass of this session mistakenly reset the branch to `origin/main`, discarding that
  history; caught immediately via `git reflog` before anything was pushed, and the
  branch was restored to its actual tip (`b1279e3`, PR #197's merge). Recorded here
  because it is exactly the kind of destructive-action risk this project's own
  guardrails exist to catch, and it did not reach the remote.
- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite` via
  apt (`apt-get update` needed first — stale index). **R 4.3.3 / mgcv 1.9.1**,
  matching the routine's documented expectation exactly — no version drift to log.
  `export OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- `docker info` fails (no daemon) — tier 2 unavailable, as documented.

## Baseline and end state

| | |
|---|---|
| Baseline (this branch @ `b1279e3`, R present) | **3198 passed, 5 failed, 22 skipped, 126 deselected** — matches the prior parity session's own end state exactly (`DEV_SESSION_LOG_2026-08-15b…`), so no drift since. |
| The 5 failures | Same pre-existing `data/mortality_tables/*.csv`-absent root cause (2nd-order NICE-TO-HAVE, orthogonal to this epic, unaddressed here). |
| The 22 skips | Same gate, unrelated to R availability. |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical. |
| End state | 3198 + 9 new (`test_gam_stage_a.py`) = **3207 passed**, same 5 pre-existing failures, same 22 skips. |
| Perf row | one row appended (`src/polaris_re/analytics/gam_stage_a.py` touched, so ADR-177's docs-only exemption does not apply). **Creep verdict:** no structural creep — `peak_mib` 33 → 33 (delta 0). Wall-time recent/baseline ratio 1.321x is advisory-only cross-machine noise, not a gate signal. |

## Gap Before

Slice 1b (the work order's actual scope, §§1-5/8-9) was entirely unbuilt: no `smoothCon`
branch in `scripts/gam_term_extract.R`, no `extract_smooth_terms` in `gam_stage_a.py`,
`TermExtract.knots` always `None` and never compared, and the index-range design
question (work order §4) unsettled in writing.

**Stage A / Stage B, existing 10-cell suite** (unchanged, tier 3, oracle
`sha256:0d54c192…` build 8): level 1: AGREES, level 2: AGREES, level 3: AGREES, level 4:
DISAGREES (standing Kass-Steffey formula gap, ADR-190 — not this slice's concern), level
5: DISAGREES (`gamma`, unsettled). Re-confirmed at tier 1 before touching anything.

**Primary metric (the MI contrast on the pinned grid):** still not computable — slices
4-5 (the outer optimiser, the MI term) do not exist yet. Unchanged by this session.

## Gap After

- **The R-side `smoothCon` branch: built.** `scripts/gam_term_extract.R`'s
  `extract_smooth_one` — three isolated `bs="cr"` cases (default knots `k=8`/`k=13`,
  supplied knots `k=8`), same synthetic generation as `smoothcon_lpmatrix_probe.R`
  (seed 20120101). Its own internal consistency guard (four `stop()` checks: `X` vs
  `lpmatrix`, `S` vs `m$smooth[[1]]$S`, `rank` vs `m$smooth[[1]]$rank`, `xp` vs
  `m$smooth[[1]]$xp`) promotes the probe's one-off diagnostic assertion into a standing
  check that fails the script loudly if it ever stops holding.
- **The Python packaging: built.** `extract_smooth_terms` in `gam_stage_a.py` reads the
  R payload directly into `TermExtract` — there is no independent Python `cr`/`ti`/`sz`
  basis yet, so this is packaging, not re-verification (ADR-192's own framing).
  `compare_term_extract` now compares `knots`, handling both-absent (agrees trivially,
  the `raw` path's case), both-present-and-equal, and presence-mismatch.
- **Index-range design question settled: ADR-192.** A term's coefficient index range is
  assigned by whichever side assembles the term into a model, never read off a fit — the
  `raw` path already did this implicitly (`DesignExport.n_tensor`/`n_coef`); slice 1b
  makes it explicit for the isolated case (`[0, width)`, since the model an isolated
  Stage-A case assembles *is* that one term).
- **A real bug, caught by the harness proving itself on its first run.** jsonlite's
  `auto_unbox` silently collapsed the single-penalty `rank = sm$rank` (a length-1
  vector) to a bare JSON scalar; Python's `for v in r_term["rank"]` raised `TypeError:
  'int' object is not iterable`. The `raw` path never hit this because it always
  carries two penalties. Fixed with `rank = I(sm$rank)`. Exactly what Anchor 1's
  "prove the harness first" discipline is for.
- **Confirmed at both tiers.** Tier 1: all three cases exact — `0.0` diffs, rank diff
  `(0,)`, knots agree; dims/ranks match ADR-191's own measurements (`200×7` rank 6 for
  `k=8`, `400×12` rank 11 for `k=13`) exactly. Tier 3 (CI run 31946132947, ~58s round
  trip): the R step's `stop()`-gated internal guard passed (a genuine hard check), and
  the Python packaging step raised no exception on the tier-3 payload — but the
  per-metric diff table itself was **not** read: this environment's egress policy
  blocks the Actions artifact blob-storage host, and the job summary is not exposed
  through the workflow-run/job API this session used. `docs/CONFORMANCE_LEDGER.md`
  states that boundary explicitly rather than inferring the values.
- **Slice 1b acceptance criteria (work order §5): all met** — see the table below.
  `docs/PLAN_mgcv_parity_engine.md` and `docs/CONTINUATION_mgcv_parity_engine.md`
  updated to DONE; slice 2 (`bs = "cr"`) is genuinely unblocked and marked NEXT.

## Hypotheses Tried

1. **The R-side `smoothCon` branch and its Python counterpart agree term by term on
   three isolated `bs="cr"` cases (Anchor 1, same shape of proof as slice 1's `raw`
   path).**
   - **Tier 1** (R 4.3.3 / mgcv 1.9.1, local apt): wrote both sides; first run hit the
     `auto_unbox`/`rank` bug (a real `TypeError`, not a value disagreement); fixed with
     `rank = I(sm$rank)`; re-ran. **CONFIRMED at tier 1** — exact agreement, all 3 cases.
   - Per `ROUTINE_MGCV_PARITY.md` step 2, this is a structural claim about reading a
     specific `mgcv` version's fitted object correctly, so it needs tier 3. Dispatched
     the existing `mgcv-conformance.yml` workflow (already wired to run
     `gam_term_extract.R` and compare its output; this session extended the comparison
     step to also cover `smooth_designs`).
   - **Tier 3** (R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192…` build 8, CI run
     [31946132947](https://github.com/jonathancrawford05/polaris-re/actions/runs/31946132947),
     ~58s round trip): the R extraction step (which contains the actual `stop()`
     guards) and the Python comparison step both completed with `conclusion: success`.
     **CONFIRMED for the R-side guard — settled; weaker confirmation for the Python
     step**, which does not `sys.exit` on a value disagreement, only on an exception —
     recorded honestly in the ledger rather than overclaimed, per the routine's own
     tier discipline (ADR-190 decision 5, ADR-191's "settle it in writing").

No hypothesis stood refuted this session — the one genuine defect found (the
`auto_unbox` bug) was in this session's own new code, caught and fixed within the same
tier-1 iteration before any tier-3 dispatch, exactly as the iterate-locally-verify-on-
tier-3 loop is meant to work.

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1 (local apt, this container), `OPENBLAS_NUM_THREADS=1`.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, `jsonlite` 2.0.0, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run 31946132947 on commit `7f06ebd`.

## What Was Done

1. `scripts/gam_term_extract.R` — `extract_smooth_one`, the mgcv-native `smoothCon`
   branch, wired into `main()` alongside the existing raw-path extraction.
2. `src/polaris_re/analytics/gam_stage_a.py` — `extract_smooth_terms`, `knots` added to
   `RTermPayload` and `TermExtractComparison`, `compare_term_extract` extended.
3. `.github/workflows/mgcv-conformance.yml` — extended the existing per-term comparison
   step to also cover `smooth_designs`, same `continue-on-error` diagnostic contract.
4. `docs/DECISIONS.md` — **ADR-192**, the index-range design question settled in
   writing.
5. `docs/CONFORMANCE_LEDGER.md` — two new rows: the tier-1 hypothesis (including the
   caught-and-fixed bug) and its tier-3 confirmation, with the artifact-access
   limitation stated explicitly.
6. `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`,
   `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md` — slice 1b marked DONE, slice 2
   marked NEXT.
7. `docs/PRODUCT_DIRECTION_2026-07-24.md` — struck through the slice-1b BLOCKER as
   shipped; added this session's harvest entry.
8. `perf/history.jsonl` — one row for this PR's initial open (ADR-177).

## Tests Added

`tests/test_analytics/test_gam_stage_a.py` — 9 new tests: `extract_smooth_terms`
(builds a `TermExtract` from a fake R payload; refuses a `"raw"` term; refuses a label
with no matching R entry), `compare_term_extract` knots handling (agree when both
absent; agree when both present and equal; catches a perturbed knot; catches a
presence mismatch; refuses a shape mismatch), and the R-gated end-to-end proof
(`test_the_r_extractor_agrees_with_the_python_side_on_every_smooth_design`, skipped
wherever R is absent).

## Acceptance Criteria

| Criterion (from the work order §5) | Status | Notes |
|---|---|---|
| `gam_term_extract.R` emits the schema for default and supplied knots | ✅ | 3 cases |
| Extractor's internal guard passes | ✅ | 4 `stop()` checks, tier 1 and tier 3 |
| Python counterpart consumes it; `compare_term_extract` compares knots | ✅ | `extract_smooth_terms` |
| Index-range question decided in writing | ✅ | ADR-192 |
| Confirmed at tier 3 | ✅ (with a stated boundary) | R-side guard confirmed; Python step's exception-freedom confirmed; per-metric table not read (egress policy) |
| `docs/CONFORMANCE_LEDGER.md` carries both readings | ✅ | |
| Suite green; `tests/qa/` untouched; goldens byte-identical | ✅ | 85/9, unchanged |

**Slice 1b is complete.**

## Open Questions / Follow-ups

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md` under "Harvested 2026-08-16" (third
entry):

1. **Slice 2 — `bs = "cr"`, with supplied and default knots.** Now genuinely unblocked.
   1st-order — the epic's own NEXT slice.
2. **Any future R-side field that can be length-1 needs `I()` to survive
   `auto_unbox`.** `S`/`X` are already list-wrapped so only scalar-shaped fields are at
   risk — a documented gotcha for whoever writes the next R-side branch (`sz`'s rank,
   `ti`'s per-margin quantities). 2nd-order, NICE-TO-HAVE.
3. **The pre-existing `data/mortality_tables` environment gap** — unchanged from prior
   sessions, still unaddressed here. 2nd-order, NICE-TO-HAVE.

## Parked Polish

None.

## Impact on Golden Baselines

None. `tests/qa/` untouched, 85/9 pass/skip unchanged, byte-identical goldens. No
`products/`, `reinsurance/` or CLI code moved.
