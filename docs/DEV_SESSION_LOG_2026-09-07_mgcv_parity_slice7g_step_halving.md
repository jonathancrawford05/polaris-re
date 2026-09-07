# Session log — 2026-09-07 — Slice 7g direction 1: step-halving `penalized_irls_general`

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7g direction 1 — `docs/PLAN_mgcv_parity_engine.md`, registered by ADR-222,
re-scoped/promoted by ADR-222 amendment 1.
**Branch:** `claude/intelligent-hamilton-zh9su7`
**ADR:** ADR-224.

**Work selection:** the PLAN's next unchecked slice (no fallback pick) — slice 7h was
DONE as of the prior session (ADR-223); slice 7g direction 1 was the next open item,
explicitly promoted over direction 2 by ADR-222 amendment 1's re-scoping.

## Setup

- `uv sync --all-extras` — clean.
- Installed the tier-1 scratch oracle: `apt-get install -y -qq r-base-core
  r-cran-mgcv r-cran-jsonlite` (a fresh apt index refresh was needed first — the
  first attempt 404'd on stale package URLs). **R 4.3.3 (2024-02-29) / mgcv
  1.9.1** — the routine's expected apt versions, no drift.
- Mortality tables generated (`scripts/convert_soa_tables.py --source pymort`) —
  the routine's own noted one-time environment step.

## Baseline

`make test` (`OPENBLAS_NUM_THREADS=1`), before any change: **3640 passed, 3
skipped, 126 deselected, 0 failed** (506s). The initial raw run (before generating
mortality tables) showed 5 failures, all `FileNotFoundError` on missing SOA VBT
CSVs — the routine's own documented one-time environment step, not a code defect;
resolved by the table-generation step above, then re-confirmed clean.

## Gap Before

Tier-1 conformance suite (`Rscript scripts/mgcv_conformance.R` +
`compare_mgcv_conformance.py`), digest: local apt build, R 4.3.3 / mgcv 1.9.1,
exchange `78dc8914de78`:

```
level 1: AGREES     level 2: AGREES     level 3: AGREES
level 4: DISAGREES  level 5: AGREES
```

Matches `docs/CONTINUATION_mgcv_parity_engine.md`'s recorded status exactly — no
drift since ADR-223. Level 4's DISAGREES is ADR-190's permanent, expected reading
(the shipped legacy engine is not re-pointed, per ADR-207 decision 3).

**Slice 7g's own gap, measured fresh on the current (post-ADR-223) codebase** — the
prior session's own ADR-222 numbers predate slice 7h's sum-of-squares fix, so they
are not directly comparable; a fresh baseline was taken rather than assumed:

Fixture: `scripts/gam_select_multiterm_free_sp_probe.R` (seed `20260902`, pinned,
ADR-074), the same `select=TRUE` N=7 three-term structure ADR-217/218/222
measured. Blind single-start, `analytic_gradient=True`, no restarts: `nfev=43`,
`score=524.313836582247`. With `max_gtol_restarts=4` (ADR-222's own partial
mitigation): `nfev=94`, `score=523.6569217612956`, `n_gtol_restarts=2`,
`max_abs_projected_gradient=0.049335` (already ~10x tighter than ADR-222's own
pre-7h `4.889e-01` reading — slice 7h's own criterion fix had a side benefit here
too, not investigated further). Central-difference probe along the worst free
block (index 6) around that plateau: `h=1e-1` (`+` direction) and `h=1e-5` (`-`
direction) both raise `PolarisComputationError` from `penalized_irls_general` —
the exact non-convergent-neighbourhood mechanism ADR-222 named, reproduced fresh.

## Hypotheses tried

### Pass 1 — gate step-halving on raw deviance (mirrors the most literal reading of `mgcv.half`)

**Hypothesis:** halving a Newton step whenever it makes the DEVIANCE worse (or
non-finite) than the previous iteration's, up to 30 times, closes the
non-convergent neighbourhood.

**Result:** fixes the N=7 case cleanly, but breaks
`tests/test_analytics/test_gam_family.py::TestPoissonReducesToTheVerifiedRecursion::test_matches_experience_gam_penalized_with_a_real_penalty`
— coefficients land `0.0089` from the already-verified answer. Root cause,
confirmed independently via `scipy.optimize.minimize` on `deviance +
coef'Scoef`: a legitimate Newton step can trade a small penalty increase for a
larger deviance decrease, net-IMPROVING the true (penalized) objective while raw
deviance goes up — this halving fights that trade-off and lands on a genuinely
worse point. **REJECTED** — verified off the true optimum, not merely different
from it.

### Pass 2 — gate on the penalized objective, but exit the halving loop at the SAME tight tolerance the outer convergence check uses

**Hypothesis:** gating on `deviance + coef'Scoef` instead of deviance alone fixes
Pass 1's defect.

**Result:** fixes the closed-form fixture, but on the SAME N=7 case the halving
loop collapses to a no-op: repeated halving shrinks the step toward zero, and an
unchanging point trivially satisfies a tight absolute tolerance — 30 halvings
later, "converged" at a point measurably away from the true fixed point (the
SAME symptom as Pass 1, a different mechanism: an artificially-shrunk step
satisfying a criterion meant to certify a genuine one). **REJECTED**, traced by
instrumenting the per-iteration halving count and deviance trajectory directly.

### Pass 3 — separate the halving loop's own exit test from the outer convergence tolerance (matches `glm.fit`'s own structure)

**Hypothesis:** the halving loop should exit as soon as the step is "not worse
than where this iteration started" (`new_objective <= previous_objective`, no
tolerance), decoupled from the much tighter test that decides whether the WHOLE
outer iteration has converged.

