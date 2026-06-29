# Dev Session Log — 2026-06-29

## Item Selected
- **Source:** CONTINUATION_asset_alm.md (active Epic — Asset/ALM model, Tier-C C0
  from COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md) — Slice 4b-3b, dashboard surface.
- **Priority:** Tier-C / C0 (active Epic; the routine advances its next unchecked
  slice before any fallback pick).
- **Title:** Dashboard asset-portfolio input + duration-gap display
- **Slice:** 4b-3b of the Asset/ALM epic
- **Branch:** claude/awesome-bardeen-8vngcl (environment-designated)

## Selection Rationale
Step 5 found the Asset/ALM CONTINUATION **IN PROGRESS** with Slice 4b-3b marked
NEXT. Step 5b confirms Asset/ALM is the single active Epic; its next slice must be
advanced before any fallback. Slice 4b-3b's dependency (4b-3a) is merged — PR #114
(`684be11 feat: ALM duration-gap sheet on the deal-pricing Excel workbook`) is on
`main`, and `list_pull_requests state=open` returned `[]`, so there is no
draft-blocked slice and no review feedback to address. Shipping the dashboard
surface is the session's deliverable; per the guardrail, no fallback item was also
picked.

Ledger healing (step 4b): the only PR merged since the prior session log is #114
(Slice 4b-3a), already recorded as DONE in the CONTINUATION — the Asset/ALM slices
are tracked in the CONTINUATION, not as PRODUCT_DIRECTION ledger entries, so there
is no crossout to heal.

## Premise Verification (step 7b)
Reproduced the gap before coding by reading `dashboard/views/pricing.py` end to
end: the Deal Pricing page has **no** asset-portfolio input and **no** duration-gap
reference anywhere (`grep` for `alm`/`duration_gap`/`asset` over the file returned
nothing), while the CLI (`_render_alm_duration_gap`), the REST API
(`/api/v1/price`), and the Excel writer (ADR-115) all surface the dual gap. Premise
holds: the dashboard is the last pricing surface blind to the asset side, and the
PR-#111 `to_dict()` carry-forward was correctly still open (the two ALM
`DealConfig` fields were absent from `to_dict()` because no dashboard surface had
consumed them yet).

## Decomposition Plan (Asset/ALM epic — surfacing tail)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 4b-1 | CLI asset-portfolio input + duration-gap output | ✅ Done | merged |
| 4b-2a | Reserve-backed Option-B liability stream + CLI rewire | ✅ Done | merged |
| 4b-2b | Reinsurer/cedant dual gap + REST API surface | ✅ Done | #113 |
| 4b-3a | ALM duration-gap sheet on the Excel workbook | ✅ Done | #114 |
| 4b-3b | **Dashboard asset-portfolio input + duration-gap display** | ✅ Done | this PR |
| 4b-4 | ALM validation notebook | 🔲 Next | — |

## What Was Done
Added an optional "Asset-Liability Duration Gap" expander to the Streamlit Deal
Pricing page: an `AssetPortfolio` JSON text area (the same `{"bonds": [...]}` shape
the CLI `deal.asset_portfolio` config accepts) plus an ALM valuation-yield number
input (0 → defer to the deal `discount_rate`, mirroring the CLI default). The
payload is `AssetPortfolio.model_validate_json`-parsed; an invalid payload shows an
error and is treated as "no asset side" so pricing never aborts.
`_run_pricing_for_cohort` gained `asset_portfolio` / `alm_valuation_yield`
parameters and, when a portfolio is supplied, calls the **same**
`dual_duration_gap(asset_portfolio, net, ceded, gap_yield,
config.effective_valuation_rate)` path the CLI/API use (ADR-113/114). The result is
stored on a new `CohortPricingData.alm_duration_gap` field and rendered by
`_render_alm_duration_gap` (reinsurer-view headline first, then cedant-view; a
`None` side omitted), mirroring the CLI Rich block's layout and labels exactly.

