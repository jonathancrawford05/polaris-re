# Continuation: Reserve-Basis Exactness (statutory valuation table + GAAP)

**Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT ("Statutory valuation
mortality table (2001 CSO) for CRVM" + "GAAP (FAS 60) concrete reserve basis",
both 1st-order Epic-1 residuals); epic constituted per step 5b with the
Tier-A ladder exhausted — see `docs/PLAN_reserve_basis_exactness.md`.
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~6-8 dev-days

## Overall Goal

Close the last two gaps between "a reserve on the right method" and "the
cedant's reserve, reproduced": value CRVM / VM-20-NPR on the prescribed
statutory mortality table (2001 CSO) instead of the pricing best-estimate
table, and implement GAAP (FAS 60) as a concrete selectable basis.

## Decomposition

### Slice 1: `valuation_mortality` slot + CRVM/VM-20-NPR wiring
- **Status:** DONE
- **Branch:** claude/laughing-ride-q6qrf4
- **PR:** #124
- **What was done:** Added `AssumptionSet.valuation_mortality: MortalityTable
  | None = None`. TermLife builds a statutory valuation q (valuation-table
  lookup, **no** improvement, substandard rating applied, zeroed post-expiry)
  and CRVM + the VM-20 NPR value on it when the slot is set; WholeLife's
  `_build_valuation_mortality` / `_valuation_months_to_omega` take an optional
  table and CRVM (hence the VM-20 NPR) uses the valuation table including its
  omega. VM-20 DR stays best-estimate on both products. Default `None` is
  byte-identical everywhere. ADR-125. Also shipped here (review P2 +
  maintainer direction): the shared `BaseProduct._lookup_qx_column` /
  `_sex_smoker_masks` mortality-lookup helper replacing all six per-product
  copies of the masked per-(sex,smoker) lookup.
- **Key decisions (affect later slices):**
  - The statutory valuation q is **static** — the mortality-improvement scale
    is never applied to it (prescribed tables are published without
    improvement). Slice 2's config surfacing does not need an improvement
    switch.
  - Substandard rating (multiplier + flat extra) IS applied to the valuation
    table, mirroring rated statutory valuation practice.
  - VM-20: only the NPR floor moves to the prescribed table; the DR is
    anticipated-experience by definition and ignores `valuation_mortality`.
  - `NET_PREMIUM` ignores the slot entirely (historical pricing basis).

### Slice 2: Surface `valuation_mortality` end-to-end (2001 CSO)
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `core/pipeline.py` (DealConfig +
  `build_assumption_set` threading), `cli.py` (`--valuation-mortality`),
  `api/main.py` (request-model field), `notebooks/02_reserve_basis_comparison.ipynb`,
  tests (`tests/test_cli_*`, `tests/test_api/`).
- **Tests to add:** config parse + threading; CLI end-to-end CRVM-on-CSO vs
  CRVM-on-projection-table differ (`@requires_soa_tables`-gated by table
  availability); API round-trip; malformed table id raises
  `PolarisValidationError` at parse time.
- **Acceptance criteria:**
  - `polaris price --config <cfg> --reserve-basis crvm` with
    `deal.valuation_mortality: "cso_2001"` values CRVM on 2001 CSO.
  - Omitting the key is byte-identical on all goldens.

### Slice 3: GAAP (FAS 60) basis for TermLife
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:** design ADR (PAD structure: mortality multiplier + interest
  haircut; config surface for PADs), `_compute_reserves_gaap` on TermLife,
  add GAAP to `_supported_reserve_bases`, closed-form FAS 60 test.
- ~~**Pre-step (PR #124 automated review, P2):** extract a shared
  mortality-lookup helper before the GAAP slices add another copy.~~ —
  **DONE in Slice 1** (PR #124, maintainer direction): the per-(sex,smoker)
  masked lookup is now `BaseProduct._lookup_qx_column` (with cached
  `_sex_smoker_masks`), consumed by all six former copies — Term projection +
  statutory builders, WL projection + valuation builders, UL and Disability
  mortality builders. Verified byte-identical (full suite + QA green; golden
  JSON diff empty pre- vs post-refactor). Slice 3's GAAP path should call the
  same helper.

### Slice 4: GAAP (FAS 60) for WholeLife + epic close
- **Status:** PLANNED
- **Depends on:** Slice 3 merged
- **Scope:** WL GAAP prospectively to omega; supported-bases update; notebook
  + ARCHITECTURE; HARVEST FOLLOW-UPS then Status → COMPLETE.

## Context for Next Session

- The per-(sex,smoker) masked lookup is single-source:
  `BaseProduct._lookup_qx_column` (cached `_sex_smoker_masks`), used by every
  mortality builder across Term/WL/UL/Disability. The statutory-q builders
  still own their basis-specific wrapping (duration seasoning via
  `duration_inforce_vec_at`, age caps at the **valuation table's** max_age,
  no improvement, rating, WL certain-death forcing at its omega). New
  mortality paths (e.g. GAAP) must call the shared helper, not copy the loop.
- TermLife byte-identity is by construction: when the slot is `None` the CRVM
  / VM-20-NPR paths receive the projection q object unchanged (no rebuild).
- WholeLife: when the slot is `None`, `_build_valuation_mortality(t_val)`
  falls back to the projection table — also unchanged code path.
- 2001 CSO CSVs (`cso_2001_male.csv` / `cso_2001_female.csv`) are produced by
  `scripts/convert_soa_tables.py` and loaded via
  `MortalityTable.load(MortalityTableSource.CSO_2001, ...)` — confirm the
  exact source enum value when wiring Slice 2. Note 2001 CSO is
  ultimate-only (select_years=1 in the conversion table output).
- Rejected: putting the slot on `ProjectionConfig` (it is an assumption — a
  table — and `AssumptionSet` is the versioned audit carrier); building the
  statutory q with improvement applied (prescribed tables are static).

## Open Questions (for human)

- Slice 3 PAD calibration: FAS 60 PADs are company-specific. Proposed default:
  mortality PAD as a configurable multiplier (e.g. 1.10) and a valuation-rate
  haircut, both on `ProjectionConfig` — confirm or redirect at Slice-3 review.
- Should Slice 2 also accept a CSV path (arbitrary cedant valuation table)
  in addition to a named source id? Leaning yes-later (the `yrt_rate_table_path`
  precedent) — flag if wanted in Slice 2 itself.

## Refinement Backlog

(harvest into PRODUCT_DIRECTION when this CONTINUATION closes)

- Sex-distinct / smoker-distinct statutory table composition helper (2001 CSO
  loads per sex; a cedant filing may prescribe smoker-distinct variants).
- Statutory valuation-interest prescription helper (issue-year → prescribed
  max valuation rate), currently manual via `valuation_interest_rate`.
