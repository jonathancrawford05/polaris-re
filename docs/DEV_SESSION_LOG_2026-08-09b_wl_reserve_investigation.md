# Dev session log — 2026-08-09b — the WL net-premium fix, built and withdrawn

## Item Selected

- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — Carried-Forward Promoted Follow-ups,
  IMPORTANT **#2**. *Source: ADR-089 Out of scope +
  `DEV_SESSION_LOG_2026-06-19_reserve_basis_slice2b` Open Questions (1st-order).*
- **Priority:** IMPORTANT (gated fallback — the Epic is blocked, see rationale)
- **Title:** Close the WL terminal-reserve artefact on the NET_PREMIUM basis
- **Slice:** **none shipped.** The item was re-scoped into a 2-slice feature; this
  session delivered the investigation, the ADR and the plan.
- **Branch:** `claude/quirky-ramanujan-1rx749` (environment-designated; overrides the
  routine's `feat/auto-*` default per step 8's ENVIRONMENT OVERRIDE)
- **ADR:** **ADR-189** — a negative-result record

## Outcome, stated first

**The change the backlog asked for was implemented in full, passed its own closed-form
tests, and was then withdrawn because measurement showed it makes the engine worse on
this project's primary use case.** No engine code is on the branch. What ships is the
measurement set, ADR-189, `PLAN_wl_valuation_premium.md`, a CONTINUATION with slice 1
NEXT, and the ledger re-scoping.

The one-line finding: **the backlog item was sequenced wrong.** Valuing the whole-life
net-premium reserve to omega is correct, and it is a regression until a prerequisite
nobody had recorded — an issue-age valuation premium — lands first.

## Baseline

