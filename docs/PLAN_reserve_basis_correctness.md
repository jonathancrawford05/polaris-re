# PLAN: Reserve-Basis Correctness & Interest Exactness

**Status:** IN PROGRESS — constituted 2026-07-05 as the active epic after the
Reserve-Basis Exactness epic closed (`PLAN_reserve_basis_exactness.md` → COMPLETE,
ADR-128). Slice 1 (WholeLife mortality-improvement correctness fix) is NEXT.

**Source / derivation.** The COMMERCIAL_VIABILITY_REVIEW_2026-06-18 Tier-A ladder
(A1 reserve basis, A2 IFRS 17 movement, A3 cross-jurisdiction capital) plus the
C0 Asset/ALM and B3 expense-allowance epics are ALL COMPLETE, and Phases 1–3 of
`docs/ROADMAP.md` are complete. This epic is therefore constituted from the
highest-value unshipped items the harvested Promoted Follow-ups point at
(`docs/PRODUCT_DIRECTION_2026-06-18.md`), same pattern as the Reserve-Basis
Exactness epic was constituted (Tier-A ladder exhausted, so the epic derives from
the ranked follow-ups):

1. **WholeLife does not model mortality improvement on any basis** — a *silent
   correctness bug* surfaced by the Slice-4 GAAP guardrail asymmetry (ADR-128 Out
   of scope). `WholeLife._build_rate_arrays` never reads
   `AssumptionSet.improvement`, so a WL deal priced with an improvement scale
   configured silently ignores it. This is the reason there is no WL analogue of
   the TermLife "GAAP reflects improvement" guardrail test.
2. **Prescribed statutory valuation-interest helper** (issue-year → SVL max
   valuation rate / VM-20 NPR discount rate) — the gating item for *penny-exact*
   CRVM reproduction (IMPORTANT). `valuation_mortality` (Reserve-Basis Exactness
   Slices 1–2) fixed only the mortality half of the reserve; without prescribed
   valuation interest, statutory reproduction is directional, not exact.

**Priority rationale (correctness before exactness).** Item 1 is a bug — silent
wrong behaviour, not a missing feature — so it leads the epic. Item 2 is
exactness polish that completes the Reserve-Basis Exactness value proposition.

## Overall Goal

