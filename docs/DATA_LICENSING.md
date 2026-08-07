# Data provenance, attribution and licensing

**Covers:** the two external experience datasets this repository has been run
against — the **Human Mortality Database (HMD)** and the **SOA Individual Life
Experience Committee (ILEC)** 2012–2019 release — and the findings committed
under `docs/measurements/`.

**Status, 2026-08-07:**

| | |
|---|---|
| Attribution | **Added** (§2), and pinned by `tests/test_docs/test_data_attribution.py` |
| Inventory of what is actually committed | **Verified by inspection** (§1) |
| The licence terms themselves | **NOT read.** See §4 — this is an open item, not a settled one |

§4 exists because the honest answer to "are we inside the terms?" is currently
*"we have not read them"*. Everything this repository has said about HMD and SOA
licensing to date is second-hand — reasonable-sounding paraphrase with nothing
behind it. §3 quotes that language and says so.

---

## 1. What is actually committed — the verified inventory

This is not a summary; it is the result of reading every committed report. There
are four, all under `docs/measurements/`, all generated verbatim by
`scripts/experience_diligence.py`.

### 1a. Derived from the licensed data (real figures, not model output)

**Both HMD reports** (`experience_gam_hmd_usa`, `experience_gam_hmd_gbrtenw`) carry
**totals only**:

| Field | USA | GBRTENW |
|---|---:|---:|
| cells loaded / grouped / fitted | 4,260 | 4,260 |
| total exposure (person-years) | 5,750,237,304 | 1,117,115,546 |
| total deaths | 68,998,510 | 15,153,718 |
| base strata (`attained_age, sex`) | 142, none dropped | 142 |

No rate is published per stratum — the `base` block records *counts and
diagnostics* about the empirical base, never the base rates themselves. There is
no age–year table of deaths or exposures anywhere in these files.

**Both ILEC reports** carry the same class of totals (exposure 420,365,573
policy-years, 4,354,590 deaths, 11,059,501 cells loaded → 126,223 grouped) **plus
three aggregate tables that are genuinely data-derived**:

- `ae_by_year.rows` — **8 rows**, one per calendar year, each carrying *absolute*
  actual and expected death counts (e.g. 2012: actual 518,386, expected
  474,583.8, expected-with-MI 482,055.8) and the two ratios.
- `standardised_ae.rows` — **8 rows**, ratios and mix effects only, no counts.
- `soa_surface_comparison.rows` — **35 rows**; the `soa_mi` column is SOA's *own*
  implied improvement rate at each (age, year), recovered from SOA's published
  `ExpDth_VBT2015_Cnt` / `..._MI` columns. This is a derived reading of an SOA
  quantity, not of ours.

### 1b. Model output (ours, not theirs)

`improvement_surface` (145 rows on HMD, 35 on ILEC), `window_comparison` (5 rows),
the standardisation slopes, and the fit diagnostics (dispersion φ, degrees of
freedom, band inflation).

### 1c. Not present, in any report

Cell-level rows. Policy-level anything. Rates by stratum. Contributor identities.
Filesystem paths — the `inputs` block carries **basenames and byte sizes only**
(`ILEC_2012_19 - 20240429.txt`, 12,477,136,749 bytes), which is asserted by
`tests/test_notebooks/test_experience_gam_diligence_notebook.py`.

### 1d. The line that has never been crossed

The **grouped cell table** — 126,223 rows keyed by
`(attained_age, calendar_year, sex, smoker, uw_class, duration_months)` with
exposure and deaths — has never been committed and must not be. It is not a
finding; it is the dataset at a coarser grain, and it would let someone reproduce
most of this work without obtaining the original. **Row count is not the test;
substitutability is.**

---

## 2. Attribution

These are the canonical blocks. `docs/measurements/README.md` and both
`docs/MEASUREMENT_experience_gam_*.md` carry them; a guard test fails if they are
dropped.

### 2a. Human Mortality Database

> **HMD.** Human Mortality Database. Max Planck Institute for Demographic Research
> (Germany), University of California, Berkeley (USA), and French Institute for
> Demographic Studies (France). Available at <https://www.mortality.org>.

**Series used:** `Deaths_1x1.txt` and `Exposures_1x1.txt` for **USA** and
**GBRTENW** (England & Wales, total population), calendar years 1990–2019, ages
25–95, both sexes. Downloaded by the maintainer in **August 2026** under their own
HMD account.

### 2b. SOA Individual Life Experience Committee

> **Society of Actuaries Research Institute**, Individual Life Experience Committee
> (ILEC). Individual life insurance mortality experience study covering study
> years **2012–2019**; dataset file `ILEC_2012_19 - 20240429.txt`. Available at
> <https://www.soa.org>.