The surface is purely additive: with no pasted portfolio the widget returns
`(None, None)` and the page is byte-identical to its pre-ADR-116 form. The PR-#111
review-P2 carry-forward is discharged in the same slice — now that the dashboard
consumes them, `DealConfig.to_dict()` carries `asset_portfolio` /
`alm_valuation_yield` (default `None`), so the dashboard `DEFAULTS` / CLI↔Streamlit
parity surface includes them. A test locks the contract by asserting the dashboard
gap is byte-identical to a direct `dual_duration_gap` call on the cohort's own
net/ceded results — the page wires the analytics, it does not reimplement them.
Recorded as ADR-116.

## Files Changed
- `src/polaris_re/dashboard/views/pricing.py` — `AssetPortfolio` /
  `DualDurationGap` / `DurationGapResult` / `dual_duration_gap` imports;
  `CohortPricingData.alm_duration_gap` field; `asset_portfolio` /
  `alm_valuation_yield` params + dual-gap compute in `_run_pricing_for_cohort`;
  `_render_duration_gap_side` + `_render_alm_duration_gap` builders; render call in
  `_render_cohort_results`; `_asset_portfolio_input` widget wired into
  `page_pricing`.
- `src/polaris_re/core/pipeline.py` — `DealConfig.to_dict()` now emits
  `asset_portfolio` / `alm_valuation_yield` (PR-#111 carry-forward).
- `docs/DECISIONS.md` — ADR-116.
- `docs/CONTINUATION_asset_alm.md` — 4b-3b DONE, 4b-4 NEXT.
- `docs/PLAN_asset_alm.md` — 4b-3b SHIPPED, 4b-4 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — harvested follow-up.

## Tests Added
- `tests/test_dashboard/test_pricing_alm.py` — 7 tests driving
  `_run_pricing_for_cohort` directly: no portfolio → gap `None`; supplied portfolio
  → non-empty `DualDurationGap`; **byte-identical to a direct `dual_duration_gap`
  call** (wire-not-reimplement); YRT path carries cedant side only (reinsurer
  `None`); coinsurance carries both sides; explicit `alm_valuation_yield` overrides
  the discount rate; `DealConfig.to_dict()` surfaces both ALM fields.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Dashboard surfaces the ALM duration gap | ✅ | "Asset-Liability Duration Gap" expander + display |
| Reuses the CLI/API compute path (no recompute) | ✅ | byte-identical-to-`dual_duration_gap` test |
| Mirrors CLI Rich block (reinsurer headline, cedant after, labels) | ✅ | shared layout/labels |
| Additive — no asset portfolio → byte-identical page | ✅ | `(None, None)` widget default; QA dashboard flows 76 passed |
| Per-side graceful omission (YRT reinsurer side `None`) | ✅ | cedant-only block |
| PR-#111 carry-forward: `to_dict()` carries both ALM fields | ✅ | new test asserts presence + `None` default |
| Full fast suite green | ✅ | 1792 → 1799 passed (+7 new) |
| QA + golden suites green | ✅ | 76 passed; golden price output unaffected |
| ADR recorded | ✅ | ADR-116 |

## Open Questions / Follow-ups
None requiring human decision. The ALM validation notebook (4b-4) remains the
final planned epic slice in the CONTINUATION. A convenience follow-up (a
saved-portfolio / file-upload affordance for the dashboard ALM input, rather than a
per-run JSON paste) was harvested as a NICE-TO-HAVE to PRODUCT_DIRECTION_2026-06-18.

## Parked Polish
None.

## Impact on Golden Baselines
None. The golden configs supply no asset portfolio, so no run emits an ALM block
and the CLI is unchanged; `polaris price` on the golden inforce/config produced the
unchanged headline (Total PV Profits Reinsurer $45,386), and the QA golden suite
(76 passed) confirms byte-identical output.
