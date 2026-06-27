# Dev Session Log — 2026-06-27 (Asset/ALM CLI duration-gap surface, Epic 4 Slice 4b-1)

## Item Selected
- **Source:** `CONTINUATION_asset_alm.md` (active Epic 4 — Asset/ALM model,
  Tier-C C0 from `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`; ROADMAP 5.4) —
  Slice 4b, re-decomposed into 4b-1.
- **Priority:** Active Epic (advanced before any fallback, per routine step 5b).
- **Title:** Asset/ALM model — Slice 4b-1: CLI asset-portfolio config input +
  duration-gap output (the first ALM surfacing sub-slice).
- **Slice:** 4b-1 of 4b (4b re-decomposed into 4b-1 CLI / 4b-2 API / 4b-3
  dashboard+Excel / 4b-4 notebook).
- **Branch:** `claude/awesome-bardeen-lu9ugs` (environment-designated; the
  routine's `feat/auto-*` default is overridden by the remote-session designated
  `claude/*` branch per step 8 ENVIRONMENT OVERRIDE).

## Selection Rationale
Step 5 found `CONTINUATION_asset_alm.md` **IN PROGRESS** with Slices 1, 2, 3, 4a
all DONE and merged (git log on `main`: PR #107/#108/#109/#110; HEAD `8f97aa2`
is the PR #110 merge). Slice 4b is NEXT and unblocked (`list_pull_requests`
state=open → `[]`, so no review feedback to address, no draft-blocked epic). The
CONTINUATION's next slice IS the work selection (step 5c) — no fallback item
picked, per the one-active-Epic guardrail.

