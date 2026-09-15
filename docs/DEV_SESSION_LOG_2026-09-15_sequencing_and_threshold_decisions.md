# Dev session log — 2026-09-15: two maintainer decisions recorded, and a P0 of my own making

**Branch:** `claude/brave-keller-6tygau`, restarted from `origin/main` at
`7f2cfd4` — the branch's previous PR (#233) is MERGED, so per the repo rule
follow-up work restarts from the default branch rather than stacking.

**Base:** `7f2cfd4` (PR #233, blocker E closed by measurement, ADR-226).

**Gate reason:** maintainer direction, 2026-09-14 — two decisions taken in
response to #233's findings ("slice 1 first and record the thresholds as
pending measurement"), plus the instruction to get them into the project so
the daily-dev routine reads them as settled. A directed pick, not a fallback
one.

**Decomposition:** one slice, docs only — record the decisions where they are
consumed (both PLANs, the CONTINUATION, the proposal, the ledger). No code
change, no new ADR (see "On not writing an ADR" below).

## Test baseline

`uv run pytest tests/ -m "not slow"` on this branch: **see "Baseline result"
at the end.** R **is** installed in this container, so the R-gated conformance
tests run here rather than skipping.

For whoever diffs against it: PR #233 recorded `3646 passed, 3 skipped, 126
deselected, 0 failed` in a container WITH R; #234's reviewer recorded `3632
passed, 17 skipped, 126 deselected, 0 failed` in a container WITHOUT R. The
collected total is identical (3649) and the 14-test difference is exactly the
mgcv-dispatch set moving between passed and skipped. Expect this run to match
#233's shape, not the reviewer's.

## What this session recorded

**Decision 1 — sequencing.** The parity epic yields the one-active-epic slot
to `PLAN_gam_production_wiring.md` slice 1. Blocker E's closure left wiring
slice 3 gated on Anchor W6 alone, and slice 1 is the measurement W6 consumes.
Two reasons recorded so it is not re-litigated (slice 1 can *retire* a gate;
it is the cheaper information because it tests blocker A), plus the
counter-argument — ADR-226 decision 2 means slice 8 has a real quantified
target — recorded rather than buried.

**Decision 2 — convergence thresholds: PENDING MEASUREMENT.** Recorded with
provisional values and explicitly not ratified, because `ε_f` turned out to be
necessary but not sufficient: the second input (the plateau the RESTRICTED
gradient reaches under the POST-7h criterion) has never been measured.

## The P0 in my own recommendation, and what it teaches

**PR #234's review found a [P0] in decision 2, and it was correct.** I had
written, in four places and in conversation with the maintainer, that the
curvature-to-noise ratio should be calibrated to reproduce *"slice 7c's
committed `5 identified directions of 7`"*.

**That number was RETRACTED by ADR-219 amendment 2**, which says in terms: *"it
counted the sign of a quantity this ADR's own step-stability scan had already
shown to be noise."* The eigenvalue-sign count reads `5 / 7 / 6 / 5` across
four readings of one fixture. ADR-219 amendment 3 even wrote a warning box for
exactly this misreading, because the *surviving* step-stability verdict happens
to land on the same digits.

Three things make this worse than a citation slip, and all three are the
reviewer's points, verified at source before accepting them:

1. **It was operative.** It landed as a `[judgement]` DoD criterion on slice 8
   and an **IMPORTANT** ledger entry — a future session would have executed it.
2. **The machinery was hardened against precisely this.**
   `gam_sp_identifiability.identified_direction_count` makes `floor` a
   **required** argument so a sign count cannot be obtained by accident
   (`gam_sp_identifiability.py:238-246`). My instruction asked a session to
   choose `floor` so the accidental quantity came out at 5 — defeating the
   guard deliberately.
3. **The justification was inverted.** I wrote that this "anchors the ratio on
   a measurement rather than on taste, which is this document's whole premise
   applied to itself" — while anchoring on the one number in this epic that had
   been formally withdrawn.

**Fixed by re-anchoring on the reading that survived** — the step-stability
verdict, "2 of 7 directions carry no resolvable curvature", which held
identically across all four readings — with the digit coincidence named
explicitly at every site so the next reader cannot repeat the error. The target
value does not move; its epistemic status does.

**The lesson, recorded because it generalises:** I reached for a number that
was *memorable* and *convenient* rather than checking its status. This project
retracts numbers, and a retracted number reads exactly like a live one in a
grep. `PATTERN_resolvable_tolerances.md` argues thresholds should be anchored
on measurements — this session shows that "a measurement" is not sufficient;
it has to be a measurement that is still standing.

## Other findings addressed

- **[P1-2]** `PLAN_gam_production_wiring.md` said two different things about
  blocker E: the new status line said CLOSED while slice 3's body still called
  7h "a hard dependency" and asserted multistart "fails the cross-thread axis"
  — factually wrong post-ADR-226. Swept all four sites, using
  strikethrough-with-correction rather than deletion so the original reading
  stays visible. Pre-existing (#233 updated the banner without sweeping the
  bodies), fixed here because this PR edits the file to settle sequencing.
- **[P2-1]** Restored "**three**" independent instances rather than silently
  dropping the count.
- **[P2-2]** The CONTINUATION's Status header now names the yield, rather than
  leaving it only in an appended banner 1800 lines down.
- Also fixed, not flagged by the reviewer: the same retracted-number citation
  in `CONTINUATION_mgcv_parity_engine.md:1517`, which was mine from PR #227.

## On not writing an ADR ([P2-3])

Considered and declined. These are maintainer decisions recorded where they are
consumed, not architecture choices this session made — ADR-226 already carries
the *findings* that prompted them, and its consequences 1-2 state the
sequencing implication. A new ADR would restate that. Recorded here so the
absence is legible rather than looking like an omission; if the maintainer
prefers an ADR, it is a small follow-up.

## Perf history

No row. Zero engine code, same measured grounds as #227 and #233 (a docs-only
row moved the series' creep ratio `1.258x → 1.339x`). The policy question is
registered in `PRODUCT_DIRECTION` for the maintainer rather than taken here;
#234's review accepted the decline explicitly and did not count it a finding.

## Verification provenance (ADR-193)

This session publishes **no comparison**. Every figure is quoted from committed
ADR-219, ADR-221, ADR-223 or ADR-226 rows. The corrected calibration anchor is
a `MEASUREMENT (own criterion)` reading; nothing here is parity evidence.

## Baseline result

`uv run pytest tests/ -m "not slow"`:
**3646 passed, 3 skipped, 126 deselected, 5 warnings, 0 failed (647.59s).**

The expectation recorded before the run held exactly: identical to #233's
`3646 / 3 / 126 / 0`, this container having R. No Python changed and no
failures.

**Reconciliation for whoever diffs against this**, since three different
figures now exist for the same suite and they are all consistent:

| run | passed | skipped | R present? |
|---|---|---|---|
| #233's baseline, and this one | 3646 | 3 | yes |
| #234's reviewer | 3632 | 17 | no |

Collected total is `3649` in every case, and the 14-test difference is exactly
the mgcv-dispatch set moving between passed and skipped. Deselected is `126`
throughout.
