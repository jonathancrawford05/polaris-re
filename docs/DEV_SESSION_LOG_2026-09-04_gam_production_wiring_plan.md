# Session log — 2026-09-04 — registering the GAM production-wiring epic

**Session type:** NOT a daily-dev routine run. An interactive, maintainer-directed
session: review of PR #225 (slice 7d) and PR #226 (slice 7e), followed by an
external-consumption readiness assessment the maintainer asked for, followed by
the plan they then asked me to prepare. Recorded in this format anyway because
the routine reads these files, and PR #227's own review found the absence a [P1].

**Branch:** `claude/brave-keller-6tygau` (this session's designated branch),
rebased onto `origin/main` at `40f14d8` after the maintainer merged PR #226.
**PR:** [#227](https://github.com/jonathancrawford05/polaris-re/pull/227).
**Deliverable:** `docs/PLAN_gam_production_wiring.md` — docs only, no code.
**ADR:** none. Registering a plan is not an architecture decision; the decisions
this epic needs are the three open questions it files for the maintainer.

## Gate reason (why this work, and not slice 7f)

**Maintainer direction, 2026-09-04**, in as many words: *"I always planned to
wire our best mgcv parity candidate. I recommend you prepare the plan."* Raised
from the PR #225/#226 review conversation, in answer to the maintainer's own
question about whether the GAM is fit to show on the dashboard.

This is a directed pick, not a fallback pick, so the fallback gate does not
apply. Recording it explicitly because the active epic
(`CONTINUATION_mgcv_parity_engine.md`, IN PROGRESS) *did* have an advanceable
next slice — 7f — and a reader checking the fallback rule mechanically would
otherwise score this as "polish shipped while the epic could advance." It was
not: the maintainer ranked it. Whether it continues to outrank 7f is open
question 3 of the plan.

## Baseline

`uv run pytest tests/ -q -p no:randomly` on `claude/brave-keller-6tygau` @
`979a07d`, after `uv sync --all-extras` and
`scripts/convert_soa_tables.py --source pymort`:

**3727 passed, 19 skipped, 0 failed** (858s, no deselection — `@slow` included).
Independently reproduces PR #227's review run on this same commit, which
reported the identical 3727 / 19 / 0.

No standing SOA-conversion failures: step 2's `pymort` conversion reached its
source, so the CSVs the 4–5 commonly-recorded failures depend on were present.
R is **not** installed in this container, so the R-gated conformance tests are
part of the 19 skips — this baseline does not exercise them. Docs-only change;
the suite cannot differ from `main` and did not.

## What was done

1. **Reviewed PR #225 (slice 7d)** — approved, one [P1] and two [P2] posted as
   inline comments. The [P1] is a live defect in a published justification: the
   cheap-check sentence cites `TestFiniteDiffStep`'s `< 0.05` gradient-norm
   assertion as if it were the central difference's noise floor, and calls a
   `0.02` residual "an order of magnitude above" a bound it is in fact below.
   The conclusion holds for a different reason already in the ADR (the exact
   term collapses the residual ~1500x). Mirrored in three places.
2. **Reviewed PR #226 (slice 7e)** — no objection; verified the re-gate does not
   loosen. Tolerances derived from precedent, the gate still discriminates
   (single-start reads `0.4456` against the `2e-2` bound and still fails), the
   old gate preserved as `agrees_log10_sp`, claim sentence written before code.
   Merged by the maintainer.
3. **Audited the import graph for external-consumption readiness** — the finding
   below.
4. **Registered `PLAN_gam_production_wiring.md`** and harvested it.

## The finding

**`gam_model.fit_polaris_gam` — the engine slices 1–7e validated — has zero
production consumers.** Read off the source tree at `40f14d8`, not asserted:

- imported by exactly five conformance modules and three test files;
- absent from `analytics/__init__.py`, which *does* export `ExperienceGAM`,
  `TensorMIModel` and `BayesianTensorMIModel`;
- neither it nor `experience_gam_penalized` / `gam_uncertainty` /
  `gam_uncertainty_mi` is referenced from `dashboard/`, `api/`, `cli.py`,
  `mcp/`, `services/`, `pipeline.py` or `viz/`.

`dashboard/views/experience_improvement.py` takes its GAM imports from
`experience_gam` alone — statsmodels-backed. **So the parity evidence and the
shipped surface are attached to two different implementations, and no slice
downstream of 7e changes that.**

Four blockers scope the epic, each measured rather than assumed: no `te`
producer in the validated path (blocker A); quasi-Poisson blocked by
`dispersion_fixed=False` (B); re-pointing the band would lower coverage (C);
the defaults are the configuration that fails ADR-221's own gate (D). Full
statement and line references in the PLAN.

## Provenance (ADR-193)

**This session publishes no parity comparison.** The one table it transcribes
(blocker C's coverage figures) compares empirical coverage against a *nominal*
0.95 — one producer, no external reference, so `MEASUREMENT (own criterion)`
and not a comparison at all in the two-producer sense. Every figure is quoted
from `docs/MEASUREMENT_unconditional_coverage.md`, with the two caveats that
document attaches to its ADR-187 row now carried across (see the post-review
addendum).

The PLAN's *planned* comparisons are classified in advance: slice 1 INDEPENDENT
(vs `mgcv`, claim + ledger row + both tiers required); slice 2
`MEASUREMENT (own criterion)` (Polaris vs Polaris — cannot be parity evidence
however small its residual); slice 5 forbids an unqualified "mgcv parity"
claim. Goldens appear only as a byte-identical behaviour pin, never as evidence
a number is correct.

## Quality gate

- `ruff format --check` / `ruff check` on `src/` and `tests/` — clean (nothing
  Python changed).
- `scripts/measurement_stamp.py check` — `5 ok, 1 unstamped, 0 drifted`;
  unchanged by this PR.
- `pytest tests/test_docs` — 15 passed.
- Full suite — the baseline above.
- CI on `979a07d` — all 7 checks green.

## Perf history

**No row appended, deliberately.** ADR-177 expects one row per initial routine
PR; this is not a routine PR and changes zero engine code, so a row would
duplicate `main`'s own reading and add a noise point to the series the creep
detector reads. Recorded here as a deviation rather than an omission — PR #227's
review raised it as [P2-1] and this is the response.

## Post-review addendum — PR #227's automated review

Approved, zero P0s, four findings. All verified before acting; two fixed here,
one fixed in the PLAN, one declined with reason.

- **[P1-1] epic unharvested — FIXED.** `PRODUCT_DIRECTION_2026-07-24.md` now
  carries a `Harvested 2026-09-04` section registering the epic with a pointer
  to the PLAN, the import-graph finding, blockers B and C, the dormant-owner
  problem, and the three maintainer questions — each with an order tag. The
  review was right that the epic was otherwise discoverable only by someone who
  already knew the filename, since it deliberately has no CONTINUATION.
- **[P1-2] no session log — FIXED.** This file. Baseline, branch record and gate
  reason are the three things the review named as missing.
- **[P2-2] the coverage table dropped two caveats — FIXED, and it mattered.**
  The `0.9586` row is **age-flat truth only** and is **quoted from ADR-187, not
  re-measured**. Both are now stated in the PLAN, the comparison is restated
  like-for-like as age-flat 0.9586 vs age-flat 0.7815, and the gap this exposes
  — no age-varying coverage figure exists for the shipped estimator — is now
  slice 4's **first `[machine]` criterion**, because the recommendation slice 4
  is expected to make would otherwise rest on a comparison that exists on one
  truth and is assumed on the other. The conclusion survives; its statement was
  sloppier than the source supports.
- **[P2-1] no perf-history row — DECLINED**, see "Perf history" above.

The review also raised two items for the maintainer that are not mine to close:
the sequencing question (open question 3), and that the coverage BLOCKER's
nominal owner (`PLAN_penalized_mi_surface.md`) has slices 6–7 PARKED, so it has
no active path to closure. The second is now harvested.

## Follow-ups filed

All six are in `PRODUCT_DIRECTION_2026-07-24.md` under
`Harvested 2026-09-04`, order-tagged. Nothing 3rd-order or deeper was promoted;
nothing was parked that a 1st-order reading would promote.

**Not filed, because it belongs to the PR that owns it:** PR #225's [P1] (the
cheap-check justification) is posted on that PR as an inline comment and is
that PR's to fix, not this session's.