The planned Slice 4b proved LARGE on inspection — five presentation surfaces
(CLI / API / dashboard / Excel) plus a validation notebook, each needing an
asset-portfolio input threaded through its config/request. Per the routine's
allowance for a slice that proves larger than expected (the same allowance under
which Epic 3's Slice 4c was split into 4c-1/4c-2a/4c-2b/4c-2c), 4b was
re-decomposed into surface-sized sub-slices and this session ships **4b-1 — the
CLI machine surface**. The config-schema decision (how an asset portfolio is
specified in JSON) is load-bearing — the API (4b-2) and dashboard (4b-3) mirror
it — so settling it on the CLI first is the "config model first, then consumers"
pattern.

## Verify Premise (step 7b)
Reproduced before writing code that the duration gap is **not** surfaced
anywhere: `grep -ci "duration_gap|asset_portfolio|analytics.alm"` over `cli.py`,
`api/main.py`, and `pipeline.py` (DealConfig) returned **0** for all (the 5
"alm" hits in `excel_output.py` are substrings of `DealMetaExport`, not ALM).
`analytics/alm.py` exists (Slice 4a) but is imported by nothing in the pricing
path. Premise holds — the surfacing is genuinely absent.

## Decomposition Plan (Slice 4b → sub-slices)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 4a | `analytics/alm.py` duration-gap core | ✅ Done | #110 |
| 4b-1 | CLI `deal.asset_portfolio` input + duration-gap JSON/console output | ✅ Done | this PR |
| 4b-2 | API request/response duration-gap surface | ⏳ Next | — |
| 4b-3 | Dashboard + Excel presentation surfaces | 🔲 Planned | — |
| 4b-4 | ALM validation notebook | 🔲 Planned | — |

## What Was Done
Wired the asset side into the CLI pricing path as a purely additive reporting
block. `DealConfig` (`core/pipeline.py`) gained `asset_portfolio:
AssetPortfolio | None = None` and `alm_valuation_yield: float | None = None`,
both defaulting to `None` so every existing config and priced number is
byte-identical. The CLI's nested-schema config parser reads `deal.asset_portfolio`
(the existing `AssetPortfolio` JSON shape `{"bonds": [...]}`, validated by the
Pydantic model so a malformed bond raises *before* pricing) and
`deal.alm_valuation_yield`.

`_price_single_cohort` now computes `duration_gap(asset_portfolio,
liability_cash_flows(net), gap_yield)` per cohort when a portfolio is supplied,
where `gap_yield` is the explicit `alm_valuation_yield` or — by default — the
deal `discount_rate` (a single common yield isolates the asset-vs-liability
*timing* mismatch from any yield difference, per ADR-111). The result rides on a
new `CohortResult.alm_duration_gap` field, is emitted as a per-cohort
`alm_duration_gap` JSON key (mirrored at the top level for a single-cohort run,
like `cedant` / `reinsurer`), and is rendered as a Rich console table
(`_render_alm_duration_gap`) with the asset vs liability durations and the
headline duration / dollar-duration gaps. Recorded as ADR-112.

**Key correctness decision — additive, never aborts pricing.** A cohort whose
net benefit-outgo (`liability_cash_flows` = claims + lapses + expenses −
premiums) discounts to a **non-positive present value** at the valuation yield
has an *undefined* liability duration, and `duration_measures` raises
`PolarisComputationError`. This is caught per cohort; the block is skipped with
a console warning and pricing continues. This is not hypothetical: the golden
WHOLE_LIFE cohort discounts to a non-positive net-outgo PV **even at 6%**
(premiums dominate benefits in PV for the premium-paying / reserve-building
block), so it is skipped while the TERM cohort (liability modified duration
≈ 5.89 yrs) carries a full gap. A reporting add-on must never break a price run.

## Files Changed
- `src/polaris_re/core/pipeline.py` — `DealConfig.asset_portfolio`,
  `DealConfig.alm_valuation_yield`; `AssetPortfolio` import.
- `src/polaris_re/cli.py` — parse the two config fields; `AssetPortfolio` /
  `analytics.alm` imports; `CohortResult.alm_duration_gap`; `_price_single_cohort`
  computes the gap (with the graceful-skip guard); thread the portfolio through
  the cohort loop; emit the JSON key (per-cohort + single-cohort top-level);
  `_render_alm_duration_gap` Rich table; `PolarisComputationError` import.
- `tests/test_cli_alm.py` — new (12 tests).
- `docs/DECISIONS.md` — ADR-112.
- `docs/CONTINUATION_asset_alm.md` — Slice 4b re-decomposed; 4b-1 DONE, 4b-2 NEXT.
- `docs/PLAN_asset_alm.md` — status banner + Slice 4b sub-slice breakdown.
- `docs/ROADMAP.md` — Milestone 5.4 Slice 4b sub-slices.

## Tests Added
`tests/test_cli_alm.py` (12):
- **Config parsing (3):** the portfolio + yield round-trip onto `DealConfig`;
  absent portfolio leaves both fields `None`; a malformed bond (invalid coupon
  frequency) raises at parse, before pricing.
- **Duration-gap output (4):** the TERM cohort carries a block; the asset
  measures are the **exact closed forms** for a 10-year zero (Macaulay 10 yrs,
  modified `10/(1+y)`, market value `1e6·(1+y)^-10`); the default valuation
  yield equals the deal discount rate; the liability side is present and the
  gap / dollar-duration-gap identities hold.
- **Valuation-yield override (1):** an explicit `alm_valuation_yield` is honoured
  and moves the asset modified duration.
- **Purely additive (2):** absent portfolio omits the block everywhere; with vs
  without an asset side, the cedant / reinsurer / summary blocks are identical.
- **Graceful skip (1):** at a 4% yield the WHOLE_LIFE net outgo discounts to a
  non-positive PV; the block is skipped (no key) but the cohort is still priced
  and the run succeeds.
- **Single-cohort top-level mirror (1):** a one-policy TERM run sets
  `summary.n_cohorts == 1` and mirrors `alm_duration_gap` at the top level.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `deal.asset_portfolio` config input parsed + validated | ✅ | Pydantic `AssetPortfolio`; malformed bond raises at parse |
| Per-cohort `alm_duration_gap` JSON output | ✅ | + top-level mirror for single-cohort |
| Asset measures match closed forms | ✅ | 10-yr zero: Macaulay 10, modified `10/(1+y)`, MV `1e6·(1+y)^-10` |
| Default valuation yield = deal discount rate; override honoured | ✅ | both tested |
| Purely additive (default None → byte-identical) | ✅ | priced-numbers-identical test; golden run emits no block |
| Reporting block never aborts pricing | ✅ | non-positive liability PV skipped per cohort + warning |
| Rich console rendering | ✅ | `_render_alm_duration_gap` |
| Own ADR | ✅ | ADR-112 |

## Open Questions / Follow-ups
- **Canonical liability cash-flow stream (resolve in 4b-2 with the maintainer).**
  This slice surfaced the open design question concretely: the net benefit-outgo
  default (`liability_cash_flows`, ADR-111) has a **non-positive PV for
  premium-paying / reserve-building blocks** (the golden WHOLE_LIFE cohort, even
  at 6%), so its duration gap is undefined and 4b-1 skips it. The duration-gap
  feature therefore only produces output for run-off-shaped blocks (e.g. TERM)
  under this convention. A reserve-runoff or reinsurer-side liability stream
  would likely be defined for permanent business; the API slice (4b-2) should
  settle the canonical mapping. Tracked in `CONTINUATION_asset_alm.md` (IN
  PROGRESS, so in routine read-scope) — not separately promoted.
- **Reinsurer-side / result-level duration gap** — deferred with the same
  canonical-stream decision.

## Parked Polish
None. (Nothing 3rd-order-or-deeper surfaced this session.)

## Impact on Golden Baselines
None. The duration gap is computed only when `deal.asset_portfolio` is supplied
(absent in every golden config), and the new `DealConfig` fields default to
`None`. Verified: the `polaris price` golden run emits no `alm_duration_gap` and
its summary is unchanged; QA golden suite (76) green; the priced-numbers-identical
test proves the block is additive. No baseline regenerated.

## Harvest (step 17)
ADR-112 "Out of scope" yields: the API / dashboard+Excel / notebook surfaces
(= the planned Slices 4b-2 / 4b-3 / 4b-4, tracked in the PLAN / CONTINUATION) and
the canonical-liability-stream question (tracked as the CONTINUATION open-design
question, IN PROGRESS → in read scope). All already tracked — none newly promoted
(same disposition as the Slice 2 / 3 / 4a harvests). The two Slice-2 NICE-TO-HAVE
follow-ups (net-of-spread book yield; time-varying amortising earned rate) remain
in `PRODUCT_DIRECTION_2026-06-18.md`. Ledger healing (step 4b): PRs #109 (Slice 3)
and #110 (Slice 4a) merged since the last session are Epic-4 CONTINUATION-backed
slices, not discrete PRODUCT_DIRECTION queue entries — the epic stays IN PROGRESS,
correctly un-struck; nothing to heal.

## Baseline Note
Branch `claude/awesome-bardeen-lu9ugs`, base HEAD `8f97aa2` (PR #110 merge = the
real `main`; the local `origin/main` ref is stale at `8515a84`, a known pattern
noted in the CONTINUATION). Baseline fast suite (`make test` / `pytest -m "not
slow"`, exit 0): **1742 passed, 110 deselected** (CIA tables MISSING from pymort
as usual — those tests deselect, not fail; SOA + CSO converted). No NEW/CHANGED
failures vs the prior session's recorded post-change baseline, so proceeded per
the tolerance-aware check. Post-change: **1754 passed** (+12 new tests).
