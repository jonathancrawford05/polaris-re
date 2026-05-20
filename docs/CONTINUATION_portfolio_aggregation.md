# Continuation: Portfolio Aggregation (Milestone 5.2)

**Source:** PRODUCT_DIRECTION_2026-04-19.md — IMPORTANT
**Status:** IN PROGRESS
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

- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:**
  - `src/polaris_re/cli.py` — `polaris portfolio run --config deals.yaml`
    (YAML-driven multi-deal runner) and `polaris portfolio report`
    (Rich summary table of the per-deal breakdown + concentration).
  - `src/polaris_re/api/main.py` — `POST /api/v1/portfolio` accepting a
    list of deal configs, returning a serialised `PortfolioResult`.
  - `analytics/portfolio.py` — add a `PortfolioResult.to_dict()` for
    JSON/Rich consumption (kept out of Slice 1 to stay focused).
  - Tests: CLI portfolio command, API endpoint.
- **Acceptance criteria:**
  - `polaris portfolio run` on a 2-deal YAML produces a JSON result
    whose `total_pv_profits` equals the sum of the per-deal PV profits.
  - `polaris portfolio report` renders a per-deal table and the three
    concentration breakdowns.
  - `POST /api/v1/portfolio` round-trips a 2-deal request.

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

## Open Questions (for human)

- None blocking. One design note: portfolio profit testing uses a
  single `hurdle_rate` for the whole book. If cedants warrant
  deal-specific hurdle rates, that would be a Slice 2+ extension.
