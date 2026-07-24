# Dev Session Log — 2026-07-24 (Slice 4d-3 — ARCHITECTURE + QUICKSTART docs; CLOSES EPIC A4′)

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b),
  backing docs/CONTINUATION_experience_gam.md (was IN PROGRESS)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 4d-3:
  ARCHITECTURE + QUICKSTART documentation of the experience-GAM capability end-to-end,
  HARVEST FOLLOW-UPS, and close the CONTINUATION (→ COMPLETE). **This slice CLOSES the epic.**
- **Slice:** 4d-3 of Slice 4d (final sub-slice) — epic complete
- **Branch:** `claude/loving-gauss-km5fwp` (environment-designated; `feat/auto-*` default overridden)

## Selection Rationale
Step 5 found the active epic's CONTINUATION (`experience_gam`) IN PROGRESS. **Ledger-healed (step
4b):** Slice 4d-2's **PR #155 confirmed merged** into `main` (git log `bd6d59f Merge pull request
#155`) — the CONTINUATION's "draft — awaiting review/merge" marker was stale because the routine
never merges its own PRs. Recorded `#155 — MERGED 2026-07-24 (bd6d59f)`. Cross-checked merges since
the last session log (2026-07-23 slice4d2): #154 (4d-1) and #155 (4d-2) — both experience_gam
slices, both merged; no other stale ledger entries.

With #155 merged, the epic's only remaining unchecked slice — **4d-3 (docs + close)** — is unblocked,
so per the ACTIVE-EPIC guardrail it is advanced before any fallback pick. No fallback item was
selected. Advancing the epic to close is strictly higher-value than any Tier-B/C/D fallback.

