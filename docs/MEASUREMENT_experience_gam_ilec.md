# Measurement: the tensor MI surface against real SOA-ILEC insured experience

**Slice 3 of** `docs/PLAN_experience_gam_realdata.md`.
**Run by** the maintainer, 2026-08-05, on `ILEC_2012_19 - 20240429.txt` (~12.5 GB),
ages 25–95, `--year-df 3`, twice: once pooled across duration and once with
`--duration-bands`.
**Raw output:** `docs/measurements/experience_gam_ilec.{json,md}` (pooled) and
`experience_gam_ilec_duration_banded.{json,md}` — generated verbatim by
`scripts/experience_diligence.py`, never hand-edited.
**Harness:** ADR-182, at `0787187`.

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

Both are correct, and the tension between them is the most commercially useful
thing in this slice. See §4.

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

- **Different question.** ILEC 2012–2019 lies *entirely after* the ~2010 break.
  It cannot speak to a post-2010 change; it describes what happened within the
  2010s.
- **Different population.** Insured lives are underwritten — see §5.
- **Age 45 is still boundary-contaminated.** Its fitted MI runs 0.05% (2013) →
  3.59% (2019); the terminal ramp did not fully clear at `year_df=3`, which is
  the floor. Ages 55–85 no longer show it and are the defensible ones.

## 4. The tension in §1 is the finding a reinsurer should care about

Aggregate A/E-with-MI is flat, which reads as *"our improvement assumption is
fine."* The duration-controlled surface says the underlying business improved
**faster** than VBT 2015's scale assumes.

Both are true because they are offsetting. A flat aggregate A/E is the product of
genuine improvement running ahead of the assumed scale, **cancelled by a book
whose duration mix is drifting toward higher-mortality cells** as it ages and new
business slows.

The practical consequence: **a flat A/E is not evidence that assumptions are
sound.** It can be two effects of opposite sign, either of which can change
independently — and one of them is a mix effect that will keep moving as the block
matures. This is exactly the sort of thing a pooled A/E study hides and a fitted,
duration-controlled surface exposes, which is the case for the model existing.

Stated conservatively: this is one book over eight years, and the decomposition
above is inferred from the pooled-versus-banded contrast rather than measured
directly. It is a hypothesis with strong supporting evidence (§2), not a
quantified attribution.

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
- **Age 45 remains boundary-contaminated** and `year_df=3` is the floor. If that
  age matters commercially, it needs a longer vintage, not a different setting.
- **Selection within a band is still pooled.** Bands 1/2/3 are singly resolved
  because that is where selection moves fastest, but 26+ is one open band.
- **Band overlap is not a significance test for the difference** — the two window
  contrasts share fitted coefficients.
- **The A/E *level* of 1.079 is not interpreted.** Actual deaths run ~8% above VBT
  2015 expected on this book; decomposing that into basis, mix and selection
  effects is not attempted here. Only the *drift* is claimed.
- **§4's decomposition is inferred, not measured.** Quantifying the mix effect
  directly would need a standardised-mix A/E, which the harness does not compute.

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
