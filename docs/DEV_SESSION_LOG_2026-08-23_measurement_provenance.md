# Dev session log — 2026-08-23: measurement provenance stamps (PR #208)

**ADR:** ADR-204.
**PR:** #208, branch `claude/measurement-stamp`.
**Companion:** `DEV_SESSION_LOG_2026-08-23_coverage_gate_and_provenance.md` (PR #207,
ADR-203 — the finding this PR is the mechanism for).

Added because PR #208's review graded its absence a [P1]: without a log the next
run has no stated baseline to diff against.

---

## 1. Test baseline

**Full suite at session start (this branch, off `main` at `90e65fe`): 3350 passed,
22 skipped, 126 deselected, 5 failed — and the 5 were my environment, not the
repository.** All five raise `FileNotFoundError` on
`data/mortality_tables/soa_vbt_2015_male_smoker.csv`; I had not run the documented
`scripts/convert_soa_tables.py --source pymort` step. After running it: **0
failures**.

The reviewer's own run reached 3492 passed / 0 failed, consistent with that.

This is the second time in one day the same omission cost a cycle — it also
produced a wrong baseline in the two 2026-08-22 logs. **Run the table-conversion
step before recording any baseline.**

## 2. What was built

`utils/measurement_provenance.py` (library), `scripts/measurement_stamp.py` (CLI),
one non-`continue-on-error` CI step, `RUNBOOK_measurement_provenance.md`, ADR-204.
Additive: no existing assertion touched, no core data contract touched, goldens
byte-identical.

**Nothing is stamped.** All six documents land unstamped and therefore warning, so
the gate is green on arrival. Stamping requires verification and verification is a
separate act.

## 3. Review round 1 — the finding that mattered

**[P1-1] the closure walker had a false-pass channel.** It resolved a dotted import
only as `pkg/name.py`, never as `pkg/name/__init__.py`, so
`from polaris_re.core import ReserveBasis` dropped `core/reserve_basis.py` and
everything below it. Reproduced on this checkout before fixing; the fix takes the
closure of a two-import probe from 6 files to 16, with `reserve_basis.py` appearing.
Mutation-verified: removing the package hop again fails the new test with
`assert 'beta.py' in {'producer.py'}` — the reviewer's own "closure of size 1".

This is exactly what ADR-204 decision 1 names as the failure that matters
(*"an unfollowed import is a false pass"*), and the original tests did not cover it:
the sibling case passes only because there the imported name *is* a module.
**The gate as landed was still sound for all six shipped documents** — the reviewer
checked every closure, and so did I — but the idiom is live in four test modules
here, so it was reachable.

**[P2-3] `git_head` was dead code** — computed and discarded. Now carried in the
stamp block. It is context, not identity: `check` compares the fingerprint, which
is content-addressed, so a stamp survives commits that do not touch the closure.
The sha exists so a reader auditing an `asserted` stamp can locate what the
operator was standing on. Older stamps without it still parse.

## 4. Perf history — no row, deliberately

`perf/history.jsonl` stands at **24 rows** and this PR appends none.

The review rated this [P2] and noted the series loses no signal, since the change
touches no engine code. I am leaving it that way rather than appending a row: the
harness measures engine hot paths, and a row generated here would record this
container's hardware against a change that cannot move any of those numbers —
adding noise to a series whose value is its comparability. **Flagged for the
maintainer** in case the convention is meant to be unconditional; it is a one-line
change if so.

Creep verdict on the existing series, measured: `insufficient_data=False`, no
structural creep, no wall-time creep.

## 5. Quality gate

- `ruff format` / `check` clean on `src/`, `tests/`, `scripts/measurement_stamp.py`.
- `mypy` clean on the new module.
- **23 R-free tests**, up from 20 after the review.
- CI green on `4d02841` (all 7 checks, including the Docker job the second commit
  fixed).
- Demonstrated end-to-end on the real repository — stamp, edit a module two hops
  away, `check` exits 1 — and reverted. **Not committed**: a stamp asserting a
  verification nobody performed is the defect ADR-204 exists to prevent.

## 6. Not closed

- **Six documents unstamped**, two of which need the experience cache
  (`RUNBOOK_measurement_provenance.md` §3 is written for a session that has it).
- **Merge ordering:** ADR-204 cites ADR-203, which lands with #207. If #208 merges
  first, `main` briefly carries a decision record whose premise is a dangling
  reference. Self-healing; flagged in both PRs.
- **The CI gate is a policy change** by design. ADR-204 argues the case; accepting
  it is the maintainer's call.
