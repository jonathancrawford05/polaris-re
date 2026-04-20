# Continuation: Per-Policy Substandard Rating and Flat Extras

**Source:** PRODUCT_DIRECTION_2026-04-19.md — BLOCKER (item #3 in Recommended Next Sprint)
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~3 dev-days

## Overall Goal

Give Polaris RE the ability to price substandard business — policies issued with
extra mortality risk such as Table 2, Table 4, or a flat extra premium per
$1,000 of face amount. Without this, no reinsurer can quote a substandard deal.
The feature adds two per-policy fields (`mortality_multiplier`,
`flat_extra_per_1000`) and wires them through every product engine so that
`q_effective = q_base * multiplier + flat_extra/1000/12` is the mortality
rate used when projecting claims.

## Decomposition

### Slice 1: Data model first
- **Status:** DONE
- **Branch:** `claude/blissful-volta-pNmtL`
- **PR:** #28 (merged)
- **What is done in this slice:**
  - Add `mortality_multiplier: float = 1.0` to `Policy` (ge=0.0, le=20.0).
  - Add `flat_extra_per_1000: float = 0.0` to `Policy` (ge=0.0, le=100.0).
  - Add `InforceBlock.mortality_multiplier_vec` (float64, shape (N,)).
  - Add `InforceBlock.flat_extra_vec` (float64, shape (N,)).
  - Extend `InforceBlock.from_csv()` to read optional columns with defaults.
  - Default values (1.0, 0.0) preserve backward compatibility — no product
    engine yet consumes these fields, so existing projections and golden
    baselines are unchanged.
  - Tests: field validation (bounds, defaults), vec extraction shapes/dtypes,
    backward-compat for existing CSVs without the new columns.
  - ADR-042 records the design choice.
- **Key decisions that affect later slices:**
  - Effective mortality formula: `q_eff = q_base * multiplier + flat_extra / 1000 / 12`
    where the flat extra is expressed as $/1000 face amount per YEAR, divided
    by 12 to produce a monthly decrement probability. Slices 2 must use this
    exact formula.
  - `multiplier` is dimensionless (1.0 = standard, 2.0 = Table 2 = 200%).
  - `flat_extra` in this project is $/1000 annual; NOT $/1000 monthly.
  - Fields are on `Policy`, not on `AssumptionSet`, because substandard
    treatment is per-life and must survive filtering/aggregation.
  - `q_eff` is capped at 1.0 inside each product engine to preserve the
    invariant that mortality rates are probabilities.

### Slice 2: Wire into product engines
- **Status:** DONE (this slice)
- **Branch:** `claude/blissful-volta-rpTYA`
- **PR:** (draft; opened by this session)
- **What was done:** Applied the ADR-042 formula
  `q_eff = min(q_base * multiplier + flat_extra / 12000, 1.0)` inside
  `TermLife._build_rate_arrays()` (after mortality improvement),
  `WholeLife._build_rate_arrays()` (before the max-age override), and
  `UniversalLife._build_mortality_arrays()` (before the max-age
  override). Disability is intentionally skipped (see "Key decisions"
  below and ADR-043).
- **Files modified:**
  - `src/polaris_re/products/term_life.py`
  - `src/polaris_re/products/whole_life.py`
  - `src/polaris_re/products/universal_life.py`
- **Tests added (15):** `TestTermLifeSubstandardRating`,
  `TestWholeLifeSubstandardRating`, `TestUniversalLifeSubstandardRating`
  — five per product (default-is-identity, multiplier scales first-month
  claim exactly 2x, flat-extra first-month increment = `face * 5 / 12000`,
  zero-rating produces zero claims, extreme multiplier is capped at 1.0).
- **Acceptance criteria:**
  - TERM, WL, UL all consume the new fields.  ✅
  - Closed-form tests pass on each product.  ✅
  - Existing golden baselines unchanged (standard policies have
    multiplier=1.0 and flat_extra=0.0 by default).  ✅
- **Key decisions that affect later slices:**
  - **YRT rates remain unmultiplied.** Ceded claims already flow through
    `CashFlowResult.death_claims` (which reflects `q_eff`), so the
    reinsurer inherits rated-mortality risk through claims. Premium
    rates are not scaled by `mortality_multiplier`. A future treaty
    field can override this default without touching product engines.
  - **Disability is deferred.** CI/DI substandard rating is a morbidity
    concept, not a mortality concept. Slice 2 does not modify
    `DisabilityProduct._build_mortality_arrays`. If, during Slice 3
    ingestion, the registry shows cedant rating codes that must apply
    to CI/DI, a follow-on ADR will decide whether mortality multipliers
    should decrement active CI/DI lives.
  - **Flat extra folds into `death_claims`.** Not reported as a separate
    `CashFlowResult` line. Splitting would require a contract change
    and is out of scope here.

### Slice 3: CLI, ingestion, and dashboard
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:**
  - `src/polaris_re/utils/ingestion.py` — map cedant rating codes
    (`TABLE_2`, `TABLE_4`, `STANDARD`) to `mortality_multiplier` via a
    YAML-driven lookup.
  - `src/polaris_re/cli.py` — ensure `--config` / inforce CSV pass-through
    works with rated business end-to-end.
  - Streamlit dashboard — display per-policy rating in the inforce table;
    summary metric "% of block rated > standard".
  - ADR update if ingestion needs a new rating-code registry.

## Context for Next Session

- The monthly conversion factor for `flat_extra` uses `/ 1000 / 12` because
  `flat_extra_per_1000` is quoted as an ANNUAL $/1000 face amount, mirroring
  reinsurer practice. Do not double-divide when applying inside a monthly
  projection loop.
- `q_eff` must be clipped to `[0, 1]` via `np.minimum(q_eff, 1.0)` in every
  product engine. Negative check is unnecessary because both fields have
  `ge=0.0` validation at the Pydantic layer.
- In `_build_rate_arrays`, the multiplier and flat extra are per-policy
  (shape `(N,)`) and must be broadcast across the time dimension via
  `multiplier_vec[:, None]`.
- For `YRTTreaty`, ceded claims are a function of post-multiplier `q_eff`
  because the NAR computation is indirect through the gross cash flows.
  The treaty layer does NOT need changes — it operates on
  `CashFlowResult.death_claims` which already reflects `q_eff`.
- Policy-level YRT rate lookup (`yrt_rate * multiplier`) is an OPEN DESIGN
  QUESTION for Slice 2: production reinsurers sometimes bill YRT at
  standard rates regardless of substandard, with the extra risk absorbed by
  the cedant. Default behaviour in this slice should be: YRT rates are NOT
  multiplied — the cedant bears the extra risk unless the treaty is
  explicitly configured otherwise. Flag in PR for human confirmation.

## Open Questions (for human)

1. Should `flat_extra_per_1000` be treated as a separate cash flow line
   (reported alongside `death_claims`) or folded into the aggregate
   `death_claims` output? Slice 1 defaults to **folded** — reported in the
   same `CashFlowResult.death_claims` field. If the reinsurance committee
   wants it reported separately, we'll split the output contract in a later
   ADR.
2. Do any rating codes in the cedant's system need a `flat_extra_per_1000`
   translation (as opposed to a mortality multiplier)? Slice 3 ingestion
   registry needs confirmation.
3. Slice 2 default: YRT rates are NOT multiplied by `mortality_multiplier`.
   Implemented as default in Slice 2 (see ADR-043). Confirm before
   Slice 3 whether any cedants need a treaty-level override that bills
   rated YRT at `yrt_rate × mortality_multiplier`. If yes, Slice 3 will
   add a treaty-level opt-in flag.
4. Disability substandard (new, post-Slice-2): should CI/DI mortality
   decrements on active lives be scaled by `mortality_multiplier`? See
   ADR-043 for the current "skip until ingestion confirms" stance.

When all slices are DONE, update Status to COMPLETE.
