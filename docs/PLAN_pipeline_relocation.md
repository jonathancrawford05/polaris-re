# Plan — Relocate `pipeline.py` out of `core/` (retire the CLAUDE.md §6 layer violation)

> **Audience.** A new Claude Code session that will execute this refactor end to
> end. Read this document fully before writing code, then read the linked
> CLAUDE.md §6 (module responsibilities) / ARCHITECTURE.md (data flow) /
> `docs/DECISIONS.md` ADR-155 sections it points at. Update the CONTINUATION +
> DECISIONS + DEV_SESSION_LOG at the end of every slice — this plan is the
> read-only spec, not the running log.
>
> **Status.** 🔲 PLANNED (not started). Queued as **Next Sprint S1**
> (maintainer-directed 2026-07-24) in `PRODUCT_DIRECTION_2026-07-24.md` — the
> immediate next routine item, ahead of the Tier-B quick wins. Running log (to
> be created by Slice 1): `docs/CONTINUATION_pipeline_relocation.md`.
>
> **Provenance.** ADR-155 "Out of scope" (the proper architectural fix; ADR-155
> shipped only the cheap symptom fix — removing the eager re-export from
> `core/__init__.py`). PR #157 review flagged the same. Maintainer directive
> 2026-07-24.

---

## 1. Goal

Move `src/polaris_re/core/pipeline.py` (the deal-config → inforce/assumptions/
config composition root, ~887 lines) **out of the `core/` layer** to
`src/polaris_re/pipeline.py`, and update every call site to import from the new
path. This **retires the CLAUDE.md §6 layering exception** — `core/` may not
import `assumptions/`, yet `core/pipeline.py` imports `AssumptionSet`,
`MortalityTable`, `LapseAssumption`, `MortalityImprovement`, and the version
store. `pipeline.py` is legitimately a *composition root* that sits **above**
`core/`, `assumptions/`, `products/`, and `reinsurance/` — its correct home is
the package top level, not inside `core/`.

ADR-155 removed the *symptom* (the eager `core/__init__.py` re-export that
dragged `pipeline` — and thus `assumptions`, mid-initialisation — into any leaf
`core.*` import). This plan removes the *cause*: with `pipeline.py` no longer
under `core/`, the `core` package can no longer import `assumptions/` at all,
and the §6 rule holds without exception.

**End state:**
1. `src/polaris_re/pipeline.py` exists (moved, not copied — `git mv` to preserve
   history); `src/polaris_re/core/pipeline.py` is gone.
2. All ~30 non-pycache call sites (src + tests + scripts) import from
   `polaris_re.pipeline`. Enumerate current importers with:
   `grep -rln "core\.pipeline\|from polaris_re.core.pipeline import" src/ tests/ scripts/ notebooks/`
   (56 hits incl. pycache; ~30 real files — CLI, API, all `dashboard/views/*`
   + `components/*`, `analytics/scenario.py`, `analytics/portfolio.py`, and the
   CLI/dashboard/QA test suites).
3. **No backward-compat shim at the old `core/pipeline.py` path** — a shim (a
   stub left at `core/pipeline.py` that re-exports the names from the new
   `polaris_re.pipeline`) would keep a `core` module importing `assumptions`,
   re-introducing the very violation this retires, and keep
   `import polaris_re.core.pipeline` working (re-opening the ADR-155 circular
   import). Update the call sites instead. The usual reason to leave a
   one-release deprecation shim at an old path — not breaking external
   importers mid-release — does not apply here: this is an internal package with
   no external importers, so rewrite the in-repo call sites and delete the old
   file outright.
4. `docs/DECISIONS.md` gains an ADR (next free number, ADR-156 at time of
   writing — confirm) recording the relocation, the §6-exception retirement, and
   the "no shim" decision.
5. The existing `tests/test_core/test_import_layering.py` guards still pass
   (they assert `import polaris_re.core` does not drag `core.pipeline`); extend
   or add an assertion that `polaris_re.core.pipeline` no longer exists and that
   `polaris_re.pipeline` imports cleanly in a fresh interpreter.

## 2. Why this work, and what it does NOT do

**Why.** The §6 layering rule is a stated invariant of the architecture; the
`core/pipeline.py` exception is the one place it is broken, and it produced a
latent circular import that only luck (import ordering) kept off the shipped
paths. ADR-155 patched the blast radius; this makes the layering honest.

**What it does NOT do.**
- Does **not** change any pipeline *behaviour* — this is a pure move + import
  rewrite. Goldens are byte-identical; no assertion changes.
- Does **not** split or refactor `pipeline.py`'s internals (that ~887-line file
  can be decomposed later; out of scope here).
- Does **not** touch the `core/` data contracts (`Policy`, `InforceBlock`,
  `CashFlowResult`, `ProjectionConfig`) — only the *location* of the composition
  root moves.

## 3. Decomposition

### Slice 1 — Relocate + rewrite all importers (the whole move)
- `git mv src/polaris_re/core/pipeline.py src/polaris_re/pipeline.py`.
- Update the module docstring (drop the "under core" framing; state it is the
  composition root above all sub-packages).
- Rewrite every importer to `from polaris_re.pipeline import (...)`.
- Confirm `core/__init__.py` no longer references `pipeline` in any form (ADR-155
  already removed the re-export; verify the docstring note still makes sense).
- Extend `tests/test_core/test_import_layering.py`: assert
  `polaris_re.core.pipeline` is absent and `polaris_re.pipeline` imports clean
  first in a fresh interpreter.
- ADR (ADR-156): relocation, §6-exception retirement, no-shim rationale.
- **Acceptance:** full suite green (byte-identical count + the new guard); QA
  76/76; `polaris price` golden `flat` run byte-identical; ruff clean; a
  repo-wide `grep` for `core.pipeline` returns **zero** non-docs hits.
- Size: SMALL/MEDIUM (mechanical import churn across ~30 files + ADR). Likely one
  session. If the import rewrite is clean and fast, fold Slice 2 in.

### Slice 2 (optional, fold into Slice 1 if time allows) — Anti-pattern sweep
- Audit every `src/polaris_re/**/__init__.py` for the same **eager cross-layer
  re-export** anti-pattern (a lower-layer package `__init__` eagerly importing a
  higher-layer or sibling-layer module, forcing it into the graph at package
  import). Fix any found the same way (drop the eager re-export; import direct).
- If none are found, record that in the ADR/session log ("swept N `__init__.py`;
  no other instances"). If several are found and fixing them is non-trivial,
  split this into its own PR and note it in the CONTINUATION.
- **Acceptance:** documented sweep result; any fix behaviour-neutral (goldens
  byte-identical).

## 4. Guardrails (from the routine + CLAUDE.md)

- Byte-identical goldens — do **not** regenerate baselines (behaviour-neutral).
- Do not change existing test assertions to make them pass.
- `git mv` (not delete+create) so history follows the file.
- No new `data/` files → no Dockerfile / `.dockerignore` obligation.
- Draft PR only; never self-merge.

## 5. Open Decisions (locked defaults; revivable by maintainer)

- **No backward-compat shim** (default, locked): update call sites directly and
  delete `core/pipeline.py`. Revive a one-release deprecation shim **at the old
  `core/pipeline.py` path** (re-exporting from `polaris_re.pipeline`) only if an
  external consumer of the old import path is discovered — accepting that such a
  shim would temporarily keep `core` importing `assumptions`.
- **Target path** `polaris_re/pipeline.py` (default). Alternative
  `polaris_re/composition/pipeline.py` if a future split is anticipated —
  not now; keep the move minimal.
