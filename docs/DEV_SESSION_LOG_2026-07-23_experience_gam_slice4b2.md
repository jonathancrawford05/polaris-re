# Dev Session Log — 2026-07-23 (experience GAM, Slice 4b-2)

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md (active Tier-A epic A4′) — the
  in-progress feature picked up by routine step 5.
- **Priority:** Tier-A epic (A4′ — Data-Driven Experience Analysis & Assumption-Setting)
- **Title:** Assumption versioning under `data/assumption_versions/`
- **Slice:** 4b-2 of Slice 4b (4b-1/4b-2/4b-3); Slice 4 of the 4-slice epic
- **Branch:** `claude/loving-gauss-yyrw5z` (environment-designated `claude/*` branch)

## Selection Rationale
The active epic's CONTINUATION is IN PROGRESS with Slice 4b-1 (PR #148) **merged**
(merge commit `df0aad0`), so Slice 4b-2 is unblocked and is the routine's mandated work
before any fallback pick (step 5b / the always-on-Epic guardrail). No fallback item was
considered. No open PRs (`list_pull_requests state=open` → `[]`), so no draft dependency
blocks the next slice.

**Ledger-heal (step 4b):** PR #148 was merged since the last session log but the CONTINUATION
still marked Slice 4b-1 "(draft — awaiting review/merge)"; healed to **MERGED 2026-07-23**
(merge commit `df0aad0`). No other merged-but-uncrossed entries found (`list_pull_requests
state=merged` shows #148 as the only merge since the 4b-1 log).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Experience-data contract + additive A/E model | ✅ Done | #141 |
| 2a | Frequentist tensor MI surface + `MI_x(y)` grid | ✅ Done | #142 |
| 2b-surface | Bayesian reduced-rank-GP credible-interval surface | ✅ Done | #143 |
| 2b-projection | CMI/MP-style mean-reverting MI projection | ✅ Done | #144 |
| 2c | `MortalityImprovement` CUSTOM-scale emission | ✅ Done | #145 |
| 3 | Hierarchical partial pooling (credibility) | ✅ Done | #146 |
| 4a | `polaris experience improvement` CLI surface | ✅ Done | #147 |
| 4b-1 | `polaris experience fit` effect-shape diagnostics CLI | ✅ Done | #148 |
| 4b-2 | Assumption versioning under `data/assumption_versions/` | ✅ Done (this PR) | — |
| 4b-3 | Wire `ImprovementScale.CUSTOM` into `--config` + `AssumptionSet` | ⏳ Next | — |
| 4c | Loaders + insured validation deck + `mgcv` oracle | 🔲 Planned | — |
| 4d | Diagnostic plots + docs (CLOSES EPIC) | 🔲 Planned | — |

## Verify Premise (step 7b)
Reproduced the gap before writing code. Ran `polaris experience improvement -e exp.csv -o
scale.json` on a synthetic grouped-cell extract and inspected the artifact: the emitted JSON
carries only `{scale, base_year, custom_ages, custom_years, custom_mi_grid,
custom_ultimate_rate}` — a bare `MortalityImprovement` with **no** study-date, credibility, or
version metadata. `data/assumption_versions/` does not exist, and `polaris experience --help`
lists no `save`/`list` commands. The premise (no versioned, provenance-tagged persistence for
the experience-derived basis) holds exactly as the CONTINUATION states.

## What Was Done
Added `src/polaris_re/assumptions/version_store.py`. `AssumptionVersion` (a `PolarisBaseModel`)
wraps an experience-derived `ImprovementScale.CUSTOM` `MortalityImprovement` with the provenance
that makes a frozen basis auditable: a pinned `study_date`, an optional `credibility` weight
(validated ∈[0,1]), optional `label`/`notes` tags, a `kind` (default `mortality_improvement`),
and a store-allocated `version_id`. A `@model_validator` rejects any non-CUSTOM scale — the
study/credibility provenance is meaningless for a built-in scale.

`AssumptionVersionStore` is an **append-only** filesystem store: records live at
`{root}/{kind}/{version_id}.json` with `version_id = {study_date.isoformat()}-{seq:03d}`
(e.g. `2024-12-31-001`). `save` allocates the next sequence for a `(kind, study_date)` pair
(`1 + max existing`), so re-saving the same study date appends a fresh version rather than
overwriting — the full history of frozen bases is preserved for audit. `load` and
`list_versions` (optionally `kind`-filtered, sorted kind → study-date → id) read it back
deterministically. Version ids key on the pinned study date + a sequence counter, never the
wall clock (ADR-074) — the store is bit-deterministic given its inputs.

CLI surface (in the existing `experience` Typer group): `polaris experience save` consumes the
`experience improvement --output` JSON (decoupled — a scale can be reviewed before it is
frozen), wraps it with `--study-date`/`--credibility`/`--label`/`--notes`, and appends it;
`polaris experience list` renders the stored history as a Rich table (id, kind, study date,
credibility, grid extent, label). `--store-dir` defaults to `$POLARIS_DATA_DIR/assumption_versions`.
Additive — engine/goldens byte-identical. ADR-147.

Validated end-to-end: `improvement -o scale.json` → two `save`s of the same study date →
`list` showed `2024-12-31-001` (cred 0.80, label blockA) and `2024-12-31-002` (both files on
disk), confirming append-only history.

## Files Changed
- `src/polaris_re/assumptions/version_store.py` — new module (`AssumptionVersion`,
  `AssumptionVersionStore`, `DEFAULT_ASSUMPTION_KIND`, `__all__`).
- `src/polaris_re/assumptions/__init__.py` — export the new public API.
- `src/polaris_re/cli.py` — `experience save` / `experience list` commands + `_resolve_store_dir`
  / `_parse_study_date` helpers; top-level `import os` and `DEFAULT_ASSUMPTION_KIND` import
  (needed as a Typer default value).
- `docs/DECISIONS.md` — ADR-147.
- `docs/CONTINUATION_experience_gam.md` (ledger-heal #148 → MERGED; Slice 4b-2 → DONE,
  Slice 4b-3 → NEXT), `docs/PRODUCT_DIRECTION_2026-06-18.md` (2 harvested NICE-TO-HAVE
  follow-ups), this session log.

## Tests Added
- `tests/test_assumptions/test_version_store.py` (12): JSON round-trip; credibility range
  validation; non-CUSTOM rejection; optional tags; id allocation + file write; append-only for
  a repeated study date (both files survive, distinct grids); per-study-date sequence scoping;
  deterministic sorted listing; kind filter; empty-store listing; missing-version load raises;
  determinism (same saves → identical ids + bytes).
- `tests/test_cli_experience_versions.py` (7): `save` persists with provenance; `save` is
  append-only (-001/-002); `list` renders stored versions; `list` empty store (exit 0);
  `save` rejects a non-CUSTOM scale; `save` rejects a bad study date; `save` on a missing file.
  All study dates pinned literals (ADR-074 guard); no wall-clock read.

## Acceptance Criteria
| Criterion (CONTINUATION Slice 4b-2) | Status | Notes |
|-------------------------------------|--------|-------|
| Persist a CUSTOM scale (the `experience improvement` JSON) under a versioned store | ✅ | `AssumptionVersionStore.save` → `{root}/{kind}/{version_id}.json` |
| Study-date + credibility tags | ✅ | `AssumptionVersion.study_date` (pinned) + `credibility` (∈[0,1]) + `label`/`notes` |
| Preserved history (append-only, never overwrite) | ✅ | per-`(kind, study_date)` sequence; both files survive a repeated study date; defensive existence guard |
| `polaris experience save` / `list` surface | ✅ | both commands in the `experience` group; `--store-dir` defaults to `$POLARIS_DATA_DIR/assumption_versions` |
| Dockerfile COPY + `.dockerignore` allowlist updated if files land under `data/` | ✅ (N/A) | No files land under `data/` — tests use `tmp_path`; allowlist untouched |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + QA suite (76) unchanged |

Full non-slow suite: **2354 passed, 3 skipped, 110 deselected**, 0 failures (+19). ruff format
+ check clean. QA suite (incl. golden regression): 76 passed.

## Open Questions / Follow-ups
- Sibling assumption kinds (lapse improvement, base mortality) reuse the `kind`-parameterised
  store contract but are not emitted/consumed anywhere — harvested as NICE-TO-HAVE.
- The store is append-only with no `remove`/`prune` or retention surface — a housekeeping
  refinement, deliberately a human decision; harvested as NICE-TO-HAVE.

## Parked Polish
None. Both harvested items this session are 1st-order follow-ups of the planned Slice-4b-2
versioning feature (promoted normally as NICE-TO-HAVE).

## Impact on Golden Baselines
None. Purely additive — a new persistence module + two CLI commands. No pricing path,
assumption contract, or golden touched. Baseline `make test` at session start: **2335 passed,
3 skipped, 110 deselected, 0 failures** — matches the recorded post-4b-1 baseline (2334) +1
(the P2-accessor test from commit `8b2cb1a`, part of merged PR #148); tolerance-aware, no
new/changed failures (the 4 CIA SOA-conversion tables were resolved by the step-2 pymort
conversion). After this slice: **2354 passed** (+19).

## Ledger / Housekeeping Note
`PRODUCT_DIRECTION_2026-06-18.md` is now **35 days old (>30)**. Consistent with the
immediately-prior slices (#142–#148), this session's harvest was **appended** to its "Promoted
Follow-ups" section rather than opening a new file, to avoid fragmenting the active epic's
harvest trail while the epic is mid-flight (Slice 4b-3/4c/4d remain). A fresh
`PRODUCT_DIRECTION` regeneration (list-shipped-since #69..#148, carry-forward unresolved, then
harvest) is **overdue and flagged for the next run** — it is a substantial standalone task and
would blow this session's wall-clock alongside the slice. The `COMMERCIAL_VIABILITY_REVIEW`
(2026-07-15) is 8 days old — fresh, no re-rank needed.
