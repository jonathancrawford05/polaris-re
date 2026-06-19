# Dev Session Log — 2026-06-19 (reserve-basis epic, slice 2b)

## Item Selected
- **Source:** CONTINUATION_reserve_basis.md (active Epic A1 — Reserve-basis
  matching) — next unchecked slice.
- **Priority:** IMPORTANT (Tier-A epic, top-ranked in
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md).
- **Title:** CRVM for Whole Life + prospective terminal-reserve artefact.
- **Slice:** 2b of 5 (slices 1, 2a complete).

## Selection Rationale
Step 5 found CONTINUATION_reserve_basis IN PROGRESS; slice 2a (PR #82) is merged,
so I continued the Epic on the designated branch with the next unchecked slice
(2b). The ACTIVE EPIC track (step 5b) mandates advancing the Epic before any
fallback pick — no fallback considered. No other CONTINUATION was IN PROGRESS as
a draft to defer.

## Decomposition Plan (multi-session)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | ReserveBasis enum + dispatch guard | ✅ Done | #81 |
| 2a | TermLife CRVM (FPT) | ✅ Done | #82 |
| 2b | WholeLife CRVM + terminal-reserve artefact | ✅ Done | (this draft) |
| 3 | VM-20 simplified (NPR floor) | ⏳ Next | — |
| 4 | Surface basis selector (CLI/API/Excel/notebook) | 🔲 Planned | — |

## What Was Done
Implemented CRVM for `WholeLife` as Full Preliminary Term valued
**prospectively to omega** — the key design choice that distinguishes this slice
from the Term case. The whole-life reserve is prospective to the end of the
mortality table, so a backward recursion seeded by the historical one-period
terminal estimate `V_T = face·q_T·v` collapses near the projection horizon
(ARCHITECTURE §4's documented limitation). Instead, CRVM builds a mortality-only
valuation grid out to omega (`_build_valuation_mortality` /
`_valuation_months_to_omega`), splits the modified net premium into a first-year
`alpha` and renewal `beta` on the equivalence principle
(`_compute_crvm_modified_premiums`), and forms the per-survivor prospective
reserve via reverse cumulative PV sums (`_compute_reserves_crvm`). The valuation
extent is independent of the projection horizon, so the reserve grades
monotonically toward face and does not collapse.

Per routine step 7b I **reproduced the artefact first**: on the golden WL block
($25.5M, 6 policies, SOA VBT 2015, 6% discount, 20y horizon) the net-premium
`reserve_balance` measured $7,171,356 (yr10) → $56,433 (yr20), reproducing the
documented $7.18M→$56k collapse exactly. Under CRVM the yr20 aggregate rises to
~$2.35M (>40×) and the per-survivor aggregate increases from yr10→yr20 — the
artefact is closed under the CRVM basis. The NET_PREMIUM path is left
byte-identical (the epic's golden constraint); closing it on the default basis
is a rebaseline-bearing follow-up that I promoted rather than smuggled in.

The 20-pay expense-allowance cap binds only for premium-paying periods < 20
years; for whole-life pay and limited-pay ≥ 20 years FPT is exact CRVM (same
reasoning as Term in 2a). Rather than ship a knowingly-uncapped reserve
mislabelled CRVM, short-pay WL **raises** `PolarisComputationError`. Implementing
the cap and the distinct 2001 CSO valuation table are deferred and promoted.

## Files Changed
- `src/polaris_re/products/whole_life.py` — CRVM dispatch; `_supported_reserve_bases`
  widened; `_compute_reserves_net_premium()` extracted (byte-identical);
  `_compute_reserves_crvm()`, `_compute_crvm_modified_premiums()`,
  `_build_valuation_mortality()`, `_valuation_months_to_omega()` added.
- `tests/test_products/test_reserve_basis_dispatch.py` — WL no longer raises on CRVM.
- `docs/DECISIONS.md` — ADR-089.
- `ARCHITECTURE.md` — §4 note on CRVM prospective-to-omega WL valuation.
- `docs/CONTINUATION_reserve_basis.md` — slice 2b DONE, slice 3 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — slice 2b SHIPPED crossout + 3 harvested
  follow-ups.

## Tests Added
- `tests/test_products/test_whole_life_crvm_reserve.py` (new, 11 tests):
  FPT identities (`0V = 0`, `12V = 0`); no-collapse + monotonicity vs the
  collapsing net-premium path; expense-allowance grading (CRVM < net premium yr1);
  convergence to face at omega; YRT NAR/ceded-premium integration; short-pay
  raises; limited-pay-20 OK; NET_PREMIUM byte-identical; valuation-q matches
  projection-q over the horizon; and the **named golden-WL acceptance test**
  pinning $7.18M→$56k and the CRVM closure.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| WL CRVM first-year reserve < NET_PREMIUM first-year reserve | ✅ | `12V = 0` < net premium; `test_crvm_below_net_premium_first_year` |
| WL terminal-reserve artefact closed/improved on golden WL block | ✅ | Closed under CRVM; yr20 ~$2.35M vs $56k (>40×); `test_golden_wl_*` |
| 20-pay expense-allowance cap applied where it binds (or TODO + flag) | ✅ | Cap binds only for pay < 20y; short-pay CRVM **raises** + flagged + promoted follow-up |
| NET_PREMIUM default unchanged (goldens byte-identical) | ✅ | QA suite 72 passed; CLI goldens 12 passed; `test_net_premium_default_unchanged` |

## Open Questions / Follow-ups
- The artefact is closed only under the **CRVM** basis; the default NET_PREMIUM
  WL reserve still collapses. Closing it on NET_PREMIUM moves goldens → needs
  ADR + rebaseline + human authorization. Promoted IMPORTANT.
- CRVM values on the **projection (best-estimate) mortality**, not 2001 CSO.
  Promoted IMPORTANT (exact statutory reproduction is the epic's purpose).
- 20-pay expense-allowance cap for short-pay WL (currently raises). Promoted
  NICE-TO-HAVE.

## Parked Polish
None.

## Impact on Golden Baselines
None. The default NET_PREMIUM path is untouched and byte-identical (QA golden
suite + CLI goldens all green). CRVM is opt-in (`reserve_basis=CRVM`) and is not
exercised by any golden. No rebaseline.

## Baseline Note
`make test` baseline this session: **1416 passed, 0 failures, 83 deselected** —
matches the recorded slice-2a baseline; no new/changed failures. Post-change:
**1426 passed, 83 deselected** (+11 new WL CRVM tests, −1 dispatch parametrize
case: the `test_whole_life_raises[CRVM]` case was removed because CRVM is now
supported for WL, mirroring slice 2a's TermLife update — not an assertion
weakened to pass).
mypy not run locally per routine (CI's job; ~207 inherited baseline errors).
