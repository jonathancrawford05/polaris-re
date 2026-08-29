# Dev session log — 2026-08-29 — mgcv-parity slice 5d (finite-difference-step fix)

**Routine:** `ROUTINE_MGCV_PARITY.md`. Second slice of the day, same session lineage
as slice 5c (ADR-210) — PR #215 for 5c merged first, this branch restarted from
`main` per the merged-PR protocol, then slice 5d designated as the PLAN's next
unchecked, READY slice.

## Setup

- `uv sync --all-extras` — no changes.
- R already installed from the earlier session in this container:
  `R version 4.3.3 (2024-02-29)`, `mgcv 1.9.1` (apt) — tier 1 confirmed available.
- Read `docs/PLAN_mgcv_parity_engine.md` slice 5d (registered by ADR-210),
  `docs/DECISIONS.md` ADR-210, `docs/CONFORMANCE_LEDGER.md`'s tail.
- Baseline `uv run pytest tests/ -m "not slow"`: **3504 passed, 3 skipped** —
  matches the merged PR #215's own final state exactly, no drift.

## Gap Before

Stated in PLAN slice 5d exactly as ADR-210 left it:
- Fixed-`sp` REML criterion: closed to float round-trip precision at both tiers
  (ADR-210) — not in question this session.
- Free-`sp` selection, N=4 structure: `max_abs_log10_sp_diff = 0.7560` (tier 1) /
  `1.0996` (tier 3).
- Discriminating measurement (our own criterion at both sides' points, tier 1
  only): `mgcv`'s point scores `612.6108`, our optimiser's own converged point
  scores `612.6630` — `mgcv`'s point better by `+0.0523`.
- Two live, undistinguished hypotheses: (1) optimiser/gradient precision,
  (2) genuine multi-modality.

## Provenance gate (ADR-193)

- The cheap step (re-running the existing discriminating measurement at tier 3)
  reuses `gam_reml_optimize_conformance.FIXED_SP_MULTITERM_REML_CLAIM`
  (declared PR #215 review round 2) on the "ours" side, and `mgcv`'s own
  `gcv.ubre` on the other — same INDEPENDENT classification as ADR-210, no new
  claim needed since no new quantity was declared, only a stale input refreshed.
- The interpolation sweep and the forward-difference noise-floor scan are pure
  Python diagnostics — no `mgcv` involved on either side, so no provenance
  classification applies (nothing is being compared against the oracle).
- The fix's own validation (multi-start scores, `delta_mgcv`, `max_abs_eta_diff`,
  `edf_total_diff`) reuses `FREE_SP_MODEL_CLAIM` (ADR-208) and the
  `gam_multiterm_sp_delta_probe.R` diagnostic (ADR-208 amendment) — both
  pre-existing, unchanged in kind.

## The loop

1. **Hypothesis:** re-running the discriminating measurement at tier 3 (PLAN's
   own "cheap step") will reproduce the tier-1 sign and magnitude, since the
   fixed-`sp` criterion is already proven identical at both tiers.
   **Change:** refreshed the stale `python_opt_log10` (still ADR-208's
   pre-Appendix-B reading) in `gam_fixed_sp_score_probe.R` and the
   `gam_multiterm_sp_delta_probe.R` workflow invocation to Python's CURRENT
   `fit_free_sp_case` selection. No new code.
   **Result:** CONFIRMED IDENTICAL at tier 3 (CI run 33275225043) — our
   criterion `+0.05229`, `mgcv`'s own criterion `-0.052286`. Since the fixed-`sp`
   spread is 0 everywhere, this also mechanically retires hypothesis (b)/2's
   "the two criteria disagree" framing entirely.

2. **Hypothesis:** if the surface is genuinely multi-modal between the two
   points, an interpolation sweep between them should show a barrier; if it is
   an optimiser-precision problem, the sweep should be smooth.
   **Change:** none to the code — scored `penalized_fit_and_score` at 11 points
   along the straight line between the default optimiser's converged point and
   `mgcv`'s point.
   **Result:** monotonic, smooth decrease from `612.663` to `612.611` at every
   step — no barrier. Evidence AGAINST hypothesis 2 for this pair of points.

3. **Hypothesis:** the "converged" point's own gradient, measured independently
   (central differences at several step sizes), should be near zero if SciPy's
   own convergence check is trustworthy.
   **Change:** none — pure measurement.
   **Result:** `~0.55` at every tested step size (`1e-2` to `1e-6`), nowhere near
   `gtol=1e-8`. SciPy's own reported convergence was spurious.

4. **Hypothesis:** the spurious convergence traces to SciPy's default
   finite-difference step being too small for this objective's own noise floor
   (the nested penalized-IRLS solve only converges to `_IRLS_TOL=1e-10`
   relative).
   **Change:** none — a forward-difference scan at ONE point across step sizes
   `1e-1` to `1e-10`.
   **Result:** stable derivative estimate (`0.231`-`0.236`) from `h=1e-1` to
   `1e-6`; breaks down at `h<=1e-9` (WRONG SIGN at `1e-9`). SciPy's own default
   (`1.49e-8`) sits inside the broken region. Hypothesis 1 CONFIRMED with a
   specific, measured mechanism.