**Premise verified (step 7b).** Before writing, reproduced the claimed docs gap with `grep`:
`ARCHITECTURE.md` has **no** experience-GAM / tensor-MI / A4′ mention, and `docs/QUICKSTART.md` has
**no** `polaris experience` / experience-improvement mention — despite 15 shipped slices (PRs
#141–#155). The capability was reachable only by reading module source + per-slice ADRs. Premise
holds; the docs slice is a real gap, not a no-op.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + additive A/E GAM + export | ✅ Done | #141 |
| 2a | Frequentist tensor MI surface + `MI_x(y)` grid | ✅ Done | #142 |
| 2b-surface | Bayesian reduced-rank-GP MI surface + credible intervals | ✅ Done | #143 |
| 2b-projection | Posterior-predictive forward projection | ✅ Done | #144 |
| 2c | `ImprovementScale.CUSTOM` emission (`from_grid`) | ✅ Done | #145 |
| 3 | Hierarchical partial pooling (credibility) | ✅ Done | #146 |
| 4a | `polaris experience improvement` CLI surface | ✅ Done | #147 |
| 4b-1 | `polaris experience fit` effect-shape diagnostics | ✅ Done | #148 |
| 4b-2 | Append-only assumption versioning | ✅ Done | #149 |
| 4b-3 | Wire CUSTOM into `--config` + `AssumptionSet` | ✅ Done | #150 |
| 4c-1 | HMD / ILEC experience loaders | ✅ Done | #151 |
| 4c-2 | Insured A/E + improvement validation deck | ✅ Done | #152 |
| 4c-3 | Offline `mgcv`-via-`rpy2` oracle (dev-only) | ✅ Done | #153 |
| 4d-1 | Public `all_effects()`/`feature_ranges` + `fitted_glm_arrays()` | ✅ Done | #154 |
| 4d-2 | Static `[viz]` diagnostic plots | ✅ Done | #155 |
| 4d-3 | **ARCHITECTURE + QUICKSTART docs; CLOSES EPIC** | ✅ Done | _(this draft PR)_ |

## What Was Done
Documented the experience-GAM capability end-to-end in the two canonical entry points and closed the
A4′ epic (ADR-154). This is a **docs + ledger** slice — no source, contract, CLI, treaty, or golden
touched.

`ARCHITECTURE.md` §7 (Analytics Layer) gained an "Experience Analysis & Assumption-Setting (GAM)"
subsection: the module's role as the auditable middle layer between grouped credibility and black-box
ML; the canonical grouped-cell Lexis contract (Anchor 7 — grouping is sufficiency, not compromise);
the four design anchors (static select-base offset, A/E parameterization, three-axis identifiability,
duration-enters-twice); the four model tiers (`ExperienceGAM`, `TensorMIModel`,
`BayesianTensorMIModel` + projection, `HierarchicalMIModel`) with their backends and uncertainty
semantics; the emission path to `ImprovementScale.CUSTOM` via `from_grid` (core layering preserved);
and the versioning / CLI / config-wiring / loaders / validation-deck / oracle / `[viz]` surfaces —
each ADR-cited (ADR-139…153). A row was added to the §8 Key Design Decisions summary table.

`docs/QUICKSTART.md` §14 is a new runnable "Experience Analysis & Assumption-Setting (GAM)" section:
the canonical grouped-cell CSV schema; the `polaris experience improvement`/`fit`/`save`/`list`
workflow (frequentist vs Bayesian, forward projection, append-only versioning); driving a priced run
from a versioned basis via the `mortality` config block or the `--improvement-version` flag; the
Python API; the loaders; `polaris benchmark --pack experience`; and the `[viz]` plots. The
documented CLI options, config keys, and Python call shapes were **re-verified against the live
commands and module signatures** while writing — notably that cells (with a static `q_base`, attached
via `attach_base_rate`) go to the `TensorMIModel(cells)` **constructor** and `.fit()` takes no
argument, and that `project_improvement(horizon_years, long_term_rate, ...)` lives on the Bayesian
result. Every documented `analytics`/`viz` import was confirmed to resolve.

Ledger-healed #155 (4d-2 draft→merged) and set `CONTINUATION_experience_gam.md` Status **IN PROGRESS
→ COMPLETE**, with a "Harvest verification (epic close)" section confirming all surviving refinements
are already first-class items in the latest PRODUCT_DIRECTION. Updated the PLAN status header to
COMPLETE.

## Files Changed
- `ARCHITECTURE.md` (§7 experience-GAM subsection; §8 Key-Design-Decisions row)
- `docs/QUICKSTART.md` (§14 Experience Analysis & Assumption-Setting (GAM))
- `docs/DECISIONS.md` (ADR-154)
- `docs/CONTINUATION_experience_gam.md` (#155 ledger heal; 4d-3 DONE; Status → COMPLETE; harvest
  verification section)
- `docs/PLAN_experience_gam.md` (status header → COMPLETE)
- `docs/DEV_SESSION_LOG_2026-07-24_experience_gam_slice4d3.md` (this file)

## Tests Added
None. The deliverable is documentation; every code path it describes is already test-covered by the
15 prior slices (ADR-139…153). Correctness of the docs was verified by (a) re-running the documented
CLI `--help` surfaces and (b) importing every documented `analytics`/`viz` symbol.

## Acceptance Criteria
| Criterion (CONTINUATION Slice 4d-3) | Status | Notes |
|-----|--------|-------|
| ARCHITECTURE documents the experience-GAM capability end-to-end | ✅ | §7 subsection + §8 table row, ADR-cited |
| QUICKSTART documents the capability end-to-end (runnable) | ✅ | §14: CSV schema, CLI workflow, config wiring, Python API, loaders, viz |
| ADR added | ✅ | ADR-154 |
| HARVEST FOLLOW-UPS run before close | ✅ | Re-verified all surviving refinements present in PRODUCT_DIRECTION_2026-06-18; none newly surfaced |
| CONTINUATION → COMPLETE | ✅ | Status set; harvest verification recorded |
| Engine / goldens byte-identical | ✅ | No code changed; QA 76/76 (incl. golden CLI + pipeline) green; `polaris price` golden run OK |

## PR #156 Review Response (post-open)
The automated review APPROVED (0 P0/P1-blocking) and raised two valid findings on the QUICKSTART
§14 example I authored — both fixed in a follow-up commit on this branch:
- **[P1] non-runnable import order (fixed).** `from polaris_re.assumptions.mortality import ...` as
  the first `polaris_re` import raises a circular `ImportError` via `core/pipeline.py:26`; it only
  resolves if `polaris_re.analytics` is imported first. Reproduced it, reordered the example
  (analytics import first) with a one-line note, and re-ran the exact snippet to confirm it now runs.
  My earlier "imports resolve" check had run in a primed order that masked this.
- **[P2] phantom parameter (fixed).** Dropped the `allow_generational_base=False` parenthetical from
  the `attach_base_rate` comment — that kwarg is on `TensorMIModel`, not `attach_base_rate`.
- **Underlying circular import (filed, not fixed here).** The latent `core/pipeline.py` ↔
  `assumptions.assumption_set` circular import is pre-existing on `main` and out of this docs PR's
  scope (discovery protocol: quantify-file-ship, don't balloon the PR). Filed as a NICE-TO-HAVE
  promoted follow-up in PRODUCT_DIRECTION_2026-06-18 with the repro and the proper fix.

## Open Questions / Follow-ups
- **Latent `core/pipeline.py` circular import (filed NICE-TO-HAVE).** See the PR #156 review
  response above; harvested to PRODUCT_DIRECTION_2026-06-18.
- **PRODUCT_DIRECTION regeneration is OVERDUE (housekeeping).** `PRODUCT_DIRECTION_2026-06-18.md` is
  now ~36 days old (>30). Every session since #151 has APPENDED to it rather than regenerating
  mid-epic (the wall-clock guardrail: a full regeneration alongside a slice risks the budget). With
  the A4′ epic now **closed**, the next routine run has no in-progress epic to advance, so a full
  regeneration — list shipped since #69…#155, carry forward unresolved items, re-rank against the
  fresh `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` (8 days old), start the next Tier-A epic — is the
  **recommended sole deliverable of the next run**. This is a routine-housekeeping flag, not a
  feature follow-up.
- **Next Tier-A epic selection.** With A4′ done, step 5b will start a new epic next run from the
  COMMERCIAL_VIABILITY_REVIEW Tier-A table (respecting the recommended sequence). The review is
  fresh (no re-rank needed), so the regeneration and the next-epic PLAN can be one session's work.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced from the docs work. All A4′ refinements were
harvested during the per-slice sessions (1st/2nd-order, provenance-tagged) and remain in
PRODUCT_DIRECTION_2026-06-18 "Promoted Follow-ups".

## Impact on Golden Baselines
None. Docs-only change; no source, contract, CLI, or golden touched. The QA suite (76, including the
golden CLI and pipeline regressions) is byte-identical to the session baseline and the
`polaris price` golden run succeeds.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (on `main` post-#155 merge):
**2455 passed, 3 skipped, 112 deselected**, 0 failures — matches the recorded post-4d-2 baseline
exactly (tolerance-aware; VBT/CSO tables OK, CIA 2014 MISSING but handled — the standing baseline).
No new/changed failures → proceeded. After this slice (docs-only): test counts **unchanged**
(2455 passed); QA suite **76/76**; ruff format/check clean; `polaris price` golden run byte-identical.
