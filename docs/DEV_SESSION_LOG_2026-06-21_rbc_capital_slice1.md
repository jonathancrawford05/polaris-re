# Dev Session Log — 2026-06-21 (US RBC capital core + `CapitalModel` protocol, Epic 3 Slice 1)

## Item Selected
- **Source:** `docs/PLAN_cross_jurisdiction_capital.md` (new Epic 3, Tier-A A3)
  — Slice 1; backed by `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT
  "Cross-jurisdiction regulatory capital (US RBC + Solvency II)" and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT (restored from 2026-04-19 BLOCKER)
- **Title:** US NAIC Life RBC core module + shared `CapitalModel` protocol
- **Slice:** 1 of 4 (starts Epic 3)
- **Branch:** `claude/awesome-bardeen-kp19mp` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session
  designated `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found **no** IN PROGRESS CONTINUATION (all nine are COMPLETE — Epic 1
Reserve-basis and Epic 2 IFRS 17 movement both closed, the latter this morning
via PRs #87–#91). Step 5b therefore applies: the routine must always have
exactly one active Epic, and none was active, so the session's deliverable is to
**start the next Tier-A epic** (PLAN + Slice 1) rather than pick fallback work.

The next unstarted Tier-A item is **A3 — Cross-jurisdiction capital (US RBC +
Solvency II)**: Epics 1 (A1) and 2 (A2) shipped, A3 is next in the CVR's
recommended sequence (§4) and is a market-access gate (the engine cannot quote a
US deal on a return-on-capital basis today — confirmed in Verify Premise). The
CVR is 3 days old (not stale, no regeneration needed). No fallback item was
considered — starting the Epic is the mandated deliverable.

## Verify Premise (step 7b)

Reproduced before writing code. `grep -rli "rbc|risk.based.capital|solvency.ii|
authorized.control" src/polaris_re/` returns nothing — the only regulatory
capital module is `LICATCapital` (Canada/OSFI). `ProfitTester.run_with_capital`
is hard-typed to the concrete `LICATCapital`. The gap is real: there is no US
RBC anywhere, so a US deal cannot be evaluated on a return-on-capital basis. The
slice is not a no-op.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core (`rbc.py`) + `CapitalModel`/`CapitalSchedule` protocols (`capital_base.py`) | ✅ Done | #92 |
| 2 | Generalise `run_with_capital` to the `CapitalModel` protocol + RBC ratio surface | ⏳ Next | — |
| 3 | Solvency II SCR module (`solvency2.py`) — correlation-matrix BSCR + risk margin | 🔲 Planned | — |
| 4 | CLI/API/Excel/dashboard `--capital {licat,rbc,solvency2}` selector + validation notebook | 🔲 Planned | — |

Full plan in `docs/PLAN_cross_jurisdiction_capital.md`; running state in
`docs/CONTINUATION_cross_jurisdiction_capital.md`.

## What Was Done

Added two new analytics modules. `analytics/capital_base.py` defines the
jurisdiction-agnostic `CapitalModel` and `CapitalSchedule` structural
`Protocol`s — the calculator/result contract that `LICATCapital` /
`CapitalResult` already satisfy — plus two small shared helpers
(`discount_stream`, `strain_of`) that factor out the discounting and
period-over-period-change arithmetic every schedule needs. Because the protocols
are structural (PEP 544), the pre-existing LICAT classes conform with **no
modification** (locked by `isinstance` tests), and future siblings only match
the shape.

`analytics/rbc.py` implements the US NAIC Life RBC standard as the US analogue of
`LICATCapital`: `RBCFactors` (the nine C-0…C-4 component factors), `RBCResult`
(component arrays + the covariance aggregate + ACL/CAL + `rbc_ratio`), and the
`RBCCapital` calculator. Each component is `factor * exposure` per month — C-2
(insurance risk) on NAR, the rest on `reserve_balance` — and they aggregate via
the NAIC **covariance square root**
(`C0 + C4a + sqrt[(C1o+C3a)² + C1cs² + C2² + C3b² + C3c² + C4b²]`), not a simple
sum. `capital_by_period` is the Company Action Level (the held-capital basis fed
to RoC); `authorized_control_level` (= ½ CAL) is the RBC-ratio denominator.
`for_product` selects NAIC-order committee factors per product (C-1o 1.0%, C-2
0.00150 of NAR, C-3 Phase I categories by product); the remaining components are
overridable zero stubs pending the Asset/ALM epic.

The work is purely additive — both new modules are imported by nothing in the
pricing path, and `LICATCapital` / `CapitalResult` are untouched — so all
goldens are byte-identical (QA golden suite green, no rebaseline). ADR-098.

## Files Changed
- `src/polaris_re/analytics/capital_base.py` — NEW: `CapitalModel` /
  `CapitalSchedule` protocols + `discount_stream` / `strain_of` helpers.
- `src/polaris_re/analytics/rbc.py` — NEW: `RBCFactors`, `RBCResult`,
  `RBCCapital`.
- `src/polaris_re/analytics/__init__.py` — export the five new names.
- `docs/DECISIONS.md` — ADR-098.
- `docs/PLAN_cross_jurisdiction_capital.md` — NEW: the Epic 3 plan.
- `docs/CONTINUATION_cross_jurisdiction_capital.md` — NEW: Slice 1 DONE,
  Status IN PROGRESS.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — ledger healing (struck through the
  shipped IFRS 17 movement IMPORTANT entry, Epic 2 / PRs #87–#91); harvested the
  configurable-ACL-multiple follow-up.

## Tests Added
- `tests/test_analytics/test_rbc.py` (33 tests): factor validation / freeze;
  per-product factor schedule (parametrized over all six product types);
  **covariance closed form** (default factor set `sqrt[(C1o+C3a)² + C2²]` and
  the full nine-component formula); `ACL = ½ CAL`; the linear
  (no-diversification) effect of C-0 / C-4a outside the root; `pv_capital` /
  `capital_strain` / `pv_capital_strain` against a manual discount; the RBC-ratio
  closed form and its zero-ACL guard; CEDED rejection; NAR resolution, override
  precedence, and length-mismatch validation; NET-basis acceptance; empty
  projection; **both `RBCResult` and the unmodified `CapitalResult` satisfy
  `CapitalSchedule`, and both calculators satisfy `CapitalModel`**; and a
  jurisdiction-difference test (RBC ≠ LICAT on the same block).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| US RBC module exists with C-0…C-4 components | ✅ | `analytics/rbc.py` |
| NAIC covariance aggregation (not a sum) | ✅ | closed-form test |
| ACL / CAL + RBC ratio exposed | ✅ | `authorized_control_level`, `rbc_ratio` |
| Shared `CapitalModel` protocol LICAT also satisfies | ✅ | `isinstance` tests on both |
| Per-product factor defaults | ✅ | `for_product`, parametrized test |
| Goldens byte-identical (nothing wired into pricing) | ✅ | QA golden suite green, no rebaseline |
| Full fast suite green | ✅ | 1561 passed (1528 baseline + 33), 94 deselected |

## Open Questions / Follow-ups
- **Configurable held-capital basis (target multiple of ACL).** Slice 1 fixes
  the RBC held basis at Company Action Level (2× ACL). Reinsurers commonly hold
  300–400% of ACL — a configurable multiple would make the RoC denominator
  reflect a real capital target. Promoted NICE-TO-HAVE (1st-order); design
  resolved in Slice 2/4.
- **NAIC factor calibration sign-off.** The committee-stage NAIC factors (C-2
  0.00150 of NAR, C-3 Phase I categories, C-1o 1.0%) are approximations pending
  the Asset/ALM epic — same disposition as the LICAT factors. Confirmation, not
  a work item.
- **Slice 2 is a signature widening.** `run_with_capital` already only uses the
  `CapitalSchedule` surface, so widening its `capital_model` type hint from
  `LICATCapital` to `CapitalModel` (and re-pointing the import) is the bulk of
  Slice 2; verify the existing LICAT RoC tests stay byte-identical.

## Parked Polish
None. (No 3rd-order-or-deeper follow-ups surfaced this session. The 2021+ NAIC
designation-based bond factors and C-3 Phase II stochastic requirement are
Asset/ALM-epic work, already tracked as CVR Tier C0 — not newly surfaced here.)

## Impact on Golden Baselines
None. Both new modules are imported by nothing in the pricing path and the LICAT
classes are untouched; the golden CLI/pipeline QA suite is green with no
rebaseline.
