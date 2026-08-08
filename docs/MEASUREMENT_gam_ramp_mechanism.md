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

## 5b. Slice 3: the price list

Slice 1 measured what a lower polynomial order *buys*. Slice 3 measures what it
**costs** — by injecting a truth whose MI genuinely climbs 0% → 3.5% across the
window at every age and asking whether each setting can still see it.

| `df` = `degree` | year margin | span @45 | mean MI @45 (truth 1.50) | recovers a genuine 3.5pp climb |
|---|---|---:|---:|---:|
| 1 | global linear | **0.00** | **1.50** | **0.00 — blind** |
| 2 | global quadratic | **0.69** | **1.50** | **3.50 — exact** |
| 3 | global cubic *(shipped)* | 3.13 | **1.19** | 3.50 — exact |

**The middle rung dominates the shipped setting**, which was not the expected
result. Quadratic gives 4.5x less swing than cubic, restores the level at age 45,
**and** still recovers real curvature exactly. There is no trade being made against
cubic at all on this fixture — it is simply better.

Linear is the rung that pays. It cannot represent a changing improvement rate, so
a genuine 3.5-point climb reports as **zero**. That is why it ships behind a flag
with the cost documented rather than as a new default, and why §1's framing —
"a linear year margin removes the swing" — is only half the sentence.

**Revised recommendation for an eight-year window: `--year-df 2 --year-degree 2`,**
not the linear margin this plan first reached for.

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

---

## 8. Slice 4 on real ILEC: the diagnosis does **not** transfer

**Run by** the maintainer, 2026-08-08, against the 12.5 GB cache — control
(`--year-df 3 --duration-bands`) and treatment (`--year-df 2 --year-degree 2
--duration-bands`). Raw output:
`docs/measurements/experience_gam_ilec_duration_banded{,_quadratic}.{json,md}`.

This is interpretation-table **row 2**, written before the run: *"age 45 still
climbs steeply under (2) → the real ramp is not the artifact this diagnostic
reproduced."*

### 8a. The control reproduced, and the determinism claim did not

Every fit output is bit-identical to the committed report — `dispersion`
1.16326330754, `overall_ae` 1.00000000063, `n_cells` 125676, and the whole fitted
surface. One value moved: `dropped_exposure_share`, from `9.17073903863e-05` to
`9.17073903864e-05`.

That is a ratio of Polars sums over 126,223 cells, sitting within 1 ulp of a
12-significant-digit rounding boundary, so a reassociated parallel sum flips which
way it rounds. **The estimator is deterministic; a data aggregation is not** — and
the repository's claim that a re-run "reproduces these files byte for byte" is
therefore too strong. No rounding cutoff can be tie-free; every cutoff has values
that straddle it. `docs/measurements/README.md` now says what is actually true.

### 8b. The real interior knots, seen for the first time

| margin | interior knots |
|---|---|
| `bs(attained_age, df=6)` | **43.0, 60.0, 76.0** |
| `bs(calendar_year, df=3)` | **`[]`** |
| `bs(duration_years, df=4)` | 7.0 |

Close to the uniform-grid 42/60/78 but not equal, so the cell distribution is
near-uniform in age. And the empty calendar list **confirms on the real fit** what
slice 1 derived from the design: the shipped year margin has zero interior knots
and is a global cubic.

### 8c. The climb is invariant to the setting — which is the finding

| Age | span (cubic → quad) | climb 2013→2019 (cubic → quad) | early-vs-late Δ (cubic → quad) |
|---:|---|---|---|
| 45 | 3.99 → 3.58 | **3.54 → 3.58** | **2.38 → 2.39** |
| 55 | 1.94 → 1.63 | 1.65 → 1.63 | 1.11 → 1.09 |
| 65 | 0.82 → 0.55 | 0.53 → 0.55 | 0.35 → 0.36 |
| 75 | 1.38 → 1.38 | 1.38 → 1.38 | 0.92 → 0.92 |
| 85 | 1.93 → 1.42 | 1.40 → 1.42 | 0.94 → 0.94 |

Removing a polynomial order from the calendar margin changes the early-vs-late
contrast by **at most 0.02 points at any age**, and leaves the verdict
(`acceleration`, 0/5 slower) untouched. Age 45's climb is *unchanged*: 3.54 → 3.58.

What the quadratic **does** remove is curvature — the cubic's mid-window dip (age
45 runs 0.05 → −0.40 → 3.59; the quadratic runs a straight −1.20 → 2.38). Span
falls 0.3–0.5 points at three of five ages. So the slice-1 mechanism **is present
and is measurable**; it is simply not what age 45 is made of.

### 8d. Consequences, including for slices 1–3

**The ILEC measurement's stated reason for distrusting age 45 is not supported.**
§3 attributed the ramp to a terminal artifact of an over-flexible spline. Lowering
the flexibility leaves it intact, so that explanation is out. The acceleration is
also *resolvable* under the quadratic — age 45's 2013 band is [−1.98, −0.42]
against 2019's [1.63, 3.12].

**That is not the same as the climb being real improvement**, and this document
does not claim it is. It rules out one explanation. Duration mix *within* a band,
`uw_class` composition drifting at young ages, the empirical `q_base` at sparse
ages, and genuine underwriting-era effects all remain live, and none of them is
addressed by anything measured here.

**Slices 1–3 stand as a finding about the estimator, not about this book.** The
artifact is real, reproducible, and worth the guard tests; it is not the
explanation for the thing that motivated looking for it. That distinction is the
whole reason slice 4 existed rather than shipping the synthetic result as a
conclusion.

**And §7's hedge was wrong in direction.** It said the fixture's simplifications
"plausibly make the real artifact larger rather than smaller". Relative to the
signal on this book, it is smaller. A guess about which way a limitation cuts is
still a guess.

### 8e. The quadratic is the better fit, on the one check that is independent

Against SOA's own published expected deaths — the only comparison here that does
not use our model on both sides:

| | cubic | quadratic |
|---|---:|---:|
| mean absolute difference vs SOA MI | 0.006100 | **0.005488** (−10%) |
| mean difference vs SOA MI | 0.002682 | **0.001732** (−35%) |
| Pearson dispersion φ | 1.16326 | 1.16388 |

Closer to SOA on both, at the same dispersion and one fewer parameter. That is a
reason to prefer `--year-df 2 --year-degree 2` on an eight-year window — arrived at
from the fixtures and independently corroborated here.

`ae_by_year` and `standardised_ae` are **byte-identical** between the two runs, as
they must be: A/E is actual against SOA's expected and does not involve our fit.
The quadratic report therefore duplicates already-committed figures rather than
disclosing anything new (`DATA_LICENSING.md` §5c).