**Also SOA's, and used as such:** the `ExpDth_VBT2015_Cnt` and
`ExpDth_VBT2015_MI_Cnt` columns — SOA's own expected deaths on the **2015 VBT**
basis, which are what make the A/E level check in
`MEASUREMENT_experience_gam_ilec.md` §1 an *independent* check rather than an
identity. The 2015 VBT is likewise an SOA product. Obtained by the maintainer in
**August 2026** through SOA's own download, accepting the terms presented there.

### 2c. Disclaimer

Neither the HMD nor the Society of Actuaries has reviewed, approved, endorsed or
been consulted about this analysis. Every modelling choice — the tensor basis, the
degrees of freedom, the duration banding, the overdispersion handling — is ours,
as is every error. Where a finding disagrees with a published SOA scale (see the
ILEC measurement §1b), that is a statement about **our fit**, not a correction to
SOA.

---

## 3. What this repository asserted before anyone read the terms

Recorded verbatim, because the fix is not to delete it quietly.

| Where | What it said |
|---|---|
| `RUNBOOK_experience_data_acquisition.md` §0 | "it is also what keeps you inside both licences" |
| `RUNBOOK...` §1a | "HMD is open-data-principled but attribution-bearing — redistribution of the raw files is not ours to do" |
| `RUNBOOK...` §2 | "Accept the SOA terms of use" |
| `RUNBOOK...` §6 | "committing it is forbidden by the licences and by Design Anchor 6" |
| `docs/measurements/README.md` | a section headed "Why committing these is not a licence problem" |

**Not one of these cites a licence.** No section number, no quotation, no URL to a
terms document appears anywhere in the repository. The claims may well be right —
they are the conventional reading, and §1 shows the committed artefacts are
conservative by any standard — but "conventional reading" is not the same as
"checked", and the difference is exactly the kind of thing this project is
otherwise careful about. The measurements README heading has been reworded
accordingly (it now states the conduct, not a legal conclusion).

---

## 4. What has not been verified, and why

### 4a. The blocker

An attempt was made in-session, 2026-08-07, to read the primary sources:

- `https://www.mortality.org/Data/UserAgreement`
- `https://www.soa.org/legal/terms-of-use/`
- the SOA ILEC 2012–2019 release page

All returned **HTTP 403 at the network gateway, before reaching the host**. This
container's egress policy is a narrow allowlist (GitHub and package registries);
`www.mortality.org` and `www.soa.org` are both denied, as are archive and
text-extraction mirrors. The denial is recorded in the proxy's own
`recentRelayFailures` for both hosts.

Search-engine summaries were available and are *not* being used as a substitute.
Replacing one layer of paraphrase with a different layer of paraphrase would
reproduce the defect §3 describes rather than fix it. In particular, the commonly
repeated claim that HMD data are released under **CC BY 4.0** is plausible and
widely echoed, but it is not quoted here as fact because nobody in this project
has yet read it on mortality.org.

### 4b. The three questions to answer

For whoever reads the terms — a browser and about fifteen minutes:

1. **Do the terms restrict redistribution of *derived aggregates*, or only of the
   dataset?** This is the one that decides whether §1a's ILEC tables — the 8-row
   A/E series with absolute death counts, in particular — are fine as committed.
   The HMD side of this is the lighter question; the SOA side is the real one.
2. **Is there a prescribed attribution wording, and does §2 meet it?** §2 gives a
   full scholarly citation, which satisfies an attribution requirement in
   substance, but if either body specifies exact wording it should be adopted
   verbatim.
3. **Is there a non-commercial or research-only condition?** This repository is
   public and openly product-adjacent — CLAUDE.md §1 describes a commercial
   alternative to AXIS/Prophet. A research-use-only condition would not affect the
   maintainer's private analysis, but it would bear on committing findings derived
   from the data into a repository with that stated purpose.

### 4c. If an answer comes back unfavourable

The remedy is already available and cheap. The committed reports are
regenerable, and the offending content would be narrow: on the SOA side it is
`ae_by_year.rows` (absolute counts) and `soa_surface_comparison.rows` (SOA's
implied scale). Both could be reduced to ratios and differences — losing the
absolute counts, keeping every finding in `MEASUREMENT_experience_gam_ilec.md`
except the raw scale of the book. Nothing in the analysis depends on publishing
518,386 as a number.

The stronger long-term answer, unchanged from the measurements README: if a
derived artefact is ever wanted for distribution, the right one is a **model
output** — a fitted `MortalityImprovement` scale via
`MISurface.to_mortality_improvement()`. That is our model, not anybody's data.
