# Dev Session Log — 2026-07-28 (GAAP FAS 60 PADs on the deal path)

## Item Selected
- **Source:** `docs/PRODUCT_DIRECTION_2026-07-24.md` — **IMPORTANT #5** (a
  promoted follow-up of ADR-127/128, first-class work item per routine step 6c).
- **Priority:** IMPORTANT (gated maintenance-mode fallback; no startable Tier-A
  epic — see Selection Rationale).
- **Title:** Surface the GAAP (FAS 60) provisions for adverse deviation (PADs) on
  the deal path — `DealConfig` / CLI / REST API.
- **Slice:** complete (SMALL item — no CONTINUATION).
- **Branch:** `claude/loving-gauss-gwy4zq` (environment-designated).

## Selection Rationale
Step 5 found **no IN PROGRESS feature-advancing CONTINUATION** (the only IN
PROGRESS one, `reserve_basis_correctness`, is explicitly deprioritised/parked and
its remaining slices were demoted to NICE-TO-HAVE by the 2026-07-05 checkpoint).
Step 5b found **no startable Tier-A epic**: A4′ (experience-GAM) was the last
unstarted roadmap milestone and is COMPLETE; the AXIS/Prophet reconciliation is
reference-blocked and a Phase-7 frontier awaits a maintainer decision
(`COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7). The routine is therefore in
**documented maintenance mode** — as the last several session logs record. The
latest commercial review is 13 days old (< 30) — no regeneration needed.

Reaching gated fallback (step 6), the priority order is BLOCKER > IMPORTANT >
NICE-TO-HAVE. No BLOCKER remains; the 12 IMPORTANT promoted follow-ups are the
top tier. Among them I picked the one that is **self-contained, clearly scoped,
testable, SMALL, and a production-correctness/auditability gap**: **#5 — GAAP PADs
on the deal path**. It mirrors the just-shipped FW-coinsurance surfacing slice (an
existing engine capability unreachable from any deal surface). Skipped: #1/#2
(prescribed CSO / WL terminal-reserve — touch core reserve contracts + golden
rebaseline, MEDIUM), #6/#7/#8/#9/#10 (multi-replica ops + CI perf/smoke infra —
larger, some with dependency chains), #11 (a maintainer confirmation, not code),
#3 (expense-allowance duration mapping — moves goldens for allowance configs,
riskier). #5 is additive, default-preserving, and fully shippable in one session.

The Tier-C queue (C4/C5/C6) sits *below* the IMPORTANT follow-ups in step 6's
priority order and is left for a later maintenance-mode session.

## VERIFY PREMISE (step 7b)
Reproduced the gap before writing code: parsed a config with
`deal.gaap_mortality_pad = 1.10` / `gaap_interest_margin = 0.005` through
`_parse_config_to_pipeline_inputs` → `build_projection_config`; the resulting
`ProjectionConfig` carried the **neutral defaults** (1.0 / 0.0) — the values were
silently dropped (`DealConfig` did not even have the attributes). Confirmed the
two PADs exist on `ProjectionConfig` (ADR-127/128) and are honoured by the
TermLife/WholeLife GAAP engines, but are threaded from **no** deal surface. Premise
holds: every GAAP-basis deal priced via config/CLI/API produced a PAD-free
reserve, so a reinsurer could not reproduce a cedant's held FAS 60 reserve.

## What Was Done
Threaded both GAAP PADs through the three deal surfaces, additively and
default-preserving. `DealConfig` gained `gaap_mortality_pad` (default 1.0) and
`gaap_interest_margin` (default 0.0); `build_projection_config` threads them onto
`ProjectionConfig`, which validates the ranges (pad ≥ 1.0, margin ∈ [0, 1]). The
CLI parses both keys in **both** config schemas (legacy flat + nested `deal`),
adds `--gaap-mortality-pad` / `--gaap-interest-margin` flags (flag-over-config
precedence, eagerly validated with a clear message), and **echoes** each PAD in
the JSON summary only when non-neutral (so a run without them is byte-identical).
The REST `PriceRequest` carries both (out-of-range → 422 via Pydantic), threads
them through `_build_components`, and `PriceResponse` echoes them (always present,
like `reserve_basis`). Neutral defaults keep every existing config / CLI run / API
response byte-identical, and the PADs are consumed **only** on the GAAP reserve
basis (a padded NET_PREMIUM run equals the plain run). ADR-165 records the design.

## Files Changed
- `src/polaris_re/pipeline.py` — `DealConfig.gaap_mortality_pad` /
  `gaap_interest_margin`; threaded through `build_projection_config`.
- `src/polaris_re/cli.py` — parse both keys in both config schemas; two override
  params on `_build_pipeline_from_config`; `--gaap-mortality-pad` /
  `--gaap-interest-margin` flags + eager validation; JSON-summary echo.
- `src/polaris_re/api/main.py` — `PriceRequest` fields; `_build_components` params
  → `ProjectionConfig`; `price` handler threading; `PriceResponse` echo.
- `docs/DECISIONS.md` — ADR-165.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #5 struck (SHIPPED, pending
  merge); C3 struck (ledger-healed, PR #166 merged); ADR-165 harvest section.
- `docs/DEV_SESSION_LOG_2026-07-28_gaap_pads_deal_path.md` (this file).

## Tests Added
- `tests/test_core/test_pipeline_gaap_pads.py` (6) — `build_projection_config`
  threads both PADs; neutral defaults; range validation delegated to
  `ProjectionConfig`.
- `tests/test_cli_gaap_pads.py` (10) — default GAAP run has no PAD summary keys;
  explicit neutral byte-identical; a mortality PAD and an interest margin each move
  the priced numbers on GAAP and are echoed; PADs ignored on NET_PREMIUM;
  flag-over-config precedence; config field honoured; out-of-range flags error
  cleanly.
- `tests/test_api/test_gaap_pads.py` (7) — omitting is byte-identical to explicit
  neutral; each PAD moves `pv_profits` on GAAP and is echoed on the response;
  ignored on NET_PREMIUM; out-of-range yields 422.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `deal.gaap_mortality_pad` / `gaap_interest_margin` parse from config | ✅ | both schemas; pipeline threading test |
| `--gaap-*` CLI flags override the config, validated eagerly | ✅ | CLI flow tests |
| REST `PriceRequest` accepts & prices both PADs; echoed on response | ✅ | 7 API tests |
| A non-neutral PAD moves the GAAP-basis priced numbers | ✅ | CLI + API |
| Neutral defaults byte-identical (config / CLI / API); goldens unchanged | ✅ | `golden_flat` byte-identical; 4 baselines unchanged |
| PADs ignored on non-GAAP bases | ✅ | NET_PREMIUM equality tests |
| ADR added | ✅ | ADR-165 |

## Open Questions / Follow-ups
- Harvested to `PRODUCT_DIRECTION_2026-07-24` (NICE-TO-HAVE, 1st-order): surface
  the two PADs on the **Streamlit dashboard Deal Pricing page** +
  `DealConfig.to_dict()` round-trip (CLI/API-first per the
  `valuation_mortality` / `expense_allowance` precedent). The other two ADR-165
  out-of-scope items (duration-varying GAAP PAD structures; FAS 60 DAC /
  loss-recognition on the deal path) are already carried in the NICE-TO-HAVE GAAP
  group from ADR-127 — no new duplicates.
- **Maintenance-mode flag (routine §7):** the Phase-7 frontier remains
  unchosen; the routine stays in maintenance mode drawing down the IMPORTANT
  follow-ups then the Tier-C queue.

## Parked Polish
None. The single harvested item is a 1st-order follow-up of the originally-planned
IMPORTANT #5; no 3rd-order-or-deeper follow-ups surfaced.

## Impact on Golden Baselines
None. The change is purely additive with neutral defaults: `polaris price` on
`golden_config_flat.json` is byte-identical (no PAD keys in the summary; cedant PV
$3,513,563.42 unchanged), and all four committed golden baselines are unchanged.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start on
`claude/loving-gauss-gwy4zq` (= `main` post-#166): **2571 passed, 3 skipped, 113
deselected**, 0 failures. The 3 skips are the absent CIA-2014 tables (pymort could
not reach source in step 2) — the standing tolerance-aware baseline. Matches the
prior session log's recorded baseline pattern (VBT/CSO OK, CIA MISSING but
handled) → no new/changed failures → proceeded. After this session: **+23
GAAP-PAD surfacing tests** (pipeline 6 + CLI 10 + API 7) → **2594 passed, 3
skipped**; ruff format/check clean; `polaris price` golden run byte-identical.
