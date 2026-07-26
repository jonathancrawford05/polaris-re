# Dev Session Log — 2026-07-26 (FW Coinsurance — Slice 1 of 2)

## Item Selected
- **Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §4 Tier-C **C3** →
  `PRODUCT_DIRECTION_2026-07-24` Tier-C (`FWCoinsuranceTreaty`). New
  `docs/PLAN_fw_coinsurance.md` + `docs/CONTINUATION_fw_coinsurance.md`.
- **Priority:** Tier-C (gated maintenance-mode fallback).
- **Title:** Funds-Withheld Coinsurance treaty — Slice 1: treaty module +
  funds-withheld interest.
- **Slice:** 1 of 2.
- **Branch:** `claude/loving-gauss-saf8oc` (environment-designated).

## Selection Rationale
**No active Tier-A epic could be advanced (step 5b), and none is startable.** The
last roadmap epic (A4′ experience-GAM) closed 2026-07-24; the post-A4′ Sprint 0
(S0.1 regeneration, S0.2/S1 pipeline layering, S2 MI dashboard, S3 Tier-B
B1/B2/B4) is fully drawn down — B1 #162, B2 #163, B4 #164 all shipped. The
`COMMERCIAL_VIABILITY_REVIEW_2026-07-15` (11 days old, < 30 → no regen) and
`PRODUCT_DIRECTION_2026-07-24` (2 days old) both record **no unstarted Tier-A
"big rock"**: the only Tier-A-scale items are the reference-blocked AXIS/Prophet
reconciliation and a Phase-7 frontier that is **awaiting a maintainer decision**
and cannot be autonomously constituted. Per the ACTIVE-EPIC guardrail, the
routine correctly falls to gated Tier-C fallback and **flags maintenance mode**.
The sole IN PROGRESS CONTINUATION (`reserve_basis_correctness`) is explicitly
parked/deprioritised.

