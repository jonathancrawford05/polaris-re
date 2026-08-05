# Measurement: the tensor MI surface against real SOA-ILEC insured experience

**Slice 3 of** `docs/PLAN_experience_gam_realdata.md`.
**Run by** the maintainer, 2026-08-05, on `ILEC_2012_19 - 20240429.txt` (~12.5 GB),
ages 25–95, `--year-df 3`.
**Raw output:** `docs/measurements/experience_gam_ilec.{json,md}` — generated
verbatim by `scripts/experience_diligence.py`, never hand-edited.
**Harness:** ADR-182, at `e0a0ebb`.

---

## 1. The headline

**Our fitted improvement agrees with SOA's own published assumption to about a
tenth of a percentage point per year.** That is the check PLAN §2 called the
strongest available, and it is the result worth quoting from this slice.

| | |
|---|---|
| Overall A/E, VBT 2015 basis | **1.0791** |
| Overall A/E, VBT 2015 **with SOA's MI** | **1.0823** |
| Drift in A/E-with-MI | **−0.00119 / yr** (−0.110% of its mean) |
| Fitted MI − SOA MI, exposure-weighted mean | **−0.041%** |
| Fitted MI − SOA MI, mean absolute | **0.368%** |

A flat A/E-with-MI profile means our experience improved at the rate SOA assumed.
It is flat to about a tenth of a point per year over eight years. The surface
comparison says the same thing a second way and at age level: essentially
unbiased (−0.04%), with year-to-year scatter of 0.37%.

This is a **numeric** external validation, computed on identical cells from
identical exposure with no model of ours standing between the two figures. It
replaces what would otherwise have been an eyeball comparison against a narrative.

## 2. The slowdown test returns nothing resolvable — and that is the correct answer

The harness reports `mixed — 1 of 5 reference ages slower`. The count is the least
informative part of it.

| Age | MI 2012–2015 | 95% band | MI 2016–2019 | 95% band | Δ | bands overlap |
|---:|---:|---|---:|---|---:|:---:|
| 45 | −0.66% | −1.54 – 0.22% | 2.16% | 1.30 – 3.02% | +2.82 | no |
| 55 | 0.48% | −0.01 – 0.97% | 1.33% | 0.84 – 1.82% | +0.85 | **yes** |
| 65 | 0.89% | 0.49 – 1.28% | 0.40% | 0.01 – 0.78% | −0.49 | **yes** |
| 75 | 0.64% | 0.32 – 0.96% | 0.67% | 0.37 – 0.97% | +0.03 | **yes** |
| 85 | 0.20% | −0.07 – 0.46% | 0.77% | 0.51 – 1.03% | +0.57 | no |

**Three of five ages are unresolvable.** Of the two that are not, age 45's +2.82%
sits exactly where the residual boundary artefact is largest (§4) and should not be
read as experience. That leaves age 85's +0.57% as the only defensible non-null,
and it is modest.

**The structural reason is the observation window, and it is decisive.** ILEC
2012–2019 is eight years, split by the harness into 2012–2015 vs 2016–2019 — four
years each. The documented US slowdown breaks at **~2010**, so this window lies
*entirely on one side of it*. "Did improvement slow within 2012–2019" is a
different question from "did improvement slow after 2010," and a null answer to the
first says nothing about the model. HMD resolved the slowdown because it spans 30
years straddling the break (`MEASUREMENT_experience_gam_hmd.md`).

Recording a null here is the point of naming success criteria in advance. Nothing
was re-parameterised to manufacture a signal.

## 3. Insured-versus-population divergence — the finding PLAN §2 actually wanted

PLAN §2: *"ILEC should not look identical to HMD — a model that shows them
identical has a bug; the interesting output is the shape of the difference."*

| Age | HMD population, 2010s | ILEC insured, 2016–19 |
|---:|---:|---:|
| 55 | 0.32% | **1.33%** |
| 65 | 0.25% | **0.40%** |
| 85 | **1.27%** | 0.77% |

Insured lives at 55 improved roughly **four times faster** than the US population
over comparable years; at 85 they improved *slower*. The direction is not arbitrary
and it is not a bug: the US midlife mortality stagnation is concentrated in
populations that underwriting screens out, so an insured book largely does not
participate in it. At the oldest ages selection has worn off and the population
gains — driven by causes that affect everyone — dominate.

