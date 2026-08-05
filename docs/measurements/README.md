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
| `experience_gam_hmd_usa.{json,md}` | `scripts/experience_diligence.py --source hmd --country USA --min-year 1990 --max-year 2019` |
| `experience_gam_ilec.{json,md}` | `scripts/experience_diligence.py --source ilec --year-df 3` |

Read them alongside `docs/MEASUREMENT_experience_gam_hmd.md` and
`docs/MEASUREMENT_experience_gam_ilec.md`, which say what the numbers mean and
where they should not be trusted.

## Why committing these is not a licence problem

**Findings, not data** — Design Anchor 6, and the HMD and SOA-ILEC terms.

These reports carry aggregate summary statistics: A/E by calendar year (8 rows),
an improvement surface at five reference ages, fit diagnostics, and cell counts.
They carry input file **basenames and byte sizes**, never paths, never cells, and
never a row of source data. That is the same class of aggregate SOA publishes in
its own ILEC reports.

**What must never be committed**, and never has been:

- the HMD `Deaths_1x1.txt` / `Exposures_1x1.txt` files;
- the ILEC flat file, at any resolution;
- **the grouped cell table** — 15,882 rows keyed by
  `(attained_age, calendar_year, sex, smoker, uw_class)` with exposure and deaths
  is not a finding, it is the dataset at a coarser grain, and it would let someone
  reproduce most analyses without accepting the terms the original was released
  under. Row count is not the test; substitutability is.

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