| | |
|---|---|
| Baseline (`main` @ `a2a58d1`, PR #189 merged) | **3102 passed, 3 skipped, 125 deselected**, 0 failed (9m34s) |
| Previous session log's recorded end state | 3102 passed, 3 skipped, 125 deselected |
| Delta | **none** — no new or changed failures; tolerance-aware check passes |
| End state | **unchanged from baseline** — the branch carries documentation only |
| SOA conversion (step 2) | 6/6 converted; the 4 CIA 2014 tables report MISSING, as on every run |

## Selection Rationale

**The active Epic could not be advanced, so this is a gated fallback pick (step 6).**

The Epic is the penalized MI surface (`CONTINUATION_penalized_mi_surface.md`, IN
PROGRESS). Its next slice is **5** — the `mgcv` conformance suite — and it is blocked:

- **Slice 4 is PR #190, open and unmerged** (approved; zero P0/P1, six optional P2s).
- **Slice 5 depends on slice 4's code specifically** — conformance levels 4 and 5 test
  the Kass–Steffey unconditional covariance and Wood's `gamma`, both introduced there.
  An exporter built on `main` could not reference them.
- The guardrail *"NEVER start a new slice if the prior slice's PR has unresolved review
  feedback"* also binds: #190's six P2s are unaddressed.
- Addressing those P2s directly was considered and rejected — they live on
  `claude/quirky-ramanujan-mgvwcy`, and this session must push to
  `claude/quirky-ramanujan-1rx749`, so the fixes would open a second PR rather than
  update #190.

This is the merge-cadence gate the routine's own notes anticipate. Recorded under Open
Questions.

**Within fallback, why this item.** No BLOCKER remains. Of the five unshipped IMPORTANT
items, #4 (prescribed valuation-interest helper) needs NAIC rate data that CLAUDE.md
forbids guessing at; #6 and #7 need an external store (Redis) and deployment
infrastructure; #11 is a maintainer decision, not code. The two items harvested
2026-08-08d need the maintainer's local ILEC cache. #2 was the remaining
self-contained, closed-form-verifiable item, on the **default** reserve basis of a
shipped product, with a tested reference implementation of the fix already in the same
class (the GAAP path). Tier-C's C5/C6 rank below an IMPORTANT item under step 6a.

## Verify Premise (step 7b) — held, and got sharper

The entry says the reserve "collapses at the horizon". It does. But the sharper
falsification needs no reference to the horizon at all: **a net level premium reserve is
zero at issue by definition**, and it was not.

| projection horizon | `V_0` (must be 0) | shape |
|---|---:|---|
| 5 years | $198.45 | peaks month 36, falls to the horizon |
| 10 years | $613.79 | peaks month 60 |
| 20 years | **$5,067.67** | peaks month 144, ends 96% below peak |
| 40 years | **$47,556.78** | — |

**Four** defects, of which the entry named one: a premium solved over the truncated grid
(so the error *grows* with the horizon); a premium solved over `lx`, which carries lapse,
so the lapse assumption moved a mortality-only quantity; the one-period terminal estimate
`face · q_T · v` standing in for `A_{x+T}`; and — previously unrecorded — an incoherent
limited-pay window, capped at `min(pay_years·12, projection_months)`, so a 20-pay policy
on a 10-year projection had its premium solved over a window shorter than its own pay
period.

## What Was Built (and is not on the branch)

`_compute_reserves_net_premium` rewritten to value prospectively to omega through a
routine **extracted from `_compute_reserves_gaap`** rather than newly written — that
arithmetic has been correct since ADR-128, and NET_PREMIUM was the one basis on this
class not using it. It worked:

- `V_0 == 0` to 1e-6 at 5/10/20/40-year horizons;
- the reserve became independent of the projection horizon (10y vs 30y agreeing to 1e-8);
- a 6× lapse assumption stopped moving it;
- it matched an independently-coded backward recursion to 1e-6;
- it restored `NET_PREMIUM == GAAP(neutral PADs)`, the identity TermLife has always had.

11 new tests passed. Four existing *contrast* tests that pinned the artefact were
inverted into strictly stronger statements of its closure. All five QA goldens were
regenerated — TERM byte-identical in all five, only WHOLE_LIFE moving, with the YRT
reinsurer moving −0.3% (NAR-based) against the coinsurance reinsurer's −10.5%
(proportional), the divergence that shows it flowing through treaty mechanics correctly.

## Why It Was Withdrawn

The full suite surfaced three failures in one place: the REST ALM duration-gap block, the
MCP whole-life eval, and **the Asset/ALM epic's own validation notebook**, which failed
constructing a bond portfolio sized off the opening ceded reserve — because that reserve
had become `$0`.

`analytics.alm.reserve_liability_cash_flows` is built so its present value equals the
**opening held reserve**. Measured on that notebook's block — ten $1M whole-life policies
**issued 20 years ago**, attained age 60:

| | opening net reserve `R_0` | peak |
|---|---:|---:|
| shipped `main` | **$497,698.59** | $800,300.30 |
| the to-omega change | **$0.00** | $1,245,464 |

A twenty-year-seasoned policy has a large positive reserve. `main` produces a plausible
$497.7k from a formula that is wrong in four ways; the "fixed" version produces exactly
zero. **It is right at issue and wrong whenever the policy is seasoned.**

The cause is a defect this project had not recorded: every whole-life basis re-solves its
equivalence-principle premium on a grid starting at the **valuation date**, so a policy
is valued as though issued today at its attained age, and `V_0 == 0` follows by
construction at any duration. Confirmed on untouched code — a 10-years-in-force policy
returns `V_0 = 0.00` on **both CRVM and GAAP**. NET_PREMIUM's truncated recursion was the
only basis returning something non-zero for a seasoned policy, accidentally.

**CLAUDE.md §1 names inforce block evaluation as the target use case.** A change correct
for new issues and returning zero for seasoned blocks is a regression on exactly that, so
it was withdrawn rather than shipped behind a draft-PR flag.

## Files Changed

- `docs/DECISIONS.md` — **ADR-189**, a negative-result record carrying the full
  measurement set.
- `docs/PLAN_wl_valuation_premium.md` — **new**, 2 slices, 5 design anchors.
- `docs/CONTINUATION_wl_valuation_premium.md` — **new**, IN PROGRESS, slice 1 NEXT.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #2 marked **RE-SCOPED, NOT SHIPPED**
  with the evidence; harvest section appended.
- This log.

**No source, test or baseline file is modified.** `git status` against `main` shows
documentation only.

## Tests Added

**None on the branch.** The 11 written for the withdrawn change test behaviour that is
not shipped; committing them would mean committing 11 failing tests. They are specified
in `PLAN_wl_valuation_premium.md` §3 so slice 2 rebuilds them rather than re-deriving
them.

## Acceptance Criteria

| Criterion | Status | Notes |
|---|---|---|
| Premise reproduced before implementing (step 7b) | ✅ | And sharpened — 4 defects, not 1 |
| The terminal-reserve artefact closed on NET_PREMIUM | ❌ **not shipped** | Correct in isolation, regression in context |
| Its own ADR | ✅ | ADR-189, as a negative result |
| Item disposed of rather than left ambiguous | ✅ | Re-scoped into a 2-slice plan, prerequisite first |
| Discovery quantified and filed (step 11b) | ✅ | Three items harvested, two IMPORTANT |
| Suite green | ✅ | Branch is documentation-only; baseline unchanged |
| No core data contract changed | ✅ | Nothing in `src/` modified |

## Perf History

**No row appended.** Step 14b records one deterministic-first row per PR for the *branch
HEAD as changed engine*; this branch changes no engine code, so a row would pin a commit
identical to `main` in every measured respect and add a duplicate point to the series
without adding information. Recorded here rather than skipped silently. Creep verdict:
**not run** — no engine change to assess.

## Open Questions / Follow-ups

1. **Is the valuation-date premium re-solve a deliberate convention?** It is consistent
   across all four whole-life bases *and* TermLife, which is more consistency than a bug
   usually shows. If deliberate — "price this block from today forward" rather than
   "reproduce the cedant's balance sheet" — then slice 1 is a product decision and the
   ALM surface needs re-specifying instead. **This is the one answer that should precede
   slice 1**, and it is the plan's stated assumption, not its finding.
2. **The Epic is blocked on a merge, not on the routine.** PR #190 is approved and
   unmerged; slice 5 depends on its code. Merging it unblocks the Epic immediately.
3. **Whole-life ALM has never worked and nothing says so** — $20.34 of liability against
   $1M of face on the REST fixture, on shipped code. Harvested IMPORTANT.
4. **Step 4b ledger healing was deliberately not duplicated.** PR #189 merged since the
   last session log, and its heal is already carried by the open PR #190 (its review
   confirms "step-4b ledger heal (#189)"). Repeating it here would guarantee a conflict
   on the same lines. This PR touches that file only to re-scope IMPORTANT #2 and append
   a harvest section; a conflict with #190's appended section remains possible and is a
   trivial both-sides-keep.

## DISCOVERY (step 11b) — three items filed

1. **Whole-life ALM has never worked** — the duration-gap liability *is* the opening
   reserve, and it is $20.34 against $1M of face on shipped code. **IMPORTANT.**
2. **Every WL basis re-solves its valuation premium at the valuation date** — so no
   seasoned block has a correct opening reserve on any basis, including three shipped
   statutory ones. **IMPORTANT.**
3. **`deal.product_type` in the golden configs does not describe what the goldens
   price** — all five read `"TERM"` and all five price a WHOLE_LIFE cohort from the
   shared inforce CSV. **NICE-TO-HAVE** (documentation of a trap).

Item 3 is a correction to this session's own work: a mid-session conclusion that "no
rebaseline is needed" came from reading the configs, and only the quality gate caught it.

## Parked Polish

None. All three harvested items are 1st-order, so the step-17 order cap did not bind.

## Impact on Golden Baselines

**None.** The baselines were regenerated while the change was in the tree and then
reverted with it; `tests/qa/golden_outputs/` is not in the diff. The measured deltas are
preserved in ADR-189 for slice 2, with the warning that they are **stale by
construction** — slice 1 moves the premium they were measured against.
