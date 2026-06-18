# Proposed Changes — Daily Dev Routine (2026-06-18)

## Why

The 2026-05-23 routine changes fixed a *real* problem (follow-ups going
invisible when a CONTINUATION closed) but introduced a side effect: the
"harvest follow-ups" step deposits 2–3 fresh micro-items into the work queue
every time a feature ships, and the routine's single-session selection bias
then preferentially picks the smallest of them. The result is documented in
`docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`: the last 10 PRs (#69–#78)
collapsed into three polish themes, while the two long-standing IMPORTANT
features (reserve-basis matching, IFRS 17 movement) never started because
"no single session can finish a 10-day item."

These changes add an **epic track** so the routine advances one large,
high-value feature across staggered sessions, and **cap the polish spiral**
so third-order follow-ups stop crowding out direction work.

As with the 2026-05-23 proposal, the routine prompt lives in the trigger
configuration outside this repo; the human who owns that trigger must apply
these edits. This PR changes only the docs.

## Change 1 — New routine step: maintain exactly one active Epic

**Insert as a new step 5b (before the work-selection step 6).**

```
== ACTIVE EPIC (always-on, plan-driven) ==

5b. The routine must always have exactly ONE active Epic. An Epic is a
    Tier-A feature from docs/COMMERCIAL_VIABILITY_REVIEW_*.md (or a
    successor review) that is too large for one session and has a written
    multi-slice plan file docs/PLAN_<feature>.md (same style as
    docs/PLAN_dashboard_portfolio.md).

    a. Find the active Epic: the most recent docs/PLAN_*.md whose backing
       CONTINUATION_<feature>.md is IN PROGRESS, or whose plan has unchecked
       slices.

    b. If NO Epic is active, START one before picking any fallback work:
       - Take the top-ranked unstarted item from the Tier-A table in the
         latest COMMERCIAL_VIABILITY_REVIEW (respecting the recommended
         sequence and any stated dependencies).
       - Write docs/PLAN_<feature>.md decomposing it into 3–4 slices, each
         sized to one session and each leaving the goldens byte-identical
         until the final surfacing slice.
       - Open CONTINUATION_<feature>.md (status IN PROGRESS) and ship
         slice 1 this session. Writing the plan + slice 1 IS the session's
         deliverable; do not also pick a fallback item.

    c. If an Epic IS active, advance its next unchecked slice THIS session
       before considering any fallback work (see step 6).
```

## Change 2 — Remove the "scope it as a dedicated roadmap entry" escape hatch

**The current behaviour (PRODUCT_DIRECTION_2026-05-23, "What the next session
should consider") treats any ~10 dev-day item as out of bounds for a session
and falls back to the NICE-TO-HAVE queue. Replace that disposition with:**

```
   A large (multi-day) top-ranked item is NEVER a reason to fall back to a
   smaller item. When the highest-value available work is large, the
   session's job is to (a) ensure it has a PLAN file (write one if missing,
   per step 5b) and (b) ship its next slice. "It doesn't fit one session"
   is a decomposition instruction, not a skip condition.
```

## Change 3 — Fallback work is gated and bounded

**Replace step 6's free pick from the NICE-TO-HAVE queue with:**

```
6'. Fallback (Tier-B/C/D) work may be selected ONLY when:
    - the active Epic's next slice is genuinely blocked (state the blocker
      in the session log under "Open Questions"), OR
    - the Epic's next slice is complete and the session has remaining
      capacity, OR
    - the pick is a Tier-B quick win explicitly listed in the latest
      COMMERCIAL_VIABILITY_REVIEW "Sprint 0" / between-epics set.

    Within fallback work, prefer higher value-per-day (use the review's
    value x effort ranking, NOT "smallest available") as the tiebreaker.
```

## Change 4 — Cap the polish spiral on harvest

**Amend the 2026-05-23 "harvest follow-ups" step (Change 1 of that doc):**

```
   When harvesting ADR "Out of scope" notes, classify each by ORDER:
   - 1st-order: a follow-up of an originally-planned feature → promote
     normally (BLOCKER / IMPORTANT / NICE-TO-HAVE as today).
   - 2nd-order: a follow-up of a follow-up → promote as NICE-TO-HAVE only.
   - 3rd-order or deeper (a follow-up whose own source was already a
     promoted follow-up, e.g. "comparison sheet" -> "per-line-item
     comparison" -> "merged-header comparison"): DO NOT auto-promote.
     Log it once in the session log under "Parked Polish" and stop. It can
     be revived by an explicit human decision, not by the routine.

   Provenance lines must record the order, e.g.
   "Source: ADR-086 Out of scope (3rd-order — parked)".
```

## Change 5 — Re-rank against the commercial review, monthly

**Insert into the work-selection step:**

```
   Selection inputs, in priority order:
   1. The active Epic (step 5b) — always advanced first.
   2. The latest docs/COMMERCIAL_VIABILITY_REVIEW_*.md value x effort
      ranking — for choosing the NEXT Epic and for ordering fallback work.
   3. The latest docs/PRODUCT_DIRECTION_*.md — for newly surfaced items
      and reasonability context.

   If the latest COMMERCIAL_VIABILITY_REVIEW is older than ~30 days,
   regenerate it (re-review the last 10 PRs + docs, re-rank the catalogue)
   before selecting the next Epic, so "smallest available" never silently
   becomes the default again.
```

## Suggested Validation

After applying these changes, the next daily-dev run should:

1. Read `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`.
2. Find no active Epic (no `docs/PLAN_*.md` is IN PROGRESS for a Tier-A
   item).
3. Start Epic 1 — **Reserve-basis matching** — by writing
   `docs/PLAN_reserve_basis.md` (3–4 slices), opening
   `docs/CONTINUATION_reserve_basis.md` (IN PROGRESS), and shipping slice 1
   (the `ReserveBasis` enum + plumbing, goldens byte-identical).
4. NOT pick another sub-day Excel/sufficiency polish item this session.

If instead the run ships another sub-day polish PR and reports "no
single-session IMPORTANT item available", the epic track isn't wired in —
check that step 5b runs before step 6.

## Rejected Alternatives

- **Just stop harvesting follow-ups.** Throws out the 2026-05-23 fix; real
  1st-order follow-ups would go invisible again. The order-cap (Change 4)
  keeps the fix while stopping the spiral.
- **Manually pick the Epic each day.** Defeats the point of an autonomous
  routine. The ranking lives in the review doc so the routine can self-select.
- **One giant PR per Epic.** Unreviewable and high-risk; violates the
  byte-identical-goldens-until-surfacing discipline that has kept the suite
  green. Staggered slices preserve it.
- **Drop the single-session constraint entirely.** Sessions are still
  one-slice; the change is that slices now ladder up to a large feature
  instead of being the whole deliverable.
