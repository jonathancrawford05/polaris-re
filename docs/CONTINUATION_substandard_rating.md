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
- **Status:** IN PROGRESS
- **Branch:** `claude/blissful-volta-pNmtL`
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
- **Status:** PLANNED (NEXT)
- **Depends on:** Slice 1 merged
- **Files to create/modify:**
  - `src/polaris_re/products/term_life.py` — apply in `_build_rate_arrays()`.
  - `src/polaris_re/products/whole_life.py` — apply in `_build_rate_arrays()`.
  - `src/polaris_re/products/universal_life.py` — apply in rate construction.
  - `src/polaris_re/products/disability.py` — if applicable (may only apply
    multiplier to mortality decrement, not to CI/DI incidence).
- **Tests to add:**
  - Closed-form: a Policy with `multiplier=2.0` produces exactly 2x the
    PV of claims of an otherwise identical Policy (within float tolerance),
    on each product.
  - Closed-form: a $5/1000 flat extra on a $1M face, zero-multiplier policy
    produces an annual extra claim stream of ~$5,000/year scaled by `lx`.
  - Edge case: `multiplier=0.0` with `flat_extra_per_1000=0.0` produces
    exactly zero claims (no base mortality survives).
  - Edge case: `q_eff` capped at 1.0 when multiplier is extreme.
- **Acceptance criteria:**
  - TERM, WL, UL all consume the new fields.
  - Closed-form tests pass on each product.
  - Existing golden baselines unchanged (standard policies have
    multiplier=1.0 and flat_extra=0.0 by default).

### Slice 3: CLI, ingestion, and dashboard
- **Status:** PLANNED
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
   Confirm or reject before Slice 2 starts.

When all slices are DONE, update Status to COMPLETE.
