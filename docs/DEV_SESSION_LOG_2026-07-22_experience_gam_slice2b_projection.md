# Dev Session Log — 2026-07-22 (Slice 2b — projection)

## Item Selected
- **Source:** docs/PLAN_experience_gam.md — Tier-A epic A4′ (active epic per step 5b),
  backing docs/CONTINUATION_experience_gam.md (IN PROGRESS)
- **Priority:** Tier-A (COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §3/§5; ROADMAP 6.1)
- **Title:** Data-Driven Experience Analysis & Assumption-Setting (GAM) — Slice 2b
  (posterior-predictive forward projection), **sub-slice "projection"**: CMI/MP-style
  mean-reverting `MI_x(y)` forward projection with a posterior credible band
- **Slice:** 2b-projection of the Slice-2 HEADLINE (Slice 2 = 2a/2b/2c; 2b split
  surface/projection on 2026-07-22)
- **Branch:** `claude/loving-gauss-koxn1s`

## Selection Rationale
Step 5 found the active epic's CONTINUATION (`experience_gam`) IN PROGRESS.
Ledger-healed (step 4b): Slice 2b-surface's **PR #143 confirmed merged** into `main`
(git log shows merge commit `4ed7019`; GitHub MCP `merged_at` set) — the CONTINUATION's
"draft — awaiting review/merge" marker was stale because the routine never merges its own
PRs. Recorded `#143 — MERGED 2026-07-22`. Cross-checked #141/#142 (both already recorded
merged); no other stale ledger entries. No open PRs.

With Slice 2b-surface merged, the epic's next unchecked slice (Slice 2b-projection) is
unblocked, so per the ACTIVE-EPIC guardrail it is advanced before any fallback pick. No
fallback item was selected.

