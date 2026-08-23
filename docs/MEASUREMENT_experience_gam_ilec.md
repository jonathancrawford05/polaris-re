# Measurement: the tensor MI surface against real SOA-ILEC insured experience

**Slice 3 of** `docs/PLAN_experience_gam_realdata.md`.
**Run by** the maintainer, 2026-08-05, on `ILEC_2012_19 - 20240429.txt` (~12.5 GB),
ages 25–95, `--year-df 3`, twice: once pooled across duration and once with
`--duration-bands`; the banded run re-run 2026-08-06 to add the mix
decomposition.
**Raw output:** `docs/measurements/experience_gam_ilec.{json,md}` (pooled) and
`experience_gam_ilec_duration_banded.{json,md}` — generated verbatim by
`scripts/experience_diligence.py`, never hand-edited.
**Harness:** ADR-182 through amendment 5.

**Data source and attribution:**

> Society of Actuaries Research Institute, Individual Life Experience Committee
> (ILEC). Individual life insurance mortality experience study, study years
> **2012–2019**; dataset file `ILEC_2012_19 - 20240429.txt`. Available at
> <https://www.soa.org>.

Obtained by the maintainer in August 2026 through SOA's own download, accepting
the terms presented there. **SOA supplies both sides of the level check in §1(a):**
the experience *and* the `ExpDth_VBT2015_Cnt` / `ExpDth_VBT2015_MI_Cnt` expected
deaths on SOA's 2015 VBT basis, which is what makes that A/E independent of our
model rather than an identity. The SOA has not reviewed or endorsed this analysis;
where §1(b) reports that the fitted surface improves faster than SOA's scale
assumed, that is a statement about **our fit**, not a correction to SOA. No ILEC
data file is committed to this repository; what is, is inventoried in
[`DATA_LICENSING.md`](DATA_LICENSING.md) §1.

> **Licensing caveat — read before reusing anything below.** The SOA Website Terms
> of Use (read 2026-08-07, quoted in `DATA_LICENSING.md` §3) are the only document
> governing this dataset, and they are restrictive: use is permitted for "personal
> or other non-commercial, educational purposes", public **or** commercial
> reproduction and distribution is prohibited, derivative works are barred, and the
> mechanism offered for anything else is **prior written permission**, which has
> been drafted (§6) but **not yet granted**. This measurement is published by a
> single contributor developing these models for their own education, with the
> position and its change-triggers recorded in `DATA_LICENSING.md` §5. Treat the
> numbers here as findings under an unresolved permission question, not as SOA
> material cleared for redistribution.

> **Read the duration-banded run.** The pooled run is retained because the
> comparison between them *is* one of this slice's findings, but its fitted
> surface is confounded — see §2.

---

## 1. Two findings, and they are in tension

**(a) Aggregate A/E against SOA's published expected deaths is flat.** This
number involves no model of ours at all — it is actual deaths over SOA's own
expected, on identical cells, so it is identical in both runs.

| | |
|---|---|
| Overall A/E, VBT 2015 basis | **1.0791** |
| Overall A/E, VBT 2015 **with SOA's MI** | **1.0823** |
| Drift in A/E-with-MI | **−0.00119 / yr** (−0.110% of its mean) |

**(b) The duration-controlled fitted surface says we improved *faster* than SOA
assumed** — by **+0.27%/yr** on an exposure-weighted basis at the reference ages
(mean absolute difference 0.61%), against SOA's flat ~0.58%/yr scale.

**(c) With the covariate mix held fixed, the A/E drift is −0.150%/yr, not the
−0.119%/yr the crude series shows.** The crude figure understates the experience
signal by 27%, because a modest mix effect pushes the other way. See §4 — the
measurement confirmed the direction of the reading that preceded it and cut its
claimed magnitude.

## 2. Duration mix was confounding the trend — measurably

The first ILEC fit pooled across duration. The caveat said mix drift could leak
into the improvement trend; it was unmeasured. It has now been measured, and the
leak was **large**.

| | pooled | duration-banded |
|---|---|---|
| Pearson dispersion φ | 2.25 | **1.163** |
| cells fitted | 15,880 | 125,676 |
| base strata (dropped) | 426 (0) | 3,767 (61) |
| dropped exposure share | 0.000% | **0.009%** |
| slowdown verdict | `mixed`, 1/5 slower | `acceleration`, **0/5 slower** |

