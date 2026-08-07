# `docs/measurements/` — raw harness output

Files here are **generated verbatim and never hand-edited.** A re-run overwrites
them and the diff is the finding.

That is why they are separate from the `docs/MEASUREMENT_*.md` documents one level
up: those are *written readings* with interpretation, caveats and a verdict in
them. Keeping the two apart means re-running a harness produces a clean,
mechanical diff without disturbing prose that a human wrote.

## What is in here

| File | Produced by |
|---|---|
| `experience_gam_hmd_usa.{json,md}` | `--source hmd --country USA --min-year 1990 --max-year 2019` |
| `experience_gam_hmd_gbrtenw.{json,md}` | `--source hmd --country GBRTENW --min-year 1990 --max-year 2019` |
| `experience_gam_ilec.{json,md}` | `--source ilec --year-df 3` |
| `experience_gam_ilec_duration_banded.{json,md}` | `--source ilec --year-df 3 --duration-bands` |

The two ILEC runs are both kept **on purpose**: the difference between them is
itself a finding (duration mix was confounding the trend — ADR-182 amendment 4).
The banded one is the better-specified fit; the pooled one is the control that
shows how much the confound was worth.

Read them alongside `docs/MEASUREMENT_experience_gam_hmd.md` and
`docs/MEASUREMENT_experience_gam_ilec.md`, which say what the numbers mean and
where they should not be trusted.

## Attribution

The experience behind every number in this directory is somebody else's, obtained
by the maintainer under their own account and terms acceptance, and it is credited
here.

> **HMD.** Human Mortality Database. Max Planck Institute for Demographic Research
> (Germany), University of California, Berkeley (USA), and French Institute for
> Demographic Studies (France). Available at <https://www.mortality.org>.
> Series used: `Deaths_1x1.txt` / `Exposures_1x1.txt` for USA and GBRTENW,
> 1990–2019, ages 25–95, both sexes.

> **Society of Actuaries Research Institute**, Individual Life Experience
> Committee (ILEC). Individual life insurance mortality experience study, study
> years 2012–2019; dataset file `ILEC_2012_19 - 20240429.txt`. Available at
> <https://www.soa.org>. SOA's own `ExpDth_VBT2015*` expected deaths — on SOA's
> 2015 VBT basis — are what make the A/E level check independent rather than an
> identity.

Neither body has reviewed, approved or endorsed this analysis. The modelling
choices and any errors are ours.

Full provenance, the verified inventory of what these files do and do not contain,
and the **open** question of what the licences actually say are in
[`../DATA_LICENSING.md`](../DATA_LICENSING.md).

## What is committed here, and what never is

**Findings, not data** — Design Anchor 6.

These reports carry aggregate summary statistics: a fitted improvement surface at
five reference ages, fit diagnostics, and book-level totals. The two ILEC reports
additionally carry **A/E by calendar year — 8 rows, with absolute actual and
expected death counts** — which is the most data-derived thing committed anywhere
here and is called out as such rather than folded into "aggregates". They carry
input file **basenames and byte sizes**, never paths, never cells, and never a row
of source data. `../DATA_LICENSING.md` §1 is the exhaustive inventory.

**What must never be committed**, and never has been:

- the HMD `Deaths_1x1.txt` / `Exposures_1x1.txt` files;
- the ILEC flat file, at any resolution;
- **the grouped cell table** — 126,223 rows keyed by
  `(attained_age, calendar_year, sex, smoker, uw_class, duration_months)` with
  exposure and deaths is not a finding, it is the dataset at a coarser grain, and
  it would let someone reproduce most analyses without obtaining the original.
  Row count is not the test; substitutability is.

That is the conduct. Whether it is *sufficient* under the HMD and SOA terms is a
separate question, and one nobody on this project has yet checked against the
terms themselves — see `../DATA_LICENSING.md` §4, which says so plainly rather
than asserting a conclusion this repository has not earned.

If a derived artefact is ever wanted for distribution, the right one is a **model
output** — a fitted `MortalityImprovement` scale via
`MISurface.to_mortality_improvement()`. That is our model, not a redistribution of
somebody's data.

## Reproducing them

The reports are deterministic: no timestamps, and floats rounded to 12 significant
digits so multithreaded-BLAS jitter in the delta-method band cannot produce a
spurious diff (see `REPORT_SIGNIFICANT_DIGITS`). Given the same cache and the same
arguments, a re-run reproduces these files byte for byte.

Acquisition and the exact commands are in
`docs/RUNBOOK_experience_data_acquisition.md` §3.
