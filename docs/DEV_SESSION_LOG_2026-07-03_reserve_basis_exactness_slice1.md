# Dev Session Log — 2026-07-03 (second run: reserve-basis exactness, Slice 1)

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT ("Statutory valuation
  mortality table (2001 CSO) for CRVM", ADR-089 Out of scope, 1st-order) —
  constituted as Slice 1 of the NEW active Epic
  `docs/PLAN_reserve_basis_exactness.md` (see rationale).
- **Priority:** IMPORTANT (new Epic, step 5b — PLAN + slice 1 is the session
  deliverable)
- **Title:** `AssumptionSet.valuation_mortality` — prescribed statutory
  valuation table for CRVM / VM-20 NPR
- **Slice:** 1 of 4
- **Branch:** claude/laughing-ride-q6qrf4

## Baseline
`make test` at session start: **1925 passed, 0 failures, 110 deselected**
(clean green — the prior recorded baseline of 1913 extended by Slice
3b-2b-2's 12 new Excel/CLI tests). `convert_soa_tables.py` produced the
VBT/CSO tables; the four CIA tables report MISSING from pymort
(known-standing, no test depends on them). No new or changed failures →
PROCEED.

## Ledger Healing (step 4b)
PR #123 (B3 final slice) merged since the prior session log. The B3 epic's
queue entries were still un-struck in both PRODUCT_DIRECTION files:
- `PRODUCT_DIRECTION_2026-05-23.md` "Sliding-scale expense allowances /
  experience refunds" → struck with SHIPPED footer (PRs #117–#123).
- `PRODUCT_DIRECTION_2026-06-18.md` same entry in the queue restatement →
  struck with SHIPPED footer.

## Selection Rationale
Every CONTINUATION is COMPLETE (B3 closed by PR #123, merged) — no Epic was
active, so per step 5b starting one is mandatory before any fallback pick.
The COMMERCIAL_VIABILITY_REVIEW_2026-06-18 Tier-A ladder (A1–A3), the
deferred C0 Asset/ALM epic, and Tier-B B3 are ALL COMPLETE, so the review's
epic queue is exhausted; the review itself is 15 days old (< the ~30-day
regeneration trigger), so rather than regenerate it early, the new Epic is
constituted from the highest-value unshipped work it points at: the two
surviving IMPORTANT items in PRODUCT_DIRECTION_2026-06-18 — the **2001 CSO
statutory valuation mortality table for CRVM** and the **GAAP (FAS 60)
concrete basis** — both 1st-order residuals of Epic 1 (reserve-basis
matching) and the direct continuation of its value proposition ("a reinsurer
that cannot reproduce the cedant's statutory reserve cannot trust the profit
number"). Together they form the 4-slice **Reserve-Basis Exactness** epic
(PLAN + CONTINUATION opened this session).

Skipped: the third IMPORTANT reserve item (NET_PREMIUM WL terminal-reserve
artefact closure) is rebaseline-gated on human authorization; the fourth
IMPORTANT (expense-allowance `use_policy_cession` duration mapping) is a
SMALL fallback item, and the guardrail forbids pairing fallback work with an
epic start. Tier-B B1/B2/B4 and Tier-C remain fallback candidates for
blocked-epic sessions.

## Verify Premise (step 7b)
Reproduced by code inspection before writing code: `AssumptionSet` had no
valuation-table slot (adding the field in a test raised Pydantic
`extra_forbidden` — the red test confirmed it); TermLife's CRVM receives the
projection `q` (improvement scale included) from `_build_rate_arrays()`, and
WholeLife's `_build_valuation_mortality` hardcoded
`self.assumptions.mortality`. The backlog entry's claim is factually correct;
premise holds.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `valuation_mortality` slot + CRVM/VM-20-NPR wiring (Term + WL) | ✅ Done | (this draft) |
| 2 | Surface end-to-end: config / CLI / API + 2001 CSO integration + notebook | ⏳ Next | — |
| 3 | GAAP (FAS 60) basis for TermLife (design ADR + closed-form test) | 🔲 Planned | — |
| 4 | GAAP (FAS 60) for WholeLife + epic close | 🔲 Planned | — |

## What Was Done
Added `AssumptionSet.valuation_mortality: MortalityTable | None = None` — the
prescribed statutory valuation table for the statutory reserve bases. TermLife
gained `_valuation_q()` (returns the projection `q` unchanged when the slot is
unset — byte-identical by construction) and `_build_statutory_valuation_q()`
(mirrors `_build_rate_arrays`'s mortality half: per-(sex,smoker) masked
lookup, duration seasoning, substandard rating, rates zeroed post-expiry —
but from the valuation table, with **no improvement scale**, ages capped at
the valuation table's max age). CRVM and the VM-20 NPR floor value on it;
the VM-20 deterministic reserve is anticipated-experience by definition and
stays on the projection assumptions.

WholeLife's `_build_valuation_mortality` and `_valuation_months_to_omega` now
take an optional table / max-age: CRVM (and hence the WL VM-20 NPR) values on
the prescribed table **to that table's omega** (certain-death forcing at its
max age), while the VM-20 DR keeps the projection table and its omega.
Recorded in ADR-125; ARCHITECTURE.md reserve-basis section updated (the
"tracked follow-up" sentence is now the shipped behaviour).

An actuarial subtlety surfaced by the tests: a uniformly conservative
(1.5×-scaled) valuation table raises the WL CRVM reserve at early/mid
durations but sits slightly *below* baseline approaching omega — both bases
grade to face, and the higher-q basis carries a higher renewal valuation
premium, so the curves cross (empirically month ~147 on the test block). The
WL directional test asserts early-duration dominance only, with the rationale
documented in the test.

## Files Changed
- `src/polaris_re/assumptions/assumption_set.py` — `valuation_mortality` field
- `src/polaris_re/products/term_life.py` — `_valuation_q`,
  `_build_statutory_valuation_q`, CRVM/VM-20 dispatch, docstrings
- `src/polaris_re/products/whole_life.py` — table-parametrised
  `_build_valuation_mortality` / `_valuation_months_to_omega`, CRVM wiring,
  docstrings
- `ARCHITECTURE.md` — Reserve Basis Selection section
- `docs/DECISIONS.md` — ADR-125
- `docs/PLAN_reserve_basis_exactness.md` — NEW (epic plan)
- `docs/CONTINUATION_reserve_basis_exactness.md` — NEW (IN PROGRESS)
- `docs/PRODUCT_DIRECTION_2026-05-23.md` / `..._2026-06-18.md` — ledger
  healing (B3 SHIPPED crossouts) + 2 promoted follow-ups
- `docs/DEV_SESSION_LOG_2026-07-03_reserve_basis_exactness_slice1.md` — this log

## Tests Added
- `tests/test_products/test_statutory_valuation_table.py` — 15 tests across
  4 classes: AssumptionSet contract (default None, accepts table); Term
  same-table consistency, conservative-table direction, improvement isolation,
  NET_PREMIUM ignores slot, VM-20 composition (`max(NPR_stat, DR_best_est)`),
  independent closed-form FPT recomputation on a rated block; WL same-table
  consistency, early-duration conservative direction, omega-follows-table,
  VM-20 composition, NET_PREMIUM ignores slot; projection cash flows
  unchanged (claims/premiums identical, reserves move) for CRVM and VM20.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `valuation_mortality` slot with backward-compat default | ✅ | default `None`, Pydantic-validated |
| CRVM values on prescribed table when set (Term + WL) | ✅ | closed-form + direction tests |
| VM-20: NPR on prescribed table, DR best-estimate | ✅ | composition test on both products |
| Statutory q is static (no improvement scale) | ✅ | improvement-isolation test |
| NET_PREMIUM untouched | ✅ | ignores-slot tests |
| Default `None` byte-identical | ✅ | 1925 pre-existing tests green; golden flat exact ($45,386 / $3,513,563) |
| WL omega follows the valuation table | ✅ | `_valuation_months_to_omega(max_age)` test |

## Open Questions / Follow-ups
- **Successor COMMERCIAL_VIABILITY_REVIEW due ~2026-07-18.** The 2026-06-18
  review's epic queue (A1–A3, C0, B3) is fully shipped. This epic was
  constituted from the review-pointed IMPORTANT residuals, but the next
  epic after it has no ranked source — regenerate the review at the 30-day
  mark (or earlier if this epic finishes first) to re-rank the catalogue.
- Slice-3 GAAP PAD calibration and a Slice-2 CSV-path escape hatch are
  recorded as human questions in `CONTINUATION_reserve_basis_exactness.md`.
- Harvested this session (ADR-125 residuals → PRODUCT_DIRECTION_2026-06-18
  Promoted Follow-ups): sex/smoker-distinct valuation-table composition
  helper (NICE-TO-HAVE, 1st-order); prescribed valuation-interest helper
  (NICE-TO-HAVE, 1st-order).

## Parked Polish
None. (Both harvested items are 1st-order residuals of the originally-planned
epic feature and were promoted normally.)

## Impact on Golden Baselines
None — the new field defaults to `None` on every path, so all priced numbers
are byte-identical. Golden `flat` config reproduces Total PV Profits
Reinsurer $45,386 / Cedant $3,513,563 exactly. No baseline regeneration.