Banding took dispersion from 2.25 to **1.163** — close to nominal Poisson. The
model now explains variation it previously could not, at a cost of 0.009% of
exposure. That is not a marginal improvement in fit; it is the removal of a real
omitted variable.

**Why the fitted surface legitimately moves.** The duration representative is
calendar-invariant by construction, so the duration term cancels exactly in the
calendar contrast `η(x,y) − η(x,y−1)` and cannot itself shift MI. What changes is
the **cell set**: conditioning on duration means the `te(age, calendar_year)`
tensor is no longer absorbing duration-mix drift that correlates with calendar
year. The pooled fit was attributing part of an ageing book's rising mortality to
"less improvement".

Every reference age moved, and all in the same direction:

| Age | pooled 2016–19 | banded 2016–19 |
|---:|---:|---:|
| 45 | 2.16% | 2.14% |
| 55 | 1.33% | **2.16%** |
| 65 | 0.40% | **1.55%** |
| 75 | 0.67% | **1.49%** |
| 85 | 0.77% | **1.01%** |

## 3. The slowdown test: `acceleration`, 0 of 5 ages slower

| Age | MI 2012–2015 | 95% band | MI 2016–2019 | 95% band | Δ | bands overlap |
|---:|---:|---|---:|---|---:|:---:|
| 45 | −0.24% | −0.88 – 0.39% | 2.14% | 1.51 – 2.76% | +2.38 | no |
| 55 | 1.06% | 0.70 – 1.41% | 2.16% | 1.81 – 2.52% | +1.11 | no |
| 65 | 1.19% | 0.91 – 1.48% | 1.55% | 1.27 – 1.82% | +0.35 | **yes** |
| 75 | 0.57% | 0.33 – 0.81% | 1.49% | 1.27 – 1.72% | +0.92 | no |
| 85 | 0.07% | −0.12 – 0.26% | 1.01% | 0.82 – 1.20% | +0.94 | no |

Four of five are resolvable accelerations. **This does not contradict the HMD
slowdown**, and reading it that way would be the main error available here:

> **The bands this table rests on were measured on 2026-08-09, and they hold**
> (ADR-187). Every "resolvable / overlaps" verdict above is an inference from a
> delta-method interval that had never been checked against its nominal rate — it
> was 95% because the formula said so. A 200-replicate simulation puts it at
> **95.7%–95.9%** against nominal 95%, and *young ages are the best-covered region*,
> not the worst. The pre-registered hypothesis was that these bands under-cover at
> the death-poor young end, which would have undermined the age-45 row specifically;
> it is falsified. **Two caveats travel with that.** Coverage was measured on truths
> the basis can represent — where it cannot, coverage falls to ~85% overall and ~67%
> at age 80+, so the table's protection is against sampling noise, not against
> misspecification. And it is a statement about the *interval*, not about the point
> estimates, which ADR-184 showed swing far more at 45 than at 85.

- **Different question.** ILEC 2012–2019 lies *entirely after* the ~2010 break.
  It cannot speak to a post-2010 change; it describes what happened within the
  2010s.
- **Different population.** Insured lives are underwritten — see §5.
- ~~**Age 45 is still boundary-contaminated.**~~ **This explanation was tested on
  2026-08-08 and is not supported.** Age 45's fitted MI runs 0.05% (2013) → 3.59%
  (2019), and the reading here was that an over-flexible spline was ramping at the
  terminal year. Refitting with a *less* flexible calendar margin
  (`--year-df 2 --year-degree 2`) leaves the climb intact — 3.54 → 3.58 points —
  and moves the early-vs-late contrast by 0.01. Whatever age 45 is, it is not this.
  `year_df=3` was also never "the floor": that was a floor on `df` with `degree`
  hardcoded at 3, and `df=1, degree=1` is both legal and less flexible (ADR-184).
  See `MEASUREMENT_gam_ramp_mechanism.md` §8. **Ages 55–85 remain the defensible
  ones**, but now because their bands are narrow, not because 45 is discredited.

## 4. Experience versus mix — measured, and it corrects §4's earlier claim

