# PLAN: Reserve-Basis Exactness (statutory valuation table + GAAP)

**Status:** IN PROGRESS — Slices 1–2 shipped 2026-07-03, Slice 3 (GAAP FAS 60,
TermLife) shipped 2026-07-04 (Slice 4 next: GAAP for WholeLife + epic close)
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
- Also shipped (PR #124 review P2, maintainer direction): the shared
  `BaseProduct._lookup_qx_column` / `_sex_smoker_masks` mortality-lookup
  helper replacing all six per-product copies of the masked per-(sex,smoker)
  lookup (Term/WL/UL/Disability). GAAP (Slices 3–4) calls the helper.
- Goldens: byte-identical (field defaults to `None` everywhere; refactor
  verified by an empty byte-level JSON diff).

### Slice 2: Surface `valuation_mortality` end-to-end (2001 CSO)
- **Status:** DONE (2026-07-03, ADR-126 — CLI/config/API/notebook)
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
- **Status:** DONE (2026-07-04, ADR-127)
- **Depends on:** Slice 2 merged.
- Net-premium benefit reserve on locked-in assumptions with PADs (design ADR:
  PAD structure — mortality multiplier + interest haircut — and where the PADs
  are configured). Add `GAAP` to `TermLife._supported_reserve_bases`.
- Closed-form verification vs a hand-worked FAS 60 example.
- **GUARDRAIL — GAAP defines its OWN basis; it does NOT inherit the statutory
  static/no-improvement rule.** FAS 60 is a locked-in **best-estimate** reserve
  plus explicit PADs — the best-estimate legitimately includes the mortality
  improvement scale (locked in at issue). So GAAP does **not** read
  `AssumptionSet.valuation_mortality` (the prescribed statutory table) and does
  **not** suppress improvement the way `_build_statutory_valuation_q` does.
  (This supersedes the earlier "GAAP should honour `valuation_mortality`" note —
  that conflated the statutory basis rule with GAAP; see ADR-126 design
  boundary.) Reuse `load_valuation_mortality` / `_lookup_qx_column` as plumbing
  only, never the statutory basis rule.

### Slice 4: GAAP (FAS 60) for WholeLife + epic close
- **Status:** NEXT
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
  issue-year/product is config guidance, not engine work). **NOTE:** although
  out of this epic's *engine* scope, this is the gating item for penny-exact
  CRVM reproduction — `valuation_mortality` (Slices 1–2) fixes only the
  mortality half of the reserve. Sequence an issue-year → prescribed-rate helper
  before positioning "exact statutory reproduction" as complete (tracked in the
  CONTINUATION Refinement Backlog and PRODUCT_DIRECTION).
