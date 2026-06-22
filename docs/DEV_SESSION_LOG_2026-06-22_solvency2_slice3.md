# Dev Session Log — 2026-06-22 (EU Solvency II SCR module, Epic 3 Slice 3)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 3; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** EU Solvency II SCR module (`analytics/solvency2.py`)
- **Slice:** 3 of 4
- **Branch:** `claude/awesome-bardeen-ed43mz` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 IS the work selection (routine step 5c — the CONTINUATION is the
selection; skip fallback). Slice 2 (PR #98, RoC entry points widened to the
`CapitalModel` protocol) is merged to `main` (`git log` shows merge commit
`f7c57d5`, the branch HEAD), so the NEXT slice (3) is unblocked. No open PRs to
address first; no fallback considered — the guardrail forbids falling back while
the active Epic's next slice can advance, and it can.

## Verify Premise (step 7b)

Reproduced before writing code: `analytics/` has `capital.py` (LICAT) and
`rbc.py` (US RBC) but **no** Solvency II module (`ls`/`grep` confirm); the only
`solvency2` references in the tree are two tests that assert the string is
*rejected* at the CLI (`exit 1`) and API (`422`) boundaries — i.e. the EU
jurisdiction genuinely cannot be priced today, and the surface deliberately
rejects it until the Slice 4 selector lands. The premise holds: the gap is a
missing calculator, and this slice adds it without touching the CLI/API surface
(those two rejection tests stay green).

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ✅ Done | (this PR) |
| 4 | CLI/API/Excel/dashboard `--capital {licat,rbc,solvency2}` selector + ratio surface | ⏳ Next | — |

## What Was Done

Added `analytics/solvency2.py` implementing the EU Solvency II **standard-formula**
SCR as the third regulatory-capital sibling of `LICATCapital` (Canada) and
`RBCCapital` (US), all three satisfying the shared `CapitalModel` /
`CapitalSchedule` protocols from Slice 1. Like LICAT and RBC it is a
factor-based committee-stage calculator: each risk sub-module is
`factor * exposure` per projection month, with conservative, documented,
per-product default factors the caller can override.

The genuine structural difference from RBC is the aggregation. Solvency II builds
the SCR bottom-up through **two correlation-matrix** aggregations, not the single
covariance pair RBC uses: the life-underwriting sub-modules (mortality, lapse,
catastrophe) aggregate via `LIFE_CORRELATION` into a life SCR; that, with market
and counterparty-default risk, aggregates via `TOP_LEVEL_CORRELATION` into the
Basic SCR (BSCR); operational risk adds linearly outside the matrix
(`SCR = BSCR + Op`). Both aggregations use the standard-formula quadratic-form
square root `sqrt(rᵀ·Corr·r)`, evaluated per period via a single `einsum` over
the component index (vectorised, no per-period loop). The two correlation
matrices are the Commission Delegated Regulation (EU) 2015/35 Annex IV values,
held in documented module constants. A cost-of-capital risk margin
(`risk_margin`, regulatory CoC 6%) applies `RM = CoC · PV(future SCR)`.

The catastrophe default (0.0015 of NAR) is the citable standard-formula life-CAT
shock (+1.5‰ of capital-at-risk for one year); the remaining factors are
committee-stage placeholders pending the shock-based Asset/ALM calibration,
exactly the disposition LICAT/RBC use. Recorded as ADR-100. The module is wired
into nothing in the pricing path — the `--capital solvency2` selector is Slice 4 —
so goldens are byte-identical and the existing CLI/API rejection tests stay green.

## Files Changed

- `src/polaris_re/analytics/solvency2.py` — new module (`SolvencyIIFactors`,
  `SolvencyIIResult`, `SolvencyIICapital`, `LIFE_CORRELATION`,
  `TOP_LEVEL_CORRELATION`, `_correlation_aggregate`).
- `src/polaris_re/analytics/__init__.py` — export `SolvencyIICapital`,
  `SolvencyIIFactors`, `SolvencyIIResult` (+ `__all__`).
- `docs/DECISIONS.md` — ADR-100.
- `docs/PLAN_cross_jurisdiction_capital.md`,
  `docs/CONTINUATION_cross_jurisdiction_capital.md` — Slice 3 DONE, Slice 4 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — two harvested Promoted Follow-ups.
