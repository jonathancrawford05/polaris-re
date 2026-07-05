# Continuation: Reserve-Basis Correctness & Interest Exactness

**Source:** PRODUCT_DIRECTION_2026-06-18.md Promoted Follow-ups — IMPORTANT
("WholeLife does not model mortality improvement on any basis" [correctness bug]
+ "Prescribed statutory valuation-interest helper" [penny-exact CRVM]). Epic
constituted per step 5b with the COMMERCIAL_VIABILITY_REVIEW Tier-A ladder
exhausted and Phases 1–3 complete — see `docs/PLAN_reserve_basis_correctness.md`.
**Status:** IN PROGRESS
**Total slices:** 3 (+ a viability-review checkpoint after Slice 1)
**Estimated total scope:** ~4–6 dev-days

## Overall Goal

Make the reserve basis both **correct** — WholeLife honours the configured
mortality-improvement scale on its best-estimate bases (projection cash flows,
GAAP, VM-20 deterministic reserve), as TermLife already does — and **exact** —
CRVM / VM-20-NPR value on the prescribed statutory valuation interest rate,
closing the interest half of "reproduce the cedant's held statutory reserve."

## Priority note (why this ordering)

Slice 1 fixes a **silent correctness bug** (WholeLife ignores a configured
`improvement` scale entirely), which was reprioritised to the front of the queue
at the maintainer's direction (2026-07-05) so it is fixed in the next dev run —
ahead of the interest-exactness slices, which are exactness polish. A bug that
silently produces wrong best-estimate mortality outranks penny-exactness.

## Decomposition

