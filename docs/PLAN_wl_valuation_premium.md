# Plan: the whole-life valuation premium, and the reserve that depends on it

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #2, **re-scoped 2026-08-09**
after the item as written was built, measured and withdrawn (**ADR-189**).
**Total slices:** 2
**Estimated scope:** ~2–3 dev-days.

## 1. Why this plan exists — the backlog item was sequenced wrong

IMPORTANT #2 asked for one thing: value the whole-life NET_PREMIUM reserve prospectively
to omega, closing the terminal-reserve artefact. That change was implemented in full. It
passed every closed-form test written for it, and it is **a regression**.

The reason is a second defect that the first one was masking. Every whole-life reserve
basis re-solves its equivalence-principle premium on a grid that starts at the
**valuation date**, so a policy is valued as though issued today at its attained age.
Under that convention `V_0 == 0` for a policy of *any* duration — and the to-omega
valuation is the first formulation honest enough to return it.

Measured on `notebooks/04_alm_duration_gap.ipynb`'s block (ten $1M whole-life policies
issued 20 years ago, attained 60):

| | opening reserve `R_0` |
|---|---:|
| shipped `main` | **$497,698.59** |
| to-omega change alone | **$0.00** |

A twenty-year-seasoned policy has a large positive reserve. `main` gets a plausible
number from a wrong formula; the to-omega change gets zero from a formula that is right
about everything except the premium it is handed. **CLAUDE.md §1 names inforce block
evaluation as the target use case**, so a zero seasoned reserve is a regression on
precisely the thing this project is for.

ADR-189 carries the full measurement set. This plan is its disposition.

## 2. Design anchors

**Anchor 1 — the premium is a property of the policy at issue, not of the valuation
date.** A valuation reserve is `APV(future benefits) − P · APV(future premiums)` where
`P` is the premium the policy was *sold* at. Re-deriving `P` at the valuation date makes
the reserve identically zero and is the defect. This anchor is the whole of slice 1.

**Anchor 2 — `V_0 == 0` must hold for a new issue and must NOT hold for a seasoned
policy.** Both halves are load-bearing and the pair is two-sided by construction: the
current engine satisfies the first and violates the second; a naive "just make it
non-zero" fix would do the reverse. Every slice asserts both.

**Anchor 3 — the ALM surface is the acceptance test, not a downstream consumer.**
`analytics.alm.reserve_liability_cash_flows` is built so its present value *equals* the
opening reserve. That makes the ALM duration gap the most sensitive available probe of
whether the opening reserve is right, and it is already wired to whole life. A fix that
leaves `notebooks/04_alm_duration_gap.ipynb` reconciling `$0 = $0` has not worked.

**Anchor 4 — every basis that solves a valuation premium moves together, and VM-20 is
half an exception.** NET_PREMIUM, CRVM, GAAP and **VM-20's NPR leg** all solve an
equivalence-principle premium on the valuation-date grid and all inherit the fix.
**VM-20's DR leg does not** — a deterministic gross-premium reserve uses no valuation
premium at all, so it already returns a non-zero seasoned reserve wherever it dominates
`max(NPR, DR)`.

*Amended after PR #191 [P1-1], which caught the original "all four bases" wording.* The
distinction is not pedantry: it means **VM-20 cannot be tested the way the other three
are**. A `V_0 > 0` assertion on VM-20 passes via DR dominance whether or not the fix
reaches its NPR leg, so on VM-20 the test must target the NPR component directly, or a
case constructed so `NPR > DR`. Measured on the ADR-189 fixture, VM-20 returns
$88,720.73 at issue and $497,901.99 at 20 years in force — non-zero throughout, on
entirely unfixed code.

**Anchor 5 — the goldens move, and that is expected.** All five `data/qa/` configs price
a WHOLE_LIFE cohort out of the shared `golden_inforce.csv`, despite every config's
`deal.product_type` reading `"TERM"`. TERM must stay byte-identical in all five; that is
the check that a change is scoped to the engine it claims.

## 3. Slices

### Slice 1: the issue-age valuation premium (all bases)

- **Status:** NEXT
- **Depends on:** nothing

**Scope.** Solve the equivalence-principle premium on a grid running from **issue**
(issue age, duration 0) rather than from the valuation date, then value the reserve
prospectively from the valuation date against that premium. Concretely this needs a
valuation mortality grid that starts at issue — `_build_valuation_mortality` currently
walks from `attained_age` and `duration_inforce`, and the premium solve needs the
issue-anchored variant while the prospective reserve slice still starts at the valuation
date.

