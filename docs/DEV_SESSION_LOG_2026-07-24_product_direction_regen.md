# Dev Session Log — 2026-07-24 (S0.1 PRODUCT_DIRECTION regeneration + S0.2 circular-import fix)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-06-18.md` "⏭️ Next Sprint — QUEUED" block (maintainer-directed
  2026-07-24) — **S0.1** (regeneration + Phase-7 surfacing) bundling **S0.2** (circular-import fix).
- **Priority:** Sprint 0 housekeeping / Tier-B — the routine's explicit next-run deliverable after the
  A4′ epic closed (no unstarted Tier-A "big rock" remains).
- **Title:** Regenerate the nightly PRODUCT_DIRECTION line (→ `PRODUCT_DIRECTION_2026-07-24.md`) and
  retire the latent `core` → `assumptions` circular import (ADR-155).
- **Slice:** complete (single PR; not multi-session).
- **Branch:** `claude/loving-gauss-60wrng` (environment-designated; `feat/auto-*` default overridden).
- **PR:** #157 (draft) — https://github.com/jonathancrawford05/polaris-re/pull/157

## Selection Rationale
**Step 5 (continuation check):** the only IN PROGRESS CONTINUATION is `reserve_basis_correctness`,
explicitly **DEPRIORITISED / parked** (not the active epic) — so step 5 picks up nothing. Every other
CONTINUATION is COMPLETE, including `experience_gam` (A4′ closed via PR #156, merged `faae4a3`).

**Step 5b (active epic):** **no** epic is active — A4′ was the last unstarted roadmap milestone and is
COMPLETE. The fresh `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` (9 days old, no re-rank needed) confirms
**no unstarted Tier-A item exists** (§3/§5/§7): the only Tier-A-scale candidates are the
reference-blocked AXIS/Prophet Slice 4 and an unchosen Phase-7 frontier. Per the ACTIVE-EPIC guardrail,
with no startable epic the session falls to **gated Sprint-0 fallback** and flags maintenance mode.

**Selection:** the prior session (A4′ close) + the maintainer set up an explicit post-A4′ Sprint 0 in
the 2026-06-18 file naming **S0.1 as "the next run's sole deliverable"** (regeneration is overdue — the
file is 36 days old, past the ~30-day trigger; every session since #151 appended rather than
regenerating mid-epic). S0.2 (the circular-import fix) is explicitly recommended to **bundle into the
S0.1 session** ("no epic slice competing for wall-clock"). Both selected. No other fallback item was
taken — B1/B2/B4 are deferred to S0.3 next runs.

## What Was Done
**S0.1 — regeneration.** Created `PRODUCT_DIRECTION_2026-07-24.md` superseding the 36-day-old
2026-06-18 line (which is preserved, not deleted — audit trail). It (a) lists everything shipped since
2026-06-18 — the IFRS-17-movement / cross-jurisdiction-capital / asset-ALM / expense-allowance /
reserve-basis-exactness modeling epics **and** the A1′/A2′/A3′ productization ladder **and** the A4′
experience-GAM epic (PRs #87–#156, ADRs 093–154), cross-checked against `git log` + COMPLETE
CONTINUATIONs; (b) carries forward the **102 unresolved** Promoted Follow-ups (12 IMPORTANT + 90
NICE-TO-HAVE, provenance preserved, grouped by theme) — surveyed exhaustively from the prior file, with
the 10 shipped items excluded and the CI-perf/smoke maintainer-discussion group + its
"deterministic-metrics-only-may-gate" design rule preserved; (c) **re-ranks** the catalogue against
the fresh review (Tier A: none unstarted; Tier B: B1/B2/B4; Tier C: C3/C4/C5/C6; Tier D: polish); and
(d) **surfaces the Phase-7 go/no-go** to the maintainer (AXIS/Prophet reconciliation / new product
frontier GMxB or group / stochastic ALM / multi-user persistence) and logs that the routine is now in
**maintenance mode, not growth mode** until a frontier is chosen.

**S0.2 — circular-import fix (ADR-155).** `core/pipeline.py` is the composition root and legitimately
imports from `assumptions/` (a CLAUDE.md §6 exception), but `core/__init__.py` *eagerly* re-exported
the pipeline symbols — so importing any leaf `core.*` module dragged `pipeline`, and thus a
mid-initialising `assumptions` layer, into the graph. Importing `assumptions.mortality` first therefore
raised a circular `ImportError`. Removed the eager `from polaris_re.core.pipeline import (...)` block +
its five `__all__` entries. A repo-wide search confirmed **zero** callers of the re-export (all 27
importers already use the direct `core.pipeline` path), so it was behaviour-neutral dead surface. Added
three fresh-interpreter regression tests. The *proper* fix (relocate `pipeline.py` out of `core/`) is
carried forward as a NICE-TO-HAVE.

## Verify Premise (step 7b)
- **S0.2 reproduced:** `uv run python -c "from polaris_re.assumptions.mortality import MortalityTable"`
  raised `ImportError: cannot import name 'AssumptionSet' from partially initialized module ...` via
  `core/pipeline.py:26` — premise holds. Zero re-export callers confirmed by `grep`
  (`from polaris_re.core import DealConfig/…` = 0; no `core.DealConfig` attribute access).
- **S0.1 premise:** the 2026-06-18 file is 36 days old (> 30-day trigger) and the routine has appended
  to it for six weeks — regeneration is genuinely overdue, not a no-op.

## Files Changed
- `docs/PRODUCT_DIRECTION_2026-07-24.md` (**new** — the regenerated direction line)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (ledger-heal: struck through the circular-import follow-up as
  SHIPPED / S0.2 / ADR-155)
- `src/polaris_re/core/__init__.py` (removed the eager `pipeline` re-export + `__all__` entries;
  docstring notes the layering rationale + ADR-155)
- `docs/DECISIONS.md` (**ADR-155**)
- `docs/DEV_SESSION_LOG_2026-07-24_product_direction_regen.md` (this file)

## Tests Added
- `tests/test_core/test_import_layering.py` (3 fresh-interpreter tests): (1) `assumptions.mortality`
  imports first in a clean process; (2) `import polaris_re.core` does not drag `core.pipeline` into
  `sys.modules`; (3) pipeline symbols remain reachable at their canonical path. Tests (1)+(2) fail
  against the pre-fix `__init__.py` (verified red-green via `git stash`).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Regenerated PRODUCT_DIRECTION lists shipped-since-#69…#156 | ✅ | "What Has Shipped Since 2026-06-18" table + SHIPPED list |
| Unresolved Promoted Follow-ups carried forward with provenance | ✅ | 102 items (12 IMPORTANT + 90 NICE-TO-HAVE), grouped; full prose preserved in the 2026-06-18 file |
| Catalogue re-ranked against COMMERCIAL_VIABILITY_REVIEW_2026-07-15 | ✅ | Tier A none / B1-B2-B4 / C3-C6 / D |
| Phase-7 frontier decision surfaced to maintainer | ✅ | "Decision Surfaced" section; maintenance-mode flag |
| S0.2 circular import fixed | ✅ | ADR-155; `assumptions.mortality` imports clean |
| S0.2 behaviour-neutral (zero re-export callers) | ✅ | grep-confirmed; goldens byte-identical |
| Regression test for the import layering | ✅ | 3 tests, red-green verified |
| Goldens / engine byte-identical | ✅ | QA 76/76; `polaris price` golden `flat` run OK; core 164/164 |
| ruff format + check clean | ✅ | 237 files unchanged; all checks passed |

## Open Questions / Follow-ups
- **Phase-7 go/no-go (maintainer).** The single strategic decision this regeneration surfaces.
  **Maintainer response (2026-07-24, live): still open / not yet chosen** — the routine stays in
  maintenance mode. Candidates unchanged: real AXIS/Prophet reconciliation (unblocks validation
  Slice 4), a new product frontier (GMxB / group), stochastic ALM / nested-stochastic, or multi-user
  persistence + audit. *(Carried into the new file.)*
- **Next-sprint order changed by live maintainer directive (2026-07-24).** The maintainer directed the
  next **two** routine items explicitly, ahead of the Tier-B B1/B2/B4 default:
  **S1 — proper `pipeline.py` relocation** (the architectural fix for the S0.2 layer violation; ADR-155
  shipped only the cheap symptom fix), then **S2 — an MI (mortality-improvement) page on the Streamlit
  dashboard** (folding IMPORTANT #12's dashboard half / ADR-148 + the experience-GAM diagnostics
  view / ADR-153). Both are maintenance-mode refinements → the routine stays in maintenance mode. Baked
  into `PRODUCT_DIRECTION_2026-07-24` "Recommended Next Sprint" (S1/S2/S3) + annotated on the relevant
  catalogue items. S1 is the immediate next pick; S2 follows; B1→B2→B4 become S3.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced. The regeneration only re-classified and re-grouped
existing 1st/2nd-order harvested items; ADR-155's own out-of-scope items (proper relocation; `__init__`
anti-pattern sweep) are 1st-order and promoted normally.

## Impact on Golden Baselines
None. S0.1 is docs-only. S0.2 removes dead re-export surface with zero callers → behaviour-neutral: the
QA golden suite is 76/76, the `polaris price` golden `flat` run is byte-identical, and no golden was
regenerated.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (branch `claude/loving-gauss-60wrng`,
post-#156): **2455 passed, 3 skipped, 112 deselected**, 0 failures — matches the recorded post-4d-3
baseline exactly (tolerance-aware; VBT/CSO tables OK, CIA 2014 MISSING but handled — the standing
baseline). No new/changed failures → proceeded. After this session: **2458 passed** (+3 new
import-layering tests), 3 skipped; QA 76/76; ruff clean; golden run byte-identical.
