# Dev Session Log — 2026-08-11

## Item Selected

- **Source:** maintainer direction in conversation (2026-08-10/11) — **not** a routine run
- **Priority:** ACTIVE EPIC start + PR #194 review response
- **Title:** The `mgcv`-parity engine epic — PLAN, routine instructions, oracle digest
- **Slice:** epic-start (PLAN + CONTINUATION); slice 1 is NEXT and not started
- **Branch:** `claude/mgcv-parity-engine` — **PR #194**

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `95c3f46`) | **3175 passed, 3 skipped, 126 deselected** — no standing failures |
| End state | **identical** — this PR changes no `src/`, `tests/` or `data/` |
| `tests/qa/` goldens | untouched, not regenerated |
| perf row | **none** — docs-only, and ADR-177 amendment 1 now says so in writing |

**The baseline moved by one test for a reason worth knowing.** Earlier logs in this
session recorded *3174 passed, 4 skipped*. The difference is
`test_the_r_script_runs_end_to_end_and_agrees`, which is gated on
`rscript_mgcv_available()`: it **skipped** when this container had no R, and **passes** now
that R is installed. Same code, same commit — a different environment.

That matters for the new routine specifically, because its step 2 installs R. **A parity
routine run will always see one more pass and one fewer skip than a run without R**, and a
tolerance-aware baseline check that does not know this would read a real environment
difference as a change in the code. A note has been added to
`ROUTINE_MGCV_PARITY.md` step 4 so the next run is not surprised by its own setup step.

The four SOA-conversion failures the routine's baseline note anticipates did **not** occur.

## What Was Done

Two documents defining the successor epic, plus the oracle digest bump — and then the
PR #194 review response, which is the larger half of the diff.

**The epic.** `PLAN_mgcv_parity_engine.md`: 7 slices, 9 anchors, 4 predictions registered
in advance. The two anchors that change what gets built rather than how it is checked are
**Anchor 1** (two-stage conformance — verify construction before fit, because a basis
defect and a fitter defect are different defects and one end-to-end comparison cannot
separate them) and **Anchor 2** (the fitted surface is the acceptance criterion and
coefficients are not, because `mgcv` reparameterises).

**The routine.** `ROUTINE_MGCV_PARITY.md`: a convergence loop rather than a backlog walk.
It measures the gap before changing anything, changes exactly one thing per pass, and
appends every attempt — including the failures — to a conformance ledger. Its feasibility
rests on measurements taken before it was written: R installs in ~3.5 min, the ten-cell
suite runs in 2.2 s, `bam(discrete=TRUE)` at 125k rows in 1.69 s.

**The digest.** `sha256:8853bf2b…`, adding `mboost` with R / `mgcv` / the CRAN snapshot
held fixed. CI's conformance workflow ran against it and passed, which — because the gate
blocks on levels 1-3 — is functional proof the rebuild did not perturb `mgcv`'s numerics.

## PR #194 review — five findings, all five actioned

An approving review, zero P0s. Two of the three [P1]s compounded into a real hazard.

**[P1-1] + [P1-2] together were the serious one, and the reviewer was right to link them.**
I added a READ-FIRST banner to the old CONTINUATION but left the slice statuses below it
saying "Slice 6 — **NEXT**" in two places, and I shipped the new epic's PLAN with no
CONTINUATION. The slice-status convention is the machine-readable part a routine keys on;
a banner is prose above it. So the only `IN PROGRESS` CONTINUATION in the repo was the
**superseded** epic's, pointing at a **parked** slice as the next work — precisely the
outcome the banners were added to prevent.

**This is the claim-set defect this project has now caught in its own work five times**
(ADR-186 amendment 2 named it; I quoted it at the maintainer twice this week). I updated
the prose and did not sweep the statuses underneath. Fixed: every slice status in the old
CONTINUATION is now PARKED with a pointer, and the new epic has a CONTINUATION with status
IN PROGRESS and slice 1 as NEXT.

**[P1-3]** — no session log, so no stated baseline. This file, and the baseline above.