Applies to all four bases (Anchor 4). CRVM's Full Preliminary Term modification and
VM-20's NPR floor both sit on top of the same premium and inherit the fix.

**Tests.**
- `test_the_reserve_at_issue_is_zero_for_a_new_issue` — Anchor 2, first half. Unchanged
  behaviour, asserted so the fix cannot break it.
- `test_a_seasoned_policy_has_a_positive_opening_reserve` — Anchor 2, second half. The
  defect, stated directly.
- `test_the_opening_reserve_matches_a_prospective_hand_calculation` — closed form: for a
  policy `d` months in force, `V_d = APV_d(benefits) − P_issue · APV_d(annuity)` computed
  independently, where `P_issue` is solved at issue.
- `test_the_seasoned_reserve_is_continuous_in_duration` — value the *same* policy at
  duration 0, 60 and 120 months and require the reserve to trace the same accumulation
  curve a single projection produces. This is the strongest available statement that the
  premium no longer depends on when you look.
- One test per basis that the fix reaches it (Anchor 4) — **and on VM-20 that test must
  assert on the NPR leg, or on a case where `NPR > DR`.** A plain `V_0 > 0` on VM-20
  passes today, unfixed, via DR dominance, so it would certify nothing.

**Acceptance criteria.** Anchor 2 holds on NET_PREMIUM, CRVM and GAAP, and on **VM-20's
NPR leg specifically** (not on `max(NPR, DR)`, which already satisfies it for the wrong
reason). The ALM notebook's block reports a seasoned opening reserve within a stated
tolerance of a hand calculation. QA goldens regenerated with TERM byte-identical.

### Slice 2: the to-omega net-premium valuation

- **Status:** BLOCKED on slice 1
- **Depends on:** Slice 1

**Scope.** The change ADR-189 built and withdrew. It is written up in full there and can
be rebuilt from that record: value `NET_PREMIUM` prospectively to omega through a routine
extracted from `_compute_reserves_gaap`, delete `_compute_annual_net_premiums` and
`_compute_terminal_reserves`, and restore the identity
`NET_PREMIUM == GAAP(neutral PADs)` that TermLife already has.

**What slice 2 must re-do rather than reuse.** Its measurements were taken against a
seasoned-premium basis that slice 1 changes, so every number in ADR-189's golden table is
stale by construction. The *tests* transfer; the *baselines* do not.

**Known consequences, already measured once (ADR-189):** four existing contrast tests in
`test_whole_life_crvm_reserve.py`, `test_whole_life_vm20_reserve.py` and
`test_wl_gaap_reserve.py` pin the artefact and invert into stronger statements of its
closure; the MCP eval `price_golden_whole_life` is a committed WL baseline and moves with
the goldens.

**Acceptance criteria.** `V_0 == 0` for a new issue at every horizon; the reserve
independent of the projection horizon; lapse unable to move it; and — the criterion
slice 2 could not meet on its own — the seasoned opening reserve **unchanged from slice
1's**, since valuing to omega must not disturb a premium solved at issue.

## 4. What is explicitly out of scope

- **TermLife.** Its `V_T = 0` terminal condition is correct because term coverage
  expires, and its seasoned re-solve produces a small but non-degenerate reserve. On the
  REST `SEASONED_POLICY` fixture (YRT 90%, `discount_rate=0.06`, default measurement
  yield) TERM reports $21.71 of ALM liability present value against whole life's $25.48
  — *both* negligible against $1,000,000 of face, which is the point: whole life's
  problem is a duration of 11.8 years attached to a liability of $25, not a smaller
  number than TERM's. (An earlier revision wrote "against $0.00 for whole life", which
  was the *post-change* figure quoted as though it were shipped behaviour — PR #191
  [P1-2].)
- **The prescribed statutory valuation-interest helper** (IMPORTANT #4).
- **Rebuilding the ALM epic's conclusions.** Slice 1 makes its notebook meaningful again;
  it does not re-derive `MEASUREMENT_*` documents.

## 5. Risks

1. **The issue-anchored grid is more expensive.** The premium solve extends the mortality
   grid backward by `duration_inforce` months for every policy. On a real inforce block
   with long durations that is a real cost, and the perf harness (ADR-176) will see it.
2. **CRVM's FPT modification may not compose cleanly** with an issue-anchored premium —
   its year-1/renewal split is defined relative to issue, which should *help*, but it has
   never been exercised that way.
3. **The goldens move twice**, once per slice. That is unavoidable given the ordering and
   is why each slice states TERM-byte-identical as its scoping check.
