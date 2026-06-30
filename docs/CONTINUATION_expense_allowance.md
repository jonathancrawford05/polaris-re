# Continuation: Sliding-scale expense allowances & experience refunds

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier-B **B3**
**Status:** IN PROGRESS
**Total slices:** 3 (Slice 3 split data-model-first into 3a + 3b; 3b split into
3b-1 treaty wiring + 3b-2 deal-path surfacing; 3b-2 further split into 3b-2a CLI/config
path + 3b-2b API/Excel; 3b-2b further split into 3b-2b-1 API + 3b-2b-2 Excel — see below)
**Estimated total scope:** ~3 dev-days
**Epic framing:** maintainer-confirmed (2026-06-29, PR #117 — "Option A: proceed").
B3 was promoted from a between-epics quick win to a 3-slice active epic because
the Tier-A ladder + C0 are exhausted and step 5b requires one active epic;
treat it as the blessed active epic until COMPLETE.

## Overall Goal

Give Polaris RE a real expense-allowance mechanism on its proportional
treaties: a per-treaty allowance quoted as a % of ceded premium with a
first-year vs renewal split and an optional sliding scale keyed to loss
experience, applied inside `CoinsuranceTreaty`/`YRTTreaty` as a
reinsurer→cedant transfer that preserves `net + ceded == gross`; plus an
experience-refund (profit-sharing) mechanism surfaced on the deal-pricing path.
Today the only allowance handling is `CoinsuranceTreaty.include_expense_allowance`,
a boolean that shares expenses proportionally — a crude approximation that
cannot reproduce any real large YRT/coinsurance treaty's cash flows.

## Decomposition

### Slice 1: `ExpenseAllowance` model + computation primitive
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-ckdfj4
- **PR:** (this draft)
- **ADR:** ADR-118
- **What was done:** Added `reinsurance/expense_allowance.py` with the
  `ExpenseAllowance` / `ExpenseAllowanceBand` Pydantic models and the pure
  `compute_allowance()` primitive (first-year vs renewal % of ceded premium,
  optional sliding scale selecting the renewal rate from realized-loss-ratio
  bands). Validated the scale is ascending / distinct / monotone non-increasing.
  26 unit + closed-form tests. Not wired into any treaty → goldens byte-identical.
- **Key decisions:**
  - The allowance is a fraction of **ceded premium**; first year = the first
    `months_per_year` periods.
  - Sliding scale keys off the realized loss ratio `claims.sum()/premiums.sum()`;
    the first band whose `max_loss_ratio` is not exceeded wins; above all bands →
    last (lowest) band.
  - The scale must be monotone non-increasing in loss ratio (better experience
    pays at least as much) — enforced by a `PolarisValidationError`.
  - The allowance will be applied (Slice 2) as a transfer folded into the
    existing `expenses` line — **no `CashFlowResult` contract change**.

### Slice 2: Wire into `CoinsuranceTreaty` + `YRTTreaty`
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-0elamx
- **PR:** (this draft)
- **ADR:** ADR-119
- **What was done:** Added `expense_allowance: ExpenseAllowance | None = None` to
  both `CoinsuranceTreaty` and `YRTTreaty` (default None → goldens byte-identical).
  When set, the allowance is computed on the treaty's own ceded premium stream and
  folded into the expense line (+A ceded, −A net) via the shared
  `BaseTreaty._expense_allowance_transfer()` helper, preserving
  `net + ceded == gross`. Implemented the P2 duration mapping: `ExpenseAllowance`
  gained `first_year_fraction_for_block()` (face-weighted fraction of the block in
  policy year one at each projection step) and `compute_allowance()` gained an
  optional `first_year_fraction` blend argument. New business recovers the default
  first-12-periods split; a mid-duration inforce block is charged the renewal rate
  throughout. 22 new tests (13 primitive + 9 treaty wiring).
- **Key decisions:**
  - Duration mapping chosen as option (a) — map projection month → policy duration
    from the seriatim durations on `InforceBlock`, aggregated to a face-weighted
    per-period first-year fraction. The fraction is face-weighted, not
    survivorship-weighted (deliberate first cut; exact at the all-new / all-renewal
    boundaries — see ADR-119 Out of scope).
  - Without an `InforceBlock`, the allowance falls back to the new-business
    projection-month basis (documented on `compute_allowance()`), rather than
    raising — aggregate/new-business use without a block is legitimate.
  - The legacy `CoinsuranceTreaty.include_expense_allowance` boolean and the new
    `expense_allowance` are independent, composable layers (test asserts the delta
    is identical with the proportional split on or off).
- **Depends on:** Slice 1 merged
- **Files to create/modify (original plan):**
  - `reinsurance/coinsurance.py`, `reinsurance/yrt.py` — add optional
    `expense_allowance: ExpenseAllowance | None = None` field (default None →
    current behaviour, goldens byte-identical).
  - When set, `allowance = expense_allowance.compute_allowance(ceded_premiums,
    ceded_claims)`; apply `ceded.expenses += allowance`, `net.expenses -= allowance`,
    and recompute both NCF lines so `verify_additivity` still passes.
  - `tests/test_reinsurance/` — closed-form + additivity tests.
- **Acceptance criteria:**
  - Default (no allowance) leaves every treaty output byte-identical → goldens
    unchanged.
  - With an allowance, `net + ceded == gross` still holds on premiums, claims,
    expenses, and NCF.
  - A hand-computed premium stream + known FY/renewal rates reproduces the
    expected per-period allowance and the shifted net/ceded NCF.
  - Document the interaction with `CoinsuranceTreaty.include_expense_allowance`
    (the boolean proportional path) — they are independent layers.
  - **Map projection periods → policy duration before applying the FY rate.**
    The Slice-1 primitive defines "first year" as the first `months_per_year`
    *projection* periods. That is correct only for new business projected from
    inception. The primary use case is an **inforce block** where most policies
    are mid-duration, so feeding a renewal-business stream starting at projection
    month 0 would wrongly apply the first-year rate. Slice 2 must either (a) map
    each policy's projection month to its actual policy duration (preferred, via
    the seriatim duration on `InforceBlock`), or (b) explicitly document and
    test a new-business-only assumption and guard against silent misuse on
    inforce blocks. This becomes load-bearing the moment the allowance touches
    the inforce projection. *(Source: PR #117 automated review, P2 Slice-2
    design note.)*

