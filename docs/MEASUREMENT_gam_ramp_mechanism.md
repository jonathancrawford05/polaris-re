# Measurement: what actually produces the age-45 ramp

**Slice 1 of** `docs/PLAN_gam_spline_diagnostics.md`.
**Run** autonomously, 2026-08-07, on synthetic fixtures with an injected known
surface. **No licensed data touched** — this slice needs none, and that is the
point (see §1).
**Evidence:** `tests/test_analytics/test_experience_gam_ramp_diagnostic.py`, which
carries every claim below as an executing assertion.

---

## 1. Headline: it is a variance artifact at the information-poor young end

Both mechanisms the plan proposed are **wrong**, and the real one is a third thing.

| Hypothesis | Verdict |
|---|---|
| **A** — an unpenalized cubic must place curvature somewhere and ramps at the ends | **Falsified.** Noiseless recovery is *exact* |
| **B** — age 45 sits next to an interior age knot at ~42.5 | **Falsified.** Move the knots and the anomaly does not follow |
| **C** — sampling noise at the death-poor young end, converted into a smooth swing by three free year parameters | **Supported** |

**Why synthetic beat real data here.** On real ILEC the true surface is unknown, so
a ramp is only ever suspicious. On a fixture with a *known constant* injected
surface, a swing is proof of artifact — there is nothing else it could be. This is
the one question in the whole epic where the fixture is the stronger evidence, and
it is why slice 4 is a single confirmation run rather than the experiment.

## 2. The cubic basis is not biased — hypothesis A falsified

Fit the exact configuration both committed ILEC reports used (`age_df=6`,
`year_df=3`, count basis, ages 25–95 × 2012–2019) against a constant 1.5%/yr truth
with **no sampling noise**:

| Age | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 45 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 |
| 85 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 | 1.50 |

Exact to 1e-6 at every reference age. The reason is simple in hindsight and was
missed: a **cubic can represent a straight line exactly**. Constant MI means η is
linear in calendar year, which sits inside the cubic's span with three parameters
to spare. There is no bias to find. The plan's claim that "an unpenalized cubic
must place its curvature somewhere" is true of *interpolation through noise*, not
of a least-squares fit to a representable truth — and the distinction is the whole
finding.

## 3. Noise alone manufactures it — hypothesis C

Same fixture, same configuration, Poisson-sampled deaths, nothing else changed.
Truth is still exactly 1.5% at every age and every year:

| Age | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | span |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 45 | 1.61 | 1.40 | 1.30 | 1.28 | 1.37 | 1.56 | 1.84 | **3.13** |
| 55 | 2.13 | 1.65 | 1.33 | 1.18 | 1.20 | 1.39 | 1.75 | 2.45 |
| 65 | 1.95 | 1.66 | 1.46 | 1.37 | 1.37 | 1.46 | 1.66 | 1.18 |
| 75 | 1.43 | 1.49 | 1.52 | 1.53 | 1.52 | 1.47 | 1.40 | 0.30 |
| 85 | 1.37 | 1.47 | 1.53 | 1.55 | 1.53 | 1.48 | 1.39 | **0.46** |

*(span = peak-to-trough across the window, percentage points, seed 7)*

Age 45 swings **3.13 points** on a flat truth — the same order as the 0.05% → 3.59%
the real ILEC run reported. Age 85 barely moves. **The mechanism is expected
deaths:** under a realistic mortality curve, deaths at 45 are ~24× scarcer than at
85 for the same exposure, and information for the age-varying year slope scales
with deaths, not exposure.

**It is a variance phenomenon, and it behaves like one.** Across ten seeds, age
45's span ranges **0.17 to 3.83** while age 85's stays in **0.21–0.62**. The
committed test asserts on the *mean over eight seeds* rather than a single draw,
because a single draw of a variance artifact is a coin flip — and that instability
is itself part of the evidence.

Scaling total deaths confirms it directly:

| total deaths | age-45 span | age-85 span |
|---:|---:|---:|
| 12,898,774 | 0.56 | 0.18 |
| 1,290,666 | 3.13 | 0.46 |
| 128,933 | 9.86 | 1.30 |
| 12,935 | 27.18 | 7.67 |

