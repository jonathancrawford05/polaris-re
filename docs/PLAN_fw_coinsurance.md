# PLAN: Funds-Withheld Coinsurance (`FWCoinsuranceTreaty`)

**Status:** IN PROGRESS (Slice 1 shipped 2026-07-26)
**Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §4 Tier-C **C3**; carried into
`PRODUCT_DIRECTION_2026-07-24` Tier-C. Gated maintenance-mode fallback (no
unstarted Tier-A epic; Phase-7 frontier awaiting maintainer).
**Estimated total scope:** ~2 dev-days, 2 slices.
**Classification:** MEDIUM (new treaty module + one controlled additive
`CashFlowResult` field + surfacing).

## Overall Goal

Add funds-withheld (FW) coinsurance as a first-class reinsurance treaty. FW
coinsurance is coinsurance in which the reinsurer assumes the full proportional
share of every cash-flow line **including reserves**, but the assets backing the
ceded reserve are **withheld by the cedant** in a funds-withheld account; the
cedant credits funds-withheld interest to the reinsurer in lieu of transferring
the assets. It is the economic dual of the two existing proportional treaties:
it shares **coinsurance's reserve transfer** and **modco's interest-on-retained-
assets** mechanic. When complete, a user can price a deal on an `FWCoinsurance`
treaty from the CLI, REST API, and dashboard, exactly as they can for
Coinsurance / Modco today.

## Design Anchors

- **Reuse, don't reinvent.** The proportional split is coinsurance's; the
  interest mechanic (rate resolution, Option-A asset `book_yield()` precedence,
  both-sides-equal transfer) is modco's. The module is a standalone
  `PolarisBaseModel` + `BaseTreaty` mirroring `ModcoTreaty` for readability.
- **`net + ceded == gross` is inviolate.** The funds-withheld interest is a
  cedant→reinsurer transfer (−net, +ceded), so it cancels in the sum. Asserted
  across the cession range in every slice.
- **Additive until surfacing.** Slice 1 leaves goldens byte-identical (no config
  references the treaty). The `FWCoinsurance` golden config appears only in
  Slice 2, the surfacing slice.
- **Controlled contract change, flagged.** The one core change — a new optional
  `CashFlowResult.funds_withheld_interest` array (`None` default) — follows the
  `modco_interest` precedent and is flagged for human review per the guardrail.
- **Dates pinned** (ADR-074); **Dockerfile COPY / `.dockerignore`** updated
  in-PR for any test-referenced `data/` fixture (#61/#66 trap) — Slice 2 only if
  a golden CSV/JSON is added.

## Decomposition

### Slice 1 — Treaty module + funds-withheld interest (SHIPPED)
New `reinsurance/fw_coinsurance.py`; proportional split of all lines incl.
reserves; funds-withheld interest on the withheld ceded reserve with Option-A
book-yield precedence; `include_expense_allowance` toggle; new optional
`CashFlowResult.funds_withheld_interest` field; `__init__` export; ADR-163.
Closed-form + additivity + asset-driven + edge-case unit tests. **Not** wired
into `build_treaty` — goldens byte-identical. **~250 lines + tests.**

### Slice 2 — Surface on CLI / REST API / dashboard (NEXT)
Thread `FWCoinsurance` through `build_treaty` (and the `DealConfig.treaty_type`
schema, the CLI `--treaty-type` choices, the REST `PriceRequest` treaty enum,
and the Streamlit treaty selector). Add an `FWCoinsurance` pipeline golden config
(with Dockerfile/`.dockerignore` allowlist update if a new data file is added).
`AppTest`/CLI/API flow tests + a pipeline golden. This is the surfacing slice —
the only one that touches goldens. **~200 lines + tests.**

## Out of Scope (whole feature)

- Sliding-scale `ExpenseAllowance` / `ExperienceRefund` layers on FW coinsurance
  (coinsurance carries them; FW models only the proportional expense split).
- A stochastic / amortising funds-withheld balance distinct from the ceded
  reserve.
- "Funds-withheld modco" (FW applied to a modco-style non-transferred reserve).
- Capital-model integration nuances specific to withheld assets (the existing
  `derive_capital_nar` proportional path applies as for coinsurance).