Direct standardisation over `attained_age, sex, smoker, uw_class, duration_months`,
holding the mix fixed at the whole-window average. 14,757 complete-panel cells
covering **99.96%** of expected deaths, so this speaks for essentially the whole
book.

| component | slope |
|---|---|
| crude A/E-with-MI | **−0.001185 / yr** |
| **experience** (mix held fixed) | **−0.001505 / yr** |
| **mix** | **+0.000320 / yr** |

Additive by construction, and it holds to 2e-15.

> **These figures are the BANDED run's, and the pooled run now reports a
> different-looking decomposition. Both are right.** Since 2026-08-23
> `docs/measurements/experience_gam_ilec.json` (the **pooled** run) also carries a
> `standardised_ae` block, and read cold it appears to contradict the table above:
> its mix term (−0.000990/yr) *dominates* its experience term (−0.000195/yr),
> where here mix is small and opposite-signed.
>
> They standardise over different key sets on different cell sets. The table above
> comes from `experience_gam_ilec_duration_banded.json` — five keys **including
> `duration_months`**, 14,757 cells. The pooled block has four keys and 1,973
> cells, because the pooled fit has no duration dimension to hold fixed, so its
> "mix" necessarily absorbs the uncontrolled duration composition.
>
> That is not a contradiction of §4; it is §2's and §4's own thesis measured a
> second way — **duration mix is the dominant confounder in the pooled fit.** The
> note is here because the session that regenerated these files on 2026-08-23 hit
> the apparent inversion and had to work out why, and a future reader would too.

**The direction of the earlier inference is confirmed.** Experience drifts down —
the business improved faster than SOA's scale assumed — and mix pushes the other
way, exactly as an ageing book drifting toward higher-mortality durations would.

**The magnitude is not.** An earlier version of this section said a flat crude A/E
was "the product of genuine improvement running ahead of the assumed scale,
**cancelled by** a book whose duration mix is drifting" — language implying two
comparable effects roughly annihilating each other. They are not comparable:

- mix offsets only **21.2%** of the experience signal;
- the crude slope is already **78.8%** of the experience slope.

So the crude number is not a coincidence of cancellation. It is a mostly-honest
reading of the experience signal, **understated by 27%** because a modest mix
effect works against it. That is a real and material correction to a quoted
figure — the A/E-with-MI drift is −0.150%/yr on experience, not the −0.119%/yr
the crude series shows — but it is not the dramatic story the earlier wording told.

**And the mix slope itself is weak evidence.** The year-by-year mix effect runs
−0.0017, +0.0014, −0.0016, −0.0019, −0.0048, −0.0059, +0.0045, +0.0017: **three
sign changes across eight points**, with the positive slope driven substantially
by the last two years. A trend fitted through that is fragile. The *existence* and
*direction* of a mix effect are established; its **rate** is not, and should not
be extrapolated.

**What survives, stated exactly.** A crude A/E understates this book's experience
drift against SOA's basis by about a quarter, because duration mix works in the
opposite direction. That is enough to matter when the drift is the number being
quoted, and it is the kind of thing a pooled A/E study cannot show and a fitted,
duration-controlled surface can. It is *not* evidence that a flat A/E is generally
a coincidence of two large cancelling forces — on this book, over these eight
years, it was not.

This section is now a measurement rather than an inference, and the measurement
was worth taking precisely because it moved the claim.

## 5. Insured-versus-population divergence

PLAN §2: *"ILEC should not look identical to HMD — a model that shows them
identical has a bug; the interesting output is the shape of the difference."*

| Age | HMD USA population, 2010s | ILEC insured, 2016–19 (banded) |
|---:|---:|---:|
| 55 | 0.32% | **2.16%** |
| 65 | 0.25% | **1.55%** |
| 75 | 0.94% | 1.49% |
| 85 | **1.27%** | 1.01% |

Insured lives improved roughly **six to seven times faster than the US population
at ages 55–65** over comparable years, and slightly *slower* at 85. The direction
is what underwriting predicts: the US midlife mortality stagnation is concentrated
in populations that underwriting screens out, so an insured book largely does not
participate in it. By 85 selection has worn off and the two converge, with the
population's late-life acceleration (§ HMD measurement) taking it slightly ahead.