**[P2-1] was the finding I would least have wanted to ship.** The routine's quality gate
told an autonomous session to run `polaris price -o /tmp/dev_check.json` and then asserted
"`tests/qa/` goldens must be BYTE-IDENTICAL" without saying what the dump is compared
against. **They are different schemas** — the dump is the full nested result, the goldens
are `golden_runner`'s distilled digest — and diffing them always differs. That exact
confusion produced a false four-config regression report on PR #180. The daily-dev routine
carries an explicit warning about it at step 13; I wrote a new routine and dropped the
warning. A defect in an instruction document that will be followed without a human reading
it is worse than the same defect in code. Fixed, with the authoritative gate named, all
five configs mentioned, and the trap spelled out.

**[P2-2]** — no perf row on an initial-open PR. The reviewer agreed the reasoning was sound
and correctly noted the *codified rule* did not carry the exemption, so the next reviewer
would read a decision as an omission. **ADR-177 amendment 1** now states it: a PR that
modifies nothing under `src/polaris_re/` appends no row, because a row that cannot have
moved the engine is not merely useless — the analyser medians over a window, so padding the
series dilutes it and makes a real step harder to see.

## Files Changed

| file | what |
|---|---|
| `docs/PLAN_mgcv_parity_engine.md` | **new** — the epic |
| `docs/ROUTINE_MGCV_PARITY.md` | **new** — the routine; [P2-1] golden guidance corrected |
| `docs/CONTINUATION_mgcv_parity_engine.md` | **new** — [P1-2] |
| `.github/workflows/mgcv-conformance.yml` | oracle digest + the moved-tag finding |
| `docs/PLAN_penalized_mi_surface.md` | SUPERSEDED banner |
| `docs/CONTINUATION_penalized_mi_surface.md` | banner + [P1-1] slice statuses → PARKED |
| `docs/DECISIONS.md` | ADR-177 amendment 1 — [P2-2] |
| `docs/PRODUCT_DIRECTION_2026-07-24.md` | the epic registered in the ledger + 3 items |
| `docs/DEV_SESSION_LOG_2026-08-11_mgcv_parity_epic.md` | this file — [P1-3] |

## Tests Added

None. No `src/` or `tests/` changes — this is a planning and record PR.

## Acceptance Criteria

| Criterion | Status | Notes |
|---|---|---|
| A PLAN exists with anchors, slices and registered predictions | ✅ | 7 slices, 9 anchors, 4 predictions |
| A CONTINUATION exists at IN PROGRESS with a NEXT slice | ✅ | added in review response |
| The routine is written and its feasibility measured, not assumed | ✅ | 3.5 min / 2.2 s / 1.69 s |
| A selecting routine cannot resolve a superseded slice as next work | ✅ | every old slice status is PARKED |
| The oracle digest is bumped and verified | ✅ | CI conformance green on the new digest |
| The epic is visible in the ledger | ✅ | added in review response |
| **The routine is scheduled** | ❌ | cron lives outside the repo — maintainer's |

## Open Questions / Follow-ups

1. **Scheduling `ROUTINE_MGCV_PARITY.md`** — until it is registered, nothing advances the
   epic. Raised in the ledger as a BLOCKER on the epic itself, and it is the cheapest item
   on the list.
2. ~~**Retire or re-cut `r4.6.1-2026-08-01`**~~ — **CLOSED** (R-Gam-base PR #3, 2026-08-11).
   Immutable never-reused tags, a digest-keyed `BUILDS.md`, and a CI refusal to push an
   existing tag. The tag is **deprecated, not deleted**: GHCR deletes package versions, not
   tags, and that tag sits on the digest this repo pins — deleting it would have destroyed
   our oracle. The right refusal. **What it cost us to close: nothing, and it bought a
   provenance correction** — build 1 (`a77a61cf…`) produced ADR-189 amendment 1's numbers,
   build 2 (`8853bf2b…`) is the current pin, and that distinction was nowhere in our record.
3. **Confirm the slice 6-7 parking**, and the old CONTINUATION's refinement-backlog harvest,
   which is still owed before its status may change.
4. **The duration treatment on real data** — reserved as a maintainer modelling judgement;
   the engine will support both and the routine is forbidden from deciding it.
5. **`smoothCon()` vs `lpmatrix` as Stage A's referent** — the epic's one unresolved
   design risk, named as a slice-1 deliverable with a weaker fallback recorded.

## Parked Polish

**None.** Every follow-up is first-order — a consequence of the epic being started or of
the PR #194 review.

## Impact on Golden Baselines

**None.** No `src/`, `tests/` or `data/` changes; `tests/qa/` untouched and not regenerated.
