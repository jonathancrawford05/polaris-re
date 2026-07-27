# Continuation: Funds-Withheld Coinsurance (`FWCoinsuranceTreaty`)

**Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §4 Tier-C **C3** /
`PRODUCT_DIRECTION_2026-07-24` Tier-C
**Status:** COMPLETE
**Total slices:** 2
**Estimated total scope:** ~2 dev-days

## Overall Goal

Add funds-withheld (FW) coinsurance as a first-class reinsurance treaty:
coinsurance's full proportional split of every line **including reserves**, with
the reserve-backing assets **withheld by the cedant** and compensated by a
funds-withheld interest credit to the reinsurer (modco's interest mechanic).
When complete, `FWCoinsurance` is priceable from the CLI, REST API, and
dashboard exactly as Coinsurance / Modco are today.

## Decomposition

### Slice 1: Treaty module + funds-withheld interest
- **Status:** DONE
- **Branch:** `claude/loving-gauss-saf8oc`
- **PR:** #165
- **What was done:** New `reinsurance/fw_coinsurance.py` `FWCoinsuranceTreaty`.
  Proportional split of premiums / claims / lapses / expenses / **reserves**
  (like coinsurance), plus a funds-withheld interest credit
  `fwi_t = ceded_reserve_balance_t * fw_rate / 12` folded in as a
  cedant→reinsurer transfer preserving `net + ceded == gross`. `fw_rate` is the
  flat `funds_withheld_rate`, overridden by an `AssetPortfolio.book_yield()`
  when supplied (Option A, identical to `ModcoTreaty`). `include_expense_allowance`
  toggle mirrors coinsurance. New optional `CashFlowResult.funds_withheld_interest`
  field (additive, `None` default). `__init__` export. ADR-163. 31 unit tests
  (closed-form, additivity across five cessions, asset-driven, expense toggle,
  edge/validation). Not wired into `build_treaty` → goldens byte-identical.
- **Key decisions:**
  - **Reserve IS transferred** (`net_reserve = gross_reserve * (1-c)`), the
    distinction from `ModcoTreaty`. This makes FW coinsurance == coinsurance +
    the interest transfer, a closed-form identity asserted in the tests.
  - The funds-withheld balance is taken **equal to the ceded reserve balance**
    (a stochastic / amortising FW balance is out of scope).
  - New `CashFlowResult.funds_withheld_interest` field rather than reusing
    `modco_interest`, for audit clarity — flagged for human review.

### Slice 2: Surface on CLI / REST API / dashboard
- **Status:** DONE
- **Branch:** `claude/loving-gauss-pdd5zq` (environment-designated)
- **PR:** (this PR)
- **Depends on:** Slice 1 merged (PR #165, merged 2026-07-27).
- **What was done:** Added the `FWCoinsurance` branch to `pipeline.build_treaty`
  and the REST `_build_treaty`, constructing
  `FWCoinsuranceTreaty(cession_pct, funds_withheld_rate=modco_rate)`. The
  dashboard Assumptions-page treaty selector now offers `FWCoinsurance` and
  reuses the modco-rate slider (relabelled "Funds-Withheld Rate (%)") for it.
  Committed `data/qa/golden_config_fw_coins.json` + `golden_fw_coins` baseline
  (the first FW golden). No Dockerfile/`.dockerignore` change needed — `data/qa/`
  is copied wholesale and the allowlist already covers `data/qa/**`. ADR-164.
- **Config-field decision (resolved):** REUSE `modco_rate` /
  `modco_interest_rate` as the funds-withheld rate (recommended path); a
  dedicated `funds_withheld_rate` field is a harvested NICE-TO-HAVE follow-up.
- **Acceptance criteria:**
  - `polaris price --config <fw-config>` produces a net/ceded split whose
    additivity holds and whose funds-withheld interest matches the module. ✅
  - The REST `/api/v1/price` and dashboard both accept and price
    `FWCoinsurance`. ✅
  - A committed `FWCoinsurance` pipeline golden reproduces within tolerance. ✅

## Refinement Backlog (harvested to PRODUCT_DIRECTION on close)

1. Dedicated `funds_withheld_rate` config/request field distinct from
   `modco_rate` (only needed if one config must express distinct modco vs FW
   rates simultaneously — a treaty-comparison surface).
2. Add `FWCoinsurance` to the dashboard **Treaty Comparison** page columns.
3. Thread `ExpenseAllowance` / `ExperienceRefund` and the `AssetPortfolio`
   book-yield path through the surfaces for FW coinsurance (shared gap with
   Modco — no surface threads an asset portfolio into a proportional treaty
   today).

## Context for Next Session

- Slice 1's module is fully tested and independent; Slice 2 is pure surfacing.
- **Config-field decision for Slice 2:** `build_treaty` already carries
  `modco_rate` (default 0.045). Simplest path is to reuse it as the
  funds-withheld rate for the `FWCoinsurance` branch (both are "interest on
  retained/withheld reserve assets"); cleaner-but-wider path is a dedicated
  `funds_withheld_rate` field on `DealConfig`. Recommend reuse for Slice 2 to
  keep the contract stable, with a follow-up to split the field if a deal ever
  needs distinct modco vs FW rates in one config.
- `derive_capital_nar` already handles the proportional (coinsurance-style)
  cession path, so capital surfaces should work for FW coinsurance without
  change; verify in Slice 2.

## Open Questions (for human)

- **New `CashFlowResult.funds_withheld_interest` field** (RESOLVED for the
  routine's purposes; still flagged for human confirmation on the merged PR
  #165) — a controlled additive core-contract change (optional, `None` default,
  backward-compatible). Shipped in Slice 1 as a distinct field (not a reuse of
  `modco_interest`) for audit clarity; carried here so the human reviewer can
  confirm the distinct-field choice.
- **Funds-withheld rate config surface** (RESOLVED) — Slice 2 reuses
  `modco_rate` / `modco_interest_rate` as the funds-withheld rate (ADR-164). A
  dedicated `funds_withheld_rate` field is a harvested NICE-TO-HAVE
  (Refinement Backlog #1).