Age 45 is excluded from the table for the boundary reason in §3. The windows are
not identical (HMD 2010–2019 against ILEC 2016–2019), so this compares overlapping
regimes rather than the same years.

## 6. Fit diagnostics (duration-banded run)

| | |
|---|---|
| raw file | 12,477,136,749 bytes, tab-delimited |
| cells loaded (post-filter) | 11,059,501 |
| cells after aggregation | 126,223 |
| cells fitted | 125,676 |
| aggregation level | `attained_age, calendar_year, sex, smoker, uw_class, duration_months` |
| duration bands | 9 — start policy years 1, 2, 3, 4, 6, 11, 16, 21, 26 |
| `uw_class == "U"` held out | 277,173 cells |
| zero-exposure cells dropped | 152, holding 0.0 deaths |
| total deaths | 4,354,590 |
| factors | `sex`, `smoker`, `uw_class` |
| dispersion φ | **1.163** — scaling applied, bands ×1.08 |
| `overall_ae` | 1.000 **by construction** — the real level check is §1 |

**The `uw_class` disambiguation was material.** 11,059,501 loaded cells against
the 9,714,592 measured before ADR-181's composition fix: ~1.35M cells were being
pooled by `Preferred_Class` alone, merging class-2-of-2 (worst) with class-2-of-4
(second-best).

## 7. Honest limitations

- **Eight years is short** for any trend-change question (§3).
- ~~**Age 45 remains boundary-contaminated** and `year_df=3` is the floor. If that
  age matters commercially, it needs a longer vintage, not a different setting.~~
  **Both halves retracted 2026-08-08.** `year_df=3` is not a floor on flexibility,
  and a different setting does not remove age 45's climb — so the sentence was
  wrong about the mechanism *and* about the remedy. What survives is narrower and
  weaker: age 45's acceleration is robust to the calendar margin's flexibility and
  is resolvable on its own bands, which rules out one explanation without
  establishing that it is genuine improvement. Duration mix *within* a band,
  `uw_class` composition drift at young ages, and the empirical `q_base` at sparse
  ages are all still untested. `MEASUREMENT_gam_ramp_mechanism.md` §8d.
- **Selection within a band is still pooled.** Bands 1/2/3 are singly resolved
  because that is where selection moves fastest, but 26+ is one open band.
- **Band overlap is not a significance test for the difference** — the two window
  contrasts share fitted coefficients.
- **The A/E *level* of 1.079 is not interpreted.** Actual deaths run ~8% above VBT
  2015 expected on this book; decomposing that into basis, mix and selection
  effects is not attempted here. Only the *drift* is claimed.
- ~~**§4's decomposition is inferred, not measured.**~~ **Measured 2026-08-06.**
  It confirmed the direction and **cut the claimed magnitude by a factor of ~5** —
  see §4. The mix slope itself rests on a sign-flipping 8-point series and should
  not be extrapolated.

## 8. Verdict against slice 3's acceptance criteria

| Criterion | Outcome |
|---|---|
| Insured surface fitted and compared to the population surface | ✅ §5 |
| Divergence characterised | ✅ Insured improve ~6–7x faster at 55–65, slightly slower at 85 |
| Column-map override committed if needed | ✅ `ILEC_2012_19_COLUMN_MAP` shipped in ADR-181 |
| No data files added | ✅ Findings only; the 12.5 GB file never left the maintainer's machine |

**Beyond the original criteria:** the duration-mix confound (§2) and the
offsetting-effects reading of a flat A/E (§4) were not anticipated by the plan.
Both came from running the harness twice and comparing, which is only possible
because the aggregation level is an explicit parameter (ADR-182) rather than a
buried default.

<!-- measurement-provenance
fingerprint: 6ebf696b7d4106661c0e1e625d80d329da6c2567cbc5678d96f5b9f5006ed71a
generated: 2026-08-23
producer: scripts/experience_diligence.py
method: asserted
head: b45d497
note: raw output regenerated 2026-08-23 against ILEC extract 'ILEC_2012_19 - 20240429.txt' (12,477,136,749 bytes, 2012-2019); docs/measurements diff: no fitted quantity moved; banded standardised block byte-identical; pooled run gained an additive 4-key standardised_ae section + duration_degree; last-ulp jitter on dropped_exposure_share
-->
