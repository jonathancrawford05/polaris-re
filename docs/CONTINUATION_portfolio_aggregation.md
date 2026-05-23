# Continuation: Portfolio Aggregation (Milestone 5.2)

**Source:** PRODUCT_DIRECTION_2026-04-19.md — IMPORTANT
**Status:** COMPLETE (Slice 2 shipped 2026-05-23)
**Total slices:** 2
**Estimated total scope:** ~5 dev-days

## Overall Goal

A reinsurer never prices a single treaty in isolation. This feature adds
a `Portfolio` aggregation layer that runs a collection of independent
reinsurance deals, aggregates their projected cash flows into a single
reinsurer-level view, and reports portfolio-level profitability (total
PV profits, total IRR) plus concentration metrics by cedant, product
type, and treaty type. When complete, the engine answers "what does my
whole assumed book look like" — not just "what does this one deal look
like".

## Decomposition

### Slice 1: `analytics/portfolio.py` core module

- **Status:** DONE
- **Branch:** claude/lucid-hawking-Upr7U
- **PR:** —
- **What was done:** New `analytics/portfolio.py` with `Portfolio`
  (builder pattern via `add_deal`), `Deal`, `DealResult`, and
  `PortfolioResult`. `Portfolio.run(hurdle_rate)` projects each deal,
  applies its treaty, profit-tests the ceded (reinsurer) cash flow, and
  aggregates: month-by-month aggregate NCF (zero-padded for deals with
  shorter horizons), total PV profits, total IRR (via `ProfitTester` on
  the aggregate), total/ceded face, aggregate ceded NAR, a per-deal
  breakdown, and concentration shares + Herfindahl indices by cedant /
  product / treaty. Unit tests cover two-deal additivity, mixed
  horizons, concentration metrics, and validation.
- **Key decisions:**
  - Portfolio = the **reinsurer's** assumed book; each deal's reinsurer
    position is the *ceded* cash flow re-viewed as NET via
    `ceded_to_reinsurer_view`.
  - Proportional treaties only (YRT / coinsurance / modco — anything
    exposing `cession_pct`). Stop-loss deferred.
  - Treaty-level `cession_pct` governs every deal; policy-level cession
    overrides are not applied (keeps `ceded_face = cession_pct × face`
    exact and consistent with the aggregated cash flows).
  - Each deal's inforce block must be single-product (validated in
    `add_deal`).
  - No core data contracts changed — purely additive new module.

### Slice 2: CLI + API integration

- **Status:** DONE
- **Branch:** claude/lucid-hawking-zkLrV
- **PR:** —
- **What was done:** `PortfolioResult.to_dict()` flattens the result for
  JSON / Rich consumption (numpy arrays → lists, per-deal breakdown
  → list of plain dicts with nested `profit_test` blocks, concentration
  grouped by dimension). `polaris portfolio run --config deals.yaml`
  loads a YAML / JSON portfolio config (`hurdle_rate` + a `deals` list,
  each deal a per-deal `mortality` / `lapse` / `deal` block plus inline
  `policies` or an `inforce_csv` reference), projects every deal,
  applies its proportional treaty, and writes the aggregated result as
  JSON. `polaris portfolio report --result result.json` re-renders the
  per-deal breakdown and three concentration tables without re-running.
  `POST /api/v1/portfolio` accepts a list of deal configs and returns a
  serialised `PortfolioResult`. YRT rate derivation in the CLI mirrors
  `polaris price`: when `treaty_type='YRT'` and no rate is supplied, a
  one-off gross projection feeds `derive_yrt_rate` so ceded premiums
  are calibrated to the block's actual claims (rather than zero, which
  would happen with a None rate / claims-only cession).
- **Key decisions:**
  - YAML and JSON are interchangeable for the portfolio config (format
    inferred from suffix); JSON keeps error messages consistent with
    the rest of the CLI, YAML is the documented primary format.
  - Per-deal config blocks reuse `_parse_config_to_pipeline_inputs`, so
    the same schema documented for `polaris price` works inside a
    portfolio's `deals[]` array unchanged.
  - `POST /api/v1/portfolio` reuses `_build_components` and `_build_treaty`
    from the existing `/api/v1/price` endpoint — no schema duplication.
    The endpoint returns a plain dict (the `to_dict()` shape) rather
    than a dedicated Pydantic response model so concentration / per-deal
    dicts pass through without coercion to fixed keys.
  - Sample portfolio config shipped at
    `data/configs/portfolio_demo.yaml` for quick CLI smoke testing.