**Why C3 over the rest of the Tier-C queue (C4/C5/C6).** By strict value-per-day,
C6 (Phase-6.3 load test, ~1–2 d) ranks highest among the equal-starred Tier-C
items. It was **not** selected: its value is a wall-clock latency gate, which the
PRODUCT_DIRECTION's own CI-perf design rule calls out as an alert-fatigue
anti-pattern ("deterministic / noise-normalized metrics may gate; raw wall-time
only informs"), and a 100-concurrent-request load test is unreliable to author in
a shared sandbox. **C3** is the strongest fit for an autonomous session on the
routine's own criteria: a self-contained new treaty module following the
established `BaseTreaty` pattern (mirrors `ModcoTreaty`/`CoinsuranceTreaty`),
closed-form verifiable, core-competency liability modeling, MEDIUM (2 slices),
additive/byte-identical until the Slice-2 surfacing. C4/C5 are perf/portfolio
plumbing (C5 ~5 d is the lowest value-per-day).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Treaty module + funds-withheld interest + `CashFlowResult` field; unit tests; ADR-163 | ✅ Done | _(this draft PR)_ |
| 2 | Surface `FWCoinsurance` on CLI / REST API / dashboard + pipeline golden | ⏳ Next | — |

## VERIFY PREMISE (step 7b)
Reproduced the gap before writing code: `grep -rn "FWCoinsurance|funds_withheld"
src/` returned nothing, and `build_treaty` (`pipeline.py`) accepted only `YRT` /
`Coinsurance` / `Modco` / gross. The treaty genuinely did not exist. Premise
holds; this is a real capability gap, not a no-op.

## What Was Done
Added funds-withheld (FW) coinsurance as a first-class treaty. FW coinsurance is
coinsurance's full proportional split of every line **including reserves**, but
the reserve-backing assets are withheld by the cedant, who credits funds-withheld
interest to the reinsurer in lieu of transferring the assets. The new
`reinsurance/fw_coinsurance.py` `FWCoinsuranceTreaty` reuses coinsurance's
proportional split and modco's interest mechanic: `funds_withheld_interest_t =
ceded_reserve_balance_t * fw_rate / 12`, folded in as a cedant→reinsurer transfer
(−net, +ceded) so `net + ceded == gross` holds exactly. `fw_rate` is the flat
`funds_withheld_rate`, overridden by an `AssetPortfolio.book_yield()` when
supplied (Option A, identical to `ModcoTreaty`), flat rate as fallback. An
`include_expense_allowance` toggle mirrors coinsurance's proportional expense
split.

The one core-contract change is a **new optional
`CashFlowResult.funds_withheld_interest` array** (`np.ndarray | None = None`),
additive and backward-compatible, following the `modco_interest`/`yrt_premiums`
precedent — flagged for human review per the guardrail. The treaty is **not**
wired into `build_treaty` (Slice 2), so all pipeline goldens are byte-identical.

## Files Changed
- `src/polaris_re/reinsurance/fw_coinsurance.py` (new — `FWCoinsuranceTreaty`)
- `src/polaris_re/reinsurance/__init__.py` (export `FWCoinsuranceTreaty`)
- `src/polaris_re/core/cashflow.py` (new optional `funds_withheld_interest` field)
- `docs/DECISIONS.md` (ADR-163)
- `docs/PLAN_fw_coinsurance.md` (new)
- `docs/CONTINUATION_fw_coinsurance.md` (new, IN PROGRESS)
- `docs/DEV_SESSION_LOG_2026-07-26_fw_coinsurance_slice1.md` (this file)

## Tests Added
- `tests/test_reinsurance/test_fw_coinsurance.py` (new — 31 tests): NCF/line
  additivity (incl. `@pytest.mark.parametrize` across five cessions); reserve
  proportional-transfer vs modco contrast; funds-withheld interest closed-form,
  both-sides-equal, rate/cession nulls, linear rate sensitivity; the
  `FW == coinsurance + interest-transfer` identity and modco interest parity;
  Option-A asset-book-yield closed form + flat-rate fallback + no-portfolio
  byte-identity; expense toggle; edge/validation (empty reserve →
  `PolarisComputationError`, full/zero cession, negative-rate & out-of-range
  rejection); package export.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `FWCoinsuranceTreaty` produces (net, ceded) with `net + ceded == gross` | ✅ | Asserted across five cessions + `verify_additivity` |
| Funds-withheld interest closed-form `ceded_reserve * rate / 12` | ✅ | Whole-vector allclose |
| Reserve transferred proportionally (distinct from modco) | ✅ | `net_reserve = gross*(1-c)`; modco contrast test |
| Asset book yield drives rate (Option A), flat fallback | ✅ | Par-bond closed form + zero-book fallback |
| Additive / goldens byte-identical (not surfaced) | ✅ | Not in `build_treaty`; `polaris price` golden run OK |
| ADR added | ✅ | ADR-163 |

## Open Questions / Follow-ups
- **New `CashFlowResult.funds_withheld_interest` field** — controlled additive
  core-contract change (optional, `None` default), flagged for human review.
  Confirm the distinct field is preferred over reusing `modco_interest`.
- **Slice 2 config surface** — reuse `build_treaty`'s existing `modco_rate` as
  the funds-withheld rate vs a dedicated `funds_withheld_rate` `DealConfig`
  field (recommend reuse; see CONTINUATION Context).
- **Optional `ExpenseAllowance` / `ExperienceRefund` layers** on FW coinsurance
  (coinsurance carries them; only the proportional expense split is modeled) —
  a future refinement, harvested below.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced.

## Impact on Golden Baselines
None. Additive-only: new module + new optional `None`-default `CashFlowResult`
field + tests; no config, treaty factory, CLI, or golden touched. `polaris price`
on `golden_config_flat.json` reproduces the committed cedant/reinsurer PV figures;
the QA golden suite is byte-identical.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (on `main`
post-#164): **2529 passed, 3 skipped, 113 deselected**, 0 failures. The 3 skips
are the absent CIA-2014 tables (pymort could not reach source in step 2) — the
standing tolerance-aware baseline (VBT/CSO OK, CIA MISSING but handled). This
exceeds the previous log's recorded 2455 passed because origin/main advanced
through PRs #158–#164 since 2026-07-24. No new/changed failures → proceeded.
After this slice: **2560 passed** (+31 new FW-coinsurance tests), 3 skipped, 0
failures; ruff format/check clean; `polaris price` golden run byte-identical.
