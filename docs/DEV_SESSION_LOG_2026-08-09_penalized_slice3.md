# Dev session log — 2026-08-09 — penalized MI surface, slice 3

Bayesian bands through the band layer, and the first coverage study this project has
run on either estimator. **ADR-187.**

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `8fa5638`, PR #188 merged) | 3094 passed, 3 skipped, 125 deselected |
| End state (`make test`) | **3100 passed, 3 skipped, 125 deselected** (+6) |
| Module tests | 32 (was 26) |
| Standing failures | none new or changed |
| `tests/qa/` goldens | untouched |
| mypy | 5 pre-existing errors in this module, unchanged (verified against `main`) |

**+6 for +6 tests**, and worth stating why the refactor contributed none: extracting
the band layer removed three copies of the arithmetic without removing or adding a
single assertion. 1227 analytics tests passed unmodified across it, which is the
evidence that it was behaviour-preserving.

Known flake: `test_scaling_is_near_linear`, the wall-clock ratio gate logged in
PRODUCT_DIRECTION. Fires under container contention, passes in isolation.

## What shipped

`PenalizedMIFit.improvement_surface()`, built on a band layer that is now **shared**
rather than duplicated, plus a 200-replicate coverage study over three deliberately
different truths.

## Anchor 2 came out neither satisfied nor violated

The anchor says the extraction layer does not change, because a band is `√(cᵀVc)` and
is agnostic to how `V` was formed. Its stop-signal: *"if this layer needs modifying,
the covariance swap is wrong."*

**The covariance half is vindicated exactly.** Wood's `Vb` drops into the band
arithmetic with nothing altered.

**The design half could not hold, for a reason unrelated to `V`.** The extractor
rebuilds its grid design through `patsy.build_design_matrices`, and slice 1 already
established that patsy cannot express this basis — it always clamps boundary knots,
which destroys the difference penalty's null space. I checked whether a shim could
duck-type patsy's `DesignInfo` and rejected it: `factor_infos`, `terms` and
`term_slices` are all required, so the shim would be a reimplementation of patsy
internals living inside this project — more fragile than the thing it protects.

Recording this as "Anchor 2 held" would have been false, and recording it as "Anchor 2
violated" would have been equally false and would have triggered a stop-signal aimed at
something else. **Basis incompatibility is not covariance incompatibility.**

## The anchor assumed a shared layer, and there wasn't one

The load-bearing discovery of the slice. `experience_gam.py` carried **three
byte-identical copies** of the contrast/band/`MISurface` arithmetic: the frequentist
tensor surface, the RRGP Bayesian surface, and the segmented Bayesian surface.

The RRGP copy is the detail worth keeping. It already builds its design **without
patsy** — so it was simultaneously the standing proof that the band layer is
basis-agnostic, and the standing proof that nobody had arranged the code to exploit
that. Anchor 2 was written as though the refactor had already happened.

Extracted to `mi_surface_from_design()` / `mi_grid_axes()`; all three existing sites
and the penalized path now call them. A fourth copy would have satisfied the anchor's
letter and destroyed its intent, since two band implementations drifting apart is the
exact failure the anchor exists to prevent.

Eleven slice-1/2 limit tests also moved onto `improvement_surface`. They had been
rebuilding the grid design and differencing η *inside the test file* — asserting on
arithmetic the tests owned rather than on what a caller receives.

## The coverage study, and why it has three truths

A single "curved" truth would have conflated three different things. The first draft
did exactly that: a sine cycle over the eight-year window, which **neither basis can
resolve**, giving 73.9% penalized against 84.7% delta and reading as a band-calibration
disaster. It is a *bias* measurement. Slice 2 lost time to this same confusion and
ADR-186 carried the lesson forward, which is the only reason it was caught here at
probe stage rather than in review.

| truth | in null space? | representable? | measures |
|---|---|---|---|
| constant MI | **yes** | yes | the flattering regime |
| quadratic MI | no | **yes** | **band calibration** |
| sine, 1 cycle / 8 yr | no | **no** | bias under misspecification |

The quadratic is the load-bearing one: MI quadratic in year accumulates to a cubic η,
which a cubic P-spline at `k_year=6` and patsy's `bs(df=3)` (a global cubic) each
represent *exactly*, so any shortfall is the band's.

λ is selected **once** and every replicate fit at it. That is what `Vb` claims — it
carries no smoothing-parameter uncertainty. Re-selecting per replicate would have
measured a different, better-sounding quantity while the interval under test stayed
the same one.

## Three findings

**1. The registered hypothesis is falsified, and the committed bands stand.** PLAN
slice 3 registered that the delta-method bands might under-cover at the death-poor
young end, "published whichever way it comes out". They do not: **95.7% and 95.9%**
against nominal 95%, with young ages the *best*-covered region. That sharpens ADR-184
rather than contradicting it — the age-45 artifact is about the point estimate's
sampling spread, and the interval was honest about that spread all along.

Third time a pre-registration in this project has come back against its own
hypothesis. That is the argument for the practice, not against it.

**2. The penalized band trades 2.4 points of coverage for 4.6x the precision.**
92.6% against 95.9% on the representable curve, at 4.6x narrower. In the null space it
*over*-covers (98.2%) at 8x narrower — the flattering regime, not the headline, the
same refusal ADR-186 made of its 40x.

**3. Both collapse under misspecification and the penalized one collapses harder.**
76.0% against 84.6%, old ages ~67% for both. Shrinkage adds bias on top of
approximation error. This is the honest counterweight to finding 2, and it bounds what
findings 1 and 2 mean: the arithmetic is right when the model is.

**The weak end is old ages, not young** — the opposite of where the slice was sent to
look, in both directions at once.

## Carried forward

`tr(F)` is still adopted, not validated — PLAN §7, and slice 4 puts it in front of a
reader. `Vb` conditions on λ, so a slice-4 report showing a band beside a selected λ is
showing two numbers that are not jointly calibrated.

## Next

Slice 4 — harness integration, `--penalized` off by default (Anchor 6), `edf` and λ
reported (Anchor 4). It must quote finding 2's coverage cost alongside the width, or
the report overstates the interval.