**Result:** closes both defects. The N=7 fixture's own previously-failing
central-difference neighbours now converge; the well-conditioned closed-form
fixture (Pass 1's casualty) reproduces its exact pre-existing answer once more.
**ACCEPTED — shipped as `penalized_irls_general(step_halving=True)`.**

Even with the correct mechanism, a full test-suite run (before committing to a
design) surfaced that ENABLING it unconditionally still perturbs several other
already-verified fixtures at the `1e-6` to `1e-8` level
(`test_gam_derivatives.py`'s two derivative-vs-central-difference tests,
`TestFiniteDiffStep`) — the mechanism: even a *correct* halving takes a
*different* iteration count to reach an identical fixed point, and those tests
resolve the fitted surface finely enough to be sensitive to that. **Decision:
ship as opt-in** (`step_halving: bool = False`, default unchanged for every
existing caller) rather than loosen those tests' tolerances (CLAUDE.md: "NEVER
change an existing test assertion to make it pass").

## Gap After

**The mechanism ADR-222 named is closed.** Both previously-failing
central-difference neighbours converge with `step_halving=True` (8-9 IRLS
iterations), and still fail without it (confirmed — the opt-in default is pinned
by a test, not merely asserted). Restart plateau's own KKT residual:
`0.049335 -> 0.001125` (~44x), with `n_gtol_restarts` unchanged at 4.

**The eta/edf-vs-`mgcv` gate (`SELECT_FREE_SP_MODEL_CLAIM`) does NOT improve, and
for single-start WORSENS** — the session's own most important finding, reported
as such rather than folded into the mechanism's own good news:

| search | step_halving | nfev | max abs eta diff | agrees (eta/edf) |
|---|---|---:|---:|---|
| single-start, FD | off | 352 | 4.461e-01 | False |
| single-start, FD | **on** | 312 | **5.678e-01** | False |
| single-start, analytic | off | 43 | 6.319e-02 | False |
| single-start, analytic | **on** | 31 | **4.460e-01** | False |
| multistart(9), FD | off | 3424 | 5.470e-03 | True |
| multistart(9), FD | **on** | 6056 | 5.228e-03 | True |
| multistart(9), analytic | off | 481 | 5.449e-03 | True |
| multistart(9), analytic | **on** | 552 | 5.446e-03 | True |

`step_halving` reliably reaches a genuine KKT stationary point, but on this
non-convex, multi-modal criterion (`select=TRUE`'s null-space penalty adds
exactly this structure) that is not necessarily the point closest to `mgcv`'s
own selection — the un-halved single-start path's own non-monotone wandering
apparently sometimes lands nearer it by luck. Multistart (the production
recommendation, ADR-218) is unaffected either way.

`FREE_SP_MODEL_CLAIM` (N=4 control, non-`select`): `max_abs_eta_diff` `8.444e-04
-> 2.306e-03`, `edf_total_diff` `-0.0171 -> 0.0627` — both tiny, consistent with
this block's own already-established weak identifiability (ADR-212), not a new
defect.

## Provenance (ADR-193 / VERIFICATION_STANDARD.md §2.1)

Two distinct claims this session reports, kept separate rather than averaged:

- **The KKT-residual and non-convergent-neighbourhood readings**
  (`MEASUREMENT (own criterion)`): every number is Polaris's own criterion, own
  optimiser and own inner fitter, measured against itself before/after this
  change. No `mgcv` quantity is an operand anywhere in these readings.
- **The `SELECT_FREE_SP_MODEL_CLAIM`/`FREE_SP_MODEL_CLAIM` re-measurements**
  (`INDEPENDENT`, pre-existing claims from ADR-217/ADR-221/ADR-212): both sides
  independently select all smoothing parameters from the same recipe; re-run
  because this change touches a shared inner solver both producers' fitters
  call — verdict for multistart UNCHANGED (still agrees); verdict for
  single-start UNCHANGED (still does not agree) but the margin WORSENED.

## Oracle version

Tier 1 only: R 4.3.3 / mgcv 1.9-1 (local apt). **Tier 3 not owed for the
mechanism readings** — no `mgcv` quantity is an operand there, so a pinned-oracle
re-run would confirm nothing about them (same reasoning ADR-222's own slice 7f
addendum used). Tier 3 IS owed, and was run, for the required conformance levels
1-5 (unaffected — this change is opt-in and the ten-cell suite never sets
`step_halving=True`) and is registered as a follow-up dispatch for the
`SELECT_FREE_SP_MODEL_CLAIM`/`FREE_SP_MODEL_CLAIM` re-measurement tables (a CI
round trip, ~1 minute, per the routine's own budget).

## Quality gate

- `uv run ruff format src/ tests/` / `ruff check src/ tests/ --fix` — clean on
  every file this session touched.
- `uv run pytest tests/ -m "not slow"` — **3646 passed, 3 skipped, 126
  deselected, 0 failed** (537s). Reconciles exactly against baseline: +6 tests
  (`TestStepHalvingOnAnExtremeLambdaSpread`'s new cases), 0 change in skip/fail
  counts.
- `uv run pytest tests/qa/` — 94 passed. `tests/qa/golden_outputs/` byte-identical
  (`git diff` empty) — expected, no golden exercises `step_halving=True`.
- Conformance suite re-run (tier 1) after the change: identical verdict to Gap
  Before (levels 1-3, 5 AGREE; level 4 DISAGREES, unchanged) — the ten-cell suite
  never sets the new opt-in parameter, so this is the expected null result,
  confirmed rather than assumed.

## Definition of Done (PLAN slice 7g direction 1, verbatim, per ADR-209 decision 3)

- `[machine]` MET. Stall's KKT residual on the same N=7 case, re-measured:
  `0.049335 -> 0.001125` (~44x). Direction taken: direction 1 (`step_halving`).
- `[machine]` MET. N=4 control's score/residual re-measured before/after:
  `612.6100526 -> 612.6132599` (`+0.0032`); `max_abs_eta_diff` (vs `mgcv`)
  `8.444e-04 -> 2.306e-03` — both reported, neither hidden.
- `[machine]` MET. `tests/qa/golden_outputs/` byte-identical.
- `[judgement]` MET, restated for what was actually found: the residual DID move
  materially (satisfying the `[machine]` bar), but the eta/edf-vs-`mgcv` gate
  did not improve — and for single-start, worsened. Reported as a real, narrow
  fix with a real, named limitation, not oversold as progress toward parity.

## What was NOT done

- Direction 2 (`_REJECTED_SCORE` as a growing barrier) — not attempted. Direction
  1 alone met the DoD, and the PLAN's own text reserves direction 2 for "if
  slice 8 is deferred."
- Default-on step-halving — measured and explicitly rejected (see Pass 3's own
  quality-gate finding above); this is a derived scope decision, not a
  shortcut.
- No re-derivation of the outer solver (slice 8, still the Wood-shaped Newton
  replacement) — this slice's own finding (reliable convergence ≠ convergence to
  `mgcv`'s own basin, on a multi-modal criterion) is carried forward as a named
  consequence for that slice's design, not solved here.

## Follow-ups filed

- **Slice 8's own design should account for this session's finding**: a robust
  inner/outer solver reaching SOME stationary point reliably is not the same
  problem as reaching the one nearest `mgcv`'s own selection on a multi-modal
  criterion. *1st-order — direct input to an already-planned slice.*
- **Whether `step_halving` is worth combining with multistart in production**:
  measured no benefit and roughly 2x cost on the FD path; not recommended as
  currently configured, but not filed as a blocking decision since
  `multistart=True` alone already meets the gate. *3rd-order — parked, revisit
  only if slice 8 changes the underlying trade-off.*
- **Tier-3 confirmation of the `SELECT_FREE_SP_MODEL_CLAIM`/`FREE_SP_MODEL_CLAIM`
  re-measurement tables** — registered, not yet dispatched as of this log; a
  CI round trip is affordable per the routine's own budget. *1st-order,
  direct follow-through on this slice's own claim.*

Harvested into `docs/PRODUCT_DIRECTION_2026-07-24.md`, order-tagged as above.