### Slice 3: Experience refund + CLI/API/Excel surfacing
Split data-model-first (the Slice-1 precedent) because surfacing across four
consumers (`DealConfig` / CLI / API / Excel) is a session of its own:

#### Slice 3a: `ExperienceRefund` model + computation primitive
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-tb1bch
- **PR:** (this draft)
- **ADR:** ADR-120
- **What was done:** Added `reinsurance/experience_refund.py` with the
  `ExperienceRefund` Pydantic model and the pure `experience_balance()` /
  `compute_refund()` primitives. The experience account accumulates
  `premium − claims − allowance − reinsurer_margin_pct·premium` per period
  (allowance optional, default zeros), optionally **at interest** (default 0 →
  simple sum); the refund is `refund_pct · max(0, balance − retention)`. Refund
  is non-negative (an unfavourable balance refunds nothing; deficit carryforward
  out of scope). 25 unit + closed-form tests. Not wired into any treaty →
  goldens byte-identical.
- **Key decisions:**
  - Accumulation basis (PLAN open question) resolved: optional flat interest,
    default off. Each contribution rolls forward to the final period at
    `(1+i)^(1/months_per_year)`.
  - The reinsurer margin (`reinsurer_margin_pct · ceded premium`) is the
    reinsurer's retained charge — it reduces the sharable balance.
  - A single end-of-horizon scalar refund (not per-period). Annual/periodic
    settlement timing is a Slice-3b/future refinement.
  - The refund will be applied (Slice 3b) as a terminal reinsurer→cedant
    transfer folded into `expenses`, preserving `net + ceded == gross` — **no
    `CashFlowResult` contract change** (the allowance precedent).

