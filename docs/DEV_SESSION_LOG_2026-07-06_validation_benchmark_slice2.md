# Dev Session Log — 2026-07-06

## Item Selected
- **Source:** `CONTINUATION_validation_benchmark.md` (active epic A1′) — Slice 2
- **Priority:** IMPORTANT / Tier-A (★★★★★) — the trust-and-deployment frontier;
  the active epic per `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4–§5
- **Title:** Validation & Benchmark Pack (A1′) — published-deck reference set
  (`STATUTORY_DECK`), SOA Illustrative Life Table
- **Slice:** 2 of 3 (+ optional Slice 4, parked)
- **Branch:** `claude/loving-gauss-alct0t`

## Selection Rationale
Step 5 found `CONTINUATION_validation_benchmark` IN PROGRESS with its prior slice
(Slice 1) merged (PR #130, on `main`), so per step 5b(c) the session advances the
active Epic's next unchecked slice before any fallback pick. Slice 2 was NEXT and
fully unblocked (Slice 1 merged; the framework it needs is on main). No fallback
gate was reached. The parked `reserve_basis_correctness` epic remains
open-but-deprioritised pending the maintainer's redirect go/no-go.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Validation framework + closed-form seed set | ✅ Done | #130 |
| 2 | Published-deck reference set (`STATUTORY_DECK`, SOA ILT) | ✅ Done | (this PR) |
| 3 | Surface: `polaris validate` CLI + `05_validation_report.ipynb` | ⏳ Next | — |
| 4 | AXIS/Prophet side-by-side | ⏸ Parked (reference-blocked) | — |

## What Was Done
Delivered the `STATUTORY_DECK` category against a *published* reference — the SOA
Illustrative Life Table (Bowers et al., *Actuarial Mathematics* 2e, App. 2A) — and
validated the **WholeLife** engine (extending coverage beyond Slice 1's TermLife).
The table's `l_x` column is vendored under `data/validation/illustrative_life_table.csv`
but **generated from the table's published Makeham law** (`μ = A + Bc^x`, `A=.0007`,
`B=.00005`, `c=10^.04`, `l_0=100000`) rather than a hand-copied column — the three
constants are the citation, and the regenerated table is self-checked against the CSV
and against the *printed* ILT values (`1000·A_35=128.72`, `ä_35=15.3926`,
`1000·A_65=439.80`, `ä_65=9.8969`), which it reproduces to all printed digits.

Nine `STATUTORY_DECK` cases (issue ages 35/40/65) reproduce the whole-life net single
premium `A_x`, annuity-due `ä_x`, and net level premium `P_x = A_x/ä_x` at `i=6%`. The
reference APVs are exact annual life-table identities of the vendored `l_x` (and satisfy
`A_x = 1 − d·ä_x`, asserted independently). The engine projects a whole-life policy to
omega monthly; because the constant-force monthly split preserves the annual decrements
exactly, reconstructing the annual APVs from the monthly output (deaths aggregated to
year-end; in-force sampled at policy-year boundaries) equals the tabulated values to
`rtol=1e-9` (measured ~2e-14). Added `run_statutory_deck_benchmarks()` and a combined
`run_full_validation_pack()` (Slice 3's single entry point).

**Verify-premise step (7b) was run first:** a scratch reproduction confirmed the
Makeham generation reproduces the printed ILT to all digits, the `A_x=1−d·ä_x` identity
holds to 1e-15, and the WholeLife engine reproduces the annual `A_35`/`ä_35` to ~2e-14
(and the monthly-native quantities show the expected `i/i^{(12)}=1.0272` acceleration)
before any module code was written.

## Files Changed
- `src/polaris_re/analytics/validation.py` — Makeham generator + CSV loader +
  annual-APV helper + WholeLife-to-omega driver + `run_statutory_deck_benchmarks()` +
  `run_full_validation_pack()`; module docstring + `__all__`
- `src/polaris_re/analytics/__init__.py` — export the two new runners
- `data/validation/illustrative_life_table.csv` — **new** vendored `l_x` (cited header)
- `tests/validation/test_statutory_deck_pack.py` — **new** (26 tests)
- `Dockerfile` — `COPY data/validation/`
- `.dockerignore` — `!data/validation/` allowlist
- `docs/DECISIONS.md` — ADR-131
- `docs/CONTINUATION_validation_benchmark.md` — Slice 2 → DONE, Slice 3 → NEXT
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — ledger-heal (WholeLife-to-omega item
  struck through SHIPPED; ACTED-ON note updated) + harvest (reserve-deck NICE-TO-HAVE)

## Tests Added
`tests/validation/test_statutory_deck_pack.py` (26 tests): vendored CSV equals the
Makeham regeneration byte-for-byte; table shape/endpoints/monotonicity/contiguity; the
`A_x=1−d·ä_x` identity and an independent loop-based recompute (transcription guard);
reproduction of the printed ILT values; the WholeLife engine reproduces the annual
`A_x`/`ä_x` to `rtol=1e-9` across three issue ages; survivorship completeness; deck
report all-pass / three-cases-per-age / all-`STATUTORY_DECK` / `P_x=A_x/ä_x` /
Markdown; full pack all-pass, spans all three categories, is the union of sub-packs.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| ≥1 published/textbook deck reproduced within documented tolerance | ✅ | SOA ILT, `rtol=1e-9` (machine precision) |
| `ValidationReport` includes `STATUTORY_DECK` cases and `all_passed` | ✅ | 9 deck cases; full pack 13/13 |
| Independent-recompute self-check of expected APVs from `l_x` | ✅ | loop recompute + `A_x=1−d·ä_x` identity |
| Goldens / QA byte-identical | ✅ | QA 76 green; `polaris price` regression unchanged |
| Dockerfile / `.dockerignore` updated in same PR | ✅ | `data/validation/` COPY + allowlist |

## Open Questions / Follow-ups
- **Redirect go/no-go (still reserved for the maintainer):** confirm A1′ validation
  is the active epic (default taken across Slices 1–2) vs finishing interest-exactness
  first. Tracked in the CONTINUATION.
- **Published held-reserve deck (VM-20 / CRVM):** the ILT deck validates APV/premium
  columns; a published held-reserve worked example would validate the reserve path
  directly. Harvested to PRODUCT_DIRECTION as NICE-TO-HAVE. Not required to close A1′.

## Parked Polish
None (no 3rd-order-or-deeper follow-ups surfaced this session).

## Impact on Golden Baselines
None. The validation pack is a separate analytics module; the pricing path is
untouched. QA golden suite green and the `polaris price` regression on
`golden_config_flat.json` is unchanged.
```
Baseline `make test`: 2019 passed, 2 skipped, 110 deselected, 0 failures
  (prior session log baseline: 2001 passed — the delta is intervening merges;
  no new/changed failures, tolerance-aware check passes).
After this slice: 2045 passed, 2 skipped, 110 deselected (+26 = new tests).
```
