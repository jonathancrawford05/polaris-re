# Dev Session Log — 2026-07-04 (reserve-basis exactness, Slice 4)

## Item Selected
- **Source:** CONTINUATION_reserve_basis_exactness.md (active Epic) — Slice 4.
- **Priority:** IMPORTANT (Reserve-Basis Exactness epic; the GAAP (FAS 60)
  concrete-basis residual for WholeLife — PRODUCT_DIRECTION_2026-06-18 IMPORTANT /
  ADR-092 Out of scope).
- **Title:** GAAP (FAS 60) net level premium benefit reserve for WholeLife + epic close.
- **Slice:** 4 of 4 (final — epic COMPLETE).
- **Branch:** `claude/loving-gauss-eitwhz`

## Baseline
`make test` (fast) at session start: **1973 passed, 1 skipped, 110 deselected**
— identical to the Slice-3 log's recorded baseline. QA suite not re-run at
baseline (run in the quality gate). The four CIA tables report MISSING from
pymort (known-standing; no test depends on them). 2001 CSO + VBT CSVs produced
OK by step 2. No new or changed failures vs the recorded baseline → PROCEED.

## Ledger Healing (step 4b)
Only PR #126 merged since the prior session log — it is Slice 3 of the active
epic (GAAP for TermLife, ADR-127), not a completed PRODUCT_DIRECTION line item,
so no SHIPPED crossout is due (same disposition as the Slice-1/2/3 logs). The
GAAP PRODUCT_DIRECTION IMPORTANT entry is re-annotated "ADDRESSED in draft,
pending merge" (both Term and WL GAAP now ship; the epic is COMPLETE) rather than
struck through — the strike-through is the ledger-healing job of the next session
once this Slice-4 draft PR merges to main.