- `docs/DEV_SESSION_LOG_2026-06-22_solvency2_slice3.md` — this log.

## Tests Added

- `tests/test_analytics/test_solvency2.py` (34): default & per-product factors,
  frozen-model guard; correlation matrices symmetric / unit-diagonal / documented
  off-diagonals; **life SCR closed form** `sqrt(m²+l²+c²+0.5·m·c+0.5·l·c)`;
  **BSCR closed form** `sqrt(M²+D²+L²+0.5·(MD+ML+DL))`; operational adds linearly
  outside BSCR; diversification credit (aggregate < linear sum); risk-margin CoC
  closed form + linearity + empty case; `pv_capital` / `capital_strain` /
  `pv_capital_strain` against manual discount; CEDED rejection, NAR resolution /
  override / length-mismatch guards; empty projection; `SolvencyIICapital` /
  `SolvencyIIResult` satisfy `CapitalModel` / `CapitalSchedule`; SCR differs from
  LICAT on the same block.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `SolvencyIICapital.required_capital(...)` returns an SCR schedule | ✅ | deal-level; satisfies `CapitalSchedule` |
| Correlation-matrix BSCR aggregation `sqrt(rᵀ·Corr·r)` | ✅ | two-level (life + top), einsum-vectorised |
| Closed-form correlation-aggregation test | ✅ | life SCR + BSCR worked forms |
| Cost-of-capital risk margin | ✅ | `risk_margin`, CoC 6%, closed-form test |
| Satisfies `CapitalModel` / `CapitalSchedule` | ✅ | isinstance tests |
| Own ADR | ✅ | ADR-100 |
| Goldens byte-identical | ✅ | new module, nothing wired into pricing |

## Open Questions / Follow-ups

- **Slice 4 must flip two existing rejection tests.**
  `test_cli.py::test_capital_invalid_value_exits_non_zero` and
  `test_main.py::test_price_capital_model_invalid_value_returns_422` use
  `solvency2` as the *unknown* value today; Slice 4 (which adds the selector)
  changes that surface contract, so those two tests move to a still-unknown id
  and gain acceptance tests for `rbc`/`solvency2`. Flagged in the CONTINUATION
  "Context for Next Session" so the surface change is not a surprise.
- **Additional SII sub-modules** (longevity / expense / revision / disability;
  health / non-life) — promoted as a NICE-TO-HAVE follow-up.
- **Result-level solvency-ratio surface** (own funds / SCR) — promoted; lands in
  Slice 4 with the external own-funds input (alongside the deferred RBC ratio).

## Parked Polish

None. All out-of-scope items map to the planned Slice 4, the existing
held-capital-multiple follow-up, or the two freshly-promoted 1st-order
NICE-TO-HAVE follow-ups — none are 3rd-order polish requiring parking.

## Impact on Golden Baselines

None. `solvency2.py` is a new additive module wired into nothing in the default
pricing path; the `--capital solvency2` selector is Slice 4. The golden
`polaris price` run reproduced byte-identical and the QA golden suite passed. No
baseline regenerated.

## Harvest (step 17)

Harvested from this session's ADR-100 "Out of scope": the additional SII
sub-modules and the result-level solvency-ratio surface are genuinely new
follow-ups → promoted as NICE-TO-HAVE (1st-order) to
`PRODUCT_DIRECTION_2026-06-18` Promoted Follow-ups. The remaining out-of-scope
items (CLI/API selector, shock-based calibration) map to the planned Slice 4 and
the existing C0 Asset/ALM epic respectively — already tracked, not re-promoted.
Ledger healing (step 4b): PR #98 (Slice 2) merged since the last session is the
Epic 3 parent, which stays IN PROGRESS (correctly un-struck); it is not a
discrete PRODUCT_DIRECTION queue entry to strike. Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-ed43mz`, HEAD at `f7c57d5` (PR #98 merge).
Baseline fast suite: **1569 passed, 94 deselected** (CIA tables MISSING from
pymort as usual; SOA + CSO converted) — matches the prior session's recorded
post-change count, so no NEW/CHANGED failures; proceeded per the tolerance-aware
check. Post-change: 1603 passed (+34 new tests).
