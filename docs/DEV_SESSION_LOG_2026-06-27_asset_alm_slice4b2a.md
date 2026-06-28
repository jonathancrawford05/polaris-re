# Dev Session Log — 2026-06-27 (Asset/ALM reserve-backed liability stream, Epic 4 Slice 4b-2a)

## Item Selected
- **Source:** `CONTINUATION_asset_alm.md` (active Epic 4 — Asset/ALM model,
  Tier-C C0 from `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`; ROADMAP 5.4) —
  Slice 4b-2, split into 4b-2a.
- **Priority:** Active Epic (advanced before any fallback, per routine step 5b).
- **Title:** Asset/ALM model — Slice 4b-2a: reserve-backed (Option B) liability
  stream in `analytics/alm.py` + CLI rewire.
- **Slice:** 4b-2a of 4b (4b-2 split into 4b-2a stream/CLI and 4b-2b dual-side/API).
- **Branch:** `claude/awesome-bardeen-q0t5sj` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE).

## Selection Rationale
Step 5 found `CONTINUATION_asset_alm.md` **IN PROGRESS** with Slices 1, 2, 3, 4a,
4b-1 all DONE and merged (`git log main` HEAD `83712ac` = the PR #111 merge of
4b-1). Slice 4b-2 is NEXT and unblocked (`list_pull_requests` state=open → `[]`,
so no review feedback to address, no draft-blocked epic). The CONTINUATION's next
slice IS the work selection (step 5c) — no fallback item picked, per the
one-active-Epic guardrail.

The CONTINUATION's 4b-2 entry flagged it as likely needing a sub-split into
**4b-2a** (reserve-backed stream + CLI rewire + closed-form tests) and **4b-2b**
(the API surface + dual ceded/cedant headline), "decided once the session has
read the reserve/net-premium plumbing." Having read that plumbing
(`core/cashflow.py`, `products/term_life.py` reserve recursions,
`core/reserve_basis.py`, the YRT/coinsurance reserve handling), I confirmed the
split is warranted and this session ships **4b-2a — the load-bearing
analytics-contract change** (the reserve-backed liability stream), keeping the
existing single CLI block pointed at the new stream. The dual reinsurer/cedant
headline rides with the API on 4b-2b.

## Verify Premise (step 7b)
Reproduced the 4b-1 defect the maintainer's Option-B resolution targets: under
the gross-premium `liability_cash_flows`, the golden WHOLE_LIFE cohort's outgo
discounts to a non-positive PV (premiums dominate benefits in PV for a
premium-paying / reserve-building block), so its duration is undefined and the
block is skipped — confirmed by the prior 4b-1 session log and the (now-removed)
`TestGracefulSkip` test asserting exactly that. The reserve-backed stream fixes
it: the new `test_whole_life_cohort_has_duration_gap` asserts WHOLE_LIFE now
carries a block with a positive liability PV. Premise holds; the corrected
approach (reserve run-off, PV ties to the held reserve) is implemented.

## What Was Done
Implemented the maintainer-resolved **Option B** liability as a **reserve run-off
(release) stream**, the standard IFRS-17 / embedded-value "expected liability
cash flow". New `reserve_liability_cash_flows(result, reserve_valuation_rate)` in
`analytics/alm.py` derives the liability directly from the held reserve series:
with `R_t = reserve_balance[t]` (opening reserve `R_0`) and
`a = (1 + reserve_valuation_rate)^(1/12)`, the month-`t+1` cash flow is
`L_t = R_t·a − R_{t+1}` (final `L_{T-1} = R_{T-1}·a`). This is the expected
benefits-and-expenses-less-valuation-premiums on the valuation basis, and
discounted at the reserve valuation rate it **telescopes exactly to `R_0`** — so
its present value ties to the held reserve by construction.

