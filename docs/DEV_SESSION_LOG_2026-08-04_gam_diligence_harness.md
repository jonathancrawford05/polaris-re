# Dev Session Log — 2026-08-04/05 (the real-data GAM epic, all three slices)

## Item Selected

- **Source:** active Epic — `docs/CONTINUATION_experience_gam_realdata.md`,
  slice 1 marked `NEXT`. Routine step 5a: an Epic in progress takes precedence
  over the direction backlog, and there was exactly one CONTINUATION at
  `IN PROGRESS` (the invariant established in the previous session).
- **Priority:** IMPORTANT (epic slice).
- **Title:** The diligence harness — load a real HMD/ILEC cache, fit the tensor MI
  surface, emit a committable findings report.
- **Branch:** `claude/quirky-ramanujan-5zhsw3` (environment-designated). The branch
  carried only already-merged history after #183, so it was restarted from the new
  `main` per the environment's git rules rather than stacked on merged commits.
- **PR:** #185 (draft).

## Baseline

`make test` at session start, on `main` at `9275e49` (the #184 merge):
**2939 passed, 3 skipped, 125 deselected**, 0 failures. Exactly the end state
#184 recorded. No NEW or CHANGED failures → PROCEEDED. The 3 skips are the
standing absent-CIA-2014-table skips.

End state: **3035 passed, 3 skipped** under `make test` (125 deselected). Next
session's expected baseline is **3035 passed, 3 skipped**.

**The session did not stop at slice 1.** It was scoped to the harness alone, but
the maintainer's HMD and ILEC data arrived mid-session — the handoff PLAN §3 was
designed around — so slices 2 and 3 completed too and the epic closed. Everything
below covers all three.

## What Was Done

**Built the harness the epic is actually blocked on.** `run_diligence` loads from
the local cache, aggregates to a *stated* level, attaches a static base, fits
`TensorMIModel`, and emits `DiligenceReport` — JSON plus Markdown, no plots, no
timestamps, no absolute paths. `scripts/experience_diligence.py` is the thin
argparse wrapper the PLAN names as the entry point; the logic lives in
`src/polaris_re/analytics/experience_diligence.py` so it is linted, mypy-checked,
covered and unit-tested like everything else. See **ADR-182**.

**The falsification discipline was applied to the harness, not just the epic.**
PLAN §2 names the post-2010 US slowdown as the thing the fit could fail to
reproduce. A harness that reported "slowdown" whatever it was handed would
confirm that hypothesis by construction and be worth nothing — so the suite
injects a slowdown *and* an acceleration and requires the matching verdict both
ways, plus a constant-improvement case where the reported change must be under
5e-4. That two-sided test is the single most important thing in the diff.

**Three closed-form verifications, because each claim in the docstrings is one
somebody will lean on.**

- *The window band is exact.* Asking `improvement_surface` for the two-year grid
  `[start, end]` makes its single step the contrast `η(end) − η(start)`, because
  the per-year steps telescope. Verified against the geometric mean of the annual
  grid to 1e-12 — so the early/late bands are real delta-method intervals, not
  per-year ones rescaled.
- *The base offset cancels.* Halving `q_base` leaves the improvement surface
  identical to 1e-10 while `overall_ae` doubles. That is what licenses using the
  data's own pooled crude rate as the offset instead of a mortality table the
  harness cannot ship — and it runs in CI, and on population data for which no
  insured table is the right base.
- *SOA's own MI is recoverable.* Their expected-with-MI over expected-without is
  their cumulative improvement factor; its year-over-year change **within a fixed
  attained age** is their annual MI. Injecting SOA MI = 1.0% and actual = 1.8%,
  the harness reports SOA 1.00%, fitted 1.80%, difference +0.80% — the injected
  disagreement, exactly.

**What the harness deliberately refuses to claim.** The overlap of the two
windows' bands is *not* a significance test for their difference: both contrasts
come from the same fitted coefficients and are correlated, and the difference's
variance needs a cross-covariance the public API does not expose. Rather than
quietly presenting overlap as significance, it ships labelled — in the dataclass
docstring, in the Markdown, and as an explicit JSON key
(`bands_overlap_is_not_a_significance_test`). Same for `overall_ae` ≈ 1: it is ~1
*by construction* under an empirical base, and the report says so in its caveats
instead of presenting it as a validation.

**Two ergonomic fixes drawn from the previous session's actual failures.** HMD
discovery searches the `STATS/` subdirectory the zipped bundle extracts into as
well as the flat `fetch_hmd` layout — the maintainer hit exactly that on
2026-08-03, and a harness that only knew the fetch shape would have reported "not
found" while staring at the file. And an ILEC directory holding more than one
candidate is a **refusal**, not a guess: silently picking a vintage would produce
findings about a release nobody chose.

**Verified as a committable artefact, not just as code.** Two runs of the script
in separate processes produce byte-identical JSON, which is the property that
makes a committed finding diff meaningfully against a re-run. **This claim did
not survive being tested properly** — see the review round below; it is true now,
for a reason that was not understood when it was first written.

## What Was Done After Slice 1 (the real-data rounds)

**Three defects reached the maintainer's runs, and no synthetic fixture could
have caught any of them** — fixtures have exposure in every cell because a
generator puts it there, are Poisson because a generator drew them that way, and
have thirty years because the generator was asked for thirty. That is the A4′
limitation restated one level down, and the concrete answer to "why run this on
real data" (ADR-182 amendments 2-4):

- **Zero-exposure cells** aborted the first ILEC run outright. Two cells in 15,882.
- **Bands were 4.67x too narrow** on HMD — φ = 21.84 against a plain-Poisson
  default. Correcting it cost a finding: age 75's +0.13% stopped being resolvable.
- **The ILEC year spline was over-flexible** for an 8-year window; `year_df=3` cut
  the mean absolute difference against SOA from 0.92% to 0.368%.
- **Tuning that down walked into patsy's cubic floor**, raised several frames deep
  as a bare `ValueError` — now a sentence.

**Findings delivered.** `MEASUREMENT_experience_gam_hmd.md` (slice 2): the
slowdown reproduced and localised to ages 45-65, replicated independently in
GBRTENW, with the old-age divergence traced to the fit's own 1990s baselines.
`MEASUREMENT_experience_gam_ilec.md` (slice 3): agreement with SOA's published
improvement to ~0.11%/yr, duration mix confounding the trend (φ 2.25 → 1.163 for
0.009% of exposure), and insured lives improving ~6-7x faster than the population
at 55-65.

**Duration banding and the mix estimator**, both on maintainer direction:
`band_duration_months` controls for select-period mix at ~9x the cell count rather
than ~60x, and `StandardisedAE` decomposes crude A/E into experience and mix
components. **The estimator shipped; the measurement did not** — both committed
ILEC reports predate it, so ILEC §4 remains an inference. Filed in
PRODUCT_DIRECTION as IMPORTANT.

**The notebook** (`notebooks/06_experience_gam_diligence.ipynb`) re-derives every
quantitative claim in both measurement documents from the committed JSON and
asserts it, closing a real gap: prose does not fail CI. It reads only committed
aggregates, so it runs for anyone who clones the repo.

## Files Changed

- `src/polaris_re/analytics/experience_diligence.py` — **new**, the harness:
  discovery, empirical base, duration banding, overdispersion scaling, the
  window comparison, SOA A/E and the mix decomposition.
- `scripts/experience_diligence.py` — **new**, the CLI wrapper.
- `tests/test_analytics/test_experience_diligence.py` — **new**, 85 tests.
- `notebooks/06_experience_gam_diligence.ipynb` +
  `tests/test_notebooks/test_experience_gam_diligence_notebook.py` — **new**.
- `docs/MEASUREMENT_experience_gam_hmd.md`, `docs/MEASUREMENT_experience_gam_ilec.md`
  — **new**, slices 2 and 3.
- `docs/measurements/` — **new**: four raw reports (HMD USA, GBRTENW, ILEC pooled,
  ILEC duration-banded) plus a README on why committing findings is not a licence
  problem and why the grouped cell table is not committable.
- `Dockerfile`, `.dockerignore` — ship `docs/measurements/` so the suite can read
  it inside the image.
- `src/polaris_re/analytics/__init__.py` — public exports.
- `docs/DECISIONS.md` — **ADR-182**.
- `docs/PLAN_experience_gam_realdata.md`, `docs/CONTINUATION_experience_gam_realdata.md`
  — slice 1 DONE, slice 2 NEXT, with what carries forward into reading its output.
- `docs/RUNBOOK_experience_data_acquisition.md` — new §3 (how to run the harness,
  what the verdict means, exit codes); §4 renumbered; the stale "the loader
  ignores them today" line about SOA's expected deaths corrected.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — two follow-ups promoted with provenance.
- `perf/history.jsonl` — one row for the branch HEAD.

## Acceptance Criteria

| Criterion (CONTINUATION slice 1) | Status | Notes |
|---|---|---|
| Runs green on synthetic fixtures in CI | ✅ | 85 tests |
| `--source hmd\|ilec` contract documented | ✅ | `--help`, module docstring, runbook §3 |
| Empty/missing cache → actionable message, not a stack trace | ✅ | Exit 2, names every location searched + the runbook |
| **No plots** | ✅ | Asserted in a test (`.png`/`.svg` absent from the rendering) |
| Explicit aggregation level, conservative default | ✅ | Stated in every report; `smoker`/`uw_class` retained |
| `"NA"` pooled as its own stratum, `"U"` held out | ✅ | Per ADR-181's empirical reading |
| A/E by calendar year vs `expected_deaths_vbt2015_mi` | ✅ | Plus the within-age fitted-vs-SOA surface comparison |
| `tests/qa/` goldens untouched | ✅ | Nothing in `products/` moves |

**Slice 2** (`MEASUREMENT_experience_gam_hmd.md` §7): slowdown answered either way ✅;
compared against the published reference ✅; cross-population agreement
characterised ✅ (GBRTENW); no data files added ✅.

**Slice 3** (`MEASUREMENT_experience_gam_ilec.md` §8): insured surface fitted and
compared ✅; divergence characterised ✅; column-map override ✅ (ADR-181); no data
files added ✅.

## Perf History

Row appended for the branch HEAD, per ADR-177 and the position settled in #184:
a row on **unchanged engine code is a control observation**, and this diff touches
no engine code at all.

Measured: `peak_mib=33`, `best_of_k_seconds=0.0602`, output fingerprint
`8331a13f…` — identical to every prior row. The series now reads 0.0594 / 0.0703
/ 0.0619 / 0.1489 / 0.0870 / **0.0602**, which settles the open question from
#184: the 0.1489 outlier was runner noise, not the start of drift. That is
exactly what a control point is for.

Creep verdict: **no structural (MiB) creep** — `peak_mib` flat at 33 with Δ+0, so
the gating signal is clean. The detector does raise its *advisory* wall-time flag
(recent/baseline 1.406x), which is the arithmetic of a 6-row window still
straddling the 0.1489 spike; per the maintainer rule (2026-07-12) wall time
informs and never gates, and the run that produced this row is among the fastest
in the series. Worth re-reading, not acting on, when the window rolls past the
spike.

## PR #185 review round

Automated review **approved** — zero P0, zero test failures, goldens green. One
[P1], three [P2]s, plus a caution on the session log itself. All addressed
in-PR; two changed the design rather than the wording.

**[P1] was a real contract defect, on the path a maintainer meets first.** The
ILEC missing-cache case exited **1** against a documented **2**, because `main()`
classified "no data" by matching message *wording* and the missing-directory
message matched none of the three substrings. Fixed by classifying on **type**
(`ExperienceCacheMissingError`), so rewording can never move an exit code again.
The test had covered only `hmd` — the path that happened to work — which is
exactly why it shipped; it is now parametrised over both.

**The determinism claim in this log was over-stated, and testing it properly
falsified it.** The committed test compared two renderings of one *in-process*
report, which cannot see a per-process difference; the cross-process `cmp` was
run by hand and passed by luck. Writing the real test found two runs of the same
script over the same cache differing by up to **1.2e-14 relative** in the band
endpoints. The cause is not a clock: it is multithreaded BLAS inside
`cov_params` and the delta-method `einsum`, reassociating its sums differently
depending on how threads carve up the work — `OMP_NUM_THREADS=1` removes it
entirely. Point estimates were always stable; only the covariance path moved.

Fixed in the artefact rather than the prose, since being committed and diffed is
the artefact's whole purpose: floats round to 12 significant digits on
serialisation, and the suite now runs the script in two interpreters and compares
bytes. Byte-stable across six independent processes. The honest claim is
*vanishingly unlikely to diff spuriously*, not *provably identical*.

**[P2] verdict semantics** — `acceleration` when no age was slower includes an
exactly-zero delta, which is neither. Rule extracted into a pure `_verdict()` and
tested on exact inputs. My first attempt at that test re-implemented the rule
instead of calling it — vacuous in precisely the way PR #184's [P1-2] was, caught
before commit this time.

**[P2] A/E vs fit populations** — kept as-is (SOA's denominator should cover
every cell they priced), but the divergence is now a stated caveat naming both
counts and the exposure share.

**[P2, process]** — the `uw_class` dtype item and the new artefact-rounding
finding are promoted into PRODUCT_DIRECTION with provenance rather than listed in
a third consecutive session log.

## First real-data run (maintainer, 2026-08-04)

**HMD USA 1990-2019 ran clean and returned `mixed (3/5 reference ages slower)`** —
not the clean slowdown PLAN §2 named. Recorded as-is pending the report; per the
plan that is a *successful* slice, and nothing gets tuned until it agrees.

**ILEC aborted on the first attempt** — see ADR-182 amendment 2. Two zero-exposure
cells out of 15,882 stopped the whole run; the fix drops them and reports both the
count and the deaths they held (0.0 here, so nothing lost). The defect was
invisible to the suite because every synthetic fixture had exposure in every cell.
That is the epic's thesis in miniature: exercising a harness on data you generated
proves it recovers what you injected, not that it survives what exists.

## Open Questions / Follow-ups

1. **The mix decomposition is implemented but not measured on the book.** Both
   committed ILEC reports predate `StandardisedAE`, so ILEC §4 is still an
   inference. **Promoted to PRODUCT_DIRECTION as IMPORTANT** — one maintainer run
   with `--duration-bands` converts it.
2. ~~**The ILEC default pools across duration**, leak unmeasured.~~ **RESOLVED
   2026-08-05:** measured by running the harness twice and differencing. The leak
   was large — φ 2.25 → 1.163, every reference age moved, age 65 by 1.15pp/yr.
   Duration banding shipped; ADR-182 amendment 4. Superseded follow-ups (age 45
   boundary contamination, the uninterpreted A/E level, MIM-2021 rate comparison)
   are now in PRODUCT_DIRECTION. Original text kept for the record: worth one run
   in slice 3 before believing a surprising number.
3. **Goldens cannot detect a last-ulp engine perturbation** (carried from
   2026-08-04's earlier session). Still IMPORTANT, still unaddressed.
4. **`uw_class` dtype inconsistency across composed/uncomposed paths** — no
   longer carried here: **promoted** to PRODUCT_DIRECTION as NICE-TO-HAVE with
   provenance (PR #185 review [P2]).
5. **`mgcv` oracle (ADR-151) still unexecuted** — maintainer's to run, and real-data
   fitting is when it earns its keep.

## Epic Status

**COMPLETE.** All three slices delivered, every acceptance criterion met. Nothing
replaced it, so the next routine run lands on step 5b — start a new Tier-A epic or
document maintenance mode. Flagged for the maintainer in the PR review.

## Parked Polish

**None.** Everything above is 1st-order: a follow-up of this slice's own planned
scope or a carried item already filed. The step-17 cap did not bite.

## Impact on Golden Baselines

**None.** Nothing in `products/` or the projection path moves; `tests/qa/` is
untouched in the diff and green. The `perf/history.jsonl` append is diagnostic
data, not a golden change.
