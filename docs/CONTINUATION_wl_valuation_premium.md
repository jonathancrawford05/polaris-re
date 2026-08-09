# Continuation: the whole-life valuation premium

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #2, re-scoped 2026-08-09.
**Plan:** `docs/PLAN_wl_valuation_premium.md`
**Predecessor:** **ADR-189** (the negative result that produced this plan)
**Status:** **IN PROGRESS** — slice 1 is NEXT and unstarted.
**Total slices:** 2
**Estimated total scope:** ~2–3 dev-days.

> **Which epic does the next session advance?** (PR #191 [P2-6] — two CONTINUATIONs are
> now IN PROGRESS.) **`CONTINUATION_penalized_mi_surface.md` takes precedence.** It is
> the routine's designated ACTIVE EPIC, it was blocked only because slice 4's PR was
> unmerged, and **PR #190 has since merged** — so its slice 5 (`mgcv` conformance) is
> unblocked and is the step-5b pick. This continuation is **gated fallback work**, and
> its slice 1 additionally wants the maintainer answer under "Open questions" before it
> starts.

## Overall goal

Make the whole-life valuation premium a property of the policy **at issue**, so that a
seasoned block has a correct non-zero opening reserve on every basis — and then, on that
foundation, value the NET_PREMIUM reserve prospectively to omega.

The second half is what `PRODUCT_DIRECTION` IMPORTANT #2 originally asked for. It was
built on 2026-08-09, measured, and withdrawn: on its own it takes the opening reserve of
a twenty-year-seasoned block from $497,698.59 to **$0.00**. ADR-189 has the evidence.

## Slices

### Slice 1: the issue-age valuation premium (all four bases)
- **Status:** **NEXT**
- **Depends on:** nothing
- **Files to modify:** `src/polaris_re/products/whole_life.py`
  (`_build_valuation_mortality` needs an issue-anchored variant; the premium solves in
  `_compute_reserves_crvm`, `_compute_reserves_gaap`, `_compute_reserves_vm20` and
  `_compute_reserves_net_premium` all consume it), plus golden baselines and the MCP eval
  if WL figures move.
- **Tests to add:** see PLAN §3 slice 1 — the two-sided `V_0` pair (zero at issue,
  positive when seasoned), a prospective hand-calculation, a continuity-in-duration test,
  and one per-basis reach test.
- **Acceptance criteria:**
  - `V_0 == 0` for a new issue **and** `V_0 > 0` for a seasoned policy, on all four bases.
  - The ALM notebook's block reports a seasoned opening reserve close to a hand
    calculation (Anchor 3 — the ALM surface is the acceptance test).
  - QA goldens regenerated with **TERM byte-identical in all five**.

### Slice 2: the to-omega net-premium valuation
- **Status:** BLOCKED on slice 1
- **Depends on:** slice 1 merged
- **Scope:** rebuild ADR-189's withdrawn change from its write-up. Its tests transfer;
  its baselines do not, because slice 1 moves the premium they were measured against.

## Context for the next session

- **Read ADR-189 first.** It is a negative-result record and contains the entire
  measurement set, including the four defects in the current net-premium path and the
  exact figures for the withdrawn change. Slice 2 is a rebuild from it, not a fresh
  design.
- **The opening reserve is the ALM surface's liability.**
  `analytics.alm.reserve_liability_cash_flows` is constructed so its present value equals
  `reserve_balance[0]`. That is why the ALM duration gap is the sharpest probe here — and
  why on shipped code it reports **$10–25 of liability present value against $1,000,000
  of face** on the REST `SEASONED_POLICY` fixture, depending on treaty and measurement
  yield (ADR-189 has the parameterised table; quote it *with* its settings, per PR #191
  [P1-2]). Whole-life ALM has never worked; the notebook's larger block hides it behind
  a plausible-looking $497,698.59.
- **`V_0 == 0` for a seasoned policy already holds on CRVM and GAAP on `main`** — measured,
  untouched code. So slice 1 is not a regression risk for those two; it is a fix they need.
- **VM-20 is the exception, and it is a trap for slice 1's test design** (PR #191 [P1-1]).
  `max(NPR, DR)`'s deterministic-reserve leg uses no equivalence-principle premium, so
  VM-20 already returns a large non-zero seasoned reserve — $497,901.99 at 20 years in
  force on the ADR-189 fixture, entirely unfixed. **A `V_0 > 0` assertion on VM-20 passes
  today and certifies nothing.** Test its NPR leg directly, or construct `NPR > DR`.
- **The QA goldens price whole life.** All five `data/qa/golden_config_*.json` have
  `deal.product_type: "TERM"`, which is misleading: the runner prices every product cohort
  in the shared `golden_inforce.csv`, and that block carries a WHOLE_LIFE cohort. Reading
  the configs is not enough — this cost a wrong "no rebaseline needed" conclusion mid-session
  before the quality gate caught it. Expect all five to move on any WL engine change, with
  TERM byte-identical as the scoping check.
- **The withdrawn change's downstream footprint, already mapped:** four contrast tests
  that pin the artefact (`test_crvm_does_not_collapse_at_horizon`,
  `test_golden_wl_terminal_reserve_artefact_closed`, `TestVM20NoCollapse::test_vm20_grades_toward_face`,
  `TestNotEqualNetPremium`), the MCP eval `price_golden_whole_life`, the REST ALM block
  tests, and `notebooks/04_alm_duration_gap.ipynb`.
- **`_compute_annual_net_premiums` carries two of the four defects** (truncated window,
  `lx` rather than mortality-only survival) and has exactly one caller. It is deletable in
  slice 2, not slice 1 — slice 1 still needs a premium solve, just an issue-anchored one.

## Open questions (for human)

- **Is the valuation-date premium re-solve a deliberate modelling convention?** It is
  consistent across all four whole-life bases and TermLife, which is more consistency than
  a bug usually shows. If it is deliberate — "price this block from today forward" rather
  than "reproduce the cedant's balance sheet" — then slice 1 is a product decision, not a
  defect fix, and the ALM surface is what needs re-specifying instead. This plan assumes
  it is a defect, because a reinsurer pricing an inforce block needs the cedant's held
  reserve, but the assumption is worth one sentence of confirmation before slice 1 starts.
- **Does the perf budget tolerate an issue-anchored grid?** It extends the mortality grid
  backward by `duration_inforce` months per policy for the premium solve (PLAN §5 risk 1).
