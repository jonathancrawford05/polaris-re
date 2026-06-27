# Dev Session Log — 2026-06-27

## Item Selected
- **Source:** CONTINUATION_asset_alm.md (active Epic 4 — Asset / ALM model,
  Tier-C C0 from COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md; ROADMAP 5.4) —
  Slice 2.
- **Priority:** Active Epic (advanced before any fallback, per routine step 5b).
- **Title:** Asset / ALM model — Slice 2: investment income + duration / convexity.
- **Slice:** 2 of 4.
- **Branch:** claude/awesome-bardeen-hecrn1 (environment-designated).

## Selection Rationale
Step 5 found the Asset/ALM CONTINUATION **IN PROGRESS** with Slice 2 marked
NEXT and Slice 1's PR (#107) **merged** (confirmed: `dd3b9d2` is on `origin/main`
after fetch; the local `origin/main` ref was merely stale). The CONTINUATION's
next slice IS the work selection (step 5c) — no fallback item picked, per the
one-active-Epic guardrail. No open PRs (`list_pull_requests` state=open → []),
so no review feedback to address and no draft-blocked epic. Ledger: PR #107 was
already crossed-out/recorded by the Slice 1 session; nothing to heal.

## Premise Verification (step 7b)
Reproduced before coding that the Slice 2 surface did not yet exist: `grep` for
`book_yield|investment_income|macaulay|modified_duration|convexity` in
`core/asset.py` matched only a docstring forward-reference — no methods.
Premise holds.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Bond cash-flow model + `AssetPortfolio` (pricing) | ✅ Done | #107 |
| 2 | Investment income + book yield + duration / convexity | ✅ Done | this PR |
| 3 | Modco integration (asset-driven modco interest) | ⏳ Next | — |
| 4 | `analytics/alm.py` duration gap + CLI/API/dashboard/Excel surfacing | 🔲 Planned | — |

## What Was Done
Advanced Epic 4 by shipping Slice 2 — the asset *measures* the rest of the epic
consumes. Extended `AssetPortfolio` (in `core/asset.py`) with four methods, all
purely additive (nothing wired into any product/treaty/pricing path, so goldens
are byte-identical):

- **`book_yield() -> float | None`** — the gross effective-annual IRR of the
  total carrying value vs the portfolio's projected cash flows, solved with
  `scipy.optimize.brentq` over `[-0.99, 100.0]` (the same solver/bracket as
  `ProfitTester.irr`), returning `None` on no sign change. A flat scalar, per
  the maintainer-confirmed design (PLAN §5). This is the number Slice 3 hands to
  the Modco treaty (Option A precedence over the flat `modco_interest_rate`).
- **`investment_income(reserve_vector, annual_yield=None)`** — `reserve · y / 12`
  per month, where `y` is the supplied yield or `book_yield()`; raises
  `PolarisComputationError` when no yield is supplied and the book yield is
  unrecoverable. This is the modco-interest stream Slice 3 needs.
- **`macaulay_duration(y)` / `modified_duration(y)` / `convexity(y)`** — the
  PV-weighted average time and its sensitivities, discounting the aggregate
  cash-flow vector on the engine convention (`v=(1+y)^(-1/12)`) but expressing
  time in **years** (`τ=t/12`) so the textbook forms hold under the
  effective-annual yield: Macaulay `=Στ·PV/ΣPV`, modified `=Macaulay/(1+y)`,
  convexity `=Στ(τ+1)PV/(P(1+y)²)`. Zero-bond reductions: duration `=N`,
  convexity `=N(N+1)/(1+y)²`.

ADR-109 records the decision (book-yield definition, the time-in-years
convention and its zero-bond closed forms, and the deferred net-of-spread /
time-varying earned-rate follow-ups). The load-bearing carry-forward for Slice 3
is that `book_yield()` is a single scalar consumed by the modco-interest calc.

## Files Changed
- `src/polaris_re/core/asset.py` — extended `AssetPortfolio` with `book_yield`,
  `investment_income`, `macaulay_duration`, `modified_duration`, `convexity`,
  and a shared `_pv_components` helper; module docstring updated.
- `tests/test_core/test_asset.py` — 17 new tests (see below).
- `docs/DECISIONS.md` — ADR-109.
- `docs/CONTINUATION_asset_alm.md` — Slice 2 → DONE, Slice 3 → NEXT.
- `docs/PLAN_asset_alm.md` — status banner; Slice 2 → ✅ SHIPPED.
- `docs/ROADMAP.md` — Milestone 5.4 Slice 2 checked.

## Tests Added
`tests/test_core/test_asset.py` (+17, total 51):
- **book_yield:** par-book recovers coupon; zero carried at `face·(1+y₀)^(-N/12)`
  recovers `y₀`; discount book yields above coupon; `None` when carried at zero
  (no sign change); market value reconciles to carrying value at the solved yield.
- **investment_income:** `=reserve·y/12` on an explicit yield (dtype + shape);
  uses `book_yield()` when unspecified; raises `PolarisComputationError` without
  a recoverable yield.
- **duration / convexity:** Macaulay of a zero `=N` years (parametrized over
  terms); modified `=Macaulay/(1+y)`; convexity of a zero `=N(N+1)/(1+y)²`;
  portfolio duration is the price-weighted average of constituents'; coupon-bond
  duration `<` maturity; convexity rises with maturity.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `investment_income(reserve_vector, ...)` monthly income consistent with book yield | ✅ | `=reserve·y/12`, explicit + book-yield paths |
| `book_yield()` gross IRR via brentq, `None` on no sign change, scalar | ✅ | Par-book recovers coupon; reconciliation test |
| `macaulay_duration` / `modified_duration` / `convexity` closed-form tested | ✅ | Zero closed forms + textbook convexity |
| Goldens byte-identical (additive slice) | ✅ | QA 76 passed; `polaris price` golden run unchanged |
| Full fast suite green | ✅ | 1698 → 1715 passed (+17 new) |
| ADR recorded | ✅ | ADR-109 |

## Open Questions / Follow-ups
None new. All Epic 4 design questions were resolved by the maintainer in Slice 1
(book-yield definition, deterministic reinvestment, Option-A modco precedence —
recorded in PLAN §5 / CONTINUATION). The two Slice-2-adjacent NICE-TO-HAVE
follow-ups (net-of-spread book yield; time-varying amortising earned rate) were
already promoted to PRODUCT_DIRECTION_2026-06-18.md in Slice 1; ADR-109
reaffirms them but adds nothing new to harvest. Slice 3 (Modco integration) is
the next epic slice and is planned work, not a follow-up.

## Parked Polish
None. (Nothing 3rd-order-or-deeper surfaced this session.)

## Impact on Golden Baselines
None. Slice 2 is purely additive — no product/treaty/pricing path touched. QA
golden suite (76) and the `polaris price` golden run are unchanged; no baseline
regenerated.
