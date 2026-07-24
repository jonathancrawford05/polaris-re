# Dev Session Log — 2026-07-24 (S1 — relocate `pipeline.py` out of `core/`; retire the §6 layer violation)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — Recommended Next Sprint **S1**
  (maintainer-directed 2026-07-24); backing plan `docs/PLAN_pipeline_relocation.md`.
- **Priority:** Maintenance-mode (the routine is in maintenance mode until a
  Phase-7 frontier is chosen — see the direction file's "Decision Surfaced").
  Ranked ahead of the Tier-B quick wins by explicit maintainer directive.
- **Title:** Relocate the deal composition root `pipeline.py` out of the `core/`
  layer to the package top level (`polaris_re.pipeline`), retiring the CLAUDE.md
  §6 layering exception entirely (ADR-155 fixed only the symptom).
- **Slice:** Slice 1 of 2 — **complete** (Slice 2 anti-pattern sweep folded into
  Slice 1 per the PLAN; the whole feature ships this session).
- **Branch:** `claude/loving-gauss-hlpq1e` (environment-designated; the
  `feat/auto-*` default is overridden by the remote-session mandate).

## Selection Rationale
Step 5 found **no CONTINUATION IN PROGRESS** to continue (the only IN-PROGRESS
one, `reserve_basis_correctness`, is explicitly parked/deprioritised). Step 5b:
the A4′ epic closed last session (#156), and `PRODUCT_DIRECTION_2026-07-24`
records **no unstarted Tier-A epic** — the routine is in maintenance mode. The
maintainer directed the next two items explicitly, in order: **S1** (this
relocation), then **S2** (MI dashboard page). S1 has a **locked PLAN**
(`PLAN_pipeline_relocation.md`) and no CONTINUATION yet, so it is the session's
deliverable. Nothing was skipped ahead of it; the Tier-B quick wins (B1/B2/B4)
sit behind S1+S2.

**Ledger healing (step 4b).** #156 and #157 merged since the prior session log
(slice4d3 predates both); their ledger was already healed in-PR
(`PRODUCT_DIRECTION_2026-07-24` records S0.2 shipped and struck the
circular-import follow-up). Nothing stale remained to heal at session start. This
session strikes the carried-forward "Relocate `pipeline.py`" NICE-TO-HAVE as
SHIPPED (PR #158) and marks Sprint S1 done.

**Premise verified (step 7b).** Reproduced the §6 violation before writing:
`core/pipeline.py` imports `AssumptionSet`, `MortalityTable`, `LapseAssumption`,
`MortalityImprovement`, and the version store from `assumptions/` (lines 26–30)
— a layer `core/` may not import. Enumerated the real importers
(`grep -rln polaris_re.core.pipeline` → 28 non-pycache files). Premise holds; the
relocation is a real fix, not a no-op.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `git mv` + rewrite all 28 importers + docstrings + layering guards + ADR | ✅ Done | #158 |
| 2 | Anti-pattern sweep of every `__init__.py` (folded into Slice 1) | ✅ Done (folded) | #158 |

## What Was Done
`git mv src/polaris_re/core/pipeline.py src/polaris_re/pipeline.py` (history
preserved — git detects the rename). The deal composition root legitimately
imports across `core/`, `assumptions/`, `products/`, and `reinsurance/`, so its
correct home is the package top level, above every leaf layer — not inside
`core/`. With it moved, the `core` package can **no longer import `assumptions/`
at all**, and the CLAUDE.md §6 rule holds with **no exception** (ADR-155 removed
the eager-re-export *symptom*; this removes the *cause*).

Rewrote every one of the 28 in-repo importers from `polaris_re.core.pipeline` to
`polaris_re.pipeline` — CLI, REST API, all `dashboard/**` modules,
`analytics/scenario.py`, `analytics/portfolio.py`, and the
CLI/dashboard/QA/core/products/analytics test suites — plus the bare
`core.pipeline` doc/comment references. Rewrote the module docstring
(composition-root framing) and the `core/__init__.py` note (states the new home
and the retired §6 exception). Extended `tests/test_core/test_import_layering.py`
to **four** fresh-interpreter guards: (1) `assumptions.mortality` imports first
clean; (2) `import polaris_re.core` drags in neither `polaris_re.pipeline` nor
the `assumptions` layer; (3) the old `polaris_re.core.pipeline` path no longer
resolves (`importlib.util.find_spec(...) is None`); (4) the pipeline symbols are
reachable at the new canonical path. **No backward-compat shim** at the old path
(ADR-156 "no shim" — internal package, no external importers; a shim would keep
`core` importing `assumptions` and re-open the ADR-155 cycle).

**Anti-pattern sweep (Slice 2, folded in).** Audited every
`src/polaris_re/**/__init__.py` for the same eager cross-layer re-export
anti-pattern. **No other instances found** — each `__init__.py` re-exports only
modules from its own sub-package. The `core/__init__ → core.pipeline` edge was
the sole occurrence, now structurally impossible.

## Files Changed
- `src/polaris_re/pipeline.py` (moved from `src/polaris_re/core/pipeline.py` via
  `git mv`; docstring rewritten)
- `src/polaris_re/core/__init__.py` (docstring note rewritten)
- 27 importer rewrites: `src/polaris_re/cli.py`, `src/polaris_re/api/main.py`,
  `src/polaris_re/dashboard/components/{projection,state}.py`,
  `src/polaris_re/dashboard/views/{pricing,assumptions}.py`,
  `src/polaris_re/analytics/{scenario,portfolio}.py`, and 18 test files
  (`tests/test_core/**`, `tests/test_dashboard/**`, `tests/test_analytics/**`,
  `tests/qa/**`, `tests/test_cli_*`, `tests/test_products/test_whole_life_crvm_reserve.py`)
- `tests/test_core/test_import_layering.py` (4 guards; old-path-gone assertion)
- `docs/DECISIONS.md` (ADR-156)
- `docs/CONTINUATION_pipeline_relocation.md` (new; Status COMPLETE)
- `docs/PLAN_pipeline_relocation.md` (status → COMPLETE)
- `docs/PRODUCT_DIRECTION_2026-07-24.md` (S1 done; NICE-TO-HAVE struck as SHIPPED;
  decompose-internals follow-up harvested)
- `docs/DEV_SESSION_LOG_2026-07-24_pipeline_relocation.md` (this file)

## Tests Added
No new behaviour to test (pure move + import rewrite). Extended the existing
`tests/test_core/test_import_layering.py` from 3 to 4 fresh-interpreter guards,
adding `test_old_core_pipeline_path_is_gone` (the relocation invariant) and
broadening the eager-import guard to assert the `assumptions` layer is not dragged
in either. Every rewritten call site is exercised by its existing suite (all
green).

## Acceptance Criteria
| Criterion (PLAN Slice 1) | Status | Notes |
|-----------|--------|-------|
| `pipeline.py` moved out of `core/` via `git mv` (history preserved) | ✅ | `src/polaris_re/pipeline.py`; git detects rename |
| All ~30 call sites import from `polaris_re.pipeline` | ✅ | 28 non-pycache importers rewritten |
| No backward-compat shim at old path | ✅ | old path deleted; `find_spec` returns None (guarded) |
| `core/__init__` no longer references `pipeline` | ✅ | docstring updated; no import |
| Layering guards extended (old path gone; new path clean) | ✅ | 4 guards, all pass |
| ADR added | ✅ | ADR-156 (relocation, §6-exception retirement, no-shim, sweep) |
| Repo-wide `grep core.pipeline` → zero non-docs/non-guard hits | ✅ | only the intentional "old path gone" test strings remain |
| Anti-pattern sweep documented | ✅ | no other instances found (ADR-156 + this log) |
| Goldens byte-identical | ✅ | `polaris price` flat run exit 0; QA 76/76; full suite byte-identical count |
| ruff format + check clean | ✅ | 1 reformat + 18 import-order fixes applied |

## Open Questions / Follow-ups
- **Decompose the ~887-line `pipeline.py` internals** (config parsing / treaty
  construction / cohort iteration → a `composition/` package). Pure
  maintainability, no behaviour change. Harvested to
  `PRODUCT_DIRECTION_2026-07-24` Ops/architecture as NICE-TO-HAVE (1st-order,
  ADR-156 Out of scope).
- **Next routine item is S2** — the MI dashboard page
  (`docs/PLAN_mi_dashboard.md`), which opens `docs/CONTINUATION_mi_dashboard.md`.
  The Phase-7 frontier decision remains open; the routine stays in maintenance
  mode.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced. The single harvested item
(decompose internals) is 1st-order (a follow-up of the originally-planned S1).

## Impact on Golden Baselines
None. Pure module relocation + import rewrite; no source logic, no `core/` data
contract (`Policy`/`InforceBlock`/`CashFlowResult`/`ProjectionConfig`), no CLI
behaviour, no treaty, and no golden touched. `polaris price` on the `flat` golden
config is byte-identical; the QA suite (76, incl. the golden CLI + pipeline
regressions) is unchanged.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (on the
integration branch tip, post-#157): **2458 passed, 3 skipped, 112 deselected**,
0 failures (tolerance-aware; VBT/CSO tables OK, CIA 2014 MISSING → the 3 skips
are the standing baseline). Matches the prior log's recorded baseline (2455 + the
3 ADR-155 layering tests). No new/changed failures → proceeded. After this slice:
test counts **unchanged** (pure relocation; the import-layering file gained 1
test → 2459 passed expected); QA suite **76/76**; ruff clean; `polaris price`
golden run byte-identical.
