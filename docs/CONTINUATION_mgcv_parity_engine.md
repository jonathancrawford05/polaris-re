# Continuation: a Python GAM engine at parity with `mgcv`

**Source:** maintainer direction 2026-08-10 (the target model form, supplied as R).
**Plan:** `docs/PLAN_mgcv_parity_engine.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` — a convergence loop, not a backlog walk.
**Predecessors:** ADR-189 + amendment 1 (the conformance suite and its first run),
ADR-185 through ADR-188 (the penalized fitter this epic reuses).
**Status:** **IN PROGRESS** — slice 1 is NEXT; nothing is built yet.
**Total slices:** **7** autonomous, plus one deferred to a later epic.
**Estimated scope:** the largest numerical undertaking in the project.

> **This is the ACTIVE epic.** `CONTINUATION_penalized_mi_surface.md` is superseded from
> its slice 6 onward and all of its remaining slices are PARKED. A routine run selecting
> work should land here.

## Overall goal

Fit the maintainer's selected model form — 110 coefficients, 8 smooth terms, 13-21
smoothing parameters, binomial/`cloglog` on a proportion response with prior weights and
hand-chosen non-uniform knots — in Python, verified term by term against `mgcv`. The
existing penalized IRLS core carries over and is already verified to 5e-13; **the basis
layer is a rebuild.** PLAN §1 has the target verbatim and the measurements that size it.

## Slices

1. **The Stage-A harness, and a term spec to hang it on** — **NEXT.**
   R-side per-term extractor (design block, every `S_j`, index range, rank, knots used) plus
   the Python comparator and the term-spec dataclasses of PLAN Anchor 3.
   **Prove the harness on the existing verified basis before any new basis exists**, so a
   later Stage-A disagreement is attributable to the new basis rather than to the harness.
   **One thing it must decide in writing:** `predict(type="lpmatrix")` is
   post-reparameterisation, `smoothCon()` is pre- — which one Stage A compares against
   changes what "our `X` equals `mgcv`'s `X`" means. PLAN §5.1 carries the fallback if
   neither works, and records that the fallback is weaker.
2. **`bs = "cr"`**, with supplied and default knots. PLANNED.
3. **Families, links and weights** — binomial `cloglog`/`logit` on a proportion with prior
   weights, quasi-Poisson with `φ` estimated, Poisson with a log offset. Independent of 2.
   PLANNED.
4. **The outer optimisation — N-dimensional (f)REML.** The prerequisite for everything
   multi-term, and the largest single piece of work. PLANNED.
5. **`ti()` and the varying-coefficient MI term.** Ship the MI term first if they split.
   PLANNED.
6. **`bs = "sz"`** — orthogonal factor-smooth interactions. Expect the hardest basis.
   PLANNED.
7. **`select = TRUE`** — the double penalty; 13 → 21 smoothing parameters. PLANNED.

Deferred to a later epic: `bam` + `discrete = TRUE` + fREML. Safe to defer because at
fixed `sp` on a `paraPen`-only model `bam` agrees with `gam` to **2.1e-12**, and because
`bam` at 125,000 rows takes **1.69 s** — performance is not the reason to want it.

## Context for the next session

- **Read PLAN Anchors 1 and 2 before writing code.** They change what you build, not just
  how you check it: construction is verified before fit, and the fitted surface is the
  acceptance criterion while coefficients are not.
- **Local R is a SCRATCH oracle, not a cheap version of the real one.** `apt-get install -y
  r-base-core r-cran-mgcv r-cran-jsonlite`, ~3.5 min, then 2.2 s per run — but it is **mgcv
  1.9.1 against reference `libblas`**, where the image is **mgcv 1.9.4 against OpenBLAS**.
  Different release, different BLAS: local output *cannot* match the image at Stage-A
  precision (~1e-15) however correct the code is, so a local-vs-image difference at that
  scale is evidence of nothing. **Iterate locally, verify on CI** — a `workflow_dispatch`
  round trip on the pinned digest costs about a minute (measured: run 31892118379, 59 s).
  `ROUTINE_MGCV_PARITY.md` step 2 has the three tiers and which one a number may be
  committed from. Running the image locally is *not* an option here: `docker` is installed
  but there is no daemon.
