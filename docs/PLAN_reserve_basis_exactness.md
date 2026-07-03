# PLAN: Reserve-Basis Exactness (statutory valuation table + GAAP)

**Status:** IN PROGRESS — Slice 1 shipped 2026-07-03
**Source:** PRODUCT_DIRECTION_2026-06-18.md — the two surviving IMPORTANT
reserve-basis residuals (both 1st-order harvests of Epic 1, ADR-089/ADR-092):

1. **Statutory valuation mortality table (2001 CSO) for CRVM/VM-20.** Both
   TermLife and WholeLife CRVM value on the projection best-estimate mortality,
   not the prescribed statutory valuation table. Exact reproduction of a
   cedant's US statutory CRVM reserve — the whole point of the reserve-basis
   epic — requires a distinct `valuation_mortality` slot.
2. **GAAP (FAS 60) concrete reserve basis.** `ReserveBasis.GAAP` exists but
   selecting it raises `PolarisComputationError`. US GAAP (net-premium benefit
   reserve on locked-in assumptions + PAD) is a basis a US cedant commonly
   reports on.

**Epic derivation note.** The COMMERCIAL_VIABILITY_REVIEW_2026-06-18 Tier-A
ladder (A1 reserve basis, A2 IFRS 17 movement, A3 cross-jurisdiction capital)
plus the deferred C0 Asset/ALM epic and the Tier-B B3 expense-allowance epic
are ALL COMPLETE as of PR #123. The review is 15 days old (< 30-day staleness
trigger) but its epic queue is exhausted, so this epic is constituted from the
highest-value unshipped work it points at: the two IMPORTANT items above are
the direct continuation of A1's value proposition ("a reinsurer that cannot
reproduce the cedant's statutory reserve basis cannot trust the profit
number"). A successor viability review should be regenerated at the 30-day
mark (~2026-07-18) to re-rank the catalogue for the epic after this one.

## Overall Goal

A reinsurer pricing a US cedant's block can (a) value CRVM / VM-20-NPR on the
**prescribed statutory table** (2001 CSO) rather than the pricing
best-estimate table, and (b) select **GAAP (FAS 60)** as a concrete reserve
basis — closing the last two gaps between "a reserve on the right method" and
"the cedant's reserve, reproduced".

## Design Anchors

- `AssumptionSet.valuation_mortality: MortalityTable | None = None` is the
  single new contract slot. Default `None` → statutory bases value on the
  projection mortality exactly as today (byte-identical goldens).
- The statutory valuation q is **static** (no mortality-improvement scale —
  prescribed tables are published without projection improvement) and carries
  per-policy substandard rating (multiplier + flat extra), mirroring the
  existing rated-valuation behaviour.
- VM-20 semantics: only the **NPR floor** (= CRVM) moves to the prescribed
  table; the **deterministic reserve stays best-estimate** (anticipated
  experience) by definition.
- `NET_PREMIUM` (the default basis) is untouched — it is the engine's
  historical pricing-basis reserve, not a statutory reproduction.

## Decomposition

### Slice 1: `valuation_mortality` slot + CRVM/VM-20-NPR wiring (THIS SLICE)
- **Status:** DONE (2026-07-03)
- `AssumptionSet.valuation_mortality` optional field (backward-compat `None`).
- TermLife: statutory valuation-q builder (valuation-table lookup, no
  improvement, rating applied, zeroed post-expiry); CRVM and the VM-20 NPR
  value on it when the slot is set; VM-20 DR unchanged.
- WholeLife: `_build_valuation_mortality` / `_valuation_months_to_omega`
  parametrised by table; CRVM (and hence the VM-20 NPR) uses the valuation
  table (including its omega); VM-20 DR unchanged.
- Tests: same-table consistency (slot = projection table ≡ unset, when no
  improvement is configured), improvement isolation, conservative-table
  direction, VM-20 composition (`max(NPR_stat, DR_best_estimate)`),
  closed-form independent recomputation, byte-identity when `None`.
- Goldens: byte-identical (field defaults to `None` everywhere).

### Slice 2: Surface `valuation_mortality` end-to-end (2001 CSO)
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- `DealConfig.valuation_mortality` (table source id, e.g. `"cso_2001"`),
  CLI `--valuation-mortality`, API `valuation_mortality` field; threaded via
  `build_assumption_set` on the pipeline path.
- Integration test: CRVM on 2001 CSO vs VBT best-estimate on the golden block
  (gated `@requires_soa_tables` by table availability).
- Update `notebooks/02_reserve_basis_comparison.ipynb` with a
  prescribed-table section.
- Goldens: byte-identical (no config sets the new key).

### Slice 3: GAAP (FAS 60) basis for TermLife
- **Status:** PLANNED
- **Depends on:** Slice 2 merged (GAAP should honour `valuation_mortality`
  resolution order from day one).
- Net-premium benefit reserve on locked-in assumptions with PADs (design ADR:
  PAD structure — mortality multiplier + interest haircut — and where the PADs
  are configured). Add `GAAP` to `TermLife._supported_reserve_bases`.
- Closed-form verification vs a hand-worked FAS 60 example.

### Slice 4: GAAP (FAS 60) for WholeLife + epic close
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
- WL GAAP valued prospectively to omega (no horizon-edge collapse), reusing
  the Slice-3 PAD structure; add `GAAP` to WL supported bases.
- Selector already surfaces GAAP everywhere (ADR-092) — choosing it simply
  stops raising. Notebook + ARCHITECTURE update; HARVEST + close CONTINUATION.

## Explicitly Out of Scope (epic level)

- The NET_PREMIUM WL terminal-reserve artefact closure (rebaseline-gated,
  needs human authorization — separate IMPORTANT item in
  PRODUCT_DIRECTION_2026-06-18).
- The 20-pay expense-allowance cap for short-pay WL CRVM (NICE-TO-HAVE).
- Exact VM-20 NPR X-factors / deficiency refinements (NICE-TO-HAVE).
- Statutory valuation **interest** prescription (the engine already takes
  `valuation_interest_rate` on `ProjectionConfig`; prescribing it by
  issue-year/product is config guidance, not engine work).