Make the reserve basis both **correct** (WholeLife honours the configured
mortality-improvement scale on its best-estimate bases, as TermLife already does)
and **exact** (CRVM / VM-20-NPR value on the prescribed statutory valuation
interest rate, closing the interest half of "reproduce the cedant's held
statutory reserve").

## Design Anchors

- **Improvement is a best-estimate property, applied per basis.** WholeLife must
  apply `AssumptionSet.improvement` to its **best-estimate** mortality (the
  projection cash flows, GAAP, and the VM-20 *deterministic* reserve — all
  anticipated-experience), mirroring `TermLife._build_rate_arrays`. It must NOT
  apply improvement to the **statutory prescribed** table path (CRVM / VM-20 NPR
  valued on `valuation_mortality`), which stays static by the ADR-125 design
  boundary. The improvement switch is therefore a *caller/basis* decision, not a
  blanket `_build_rate_arrays` change — see Slice 1 for the exact boundary.
- **Byte-identity is basis-dependent for the improvement fix.** No golden/QA
  config configures a WL improvement scale (to be verified in Slice 1); if that
  holds, the fix is byte-identical on every golden. If any WL golden DOES set
  improvement, the projection-side change is rebaseline-gated (human
  authorisation) and Slice 1 splits into a safe reserve-side part and a gated
  projection-side part.
- **Valuation interest is prescribed, like valuation mortality.** The SVL / VM-20
  maximum valuation interest rate is issue-year- and product-driven; the engine
  currently takes a single manual `ProjectionConfig.valuation_interest_rate`. The
  helper resolves issue-year → prescribed rate, default `None` preserving today's
  manual behaviour byte-identically.

## Decomposition

### Slice 1: WholeLife mortality-improvement on best-estimate bases (THIS SLICE — NEXT)
- **Status:** DONE (2026-07-05, ADR-129). Correctness fix shipped; next up is the
  CHECKPOINT (regenerate COMMERCIAL_VIABILITY_REVIEW) before Slice 2.
- Apply `AssumptionSet.improvement` in `WholeLife._build_rate_arrays` (mirror
  `TermLife._build_rate_arrays` lines ~103–143: annual q → `apply_improvement(q,
  ages, cal_year)` → back to monthly via constant-force interpolation, BEFORE the
  substandard-rating step and the max-age forcing).
- Apply improvement to the best-estimate valuation mortality used by GAAP and the
  VM-20 deterministic reserve (`_build_valuation_mortality` on the projection
  table, i.e. `table is None`), but NOT when a prescribed statutory `table` is
  passed (CRVM / VM-20 NPR) — pass the improvement decision explicitly from the
  caller so the statutory static rule (ADR-125) is preserved. Confirm the exact
  seam (a `apply_improvement: bool` parameter defaulting to preserve current
  behaviour is the likely cleanest form).
- Tests: closed-form improvement-isolation (a Scale AA improvement lowers WL
  best-estimate q, so it lowers GAAP and the VM-20 DR and the projected claims,
  but leaves CRVM / VM-20 NPR-on-prescribed-table unchanged); a WL analogue of
  the TermLife "GAAP reflects improvement" guardrail (now it moves); byte-identity
  when no improvement is configured.
- **Byte-identity checkpoint:** verify no golden/QA WL config sets an improvement
  scale. If confirmed, goldens are byte-identical. If not, split per the Design
  Anchor and flag the projection-side rebaseline for human authorisation.
- ADR entry. Update the PRODUCT_DIRECTION WL-improvement item to ADDRESSED.

### CHECKPOINT (after Slice 1): regenerate COMMERCIAL_VIABILITY_REVIEW
- Phases 1–3 are complete and the Tier-A ladder is exhausted, so before
  committing the epic to the interest-exactness slices, regenerate
  `COMMERCIAL_VIABILITY_REVIEW` (re-review the last ~10 PRs + docs, re-rank the
  catalogue) to confirm Slices 2–3 remain the highest-value continuation vs a
  *productization* epic (data-ingestion robustness, AXIS/Prophet benchmark
  validation, packaging/deployment, documentation). If the review re-ranks a
  productization epic above interest-exactness, re-scope Slices 2–3 accordingly.
  This is the deliberate guard against an epic-level polish spiral now that the
  modeling roadmap is done.

### Slice 2: Prescribed statutory valuation-interest helper — engine (PROVISIONAL)
- **Status:** PLANNED (pending the checkpoint).
- Issue-year (+ product/table) → SVL max valuation rate / VM-20 NPR discount rate
  resolver; wire into the CRVM and VM-20 NPR discounting when set. Default `None`
  keeps the manual `valuation_interest_rate` byte-identical.
- Closed-form: a known issue-year resolves to the published rate; CRVM on the
  prescribed rate differs from CRVM on the manual rate; byte-identity when unset.

### Slice 3: Surface valuation-interest on the deal path + docs (PROVISIONAL)
- **Status:** PLANNED (pending the checkpoint).
- `DealConfig` / CLI / API surface (mirror the `valuation_mortality` ADR-126
  surfacing); notebook + ARCHITECTURE; HARVEST + close CONTINUATION.

## Explicitly Out of Scope (epic level)

- Surfacing the GAAP PADs on the deal path (a separate IMPORTANT follow-up,
  ADR-127/128 Out of scope) — related but independent; not bundled here.
- FAS 60 DAC amortisation / loss-recognition; duration-varying PAD structures
  (NICE-TO-HAVE follow-ups).
- Sex/smoker-distinct statutory table composition and CSO-version selection
  (NICE-TO-HAVE follow-ups on the mortality side).
