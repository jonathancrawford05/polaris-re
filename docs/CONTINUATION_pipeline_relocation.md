# Continuation: Relocate `pipeline.py` out of `core/` (retire the §6 layer violation)

**Source:** PRODUCT_DIRECTION_2026-07-24.md — Recommended Next Sprint **S1**
(maintainer-directed 2026-07-24); backing plan `docs/PLAN_pipeline_relocation.md`.
**Status:** COMPLETE
**Total slices:** 2 (Slice 2 folded into Slice 1 per the PLAN — "if the import
rewrite is clean and fast, fold Slice 2 in").
**Estimated total scope:** ~0.5 dev-day (mechanical import churn + ADR + sweep).

## Overall Goal

Move the deal composition root out of the `core/` layer to the package top level
(`polaris_re.pipeline`) so that `core/` no longer imports `assumptions/` at all,
retiring the CLAUDE.md §6 layering *exception* entirely (ADR-155 only removed the
symptom — the eager re-export). Pure move + import rewrite: no pipeline behaviour,
no `core/` data contract, and no golden changes.

## Decomposition

### Slice 1: Relocate + rewrite all importers (the whole move)
- **Status:** DONE
- **Branch:** `claude/loving-gauss-hlpq1e` (environment-designated; `feat/auto-*`
  default overridden)
- **PR:** #158 (draft)
- **What was done:** `git mv src/polaris_re/core/pipeline.py
  src/polaris_re/pipeline.py` (history preserved); rewrote all 28 in-repo
  importers (`polaris_re.core.pipeline` → `polaris_re.pipeline`) across CLI, REST
  API, every `dashboard/**` module, `analytics/scenario.py`,
  `analytics/portfolio.py`, and the CLI/dashboard/QA/core/products/analytics test
  suites; rewrote the module docstring (composition-root framing) and the
  `core/__init__.py` note; extended `tests/test_core/test_import_layering.py` to
  four fresh-interpreter guards (incl. the old `core.pipeline` path no longer
  resolving via `importlib.util.find_spec`). **No backward-compat shim** at the
  old path (ADR-156 "no shim" decision — an internal package with no external
  importers).
- **Key decisions:** No shim; target path `polaris_re/pipeline.py` (not
  `composition/pipeline.py` — minimal move). `pipeline.py`'s ~887-line internals
  were **not** decomposed (out of scope; harvested NICE-TO-HAVE).

### Slice 2: Anti-pattern sweep (folded into Slice 1)
- **Status:** DONE (folded)
- **What was done:** Audited every `src/polaris_re/**/__init__.py` for the same
  eager cross-layer re-export anti-pattern (a lower-/sibling-layer package
  `__init__` eagerly importing a higher- or cross-layer module). **No other
  instances found** — each `__init__.py` re-exports only modules from its own
  sub-package. The `core/__init__ → core.pipeline` edge was the sole occurrence,
  and the relocation makes it structurally impossible. Recorded in ADR-156 and
  the session log.

## Context for Next Session

Feature complete in one session — nothing carries over. The only harvested
follow-up is a NICE-TO-HAVE to decompose the ~887-line `pipeline.py` internals
(config parsing / treaty construction / cohort iteration) into a `composition/`
package; it is promoted to `PRODUCT_DIRECTION_2026-07-24` Ops/architecture
(1st-order, ADR-156 Out of scope) and is *not* required.

Per the maintainer directive, the next routine item after this is **S2 — the MI
dashboard page** (`docs/PLAN_mi_dashboard.md`), which opens
`docs/CONTINUATION_mi_dashboard.md`.

## Open Questions (for human)

None. The plan's one open decision (no shim / target path) was locked in the
PLAN and executed as specified.

## Harvest verification (epic close)

HARVEST FOLLOW-UPS (routine step 17) ran before this CONTINUATION was set
COMPLETE:
- **ADR-156 "Out of scope"** — decompose `pipeline.py` internals → promoted as a
  NICE-TO-HAVE (1st-order) to `PRODUCT_DIRECTION_2026-07-24` Ops/architecture.
- **Anti-pattern sweep** — no instances found → no follow-up (recorded, not
  promoted).
- No Refinement Backlog / unresolved Open Questions remain on this CONTINUATION
  to promote. Ledger-healed the carried-forward "Relocate `pipeline.py`"
  NICE-TO-HAVE (struck through, SHIPPED footer, PR #158) and marked Sprint S1
  done in `PRODUCT_DIRECTION_2026-07-24`.