Two cautions. The windows are not the same (HMD 2010–2019 against ILEC 2016–2019),
so this is a comparison of overlapping regimes rather than identical ones. And age
45 is excluded from the table because of §4.

## 4. What is still wrong, stated plainly

**A residual boundary artefact at younger ages.** The first ILEC run used
`year_df=4` over eight years and produced a terminal-year spike at every reference
age. Dropping to `year_df=3` — the cubic-B-spline floor, so the least flexible year
margin available — cut the mean absolute difference against SOA from **0.92% to
0.368%**, a 2.5× reduction, while the weighted mean barely moved (−0.040% →
−0.041%). That is the exact signature of over-flexibility: unbiased before and
after, far less noisy after.

It did not vanish. Fitted MI at age 45 still ramps −0.35% (2013) → **3.83%** (2019),
and age 55 → 2.05%. Ages 65/75/85 are now well-behaved (terminal values 0.56%,
0.87%, 1.48%). So the artefact is concentrated where insured exposure is thinnest
and the age×year tensor is least constrained.

**`year_df=3` cannot be lowered further.** The floor is structural. If a plain
cubic is still too flexible for the window, the window is too short to fit a
surface on — which is the honest characterisation of the 45–55 estimates here.

## 5. Fit diagnostics

| | |
|---|---|
| raw file | 12,477,136,749 bytes, tab-delimited |
| cells loaded (post-filter) | 11,059,501 |
| cells after aggregation | 15,882 |
| cells fitted | 15,880 |
| aggregation level | `attained_age, calendar_year, sex, smoker, uw_class` |
| dropped keys | `issue_age, duration_months, band, product` |
| `uw_class == "U"` held out | 277,173 cells |
| zero-exposure cells dropped | 2, holding 0.0 deaths |
| total exposure | 420,404,127 policy-years |
| total deaths | 4,354,590 |
| factors | `sex`, `smoker`, `uw_class` |
| dispersion φ | 2.25 — quasi-Poisson scaling applied, bands ×1.50 |
| `overall_ae` | 1.000 **by construction** — the real level check is §1 |

**Insured data is far closer to Poisson than population data** (φ = 2.25 against
HMD's 21.84), which is what one would expect: an insured cell is a much more
homogeneous group than a national population cell.

**The `uw_class` disambiguation was material, not theoretical.** 11,059,501 loaded
cells against the 9,714,592 measured before ADR-181's composition fix: ~1.35M cells
were being pooled by `Preferred_Class` alone, merging class-2-of-2 (worst) with
class-2-of-4 (second-best).

## 6. Honest limitations

- **Pooled across duration.** Select-period mortality is absorbed into the
  attained-age effect. If the duration mix drifts with calendar year, part of that
  drift lands in the fitted improvement. Unmeasured here; re-running with
  `duration_months` in `--group-by` at ~60× the cell count would bound it, and is
  the single most valuable follow-up on this path.
- **Eight years is short** for a decade-scale trend question (§2).
- **Band overlap is not a significance test for the difference** — the two window
  contrasts share fitted coefficients.
- **A/E covers the full loaded book; the fit covers the fitted cells.** They differ
  by the two zero-exposure cells only, which is immaterial here.
- **The A/E *level* of 1.079 is not interpreted.** Actual deaths run ~8% above VBT
  2015 expected on this book, which is a basis/mix question this slice does not
  attempt to decompose. Only the *drift* is claimed.

## 7. Verdict against slice 3's acceptance criteria

| Criterion | Outcome |
|---|---|
| Insured surface fitted and compared to the population surface | ✅ §3 |
| Divergence characterised | ✅ Insured improve faster at midlife, slower at 85 |
| Column-map override committed if needed | ✅ `ILEC_2012_19_COLUMN_MAP` shipped in ADR-181; no further override needed |
| No data files added | ✅ Findings only; the 12.5 GB file never left the maintainer's machine |

**Additional outcome not in the original criteria:** the strongest result on this
path turned out to be the A/E agreement with SOA's published expected deaths (§1),
not the slowdown test. That check was added mid-epic on maintainer direction
(2026-08-04) and is the reason this slice has a positive finding at all.
