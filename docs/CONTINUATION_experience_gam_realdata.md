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
- **Status:** NEXT
- **Depends on:** nothing
- **Scope:** `scripts/experience_diligence.py` — load (HMD or ILEC from a local
  cache) → fit the tensor MI surface → emit a structured findings report (JSON +
  Markdown table): fit diagnostics, improvement-rate surface at reference ages,
  and the decade-over-decade comparison the slowdown test needs.
- **Tests:** end-to-end on the **existing synthetic fixtures**, so the harness is
  proven before it meets real data; a missing/empty cache must produce an
  actionable message pointing at the acquisition runbook, not a stack trace.
- **Acceptance criteria:**
  - Runs green on synthetic fixtures in CI; `--source hmd|ilec` contract documented.
  - **No plots** — numbers and tables commit and diff, images do not.
  - `tests/qa/` goldens untouched (nothing in `products/` moves).

### Slice 2: HMD findings (maintainer runs; session records)
- **Status:** BLOCKED on maintainer data acquisition + slice 1 merged
- **Scope:** maintainer runs slice 1's harness against HMD (USA 1990–2019
  primary; GBRTENW secondary) and returns the report; the session commits
  `docs/MEASUREMENT_experience_gam_hmd.md`.
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
  `default_experience_cache_dir`. Slice 1 consumes them; it should not need to
  modify them.

## Open Questions (for human)

- **Which HMD countries.** The plan proposes USA 1990–2019 primary, GBRTENW
  secondary. Ends at 2019 deliberately: a tensor surface fitted through the COVID
  shock will attribute it to smooth improvement, which is wrong and would
  discredit the output. Pull 2020–2022 as a separate window if wanted.
- **ILEC vintage.** The 2009–2018 release is the common one; header spellings
  differ between vintages, so the maintainer's header diff (runbook §2b) decides
  whether a column-map override is needed.
- **`mgcv` oracle (ADR-151), still unexecuted.** Needs an R-equipped machine and
  is the maintainer's to run. Real-data fitting is exactly when an independent
  cross-check earns its keep — worth running alongside slice 2 if convenient, but
  formally out of scope.
