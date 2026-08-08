# Continuation: diagnose the age-45 ramp before rebuilding the smoother

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Age 45 stays boundary-contaminated
on the ILEC fit", promoted to the front of the queue by the 2026-08-07 GAM
specification review recorded in `DEV_SESSION_LOG_2026-08-08_spline_diagnostics.md`.
**Plan:** `docs/PLAN_gam_spline_diagnostics.md`
**Measurement:** `docs/MEASUREMENT_gam_ramp_mechanism.md`
**Status:** **COMPLETE (2026-08-08)** — all four slices delivered. Follow-ups live
in PRODUCT_DIRECTION, not here.
**Total slices:** 4 (slice 2 subsumed; slice 4 was one maintainer run)

## Overall goal

Test a sentence nobody had tested. `MEASUREMENT_experience_gam_ilec.md` §3 called
age 45's 0.05% → 3.59% climb boundary contamination that "needs a longer vintage,
not a different setting" — a claim that blocked every age-45 insured-improvement
claim and justified waiting on a longer ILEC release.

## Slices

### Slice 1: reproduce the ramp against a known truth (autonomous)
- **Status:** DONE (2026-08-07) — 9 tests, ADR-184.
  **Both hypotheses the plan proposed were falsified.** Noiseless recovery at the
  shipped configuration is exact to 1e-6, so the cubic basis is not biased (A);
  shifting the age range moves the knots across 42/47/37 while the swing stays at
  the youngest fitted age (B). The mechanism is sampling noise at the death-poor
  young end — 3.13 points of swing at age 45 against 0.46 at 85, on a flat truth,
  because deaths at 45 are ~24x scarcer.

### Slice 2: separate the two mechanisms (autonomous)
- **Status:** SUBSUMED — the plan's escape clause fired when slice 1 killed both
  hypotheses. Its two axes were already covered by slice 1's own sweeps.

### Slice 3: expose spline degree and price it (autonomous)
- **Status:** DONE (2026-08-07) — ADR-184 amendment 1. **Quadratic dominates the
  shipped cubic outright**: 4.5x less swing at age 45, level restored from 1.19% to
  1.50% on a 1.50% truth, and a genuine 3.5pp climb still recovered exactly. The
  cost appears only at the linear rung, which reports that climb as zero. The slice
  was scoped to price a trade-off and found there wasn't one against cubic.

### Slice 4: confirm on real ILEC (maintainer run)
- **Status:** DONE (2026-08-08) — ADR-184 amendment 2, measurement §8.
  **Interpretation-table row 2: the diagnosis does not transfer.** The early-vs-late
  contrast moves by at most 0.02 points between cubic and quadratic and the verdict
  is unchanged. Slices 1-3 stand as a finding about the estimator; they do not
  explain this book.

## What this epic changed elsewhere

- `MEASUREMENT_experience_gam_ilec.md` §3/§7 retracted — mechanism *and* remedy.
- The **byte-for-byte determinism claim withdrawn** repository-wide: rounding ties
  flip when a parallel sum reassociates, and no cutoff can be tie-free.
- The **quadratic is the better fit** on the one independent check (SOA's own
  expected deaths, 10% and 35% closer at equal dispersion and one fewer parameter).
- ADR-184's own §7 hedge falsified — it guessed the fixture understated the real
  artifact; relative to this book's signal it overstates it.

## Context for the next session

- **The next epic is scoped:** `docs/PLAN_penalized_mi_surface.md`. Read §1 first —
  it opens by ruling out the framing this epic's result forbids, namely that
  penalization fixes age 45. It does not.
- **Age 45's real explanation is still open** and its three surviving candidates are
  in PRODUCT_DIRECTION (2026-08-08d), not here.
- **The fixtures are reusable.** `test_experience_gam_ramp_diagnostic.py` carries
  ILEC-shaped and HMD-shaped grids with injected known surfaces; the penalized epic
  should consume them rather than build new ones.
