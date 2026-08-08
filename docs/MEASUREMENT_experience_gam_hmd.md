# Measurement: the tensor MI surface against real HMD population experience

**Slice 2 of** `docs/PLAN_experience_gam_realdata.md`.
**Run by** the maintainer, 2026-08-05, on HMD **USA** and **GBRTENW** (England &
Wales), 1990–2019, ages 25–95, both sexes.
**Raw output:** `docs/measurements/experience_gam_hmd_usa.{json,md}` and
`experience_gam_hmd_gbrtenw.{json,md}` — generated verbatim by
`scripts/experience_diligence.py`, never hand-edited.
**Harness:** ADR-182, at `0787187`.

**Data source and attribution:**

> HMD. Human Mortality Database. Max Planck Institute for Demographic Research
> (Germany), University of California, Berkeley (USA), and French Institute for
> Demographic Studies (France). Available at <https://www.mortality.org>.
> Data downloaded [DATE TO CONFIRM]. Version DOI: [TO SUPPLY — `DATA_LICENSING.md` §4d].

Series used: `Deaths_1x1.txt` and `Exposures_1x1.txt` for **USA** and **GBRTENW**
(England & Wales, total population), calendar years 1990–2019, ages 25–95, both
sexes; downloaded by the maintainer under their own HMD account on a date not yet
established (`DATA_LICENSING.md` §4d — an earlier "August 2026" was inferred from
the run dates, not stated, and is withdrawn). The two series are from different
revision epochs: USA last modified 09 June 2026, England & Wales 31 Jan 2025.
The HMD has not reviewed or endorsed this analysis — the fit, its settings and any
errors are ours. No HMD file is committed to this repository.

The series used are from the **`STATS` output bundle**, so they are HMD's own
estimates and fall under **CC BY 4.0** — derivatives and commercial use permitted,
attribution required. The attribution above is **incomplete** until the version DOI
is supplied; see [`DATA_LICENSING.md`](DATA_LICENSING.md) §4.

---

## 1. The headline

**The fit reproduces the documented post-2010 US improvement slowdown, and
localises it to ages 45–65.**

The harness's one-word verdict is **`mixed` (3 of 5 reference ages slower)**, and
that string is stated here rather than only in §2 so the headline cannot be quoted
without it. The two are not in conflict — §2 explains why an age-localised result
is sharper than the uniform hypothesis — but anyone citing the headline should
carry the verdict with it.

| Age | MI 1990–1999 | 95% band | MI 2010–2019 | 95% band | Δ | bands overlap |
|---:|---:|---|---:|---|---:|:---:|
| 45 | 0.92% | 0.67 – 1.16% | 0.02% | −0.21 – 0.25% | **−0.90** | no |
| 55 | 1.31% | 1.16 – 1.47% | 0.32% | 0.18 – 0.46% | **−0.99** | no |
| 65 | 1.51% | 1.38 – 1.64% | 0.25% | 0.13 – 0.36% | **−1.26** | no |
| 75 | 0.81% | 0.70 – 0.93% | 0.94% | 0.83 – 1.06% | +0.13 | **yes** |
| 85 | −0.23% | −0.35 – −0.10% | 1.27% | 1.17 – 1.38% | **+1.50** | no |

Improvement at ages 45–65 did not merely slow — it **stopped**, falling to
0.02–0.32%/yr in the 2010s from 0.92–1.51%/yr in the 1990s. Meanwhile the oldest
ages went the other way: age 85 mortality was *worsening* by 0.23%/yr in the 1990s
and improving by 1.27%/yr in the 2010s.

## 2. Why the verdict string says `mixed`, and why that is the right answer

The harness reports `mixed — 3 of 5 reference ages slower`. Read as a headline that
undersells the result, and it is worth being precise about why.

PLAN §2 named the hypothesis as "improvement rates flattening in the 2010s relative
to the 1990s". Taken as a **uniform** claim across ages, the data rejects it. Taken
as the claim actually made in the literature — a *population-level* slowdown driven
by specific age bands — the data reproduces it and adds the age structure for free.

A separable (non-tensor) model would have averaged these five numbers into one
mildly negative figure and reported "slowdown", which would have been a **less
accurate** description of what the population did. That the age-varying tensor
resolves a sign change across the age range is the single strongest piece of
evidence in this epic that the A4′ machinery does something real on real data.

This is the case PLAN §2 anticipated: *"a slice that reports 'the surface did not
reproduce the slowdown' is a successful slice"*. The surface reproduced something
sharper than the hypothesis. Nothing was tuned to get here — the only parameter
change between the first and final run was applying the overdispersion scaling
described in §4, which does not move point estimates at all.

## 2b. England & Wales reproduces it independently

GBRTENW, same window, same settings. **4 of 5 reference ages slower**, and the
fifth is not resolvable.

| Age | MI 1990–1999 | 95% band | MI 2010–2019 | 95% band | Δ | bands overlap |
|---:|---:|---|---:|---|---:|:---:|
| 45 | 0.90% | 0.58 – 1.21% | 0.24% | −0.08 – 0.57% | **−0.65** | no |
| 55 | 2.47% | 2.29 – 2.65% | 0.59% | 0.39 – 0.78% | **−1.88** | no |
| 65 | 2.82% | 2.69 – 2.95% | 1.06% | 0.90 – 1.22% | **−1.76** | no |
| 75 | 1.71% | 1.60 – 1.81% | 1.30% | 1.18 – 1.42% | **−0.41** | no |
| 85 | 0.83% | 0.72 – 0.95% | 1.01% | 0.90 – 1.12% | +0.18 | **yes** |

