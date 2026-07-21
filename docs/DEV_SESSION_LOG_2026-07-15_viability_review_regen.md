# Dev Session Log — 2026-07-15

## Item Selected
- **Source:** Routine step 5b / step 6 — **Tier-A ladder exhaustion**. The
  active-epic track (`CONTINUATION_cedant_ingestion`, A3′) closed last session
  (PR #139 merged), and all three Tier-A epics from
  `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` (A1′ validation, A2′ prod
  hardening, A3′ ingestion) are now COMPLETE. No unstarted Tier-A item exists
  to start.
- **Priority:** N/A — strategic direction-setting (regenerate the commercial
  viability review), not a PRODUCT_DIRECTION work item.
- **Title:** Regenerate `COMMERCIAL_VIABILITY_REVIEW` — re-rank the catalogue
  with the 2026-07-05 Tier-A ladder exhausted; constitute the next active epic.
- **Slice:** complete (single deliverable — the review document).
- **Branch:** `claude/loving-gauss-fzhprq` (designated remote-session branch;
  environment override per step 8). Cut from `origin/main` at `ccfbdde`
  (post-#139).

## Selection Rationale
Step 5 found no IN-PROGRESS CONTINUATION driving an active epic (the only
IN-PROGRESS one, `reserve_basis_correctness`, is explicitly parked /
deprioritised — superseded 2026-07-05). Step 5b requires exactly one active
Tier-A epic and, when none is active, says to **start** the top-ranked
*unstarted* Tier-A item from the latest review. But the latest review's entire
Tier-A ladder (A1′/A2′/A3′) has shipped in the last ten days (PRs #130–#139),
so there is **no unstarted Tier-A item to start**.

Promoting a Tier-B/C item to epic status without a fresh re-rank would be
exactly the "smallest-available-becomes-the-default" failure the
review-regeneration guard exists to prevent (step 6; and §6 of the prior
review — the epic-level polish-spiral guard). The routine's own precedent is
decisive: the 2026-07-05 reserve-basis checkpoint regenerated the review
"because the Tier-A ladder is exhausted." Same trigger here.

The prior review is only 10 days old (inside the ~30-day age trigger), but —
exactly as the 2026-07-05 review argued about *its* predecessor at 17 days —
"the catalogue underneath it has changed so much that a refresh is warranted
regardless." Three Tier-A epics closing in ten days is a material catalogue
change. Per step 6, a thorough regeneration is a substantial analytical task,
so **the regeneration is this session's deliverable and the next epic's Slice
1 is deferred to the next run.**

**What was skipped and why:** no fallback (Tier-B B1/B2/B4) pick — the
FALLBACK GATE (step 6) permits Tier-B only when an active epic's next slice is
blocked/complete-with-capacity; there is no active epic, and step 5b's
"starting the next epic is the deliverable" takes precedence. Constituting the
next epic requires the re-rank first (this session), so its PLAN + Slice 1 is
next session's job.

## Premise Verified (step 7b)
The "premise" for a review-regeneration is *Tier-A ladder exhaustion*.
Verified directly, not assumed:
- `grep Status docs/CONTINUATION_*.md`: every CONTINUATION is COMPLETE except
  `reserve_basis_correctness` (IN PROGRESS but explicitly parked / superseded).
- `list_pull_requests --state open` → `[]` (no open PRs; nothing in flight).
- `git log` confirms A1′ (#130–#132, ADR-130–132), A2′ (#133–#135,
  ADR-133–135), and A3′ (#136–#139, ADR-136–138) all merged to main.
- `CONTINUATION_validation_benchmark` Slice 4 (AXIS/Prophet side-by-side) is
  PARKED / reference-blocked — cannot be autonomously constituted.
Premise holds: the ladder is exhausted and no Tier-A item is startable without
a re-rank.

## What Was Done
Wrote `docs/COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md`. It reviews PRs
#130–#139 (the three Tier-A productization epics), documents that the entire
*written roadmap* — Phases 1–5 modeling, the 2026-07-05 productization ladder,
and ROADMAP Milestone 6.2 — is now shipped, and re-ranks the catalogue. The
central finding: the one remaining structurally-incomplete roadmap milestone
is **Phase 6.1 — Experience-Monitoring Automation** (the ML assumption
feedback loop), which is both the last unstarted roadmap "big rock" with a
written spec and the operational form of the project's ML-native differentiator
(CLAUDE.md §1). The review **constitutes A4′ Experience-Monitoring Automation
as the next active epic**, gives a suggested 3–4 slice decomposition (Pattern
B) for next session's PLAN, keeps B1/B2 as between-epic quick wins, and
surfaces a **post-roadmap inflection** decision for the maintainer (§7): after
6.1 closes, the written roadmap is complete and the routine needs a Phase-7
frontier (real AXIS/Prophet reconciliation, a new product class, stochastic
ALM, or a multi-user/persistence layer) or it enters maintenance mode.

No code changed; this is a strategic document only.

## Files Changed
- `docs/COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md` — new (the regenerated
  review); §4/§5/§6 updated post-scoping to name the reframed A4′ epic and
  point at the locked PLAN.
- `docs/PLAN_experience_gam.md` — new (the locked A4′ epic plan; see addendum).
- `docs/DEV_SESSION_LOG_2026-07-15_viability_review_regen.md` — this log.

## Maintainer Scoping Addendum (2026-07-15) — A4′ PLAN locked
After the review was drafted, a scoping discussion with the maintainer
reshaped and **constituted the next epic** this session (ahead of the "next
session" default), so the deliverable grew from "review only" to "review +
locked PLAN":
- **Reframe:** ROADMAP 6.1 shifts from a black-box `--retrain-ml` loop to an
  **interpretable GAM layer** for experience analysis — the auditable middle
  between the grouped-A/E credibility in `analytics/experience_study.py` and
  the XGBoost path in `assumptions/ml_mortality.py`.
- **Headline:** a **tensor mortality-improvement surface** `te(age,
  calendar_year)` on a **static select-base offset**, emitted as a
  `MortalityImprovement`-compatible `MI_x(y)` scale. Confirmed the existing
  VBT/CIA tables are select-and-ultimate (`get_qx_vector(ages, sex, smoker,
  durations)`), so the offset that pins age×duration is already available.
- **Key modeling decisions locked:** A/E over direct-qx (identical MI gradient,
  plus variance reduction + native multiplicative output); duration enters
  twice (select-base offset + penalized residual smoother); **Lexis/APC
  identifiability** default = calendar trend → improvement with the issue-year
  term constrained to zero and an optional `underwriting_era` factor escape
  hatch; `statsmodels GLMGam` (Slice 1) → `bambi`/`pymc` HSGP (Slice 2+) for
  the anisotropic tensor + partial pooling + honest forward projection; `mgcv`
  via `rpy2` as an **offline validation oracle only**, never a runtime dep.
- **Dependency staging call:** `bambi`/`pymc` pins recorded in the PLAN but
  added to the `[ml]` extra by the slice that imports them (`pymc` is
  compile-heavy — not added ahead of Slice 2). No `pyproject.toml` change this
  session.
- **Scope boundary:** the maintainer's new-data-source risk-segmentation work
  is explicitly **out of scope** (forward prospective-rating, not retrospective
  experience — carriers lack the fields historically); flagged as a later
  Phase-7 candidate reusing the same GAM machinery.
- **Data-structure + sources research (folded into the PLAN):** established
  that **grouped Lexis cells are the canonical input** — Poisson/NB
  sufficiency makes grouped exposed-and-deaths identical to seriatim for the
  GAM, and it is the shape public data ships in (new Design Anchor 7; Slice-1
  contract now carries by-count + by-amount + NB dispersion + an optional
  seriatim aggregator). Added a **Data Sources & Strategy** section: **HMD**
  (mortality.org) as the real age×year dev/test fixture; **SOA ILEC** (2012–19
  grouped flat file — all three Lexis axes, by-count + by-amount) + **MIM-2021**
  as the insured fit/validation source; **CIA** (annual study to PY2022-23,
  CIA2014 already in-repo, credibility paper) as Canadian validation targets;
  **loaders-not-data** rule (large/licensed files out of the image + CI). Slice
  2 gains an HMD improvement-recovery sanity test; Slice 4 gains the
  ILEC/CIA/HMD validation decks + loaders. Sources cited in the chat thread.

## Tests Added
None — docs-only session. Baseline `make test` was run at session start to
confirm a clean tree (see Impact on Golden Baselines); no source was touched,
so the quality gate's pytest/ruff steps have nothing to act on.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Tier-A ladder exhaustion verified before regenerating | ✅ | CONTINUATION statuses + no open PRs + git log for #130–#139 |
| Last ~10 PRs re-reviewed | ✅ | §1 table, PRs #130–#139 with ADRs |
| Catalogue re-ranked with the 2026-07-05 ladder shipped | ✅ | §4 Tier A–D re-ranked |
| A next active epic constituted (not an arbitrary smallest-available pick) | ✅ | A4′ Experience-Monitoring Automation (ROADMAP 6.1), §3/§5 |
| Suggested decomposition provided to unblock next session's PLAN | ✅ | §6 (3–4 slices, Pattern B) |
| Post-roadmap inflection surfaced for the maintainer | ✅ | §7 Phase-7 decision |
| Reconciled with the latest PRODUCT_DIRECTION | ✅ | §8 |

## Open Questions / Follow-ups
- **Phase-7 frontier (for the maintainer).** Surfaced in the review §7: after
  A4′/6.1 closes, the written roadmap is complete. Decide the next frontier
  (AXIS/Prophet reconciliation / new product class / stochastic ALM /
  multi-user persistence) or accept a shift into maintenance-mode quick-win
  harvest. Not harvested into PRODUCT_DIRECTION — it is a strategic go/no-go
  captured in the review, not a scoped work item.
- **AXIS/Prophet side-by-side (validation Slice 4).** Remains
  reference-blocked; revive on a maintainer-supplied reference output.
- **Next session:** A4′ PLAN is now locked (`PLAN_experience_gam.md`). Write
  `CONTINUATION_experience_gam.md` (status IN PROGRESS) and ship **Slice 1**
  (experience-data contract + marginal effect isolation, `statsmodels GLMGam`,
  additive / byte-identical). The tensor MI surface is Slice 2.

## Harvest (step 17)
Nothing to harvest into PRODUCT_DIRECTION this session: no ADR was introduced,
no CONTINUATION closed, and the session produced a strategic direction
document rather than code with an "Out of scope" tail. The one open item (the
Phase-7 decision) is a maintainer go/no-go recorded in the review §7, not a
promotable work item. The A1′/A2′/A3′ out-of-scope follow-ups were already
harvested by their own slice sessions into
`PRODUCT_DIRECTION_2026-06-18.md` "Promoted Follow-ups".

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups this session.)

## Impact on Golden Baselines
None. Docs-only session; no source, config, or golden touched. Baseline
`make test` at session start: **2195 passed, 3 skipped, 110 deselected, 0
failures** — matches the prior session log's post-#139 expectation (2194 + the
same green tree; tolerance-aware check: no new/changed failures). The 3 skips
are the CIA-2014 tables the pymort conversion could not reach (known-standing,
same as every prior session). No `polaris price` regression run needed — the
pricing path is untouched.
