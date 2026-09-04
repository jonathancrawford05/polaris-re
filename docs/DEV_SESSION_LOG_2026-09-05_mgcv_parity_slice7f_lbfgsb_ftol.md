# Session log — 2026-09-05 — Slice 7f: is the `ftol` exit the defect?

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7f — `docs/PLAN_mgcv_parity_engine.md`, registered by ADR-220.
**Branch:** `claude/slice-7f-lbfgsb-ftol`, cut from `origin/main` at `40f14d8`.
**ADR:** ADR-222.

**Gate reason:** maintainer direction, 2026-09-04 — *"can you open a new PR for
slice 7f?"* — after a sequencing discussion in which slice 7f was identified as
a **dependency of** the GAM production-wiring epic
(`docs/PLAN_gam_production_wiring.md` slice 3 says to use
`analytic_gradient=True` only once 7f resolves this, since a page that silently
reports a non-converged fit is worse than a slow one). A directed pick, not a
fallback one.

## Setup

- `uv sync --all-extras` — clean.
- Installed the tier-1 scratch oracle: `apt-get install -y -qq
  --no-install-recommends r-base-core r-cran-mgcv r-cran-jsonlite`.
  **R 4.3.3 (2024-02-29) / mgcv 1.9-1**, the routine's expected apt versions,
  no drift.
- Fixture regenerated with `scripts/gam_select_multiterm_free_sp_probe.R`
  (seed `20260902`, pinned — ADR-074).

## Baseline

`uv run pytest tests/ -q -p no:randomly`, `OPENBLAS_NUM_THREADS=1`, after the
pymort conversion: **3727 passed, 19 skipped, 0 failed** on `40f14d8` — the same
figure PR #227's session recorded on the same base, so this session starts from
a reproduced baseline rather than a quoted one. R-gated conformance tests RUN
this session (R installed), unlike that one.

## Gap Before

ADR-220 closed slice 7d with a defect it located but did not chase: a blind
single-start `select_lambdas_continuous` with the exact analytic gradient
reports `converged=True` at true `|grad| = 3.067`, and SciPy's message names
`CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH`. ADR-220 read that as an
`ftol` rule firing instead of the `gtol` the caller set, named three candidate
fixes, and tried none.

## Registered prediction (ADR-220's, carried into this slice)

*"Candidate 2 (restart after a detected `ftol` exit with an active bound)
closes the gap outright, because ADR-220's own warm-start reading shows the
true optimum IS reachable under this criterion; candidates 1 and 3 are
mitigations, not closures."*

## Hypotheses tried

### Pass 0 — reproduce before changing anything

Blind single-start, `analytic_gradient=True`: `nfev=42`, score `524.788031`,
`at_bound=True`, true `|grad| = 3.067233` — **bit-identical to ADR-220.**

### Pass 1 — is the residual even real? (the check ADR-220 asserted and did not show)

A large gradient at a bound-pinned block is not evidence of anything; only the
**projected** (KKT) residual distinguishes an early stop from a legitimate
corner. Built `gam_reml_optimize.projected_gradient` and measured:

| block | `log10(sp)` | at bound | grad | projected |
|---|---:|---|---:|---:|
| b1 | 12.0000 | UPPER | -0.001738 | 0.000000 |
| b3 | 12.0000 | UPPER | -0.000242 | 0.000000 |
| b5 | 3.6743 | — | 2.000544 | 2.000544 |
| b6 | 2.1513 | — | -2.086049 | -2.086049 |
| b7 | 0.2380 | — | 1.026619 | 1.026619 |

`max|g^P| = 2.086049` against `gtol = 1e-8`. **Verdict: the defect is real and
ADR-220's characterisation survives being checked** — the residual sits on FREE
blocks, and the bound-pinned ones contribute exactly zero.

### Pass 2 — candidate 1, a tighter `factr`

| `factr` | nfev | score change | `max|g^P|` |
|---|---:|---:|---:|
| 1e7 (default) | 4 | +0.000e+00 | 4.889e-01 |
| 1e2 | 4 | +0.000e+00 | 4.889e-01 |
| 1.0 | 4 | +0.000e+00 | 4.889e-01 |

**Verdict: REFUTED, and not marginally — identical in every column across seven
orders.** The relative reduction really is zero, so SciPy's message is honest
and the stopping rule is not the culprit. This is what redirected the slice.

### Pass 3 — candidate 2, restart; and what the plateau actually is

Implemented `max_gtol_restarts`. Score `524.788031 → 523.677681` (−1.110350),
residual `2.086 → 0.489` (4.3x), stopping after 2 restarts. Real, and not a
closure — so the plateau was interrogated rather than accepted:

Central differences along the worst free direction (b6) vs the analytic
`0.488915`, and a direct line probe along `-g^P`:

| h | central diff | | step `t` | change in score |
|---:|---:|---|---:|---|
| 1e-1 | 0.504087 | | 1e-1 | **-1.591e-02** |
| 1e-2 | 0.505886 | | 1e-2 | **-4.678e-03** |
| 1e-3 | 0.351933 | | 1e-3 | +5.217e-04 |
| 1e-4 | 1.615256 | | 1e-4 | +6.238e-04 |
| 1e-5 | **IRLS FAILED** | | 1e-5 | **IRLS FAILED** → `1e10` |

**Verdict: DECISIVE, and it is a different cause than the slice was registered
against.** The gradient is real (coarse central differences agree to ~3%) and
descent genuinely exists at `t = 1e-1`. But `penalized_irls_general` does not
converge at neighbouring points, so `_REJECTED_SCORE`'s flat `1e10` sits
exactly where L-BFGS-B's line search probes, against a true score of `~523.7`.
**No `factr` can fix a line search that is walled rather than mis-thresholded.**

Stopped at three passes per the routine's own guardrail.

## Gap After

**Not closed, and reported as not closed.** The residual falls from `2.086` to
`0.489` — worth having, and short of any noise floor. ADR-220's registered
prediction is **REFUTED**: the warm start reaches the optimum because it
*starts* there, which says nothing about walking to it through a region where
the objective cannot be evaluated. Re-aimed at the measured cause as slice 7g.

## The design decision that was made, measured, and reverted

Redefining `converged` as "`result.success` AND `gtol` met on the true
projected gradient" was built first — it is the obvious reading of the defect.
Measuring the well-conditioned N=4 control (ADR-212's fixture) killed it: the
restarted search plateaus there at `max|g^P| = 2.040e-04`, so the flag would
report a fit optimal to `1e-6` as **unconverged**. `gtol = 1e-8` is below what
this objective resolves anywhere.

Picking a threshold between `2e-04` and `4.9e-01` to make both cases read
correctly is tuning a number to make a check pass (Anchor 8), and setting an
acceptance threshold is "May not decide" besides. So `converged` keeps its
meaning, `max_abs_projected_gradient` carries the measurement, and the
threshold question is registered for the maintainer. **Same shape as slice 7c,
and recorded as a recurring pattern rather than re-derived a third time.**

## Provenance (ADR-193)

**This slice publishes no parity comparison and makes no `mgcv` comparison at
all.** Every reading is our own criterion, our own optimiser and our own inner
fitter; `mgcv` enters only as the generator of the fixture's recipe — the same
asymmetry `SELECT_FREE_SP_MODEL_CLAIM` already documents — never as an operand.
There is no second producer to name, so the ledger row carries
`MEASUREMENT (own criterion)` (ADR-219 amendment 1 decision 2's ratified
category), not a bare absence and not a borrowed parity label.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9-1 (local apt). **Tier 3 not owed** — no reading here
is a comparison against `mgcv`, so a pinned-oracle re-run would confirm nothing
about these numbers. The conformance CI job runs on the PR regardless.

## Quality gate

- `uv run ruff format src/ tests/` and `ruff check src/ tests/` — clean.
- `uv run pytest tests/test_analytics/test_gam_reml_optimize.py` — 40 passed
  (6 new closed-form `projected_gradient` tests, 6 new restart-wiring tests).
- Full suite (`OPENBLAS_NUM_THREADS=1`, `@slow` included, no deselection) —
  **3753 passed, 5 skipped, 0 failed** (920s). **Reconciles exactly against the
  baseline**: 3746 collected there (3727 + 19) against 3758 here (3753 + 5), a
  difference of exactly the 12 tests this slice adds; and the skips fall 19 → 5
  because R is installed this session, so 14 previously-skipped R-gated
  conformance tests RUN — and pass. `3727 + 12 + 14 = 3753`. **No new or
  changed failure, and a strictly larger set of tests actually exercised than
  the baseline run.**
- `tests/qa/golden_outputs/` byte-identical; `git diff` on that path empty.

## Definition of done

Recorded inline against each criterion in `PLAN_mgcv_parity_engine.md` slice
7f. **The first `[machine]` criterion is NOT MET and says so**; the
`[judgement]` criterion that governs that outcome ("if none of the three
candidates closes the gap outright, the session says so and characterises what
remains, rather than reporting a partial mitigation as a closure") is MET.

## Follow-ups filed

- **Slice 7g registered** — the inner IRLS's non-convergent neighbourhood and
  `_REJECTED_SCORE`'s cliff, with two directions and a registered prediction.
  *1st-order.*
- **Maintainer decision owed: what `converged` should test.** *1st-order,
  IMPORTANT.*
- **`projected_gradient` is independently useful** beyond this slice — any
  bounded search in this engine can now distinguish an early stop from a
  corner. *1st-order.*
- **The recurring "ill-posed tolerance" pattern**, now seen twice (slice 7c,
  slice 7f). *2nd-order — a methodological note, not a work item.*

All are in `PRODUCT_DIRECTION_2026-07-24.md` under `Harvested 2026-09-05`,
order-tagged. Nothing 3rd-order or deeper was promoted.
