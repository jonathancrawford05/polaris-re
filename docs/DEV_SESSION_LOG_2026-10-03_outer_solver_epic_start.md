# Dev session log — 2026-10-03 — outer-solver epic start (slice 0: barrier or early stop?)

**Branch:** `claude/zen-einstein-kcjntj`, based on PR #249's head
(`claude/intelligent-hamilton-6m31s5` @ `34f1809`), so it merges cleanly once #249 does.
**PR title class:** `diag(mgcv-parity)` — lands a `MEASUREMENT (own criterion)` probe and an
epic plan; no parity comparison, no `src/` change.
**Trigger:** interactive maintainer direction after the PR #249 review: *"clearly we are
spiralling … do what you can to get us out of this loop and on track for the complete outer
solver parity."*

## Claim sentence (written before the code)
Not a comparison. `MEASUREMENT (own criterion)` (VERIFICATION_STANDARD §2.1): Polaris's own
free-scale REML score evaluated along the segment from Polaris's stopping point to `mgcv`'s
`sp`, plus a central-difference gradient at the stop and the search's first move. `mgcv`'s
`sp` is only the point of evaluation; remove `mgcv` and every number still exists for any
endpoint.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt), `OPENBLAS_NUM_THREADS=1`. Tier 2: unavailable.
Tier 3: R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 37091438628 — identical to tier 1 at every printed digit except the gradient at `mgcv`'s point (fifth significant figure). `gam.control()$newton` constants read at tier 1 only.

## Baseline
`pytest tests/` (slow included, no R at the time, tables converted) on PR #249's head:
3965 passed, 37 skipped, 0 failed; `tests/qa/` 94 passed. This PR adds 6 tests and no
`src/` change.

## Gap Before
ADR-240: the `initial.spg` seed disagrees on gaussian L1 (`eta` 0.2107); the bounds-centre
start disagrees on the 3c draw (`eta` 0.2864). Mechanism unknown; ADR-239 called the 3c stop
"a worse stationary point of the same criterion".

## Hypotheses Tried
1. *The disagreements are separate basins (a barrier between our stop and `mgcv`'s point).*
   **REFUTED on 3c** (monotone descent, no barrier, gradient up to ~2/decade at the stop);
   **weak on L1** (0.158 rise on a 15.5 descent along a straight segment).
2. *The search, not the start, is the defect.* **HELD (tier 1 and tier 3 — ADR-241), as two
   defects.** L1: the first L-BFGS-B step from the `initial.spg` seed is 11.8 decades and is
   ACCEPTED (two blocks onto the upper bound). 3c: the first 7.0-decade trial is REJECTED (first
   accepted step 1.47 decades), and the search stops on the `factr` function-reduction test with
   the gradient still ~2/decade. Both cells exit on that test. (The first version of this entry
   read the first TRIAL point as the move and attributed both to overshoot; PR #250's review
   caught it, and the accepted-iterate trace corrected 3c.)
3. ADR-239's "worse stationary point" wording for 3c: **REFUTED** — the stop is not
   stationary.

## Gap After
Unchanged by design: this session changes no solver. It changes what the next slices are.

## Provenance
| reading | producer | role of `mgcv` | class |
|---|---|---|---|
| own score along segment, gradient at stop, first move | `penalized_fit_and_score` / `fit_polaris_gam` | `sp` = point of evaluation only | `MEASUREMENT (own criterion)` |
No INDEPENDENT, ECHO or TRANSPORT columns; nothing here is parity evidence.

## Process change (the point of this PR)
- `docs/PLAN_wood_outer_solver.md` + CONTINUATION: parity slice 8 promoted to the active epic.
- `docs/ROUTINE_MGCV_PARITY.md`: active-epic pointer; new step 10 "MECHANISM BEFORE SLICE"
  (outer-search gaps become gauntlet cases, never new start-strategy slices; chain cap;
  older structural beats newer patch).
- Ladder: yields; 7c SUPERSEDED. 3e/3f were already closed by the maintainer's ruling
  (option (c), ADR-240 amendment 1, merged with #249).

## Decomposition Plan
| slice | status |
|---|---|
| 0 diagnose | DONE (this PR) |
| 1 free-scale gradient + safeguarded Newton | NEXT |
| 2 exact Hessian | registered |
| 3 §3.1 reparameterisation | registered |
| 4 surface + gauntlet | registered |

## Perf History
No row: this PR modifies nothing under `src/polaris_re/` (ADR-177 amendment 1).

## Follow-ups
Harvested into `PRODUCT_DIRECTION_2026-07-24.md` (2026-10-03 section): the epic itself
(1st-order, from parity slice 8) and a 2nd-order tier-3 re-read of `gam.control()$newton`.

## PR #250 review response
- **[P1] trial point vs accepted iterate — fixed by measurement, not by softening.** The probe
  now records accepted iterates (wrapping `gam_reml_optimize.minimize` with a `callback`) and
  SciPy's exit message. Result: the reviewer was right about 3c (trial rejected; the defect is
  the stopping rule), and the L1 reading stands (trial accepted). ADR-241 finding 3, PLAN §1,
  the ledger row, both CONTINUATIONs and slice 1's DoD (accepted steps capped AND a
  gradient-based exit) are corrected.
- **[P2] `n_at_lower`** — added, with a test.
- **[P2] ROUTINE header** — the active-epic pointer moved below `**Created:**`; `**Plan:**`
  now names the active epic and keeps the parity PLAN as the parent.
- Merged `origin/main` (#249 + ADR-240 amendment 1): amendment 1 is now the record of the 3f
  ruling; ADR-241 cites it rather than re-deciding it, and 7c alone is SUPERSEDED here.
