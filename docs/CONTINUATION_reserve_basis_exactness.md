# Continuation: Reserve-Basis Exactness (statutory valuation table + GAAP)

**Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT ("Statutory valuation
mortality table (2001 CSO) for CRVM" + "GAAP (FAS 60) concrete reserve basis",
both 1st-order Epic-1 residuals); epic constituted per step 5b with the
Tier-A ladder exhausted — see `docs/PLAN_reserve_basis_exactness.md`.
**Status:** COMPLETE (all 4 slices done; Slice 4 shipped 2026-07-04, ADR-128 —
WholeLife GAAP. Refinement Backlog + unresolved Open Questions harvested into
PRODUCT_DIRECTION_2026-06-18 Promoted Follow-ups before closing.)
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
- **Status:** DONE
- **Branch:** claude/loving-gauss-ipkczw
- **PR:** (this slice)
- **What was done:** `DealConfig.valuation_mortality: str | None = None` (a
  named mortality source id) + the shared `load_valuation_mortality(source,
  data_dir)` public helper in `core/pipeline.py`, threaded into
  `build_assumption_set` (loaded raw — no pricing multiplier, no improvement).
  CLI: `--valuation-mortality` flag with flag-over-config precedence
  (`_build_pipeline_from_config(valuation_mortality_override=...)`), config
  parsing of `deal.valuation_mortality` (nested + legacy), and a conditional
  JSON `summary` echo (present only when set → byte-identical otherwise).
  API: `PriceRequest.valuation_mortality` loaded server-side from
  `$POLARIS_DATA_DIR/mortality_tables` via the shared helper (unknown id → 422).
  Notebook `02` gains a CRVM-on-prescribed-table section (synthetic table, CI-safe).
  ADR-126.
- **Key decisions (affect later slices):**
  - Named source id (string), not a `MortalityTable` object, on the deal path —
    mirrors `MortalityConfig.source`. A CSV-path escape hatch is still deferred.
  - `load_valuation_mortality` is the single loader shared by the pipeline and
    the API; Slice 3/4 GAAP surfacing should reuse it, not re-resolve sources.
  - Summary echo is conditional (only when set) to preserve byte-identity; the
    API response is NOT echoed yet (follow-up if wanted).
- **Acceptance criteria:**
  - `polaris price --config <cfg> --reserve-basis crvm --valuation-mortality
    CSO_2001` (or `deal.valuation_mortality: "CSO_2001"`) values CRVM on 2001
    CSO — verified: WL cedant PV differs from CRVM-on-projection-table. ✅
  - Omitting the key is byte-identical on all goldens (none set it). ✅

### Slice 3: GAAP (FAS 60) basis for TermLife
- **Status:** DONE
- **Branch:** claude/loving-gauss-l0xbfn
- **PR:** (this slice)
- **What was done:** `TermLife._compute_reserves_gaap` — the FAS 60 net-premium
  benefit reserve as the net premium reserve (`_compute_reserves_net_premium`)
  on a **margined best-estimate** basis: projection `q` (improvement + rating
  already applied) × `gaap_mortality_pad`, discounted at
  `ProjectionConfig.gaap_valuation_rate` (= valuation rate − `gaap_interest_margin`,
  floored at 0). Two new neutral-default PAD fields on `ProjectionConfig`
  (`gaap_mortality_pad=1.0`, `gaap_interest_margin=0.0`) → neutral PADs collapse
  GAAP exactly onto the locked-in best-estimate NPR (byte-identical goldens; no
  golden selects GAAP). GAAP added to `TermLife._supported_reserve_bases`; the
  dispatch/API tests that asserted GAAP raises for TermLife now exercise
  WholeLife. ADR-127.
