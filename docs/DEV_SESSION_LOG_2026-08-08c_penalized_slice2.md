# Dev session log — 2026-08-08 — penalized MI surface, slice 2

**Branch:** `claude/quirky-ramanujan-5zhsw3` (reset onto `main` @ `fdd96ba` after PR #187 merged)
**Epic:** `PLAN_penalized_mi_surface.md` — slice 2 of 5
**ADR:** ADR-186

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `fdd96ba`) | 3083 passed, 3 skipped, 125 deselected |
| End state (`make test`) | **3094 passed, 3 skipped, 125 deselected** (+11) |
| — by round | 3091 as first pushed (+8), 3093 after round 1 (+2), 3094 after round 2 (+1) |
| Module tests | 26 (was 15) — 23 pushed, +2 round 1, +1 round 2 |
| Standing failures | none new or changed |
| `tests/qa/` goldens | untouched |
| perf row | `peak_mib` 33 (Δ+0), fingerprint `8331a13f7ce7` unchanged |

Known flake: `test_scaling_is_near_linear`, the wall-clock ratio gate logged in
PRODUCT_DIRECTION. Fires under container contention, passes in isolation.

## What shipped

REML λ selection over a **deterministic grid**, the amended-Anchor-4 EDF reporting
fix, and an at-bound flag. 26 tests, up from 15 — 23 as first pushed, then +2 in
review round 1 and +1 in round 2.

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

**Decision (maintainer, 2026-08-08): do not split it out.** The review recommended
separating the two licensing commits into their own PR. The maintainer judged the
separation not worth the history surgery on a live PR now that the record defects
are fixed. Recorded because the reviewer's scope finding is legitimate and remains
so — it was **accepted and overridden on cost**, not refuted, and a future reader
should see that distinction rather than assume the finding was wrong.

## Review round 2: the fix had the shape of the defect it fixed

Round 1's headline finding was two inert fields whose docstrings, in five places,
described behaviour the code did not have. Round 1's fix wired them, and ADR-186
amendment 1 generalised the shape: *a claim written from intent while the wiring is
still a two-step dance the claim does not survive.*

Round 2 found that shape **in the fix**. Two of the five claim sites were never
updated: `PenalizedMIFit`'s docstring still credited `select_lambdas_reml` with
populating the fields, and `REFINE_STEP`'s still said "recorded on every fit". The
first is the worse one, and the reviewer's reason is the right one — once a correct
entry point exists, naming the wrong one is worse than the original vagueness,
because vagueness sends nobody anywhere in particular while a wrong name sends them
precisely to the `None`.

**The generalisation was right and scoped too narrowly.** The unit of work is not
the claim, it is the **claim set**. Five sites asserted one fact; the fix updated
three; nothing counted. A `grep` for the claim before declaring the fix done costs
seconds and would have closed it. Two review rounds did not.

**The second finding is sharper than it looks.** `fit_reml()` reported
`lambda_grid_step=REFINE_STEP` — the constant, not the step swept — and forwarded
`**model_kwargs` to the model constructor as well as the selector, so the one input
that could expose the hardcoding (`refine_step=0.5`) raised `TypeError` first. The
test asserted `== REFINE_STEP`, comparing against the same constant the code
hardcoded, so it passed either way. **An unfalsifiable claim paired with a test that
cannot fail** is worse than either alone: the test's greenness was evidence for
nothing while reading as evidence for the claim. The new test sweeps a non-default
0.5 and checks log10 λ lands on the coarser lattice — it is the assertion that would
have failed on the old code, which is the only kind worth adding.

## Carried forward

`tr(F)` is chosen because it is what `mgcv` reports per smooth term, and nothing
here can verify that. Adopted, not validated — PLAN §7, the oracle's second job.
Round 2 raised its priority rather than restating it: slice 4 puts the number in
front of a reader, so the `mgcv` cross-check stops being optional before slice 5
reports it on real data. It needs R on a machine that has it — maintainer-side.

## Next

Slice 3 — Bayesian bands through the unchanged extractor (Anchor 2), and the first
coverage test this project has run on **either** estimator. Slice 2's fixture lesson
applies directly to its simulation design.
