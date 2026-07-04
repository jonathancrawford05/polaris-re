# Dev Session Log — 2026-07-04 (reserve-basis exactness, Slice 3)

## Item Selected
- **Source:** CONTINUATION_reserve_basis_exactness.md (active Epic) — Slice 3.
- **Priority:** IMPORTANT (Reserve-Basis Exactness epic; the GAAP (FAS 60)
  concrete-basis residual, PRODUCT_DIRECTION_2026-06-18 IMPORTANT / ADR-092
  Out of scope).
- **Title:** GAAP (FAS 60) net-premium benefit reserve for TermLife.
- **Slice:** 3 of 4.
- **Branch:** `claude/loving-gauss-l0xbfn`

## Baseline
`make test` (fast) at session start: **1962 passed, 0 failures, 110 deselected**
(the Slice-2 log recorded 1940; the count is higher here because step 2's
`convert_soa_tables.py` produced the VBT/CSO CSVs, so the `requires_cso` /
`requires_soa_tables` tests ran instead of skipping — no failures either way).
QA suite 76 passed. The four CIA tables report MISSING from pymort
(known-standing, no test depends on them). No new or changed failures → PROCEED.

## Ledger Healing (step 4b)
Only PR #125 merged since the prior session log — it is Slice 2 of the active
epic (in progress), not a completed PRODUCT_DIRECTION line item, so no SHIPPED
crossout is due (same disposition as the Slice-1/2 logs). The GAAP
PRODUCT_DIRECTION IMPORTANT entry is annotated IN PROGRESS (TermLife shipped
here, WholeLife = Slice 4) rather than struck through — the item is not fully
addressed until WL GAAP lands.

