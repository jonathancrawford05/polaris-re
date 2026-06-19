# Dev Session Log — 2026-06-19

## Item Selected
- **Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier A, item A1
  (Reserve-basis matching). New Epic started this session.
- **Priority:** Tier A (highest-value, ~10 dev-days, #1 unstarted epic)
- **Title:** Reserve-basis matching — Slice 1: `ReserveBasis` enum + plumbing
- **Slice:** 1 of 4

## Selection Rationale
Step 5 found **no IN PROGRESS CONTINUATION** — every existing CONTINUATION is
COMPLETE and the only PLAN (dashboard_portfolio) is shipped. So the routine
fell to step 5b (ACTIVE EPIC) and found **no active Epic**. Per step 5b.b the
session's deliverable is to *start* one: take the top-ranked unstarted Tier-A
item from the latest COMMERCIAL_VIABILITY_REVIEW, write its PLAN, and ship
slice 1 — and **not** also pick a fallback item. The top-ranked Tier-A item is
**A1 Reserve-basis matching** (★★★★★, the #1 credibility gap, carried as
IMPORTANT in both PRODUCT_DIRECTION files for two months). The routine notes
explicitly name this as the first epic to start
(`PLAN_reserve_basis.md` → `CONTINUATION_reserve_basis.md`, slice 1 =
ReserveBasis enum + plumbing, goldens byte-identical).

Sprint-0 Tier-B quick wins (B1 capital surfaces, B2 scale benchmark) were
**not** picked: they are fallback work, and the guardrail forbids fallback
while no Epic is active — starting the Epic is the deliverable.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `ReserveBasis` enum + `ProjectionConfig` field + dispatch guard | ✅ Done | (this draft) |
| 2 | CRVM concrete basis (Term + WL) + WL terminal-reserve acceptance test | ⏳ Next | — |
| 3 | VM-20 simplified (deterministic / NPR floor) | 🔲 Planned | — |
| 4 | Surface selector on CLI / API / Excel / notebook | 🔲 Planned | — |

See `docs/PLAN_reserve_basis.md` and `docs/CONTINUATION_reserve_basis.md`.

## What Was Done
Started Epic 1. Added a `ReserveBasis` StrEnum (NET_PREMIUM / CRVM / VM20 /
GAAP) in a new `core/reserve_basis.py`, exported from `polaris_re.core`, and a
`ProjectionConfig.reserve_basis` field defaulting to NET_PREMIUM. Added a
dispatch guard on `BaseProduct` — a `_supported_reserve_bases` frozenset
(NET_PREMIUM only) and `_check_reserve_basis()`, which returns the active basis
and raises `PolarisComputationError` when the configured basis is not in the
engine's supported set. Every product's `compute_reserves()` (Term, WL, UL, DI)
now calls the guard first.

The design choice that matters: a not-yet-implemented basis **raises** rather
than silently falling back to net premium, so a pricing run can never report a
reserve on a basis the engine did not compute. Because NET_PREMIUM is the
default and the recursion bodies are untouched, the change is invisible on the
default path — goldens are byte-identical, no rebaseline.

Verified the epic's premise first (routine step 7b): inspected every
`compute_reserves()` and confirmed there was no `reserve_basis` selector and no
config field — the engine genuinely could not produce a CRVM/VM-20/GAAP reserve.

## Files Changed
- `src/polaris_re/core/reserve_basis.py` (new)
- `src/polaris_re/core/projection.py`
- `src/polaris_re/core/__init__.py`
- `src/polaris_re/products/base_product.py`
- `src/polaris_re/products/term_life.py`
- `src/polaris_re/products/whole_life.py`
- `src/polaris_re/products/universal_life.py`
- `src/polaris_re/products/disability.py`
- `docs/DECISIONS.md` (ADR-087)
- `docs/PLAN_reserve_basis.md` (new)
- `docs/CONTINUATION_reserve_basis.md` (new)

## Tests Added
- `tests/test_core/test_reserve_basis.py` — enum members/values, export
  identity, config default NET_PREMIUM, accepts enum + string, rejects unknown,
  `model_dump`/`model_validate` and JSON round-trips.
- `tests/test_products/test_reserve_basis_dispatch.py` — default ==
  explicit NET_PREMIUM byte-identical (Term + WL); every unimplemented basis
  raises `PolarisComputationError` per product (parametrized); error message
  names the supported basis.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `ReserveBasis` enum exists + exported from core | ✅ | NET_PREMIUM/CRVM/VM20/GAAP |
| `ProjectionConfig.reserve_basis` field, default NET_PREMIUM | ✅ | round-trips through JSON |
| Non-default basis raises (no silent fallback) | ✅ | per product, parametrized |
| Default path byte-identical | ✅ | recursion bodies untouched; goldens unchanged |
| ADR recorded | ✅ | ADR-087 |

## Open Questions / Follow-ups
- **Valuation mortality table (Slice 2).** CRVM uses 2001 CSO, distinct from
  the best-estimate projection table. Where it lives (likely a
  `valuation_mortality` slot on `AssumptionSet`, defaulting to the projection
  table) is a controlled core-contract change needing its own ADR. Deferred to
  Slice 2 by design.
- **VM-20 scope.** Confirm the intended scope is the deterministic reserve /
  NPR floor only (no stochastic scenario reserve). The PLAN assumes so.
- **UL / DI statutory bases.** Deliberately out of scope; those engines keep
  raising on non-NET_PREMIUM bases. Revisit only if a later epic needs them.

## Parked Polish
None. (No 3rd-order follow-ups surfaced this session.)

## Impact on Golden Baselines
None. The default reserve basis is NET_PREMIUM and the recursion bodies are
unchanged, so the golden `price` JSON is byte-identical. No rebaseline.

## Baseline Note
`make test` baseline this session: **1393 passed, 0 failures, 83 deselected**
(prior recorded baseline 1356 post-change on 2026-06-16; intervening merges
#74–#80 raised the count). CIA tables MISSING from the pymort conversion as
usual; SOA tables converted, so no SOA failures. No new or changed failures vs
baseline. Post-change target: 1393 + 18 new tests = 1411 passed.
