# Dev Session Log — 2026-06-19 (reserve-basis epic, slice 4)

## Item Selected
- **Source:** CONTINUATION_reserve_basis.md (active Epic A1 — Reserve-basis
  matching) — next unchecked slice.
- **Priority:** IMPORTANT (Tier-A epic, top-ranked in
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md).
- **Title:** Surface the reserve-basis selector (CLI / API / Excel / notebook).
- **Slice:** 4 of 5 — the final slice. **Closes the epic.**
- **Branch:** claude/epic-euler-sb3e44 (environment-designated).

## Selection Rationale
Step 5 found CONTINUATION_reserve_basis IN PROGRESS; slice 3b (PR #85) is merged
into main, so I continued the Epic on the designated branch with the next
unchecked slice (4, surface the selector). The ACTIVE EPIC track (step 5b)
mandates advancing the Epic before any fallback pick — no fallback considered.
No other CONTINUATION was an IN PROGRESS draft to defer. This slice completes
the epic, so HARVEST FOLLOW-UPS (step 17) ran before the CONTINUATION was set
COMPLETE (step 18).

## Decomposition Plan (multi-session)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | ReserveBasis enum + dispatch guard | ✅ Done | #81 |
| 2a | TermLife CRVM (FPT) | ✅ Done | #82 |
| 2b | WholeLife CRVM + terminal-reserve artefact | ✅ Done | #83 |
| 3a | TermLife VM-20 simplified (`max(NPR, DR)`) | ✅ Done | #84 |
| 3b | WholeLife VM-20 (to-omega DR) | ✅ Done | #85 |
| 4 | Surface basis selector (CLI/API/Excel/notebook) | ✅ Done | (this draft) |

## What Was Done
Surfaced the `ReserveBasis` selector — built into `ProjectionConfig` in Slice 1
and given concrete CRVM / VM-20 bases for Term and Whole Life in Slices 2–3 — on
the deal-pricing entry points, so a reinsurer can actually price a deal on the
cedant's reserve basis without writing Python. ADR-092.

**Config / pipeline.** `DealConfig` gained a `reserve_basis: str` field (default
`"NET_PREMIUM"`, added to `to_dict()`); `build_projection_config` coerces it to
the `ReserveBasis` enum via a new `_coerce_reserve_basis` helper (accepts the
enum or a case-insensitive string; raises `PolarisValidationError` listing the
valid values on a bad one). No core-contract change — the
`ProjectionConfig.reserve_basis` field already existed from Slice 1.

**CLI.** `polaris price` gained `--reserve-basis`, validated eagerly (clean error
+ valid list, mirroring `--capital`), threaded into
`_build_pipeline_from_config(..., reserve_basis_override=...)` and overriding any
`deal.reserve_basis` in the config (flag-over-config precedence, matching the
YRT-rate-table surfaces). Both the nested and legacy config schemas now parse
`reserve_basis`. The JSON `summary` echoes the resolved basis.

**API.** `PriceRequest` gained `reserve_basis: ReserveBasis` (default
NET_PREMIUM), threaded into `_build_components`; `PriceResponse` echoes it. An
unsupported basis for the product surfaces the `PolarisComputationError` as the
endpoint's existing HTTP 422; an invalid enum string is rejected by Pydantic
(also 422). Scoped to `/price` to mirror the CLI `polaris price` surface.

**Excel.** `DealMetaExport` gained `reserve_basis: str` (default NET_PREMIUM for
backward compatibility) and the Assumptions sheet always labels "Reserve Basis".

**Notebook.** New `notebooks/02_reserve_basis_comparison.ipynb` prices one WL
block under NET_PREMIUM / CRVM / VM20, compares the profit signature, and shows
the WL terminal-reserve artefact closing on the to-omega bases (NET_PREMIUM
reserve stays ~flat to yr20; CRVM/VM20 grade ~28× higher). Executed end-to-end
to populate outputs.

Per routine step 7b I **reproduced the premise first**: `polaris price --help`
had no `--reserve-basis` flag, the API `PriceRequest` / Excel `DealMetaExport`
had no `reserve_basis`, and a golden run reported nothing about the basis —
confirming a surfacing gap, not a logic gap. After the change, a golden CRVM run
moved the WL cedant pv_profits ($3.55M → $3.23M) while NET_PREMIUM stayed
byte-identical.

## Files Changed
- `src/polaris_re/core/pipeline.py` — `DealConfig.reserve_basis` + `to_dict`;
  `_coerce_reserve_basis`; `build_projection_config` wiring; import.
- `src/polaris_re/cli.py` — `--reserve-basis` flag + eager validation;
  `_build_pipeline_from_config` override param; config parse (both schemas);
  JSON summary echo; `DealMetaExport.reserve_basis` wiring.
- `src/polaris_re/api/main.py` — `PriceRequest.reserve_basis`,
  `PriceResponse.reserve_basis`, `_build_components` param + `/price` wiring;
  import.
- `src/polaris_re/utils/excel_output.py` — `DealMetaExport.reserve_basis`;
  "Reserve Basis" row on the Assumptions sheet.
- `notebooks/02_reserve_basis_comparison.ipynb` — new.
- `docs/DECISIONS.md` — ADR-092.
- `docs/CONTINUATION_reserve_basis.md` — Slice 4 DONE; Status COMPLETE; open
  questions resolved.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — ledger heal (PR #83/#85 numbers on
  the slice-2b/3b SHIPPED footers); three new Promoted Follow-ups (GAAP basis;
  scenario/uq selector; dashboard selector).

## Tests Added
- `tests/test_cli_reserve_basis.py` (8): default summary reports NET_PREMIUM;
  explicit NET_PREMIUM byte-identical to default; CRVM moves WL priced numbers;
  lowercase basis accepted; unknown basis errors cleanly with valid list;
  config field honoured; flag overrides config; default config is NET_PREMIUM.
- `tests/test_core/test_pipeline_reserve_basis.py` (12): `_coerce_reserve_basis`
  parametrized valid/invalid; `build_projection_config` default / flow-through /
  bad-value-raises; `to_dict` round-trips basis.
- `tests/test_api/test_reserve_basis.py` (5): default response NET_PREMIUM;
  explicit NET_PREMIUM byte-identical; CRVM moves WL pv_profits; unsupported
  GAAP → 422; invalid string → 422.
- `tests/test_utils/test_excel_output.py` (2 added): Assumptions sheet labels
  "Reserve Basis" (default NET_PREMIUM; non-default rendered verbatim).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| CLI `--reserve-basis` selects the basis | ✅ | `test_crvm_changes_priced_numbers`; flag-over-config precedence |
| API request/response carry the basis | ✅ | `PriceRequest`/`PriceResponse.reserve_basis`; 422 on unsupported |
| Excel reserve-sheet label | ✅ | "Reserve Basis" row on Assumptions sheet |
| Validation notebook compares profit signature across bases | ✅ | `02_reserve_basis_comparison.ipynb` executed; artefact closure shown |
| Default (NET_PREMIUM) goldens byte-identical | ✅ | QA golden suite passed; CLI golden price byte-identical (excl. additive metadata key) |
| Invalid basis fails cleanly | ✅ | CLI clean error + valid list; API 422 |

## Open Questions / Follow-ups
- Reserve-basis on the **`scenario` / `uq`** surfaces (CLI + API) is not wired —
  this slice covered `price` only. Promoted NICE-TO-HAVE.
- **GAAP** concrete basis is still only an enum value + guard (raises). Promoted
  IMPORTANT — US GAAP is a common cedant reporting basis.
- **Dashboard** reserve-basis control not wired (CLI/Streamlit parity). Promoted
  NICE-TO-HAVE.
- The deferred actuarial-precision items (2001 CSO valuation table, 20-pay cap,
  exact VM-20 NPR refinements, VM-20 stochastic reserve, NET_PREMIUM WL artefact
  closure) remain promoted from ADR-088/089/090/091 — unchanged this session.

## Parked Polish
None. The three new follow-ups are all 1st-order (direct follow-ups of the
originally-planned reserve-basis feature), promoted normally per step 17. No
3rd-order-or-deeper items surfaced.

## Impact on Golden Baselines
None. NET_PREMIUM is the default everywhere; the priced numbers are
byte-identical (QA golden suite passed; CLI golden price byte-identical aside
from the new additive `summary.reserve_basis` metadata key). A non-default basis
is opt-in and is not exercised by any golden, so no rebaseline. No golden
byte-comparison exists for the Excel workbook; the additive "Reserve Basis" row
leaves the label-based Excel tests unaffected.

## Baseline Note
`make test` baseline this session: **1444 passed, 0 failures, 83 deselected** —
matches the recorded slice-3b post-change baseline; no new/changed failures.
(convert-soa-tables left the 4 CIA tables MISSING as in prior sessions; the SOA
VBT / 2001 CSO tables converted OK; no CIA-dependent failures.) Post-change:
**1471 passed, 83 deselected** (+27 new reserve-basis-surfacing tests). QA suite:
**72 passed**. mypy not run locally per routine (CI's job; ~207 inherited
baseline errors).
