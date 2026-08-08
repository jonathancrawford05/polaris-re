# Plan: diagnose the age-45 ramp before rebuilding the smoother

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Age 45 stays boundary-contaminated
on the ILEC fit", NICE-TO-HAVE, promoted to the front of the queue by the
2026-08-07 specification review.
**Predecessor:** `CONTINUATION_experience_gam_realdata.md` (COMPLETE) — this plan
consumes its harness and its committed findings.
**Total slices:** 4 (slices 1–3 autonomous, slice 4 one maintainer run)
**Estimated scope:** ~1.5–2 dev-days autonomous + a single ILEC re-run

## Overall goal

`MEASUREMENT_experience_gam_ilec.md` §3 reports that age 45's fitted MI ramps from
0.05% (2013) to 3.59% (2019) and calls it boundary contamination that "needs a
longer vintage, not a different setting". That sentence is load-bearing — it blocks
every age-45 insured-improvement claim and it justifies waiting on a longer ILEC
release. It has never been tested. **The point of this plan is to find out whether
it is true**, cheaply, before committing to the penalized rebuild that would
supersede the whole question.

The rebuild (P-splines with REML-selected λ) is almost certainly the right
destination regardless. This plan exists because a rebuild aimed at a
misdiagnosed cause is expensive to discover late, and because the diagnostic
doubles as the quantified argument for the rebuild.

## The two hypotheses

Both are consistent with the observed ramp. They are distinguishable, and they
imply different fixes.

**Hypothesis A — the year margin is a cubic polynomial, not a spline.** At
`year_df=3` with `patsy.bs` (degree 3, no intercept) the calendar margin has
**zero interior knots** — verified 2026-08-07 by building the design directly. It
is therefore a global cubic over eight years, which permits MI itself to vary
quadratically. An unpenalized cubic must place its curvature somewhere, and
end-of-range ramping is its characteristic failure mode. *Predicts:* the ramp
shrinks as the calendar window lengthens at fixed `df`, and vanishes entirely at
`df=1, degree=1` (see the ladder in slice 3 — `degree` alone is not sufficient).

**Hypothesis B — age 45 sits next to an interior age knot.** On a uniform age grid
25–95, `bs(age, df=6)` places interior knots at **42.5, 60, 77.5**. Age 45 is ~2.5
years above the first one, where the age basis changes fastest, and the tensor
interaction lets year-curvature localise there. *Predicts:* the anomaly follows the
knot rather than the age — shift the fitted age range and the affected reference
age moves with it.

They are not exclusive; A could be the mechanism and B the reason 45 shows it
worst. The crossed design in slice 2 separates the contributions.

> **On real ILEC the knots are not at 42.5/60/77.5.** `patsy` places interior
> knots at **quantiles of the supplied vector**, and the supplied vector is one row
> per grouped cell — so the real knots sit at quantiles of the *cell* distribution,
> which is dense wherever the book has many strata. Nobody has ever looked at where
> they actually fall. Slice 3 makes every report state them.

---

## Slice 1: reproduce the ramp against a known truth (autonomous — no data)

- **Status:** **DONE (2026-08-07)** — `docs/MEASUREMENT_gam_ramp_mechanism.md`,
  `tests/test_analytics/test_experience_gam_ramp_diagnostic.py` (8 tests).
  **Both hypotheses this plan proposed were falsified**, and the real mechanism is
  a third thing: sampling noise at the death-poor young end, converted into a
  smooth multi-point swing by three free year parameters.
  - **A falsified.** Noiseless recovery at the shipped ILEC configuration is
    *exact* (1e-6). A cubic represents a straight line perfectly, so a constant
    truth has no bias to find. "An unpenalized cubic must place its curvature
    somewhere" is true of interpolation through noise, not of least squares on a
    representable truth — the distinction the plan missed.
  - **C supported.** Poisson noise alone, on a truth that is exactly 1.5% at every
    age and year, produces a **3.13-point** swing at age 45 against **0.46** at
    85 — because deaths at 45 are ~24x scarcer. Span scales inversely with total
    deaths (0.56 → 27.18 as deaths fall 12.9M → 12.9k) and varies 0.17–3.83
    across seeds, which is what a variance artifact looks like.
  - **B falsified.** Shifting the fitted age range moves the first interior knot
    across 42 / 47 / 37, and in every case the swing peaks at the **youngest
    fitted age**, 2.7–3.5x its value at the knot. The knots are innocent.
- **Depends on:** nothing

**Why synthetic is the stronger evidence here, not the weaker.** On real ILEC the
true improvement surface is unknown, so a ramp is only ever *suspicious*. On a
fixture with an injected constant surface, a ramp is **proof of artifact** — there
is nothing else it could be. This is the one question where the synthetic fixture
beats the real data outright, and it is the reason slice 4 is a confirmation rather
than the experiment.

