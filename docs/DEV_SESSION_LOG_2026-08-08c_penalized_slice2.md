# Dev session log — 2026-08-08 — penalized MI surface, slice 2

**Branch:** `claude/quirky-ramanujan-5zhsw3` (reset onto `main` @ `fdd96ba` after PR #187 merged)
**Epic:** `PLAN_penalized_mi_surface.md` — slice 2 of 5
**ADR:** ADR-186

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `fdd96ba`) | 3083 passed, 3 skipped, 125 deselected |
| End state (`make test`) | **3091 passed, 3 skipped, 125 deselected** (+8) |
| Module tests | 25 (was 15) after the PR #188 review round |
| Standing failures | none new or changed |
| `tests/qa/` goldens | untouched |
| perf row | `peak_mib` 33 (Δ+0), fingerprint `8331a13f7ce7` unchanged |

Known flake: `test_scaling_is_near_linear`, the wall-clock ratio gate logged in
PRODUCT_DIRECTION. Fires under container contention, passes in isolation.

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

## The other half of this session: the HMD DOI closure

**Not slice-2 work, and the first version of this log omitted it entirely** — which
the PR #188 review flagged as the larger of two gaps, correctly: roughly half the
diff by file count was invisible to a reader trusting this document.

The maintainer supplied the HMD version DOI (`10.4054/HMD.Countries.20260615`) and
the versions-table reading in-session on 2026-08-08. That discharged the
`Maintainer-gated` flag on the ledger item — the container has no browser and
performed no lookup — and closed the HMD licensing position entirely. SOA is now
the only open licensing item.

Two things about it needed correcting after review, both mine:

- **It reverses a recorded instruction.** PRODUCT_DIRECTION said to take the DOI
  from the *Statistics* column, "not Countries". The series on disk are per-country
  `STATS` files, so *By country* is the right family — but doing the opposite of a
  recorded instruction without naming it as a reversal is how a ledger stops being
  trustworthy. Now stated as a withdrawal, with the reasoning marked as **ours** and
  still open to challenge.
- **A sentence claimed a safeguard that had not worked.** §4d said the negative
  results "stopped the visible-in-a-screenshot DOI being adopted because it was the
  one to hand" — while the DOI adopted *is* that one. What the negatives actually
  bought was adopting it **for a reason** rather than by proximity. Corrected rather
  than deleted, because the wrong version is the more instructive half.

**The process lesson is the scope one.** This rode along inside an epic-slice PR
because the maintainer supplied the DOI mid-slice and landing it felt like tidying.
Out-of-scope work belongs in its own change; a reviewer should not have to discover
a licensing closure in a PR titled "REML selection".

## Carried forward

`tr(F)` is chosen because it is what `mgcv` reports per smooth term, and nothing
here can verify that. Adopted, not validated — PLAN §7, the oracle's second job.

## Next

Slice 3 — Bayesian bands through the unchanged extractor (Anchor 2), and the first
coverage test this project has run on **either** estimator. Slice 2's fixture lesson
applies directly to its simulation design.