5. **Fix:** `gam_reml_optimize._FINITE_DIFF_STEP = 1e-5`, two orders of
   magnitude above the measured stable/unstable boundary, derived from steps
   3-4's own measurement — never from a comparison against `mgcv`. Wired via
   `options={"eps": _FINITE_DIFF_STEP, ...}` into the one
   `scipy.optimize.minimize` call `select_lambdas_continuous` makes.
   **Result:** re-ran the multi-start experiment PLAN slice 5d itself
   registered (8 starting points: the production default, at `mgcv`'s point,
   6 scattered near either, plus 2 adversarial far-outside starts). 6 of 8 now
   converge to a `~0.001`-wide score band matching `mgcv`'s own optimum;
   `delta_mgcv` (mgcv's own criterion, `mgcv`'s point vs. Python's default-start
   point) closes from `-0.052286` to `+0.000668` — confirmed IDENTICAL at tier
   3 (CI run 33279785437, `delta_mgcv=0.000668`).

## Gap After

- `delta_mgcv` (the discriminating measurement, `mgcv`'s own criterion): tier 1
  and tier 3 both `+0.000668` (from `-0.052286`) — **~78x tighter**.
- `max_abs_eta_diff` (`compare_free_sp_case`): tier 1 `8.068e-04`, tier 3
  `7.593e-04` (from an earlier pre-Appendix-B `3.677e-02`) — consistent across
  tiers, ~45-48x tighter than the pre-Appendix-B reading.
- `edf_total_diff`: tier 1 `-0.01838`, tier 3 `+0.0150` — both far tighter than
  the pre-Appendix-B `+0.7263`, small magnitude at both tiers.
- `max_abs_log10_sp_diff` (the registered primary metric): tier 1 `0.8777`
  (WORSE than the pre-fix `0.7560`), tier 3 `0.2606` (better than the pre-fix
  `1.0996`, and 3.4x smaller than this session's own tier-1 reading). **This
  metric's cross-tier instability, while `eta` stays fixed, is read as
  diagnostic of weak identifiability on one block — not as a residual defect**
  (full argument in ADR-211).

## Mutation protocol

Not applicable — this slice fixes an optimiser default and characterises an
identifiability property, not a new formula module with its own mutation
surface (Appendix B's mutation protocol was slice 5c's scope, already run and
reported in ADR-210).

## Quality gate

- `uv run ruff format src/ tests/` — 327 files unchanged.
- `uv run ruff check src/ tests/ --fix` — all checks passed.
- `uv run pytest tests/ -m "not slow"` — **3504 passed, 3 skipped** — identical
  to this session's own baseline, no regression from the `eps` change.
- `uv run pytest tests/qa/` — **94 passed** — goldens byte-identical.
- Targeted: `test_gam_reml_optimize.py`, `test_gam_reml_optimize_conformance.py`,
  `test_gam_model.py`, `test_gam_model_conformance.py` — 29 passed.

## Tier-3 dispatch

Two dispatches, both green, oracle digest
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8):
- [33275225043](https://github.com/jonathancrawford05/polaris-re/actions/runs/33275225043)
  — the cheap step, pre-fix code, confirming the `+0.0523`/`-0.052286` reading.
- [33279785437](https://github.com/jonathancrawford05/polaris-re/actions/runs/33279785437)
  — after the `_FINITE_DIFF_STEP` fix, confirming `delta_mgcv=0.000668` and the
  `eta`/`edf`/`log10(sp)` table's tier-3 column.

Required levels 1-3 of the ten-cell suite agree on both dispatches (no
regression).

## Follow-ups harvested

See `docs/PRODUCT_DIRECTION_2026-07-24.md`'s "Harvested 2026-08-29 (session 2,
slice 5d)" section: the resolution itself (1st-order, unblocks slice 6), the
weak-identifiability methodology point for future bases (1st-order for the
lesson, 2nd-order for the specific metric-revision question), and the
maintainer-reserved question of whether `FREE_SP_MODEL_CLAIM`'s primary metric
should weight `eta`/`edf` over raw `log10(sp)` (2nd-order).

## Provenance summary

| comparison | left producer | right producer | classification |
|---|---|---|---|
| our criterion at both free-`sp` points | `gam_reml_optimize_conformance.compare_fixed_sp_multiterm_case` | `mgcv`'s own `gcv.ubre` at the same fixed `sp` | INDEPENDENT (`FIXED_SP_MULTITERM_REML_CLAIM`, reused) |
| `mgcv`'s own criterion at both points | `gam_multiterm_sp_delta_probe.R`'s own `gcv.ubre` | Python's own selected point, supplied as an argument | diagnostic (reads a point the other side selected — same status as `gam_deriv_probe.R`/`gam_vc_probe.R`, never part of a committed comparator) |
| interpolation sweep | `penalized_fit_and_score` at hand-chosen points | n/a — no `mgcv` involved | not a comparison |
| forward-difference noise-floor scan | `penalized_fit_and_score` at hand-chosen points | n/a — no `mgcv` involved | not a comparison |
| free-`sp` selection (`eta`/`log10(sp)`/`edf`) | `gam_model_conformance.fit_free_sp_case`/`compare_free_sp_case` | `mgcv`'s own free-`sp` REML fit | INDEPENDENT (`FREE_SP_MODEL_CLAIM`, reused, unchanged) |