## Selection Rationale
Step 5 found the active Epic's CONTINUATION IN PROGRESS with Slice 2 merged
(PR #125, verified in `git log main`). The CONTINUATION IS the work selection;
Slice 3 is NEXT and its dependency (Slice 2 merged) is satisfied, so per the
active-epic rule the session advanced Slice 3 — no fallback pick considered.

## Verify Premise (step 7b)
Reproduced before coding: `ReserveBasis.GAAP` exists in the enum and is surfaced
by the selector, but `TermLife._supported_reserve_bases` excluded it, so
`compute_reserves()` raised `PolarisComputationError` via
`BaseProduct._check_reserve_basis` — evidenced by the baseline-green
`test_reserve_basis_dispatch::test_term_raises[GAAP]` and by
`polaris price --reserve-basis GAAP` on a term block exiting on the guard.
Premise holds: GAAP was recognised but unreachable for TermLife.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `valuation_mortality` slot + CRVM/VM-20-NPR wiring (Term + WL) | ✅ Done | #124 |
| 2 | Surface end-to-end: config / CLI / API + 2001 CSO + notebook | ✅ Done | #125 |
| 3 | GAAP (FAS 60) basis for TermLife (engine + PADs + closed-form test) | ✅ Done | this PR |
| 4 | GAAP (FAS 60) for WholeLife + epic close | ⏳ Next | — |

## What Was Done
Implemented `TermLife._compute_reserves_gaap` — the US GAAP (FAS 60) net-premium
benefit reserve. FAS 60 values a traditional life reserve as a net level premium
reserve on **locked-in best-estimate assumptions plus explicit provisions for
adverse deviation (PADs)**, so the method reuses the existing net-premium
machinery (`_compute_reserves_net_premium` — the equivalence-principle level net
premium and its backward recursion) but feeds it a *margined* basis: the
projection best-estimate `q` (improvement and per-policy substandard rating
already applied by `_build_rate_arrays`) scaled by a mortality PAD and capped at
1.0, discounted at a locked-in GAAP rate (the valuation rate less an interest
PAD, floored at 0). `GAAP` is added to `TermLife._supported_reserve_bases`, so
selecting it stops raising for term.

The two PADs are new neutral-default fields on `ProjectionConfig`
(`gaap_mortality_pad = 1.0`, `ge 1.0`; `gaap_interest_margin = 0.0`, `ge 0 le 1`)
plus a `gaap_valuation_rate` property. Because both default neutral, a GAAP run
with no explicit PAD reduces **exactly** to the locked-in best-estimate net
premium reserve — the closed-form identity — and every existing config and priced
number stays byte-identical (no golden selects GAAP).

The central design boundary (carried from ADR-125/126 and the PLAN Slice-3
guardrail): **GAAP defines its own basis and does NOT inherit the statutory
static/no-improvement rule.** Unlike CRVM / VM-20 NPR, `_compute_reserves_gaap`
never reads `assumptions.valuation_mortality` and never suppresses mortality
improvement — FAS 60 locks in the best estimate (improvement included), then adds
margin. Two tests pin this. Verified end-to-end: `polaris price --reserve-basis
GAAP` on a term-only golden subset now succeeds (previously raised) and, with
neutral PADs and the flat golden assumptions, reproduces the NET_PREMIUM PV
Profits exactly (Cedant $-35,292 / Reinsurer $596). Recorded in ADR-127.

## Files Changed
- `src/polaris_re/core/projection.py` — `gaap_mortality_pad`,
  `gaap_interest_margin` fields; `gaap_valuation_rate` property.
- `src/polaris_re/products/term_life.py` — `GAAP` in `_supported_reserve_bases`;
  `compute_reserves` dispatch; `_compute_reserves_gaap`.
- `src/polaris_re/products/base_product.py` — refreshed the guard message (GAAP
  now implemented for TermLife, not yet WholeLife).
- `tests/test_products/test_term_gaap_reserve.py` — new (12 tests).
- `tests/test_products/test_reserve_basis_dispatch.py` — GAAP moves off the
  TermLife unimplemented list; the error-message test exercises WholeLife.
- `tests/test_api/test_reserve_basis.py` — the unsupported-basis 422 test uses a
  WHOLE_LIFE policy (TermLife GAAP now succeeds).
- `docs/DECISIONS.md` — ADR-127.
- `docs/CONTINUATION_reserve_basis_exactness.md` — Slice 3 → DONE, Slice 4 → NEXT.
- `docs/PLAN_reserve_basis_exactness.md` — status; Slice 3 → DONE, Slice 4 → NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — GAAP item annotated IN PROGRESS;
  3 promoted follow-ups (ADR-127).
- `docs/DEV_SESSION_LOG_2026-07-04_reserve_basis_exactness_slice3.md` — this log.

## Tests Added
`tests/test_products/test_term_gaap_reserve.py` (12 tests):
- GAAP is supported and produces a real reserve.
- Neutral PADs equal NET_PREMIUM to 1e-9 (with and without a configured
  improvement scale) — the closed-form identity.
- A mortality PAD (1.10) and an interest margin (0.01) each raise the
  accumulation-phase reserve; reserve monotonic non-decreasing in the mortality
  PAD (parametrised).
- Independent numpy recomputation of the FAS 60 net premium reserve on the
  PAD-adjusted basis (pad 1.15, margin 0.0075) reproduces the engine reserve
  to 1e-10.
- GUARDRAIL: GAAP ignores `valuation_mortality` (byte-identical under a 2×
  prescribed table); GAAP reflects mortality improvement (moves under Scale AA).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `GAAP` selectable for TermLife (no longer raises) | ✅ | `_supported_reserve_bases`; CLI `--reserve-basis GAAP` on a term block exits 0 |
| FAS 60 = net premium reserve on locked-in best-estimate + PADs | ✅ | `_compute_reserves_gaap` reuses `_compute_reserves_net_premium` on the margined basis |
| Neutral PADs collapse to the locked-in best-estimate NPR | ✅ | identity test (with/without improvement); CLI PV equals NET_PREMIUM |
| Mortality PAD / interest margin raise the reserve | ✅ | direction + monotonicity tests |
| Closed-form independent recomputation matches to 1e-10 | ✅ | `test_independent_recomputation` |
| GUARDRAIL: GAAP ignores `valuation_mortality`, keeps improvement | ✅ | two guardrail tests |
| Byte-identical goldens (GAAP unset everywhere) | ✅ | full fast suite 1973/1 skip; QA 76; golden `flat` unchanged |

## Open Questions / Follow-ups
- **Deal-path PAD surfacing** (`DealConfig` / CLI flags / REST API) — the two
  PADs live on `ProjectionConfig` this slice; a CLI/API user gets GAAP only at
  neutral PADs until they are surfaced. Promoted IMPORTANT (ADR-127 Out of
  scope, 1st-order) — mirrors the `valuation_mortality` ADR-125→126 surfacing
  slice.
- **FAS 60 DAC amortisation + loss-recognition test** and **duration-varying PAD
  structures** — promoted NICE-TO-HAVE (ADR-127 Out of scope, 2nd-order).
- Successor COMMERCIAL_VIABILITY_REVIEW still due ~2026-07-18 (carried from the
  Slice-1/2 logs): the 2026-06-18 review's epic queue is exhausted, so the epic
  after Reserve-Basis Exactness has no ranked source — regenerate at the 30-day
  mark (or earlier if this epic finishes at Slice 4 first).

## Parked Polish
None. All three harvested items are 1st- or 2nd-order follow-ups of the
originally-planned Slice-3 GAAP work and were promoted per the ORDER cap
(1st-order → IMPORTANT/NICE-TO-HAVE as classified; 2nd-order → NICE-TO-HAVE).
No 3rd-order-or-deeper follow-ups surfaced.

## Impact on Golden Baselines
None — `gaap_mortality_pad` / `gaap_interest_margin` default neutral and no
golden config selects GAAP, so every priced number is byte-identical. Golden
`flat` unchanged; QA suite 76 green. No baseline regeneration.
