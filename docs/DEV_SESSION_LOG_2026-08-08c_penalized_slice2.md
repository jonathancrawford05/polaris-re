# Dev session log — 2026-08-08 — penalized MI surface, slice 2

**Branch:** `claude/quirky-ramanujan-5zhsw3` (reset onto `main` @ `fdd96ba` after PR #187 merged)
**Epic:** `PLAN_penalized_mi_surface.md` — slice 2 of 5
**ADR:** ADR-186

## What shipped

REML λ selection over a **deterministic grid**, the amended-Anchor-4 EDF reporting
fix, and an at-bound flag. 23 tests, up from 15.

## Anchor 3 was resolved by design, not managed

The plan expected to fight the optimiser: quantise λ, measure the jitter, justify a
tolerance. A grid makes that unnecessary — the selected λ *is* a grid point, so it
reproduces by construction. The plan's own fallback (§5 risk 1) turned out to be
the better primary. Cost is resolution, recorded as `lambda_grid_step` rather than
left implicit; ~150 fits at 4-13 ms is about a second on the fixture.

The cross-process test spawns three fresh interpreters and demands **exact** repr
equality. If it ever needs a tolerance, the selection stopped being a grid.

## Two findings from building it

**`edf_total` cannot see the calendar margin.** On a 30-year window a constant truth
and a curved truth both landed at 36.4 — the total is dominated by age. So the
graded-smoothness test asserts on `edf_tensor` and `shrinkage_year`. This is a
second and independent argument for the amended Anchor 4: the per-margin diagnostic
is not a nicety, it is the only thing that can see what the calendar penalty does.

**A smoothness ladder must be representable in the basis.** An early fixture used a
fixed 5.7-year sine; over 30 years at `k_year=6` the basis cannot resolve it, so
REML correctly smoothed it away — and the test was measuring the basis, not the
selector. It looked like a broken selector and was not.

## The thesis, and the number I did not quote

REML beats both hand settings on RMSE against the injected truth. But the gain is
40x on a *constant* truth and 2.3x on a *curved* one, because a constant MI lies
inside the second-difference penalty's null space, where heavy smoothing is exactly
right and the penalized fit wins almost for free.

**2.3x is the honest figure.** The test is parametrised over both regimes so a
selector that always smooths hard cannot pass on the flattering case alone. Fixture
evidence for the thesis, not confirmation — the arbiter on real data is SOA's own
expected deaths, which is slice 5.

## Carried forward

`tr(F)` is chosen because it is what `mgcv` reports per smooth term, and nothing
here can verify that. Adopted, not validated — PLAN §7, the oracle's second job.

## Next

Slice 3 — Bayesian bands through the unchanged extractor (Anchor 2), and the first
coverage test this project has run on **either** estimator. Slice 2's fixture lesson
applies directly to its simulation design.