- **Key decisions (affect Slice 4):**
  - GAAP does **not** read `assumptions.valuation_mortality` and does **not**
    suppress improvement — the guardrail. It reuses `_compute_reserves_net_premium`
    (and hence `_lookup_qx_column` via `_build_rate_arrays`) as plumbing, never
    the statutory basis rule. Slice 4's WL GAAP must mirror this.
  - The PADs live on `ProjectionConfig` this slice; deal-path surfacing
    (`DealConfig` / CLI / API) is a harvested 1st-order follow-up (the
    `valuation_mortality` ADR-125→126 precedent).
  - Interest-margin reserve direction is accumulation-phase only (sign can flip
    in late run-off); the property test asserts the unambiguous phase.
- **GUARDRAIL — GAAP must NOT inherit the statutory static/no-improvement rule.**
  The "value on a prescribed, static, no-improvement table" property is specific
  to the **US-statutory** bases (CRVM / VM-20-NPR): those are prescribed
  regulatory formulas whose inputs are fixed by the Standard Valuation Law /
  Valuation Manual. FAS 60 is a different animal — a net-premium benefit reserve
  on **locked-in best-estimate assumptions plus explicit PADs**. That "best
  estimate" legitimately includes mortality improvement (the improvement scale
  is part of the projection assumptions), locked in at issue. So GAAP defines
  its **own** basis: it does **not** read `AssumptionSet.valuation_mortality`
  (the prescribed statutory table), and it does **not** suppress improvement the
  way `_build_statutory_valuation_q` does. Reuse `load_valuation_mortality` /
  `_lookup_qx_column` as plumbing only where a table lookup is genuinely needed;
  do not reuse the statutory *basis rule*. Same warning applies to any future
  non-US valuation path (e.g. CIA/IFRS-17), where improvement IS applied to
  valuation mortality in some regimes.
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
- **Status:** DONE
- **Branch:** claude/loving-gauss-eitwhz
- **PR:** (this slice)
- **What was done:** `WholeLife._compute_reserves_gaap` — the FAS 60 net **level**
  premium benefit reserve, valued **prospectively to omega** (like CRVM/VM-20, so
  no horizon-edge collapse) on the same margined best-estimate basis as Slice 3:
  projection valuation q (mortality-only, to omega, on the **projection** table via
  `_build_valuation_mortality(t_val, None)`) × `gaap_mortality_pad` (capped 1.0),
  discounted at `ProjectionConfig.gaap_valuation_rate`. Uses a single net **level**
  valuation premium `P = APV(benefits to omega) / APV(premium annuity)` — not the
  CRVM Full-Preliminary-Term alpha/beta split — then the same prospective
  reverse-cumsum reserve as the CRVM path. `GAAP` added to WL
  `_supported_reserve_bases`. The `test_reserve_basis_dispatch` /
  `test_api/test_reserve_basis` GAAP-raises cases moved off WholeLife to
  UniversalLife (NET_PREMIUM-only); a new API test pins WL GAAP now prices and
  echoes the basis. Notebook §5c (GAAP with PADs) + ARCHITECTURE updated. ADR-128.
- **Key decisions:**
  - GAAP does **not** read `assumptions.valuation_mortality` (guardrail — passes
    `table=None`, the projection table). Best-estimate + PAD basis, not prescribed
    static. Pinned by a valuation-table-independence test.
  - Net LEVEL premium (equivalence principle), NOT FPT — the FPT expense-allowance
    modification is a statutory (CRVM) device, not a GAAP one.
  - Valued to omega (not the finite-horizon term recursion) so WL GAAP does not
    collapse at the horizon edge; the neutral-PAD identity is the net-level-to-omega
    reserve (verified by independent numpy recomputation), NOT WL NET_PREMIUM.
  - Mortality-PAD reserve direction is early/mid-accumulation only (the higher net
    level premium pulls the tail down); the property test asserts the unambiguous
    phase. Interest margin raises the reserve monotonically through the horizon.
  - WholeLife does not model mortality improvement on any basis, so there is no WL
    analogue of the TermLife "GAAP reflects improvement" guardrail — harvested as
    an IMPORTANT follow-up (WL-wide improvement gap).

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
- **Design boundary — "static / no-improvement" is a US-statutory property, not
  a global default.** It is correct precisely because CRVM / VM-20-NPR are
  prescribed regulatory formulas (published CSO table fixed by issue year, no
  generational-improvement overlay, conservatism already in the table's
  margins). The VM-20 **DR** deliberately stays on the best-estimate projection
  table *with* improvement, because it is an anticipated-experience reserve —
  that split (`VM20 = max(NPR_prescribed, DR_best_estimate)`) is the whole point
  of PBR. Do not let Slice 3/4 (GAAP) or any future non-US path inherit the
  statutory rule by accident — see the Slice-3 guardrail.