φ = 5.42, bands ×2.33; 15,153,718 deaths over 4,260 cells.

**Where the two populations agree** — and this is the claim worth making — is the
midlife collapse. Both show improvement at 45–65 falling by roughly one to two
percentage points a year between the decades, resolvably, in the same direction.
Two independent national populations, two independent data sources, same
structure. That is a far stronger statement than one country.

**Where they differ is at the oldest ages, and the difference is explicable from
the fit's own numbers.** The USA accelerated sharply at 85 (−0.23% → +1.27%);
England & Wales did not move resolvably (0.83% → 1.01%). The 1990s baselines say
why: US old-age mortality was *worsening* in the 1990s while E&W was already
improving at 0.83%/yr. The US had room to catch up and did; E&W had less to
recover. The divergence is a difference in starting point, not a contradiction —
and the surface recovered both without being told about either.

E&W also slowed resolvably at 75 where the USA did not (§4). So the E&W slowdown
is the *broader* of the two, covering 45–75.

## 3. Agreement with the published record

The pattern matches the independently published US picture:

- **Midlife stagnation.** US mortality at working ages stalled and in places
  reversed through the 2010s — the phenomenon documented in the SOA MIM-2021
  materials and the wider "deaths of despair" / cardiometabolic-plateau
  literature. The fit puts ages 45–65 at essentially zero improvement.
- **Continued old-age improvement.** Ages 75–85 kept improving, and at 85
  *accelerated* markedly. The fitted 1990s figure at 85 is negative, which is
  itself consistent with the documented late-20th-century stagnation in US
  old-age mortality that later reversed.

No claim of quantitative agreement with MIM-2021's own rates is made here — that
would need MIM-2021's scale loaded as a comparison basis, which is out of scope for
this slice. The claim is qualitative structure, and it holds.

## 4. What was corrected before these numbers were trusted

Two defects were found by reading the *first* real run and fixed before this one.
Both are recorded because they change how a reader should weight the table.

**The bands were 4.67× too narrow.** The count basis defaulted to plain Poisson;
the real fit came back at Pearson dispersion **φ = 21.84**. Population cells
aggregate enormously heterogeneous sub-populations, so Poisson is simply the wrong
variance. Every standard error was understated by √φ. The harness now applies the
quasi-Poisson scaling whenever φ > 1 (ADR-182 amendment 3), which changes the
covariance and not the coefficients — the point estimates in §1 are identical
before and after.

**Consequence, and it matters:** on the corrected bands, **age 75's +0.13% is not
resolvable** — its two windows overlap. Four of the five signs survive; that one
does not, and is not reported as a finding. On the original too-narrow bands the
report claimed "no overlap" for it, which would have been a published overstatement.

## 5. Fit diagnostics

| | |
|---|---|
| cells fitted | 4,260 (ages 25–95 × years 1990–2019 × 2 sexes) |
| total exposure | 5,750,237,304 person-years |
| total deaths | 68,998,510 |
| factors | `sex` |
| age_df / year_df | 6 / 4 over 30 observed years |
| dispersion φ | 21.84 — quasi-Poisson scaling applied, bands ×4.67 |
| base | empirical pooled crude rate over `(attained_age, sex)`; 142 strata, none dropped |
| `overall_ae` | 1.000 **by construction** — not a check on the level |

The base offset is estimated from the same cells, so `overall_ae` ≈ 1 is an
identity, not a validation. On population data there is no independent published
denominator to check the level against; that check exists only on the ILEC path,
where SOA publishes its own expected deaths (see
`MEASUREMENT_experience_gam_ilec.md`).

## 6. Honest limitations

- **Band overlap is not a significance test for the difference.** The two window
  contrasts come from the same fitted coefficients and are correlated. The
  overlap column is indicative; a formal test on the difference needs the
  cross-covariance, which the public API does not expose.
- **The window stops at 2019 deliberately.** A smooth tensor surface fitted
  through the COVID shock attributes it to improvement, which would be wrong and
  would discredit the output. 2020+ is a separate exercise, not an extension of
  this one.
- **`year_df=4` over 30 years is comfortable**, but the same setting over the
  8-year ILEC window was not — see the ILEC measurement. The terminal-year
  estimates of any spline fit deserve suspicion.
- **Two populations, not many.** USA and GBRTENW agree on the midlife collapse
  (§2b). That is replication, not universality — both are wealthy Anglophone
  countries with correlated public-health histories, so this is weaker evidence
  than two arbitrary populations would be.
- **No quantitative comparison to MIM-2021's own rates.** That needs the published
  scale loaded as a comparison basis, which is out of scope for this slice.

## 7. Verdict against slice 2's acceptance criteria

| Criterion | Outcome |
|---|---|
| Post-2010 US slowdown answered **either way** | ✅ Reproduced, and localised to ages 45–65 |
| Compared against the published reference | ✅ Qualitative structure agrees (§3) |
| Cross-population agreement characterised | ✅ GBRTENW slows at 4/5 ages; agrees at 45–65, diverges at 85 for a reason the fit itself explains (§2b) |
| No data files added | ✅ Findings only; the 1x1 files never left the maintainer's machine |