- **Acceptance criteria:**
  - `polaris portfolio run` on a 2-deal YAML produces a JSON result
    whose `total_pv_profits` equals the sum of the per-deal PV profits.
    ✅ `test_json_output_total_equals_sum_of_per_deal_pv`
  - `polaris portfolio report` renders a per-deal table and the three
    concentration breakdowns. ✅ `test_report_re_renders_from_result_json`
  - `POST /api/v1/portfolio` round-trips a 2-deal request.
    ✅ `tests/test_api/test_portfolio.py` (8 tests).

## Context for Next Session

- The deal-config YAML schema for Slice 2 should reuse the existing
  `PipelineInputs` / `DealConfig` dataclasses in `core/pipeline.py` so a
  portfolio is just a list of single-deal configs plus a `cedant` label
  and `deal_id`. `build_pipeline` already produces the
  `(inforce, assumptions, config)` tuple from a `PipelineInputs`.
- `Portfolio.add_deal` is keyword-only. Slice 2 wires config parsing to
  it.
- `Deal`, `DealResult`, `PortfolioResult` are plain frozen dataclasses
  (mirrors `ProfitTestResult` / `ScenarioResult` style) — Slice 2's
  `to_dict()` must flatten the `ProfitTestResult` inside each
  `DealResult` (see `cli._profit_test_to_dict` for the existing
  pattern).

## Refinement Backlog (from PR #44 generality review)

The Slice 1 generality review flagged six items that are correctly out
of scope for Slice 1 but should not become "discovered surprises". They
are recorded here so later slices can plan for them.

1. **Temporal alignment — partially addressed.** Aggregation sums cash
   flows by month index, which is only valid when every deal shares a
   calendar grid. Slice 1 now *guards* this: `Portfolio.run()` rejects
   deals with mismatched `valuation_date`. The fuller fix — aggregating
   on a common calendar grid so deals with different inception dates can
   coexist — remains a follow-up. It touches the aggregation core
   (arrays are indexed by offset, not by date), so it warrants its own
   slice.
2. **Aggregate `CashFlowResult` is a thin shell.** `run()` builds the
   internal aggregate with only `gross_premiums` and `net_cash_flow`
   (all `ProfitTester` needs). Death claims, expenses, and reserves are
   left empty. This is fine while the aggregate is internal-only, but a
   portfolio-level capital model or `loss_ratio()` would need the full
   set. Cheap to add (a few more `_pad` + `np.sum` calls) — Slice 2's
   `to_dict()` should decide whether to surface aggregate claims /
   expenses / reserves, and a capital slice will need them.
3. **No portfolio-level scenario analysis.** `ScenarioRunner` stresses a
   single deal. `run()`'s iterate-then-aggregate shape extends naturally
   to a `run_scenarios()` that applies a `ScenarioAdjustment` to every
   deal before projection. Open design question: correlated vs.
   independent stresses across cedants. High-value follow-up after
   Slice 2.
4. **Deal-specific hurdle rates need a redesign, not a parameter.** PV
   profits at different discount rates do not sum. If per-deal hurdles
   are introduced, `total_pv_profits` / `total_irr` must distinguish
   "sum of per-deal PV at per-deal hurdles" from "PV of the aggregate at
   a common benchmark rate" — the aggregate `ProfitTester` pattern is
   what changes.
5. **Concentration is face-weighted only.** The `_concentration` helper
   takes generic `(label, weight)` pairs, so NAR-weighted,
   PV-premium-weighted, or capital-weighted concentration is structurally
   trivial to add — but `PortfolioResult` currently exposes only three
   face-weighted dicts + one HHI dict. A future shape like
   `concentration[dimension][weight_basis]` would generalise it.
6. **Sequential execution, append-only builder.** `_run_deal` is
   stateless and independent — trivially parallelisable — but the loop
   is sequential. There is no `remove_deal()` and no per-deal result
   caching, so every `run()` is a full re-projection. Fine for small
   books; a 50+ deal portfolio would want a cached-by-`deal_id` pattern.

## Open Questions (for human)

- None blocking. One design note: portfolio profit testing uses a
  single `hurdle_rate` for the whole book. If cedants warrant
  deal-specific hurdle rates, that would be a Slice 2+ extension (see
  Refinement Backlog item 4 for the structural implication).