- **Reproducing the cedant's reserve to the penny needs the interest side too.**
  `valuation_mortality` makes the *mortality* basis prescribed, but CRVM / the
  VM-20 NPR also use a **prescribed maximum valuation interest rate** by issue
  year / product; the engine still takes a single manual
  `valuation_interest_rate` on `ProjectionConfig`. Mortality-basis exactness
  without interest-basis exactness reproduces the reserve *directionally*, not
  exactly. The issue-year → prescribed-rate helper (Refinement Backlog) is the
  gating item for penny-exact statutory reproduction — sequence it before
  marketing "exact CRVM reproduction" as complete.
- **CSO version is a per-deal domain call today.** 2001 vs 2017 CSO
  applicability is issue-year-driven (2017 CSO mandatory for 2020+ issues,
  elective 2017–2019); the deal takes a single named table, so a block
  straddling a CSO boundary must be split or the correct table chosen by the
  user. An issue-year → CSO-version selector is in the Refinement Backlog.

## Open Questions (for human)

- Slice 3 PAD calibration: FAS 60 PADs are company-specific. Proposed default:
  mortality PAD as a configurable multiplier (e.g. 1.10) and a valuation-rate
  haircut, both on `ProjectionConfig` — confirm or redirect at Slice-3 review.
- ~~Should Slice 2 also accept a CSV path (arbitrary cedant valuation table)
  in addition to a named source id?~~ **Resolved in Slice 2 (ADR-126): named
  source id only for now; CSV-path escape hatch deferred (the
  `yrt_rate_table_path` precedent). Promoted to the refinement backlog.**
- Should the prescribed valuation table be echoed in the REST API response and
  on the Excel/dashboard surfaces? Slice 2 echoes it only in the CLI JSON
  `summary` (conditionally). Flag if API/Excel/dashboard audit visibility is
  wanted — promoted as a NICE-TO-HAVE follow-up.
- **Interest-basis exactness (priority domain call).** Do we want a prescribed
  valuation-interest helper (issue-year → SVL max valuation rate / VM-20 NPR
  discount rate) so CRVM reproduction is penny-exact, not just directional?
  Recommended before positioning "exact statutory reproduction" as done — this
  is the largest remaining gap. See Refinement Backlog.
- **CSO version selection.** Should the engine auto-select 2001 vs 2017 CSO by
  issue year (and support a block that straddles the boundary), or is
  per-deal manual selection acceptable for now? Currently one named table per
  deal.

## Refinement Backlog

(harvest into PRODUCT_DIRECTION when this CONTINUATION closes)

- Sex-distinct / smoker-distinct statutory table composition helper (2001 CSO
  loads per sex; a cedant filing may prescribe smoker-distinct variants), and
  select-and-ultimate CSO / ALB-vs-ANB structure (current conversion is
  ultimate-only, `select_years=1`).
- **Statutory valuation-interest prescription helper (issue-year → prescribed
  max valuation rate) — the gating item for penny-exact CRVM reproduction.**
  Currently manual via `valuation_interest_rate`; mortality-basis exactness
  (Slices 1–2) is only half the reserve. Rank ahead of the cosmetic follow-ups.
- Issue-year → CSO-version selector (2001 vs 2017 CSO applicability), including
  a block that straddles the applicability boundary.
- VM-20 mortality machinery beyond the structural `max(NPR, DR)` split:
  prescribed NPR margins, company-experience credibility grading to an industry
  table, and X-factors (already a tracked NICE-TO-HAVE).