Slice 3b proved to be two distinct chunks once the surfacing path was surveyed:
neither the Slice-2 `expense_allowance` nor the Slice-3a refund is on the
deal-pricing path yet (`pipeline.py` / `api/main.py` only set the legacy
`include_expense_allowance` boolean), so surfacing across four consumers is a
session of its own. Following the Slice-1/3a data-model-first precedent, Slice 3b
is split into 3b-1 (treaty wiring) and 3b-2 (surfacing).

#### Slice 3b-1: Wire refund into `CoinsuranceTreaty` + `YRTTreaty`
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-yvdvdl
- **PR:** (this draft)
- **ADR:** ADR-121
- **What was done:** Added `experience_refund: ExperienceRefund | None = None` to both
  treaties (default None → goldens byte-identical). When set, the refund is a single
  terminal reinsurer→cedant transfer at the final projection period, computed via the
  new `BaseTreaty._experience_refund_transfer()` helper and folded into the expense
  line (+R ceded, −R net) so `net + ceded == gross`. The refund is computed **net of
  the expense allowance** already paid (the allowance array the treaty computed is
  threaded into `compute_refund`), so the two transfers compose additively without
  double-counting. 13 new tests (byte-identical default; additivity on both treaties;
  closed-form terminal landing + NCF shift; linearity in `refund_pct`; allowance+refund
  composition; below-retention / unfavourable → nothing).
- **Key decisions:**
  - Treaty field named `experience_refund` (mirrors the `ExperienceRefund` model, as
    `expense_allowance` mirrors `ExpenseAllowance`). The PLAN's `expense_refund` is the
    deal-path shorthand; 3b-2 maps the deal-path name onto this field.
  - Whole refund lands at the **final** period (single end-of-horizon settlement, per
    ADR-120). Per-period / annual settlement timing remains a future refinement.
  - The allowance array is threaded into the refund so the sharable balance is net of
    the allowance already paid (no double-count).

Slice 3b-2 proved larger than one quality session once surveyed (the API constructs
treaties at four call sites across four request models, plus the Excel writer), so it is
split — the epic's established decompose-don't-defer pattern:

#### Slice 3b-2a: Surface allowance/refund on the CLI config / pipeline deal path
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-lb2g3i
- **PR:** (this draft)
- **ADR:** ADR-122
- **What was done:** Added `expense_allowance: ExpenseAllowance | None = None` and
  `experience_refund: ExperienceRefund | None = None` to `DealConfig` (typed under
  `TYPE_CHECKING` to keep reinsurance out of the `core/` runtime import graph; default
  `None` → byte-identical). `build_treaty` gained matching kwargs threaded onto the
  YRT / Coinsurance treaties (ignored for Modco / gross). `_parse_config_to_pipeline_inputs`
  now parses the `deal.expense_allowance` / `deal.experience_refund` JSON blocks via the
  models' `model_validate` (malformed → `PolarisValidationError` at parse time), and
  `_build_treaty_for_pipeline` threads the deal terms into `build_treaty` on both the
  flat-rate and tabular-YRT paths. So `polaris price --config` now honours both terms
  end-to-end. 13 new tests. `DealConfig.to_dict()` deliberately omits both fields (the
  `yrt_rate_table_*` / dashboard-parity omission precedent). Golden byte-identical.
- **Key decisions:**
  - Deal-path key chosen as **`expense_allowance` / `experience_refund`** (matching the
    treaty fields and the model classes), not the PLAN's loose `expense_refund` shorthand.
    Documented in ADR-122.
  - `TYPE_CHECKING` annotation (vs `object | None`) gives the config contract real types
    while preserving the core→reinsurance layering — justified by the existing
    `build_treaty` lazy-import pattern in the same module.

Slice 3b-2b proved to be two distinct surfaces (the API request layer and the
Excel writer) once surveyed — the epic's established surface-by-surface split (cf.
3b-2 → 3b-2a/3b-2b, and the Asset/ALM 4b surfacing tail). It is split into
3b-2b-1 (API) and 3b-2b-2 (Excel):

