# Dev Session Log — 2026-06-03

## Item Selected

- **Source:** PRODUCT_DIRECTION_2026-05-23.md (Promoted Follow-ups —
  NICE-TO-HAVE, "Source: ADR-064 Out of scope")
- **Priority:** NICE-TO-HAVE (highest-impact entry in the queue —
  lights up the deal-committee workflow end-to-end)
- **Title:** `polaris portfolio --scenarios` CLI + `POST
  /api/v1/portfolio/scenarios` API surfacing
- **Slice:** complete (SMALL — single-session)

## Selection Rationale

The 2026-05-23 PRODUCT_DIRECTION's recommended next pick (LICAT lapse-
risk and morbidity-risk capital components) was already shipped on
2026-06-02 (ADR-065 / PR #52), and ADR-064's "Portfolio.run_scenarios"
shipped on the same day as the file was last touched (ADR-064 / PR #51).
Both items were stale entries in the file's Promoted Follow-ups
section — PRUNE step below.

With those gone, the remaining IMPORTANT items are Reserve-basis
matching and IFRS 17 movement table — both 10+ dev-days, explicitly
flagged as Phase 5.3+ work that should be scoped as dedicated roadmap
entries rather than picked up mid-sprint.

That leaves the NICE-TO-HAVE queue. The "polaris portfolio --scenarios
CLI + API surfacing" entry stands out because it closes the
deal-committee workflow that ADR-064 opened at the analytics layer: the
internal `Portfolio.run_scenarios` helper is Python-only today and
unreachable from any user-facing surface. Surfacing it via the CLI and
the FastAPI endpoint is a 2 dev-day SMALL classification:

- Files modified: 2 source files (`cli.py`, `api/main.py`) + 2 test
  files
- Lines: ~320 source + ~395 tests
- No contract changes — `PortfolioScenarioResult.to_dict()` already
  exists from ADR-064
- Self-contained: no dependencies on unmerged PRs
- Clearly scoped: existing analytics layer defines the input / output
  contracts
- Testable end-to-end via Typer's `CliRunner` and FastAPI's `TestClient`

No conflicting open PRs (verified via local `git log origin/main` and
the absence of pending CONTINUATION work). Working tree clean before
implementation.

## What Was Done

Added a new `polaris portfolio scenarios` CLI subcommand and a new
`POST /api/v1/portfolio/scenarios` API endpoint. Both wrap
`Portfolio.run_scenarios` and return the flat
`PortfolioScenarioResult.to_dict()` shape unchanged.

**CLI:** The new subcommand accepts `--config` (the same YAML / JSON
portfolio config `portfolio run` consumes), `--scenarios` (comma-
separated names from the standard six-scenario set, or `"standard"` for
the full set — default behaviour is the standard set), `--output`,
`--hurdle-rate`, and `--align`. A new
`_resolve_scenarios_argument` helper handles argument parsing with
validation (empty, duplicate, unknown name) producing clean Rich error
messages. A new `_render_portfolio_scenarios_summary` prints a Rich
per-scenario table with PV, IRR, face, and peak ceded NAR.

**API:** The new endpoint takes a `PortfolioScenariosRequest` Pydantic
model that mirrors `PortfolioRequest` plus an optional
`scenarios: list[str] | None` field. Per-deal payload validation is
shared with the existing `POST /api/v1/portfolio` via a new private
helper `_portfolio_from_request_deals` — so the two endpoints accept
identical request shapes (no per-deal duplication of build logic) and
produce identical book objects under the hood.

**Design choice — separate `scenarios` subcommand vs. `--scenarios`
flag on `run`.** Picked the separate subcommand pattern so each command
has a single, predictable JSON shape. A `--scenarios` flag on `run`
would have made the output polymorphic — JSON consumers would have had
to dispatch on the presence of a `scenarios` key. ADR-066 documents
the trade-off.

**Out of scope (carried forward):** Streamlit dashboard scenario page,
per-deal scenario overrides (heterogeneous stresses), parallel
`run_scenarios` execution. All previously promoted and remain on the
PRODUCT_DIRECTION queue.

## Files Changed

- `src/polaris_re/cli.py` (+~200 lines: new `portfolio_scenarios_cmd`
  subcommand, `_resolve_scenarios_argument` helper,
  `_render_portfolio_scenarios_summary` helper, updated module docstring)
- `src/polaris_re/api/main.py` (+~120 lines net: new
  `PortfolioScenariosRequest` model, new `api_portfolio_scenarios`
  endpoint, shared `_portfolio_from_request_deals` helper, refactored
  existing `api_portfolio` to use the shared helper, updated module
  docstring)
- `tests/test_analytics/test_cli_portfolio.py` (+~260 lines:
  `TestPortfolioScenariosCommand` with 14 tests)
- `tests/test_api/test_portfolio.py` (+~135 lines:
  `TestPortfolioScenariosEndpoint` with 11 tests)
- `docs/DECISIONS.md` (+ADR-066, ~+135 lines)
- `docs/PRODUCT_DIRECTION_2026-05-23.md` (PRUNE: removed stale
  IMPORTANT entries for shipped ADR-064 / ADR-065 items, struck through
  the `polaris portfolio --scenarios` Promoted Follow-up, updated
  Recommended Next Sprint summary)

## Tests Added

- `tests/test_analytics/test_cli_portfolio.py::TestPortfolioScenariosCommand`
  — 14 tests covering:
  - `--scenarios standard` runs the default six-scenario set
  - Omitting `--scenarios` defaults to standard
  - Comma-separated subset filtering preserves order
  - Each scenario entry carries a full `PortfolioResult.to_dict()`
    payload
  - +10% mortality stress lowers aggregate PV vs. BASE
  - Unknown scenario name exits cleanly with the offending name in
    output
  - Per-scenario Rich table is rendered
  - `--hurdle-rate` flag overrides config for every scenario
  - `--align calendar` threads through to every scenario's aggregate
    run
  - Strict-default rejects mixed valuation dates
  - Missing config file errors cleanly
  - Invalid `--align` value rejected
  - Empty `--scenarios` value rejected
  - Duplicate scenario names rejected

- `tests/test_api/test_portfolio.py::TestPortfolioScenariosEndpoint` —
  11 tests covering:
  - 200 response with default standard set
  - All six standard names present in default response
  - Named subset filters in supplied order
  - Each entry carries full `PortfolioResult` payload
  - Mortality stress lowers PV vs. BASE
  - Unknown name returns 400 / 422 with the offending name in body
  - Duplicate names rejected
  - Empty `scenarios` list rejected with 422
  - Calendar `align` threads through to every scenario
  - Strict default rejects mixed valuation dates
  - Non-proportional treaty rejected

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `polaris portfolio scenarios` runs the standard six-scenario set | ✅ | CLI test `test_runs_standard_scenarios_on_two_deal_yaml` |
| Comma-separated subset filtering preserves order | ✅ | CLI + API tests `test_named_subset_filters_to_requested_scenarios` / `test_named_subset_filters_in_order` |
| `PortfolioScenarioResult.to_dict()` shape returned as JSON | ✅ | CLI + API tests `test_each_scenario_entry_carries_full_portfolio_result` |
| `POST /api/v1/portfolio/scenarios` accepts named scenarios | ✅ | API test `test_named_subset_filters_in_order` |
| Validation: empty / unknown / duplicate names rejected | ✅ | 6 dedicated CLI + API tests |
| `--align calendar` threads through to every scenario | ✅ | CLI + API tests `test_calendar_align_threads_through_to_scenarios` / `test_calendar_align_threads_through_to_every_scenario` |
| ADR-066 added | ✅ | `docs/DECISIONS.md` |
| Existing tests still green | ✅ | 1139 passed (was 1125 + 14 new CLI tests; API tests slow-marked) |

## Open Questions / Follow-ups

- **Embed scenario set in YAML config?** Currently the scenario set is a
  CLI flag / API field only. Embedding `scenarios: [BASE, MORT_110]`
  in the portfolio config YAML would let ops scripts pin a specific
  stress set per deal. Deferred pending a deal-committee ask.
- **Golden baseline for the new endpoint.** Existing `tests/qa/`
  golden regression tests cover single-deal pricing. A portfolio-
  scenarios golden requires a stable multi-deal fixture; out of scope
  for this slice.
- **Closed by inspection during this session (PRUNE step):**
  - "Portfolio-level scenario analysis (`Portfolio.run_scenarios`)" —
    already shipped via ADR-064 (commit 8359a2b, PR #51) but still
    listed under IMPORTANT in PRODUCT_DIRECTION. Removed.
  - "LICAT lapse-risk and morbidity-risk capital components" — shipped
    via ADR-065 (commit c88db82, PR #52) on 2026-06-02. Removed.

## Impact on Golden Baselines

None. The new CLI subcommand and API endpoint are additive surfaces
that wrap an existing analytics-layer helper (`Portfolio.run_scenarios`,
ADR-064) without altering its semantics. The shared
`_portfolio_from_request_deals` helper used by both portfolio
endpoints is a pure refactor of the existing `api_portfolio` build
phase — no behaviour change to the response shape of `POST
/api/v1/portfolio`. The existing 24 portfolio API tests + the existing
40 `tests/qa/` tests + the existing 1101 other unit tests all pass
unchanged.
