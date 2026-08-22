# Dev Session Log — 2026-08-21 (ADR-198: grid-resolution hypothesis, then two confirmed decisions)

## Item Selected

- **Source:** live maintainer follow-up in this Claude Code session, on branch
  `claude/zealous-mendel-j0huik` (PR #204), after ADR-197's production fix landed. Quoting
  the maintainer's framing: the grid search is "a likely contributor to some of the values
  that have moved to within tolerances but are not at parity," plus a request to "document
  the findings and hypothesis so that future development and the plan align to what we now
  know," plus a direct question — "can you confirm that we will eventually come round to
  make our optimization aligned to MGCV to achieve parity."
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`, following directly
  from ADR-197's resolution (`c18bf26`/`ce0b9f1` per that ADR).
- **Scope:** docs only. No source or test changes in either commit below.
- **Branch:** `claude/zealous-mendel-j0huik` (PR #204, draft).

## What shipped

1. **`00ebd27`** — ADR-198 (`docs/DECISIONS.md`), naming the grid-resolution-vs-continuous-
   optimum hypothesis explicitly and quantitatively: every post-fix free-`sp` residual
   (0.0645 / 0.0791 / 0.1048 / 0.0776) sits under half the selector's own refinement step
   (0.125 = `REFINE_STEP / 2`), where before ADR-197's fix all four exceeded it. Framed as a
   hypothesis, not a result — registers two discriminating tests (re-run at
   `refine_step=0.05`; slice 4 part B's continuous optimiser) and states the refutation
   condition in advance (a residual that stalls near 0.1 kills it). Also separates the two
   searches over λ that had been discussed together: slice 4 part B goes continuous (13
   smoothing parameters make a grid impossible), the shipped production selector does not
   (ADR-186 chose the grid deliberately, for reproducibility). ADR-188 amendment 2 retires
   the "old age is a shared failure of both estimators" framing, with the delta-method
   control (unchanged at 0.6687) as the evidence the coverage move is attributable to
   ADR-197's fix and not the study. `PLAN_mgcv_parity_engine.md` slice 4's status and
   acceptance criteria updated to carry ADR-198's prediction into the next session.
   Presented, rather than decided, the two questions PR #204's round-2 review flagged as
   needing maintainer judgement (`gamma` tolerance promotion; whether the coverage move
   changes anything downstream) — both left open in this commit, on purpose.
2. **`61a59b0`** — records the maintainer's live confirmation of both questions `00ebd27`
   had left open (see this file's own session below for the exact exchange). At the time
   this commit was written, the confirming quote was not carried into the doc itself — see
   "Correction" below.

## Correction (recorded here per PR #204's round-3 review)

The round-3 review flagged `61a59b0`'s wording — *"Two decisions the maintainer
confirmed"* — as a **[P0]**: no quote, channel, or session log accompanied it, unlike
ADR-196/197's authorization, which was quoted verbatim in the commit body, a PR comment, and
a session log. The finding was correct: the substance was confirmed live in this session,
but nothing checkable said so.

**The exchange, in full.** After `00ebd27` shipped (presenting the `gamma`-tolerance and
coverage-move questions with a case for and against each), the maintainer wrote: *"Okay, I
am ready to merge, do you want to recommend a way forward on the open review questions so I
can authorize you to confirm this for future iterations to have the decision on hand?"*
Claude restated the recommendation already in `00ebd27` — do not promote the `gamma`
tolerances; the coverage move changes nothing downstream — as an explicit recommendation.
The maintainer replied: *"They look right."* `61a59b0` was written immediately after,
recording that exchange as decided.

**Fixed by this session's own follow-up commit**, which adds the quote above to
`docs/DECISIONS.md` (ADR-198) and `docs/CONTINUATION_mgcv_parity_engine.md`, following
the same pattern ADR-197's authorization used, and adds this session log — closing both
the [P0] and the accompanying [P2] (docs-only commits changing PLAN's acceptance criteria
with no session record).

**Superseded in part, 2026-08-22 (maintainer direction, PR #204 round-3).** The exchange
above is accurately recorded, but the *closure* `61a59b0` drew from it was preemptive: the
maintainer's *"They look right"* endorsed the substance of both recommendations on that
day's evidence, not a bar on revisiting them, and neither item has reached parity nor
definitive obsolescence. Both are now recorded as open, movable standing positions that a
later session may act on with its own evidence — see ADR-198's "Scope of that endorsement"
paragraph and the matching section in `docs/CONTINUATION_mgcv_parity_engine.md`.

## Baseline and end state

No code, tests, or committed reference artifacts touched by any commit in this session.
`git diff` on `src/`, `tests/`, and `data/` across all three commits (`00ebd27`, `61a59b0`,
and this one) is empty. `pytest`/`ruff` were not re-run — nothing they check moved.