**Scope decision — the deterministic projection ships; the `pymc`-NUTS audit is gated.**
The 2b-projection slice has two parts: (a) the deterministic posterior-predictive forward
projection on the already-shipped reduced-rank-GP backend, and (b) an *optional*
`pymc`-NUTS audit path. Part (b) is explicitly **gated** on the maintainer confirming the
ADR-141 backend-deviation direction (CONTINUATION Open Questions; the surface session's
harvested IMPORTANT item), and it would add the compile-heavy `pymc`/`bambi` dependency.
Since no maintainer confirmation has arrived (no live user input this session), shipping
(b) autonomously would both add a heavy dependency against an unresolved gate and violate
the "confirm before the NUTS audit path" instruction. So this session ships **only (a)** —
the deterministic reduced-rank-GP projection, which is independent of the gate and is the
common-path deliverable — and defers (b). This is a self-contained, independently
mergeable slice. ADR-142.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Grouped-cell contract + static-base offset + additive A/E GAM + export | ✅ Done | #141 (merged) |
| 2a | Frequentist tensor `te(x,t)` surface + `MI_x(y)` grid + delta-method band | ✅ Done | #142 (merged) |
| 2b-surface | Bayesian reduced-rank-GP MI surface + posterior credible intervals | ✅ Done | #143 (merged) |
| 2b-projection | CMI/MP-style mean-reverting posterior-predictive MI projection | ✅ Done | _(this draft PR #144)_ |
| 2c | `MortalityImprovement`-compatible custom scale (`ImprovementScale.CUSTOM`/from-grid) | ⏳ Next | — |
| 3 | Hierarchical partial pooling (credibility shrinkage) | 🔲 Planned | — |
| 4 | CLI + assumption versioning + validation decks/loaders + docs (CLOSES EPIC) | 🔲 Planned | — |

## What Was Done
Added forward projection to the Slice-2b reduced-rank-GP MI surface: a new `MIProjection`
dataclass and `BayesianMISurfaceResult.project_improvement(horizon_years, long_term_rate,
...)` in `analytics/experience_gam.py`.

For each attained age the projection anchors on `initial_mi(x)` — the fitted annual
improvement across the final observed step `y_last−1 → y_last`, read from the *same*
Laplace-covariance contrast machinery as `improvement_surface` — and **mean-reverts** it
toward a settable `long_term_rate` over `convergence_period` years:
`MI_x(y_last+k) = long_term_rate + w_k · (initial_mi(x) − long_term_rate)`, where the
weight `w_k` tapers from ~1 at the join to 0 at `k ≥ convergence_period`. This is the
epic's locked default (Matérn HSGP mean-reverting to a long-term rate, CMI/MP-style). The
convergence shape is selectable: `cosine` (default, the smooth CMI shape), `linear`, or
`immediate` (revert at the first projected year).

**Why mean-revert rather than extrapolate the GP.** The reduced-rank GP eigenbasis is
valid only inside its fit-time boundary `[−L, L]` (in standardised coordinates), and both
`L` and the fitted coefficients `θ` are frozen over the observed year range — so
evaluating the same basis at out-of-domain future years is not a valid GP extrapolation.
The honest, deterministic route is to project the *improvement rate* itself. ADR-142.

The band is **posterior-predictive**: `initial_mi(x)` is Gaussian under the Laplace
posterior (the last year-to-year contrast, delta-method through `1−exp(·)`); the long-term
rate is a fixed actuarial assumption; the projected rate is affine in `initial_mi(x)`, so
the band is `MI ± z·w_k·se(initial_mi(x))`. It equals the in-window surface band at the
join and narrows to zero as improvement converges to the deterministic long-term rate.
`MIProjection.cumulative_factor()` returns `Π(1−MI)` — the projected mortality multiplier
relative to `y_last`, exactly what `MortalityImprovement.apply_improvement` accumulates and
what the Slice-2c custom-scale emission will consume.

The whole projection is pure NumPy/SciPy, deterministic (bit-identical on re-run), and
needs no `[ml]` extra. The slice is additive: no pricing path, treaty, or golden output
changed. The golden `polaris price` regression and the QA suite are byte-identical to the
session baseline.

## Files Changed
- `src/polaris_re/analytics/experience_gam.py` (extended: `MIProjection` dataclass,
  `BayesianMISurfaceResult.project_improvement` + `_convergence_weights` +
  `_CONVERGENCE_METHODS`; `__all__`)
- `src/polaris_re/analytics/__init__.py` (export `MIProjection`)
- `docs/DECISIONS.md` (ADR-142)
- `docs/CONTINUATION_experience_gam.md` (Slice 2b-surface → PR #143 merged;
  2b-projection DONE; 2c → NEXT; NUTS-audit gate Open Question)
- `docs/PLAN_experience_gam.md` (status + Slice-2 sub-decomposition update)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (harvested follow-ups; amended the backend-gate
  item)
- `tests/test_analytics/test_experience_mi_bayesian.py` (+18 projection tests)

## Tests Added
- `tests/test_analytics/test_experience_mi_bayesian.py` (+18 tests): shape + strictly-
  future calendar years; **closed-form check** that `MI = ltr + w_k·(initial_mi − ltr)`
  matches the documented convergence formula to 1e-12; convergence to the long-term rate
  exactly at/after the convergence period; anchor continuity (first projected year ≈ last
  fitted step under a long convergence period); band narrows monotonically to zero
  (cosine + linear); band widens with the credible level; `immediate` method jumps to the
  LTR (zero band); linear reaches half the deviation at the midpoint; negative long-term
  rate (deterioration) honoured; cumulative factor = running product, strictly decreasing
  and < 1 for improving mortality; determinism (bit-identical on re-fit + re-project);
  `to_frame` columns/shape; custom age subset; four argument-validation rejects (horizon
  < 1, convergence_period < 1, unknown method, long_term_rate ≥ 1). No wall-clock
  dependency (ADR-074 guard). Runs in ~0.9s.

## Acceptance Criteria
| Criterion (PLAN Slice 2b, projection subset) | Status | Notes |
|-----|--------|-------|
| Posterior-predictive forward projection of `MI_x(y)` beyond the data window | ✅ | mean-reverting reduced-rank-GP anchor |
| Anchored to a settable long-term rate (locked default: Matérn mean-reverting) | ✅ | `long_term_rate` scalar; cosine/linear/immediate convergence |
| Credible band on the projection | ✅ | posterior-predictive (`MI ± z·w_k·se`); narrows to the deterministic LTR |
| Cumulative `Π(1−MI)` hand-off for Slice 2c | ✅ | `MIProjection.cumulative_factor()` |
| Deterministic + CI-lean (core-only) | ✅ | pure NumPy/SciPy, bit-identical, 18 tests ~0.9s |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + QA suite unchanged |
| RW2 alternative prior | ⏳ | deferred/harvested (NICE-TO-HAVE) — genuinely different model |
| `pymc`-NUTS audit backend; real HMD age×year slice; `mgcv` oracle | ⏳ | NUTS gated on maintainer sign-off (harvested IMPORTANT); HMD/mgcv are Slice 4 |

## Open Questions / Follow-ups
- **`pymc`-NUTS audit backend (gated).** The optional NUTS audit path for the projection
  is **not** shipped: per ADR-141's human-review flag it is held until the maintainer
  confirms the reduced-rank-GP backend direction. The deterministic projection is
  independent of that decision. Harvested to PRODUCT_DIRECTION (the existing IMPORTANT
  backend-gate item, amended to note the projection shipped without it).
- **RW2 (linear-trend, fanning-band) projection prior** as an alternative to
  mean-reversion — a genuinely different projection model the PLAN offered; not shipped.
  Harvested to PRODUCT_DIRECTION as NICE-TO-HAVE.
- **Per-age long-term rate.** `project_improvement` takes a single scalar
  `long_term_rate`; a per-age/per-segment long-term rate is a natural extension. Harvested
  as NICE-TO-HAVE.
- **PRODUCT_DIRECTION freshness.** The latest direction file (2026-06-18) is now ~34 days
  old (>30). Consistent with the Slice-1/2a/2b-surface decisions, this session **appended**
  the genuine follow-ups to its Promoted Follow-ups section rather than regenerating
  mid-run (a full shipped-since + carry-forward regeneration would risk the wall-clock
  guardrail after the slice work). A dedicated `PRODUCT_DIRECTION_{today}` regeneration
  (shipped-since #141–#144 + carry-forward) is now overdue and is a reasonable standalone
  next-session housekeeping task.

## Parked Polish
None. No 3rd-order-or-deeper follow-ups surfaced. The epic's own future slices (2c, Slice
3, Slice 4) are tracked in PLAN/CONTINUATION, not harvested.

## Impact on Golden Baselines
None. The slice is additive (a new dataclass + method on existing classes); the golden
`polaris price` regression and the full QA suite are byte-identical to the session
baseline.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (on `main` post-#143
merge): **2250 passed, 3 skipped, 110 deselected**, 0 failures — matches the recorded
Slice-2b-surface post-slice baseline, so no NEW/CHANGED failures; proceeded. After this
slice: **2268 passed, 3 skipped, 110 deselected**, 0 failures (+18 = the new
`test_experience_mi_bayesian.py` projection tests). QA suite (76) and the golden
`polaris price` regression byte-identical.
