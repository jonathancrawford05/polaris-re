# Dev Session Log — 2026-06-26

## Item Selected
- **Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier-C **C0**
  (Asset / ALM model), the recommended **fourth epic** after the three Tier-A
  epics; ROADMAP Milestone 5.4. New epic started this session
  (`docs/PLAN_asset_alm.md` + `docs/CONTINUATION_asset_alm.md`).
- **Priority:** Tier C / C0 (★★★★☆ value, ~20 dev-days, the top remaining big
  rock now that A1–A3 are complete)
- **Title:** Asset / ALM model — Slice 1: bond cash-flow model + `AssetPortfolio`
- **Slice:** 1 of 4
- **Branch:** claude/awesome-bardeen-g36zmo (environment-designated)

## Selection Rationale
Step 5 found **no IN PROGRESS CONTINUATION** — all ten existing CONTINUATIONs
are COMPLETE, including the three Tier-A epics (reserve-basis matching, IFRS 17
movement, cross-jurisdiction capital; the last Epic-3 slices shipped earlier
today via PR #106). With no active Epic, step 5b mandates **starting one**: take
the top-ranked unstarted item in the latest COMMERCIAL_VIABILITY_REVIEW's
recommended sequence. The review (2026-06-18, 8 days old — not stale) §4 names
the Asset/ALM model (C0) as the explicit fourth epic "once the three
credibility/market-access gaps are closed." All three are now closed, so
Asset/ALM is the correct next epic. Writing the PLAN + shipping Slice 1 is the
session's deliverable; per the guardrail, no fallback item was also picked.

No open PRs (`list_pull_requests` state=open → []), so no review feedback to
address and no draft-blocked epic. Ledger: the Epic-3 follow-ups were already
crossed-out as SHIPPED by today's earlier sessions; nothing further to heal.

## Premise Verification (step 7b)
The epic's premise — the engine has no asset model and Modco prices on a flat
rate — was reproduced before coding: `find src -name "*asset*"` returns
nothing, ROADMAP 5.4 is ⏳ DEFERRED, and `reinsurance/modco.py` computes
`modco_interest = ceded_reserve_balance * modco_interest_rate / 12` from a flat
`modco_interest_rate` field. Premise holds.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Bond cash-flow model + `AssetPortfolio` (pricing) | ✅ Done | #107 |
| 2 | Investment income + duration / convexity | ⏳ Next | — |
| 3 | Modco integration (asset-driven modco interest) | 🔲 Planned | — |
| 4 | `analytics/alm.py` duration gap + CLI/API/dashboard/Excel surfacing | 🔲 Planned | — |

## What Was Done
Started Epic 4 (Asset / ALM) by writing the plan (`docs/PLAN_asset_alm.md`, 4
slices) and the running log (`docs/CONTINUATION_asset_alm.md`, status IN
PROGRESS), then shipped Slice 1 — the asset-side data model.

`core/asset.py` adds two frozen `PolarisBaseModel`s. `Bond` describes a single
fixed-income instrument on the monthly projection grid (`face_value`,
`coupon_rate`, `coupon_frequency` constrained to divisors of 12, `term_months`,
optional `book_value` resolved to par via a `carrying_value` property). Its
`cash_flow_vector(months)` projects coupon + principal to a `(months,)` float64
array (1-indexed, end-of-month), and `price(annual_yield)` discounts that vector
on the **engine's** effective-annual monthly convention
(`v = (1+y)^(-1/12)`, cash flow at month t discounted by `v^t`) so a bond PV and
a `CashFlowResult` PV are directly comparable. `AssetPortfolio` holds a non-empty
list of bonds and aggregates their cash-flow vector, market value, book value,
and face. Exported from `polaris_re.core`; ADR-108.

The slice is purely additive — nothing is wired into any product, treaty, or
pricing path — so all golden baselines are byte-identical (verified: QA golden
suite 76 passed, `polaris price` golden run unchanged). The discounting-
convention decision is the load-bearing one carried into the CONTINUATION for
Slices 3–4.

## Files Changed
- `src/polaris_re/core/asset.py` — NEW; `Bond`, `AssetPortfolio`.
- `src/polaris_re/core/__init__.py` — re-export `Bond`, `AssetPortfolio`; `__all__`.
- `docs/PLAN_asset_alm.md` — NEW; the 4-slice epic plan.
- `docs/CONTINUATION_asset_alm.md` — NEW; running log, status IN PROGRESS.
- `docs/DECISIONS.md` — ADR-108.
- `docs/ROADMAP.md` — Milestone 5.4 → 🔄 IN PROGRESS, Slice 1 checked.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — two harvested follow-ups (stochastic
  reinvestment yields; non-fixed-income asset classes).

## Tests Added
- `tests/test_core/test_asset.py` — 34 tests: par-bond-to-par, zero-coupon
  closed form, premium/par/discount (parametrized), coupon timing
  (annual + semiannual), horizon truncation/padding, manual-discounting
  reconciliation, portfolio aggregation = sum of constituents, book/face
  totals, and field validation (`coupon_frequency` divides 12, positive
  face/term, non-negative coupon/book, non-empty portfolio, frozen models).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `Bond` cash-flow vector (coupon + principal) on monthly grid | ✅ | Closed-form timing tests |
| Bond pricing on engine discounting convention | ✅ | Par-bond-to-par + manual-discount reconciliation |
| `AssetPortfolio` aggregation (cash flow, market value, book, face) | ✅ | Sum-of-constituents tests |
| Field validation | ✅ | freq-divides-12, positive face/term, non-empty |
| Goldens byte-identical (additive slice) | ✅ | QA 76 passed; `polaris price` unchanged |
| Full fast suite green | ✅ | 1664 → 1698 passed (+34 new) |
| Exported from `polaris_re.core` | ✅ | `__all__` updated |
| ADR recorded | ✅ | ADR-108 |

## Open Questions / Follow-ups
- **Reinvestment yield boundary (Slice 2/3).** Slices 1–2 treat the book yield
  as the flat reinvestment yield. Stochastic reinvestment (Hull-White / CIR via
  `analytics/stochastic.py`, ROADMAP 5.4) is deliberately out of the epic's core
  scope — harvested to PRODUCT_DIRECTION as NICE-TO-HAVE. Confirm that boundary.
- **Modco precedence (Slice 3).** Proposed rule: when both an `AssetPortfolio`
  and a flat `modco_interest_rate` are supplied, the asset book yield takes
  precedence and the flat rate is the fallback. Confirm before Slice 3.
- Non-fixed-income asset classes harvested to PRODUCT_DIRECTION as NICE-TO-HAVE.

## Parked Polish
None. (All follow-ups this session are 1st-order out-of-scope items of ADR-108,
promoted normally; nothing 3rd-order-or-deeper.)

## Impact on Golden Baselines
None. Slice 1 is purely additive — no product/treaty/pricing path touched. QA
golden suite (76) and the `polaris price` golden run are unchanged; no baseline
regenerated.
