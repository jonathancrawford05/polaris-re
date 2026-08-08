# Dev session log — 2026-08-08 — spline diagnostics epic (PR #186)

**Branch:** `claude/quirky-ramanujan-5zhsw3`
**Base:** `main` @ `dd1088a` (PR #185 merged 2026-08-08)
**Epics:** `PLAN_gam_spline_diagnostics.md` (COMPLETE), `PLAN_penalized_mi_surface.md` (scoped)
**ADRs:** ADR-184 + amendments 1-3; ADR-183 amendment 2

## Baseline and end state

| | |
|---|---|
| `make test` at `1b110a0` (slice 1) | 3056 passed, 3 skipped, 125 deselected |
| `make test` at `a2f1d88` (slice 3) | **3065 passed, 3 skipped, 125 deselected** |
| Reviewer's full `pytest tests/` | 3191 passed, 5 skipped — reconciles as 3065 + 125 deselected + 1 |
| `tests/qa/` goldens | untouched; golden regression 12 passed |
| ruff | clean (`src/`, `tests/`) |
| mypy | 270 errors / 44 files, **identical to `main`** (verified by stashing) |
| perf row | `peak_mib` 33 (Δ+0), fingerprint `8331a13f7ce7` **unchanged**, best-of-5 0.1232 s |

The +9 reconciles exactly: 6 in `test_experience_gam_ramp_diagnostic.py`, 3 in
`test_experience_diligence.py` (invalid-margin guard 3→5 cases, plus the
linear-margin acceptance regression).

**On the perf row's 0.1232 s.** The series reads 0.0594 / 0.0703 / 0.0619 / 0.1489
/ 0.0870 / 0.0602 / 0.1232 — the wall-time creep flag is advisory and fires on a
window still straddling the 0.1489 spike. This container ran two full suites
concurrently with the probe. **`peak_mib` and the output fingerprint are the gates
and both are unchanged**, which is the substantive check for an epic that declared
no behaviour change.

## What happened, in order

**A specification review that turned into an epic.** The session began with the
maintainer asking a plain question — how many basis splines does the GAM use — and
the answer was worse than expected: `patsy.bs(df=k, degree=3)` carries `k - 3`
interior knots, so the ILEC reports' `year_df=3` margin has **zero** and is a global
cubic, not a spline. That is the "2026-08-07 specification review" the plan cites.

**A conflation I shipped in the plan, caught by the maintainer.** The plan set the
diagnostic axis as `year_degree ∈ {1,2,3}`, implying degree alone controls
flexibility. The maintainer asked whether degree < 3 was even available. It is —
the constraint is `df >= degree` — and `degree=1` with `df=3` keeps two interior
knots and ramps freely. **A diagnostic written that way would have run, passed, and
tested nothing.** Corrected to the `df == degree` ladder and pinned by
`test_lowering_degree_without_df_still_permits_a_ramp`.

**Slice 1 falsified both of the plan's hypotheses**, including the one argued for
in the plan itself. Noiseless recovery is exact, so the cubic is not biased; the
swing peaks at the youngest fitted age in every age range, so the knots are
innocent. The mechanism is variance at the death-poor young end.

**Slice 3 found no trade where the plan assumed one.** Scoped to price what
lowering the order costs, it found quadratic dominates cubic outright.

**Slice 4 did not transfer.** The maintainer's two real-data runs landed on
interpretation-table row 2, written in advance: the climb is invariant to the
setting, so slices 1-3 describe the estimator rather than this book.

**Two by-products outweighed the headline.** The control run falsified the
repository-wide byte-for-byte determinism claim (a rounding tie flipping under a
reassociated parallel sum), and the quadratic beat the cubic on SOA's own expected
deaths by 10% and 35% — corroborating slice 3's fixture result on real data.

**Licensing ran in parallel and closed most of the way.** SOA terms read (§3,
restrictive), permission requested with dates pinned, HMD terms read (§4,
permissive under CC BY 4.0), provenance determined as the `STATS` estimates tier,
access date established from Spotlight metadata as 3 August 2026. One item open:
the version DOI.

## Things I got wrong, and how they surfaced

1. **`df` vs `degree` conflated in the plan** — caught by the maintainer's question,
   not by me. Now a test.
2. **Hypothesis A was my own argument** and slice 1 killed it. A cubic represents a
   straight line exactly; "must place its curvature somewhere" describes
   interpolation through noise, not least squares on a representable truth.
3. **ADR-184 §7's hedge was wrong in direction** — it guessed the fixture's
   simplifications understated the real artifact; slice 4 showed the reverse.
4. **"Downloaded in August 2026" was my inference presented as fact** inside a
   licence condition. Withdrawn, then re-established independently as 3 August —
   right, but right by luck, which is the same failure the CC BY 4.0 guess would
   have been.
5. **`--year-df 1 --year-degree 1` recommended prematurely** — slice 3 showed the
   linear rung is blind to genuine curvature. Revised to `2 / 2` before it reached
   a maintainer run.
6. **`TensorMIModel`'s input narrowing shipped undisclosed** (ADR-184 amendment 3),
   surfacing only as a silent one-character edit in an unrelated test. Caught by
   the automated review, not by me.

## Routine discipline

The automated review returned **six P1s, all process**: no session log (this file),
no perf row (appended), no continuation docs (both written), a stale ledger entry
still sourcing two retracted claims (healed), the three surviving age-45
explanations unharvested (promoted 2026-08-08d), and the undisclosed behaviour
change (ADR-184 amendment 3).

Worth recording plainly: the epic's *documentation* discipline was strong while its
*routine* discipline lapsed on five counts simultaneously. The common cause is that
this session ran as a long interactive conversation rather than a routine
invocation, and every step of the routine that is a checklist item rather than a
consequence of the work got skipped. The findings were all correct.

## Next session

`PLAN_penalized_mi_surface.md` slice 1, on a fresh branch. Read the six anchors and
the four registered predictions first. Anchor 1 — λ=0 reproduces `TensorMIModel`
exactly — is the correctness spec and it already exists.
