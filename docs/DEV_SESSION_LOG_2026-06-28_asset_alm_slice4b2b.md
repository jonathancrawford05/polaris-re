# Dev Session Log — 2026-06-28

## Item Selected
- **Source:** CONTINUATION_asset_alm.md (active Epic 4 — Asset / ALM model;
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18 Tier-C C0)
- **Priority:** Epic slice (Tier-C C0, the active Epic)
- **Title:** Asset / ALM model — Slice 4b-2b: reinsurer/cedant dual duration gap +
  REST API surface
- **Slice:** 4b-2b of the 4-slice (re-decomposed) epic
- **Branch:** claude/awesome-bardeen-b4y4g1 (environment-designated)

## Selection Rationale
Step 5 found the Asset/ALM CONTINUATION **IN PROGRESS** with Slice 4b-2a's PR #112
**merged** (confirmed in `git log main`), so the routine continues the epic on a
new branch from main with the next unchecked slice — **4b-2b** — per step 5(b).
`list_pull_requests(state=open)` returned `[]`, so there was no draft blocking the
next slice and no review feedback to address. The active Epic's next slice was
advanceable, so steps 5b/6 (fallback selection) did not apply — the guardrail
mandates advancing the Epic before any fallback pick.

Baseline `make test`: **1766 passed, 110 deselected, 0 failed** — clean, no
pre-existing failures to diff against (the routine's documented 4 SOA failures did
not occur; the pymort conversion succeeded for the SOA/CSO tables the suite uses,
and the CIA tables it reports MISSING are not exercised by the test suite).

## Premise Verification (step 7b)
Reproduced the gap before coding. A `polaris price` run on the golden YRT config
with an injected `asset_portfolio` emitted a **single** flat `alm_duration_gap`
block (the cedant/net side) with no reinsurer/cedant split — confirming 4b-2a's
documented single-side limitation. Cross-checked the ceded reserve by treaty type:
YRT `ceded.reserve_balance[0] = 0` (so the reinsurer side will be undefined →
None), Coinsurance / Modco `ceded.reserve_balance[0] = 70.99` (so both sides will
be defined). The API `PriceRequest` had no `asset_portfolio` field. Premise holds.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Bond cash-flow model + `AssetPortfolio` | ✅ Done | #107 |
| 2 | Investment income + duration / convexity | ✅ Done | #108 |
| 3 | Modco integration (asset-driven modco interest) | ✅ Done | #109 |
| 4a | `analytics/alm.py` duration-gap core | ✅ Done | #110 |
| 4b-1 | CLI asset-portfolio input + duration-gap output | ✅ Done | #111 |
| 4b-2a | Reserve-backed liability stream + CLI rewire | ✅ Done | #112 |
| 4b-2b | Reinsurer/cedant dual gap + API surface | ✅ Done | #113 |
| 4b-3 | Dashboard + Excel presentation surfaces | ⏳ Next | — |
| 4b-4 | ALM validation notebook | 🔲 Planned | — |

## What Was Done
Advanced the Asset/ALM epic with Slice 4b-2b, implementing the maintainer-settled
dual-gap convention (reinsurer-view headline) and mirroring it on the REST API.

`analytics/alm.py` gained `DualDurationGap` — a frozen `PolarisBaseModel` holding a
`reinsurer` and a `cedant` `DurationGapResult | None`, with `is_empty` (both None)
and `headline` (reinsurer when defined, else cedant) helpers — and
`dual_duration_gap(portfolio, net_result, ceded_result, valuation_yield,
reserve_valuation_rate)`. The helper builds the reserve-backed run-off stream
(ADR-113) from **each** side's `reserve_balance` and measures the **same**
portfolio against both: the reinsurer-view gap (assets vs the ceded reserve — the
headline) and the cedant-view gap (assets vs the retained reserve). Each side is
computed independently; a private `_duration_gap_or_none` catches the
`PolarisComputationError` a non-positive reserve raises and returns `None` for that
side. For a YRT treaty the ceded reserve is ~0, so the reinsurer side is `None` and
the cedant side carries the gap; coinsurance / modco define both.

The CLI's `CohortResult.alm_duration_gap` became a `DualDurationGap`;
`_price_single_cohort` calls `dual_duration_gap` and omits the block only when both
sides are undefined (`is_empty`). The JSON shape moved from a flat
`DurationGapResult` to `{reinsurer, cedant}` — a *new, non-golden* output that only
appears when an asset portfolio is supplied, so the goldens stay byte-identical.
The Rich renderer prints the reinsurer (ceded) table first as the headline, then
the cedant (retained) table, skipping a `None` side.