**Scope.** Build an ILEC-shaped fixture in `tests/test_analytics/`: ages 25–95,
calendar years 2012–2019, both sexes, an exposure profile that falls with age the
way a real book does, and a **known constant** MI of 1.5%/yr at every age. Fit at
the exact configuration the committed ILEC reports used — `age_df=6`, `year_df=3`,
count basis, overdispersion auto — and measure fitted MI at the five reference ages
across 2013–2019.

**Tests.**
- `test_constant_surface_is_recovered_flat` — with a constant injected MI, fitted
  MI at each reference age is flat across years to a stated tolerance. **This is
  the test that fails if hypothesis A is right**, and its failure is the finding.
- `test_a_genuine_ramp_is_still_recovered` — inject a surface whose MI genuinely
  ramps 0% → 3.5% at age 45 and require the fit to recover it. **Two-sided by
  construction**: without this, slice 3 could "fix" the artifact by building a
  smoother that cannot see any ramp, and the suite would applaud. The same
  discipline the slowdown verdict got in ADR-182.

**Acceptance criteria.**
- The ramp either reproduces on known-constant truth or it does not, and the
  outcome is recorded either way. **A slice that falsifies hypothesis A is a
  successful slice** and stops the rebuild being justified on a false premise.
- Magnitude comparable to the real 0.05% → 3.59% — if the fixture ramps by 0.2
  points where ILEC ramped by 3.5, the mechanism is present but is not the whole
  story, and that is a third finding.
- No `tests/qa/` goldens touched; nothing in `products/` moves.

---

## Slice 2: separate the two mechanisms (autonomous — no data)

- **Status:** **SUBSUMED by slice 1 (2026-08-07)** — the escape clause fired.
  Slice 1 falsified **both** A and B, so there are no contributions left to
  attribute. Its age-range sweep already ran the knot axis, and the
  deaths-scaling table already answers the window-length axis: a longer window
  adds calendar cells and therefore deaths at every age, and span falls
  monotonically with deaths. Nothing here would be learned twice.
- **Depends on:** Slice 1 (skip entirely if slice 1 falsifies A **and** B)

**Scope.** A crossed design over the slice 1 fixture, parametrised with
`pytest.mark.parametrize`:

| Axis | Levels | Discriminates |
|---|---|---|
| calendar window | 8, 12, 20 years at fixed `year_df=3` | A — ramp should shrink as the window lengthens |
| fitted age range | 25–95, 30–100, 20–90 | B — knots move; does the anomaly follow the knot or stay at 45? |

**Acceptance criteria.** A stated attribution: A alone, B alone, or both with a
rough split. That attribution is what tells slice 3 whether exposing `degree` can
possibly be sufficient — if B contributes materially, a linear year margin will not
fix age 45 on its own and only a penalty (or knot placement control) will.

---

## Slice 3: expose spline degree, and measure what it costs (autonomous — no data)

- **Status:** NOT STARTED — **re-aimed by slice 1.** The *benefit* side is already
  measured: a global linear year margin removes the swing completely (span 0.00,
  exact to 9.7e-17) **and** de-biases the level, returning age 45's mean fitted MI
  to 1.50% against the shipped cubic's 1.19% on a 1.50% truth. So this slice is no
  longer "does lowering the degree help" — it does. It is now **only** about
  measuring the price: how much genuine calendar curvature a lower order makes
  invisible, at each age. That price is what decides whether degree-lowering is a
  usable setting or merely an argument for the penalized rebuild.
- **Depends on:** Slice 1

**Scope.**
- Add `age_degree` / `year_degree` / `duration_degree` (default **3**, preserving
  every committed number) to `TensorMIModel`, threaded through
  `experience_diligence.py` and the CLI as `--year-degree` etc.
- Validation: `degree >= 1`, and `df >= degree`. `_MIN_SPLINE_DF = 3` must be
  **replaced, not kept** — it is a floor on `df` conditional on `degree` being
  hardcoded at 3, and it reads as though 3 were a floor on flexibility. It is not:
  `df=1, degree=1` is perfectly legal and is *less* flexible. The new message
  should state the real rule — `df >= degree`, interior knots = `df - degree`.
- **Report the fitted knot vectors** in the JSON `fit` block, per margin. Additive
  field; the notebook's `DEGRADED` machinery already handles a committed report
  that predates a field, so the four existing reports degrade rather than break.

**The flexibility ladder — `df == degree`, verified 2026-08-07.**

Degree alone does **not** control this, and an earlier revision of this plan was
wrong to imply it did. `degree=1` with `df=3` carries two interior knots, making MI
a *step function* in year — which ramps perfectly well. Pinning `df == degree` sets
interior knots to zero and leaves polynomial order as the only axis:

