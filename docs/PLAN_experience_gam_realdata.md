# Plan: real-data diligence for the experience GAM (HMD + SOA-ILEC)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Real-data diligence run for the
experience GAM", **IMPORTANT** (reclassified from ADR-150 NICE-TO-HAVE on
2026-08-03 maintainer direction).
**Constituted:** 2026-08-03, replacing the parked recursion-vectorisation epic.
**Classification:** LARGE — 3 slices, with a hard split between autonomous and
maintainer-run work (see §3).
**Status:** slice 1 NEXT — see `docs/CONTINUATION_experience_gam_realdata.md`.

---

## 1. Why

The A4′ epic shipped fifteen slices of tensor-GAM machinery: `experience_gam.py`,
the `te(attained_age, calendar_year)` mortality-improvement surface, hierarchical
partial pooling, the `mgcv` oracle, HMD and ILEC loaders, CLI and versioning.

**Every fit in it is against synthetic data with an injected known surface.**

That design was right for building the thing — an injected surface is the only way
to prove a recovery is *correct*, because you know the answer. It is the wrong
place to stop, because it proves only that the implementation recovers a surface
it was handed. It says nothing about the question a reinsurer would actually ask:
*does this recover real mortality improvement from real experience?*

CLAUDE.md §1 names "no native ML integration" as a defining weakness of AXIS and
Prophet. That is the product thesis. A GAM validated exclusively on synthetic data
does not discharge it — and the gap is one real-data run wide, because the loaders
already exist and are already unit-tested.

**The deliverable is a credibility artifact**: a fitted improvement surface from
public data, shown to reproduce a structural feature with an independent published
record, that can be put in front of a client.

## 2. What "success" means, stated before we start

The tempting version of this epic is "fit the GAM to HMD, publish a nice surface".
That is unfalsifiable and worth little. The version worth doing names, in advance,
something the fit could **fail** to reproduce:

- **The US improvement slowdown after ~2010.** Widely documented, independently
  published (SOA MIM-2021 and the CMI/academic literature), and structurally
  visible in HMD 1990–2019. If the tensor surface fitted to HMD does not show
  improvement rates flattening in the 2010s relative to the 1990s, either the fit
  or the model is wrong — and finding that out is the point.
- **Cross-population agreement.** England & Wales (`GBRTENW`) has its own
  documented post-2011 slowdown. Two independent populations showing the same
  qualitative structure is a far stronger claim than one.
- **Insured-vs-population divergence.** ILEC (insured) should *not* look identical
  to HMD (population) — insured lives are underwritten and selection effects are
  real. A model that shows them identical has a bug; the interesting output is the
  *shape* of the difference.

A slice that reports "the surface did not reproduce the slowdown" is a **successful
slice**. Recording that would be more valuable than a plausible-looking plot.

## 3. The hard constraint: who can run what

This is the structural fact the plan is built around, and it cannot be designed
away.

- **HMD** requires a personal account (free, registration + user agreement).
- **SOA-ILEC** requires accepting SOA terms and is a manual download.
- **Neither may be committed** — repo, Docker image, or CI (Design Anchor 6, and
  the licences).
- **Autonomous sessions run in ephemeral containers.** Even with credentials they
  could not retain the data, and could not commit it if they did.

So the division of labour is fixed, and it mirrors the pattern that already worked
in this repo on 2026-08-03 for the parallel measurement — the routine wrote
`scripts/bench_portfolio_parallel.py`, the maintainer ran it, the **findings** were
committed and the raw data was not:

| | autonomous session | maintainer |
|---|---|---|
| loaders, fitting harness, report generator | ✅ builds | |
| exercise on synthetic fixtures | ✅ | |
| acquire HMD / ILEC data | | ✅ (`docs/RUNBOOK_experience_data_acquisition.md`) |
| run the harness on real data | | ✅ |
| commit the findings | ✅ from maintainer output | ✅ |
| commit the data | ❌ never | ❌ never |

Every slice below is scoped so its autonomous portion is complete and mergeable
**without** the data. The data unblocks the *findings*, not the code.

## 4. Slices

### Slice 1 — The diligence harness (autonomous; no data required)

A committed, reproducible entry point that takes a local cache path and emits a
findings report — the analogue of `scripts/bench_portfolio_parallel.py`.

- `scripts/experience_diligence.py`: load (HMD or ILEC) → fit the tensor MI
  surface → emit a structured report (JSON + a Markdown table) covering fit
  diagnostics, the improvement-rate surface sampled at reference ages, and the
  decade-over-decade comparison that the slowdown test needs.
- Exercised end-to-end in tests on the **existing synthetic fixtures**, so the
  harness is proven before it ever sees real data.
- Refuses to run on an empty/missing cache with an actionable message pointing at
  the acquisition runbook — the first thing a maintainer hits should be a
  sentence, not a stack trace.
- **Emits no plots.** Numbers and tables commit and diff; images do not.

Acceptance: the harness runs green on synthetic fixtures in CI; a documented
`--source hmd|ilec` contract; goldens untouched (nothing in `products/` moves).

### Slice 2 — HMD findings (maintainer runs; session records)

The maintainer runs slice 1's harness against real HMD (USA 1990–2019 primary,
GBRTENW secondary) and returns the report. The session commits
`docs/MEASUREMENT_experience_gam_hmd.md`: the fitted surface's summary, the
slowdown test verdict, cross-population agreement, and an honest reading —
including any way the fit disappoints.

Acceptance: the slowdown question answered **either way**, with the comparison
against the published reference stated; no data files added.

### Slice 3 — ILEC insured validation (maintainer runs; session records)

Same shape, against insured experience. The interesting output is the
insured-vs-population divergence, not agreement. Likely also produces a
per-vintage `ILEC_COLUMN_MAP` override, which *is* autonomous work once the header
diff comes back.

Acceptance: insured surface fitted and compared to the HMD population surface;
divergence characterised; column-map override committed if needed.

## 5. Out of scope

- Committing any HMD or ILEC file, in any form, at any resolution.
- Wiring real-data fits into the pricing path or the assumption pipeline —
  this epic validates the model, it does not change any default assumption.
- Executing the `mgcv` oracle (ADR-151) — needs an R-equipped machine, is the
  maintainer's to run, and is a separate NICE-TO-HAVE. Worth doing *alongside*
  slice 2 if convenient, since real-data fitting is exactly when an independent
  cross-check earns its keep.
- Anything in `products/`. The parked recursion epic stays parked.
