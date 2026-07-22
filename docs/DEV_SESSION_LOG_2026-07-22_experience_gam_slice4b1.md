# Dev Session Log — 2026-07-22

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md — active Tier-A epic A4′ (Data-Driven
  Experience Analysis; COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5, ROADMAP 6.1)
- **Priority:** Tier-A epic (IMPORTANT)
- **Title:** `polaris experience fit` — effect-shape diagnostics CLI
- **Slice:** 4b-1 (of Slice 4b sub-decomposed 4b-1/4b-2/4b-3; Slice 4b-1 complete)
- **Branch:** `claude/loving-gauss-3tkl4n`

## Selection Rationale
The routine keeps exactly one active Epic. `CONTINUATION_experience_gam` is the only
IN PROGRESS continuation, and its prior slices are all merged (Slice 4a / PR #147 merged
into `main` — the branch is even with `origin/main` at `e01db81`). Per step 5/5c the
CONTINUATION *is* the work selection, so no fallback pick was considered.

Slice 4b as written bundles three distinct capabilities — a `experience fit` diagnostics
command, versioned CUSTOM-scale persistence, and `--config`/`AssumptionSet` wiring. That is
MEDIUM/LARGE (well over one session), so following this epic's established de-risking cadence
(2a/2b/2c, 4a/4b/4c/4d) I sub-decomposed 4b into 4b-1/4b-2/4b-3 and shipped 4b-1: the
diagnostics command, which is self-contained, additive, and closes the last surface on the
Slice-1 `ExperienceGAM` (the only epic module still Python-only).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 4b-1 | `polaris experience fit` effect-shape diagnostics CLI | ✅ Done | #148 |
| 4b-2 | Assumption versioning under `data/assumption_versions/` | ⏳ Next | — |
| 4b-3 | Wire `ImprovementScale.CUSTOM` into `--config` + `AssumptionSet` | 🔲 Planned | — |

## Verify Premise
Reproduced with my own eyes before writing code: `polaris experience --help` listed only
`improvement` (no `fit`), confirming the diagnostics surface was absent. A programmatic
`ExperienceGAM(...).fit()` on synthetic cells with a `sex` factor recovered the exact 0.8
female A/E multiplier via `factor_effect` and a flat residual age smooth via `smooth_effect`
— confirming the Slice-1 API the command wires in behaves as documented.

## What Was Done
Added `polaris experience fit` to the existing `experience` Typer group. It reuses the
Slice-4a input helpers (`_load_experience_cells`, `_attach_base_rate_for_experience`), fits
the Slice-1 interpretable additive A/E GAM (`ExperienceGAM`, ADR-139), and renders each
standard feature's contribution to the A/E multiplier: a Rich summary (overall A/E,
quasi-Poisson dispersion φ, overdispersion state, cell count, active factors), a sampled
table per smooth term (attained age, select duration when present), and a per-level table
per categorical factor — every effect with a `--confidence-level` band.

Two private helpers carry the work: `_collect_experience_effects` assembles all effect
shapes into one tidy long-format frame (sampling each smooth at `--grid-points` across its
**observed** range, read from the cells frame since `GAMFitResult` does not carry the range),
and `_render_experience_fit` prints the Rich tables. `--effects-out` writes the long-format
CSV (`feature, term_type, x, x_value, multiplier, lower, upper`) — the plot-ready artifact
the Slice-4d diagnostics consume, with bands first-class so nothing is lost between fit and
plot.

The change is purely additive: a second command plus two helpers in `cli.py`, heavy imports
lazy, engine byte-identical. ADR-146 records the decision; the CONTINUATION sub-decomposes
Slice 4b and marks 4b-1 DONE (and heals the stale #146/#147 "draft" statuses to MERGED).

## Files Changed
- `src/polaris_re/cli.py` — new `experience_fit_cmd` + `_collect_experience_effects` +
  `_render_experience_fit`; added `GAMFitResult`/`SmoothEffect` to the TYPE_CHECKING import.
- `docs/DECISIONS.md` — ADR-146.
- `docs/CONTINUATION_experience_gam.md` — Slice 4b sub-decomposition (4b-1 DONE); #146/#147
  status healing.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — Promoted Follow-ups (harvest).

## Tests Added
`tests/test_cli_experience.py` (+7, all closed-form / invariant-based):
- `test_fit_reports_overall_ae_and_active_factors` — summary surfaces A/E, dispersion, factor.
- `test_fit_effects_out_recovers_factor_multiplier` — the sex contrast F/M recovers 0.75
  exactly (reference-invariant); exactly one level sits at 1.0.
- `test_fit_smooth_grid_spans_observed_range` — smooth sampled at `--grid-points` across the
  full observed age range.
- `test_fit_amount_basis` — `--basis amount` fits the face-weighted experience.
- `test_fit_table_attach_path_builds_q_base` — the `--table` attach path builds `q_base`.
- `test_fit_error_bad_basis`, `test_fit_error_missing_experience_file` — error paths, exit 1.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `polaris experience fit` fits Slice-1 `ExperienceGAM` and reports per-feature effects | ✅ | Smooth + factor tables + summary |
| Effect bands reported at `--confidence-level` | ✅ | Rendered + in `--effects-out` |
| `--effects-out` long-format CSV for Slice-4d plots | ✅ | `feature, term_type, x, x_value, multiplier, lower, upper` |
| Closed-form verification of a recovered effect | ✅ | Factor contrast F/M == 0.75 exact |
| Engine / goldens byte-identical | ✅ | QA 76 passed; golden `polaris price` unchanged |

## Open Questions / Follow-ups
- **Effects-out for the tensor MI surface too?** `experience improvement --grid-out` already
  emits the `MI_x(y)` grid long-format; Slice 4d will render both. No action needed now.
- Slice 4b-2 (versioning) will add files under `data/assumption_versions/` — remember the
  Dockerfile COPY + `.dockerignore` allowlist trap (PR #61/#66) in that PR.

## Parked Polish
None.

## Impact on Golden Baselines
None. Additive CLI command; the pricing path is untouched. The golden `polaris price`
regression and the full QA suite (76) are byte-identical to the session baseline.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) after running the step-2 pymort conversion
(SOA VBT tables present; the 4 CIA tables MISSING as usual — network-dependent, not a code
failure): **2334 passed, 3 skipped, 110 deselected**, 0 failures. The Slice-4a log recorded
**2327 passed** on the same basis, so +7 = the new `experience fit` tests, no NEW/CHANGED
failures → proceeded. (A first run before the conversion showed the 4 known SOA-missing
failures in `test_synthetic_block.py`; running step 2 resolved them, confirming they are the
standing baseline, not a regression.) QA suite: 76 passed. Golden `polaris price`: unchanged.