| `df` = `degree` | year margin | MI in time | free params (year) |
|---:|---|---|---:|
| 1 | global linear | **constant** | 1 |
| 2 | global quadratic | linear | 2 |
| 3 | global cubic | **quadratic** | 3 ← as shipped |

This reframes the finding the diagnostic is chasing. The committed ILEC reports
permit MI to vary **quadratically** across eight calendar years. Age 45's ramp is
not residual spline wiggle that a smaller `df` would have removed — it is the least
flexible *cubic*, and the window may only support a linear trend.

Proof that the bottom rung is exact, not approximate: differencing adjacent-year
design rows gives `max |contrast(step_k) - contrast(step_1)|` of **4.5e-01** at
`df=3, degree=3` against **9.7e-17** at `df=1, degree=1`. MI *is* that contrast, so
a linear year margin cannot ramp at machine precision.

**Tests.**
- `test_linear_year_margin_cannot_ramp` — at `df=1, degree=1` fitted MI is constant
  in year by construction; assert it recovers the injected constant.
- `test_linear_year_margin_cannot_see_a_real_ramp` — **the honest cost.** On the
  genuinely-ramping fixture, `df=1, degree=1` must *fail* to recover it. Asserting
  the limitation rather than describing it is what stops "lower the degree" being
  quietly adopted as a general fix.
- `test_degree_without_df_still_permits_a_ramp` — the trap this plan already fell
  into once: `degree=1, df=3` must be shown to ramp, so the two knobs cannot be
  confused again in code the way they were in prose.
- Defaults unchanged: an existing fixture fitted without the new arguments
  reproduces its current numbers exactly.

**Acceptance criteria.** A quantified trade-off table — artifact size against
genuine-curvature blindness, per degree. **That table is the argument for the
P-spline rebuild**: it shows the unpenalized basis forces a choice between seeing
a false ramp and being unable to see a true one, which is precisely the choice a
penalty removes.

---

## Slice 4: confirm on real ILEC (one maintainer run)

- **Status:** BLOCKED on slices 1–3
- **Depends on:** Slices 1–3

**Scope.** One command against the maintainer's cache, re-running the
duration-banded ILEC configuration at `--year-degree 3` (reproducing the committed
report byte-for-byte, which is also a determinism check) and at `--year-degree 1`.
The report now states its own knot positions, so the real age-knot geometry becomes
visible for the first time.

**Acceptance criteria.**
- The synthetic mechanism is confirmed or contradicted on real data.
- `MEASUREMENT_experience_gam_ilec.md` §3 and §7 are corrected. Either age 45
  becomes usable and "needs a longer vintage, not a different setting" was wrong,
  or it stays unusable and that sentence is finally *evidenced* rather than
  asserted. Both outcomes improve the document.
- No data files added; findings only (Design Anchor 6, and
  `DATA_LICENSING.md` §5 — note the SOA permission request is outstanding, so
  this re-run should **not** add new absolute counts to the committed reports).

---

## Follow-on epic (not in this plan): the penalized rebuild

Gated on slice 3's trade-off table. The destination is Eilers–Marx P-splines:
marginal bases with a generous `k`, Kronecker-structured difference penalties
`S_age = DᵀD ⊗ I` and `S_year = I ⊗ DᵀD`, penalized IRLS, and REML-selected λ
(REML over GCV — GCV undersmooths and has multiple minima).

Three things already established that the rebuild inherits:

- **`statsmodels` cannot do it directly.** `GLMGam` + `BSplines` penalize, and
  `select_penweight` selects λ, but the smooths are **additive only** — there is no
  tensor-product class (verified on 0.14.6). The Kronecker design and penalty must
  be hand-built.
- **The surface-extraction layer survives untouched.** Every band is `√(cᵀVc)` on
  a contrast row and is agnostic to how `V` was formed; swapping the delta-method
  covariance for the Bayesian `Vb = (XᵀWX + S)⁻¹φ` leaves the window contrast,
  the telescoping property and the quasi-Poisson scaling working as-is.
- **Determinism is the live risk.** λ selection introduces an optimizer, and
  `REPORT_SIGNIFICANT_DIGITS = 12` was calibrated against a ~1.2e-14 BLAS jitter in
  `cov_params`. An optimizer's output can exceed that, so λ likely needs rounding
  before it reaches the covariance. Budget for it rather than discovering it when
  the byte-stability test goes red.

Also inherited: **`k=10` is not a universal answer.** The rule is a generous upper
bound checked against effective df, and on ILEC's *eight distinct calendar years* a
`k=10` year margin has more basis functions than data points — 6–8 is the sane
range there, against 10–15 on HMD's 30 years.