The decisive design choice is that this is **basis-agnostic via the reserve
series, not via per-basis valuation premiums**. I had initially scoped a
valuation-premium stream out of each product engine, but found (deriving the
net-premium reserve recursion) that the projected cash flows run on *both*
decrements while the reserve runs on mortality-only valuation survival, so the
projected streams cannot reconcile to the reserve — a separate valuation stream
would be needed per basis (and VM20's `max(NPR,DR)` has no clean prospective
premium at all). The telescoping reserve-runoff identity sidesteps this entirely:
it holds for *any* reserve series, so the held `reserve_balance` (already struck
on the deal's `reserve_basis`) is the only input, and no product-engine change is
needed. Verified end-to-end on a real TermLife projection across NET_PREMIUM /
CRVM / VM20 at a reserve rate (3.5%) distinct from the discount rate (5%):
`PV(run-off) == reserve_balance[0]` on each basis.

The CLI's `_price_single_cohort` now measures the gap against
`reserve_liability_cash_flows(net, config.effective_valuation_rate)` (the stream
is built at the reserve's own valuation rate; the duration is then measured at
the common ALM yield, ADR-111/112 default = deal `discount_rate`). For the golden
YRT path `net` carries the full reserve (YRT cedes none), so this is the retained
reserve the assets back. Both golden cohorts now carry a block; the graceful skip
is now a non-positive-opening-reserve edge case (still caught, never aborts a
run). Recorded as ADR-113. `liability_cash_flows` is retained as a benefit-outgo
view, superseded only as the duration-gap liability.

## Files Changed
- `src/polaris_re/analytics/alm.py` — new `reserve_liability_cash_flows`;
  `__all__`; `liability_cash_flows` docstring notes its supersession.
- `src/polaris_re/cli.py` — import `reserve_liability_cash_flows` (drop
  `liability_cash_flows`); `_price_single_cohort` measures the gap against the
  reserve-backed stream at `effective_valuation_rate`; updated comment/skip note.
- `tests/test_analytics/test_alm.py` — 12 new tests (run-off identity, end-to-end
  PV==reserve on each basis, skip trigger, validation).
- `tests/test_cli_alm.py` — WHOLE_LIFE-now-carries-a-block test; graceful-skip
  reframed to a never-aborts assertion (the deterministic skip trigger moved to
  the analytics boundary); docstrings updated.
- `docs/DECISIONS.md` — ADR-113.
- `docs/CONTINUATION_asset_alm.md` — 4b-2 split into 4b-2a DONE / 4b-2b NEXT.
- `docs/PLAN_asset_alm.md`, `docs/ROADMAP.md` — 4b-2a status.

## Tests Added
`tests/test_analytics/test_alm.py` (12):
- **Run-off identity (3):** PV telescopes to `reserve_balance[0]` at the reserve
  rate (parametrized over 4 rates); a building reserve gives an early net inflow
  (negative) then a final positive run-off; a one-month series runs off fully.
- **Validation / skip (3):** empty `reserve_balance` raises
  `PolarisValidationError`; a non-positive (all-zero) opening reserve raises
  `PolarisComputationError` through `duration_gap` (the CLI's caught skip
  trigger); dtype/shape checks.
- **End-to-end (3, parametrized):** a real TermLife projection on NET_PREMIUM /
  CRVM / VM20 (reserve rate 3.5% ≠ discount 5%) confirms `PV(run-off) ==
  reserve_balance[0]` on each basis.

`tests/test_cli_alm.py`:
- WHOLE_LIFE cohort now carries a duration-gap block with positive liability PV.
- A price run succeeds and prices every cohort (never aborts).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Reserve-backed liability stream (Option B) in `analytics/alm.py` | ✅ | `reserve_liability_cash_flows` |
| PV(liability) == held reserve on each basis | ✅ | Telescoping identity; end-to-end on NET_PREMIUM / CRVM / VM20 |
| Follows the deal's `reserve_basis` | ✅ | Basis-agnostic — reads the held `reserve_balance` (struck on the basis) |
| CLI rewired onto the reserve-backed stream | ✅ | `_price_single_cohort` uses `effective_valuation_rate` |
| WHOLE_LIFE skip resolved (block now defined) | ✅ | `test_whole_life_cohort_has_duration_gap` |
| Graceful skip → true edge case, never aborts | ✅ | non-positive opening reserve; caught per cohort |
| Purely additive (no asset portfolio → byte-identical) | ✅ | Golden run emits no block; additive test green |
| Own ADR | ✅ | ADR-113 |

## Open Questions / Follow-ups
- **Reinsurer/cedant dual gap + API (4b-2b).** This slice keeps the single CLI
  block on the retained (`net`) reserve. The maintainer's resolution wants the
  ceded (reinsurer-view) gap as the **headline** alongside the cedant side. For
  YRT the ceded reserve is ~0 (so only the retained side is defined); for
  coinsurance/modco it is proportional and meaningful. 4b-2b decides the JSON
  shape and mirrors it on `/api/v1/price`. Tracked in `CONTINUATION_asset_alm.md`
  (IN PROGRESS → in routine read scope).

## Parked Polish
None. (Nothing 3rd-order-or-deeper surfaced this session.)

## Impact on Golden Baselines
None. The duration gap is computed only when `deal.asset_portfolio` is supplied
(absent in every golden config). Verified: the `polaris price` golden run emits
no `alm_duration_gap` and its summary is unchanged; QA golden suite (76) green;
the additive test proves priced numbers are unchanged. No baseline regenerated.

## Harvest (step 17)
ADR-113 "Out of scope" yields: the reinsurer/cedant dual gap + API (= Slice
4b-2b), dashboard+Excel (4b-3), notebook (4b-4) — all tracked in the PLAN /
CONTINUATION (IN PROGRESS → in read scope), none newly promoted. The two Slice-2
NICE-TO-HAVE follow-ups (net-of-spread book yield; time-varying amortising earned
rate) remain in `PRODUCT_DIRECTION_2026-06-18.md`. Ledger healing (step 4b): PR
#111 (Slice 4b-1) merged since the last session is an Epic-4 CONTINUATION-backed
slice, not a discrete PRODUCT_DIRECTION queue entry — the epic stays IN PROGRESS,
correctly un-struck; nothing to heal.

## Baseline Note
Branch `claude/awesome-bardeen-q0t5sj`, base HEAD `83712ac` (PR #111 merge = the
real `main`). Baseline fast suite (`make test` / `pytest -m "not slow"`, exit 0):
**1754 passed, 110 deselected** (CIA tables MISSING from pymort as usual — those
tests deselect, not fail; SOA + CSO converted). Matches the prior session's
recorded post-change baseline (1754 passed) — no NEW/CHANGED failures, so
proceeded per the tolerance-aware check. Post-change: **1766 passed** (+12 new
tests); QA suite **76 passed**.
