# Dev session log — 2026-08-09 — penalized MI surface, slice 3

**Branch:** `claude/quirky-ramanujan-5zhsw3` (reset onto `main` @ `8fa5638` after
PR #188 merged). **PR #189.**

Bayesian bands through the band layer, and the first coverage study this project has
run on either estimator. **ADR-187.**

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `8fa5638`, PR #188 merged) | 3094 passed, 3 skipped, 125 deselected |
| End state (`make test`) | **3102 passed, 3 skipped, 125 deselected** (+8) |
| — by round | 3100 as first pushed (+6), 3102 after review round 1 (+2) |
| Module tests | 34 (was 26) — 32 pushed, +2 in round 1 |
| Standing failures | none new or changed |
| `tests/qa/` goldens | untouched |
| mypy | 5 pre-existing errors in this module, unchanged (verified against `main`) |

### Perf history

One deterministic-first row appended for `4e7dd64` (ADR-177). `peak_mib` 33 -> 33,
delta 0.0, `has_structural_creep: false`, `config_drift: false`, 10 rows. Wall-time
ratio 1.37 against the 1.25 band is flagged `creep: true` and is **advisory only** —
best-of-k across CI machines, with the MiB peak flat. The row was **missing from the
initial push** and the review caught the gap in the series (PR #189 [P1]).

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

λ is selected **once, on a held-out seed**, and every replicate fit at it. That is
what `Vb` claims — it carries no smoothing-parameter uncertainty.

## Review round 1 changed two of the three findings

The review's [P1] was that "held-out" was **false**: λ was selected on seed 1000 while
the evaluation loop started at 1000, so one replicate in 200 shared the selection data.
One character, immaterial to the number, wrong in a published ADR.

Fixing it moved the selection seed to 999 — **and moved the penalized coverage from
0.9260 to 0.8710.** A 5.5-point swing from nothing but which replicate λ was read off.
Chasing that produced the slice's most consequential result, and it arrived through a
cosmetic correction rather than through the study that was designed to find things.

**New finding: REML λ selection is unstable across replicates.** On the quadratic
fixture, log10 λ_age takes 2.50, 3.00, 3.25, 3.50, 4.25, 4.50 and 8.00 across eight
consecutive seeds — five decades, on realisations of the *same truth*. The selected λ
is one draw from a wide distribution.

**Withdrawn: "the penalized estimator degrades further under misspecification".** At
the corrected seed it is 85.1% against delta's 84.6% — level, inside the Monte-Carlo
SE. The original 76.0% ordering was an artifact of the same λ lottery. Withdrawn
rather than re-argued in the opposite direction; what is robust is that **both**
collapse.

**Withdrawn: the "2.4 points" headline.** It paired a nominal-relative figure with a
delta-relative comparison (the review's [P2]), on top of a number that did not survive
a seed change. No point figure is quoted now. The *direction* — narrower, and
under-covering on a representable curve — survives; the decimals do not.

**New finding: `select_lambdas_reml` aborts on a non-converging grid corner.** Found
while attempting the unconditional (select-per-replicate) study, which is therefore
**not delivered**. `log10 λ = (-1, 8)` fails IRLS on ~1 replicate in 100 and takes the
whole selection down with it. Left unfixed deliberately — the fix is a design choice
belonging to the selector's owner, not a review-round patch — and registered as a
**slice-4 blocker**, since slice 4 runs this on a 125k-cell book where a
one-in-a-hundred abort is a failed production run.

## The findings that held

**1. The registered hypothesis is falsified, and the committed bands stand.** PLAN
slice 3 registered that the delta-method bands might under-cover at the death-poor
young end, "published whichever way it comes out". They do not: **95.7% and 95.9%**
against nominal 95%, with young ages the *best*-covered region. That sharpens ADR-184
rather than contradicting it — the age-45 artifact is about the point estimate's
sampling spread, and the interval was honest about that spread all along.

Third time a pre-registration in this project has come back against its own
hypothesis. That is the argument for the practice, not against it. These are also the
study's most durable numbers, because the unpenalized fit has no λ to be unstable.

**2. The penalized band trades coverage for precision — in direction, not magnitude.**
87.1% against 95.9% on the representable curve, at 4.4x narrower; 97.3% at 8.3x in the
null space, which is the flattering regime and not the headline.

**3. Both collapse under misspecification**, ~85% for each, with old ages 76.0% and
66.9%. **The weak end is old ages, not young** — the opposite of where the slice was
sent to look.

## Carried forward

`tr(F)` is still adopted, not validated — PLAN §7, and slice 4 puts it in front of a
reader. `Vb` conditions on λ, so a slice-4 report showing a band beside a selected λ is
showing two numbers that are not jointly calibrated.

## Next

Slice 4 — harness integration, `--penalized` off by default (Anchor 6), `edf` and λ
reported (Anchor 4). Two things are owed before it can report anything: the
**`select_lambdas_reml` abort** must be fixed, and the report must not present a band
beside a selected λ as though they were jointly calibrated — the λ instability
measured here is exactly why they are not.