## 4. The knots are innocent — hypothesis B falsified

`bs(attained_age, df=6)` places interior knots at quantiles, so shifting the fitted
age range moves the first knot. If age 45 were contaminated by knot proximity, the
worst-affected age would travel with it. It does not:

| fitted ages | first interior knot | span at that knot | span at youngest age | where the span peaks |
|---|---:|---:|---:|---|
| 25–95 | ~42 | 5.22 | **14.13** | age **25** |
| 30–100 | ~47 | 1.91 | **6.71** | age **30** |
| 20–90 | ~37 | 3.39 | **9.87** | age **20** |

In every range the swing peaks at the **youngest fitted age** and is 2.7–3.5×
larger there than at the first knot. The knots move across 42 / 47 / 37; the
anomaly stays at the young edge. Age 45 is affected because it is *near the young
boundary of a death-poor region*, not because a knot sits beside it.

## 5. What this corrects in the ILEC measurement

`MEASUREMENT_experience_gam_ilec.md` §3 and §7 say age 45 is "boundary-contaminated"
and that it "needs a longer vintage, not a different setting."

- **"Boundary-contaminated" is directionally right** — it is an edge effect — but
  the edge is the **age** edge, not the calendar-terminal one the surrounding
  prose implies, and the mechanism is variance rather than spline overshoot.
- **"Not a different setting" is wrong.** Pinning `df == degree == 1` — a global
  linear year margin — removes the swing *completely* (span 0.00 by construction,
  verified to 9.7e-17) and returns the level to the truth: mean fitted MI at age 45
  is **1.50%** against the injected 1.50%, where the shipped cubic gives **1.19%**.
  So the cubic does not merely wander at age 45; it also biases the point estimate
  there, and a setting change fixes both.

| year margin (`df` = `degree`) | age-45 span | age-45 mean MI (truth 1.50) |
|---|---:|---:|
| 1 — global linear | **0.00** | **1.50** |
| 2 — global quadratic | 0.69 | 1.50 |
| 3 — global cubic *(as shipped)* | 3.13 | 1.19 |

A longer vintage would also help, by adding years and therefore deaths at age 45 —
the doc is not wrong that it would work. It is wrong that it is *necessary*.

## 6. What this means for the penalized rebuild

It strengthens the case rather than weakening it, and sharpens what the penalty is
for. The problem is **not** that the basis is too coarse or wrongly placed; it is
that three free year parameters are estimated with wildly different precision
across the age range, and an unpenalized fit spends all three everywhere
regardless. That is exactly what a penalty fixes — it lets effective degrees of
freedom fall where the data are thin and stay high where they are not, without
anyone choosing a single global `degree` that has to suit both ends.

Lowering the degree is the crude version of the same idea: it buys the young end at
the cost of the old end, uniformly. §5's table quantifies the buy; slice 3 will
quantify the cost.

## 7. Honest limitations

- **This shows the real ramp is *reproducible* by noise at comparable scale. It
  does not show the real ramp *is* noise.** Confirming that needs slice 4 and the
  maintainer's cache. The distinction is the same one this epic has enforced
  throughout, and it is not being relaxed here.
- **The fixture is one stratum per (age, year).** Real ILEC pools 125,676 cells
  across sex, smoker, `uw_class` and duration band. Age-year information is what
  drives the surface, but the real fit estimates many more parameters and its
  `q_base` is an *empirical* pooled rate carrying its own noise — both plausibly
  make the real artifact larger than this fixture's, not smaller.
- **Exposure is flat across age**; a real book's is humped. Re-running with a hump
  gave a *smaller* age-45 span (0.71 against 0.56 at matched seed) because it puts
  more exposure at midlife, so the flat profile is not conservative in that
  direction.
- **Poisson, not overdispersed.** A negative-binomial variant at φ = 1.163 (ILEC's
  measured value) produced comparable spans, so this is unlikely to matter, but it
  was not made the primary fixture.
- **No claim about ages 55–85 on real ILEC.** Those had 5–10× narrower spans in
  every fixture tried, consistent with the measurement document's position that
  they are the defensible ones.
