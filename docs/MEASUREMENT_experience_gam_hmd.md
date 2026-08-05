# Measurement: the tensor MI surface against real HMD population experience

**Slice 2 of** `docs/PLAN_experience_gam_realdata.md`.
**Run by** the maintainer, 2026-08-05, on HMD USA 1990–2019, ages 25–95, both sexes.
**Raw output:** `docs/measurements/experience_gam_hmd_usa.{json,md}` — generated
verbatim by `scripts/experience_diligence.py`, never hand-edited.
**Harness:** ADR-182, at `e0a0ebb`.

---

## 1. The headline

**The fit reproduces the documented post-2010 US improvement slowdown, and
localises it to ages 45–65.**

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
- **Cross-population confirmation is not yet run.** GBRTENW has its own documented
  post-2011 slowdown and would materially strengthen the claim; the command is in
  `RUNBOOK_experience_data_acquisition.md` §3. Until then this is one population.

## 7. Verdict against slice 2's acceptance criteria

| Criterion | Outcome |
|---|---|
| Post-2010 US slowdown answered **either way** | ✅ Reproduced, and localised to ages 45–65 |
| Compared against the published reference | ✅ Qualitative structure agrees (§3) |
| Cross-population agreement characterised | ⚠️ **Not run** — GBRTENW outstanding |
| No data files added | ✅ Findings only; the 1x1 files never left the maintainer's machine |