The REST `/api/v1/price` surface gained `asset_portfolio: AssetPortfolio | None`
(the same JSON shape the CLI config accepts) and `alm_valuation_yield: float | None`
on `PriceRequest`, and `alm_duration_gap: DualDurationGap | None` on
`PriceResponse`, reusing the **same** `dual_duration_gap` compute path and the
`effective_valuation_rate` / `discount_rate` defaults as the CLI (CLI↔API parity).
A malformed bond is rejected as HTTP 422 by the endpoint's catch-all. ADR-114.

## Files Changed
- `src/polaris_re/analytics/alm.py` — `DualDurationGap`, `dual_duration_gap`,
  `_duration_gap_or_none`; `__all__` updated.
- `src/polaris_re/analytics/__init__.py` — re-export `DualDurationGap`,
  `dual_duration_gap`, `reserve_liability_cash_flows`; `__all__`.
- `src/polaris_re/cli.py` — `CohortResult.alm_duration_gap` → `DualDurationGap`;
  dual compute path; `_render_duration_gap_side` + dual `_render_alm_duration_gap`;
  import cleanup.
- `src/polaris_re/api/main.py` — `PriceRequest.asset_portfolio` /
  `alm_valuation_yield`; `PriceResponse.alm_duration_gap`; dual compute in `price()`.
- `docs/DECISIONS.md` — ADR-114.
- `docs/CONTINUATION_asset_alm.md` — 4b-2b → DONE, 4b-3 → NEXT.
- `docs/PLAN_asset_alm.md` — 4b-2b SHIPPED, 4b-3 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — struck the canonical-liability-stream
  IMPORTANT item as SHIPPED; harvested one NICE-TO-HAVE follow-up.

## Tests Added
- `tests/test_analytics/test_alm.py` — 5 `dual_duration_gap` tests: both sides
  defined (asset MV identical across sides; each side reproduces the single-side
  `duration_gap`; liability PV ties to each opening reserve at the reserve rate),
  YRT-like zero ceded reserve → `reinsurer is None`, `ceded_result=None` →
  `reinsurer is None`, both reserves non-positive → `is_empty`, `headline` prefers
  the reinsurer side.
- `tests/test_cli_alm.py` — updated existing tests to the dual shape (helpers
  `_blocks_by_product` / `_headline`); new `TestDualGapShape`: golden YRT →
  `{reinsurer: null, cedant: {...}}`, Coinsurance → both sides defined (identical
  asset MV, ceded liability PV > retained).
- `tests/test_api/test_main.py::TestPriceAlmDurationGap` — 7 tests: block null
  without a portfolio, both sides on Coinsurance, reinsurer-null on YRT, closed-form
  asset duration, `alm_valuation_yield` override, priced numbers unchanged by the
  asset side, HTTP 422 on a malformed bond.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Duration gap computed on both reinsurer (ceded) and cedant (net) sides | ✅ | `dual_duration_gap` |
| Reinsurer-view is the headline; YRT reinsurer side is None | ✅ | ceded reserve ~0 → caught; `headline` falls back to cedant |
| Coinsurance/modco define both sides | ✅ | CLI + API tests |
| CLI emits the dual `{reinsurer, cedant}` block + dual Rich render | ✅ | new JSON shape (non-golden) |
| `/api/v1/price` request gains asset_portfolio + alm_valuation_yield | ✅ | reuses `AssetPortfolio` JSON shape |
| `/api/v1/price` response gains alm_duration_gap (null when omitted) | ✅ | CLI↔API parity via shared compute path |
| Goldens byte-identical (additive block) | ✅ | golden run emits no `alm_duration_gap`; QA golden suite 76 passed |
| Full fast suite green | ✅ | 1766 → 1780 passed (+14 new) |
| ADR recorded | ✅ | ADR-114 |

## Open Questions / Follow-ups
- **Per-side valuation yield** (asset book yield on the reinsurer side, discount
  rate on the cedant side) instead of one common flat yield — already promoted as a
  NICE-TO-HAVE in PRODUCT_DIRECTION (ADR-111 follow-up); ADR-114 reiterates it. Not
  re-promoted (would be a duplicate / 2nd-order).
- **Distinct cedant-held vs reinsurer-held asset portfolios** — harvested as a new
  NICE-TO-HAVE this session (ADR-114 Out of scope, 1st-order). The single supplied
  portfolio is currently measured against both liabilities.

## Parked Polish
None. (The two follow-ups are 1st/2nd-order out-of-scope items of ADR-111/ADR-114;
nothing 3rd-order-or-deeper was generated.)

## Impact on Golden Baselines
None. `alm_duration_gap` only appears when an `asset_portfolio` is supplied, which
no golden config carries — the golden `polaris price` run emits no such key and the
QA golden suite (76) is unchanged. No baseline regenerated.