## Selection Rationale
Step 5 found the active Epic's CONTINUATION IN PROGRESS with Slice 3 merged
(PR #126, verified in `git log origin/main` — 512b41a). The CONTINUATION IS the
work selection; Slice 4 was NEXT and its dependency (Slice 3 merged) satisfied,
so per the active-epic rule the session advanced Slice 4 — no fallback pick
considered. This is the epic's final slice.

## Verify Premise (step 7b)
Reproduced before coding: `ReserveBasis.GAAP` is surfaced by the selector but
`WholeLife._supported_reserve_bases` excluded it, so `compute_reserves()` raised
`PolarisComputationError` via `BaseProduct._check_reserve_basis`. Confirmed by
the baseline-green `test_reserve_basis_dispatch::test_whole_life_raises[GAAP]`
and `test_error_message_names_supported_basis` (both exercised WL GAAP). Premise
holds: GAAP was recognised but unreachable for WholeLife.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `valuation_mortality` slot + CRVM/VM-20-NPR wiring (Term + WL) | ✅ Done | #124 |
| 2 | Surface end-to-end: config / CLI / API + 2001 CSO + notebook | ✅ Done | #125 |
| 3 | GAAP (FAS 60) basis for TermLife (engine + PADs + closed-form test) | ✅ Done | #126 |
| 4 | GAAP (FAS 60) for WholeLife + epic close | ✅ Done | this PR |

## What Was Done
Implemented `WholeLife._compute_reserves_gaap` — the US GAAP (FAS 60) net
**level** premium benefit reserve. Like the Slice-3 TermLife GAAP (ADR-127) it is
a net premium reserve on a **margined best-estimate basis** (projection q ×
`gaap_mortality_pad`, capped at 1.0, discounted at
`ProjectionConfig.gaap_valuation_rate` = valuation rate − `gaap_interest_margin`,
floored at 0), reusing the two neutral-default PAD knobs added in Slice 3. Unlike
TermLife (a finite-horizon backward recursion with terminal `V_T = 0`), the WL
GAAP reserve is valued **prospectively to omega** — the same to-omega valuation
grid (`_valuation_months_to_omega`, `_build_valuation_mortality`) the CRVM /
VM-20 paths use — so it does not collapse at the projection horizon the way the
WL net-premium one-period terminal estimate does (the ADR-089 artefact). The
premium is a single net **level** valuation premium `P = APV(benefits to omega) /
APV(premium annuity)`, funding the to-omega benefit over the premium-paying
window; the FPT alpha/beta split of CRVM is a statutory expense-allowance device,
not a GAAP one. The prospective reserve reuses the same reverse-cumsum machinery
as `_compute_reserves_crvm`.

`GAAP` was added to `WholeLife._supported_reserve_bases`, so selecting it stops
raising for whole life. With both PADs neutral, WL GAAP reduces to the locked-in
best-estimate net level premium reserve valued to omega — verified against an
independent numpy recomputation (whole-life pay, limited pay, and a PAD-adjusted
basis) to 1e-9. Because no golden config selects GAAP and the PADs default
neutral, every existing priced number is byte-identical.

**Guardrail (carried from ADR-127):** WL GAAP does **not** read
`assumptions.valuation_mortality` (it passes `table=None`, the projection table)
— FAS 60 is a best-estimate + PAD basis, not a prescribed static statutory one. A
test pins that a 2× prescribed valuation table does not move WL GAAP. Note WL does
not model mortality improvement on any basis, so — unlike TermLife GAAP — there is
no improvement half to the guardrail here; that pre-existing WL-wide gap is
harvested as an IMPORTANT follow-up.

The `test_reserve_basis_dispatch` and `test_api/test_reserve_basis` GAAP-raises
cases moved off WholeLife (which now implements every basis) to UniversalLife
(NET_PREMIUM only); a new API test pins that WL GAAP now prices successfully and
echoes the basis. This slice closes the Reserve-Basis Exactness epic — all four
bases (NET_PREMIUM / CRVM / VM-20 / GAAP) now compute for Term and Whole Life.
Recorded in ADR-128; CONTINUATION → COMPLETE (after HARVEST).

## Files Changed
- `src/polaris_re/products/whole_life.py` — `GAAP` in `_supported_reserve_bases`;
  `compute_reserves` dispatch; `_compute_reserves_gaap`.
- `src/polaris_re/products/base_product.py` — refreshed the guard message (GAAP
  now implemented for both Term and WL; other engines NET_PREMIUM only).
- `src/polaris_re/core/reserve_basis.py` — enum docstring (GAAP implemented for
  Term and WL).
- `tests/test_products/test_wl_gaap_reserve.py` — new (13 tests).
- `tests/test_products/test_reserve_basis_dispatch.py` — WL GAAP off the
  unimplemented list; guard-message test moved to UniversalLife.
- `tests/test_api/test_reserve_basis.py` — new WL-GAAP-succeeds test; the
  unsupported-basis 422 test moved to a UNIVERSAL_LIFE policy.
- `ARCHITECTURE.md` — GAAP for WL; epic-complete note.
- `notebooks/02_reserve_basis_comparison.ipynb` — §5c (GAAP with PADs) + intro.
- `docs/DECISIONS.md` — ADR-128.
- `docs/CONTINUATION_reserve_basis_exactness.md` — Slice 4 → DONE, Status → COMPLETE.
- `docs/PLAN_reserve_basis_exactness.md` — status; Slice 4 → DONE.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — GAAP item ADDRESSED-in-draft;
  GAAP-PAD item now covers both products; two promoted follow-ups (WL improvement
  gap, next-epic constitution).
- `docs/DEV_SESSION_LOG_2026-07-04_reserve_basis_exactness_slice4.md` — this log.

## Tests Added
`tests/test_products/test_wl_gaap_reserve.py` (17 tests):
- GAAP supported (whole-life pay and limited-pay) and produces a real reserve.
- Closed form — neutral-PAD, PAD-adjusted (pad 1.15, margin 0.0075), and
  limited-pay (20-pay) reserves each reproduce an independent numpy recomputation
  of the net-level-premium-to-omega reserve. Per the PR #127 review (P2), the
  recomputation uses a **different reserve formulation** than the engine (a
  per-survivor backward recursion vs the engine's reverse-cumulative-PV), so it
  catches a shared conceptual error rather than a transcription slip; the two
  agree to ~2e-9 (checked at 1e-8).
- Equivalence-principle identity (formulation-independent): the reserve at issue
  is zero, `V_0 = APV(benefits) - P*APV(annuity) = 0`, for neutral and padded
  bases (parametrised).
- GAAP differs materially from WL NET_PREMIUM at the horizon edge (to-omega vs
  one-period terminal).
- A mortality PAD (1.10) and an interest margin (0.01) each raise the
  accumulation-phase reserve; reserve monotonic non-decreasing in the mortality
  PAD at month 120 (parametrised).
- GUARDRAIL: WL GAAP ignores `valuation_mortality` (byte-identical under a 2×
  prescribed table).

## Post-Review Update (PR #127 review P2)
The automated review APPROVED (zero P0/P1). Its one finding — the closed-form
test mirrored the engine's reverse-cumsum machinery, so it caught transcription
slips but not a shared conceptual error — was addressed in a follow-up commit:
the test's reserve recomputation was switched to an independent backward
recursion, and a formulation-independent equivalence-principle identity
(`V_0 = 0` at issue) was added. Test-only change; goldens untouched.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `GAAP` selectable for WholeLife (no longer raises) | ✅ | `_supported_reserve_bases`; API WL GAAP returns 200 + echoes basis |
| FAS 60 = net LEVEL premium reserve on locked-in best-estimate + PADs, to omega | ✅ | `_compute_reserves_gaap` (single level P, prospective-to-omega reserve) |
| Neutral PADs = locked-in best-estimate net-level-to-omega reserve | ✅ | independent numpy recomputation (3 cases) to 1e-9 |
| Does not collapse at the horizon edge (unlike WL NET_PREMIUM) | ✅ | to-omega valuation; `test_gaap_differs_from_net_premium` |
| Mortality PAD / interest margin raise the reserve | ✅ | direction + monotonicity tests |
| GUARDRAIL: GAAP ignores `valuation_mortality` | ✅ | valuation-table-independence test |
| Byte-identical goldens (GAAP unset everywhere) | ✅ | full fast suite green; QA 76; golden `flat` unchanged |
| Epic close: all 4 bases for Term + WL; CONTINUATION COMPLETE | ✅ | HARVEST run first, then Status → COMPLETE |

## Open Questions / Follow-ups
- **WholeLife does not model mortality improvement on any basis.** Surfaced by the
  Slice-4 guardrail asymmetry: `WholeLife._build_rate_arrays` never reads
  `AssumptionSet.improvement`, so a WL block priced with an improvement scale
  silently ignores it (all WL bases + projection cash flows). Pre-existing,
  WL-wide, not GAAP-specific. Promoted IMPORTANT (ADR-128 Out of scope, 1st-order).
- **Next Tier-A epic has no ranked source.** The Reserve-Basis Exactness epic is
  COMPLETE and the COMMERCIAL_VIABILITY_REVIEW_2026-06-18 Tier-A ladder is
  exhausted; the review turns 30 days old ~2026-07-18 (step 6 regeneration
  trigger). The next daily-dev run (step 5b) must constitute a new epic from the
  highest-value promoted follow-ups (prescribed statutory valuation-interest
  helper, GAAP-PAD deal-path surfacing, WL improvement) or regenerate the
  viability review as the session deliverable. Promoted NICE-TO-HAVE (process).
- Deal-path PAD surfacing (`DealConfig` / CLI / API) remains the ADR-127 IMPORTANT
  follow-up, now covering both products (updated in place in PRODUCT_DIRECTION).

## Parked Polish
None. Both harvested items are 1st-order follow-ups of the originally-planned
Slice-4 WL GAAP work (the WL improvement gap surfaced by the guardrail asymmetry;
the next-epic-constitution note by the epic close). No 3rd-order-or-deeper
follow-ups surfaced.

## Impact on Golden Baselines
None — `gaap_mortality_pad` / `gaap_interest_margin` default neutral and no golden
config selects GAAP, so every priced number is byte-identical. Golden `flat`
unchanged; QA suite green. No baseline regeneration.