- **The oracle image is `sha256:0d54c192…`** — upstream **build 8**, the first with
  host-independent numerics. Builds 1-7 let OpenBLAS size its thread pool from the host, so
  the last bits depended on which runner drew the job. We adopted build 8 for **slice 1**,
  not for `mboost`: Anchor 1 compares design matrices at ~3.5e-15, the same order as that
  nondeterminism, so on an older build a Stage-A disagreement could have been the runner.
  Re-measured, not assumed — run 31892118379: levels 1-3 agree, 4-5 unchanged findings.
  ADR-189 amendment 2.
- **ADR-189 amendment 1's numbers belong to build 1 (`sha256:a77a61cf…`)**, and amendment 2
  deliberately does not restate them as build-8 numbers — the verdicts were reproduced, the
  per-metric digits were not read. **Never quote a conformance number without the digest
  that produced it.** This file has pinned three builds; `mgcv_version` does not distinguish
  them, because all three carry mgcv 1.9.4.
- **Upstream tagging is fixed (R-Gam-base PR #3):** immutable never-reused tags
  `r<R>-cran<snapshot>-b<NN>`, a digest-keyed `BUILDS.md` catalog, CI refusal to push an
  existing tag, and `/opt/oracle-manifest.json` from build 3 forward (builds 1-2 carry
  `/opt/versions.json`, and record no `MASS` version). `r4.6.1-2026-08-01` is **deprecated,
  not deleted** — GHCR deletes versions rather than tags, and that tag sits on the digest we
  pin. The `-b1`/`-b2` tags are staged in an upstream retag workflow and **were not yet
  applied** when this was written; the digests are the durable references either way.
- **`mboost` is not a parity target.** It is there for the maintainer's exploratory
  `gamboost` work. Componentwise boosting is a different algorithm with no likelihood
  covariance; `select = TRUE` covers the term-selection role inside penalized likelihood.
- **`weights` are not an `offset`** (PLAN Anchor 5). The target uses weights and no offset;
  the existing polaris engine uses an offset. Both are wanted, and A/E is what `η`
  estimates rather than an input.
- **The MI term is a varying-coefficient term, not a tensor**, and it is better conditioned
  than what the old epic built — 13 coefficients against 38-60. Do not "improve" it.
- **Do not compare coefficients outside Stage A.** It is the mistake that looks most like
  rigour and is least informative.
- **The conformance CI gate blocks on levels 1-3 and annotates 4-5.** Do not narrow
  `REQUIRED_LEVELS` to go green.

## Carried in from the superseded epic

- **The level-4 Kass-Steffey under-inflation is a live BLOCKER** — ours inflates
  1.11-1.21x where `mgcv` inflates 1.49-1.87x, same direction every cell. It is
  engine-agnostic, and it is the standing bar on labelling any interval a 95% band.
  Whatever this engine reports as a band inherits it. Tracked in
  `PRODUCT_DIRECTION_2026-07-24.md`.
  **ADR-190 (2026-08-15) re-scoped it: this is a FORMULA gap, not our arithmetic.**
  `vcov(unconditional = TRUE)` is not `Vb + J V_rho Jᵀ` — built from `mgcv`'s own
  coefficients, `V_rho` and λ, that expression reproduces *our* number, not `mgcv`'s.
  `mgcv` implements Wood, Pya & Säfken (2016), which uses `dw/drho`; plain Kass-Steffey is
  its first-order part. **Closing it is a slice needing `dw/drho`, and it must be re-derived
  from the paper — `mgcv` is GPL (>= 2), this project is MIT.** Do not go looking for a bug
  in `smoothing_uncertainty`; two tests now pin that arithmetic as correct.
- **The old CONTINUATION's refinement-backlog harvest is owed** before its status may
  change from IN PROGRESS. Not this epic's work, but it is the reason that file is still
  open, and a reader should not mistake it for an active epic.

## Open questions (for human)

- **The duration treatment on real data** — band as factor, or band as ordered numeric via
  a representative value. The maintainer has reserved this as a modelling judgement; the
  engine will support both and the routine is forbidden from deciding it.
- **Scheduling.** This epic advances only when `ROUTINE_MGCV_PARITY.md` is registered as a
  scheduled task; the cron config lives outside the repo. Until then nothing here moves.
- **Ledger framing.** This epic is sourced from maintainer direction rather than the Tier-A
  table of a `COMMERCIAL_VIABILITY_REVIEW`. It is registered in
  `PRODUCT_DIRECTION_2026-07-24.md` so it is visible to a selecting routine, but the next
  commercial-viability review should re-rank it properly.
