# Dev session log — 2026-08-23: the coverage gate run, and a stale measurement found

**ADRs:** ADR-203 (+ amendment 1), ADR-204.
**PRs:** #207 (`claude/zealous-mendel-9e1awi`), #208 (`claude/measurement-stamp`).
**Predecessors:** ADR-202 (level 4 closed), ADR-190 decision 4 (the registered
prediction this session resolved).

This log exists because PR #207's review graded its absence a [P0]: the two
2026-08-22 logs cover ADR-201 and ADR-202, and commits `0bb4cf2`, `6122a69` and
`db50e71` had none.

---

## 1. Test baseline, stated correctly this time

**Full suite at session start: 3350 passed, 22 skipped, 126 deselected, 5 failed.**

**The 5 failures were my environment, not the repository.** All five —
`test_synthetic_block.py::TestCalibratedPremiums` (×4) and
`test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface` — raise
`FileNotFoundError: data/mortality_tables/soa_vbt_2015_male_smoker.csv`. I had
not run the documented `scripts/convert_soa_tables.py --source pymort` step. After
running it, all 54 of those tests pass.

**The two 2026-08-22 logs recorded this wrongly**, as "5 pre-existing
missing-data-file failures" and "1 pre-existing data-file failure" — as though it
were a property of the repository. PR #207's review checked and found 0 failures,
correctly. A baseline that names an omitted setup step as a repo state is worse
than no baseline, because the next session diffs against a fiction. Corrected
here rather than in those logs, which are records of what was believed then.

The same omission bit twice: PR #208's first CI run failed for a related
environment reason (below).

---

## 2. What was done

### ADR-203 — the coverage gate, run

Maintainer authorized the sequence (quoted verbatim in ADR-203). Ran ADR-188's
gate against `gam_uncertainty` on the production path, 200 replicates × 2 truths
× 4 bands from the same fits, **without touching production** (PLAN Anchor 7):
`analytics/gam_uncertainty_mi.py` reads a fit `experience_gam_penalized` produced
and returns a covariance beside it.

**Result: confirmed in direction, refuted in sufficiency.** Eq. (7) moves coverage
0.7815 → 0.8167 and 0.8090 → 0.8354 against a 0.9192 floor. It moves — ADR-190
decision 4's direction — and still fails by up to 0.1025. The formula was *a* gap,
not *the* gap.

**Finding 0, unplanned: the committed baseline was stale.** 0.8201 / 0.8516 did
not reproduce; the *unmodified* script on current production gives 0.7435 /
0.7815. Bisected under monkeypatch to `ce0b9f1` — the correct maintainer-authorized
ADR-197 REML fix, which changed λ selection (−0.0432 / −0.0410). Nothing re-ran
the study, so it went stale silently and stayed cited as current for four days in
seven documents, including ADR-190 decision 4 itself.

### ADR-204 — provenance stamps (PR #208)

The mechanism finding 0 argues for: a SHA-256 of the transitive `polaris_re`
import closure of each measurement document's producer, checked in CI. Fails on
drift in a *stamped* document; warns on unstamped. Separate PR because a CI gate
is a policy decision reviewers should be able to accept independently of the
mathematics in #207.

---

## 3. Two things I got wrong

**The `V''` dispersion, caught by review, not by me.** `wps_correction` added a
`phi = 1` `V''` to a dispersion-scaled `Vb`. Understated by a factor of `phi`;
invisible on the conformance cases, which fix scale at 1. See ADR-203 amendment 1.

Worth recording separately: **my first verification of the reviewer's claim was
the wrong experiment.** Scaling only `v_beta` reads `phi^3`, because
`d_information` is built from design/weights/penalties and carries no scale, so
the call mixes two bases. It looked conclusive and it was not. The consistent
experiment — scaling the information matrix *and* its derivative — gives exactly
`phi` (2.000000, 3.500000, 0.500000). Had I stopped at the first number I would
have "refuted" a correct review finding with a confident measurement.

**Two provenance tests assumed a full checkout**, turning PR #208's Docker job
red. The image copies `src/`, `tests/` and `scripts/` in full but only part of
`docs/`. One test failed there; the other would have *passed vacuously*, which is
worse, since only the failure is visible. Both now skip on a partial checkout.

---

## 4. Perf history

One appended row is not part of this session's work; `perf/history.jsonl` stands
at **24 rows**.

**Creep verdict, measured:** `insufficient_data=False`, `has_structural_creep=False`,
`has_wall_time_creep=False`. A clean pass on all three.

PR #207's review expected `insufficient_data` at 22 rows against a 2×window
requirement. There are 24 rows and the verdict is not `insufficient_data`. Recorded
as measured rather than as predicted.

---

## 5. Quality gate

- `ruff format` / `ruff check` clean on `src/`, `tests/`, and the changed scripts.
- `mypy` clean on every new module.
- **#207:** 69 tests across the four affected analytics modules; full CI green on
  `9e210fe`, including both mgcv conformance jobs.
- **#208:** 20 R-free tests; CI green after the Docker fix.
- Mutation-verified twice, because a test that cannot fail is not evidence:
  zeroing `V''` fails `test_the_second_order_term_is_not_zero`; reverting the
  dispersion scaling fails the new dispersion test (ACTUAL 1.0, DESIRED 2.0).

---

## 6. What is NOT closed

- **Re-pointing production** — still needs its Anchor 7 sign-off and its own
  determinism answer (ADR-186). ADR-203 decision 2: coverage does not supply the
  argument; ADR-202's parity is a separate case.
- **The second cause of the coverage shortfall** — unidentified. Both bands are
  worst at `old >= 80` (0.7145 / 0.7165 against 0.9065 / 0.9188 at `young <= 50`).
  A lead, not a finding.
- **Labelling any interval a 95% band** — maintainer-reserved.
- **Four measurement documents remain unverified** — ADR-203's audit flagged them
  as older than their dependencies. Two (`hmd`, `ilec`) cannot be regenerated
  without the experience cache; `RUNBOOK_measurement_provenance.md` §3 is written
  for a session that has it.