### Slice 1: WholeLife mortality-improvement on best-estimate bases
- **Status:** DONE (2026-07-05, ADR-129; branch `claude/loving-gauss-8brpd5`, PR #128)
- **What was done:** `WholeLife._build_rate_arrays` applies a configured
  `AssumptionSet.improvement` scale (mirroring TermLife: monthly→annual→improve→
  monthly via constant-force interpolation, before substandard rating and max-age
  forcing). `_build_valuation_mortality` gained an explicit `apply_improvement:
  bool = False` seam; GAAP and the VM-20 deterministic reserve pass `True`
  (best-estimate), CRVM and the VM-20 NPR keep `False` (prescribed static,
  ADR-125) — the seam is the caller, NOT `table is None`. Byte-identical on all
  goldens (no config sets WL improvement — verified by grep). 11 tests in
  `test_wl_improvement.py`; full fast suite + QA green; golden `flat`
  $45,386 / $3,513,563 exact.
- **Depends on:** nothing (independent; PR #127 / WL GAAP merged to main first).
- **The bug:** `WholeLife._build_rate_arrays` never reads
  `AssumptionSet.improvement`, so every WL basis (NET_PREMIUM / CRVM / VM-20 /
  GAAP) and the WL projection cash flows silently ignore a configured improvement
  scale. `TermLife._build_rate_arrays` (lines ~103–143) applies it; WholeLife does
  not. Reproduce first: price a WL block with and without
  `improvement=MortalityImprovement.scale_aa(...)` and observe identical output
  (the wrong behaviour), then fix.
- **Files to create/modify:**
  - `src/polaris_re/products/whole_life.py` — apply improvement in
    `_build_rate_arrays` (annual q → `improvement.apply_improvement(q, ages,
    cal_year)` → back to monthly via `constant_force_interpolate_rates`, BEFORE
    substandard rating and the max-age forcing — mirror TermLife exactly). Apply
    it to `_build_valuation_mortality` **only on the best-estimate path** (GAAP
    and the VM-20 deterministic reserve, i.e. `table is None`) via an explicit
    caller flag; do NOT apply it when a prescribed statutory `table` is passed
    (CRVM / VM-20 NPR — static by ADR-125).
  - `tests/test_products/test_whole_life.py` (or a new
    `test_wl_improvement.py`) — closed-form + guardrail tests below.
- **Design boundary (carry from ADR-125 / ADR-128):** improvement is a
  best-estimate property. Best-estimate WL bases (projection, GAAP, VM-20 DR)
  reflect it; prescribed statutory bases (CRVM, VM-20 NPR on `valuation_mortality`)
  stay static. The seam is the caller of `_build_valuation_mortality`, not a
  blanket change — a `apply_improvement: bool` parameter (default preserving
  current behaviour) is the likely cleanest form. Confirm CRVM/NPR are untouched.
- **Tests to add:**
  - Improvement-isolation (closed form): a Scale AA improvement lowers WL
    best-estimate q, so GAAP, the VM-20 deterministic reserve, and the projected
    claims all move DOWN, while CRVM and the VM-20 NPR on a prescribed table are
    unchanged.
  - WL analogue of the TermLife "GAAP reflects improvement" guardrail — now WL
    GAAP moves under a configured improvement scale (add to
    `tests/test_products/test_wl_gaap_reserve.py`).
  - Independent recomputation: WL best-estimate q with improvement applied equals
    a hand-built numpy improvement application (mirror the TermLife improvement
    test).
  - Byte-identity: no improvement configured → WL output byte-identical.
- **Acceptance criteria:**
  - WholeLife applies `AssumptionSet.improvement` on its best-estimate bases;
    a configured Scale AA moves GAAP / VM-20 DR / projected claims. ✅ target
  - CRVM and VM-20 NPR on a prescribed `valuation_mortality` table are unchanged
    by an improvement scale (statutory static rule preserved). ✅ target
  - Byte-identical goldens/QA when no WL config sets improvement (VERIFY this
    holds; if a WL golden sets improvement, the projection-side change is
    rebaseline-gated — flag for human authorisation and split the slice).
- **Byte-identity checkpoint (do early):** grep the golden/QA configs and sample
  data for a WL block with an improvement scale. Expected: none → fully
  byte-identical. Record the result in the session log.

### CHECKPOINT (after Slice 1, before Slice 2): regenerate COMMERCIAL_VIABILITY_REVIEW
- **Status:** DONE (2026-07-05, `docs/COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`;
  branch `claude/loving-gauss-o37i85`).
- **Outcome — REDIRECT recommended.** The regenerated review found the entire
  modeling roadmap complete (all Tier-A epics A1/A2/A3, C0 Asset/ALM, B3
  expense-allowance shipped; ROADMAP Phases 1–5 ✅). Interest-exactness (Slices
  2–3) reclassified from Tier-A-epic to **Tier-D exactness polish (★★★☆☆)** —
  the *correctness* half of this epic shipped in Slice 1; the *exactness* half
  no longer ranks first against the productization/credibility frontier
  (validation & benchmark pack A1′, production hardening A2′, ingestion
  robustness A3′). Recommendation: **demote Slices 2–3 to a NICE-TO-HAVE
  follow-up and constitute a productization epic next.** The redirect go/no-go
  was explicitly reserved for the maintainer in the Open Questions below —
  surfaced in the review §7 and the session log. Slices 2–3 remain fully
  planned/intact so the next session ships Slice 2 unchanged if the maintainer
  prefers to finish interest-exactness first.
- Phases 1–3 are COMPLETE and the Tier-A ladder is exhausted, so before
  committing the epic to the interest-exactness slices, regenerate
  `docs/COMMERCIAL_VIABILITY_REVIEW_<date>.md` (re-review the last ~10 PRs + docs,
  re-rank the catalogue) to confirm Slices 2–3 remain the highest-value
  continuation vs a *productization* epic (data-ingestion robustness, an
  AXIS/Prophet benchmark validation, packaging/deployment, documentation). If a
  productization epic out-ranks interest-exactness, re-scope Slices 2–3 (or spin
  up the higher-value epic and demote these to follow-ups). This is the deliberate
  guard against an epic-level polish spiral now that the modeling roadmap is done.
  The review also turns 30 days old ~2026-07-18 (step 6 regeneration trigger), so
  this checkpoint satisfies that too.

### Slice 2: Prescribed statutory valuation-interest helper — engine
- **Status:** DEPRIORITIZED — checkpoint (2026-07-05) recommends REDIRECT to a
  productization epic and demoting this to a NICE-TO-HAVE follow-up. Pending
  the maintainer's go/no-go (review §7). Still fully planned below so it can
  ship unchanged if the maintainer prefers to finish interest-exactness first.
- **Depends on:** Slice 1 merged + the checkpoint (both DONE).
- Issue-year (+ product/table) → SVL max valuation rate / VM-20 NPR discount rate
  resolver; wire into the CRVM and VM-20 NPR discounting when set. Default `None`
  keeps the manual `ProjectionConfig.valuation_interest_rate` byte-identical.
- **Acceptance criteria:** a known issue-year resolves to the published SVL rate;
  CRVM on the prescribed rate differs from CRVM on the manual rate; byte-identity
  when unset.

### Slice 3: Surface valuation-interest on the deal path + docs
- **Status:** PLANNED (provisional, pending the checkpoint)
- **Depends on:** Slice 2 merged.
- `DealConfig` / CLI / API surface (mirror the `valuation_mortality` ADR-126
  surfacing); notebook + ARCHITECTURE; HARVEST FOLLOW-UPS then Status → COMPLETE.

## Context for Next Session

- **Start here:** Slice 1 is NEXT and independent. Reproduce the bug first
  (WL block with/without a Scale AA improvement → identical output today), then
  mirror `TermLife._build_rate_arrays`' improvement block into WholeLife.
- The improvement application in TermLife lives at `term_life.py` ~lines 103–143:
  `improvement = getattr(self.assumptions, "improvement", None)`, then per month
  `q_annual = 1 - (1-q_monthly)**12`, `q_annual_improved =
  improvement.apply_improvement(q_annual, current_ages, cal_year)`, then
  `constant_force_interpolate_rates(q_annual_improved, fraction=1/12)`. Copy this
  shape; keep it BEFORE substandard rating and the max-age q=1 forcing.
- `_build_valuation_mortality(t_val, table)` is called with the statutory table
  (CRVM / VM-20 NPR — NO improvement) and with `table=None` (GAAP, VM-20 DR —
  best-estimate, SHOULD reflect improvement). Do not conflate: gate improvement on
  the basis/caller, not on `table is None` alone if any statutory path can pass
  `None` (it can — CRVM without a prescribed slot falls back to the projection
  table but must STAY static). Pass an explicit `apply_improvement` flag.
- **VERIFY the byte-identity assumption:** the fix is only byte-identical if no
  golden/QA/sample WL config sets an improvement scale. Check before coding; if
  one does, the projection-side change is rebaseline-gated (human authorisation).

## Open Questions (for human)

- Slice 1: is the WL improvement fix expected to be byte-identical (no WL golden
  configures improvement), or should any WL golden that DOES be rebaselined with
  authorisation? Default assumption: byte-identical; will confirm by inspection.
- Checkpoint: after Slice 1, do you want the interest-exactness slices to proceed,
  or should the regenerated viability review be allowed to redirect the epic to a
  productization theme if it ranks higher?

## Refinement Backlog

(harvest into PRODUCT_DIRECTION when this CONTINUATION closes)

- Surface the GAAP PADs on the deal path (`DealConfig` / CLI / API) — the standing
  IMPORTANT follow-up (ADR-127/128), related but not bundled into this epic.
- Sex/smoker-distinct statutory table composition + CSO-version selection
  (mortality-side exactness, NICE-TO-HAVE).
