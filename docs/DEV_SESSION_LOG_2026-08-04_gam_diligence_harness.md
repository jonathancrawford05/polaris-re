# Dev Session Log — 2026-08-04 (slice 1: the experience-GAM diligence harness)

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

End state: **3004 passed, 3 skipped**. Next session's expected baseline is
**3004 passed, 3 skipped**.

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

## Files Changed

- `src/polaris_re/analytics/experience_diligence.py` — **new**, the harness.
- `scripts/experience_diligence.py` — **new**, the CLI wrapper.
- `tests/test_analytics/test_experience_diligence.py` — **new**, 65 tests.
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
| Runs green on synthetic fixtures in CI | ✅ | 65 tests, ~9 s |
| `--source hmd\|ilec` contract documented | ✅ | `--help`, module docstring, runbook §3 |
| Empty/missing cache → actionable message, not a stack trace | ✅ | Exit 2, names every location searched + the runbook |
| **No plots** | ✅ | Asserted in a test (`.png`/`.svg` absent from the rendering) |
| Explicit aggregation level, conservative default | ✅ | Stated in every report; `smoker`/`uw_class` retained |
| `"NA"` pooled as its own stratum, `"U"` held out | ✅ | Per ADR-181's empirical reading |
| A/E by calendar year vs `expected_deaths_vbt2015_mi` | ✅ | Plus the within-age fitted-vs-SOA surface comparison |
| `tests/qa/` goldens untouched | ✅ | Nothing in `products/` moves |

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

## Open Questions / Follow-ups

1. **Slice 2 is a maintainer run, not a coding task.** The harness is done; what
   is missing is the data. The next session's job is to read the returned report
   honestly against SOA MIM-2021 / the CMI literature and write
   `MEASUREMENT_experience_gam_hmd.md` — including any way the fit disappoints.
2. **The ILEC default pools across duration.** A duration mix drifting with
   calendar year leaks into the fitted trend. Every report states it, and
   `--group-by` can separate it at ~60x the cell count — but nobody has yet
   measured how large the leak is on the real file. Worth one run at both levels
   in slice 3 before believing a surprising number.
3. **Goldens cannot detect a last-ulp engine perturbation** (carried from
   2026-08-04's earlier session). Still IMPORTANT, still unaddressed.
4. **`uw_class` dtype inconsistency across composed/uncomposed paths** — no
   longer carried here: **promoted** to PRODUCT_DIRECTION as NICE-TO-HAVE with
   provenance (PR #185 review [P2]).
5. **`mgcv` oracle (ADR-151) still unexecuted** — maintainer's to run, and real-data
   fitting is when it earns its keep.

## Parked Polish

**None.** Everything above is 1st-order: a follow-up of this slice's own planned
scope or a carried item already filed. The step-17 cap did not bite.

## Impact on Golden Baselines

**None.** Nothing in `products/` or the projection path moves; `tests/qa/` is
untouched in the diff and green. The `perf/history.jsonl` append is diagnostic
data, not a golden change.
