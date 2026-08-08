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
| `experience_gam_ilec_duration_banded_quadratic.{json,md}` | `--source ilec --year-df 2 --year-degree 2 --duration-bands` |

The three ILEC runs are all kept **on purpose**; each pair's difference is itself a
finding. Pooled versus banded shows duration mix confounding the trend (ADR-182
amendment 4). Banded-cubic versus banded-quadratic shows that age 45's climb is
**invariant** to the calendar margin's flexibility, which retracted the stated
reason for distrusting it (ADR-184 amendment 2). The quadratic is the
better-specified fit — closer to SOA's own scale on both metrics, at equal
dispersion and one fewer parameter.

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

That is the conduct. Whether it is *sufficient* under the two sets of terms is a
separate question, and the answers are not symmetric:

- **SOA** — read 2026-08-07, and **restrictive**. No dataset-specific licence
  exists; the site-wide Terms of Use permit only "personal or other
  non-commercial, educational purposes", prohibit public **or** commercial
  reproduction and distribution, bar derivative works, and offer **prior written
  permission** as the route to anything else. That permission has been drafted and
  not yet sought a reply. Publishing findings in a public repository engages the
  *public* hook today — this is not a risk that begins if the project ever
  commercialises. `../DATA_LICENSING.md` §3 quotes the clauses and §5 records the
  maintainer's position and what would change it.
- **HMD** — **still unread.** The SOA answer does not transfer.

If a derived artefact is ever wanted for distribution, the right one is a **model
output** — a fitted `MortalityImprovement` scale via
`MISurface.to_mortality_improvement()`. That is our model, not a redistribution of
somebody's data.

## Reproducing them

The reports carry no timestamps and no paths, and floats are rounded to 12
significant digits so multithreaded-BLAS jitter in the delta-method band cannot
produce a spurious diff (see `REPORT_SIGNIFICANT_DIGITS`).

**They are not byte-for-byte reproducible, and the earlier claim that they were is
withdrawn.** Rounding cannot be tie-free: every cutoff has values sitting within
1 ulp of it, and a parallel sum reassociated across runs flips which way those
round. Observed 2026-08-08 on a control re-run — `dropped_exposure_share` moved
`9.17073903863e-05` → `...64e-05` while every fitted quantity was bit-identical.

What holds is the useful part: **the estimator is deterministic**, so the surface,
the bands, the dispersion and the verdict reproduce exactly. Aggregation ratios
over ~10^5 cells can move in their last reported digit. Compare a re-run with a
numeric diff, not `cmp`.

Acquisition and the exact commands are in
`docs/RUNBOOK_experience_data_acquisition.md` §3.
