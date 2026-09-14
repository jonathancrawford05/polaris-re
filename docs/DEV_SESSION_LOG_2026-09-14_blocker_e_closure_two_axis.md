# Dev session log — 2026-09-14: blocker E closed by measurement (ADR-226)

**Branch:** `claude/brave-keller-6tygau`, restarted from `origin/main` at
`098a06a`. The branch's previous PR (#227) is MERGED, so per the repo's own
rule follow-up work restarts the branch from the default branch rather than
stacking on merged history. The push that re-pointed it was a verified
fast-forward (`git merge-base --is-ancestor` confirmed), not a rewrite.

**Base:** `098a06a` (PR #231, the last merge on `main` at session start;
re-checked mid-session — nothing newer).

**Gate reason:** maintainer direction, 2026-09-14 — *"are we any closer to
reliable estimates that can be exposed to users?"* Answering that honestly
required a measurement nobody had taken, not a reading of the documents.

## Test baseline

`uv run pytest tests/ -m "not slow"` on `098a06a` with this session's changes
(docs only): **see "Baseline result" below.** R is installed in this container,
so the R-gated conformance tests DO run here.

## What this session did, and why it was necessary

The maintainer asked whether the last three slices (7g, 7h, 7i) brought the
engine closer to user-exposable estimates. Answering required checking whether
**blocker E** — the reproducibility blocker gating wiring slice 3 — was still
open.

It was being carried as open, but on a **pre-7h reading**. Slice 7h (ADR-223)
fixed the mechanism and measured the *criterion's* noise floor (`~5.2e-05` →
`~6.8e-13`). It never re-ran the end-to-end two-axis study, and was explicit
about it: ADR-223 leaves "the random-start/best-of-N nondeterminism 7h does not
reach" to slice 8. Slices 7g and 7i did not touch it either.

So the status of the epic's own gating blocker rested on a measurement taken
before the fix that was supposed to close it. **That gap is the finding that
motivated this session** — in either direction: if the study came back clean,
blocker E closes; if dirty, slice 8 is load-bearing rather than optional, which
is worth knowing before anyone plans around 7h having solved it.

The distinction is not pedantic. Best-of-N selection compares scores, and
selection is a **discontinuous** function of them. A stable criterion makes a
stable landing point likely; it does not demonstrate one.

## Method

Re-ran the committed `scripts/gam_convergence_two_axis_diagnostic.py` (shipped
in PR #227 precisely so this would be re-runnable rather than rebuilt from
prose) against the `select=TRUE` N=7 multiterm fixture, regenerated from the
committed `scripts/gam_select_multiterm_free_sp_probe.R`.

**Run twice, deliberately:** once on `fc25053`, then again on `098a06a` after
noticing #231 had touched `gam_fit.py`. That change proved to be comment-only,
and the two runs are **bit-identical on every seed, basin and spread** — so the
reading is reproducible across runs and across the tree change.

## Results

### Axis A — 10 seeds of `multistart(9)`, threads=1

```
      seed   edf_total          score
  20260830     14.3896     523.656922
  20260901     14.3896     523.656922
  20260902     14.3896     523.656922
  20260905     14.5609     523.644997
  20260906     14.3896     523.656922
  20260907     14.3896     523.656922
  20260908     14.5613     523.645015
  20260909     14.5600     523.644997
  20260910     14.3896     523.656922
  20260911     14.3896     523.656922

  max |d eta|       : 4.416948e-03   (gate 2e-2)
  max |d edf_total| :     0.171702   (gate 1.0)
  -> REPRODUCIBLE   margin 4.5x / 5.8x
```

### Axis B — threads 1/2/4, `multistart(9)`, pinned seed 20260830

```
   threads   edf_total          score
         1     14.3896     523.656922
         2     14.3080     523.662491
         4     14.3081     523.662514

  max |d eta|       : 1.554196e-03   (gate 2e-2)
  max |d edf_total| :     0.081613   (gate 1.0)
  -> REPRODUCIBLE   margin 12.9x / 12.3x
```

**Pre-7h this axis read `eta 0.356`, `edf_total 10.0`.** Improvement ~229x and
~123x.

### Axis B' — threads 1/2/4, single-start FD (the default)

```
  max |d eta|       : 1.988777e-03   (gate 2e-2)
  max |d edf_total| :     0.097752   (gate 1.0)
  -> REPRODUCIBLE   margin 10.1x / 10.2x
```

### The second finding, which was not what I went looking for

Axis A landed in **two basins**: `14.3896` / `523.656922` on **7 of 10** seeds,
`~14.5609` / `523.644997` on **3 of 10**. `mgcv`'s own `edf_total` on this
fixture is **`14.5624`** (read from the fixture's own payload).

The minority basin is **closer to `mgcv`** AND **better by our own REML
criterion** (lower by `0.0119`). Best-of-9 therefore lands, 7 times in 10, in a
basin that is worse by the criterion it optimises and further from the
reference — and post-7h it does so *reproducibly*.

**Reported as headroom, not a regression.** `|d edf_total|` against `mgcv` is
`0.173` against ADR-221's bound of `1.0`: the engine passes its committed gate.
Overstating this as a failure would be exactly the kind of alarmism the
`VERIFICATION_STANDARD` exists to prevent.

## Verification provenance (ADR-193)

The reproducibility axes are **`MEASUREMENT (own criterion)`** — Polaris against
itself across thread counts and seeds. One producer, no external reference, no
`VerificationClaim`, and **never citable as parity evidence**.

The basin finding's `14.5624` comparison *is* two-producer, and is reported
against ADR-221's **existing committed** `eta`/`edf` criterion rather than a new
one — no re-gating, consistent with Anchor 8 and Anchor W5.

## Limits, recorded so they travel with the headline

- One structure, one container, one BLAS build; `n=3` thread counts, `n=10`
  seeds.
- **The thread sweep is a LOCAL PROXY for the cross-runner axis, not that
  axis** — the diagnostic's own docstring says so. ADR-219 amendment 3's
  cross-runner axis is NOT discharged.
- **`SELECT_FREE_SP_MODEL_CLAIM`'s environment qualification is therefore NOT
  lifted.** ADR-224's registered tier-3 dispatch remains unrun and is the right
  instrument.
- Small samples have misled this epic before — ADR-222's own cross-start
  reading moved between `n=5` and `n=12`.

## Perf history

One row appended per ADR-177. This PR changes no engine code, so the row is
expected to duplicate `main`'s reading; it is appended rather than declined
because the absence drew a review finding on #227 ([P2-1]) and the series is
meant to be per-PR.

## Scope

Docs only. **Nothing in `src/` changed; no gate, tolerance or default moved.**
The basin finding is *registered against slice 8*, not actioned — closing it is
slice 8's job, and taking it here would be scope this session was not asked for.

## Baseline result

`uv run pytest tests/ -m "not slow"` on this branch: **run in flight at the
time of this commit; the reading is appended in this branch's follow-up commit
rather than guessed here.** This session changes no Python, so the expectation
is that it matches `main`'s own reading at `098a06a`; if it does not, that is
itself the finding and will be recorded as such.
