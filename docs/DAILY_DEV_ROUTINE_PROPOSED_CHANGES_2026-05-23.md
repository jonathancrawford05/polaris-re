# Proposed Changes — Daily Dev Routine (2026-05-23)

## Why

The current routine has a feedback gap: follow-ups documented during
work (in CONTINUATION "Refinement Backlog" sections, ADR "Out of
scope" sections, and DEV_SESSION_LOG "Open Questions") are never read
again once their CONTINUATION is marked COMPLETE. The only file the
routine consults for new work is the latest
`docs/PRODUCT_DIRECTION_*.md`. Result: every refinement item raised
during a feature's review or design becomes invisible the day it
ships.

Until 2026-05-23 there were **~25 such follow-ups** spread across the
five COMPLETE CONTINUATIONs (portfolio_aggregation,
licat_capital, yrt_rate_table, substandard_rating,
deal_pricing_excel) and their ADRs (ADR-043, 045, 048, 049, 052, 053,
055, 057, 058). None had been promoted to PRODUCT_DIRECTION. The
one-time backfill into `docs/PRODUCT_DIRECTION_2026-05-23.md`
addresses the existing backlog; the routine changes below prevent
the next 25 items from going invisible the same way.

This document is the proposal. The routine prompt lives in the
trigger configuration outside this repo, so the changes here have to
be applied by the human who owns that trigger. Code changes in this
PR are limited to the docs themselves; no routine-execution behaviour
changes until the trigger config is updated.

## Change 1 — New routine step: harvest follow-ups on CONTINUATION
close

**Insert between current step 16 (DEV_SESSION_LOG) and current step
17 (CONTINUATION file update).** The new step runs only on multi-slice
sessions where the CONTINUATION file is about to transition from
`IN PROGRESS` to `COMPLETE`.

### Proposed new step (insert as step 17, renumber existing step 17 →
step 18):

```
== HARVEST FOLLOW-UPS (multi-session feature close only) ==

17. If this slice closes a CONTINUATION (status will change from
    IN PROGRESS to COMPLETE in step 18), promote every surviving
    follow-up into the latest PRODUCT_DIRECTION file so the next
    routine run can see them.

    Sources to harvest from:
    - The CONTINUATION's "Refinement Backlog" section (every item).
    - The CONTINUATION's "Open Questions (for human)" section —
      ONLY items that remain unresolved. Resolved items are skipped.
    - Every ADR introduced during this feature — the "Out of scope"
      paragraph. Only items not already implemented in subsequent
      slices.
    - The current DEV_SESSION_LOG's "Open Questions / Follow-ups"
      section.

    Find the target file:
        ls -t docs/PRODUCT_DIRECTION_*.md | head -1

    Decide: append or create new.
    - If the latest file is from within the last 30 days, APPEND
      to its "Promoted Follow-ups" section. Create the section if
      it does not exist.
    - If the latest file is older than 30 days, CREATE a new
      docs/PRODUCT_DIRECTION_{today}.md that:
        a. Lists items shipped since the prior file (cross-checked
           against `git log main` and the COMPLETE CONTINUATIONs).
        b. Carries forward unresolved items from the prior file.
        c. Adds the freshly harvested follow-ups.
      The cleanest pattern is the format used by
      docs/PRODUCT_DIRECTION_2026-05-23.md.

    Classify each promoted item as BLOCKER / IMPORTANT /
    NICE-TO-HAVE using the same criteria as PRODUCT_DIRECTION
    (commercial impact, blocking effect on first-deal quoting). A
    refinement that affects only large books or design polish is
    NICE-TO-HAVE; one that affects production correctness on the
    common path is IMPORTANT.

    Every promoted item MUST carry explicit provenance, e.g.
    "Source: CONTINUATION_portfolio_aggregation — Refinement
    Backlog #1" or "Source: ADR-058 Out of scope". This is the
    audit trail that lets future routine runs distinguish promoted
    items from new direction items.
```

## Change 2 — Tighten step 6's "already addressed" check

**Replace the current bullet under step 6:**

> c. Skip items already addressed by merged PRs or open PRs
>    (check with `gh pr list --state open` and recent git log)

**With:**

```
c. An item is "addressed" only when every bullet under it is shipped
   on main. Cross-check with `gh pr list --state open` AND `git log
   main`. A high-level item like "Portfolio aggregation" that has
   merged a Slice 1 + Slice 2 but has surviving refinement items
   in PRODUCT_DIRECTION's "Promoted Follow-ups" section is NOT
   considered addressed — those follow-ups are first-class work
   items. Skip the parent bullet only if all of its promoted
   follow-ups are also addressed.

   Promoted follow-ups carry "Source: ..." provenance lines.
   Treat them as independent work items, not as commentary on the
   parent.
```

## Change 3 — New routine step: maintain PRODUCT_DIRECTION tidiness

**Insert near the end of step 6 (after work selection is committed):**

```
   PRUNE: as a sanity step, scan the latest PRODUCT_DIRECTION for
   items whose acceptance criteria are already satisfied on main
   (check `git log` and the relevant CONTINUATION status). If found,
   either:
   - Remove the entry and log the closure in the session log
     ("Closed by inspection: <item> — already shipped via <commit>").
   - Or, if uncertain, leave it and flag in the session log under
     "Open Questions" so the next session can confirm.

   Do NOT prune items that were never started; only prune items
   whose work is verifiably shipped. When in doubt, leave it.
```

## Change 4 — Update step 17's CONTINUATION instructions

**The existing step 17 says:**

> When all slices are DONE, update Status to COMPLETE.

**Add to it:**

```
   AND ensure step 17 (HARVEST FOLLOW-UPS) ran first. The Status
   transition to COMPLETE removes this CONTINUATION from the
   routine's read scope; any unpromoted refinement items would be
   lost. Do not close a CONTINUATION whose refinement backlog has
   not been promoted to the latest PRODUCT_DIRECTION.
```

## Suggested Validation

After applying these changes, the next daily-dev run should:

1. Read `docs/PRODUCT_DIRECTION_2026-05-23.md` (the new latest).
2. See "Calendar-aligned portfolio aggregation" as the top IMPORTANT
   item (under "Promoted Follow-ups").
3. Select it as the next work item, since (a) no BLOCKERs remain
   from 2026-04-19 and (b) the recommended sprint orders it first.

If instead the routine reads 2026-04-19 and reports "all BLOCKERs are
already addressed; no work selected", the latest-file logic isn't
working — investigate `ls -t` mtime ordering.

## Rejected Alternatives

- **Separate `BACKLOG.md` file.** Adds yet another file the routine
  has to scan. The PRODUCT_DIRECTION mechanism already exists and is
  read; better to use it.
- **Keep CONTINUATIONs `IN PROGRESS` forever.** Breaks the "feature
  is shipped" signal. Step 5 of the routine specifically uses
  IN PROGRESS as the continuation signal — keeping COMPLETE features
  open would either cause routine re-runs of finished work or
  require a new sub-status the routine would have to learn.
- **Have the routine read CONTINUATION refinement backlogs
  directly.** Possible, but the routine then needs to dedupe across
  five+ CONTINUATIONs, decide which ADR Out-of-scope items are still
  open, and re-classify them by tier — all of which is what the
  harvest step does once, at close, with the relevant context
  fresh. Doing it at every run pushes that work onto every session.
- **Put follow-ups in ADRs only.** ADRs are decision records, not a
  work queue. Mixing them muddles both purposes.