#### Slice 3b-2b-1: Surface allowance/refund on the REST API request models
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-mfjksj
- **PR:** (this draft)
- **ADR:** ADR-123
- **What was done:** Added `expense_allowance: ExpenseAllowance | None = None` and
  `experience_refund: ExperienceRefund | None = None` to the four deal-pricing request
  models (`PriceRequest`, `ScenarioRequest`, `UQRequest`, `PortfolioDealRequest`),
  imported the models directly (the API already imports from `reinsurance/`, so no
  `TYPE_CHECKING` layering is needed — that guard exists only in `core/pipeline.py`).
  `_build_treaty` gained matching kwargs threaded onto the YRT (flat **and** tabular
  paths) / Coinsurance treaties, ignored for Modco / gross; all four `_build_treaty`
  call sites (`price`, `scenario`, `uq`, `_portfolio_from_request_deals`) pass
  `request.*` / `deal_req.*` through. Added an app-level `PolarisValidationError` → HTTP
  422 exception handler so a malformed nested allowance (non-monotone sliding scale) —
  which raises during FastAPI's request-body parsing, before any endpoint `except`
  block runs — returns a clean 422 instead of a 500. 14 new tests. Golden byte-identical.
- **Key decisions:**
  - Direct model imports (not `TYPE_CHECKING`): the API module is a `reinsurance`
    consumer already, so the `core/`-layering rationale behind ADR-122's `TYPE_CHECKING`
    annotation does not apply here.
  - The 500→422 gap on malformed request bodies is a real defect the new model-validated
    fields would introduce; fixed in-scope via one app-wide handler (ADR-123) rather than
    deferred, since shipping a feature that 500s on bad input is not "byte-identical and
    correct."

#### Slice 3b-2b-2: Surface allowance/refund on the deal-pricing Excel export
- **Status:** NEXT
- **Depends on:** Slice 3b-2b-1 merged
- **Scope:** surface both terms on the deal-pricing Excel committee workbook so a
  reviewer pricing a deal with an allowance/refund sees the terms in the packet they
  circulate. There is no existing "Deal Terms" panel in the workbook, so this means a
  new sheet (or a panel on the Summary/Assumptions sheet) rendering the allowance
  (FY/renewal %, sliding-scale bands) and refund (refund %, retention, margin) terms,
  plus threading them from the CLI `--excel-out` path. Off by default (no terms → no
  panel) → byte-identical workbook unless supplied.
  - **Files to touch (surveyed):** `utils/excel_output.py` (`DealPricingExport` +
    `write_deal_pricing_excel`), `cli.py` (the `_cohort_to_deal_pricing_export` /
    `--excel-out` call site).
  - **Naming note:** keep the same keys — `expense_allowance` / `experience_refund`.
  - **Also consider:** the dashboard input surface + `DealConfig.to_dict()` parity
    (still omitted until a dashboard surface consumes the terms).

## Context for Next Session

- Additivity is the binding constraint. The allowance MUST net to zero across
  the (net, ceded) pair — it is a transfer between the two parties, not a new
  external cash flow. Folding it into the `expenses` line (+A ceded, −A net) is
  the design that keeps the invariant and avoids a contract change.
- `BaseTreaty.verify_additivity` checks premiums, claims, and NCF (not expenses
  directly), but NCF includes expenses, so the transfer is exercised by the NCF
  check. Slice 2 tests should additionally assert expense-line additivity
  explicitly.
- The sliding scale needs the ceded claims to pick the renewal rate; in Slice 2
  pass the treaty's own ceded claims array (the reinsurer's experience drives
  its allowance).

## Open Questions (for human)

- Should the sliding scale key off the **ceded** loss ratio (current plan) or
  the **gross** block loss ratio? Default is ceded; revisit if a cedant
  submission specifies the gross basis.
- Should a future slice add a dedicated allowance line to `CashFlowResult`
  (contract change) for cleaner reporting, or is folding into `expenses`
  sufficient long-term?
