# Continuation: real-data diligence for the experience GAM (HMD + SOA-ILEC)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Real-data diligence run for the
experience GAM", **IMPORTANT** (reclassified from ADR-150 NICE-TO-HAVE on
2026-08-03 maintainer direction)
**Plan:** `docs/PLAN_experience_gam_realdata.md`
**Data runbook:** `docs/RUNBOOK_experience_data_acquisition.md`
**Status:** IN PROGRESS
**Total slices:** 3 (slices 2–3 depend on maintainer-run data acquisition)
**Estimated total scope:** ~4–6 dev-days of autonomous work + 2 maintainer runs

## Overall Goal

Fit the tensor mortality-improvement GAM against **real** experience — HMD
population and SOA-ILEC insured — and publish whether it reproduces structure
with an independent published record. The A4′ epic built the machinery and
validated it exclusively on synthetic data with an injected known surface, which
proves the implementation recovers a surface it was handed but says nothing about
real experience. CLAUDE.md §1 makes ML-native assumption-setting the product
thesis; this is what discharges it.

## Slices

### Slice 1: The diligence harness (autonomous — no data required)
- **Status:** DONE (2026-08-04) — `src/polaris_re/analytics/experience_diligence.py`
  + `scripts/experience_diligence.py`, **ADR-182**, runbook §3. 65 tests. PR #185.
- **Depends on:** nothing
- **Scope:** `scripts/experience_diligence.py` — load (HMD or ILEC from a local
  cache) → fit the tensor MI surface → emit a structured findings report (JSON +
  Markdown table): fit diagnostics, improvement-rate surface at reference ages,
  and the decade-over-decade comparison the slowdown test needs.
- **Tests:** end-to-end on the **existing synthetic fixtures**, so the harness is
  proven before it meets real data; a missing/empty cache must produce an
  actionable message pointing at the acquisition runbook, not a stack trace.
- **A/E against SOA's published expected deaths** (maintainer-approved
  2026-08-04). On the ILEC path the report must include A/E by calendar year
  against `expected_deaths_vbt2015_mi`, loaded via
  `load_ilec(include_expected=True)`. This is the numeric check that replaces
  eyeballing a surface against the MIM-2021 narrative — see PLAN §2.
- **An explicit aggregation level.** The real file is **9,714,592 cells** at full
  canonical-key resolution; the MI surface needs ~10³. The harness takes the
  grouping level as a parameter and states it in the report. Conservative default:
  do **not** silently collapse across `smoker` or `uw_class`, which pool
  genuinely different populations.
- **`uw_class` handling, settled by the 2026-08-04 distribution:** pool `"NA"` as
  its own stratum (it is *not applicable*, not missing), and hold `"U"` out of any
  class-conditioned inference (it is unknown). Numbered classes arrive already
  composed with their structure size (`"1of2"` vs `"1of4"`) so the harness does
  not need to re-derive it.
- **Acceptance criteria:**
  - Runs green on synthetic fixtures in CI; `--source hmd|ilec` contract documented.
  - **No plots** — numbers and tables commit and diff, images do not.
  - `tests/qa/` goldens untouched (nothing in `products/` moves).
- **How it came out.** All acceptance criteria met. Four things are worth carrying
  into slice 2 because they change how the output should be read:
  - The slowdown test is proven **two-sided**: the suite injects a slowdown and
    requires the verdict `slowdown`, then injects an acceleration and requires
    `acceleration`. A harness that said "slowdown" either way would confirm PLAN §2
    by construction.
  - The early/late bands are **exact** window contrasts (the two-year grid's single
    step telescopes to `η(end) − η(start)`), but their *overlap* is **not** a
    significance test for the difference — the two contrasts share coefficients.
    The report says so in three places; do not upgrade that language when writing
    the findings.
  - `q_base` is the pooled crude rate from the data itself, so `overall_ae` is ~1
    **by construction** and is not a check on the level. The fitted improvement is
    unaffected (verified: halving `q_base` leaves the surface identical to 1e-10).
    On ILEC the level check is SOA's own expected deaths.
  - The ILEC default pools across **duration**. A duration mix drifting with
    calendar year leaks into the trend; every report states it. If slice 3's
    numbers look surprising, re-run with `--group-by ... duration_months` before
    believing them.

### Slice 2: HMD findings (maintainer runs; session records)
- **Status:** NEXT — unblocked by slice 1; needs the maintainer's data + run
- **Scope:** maintainer runs slice 1's harness against HMD (USA 1990–2019
  primary; GBRTENW secondary) and returns the report; the session commits
  `docs/MEASUREMENT_experience_gam_hmd.md`. The exact commands are in
  `RUNBOOK_experience_data_acquisition.md` §3; the `--markdown` output is already
  scrubbed for committing (basenames only, no cells, no plots).
