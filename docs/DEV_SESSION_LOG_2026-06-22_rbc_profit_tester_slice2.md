# Dev Session Log — 2026-06-22 (RBC ↔ RoC integration: widen `run_with_capital` to `CapitalModel`, Epic 3 Slice 2)

## Item Selected
- **Source:** `CONTINUATION_cross_jurisdiction_capital.md` (active Epic 3,
  Tier-A A3) — Slice 2; backed by `PLAN_cross_jurisdiction_capital.md`,
  `PRODUCT_DIRECTION_2026-06-18.md` IMPORTANT, and
  `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
- **Priority:** IMPORTANT
- **Title:** RBC ↔ ProfitTester integration — widen `run_with_capital` to the
  `CapitalModel` protocol + RBC ratio
- **Slice:** 2 of 4
- **Branch:** `claude/awesome-bardeen-pedp9i` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session
  designated `claude/*` branch per step 8 ENVIRONMENT OVERRIDE)

## Selection Rationale

Step 5 found `CONTINUATION_cross_jurisdiction_capital.md` IN PROGRESS, so the
active Epic 3 is the work selection (routine step 5c — the CONTINUATION IS the
selection; skip fallback). Slice 1 (PR #92, US RBC core + `CapitalModel`
protocol) is merged to `main` (`git log` shows the merge commit `c6e360c` and
PR #92 `merged_at`), so the NEXT slice (2) is unblocked. No open PRs exist, so
no review feedback to address first; no fallback item was considered — the
Epic's next slice could be advanced (guardrail: never fall back while the active
Epic can advance).

## Verify Premise (step 7b)

Reproduced before writing code. Drove `ProfitTester.run_with_capital` with an
`RBCCapital.for_product(TERM)` on a NET cash flow with reserve + NAR: it returned
a valid RoC (0.0574), `pv_capital`, and `peak_capital` — i.e. it **works at
runtime by duck typing**. But the method signature is hard-typed
`capital_model: LICATCapital` (and the internal result annotated `CapitalResult`),
so the type contract rejects RBC and **no test proved the US path**. The same
hard-typing exists on `Portfolio.run_with_capital`. The premise holds: the gap is
a type-and-test one — RoC is the primary deal metric, and until the seam is
genuinely jurisdiction-agnostic a US deal cannot be priced on a RoC basis with a
sound contract.

## Decomposition Plan (multi-session)

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | US RBC core module + `CapitalModel` / `CapitalSchedule` protocols | ✅ Done | #92 |
| 2 | Widen `ProfitTester` + `Portfolio` `run_with_capital` to `CapitalModel` | ✅ Done | #98 |
| 3 | Solvency II SCR module (`analytics/solvency2.py`) | ⏳ Next | — |
| 4 | CLI/API/Excel/dashboard `--capital {licat,rbc,solvency2}` selector + TAC/ratio surface | 🔲 Planned | — |

## What Was Done

Widened the two return-on-capital entry points — `ProfitTester.run_with_capital`
(single deal) and `Portfolio.run_with_capital` (aggregate book) — from the
concrete Canadian `LICATCapital` / `CapitalResult` annotations to the shared
`CapitalModel` / `CapitalSchedule` structural protocols introduced in Slice 1,
re-pointing the imports from `analytics.capital` to `analytics.capital_base`.
The change is **type-only**: neither method body changes a statement, because
both already depend solely on the `CapitalSchedule` surface (`required_capital`,
`pv_capital`, `pv_capital_strain`, `capital_strain`, `capital_by_period`,
`initial_capital`, `peak_capital`). Any `CapitalModel` — `LICATCapital`,
`RBCCapital`, and (Slice 3) `SolvencyIICapital` — now feeds the same RoC /
capital-strain / capital-adjusted-IRR machinery for both deals and portfolios.

`ProfitResultWithCapital` is deliberately left unchanged. RBC's
`authorized_control_level` and `rbc_ratio(tac)` (= TAC / ACL₀) live on the
`RBCResult` the model returns, reachable via `capital_model.required_capital(cf)`.
The RBC ratio needs an external Total Adjusted Capital input that `ProfitTester`
does not hold, so a result-level RBC-ratio surface is **deferred to Slice 4**
(where a TAC / target-multiple input is introduced alongside the CLI/API
selector). This keeps the jurisdiction-agnostic result from accreting
RBC-specific fields and keeps all goldens byte-identical.

The portfolio path was pulled into this slice (not left for later) because it is
the identical one-line protocol widening and shares the RoC formula; leaving it
hard-typed would have meant RBC could drive single-deal RoC but not portfolio
RoC — an inconsistent seam. Recorded as ADR-099.

## Files Changed

- `src/polaris_re/analytics/profit_test.py` — `run_with_capital` signature
  `LICATCapital → CapitalModel`, internal `CapitalResult → CapitalSchedule`;
  import re-pointed to `capital_base`; module + method docstrings generalised.
- `src/polaris_re/analytics/portfolio.py` — `run_with_capital` signature
  `LICATCapital → CapitalModel`; import re-pointed; docstrings generalised.
- `docs/DECISIONS.md` — ADR-099.
- `docs/PLAN_cross_jurisdiction_capital.md`, `docs/CONTINUATION_cross_jurisdiction_capital.md`
  — Slice 2 DONE, Slice 3 NEXT.
- `docs/DEV_SESSION_LOG_2026-06-22_rbc_profit_tester_slice2.md` — this log.

## Tests Added

- `tests/test_analytics/test_profit_test.py::TestProfitTesterWithRBCCapital` (7):
  protocol conformance (`RBCCapital` is a `CapitalModel`, schedule is a
  `CapitalSchedule`); RBC drives RoC / PV-strain / capital-adjusted IRR; RoC
  closed form against the NAIC covariance square root (`sqrt[(C1o+C3a)²+C2²]`
  for TERM defaults); RBC-ratio TAC/ACL closed form (ACL = ½ CAL, 300% position);
  LICAT and RBC feed the identical RoC formula; zero-factor RBC → `None` RoC;
  LICAT capital schedule byte-for-byte unchanged by the widening (`0.15 × NAR`).
- `tests/test_analytics/test_portfolio.py::TestPortfolioRunWithCapital::test_accepts_rbc_capital_model`:
  the aggregate RoC entry point accepts `RBCCapital`, capital matches a direct
  single-call schedule, RoC = total_pv_profits / pv_capital.

## Quality Gate

```
uv run ruff format src/ tests/      # 169 files left unchanged
uv run ruff check src/ tests/ --fix # All checks passed! (1 import-order auto-fix)
uv run pytest tests/ -m "not slow"  # 1569 passed, 94 deselected (1561 baseline + 8)
uv run pytest tests/qa/             # 72 passed
polaris price (golden_config_flat)  # exit 0; QA golden suite byte-identical
```

mypy not run locally per routine (CI's job; ~207 inherited baseline errors). The
widening narrows, not widens, the inputs accepted at the type level (concrete →
protocol the concrete already satisfies), so it introduces no new mypy errors.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `run_with_capital(RBCCapital.for_product(...))` returns RoC / strain / IRR | ✅ | deal + portfolio |
| LICAT path metrics unchanged → goldens byte-identical | ✅ | QA golden suite green; explicit regression test |
| RBC-ratio closed form (TAC / ACL) | ✅ | reachable via the schedule; closed-form test |
| `CapitalModel` accepted on both RoC entry points | ✅ | ProfitTester + Portfolio |
| Own ADR | ✅ | ADR-099 |

## Open Questions / Follow-ups

- **Held-capital basis / target multiple (carried from Slice 1).** Still open:
  should the RBC held basis be a configurable target multiple of ACL (300–400%)
  rather than fixed at CAL? Now intersects the deferred result-level RBC-ratio
  surface — both want a TAC / multiple input, naturally introduced together in
  Slice 4. Already a Promoted Follow-up in `PRODUCT_DIRECTION_2026-06-18`.
- **NAIC factor sign-off (carried from Slice 1).** Unchanged by this slice.

## Parked Polish

None. The only out-of-scope items (result-level RBC-ratio surface, Solvency II,
CLI/API selector) are all tracked planned slices (3/4) or the existing
held-capital-multiple follow-up — none are new free-floating 2nd/3rd-order
polish requiring promotion.

## Impact on Golden Baselines

None. The change is a type-only signature widening; both `run_with_capital`
bodies are unchanged and nothing in the default pricing path selects a non-LICAT
model (that is Slice 4). The QA golden suite (byte-identical pipeline/CLI checks)
passed and the golden `polaris price` run reproduced. No baseline regenerated.

## Harvest (step 17)

Harvested from this session's ADR-099 "Out of scope" and Open Questions: every
item maps to an already-tracked planned slice (Slice 3 Solvency II; Slice 4
CLI/API selector + result-level ratio surface) or the existing held-capital
target-multiple Promoted Follow-up in `PRODUCT_DIRECTION_2026-06-18`. Nothing new
to promote. Ledger healing (step 4b): PRs merged since the last session (#93–#97)
were a docs-alignment effort + docstring fix, not `PRODUCT_DIRECTION` queue
entries; PR #91's IFRS 17 Slice 3c is already struck SHIPPED; the Epic 3 parent
entry stays IN PROGRESS (correctly un-struck). Ledger healthy.

## Baseline Note

Branch `claude/awesome-bardeen-pedp9i`, cut from `main` at `1f37012` (PR #97
merge). Baseline fast suite: **1561 passed, 94 deselected** (CIA tables MISSING
from pymort as usual; SOA + CSO converted) — matches PR #92's recorded baseline,
so no NEW/CHANGED failures; proceeded per the tolerance-aware check. Post-change:
1569 passed (+8 new tests).