- **Acceptance:** the **post-2010 US improvement-slowdown question answered
  either way**, compared against the published reference (SOA MIM-2021 / CMI
  literature); cross-population agreement characterised; no data files added.

### Slice 3: ILEC insured validation (maintainer runs; session records)
- **Status:** PLANNED
- **Depends on:** Slice 2
- **Scope:** same shape against insured experience. The interesting output is
  insured-vs-population **divergence**, not agreement — insured lives are
  underwritten and selection is real, so a model showing them identical has a bug.
  Likely also yields a per-vintage `ILEC_COLUMN_MAP` override (autonomous work
  once the maintainer's header diff comes back).

## Context for Next Session

- **Read `PLAN_experience_gam_realdata.md` §2 before writing any code.** The epic
  names in advance what the fit could *fail* to reproduce. A slice reporting "the
  surface did not show the slowdown" is a **successful** slice — recording that is
  worth more than a plausible-looking output. Do not tune until it agrees.
- **The autonomous/maintainer split is structural, not a phase.** HMD needs a
  personal account, ILEC needs SOA terms acceptance, neither may be committed
  (Design Anchor 6 + licences), and sessions run in ephemeral containers that
  could not retain the data anyway. Slice 1 is scoped to be complete and mergeable
  with **no data present**. Any plan that assumes a session can fetch and keep the
  data is planning something that cannot happen.
- The proven pattern to copy is `scripts/bench_portfolio_parallel.py` (2026-08-03):
  the routine wrote the harness, the maintainer ran it, the *findings* were
  committed and the raw data was not. That round-trip worked cleanly twice in one
  session.
- The loaders already exist and are unit-tested — `experience_loaders.py`:
  `load_hmd`, `parse_hmd_1x1`, `load_ilec`, `fetch_hmd`, `ILEC_COLUMN_MAP`,
  `default_experience_cache_dir`. Slice 1 consumed them without modifying them,
  as intended.
- **Slice 2 is a recording job, not a coding one.** The harness exists; what is
  missing is the maintainer's run. The session's work is to read the returned
  report honestly against the published reference (SOA MIM-2021 / CMI) and write
  `MEASUREMENT_experience_gam_hmd.md` — including any way the fit disappoints.
  Resist the urge to add harness features while waiting; the epic's value is in
  the finding, and a slice reporting "no slowdown" is a successful slice.

## Open Questions (for human)

- **Which HMD countries.** The plan proposes USA 1990–2019 primary, GBRTENW
  secondary. Ends at 2019 deliberately: a tensor surface fitted through the COVID
  shock will attribute it to smooth improvement, which is wrong and would
  discredit the output. Pull 2020–2022 as a separate window if wanted.
- ~~**ILEC vintage.**~~ **RESOLVED 2026-08-04:** the maintainer pulled the
  **2012-2019** release (`ILEC_2012_19 - 20240429.txt`, ~12 GB, 30 columns,
  tab-delimited). `ILEC_2012_19_COLUMN_MAP` ships for it. Verified load:
  9,714,592 cells, 2012–2019, 4,552,009 deaths over 464,513,252 policy-years
  (9.8 per 1,000 crude — as expected for insured business skewed to older
  permanent).
- ~~**`uw_class = "NA"` — pool or drop?**~~ **RESOLVED 2026-08-04**, empirically,
  from the maintainer's own file rather than the data dictionary:

  | Preferred_Class | Indicator | N classes | rows |
  |---|---|---|---|
  | `NA` | 0 | `NA` | 14,615,884 |
  | numbered 1–4 | 1 | 2 / 3 / 4 | ~26.9M |
  | `U` | `U` | `U` | 798,461 |

  **`NA` means *not applicable*** — perfectly aligned with `Preferred_Indicator = 0`
  and no class count, i.e. the policy has no preferred-class structure. A
  legitimate stratum, and the largest single group. **Pool it.**
  **`U` is the missing-data category**, distinct in all three columns and ~2% of
  rows — exclude it from any inference that conditions on underwriting class,
  rather than pooling it with underwritten business.

  **The query also exposed a defect this epic introduced.** `Preferred_Class`
  alone is **not a valid stratification key**: class "2" of a 2-class structure is
  the *worst* class while class "2" of a 4-class structure is *second-best*, and
  the mapping conflated them. `load_ilec` now composes `uw_class` with the class
  count (`"2of2"`, `"2of4"`), leaving the `NA`/`U` sentinels uncomposed.
  Backwards compatible: composition happens only where the column map supplies a
  count, so vintages loaded through the default map are unaffected.
- **`mgcv` oracle (ADR-151), still unexecuted.** Needs an R-equipped machine and
  is the maintainer's to run. Real-data fitting is exactly when an independent
  cross-check earns its keep — worth running alongside slice 2 if convenient, but
  formally out of scope.
