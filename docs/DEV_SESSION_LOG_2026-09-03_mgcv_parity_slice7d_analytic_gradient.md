# Session log — 2026-09-03 — Slice 7d: the analytic REML gradient

**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (scheduled).
**Slice:** 7d — `docs/PLAN_mgcv_parity_engine.md`. Registered by slice 7c
(ADR-219), carrying forward slice 7c's own withdrawn Part 1.
**PR:** this session's designated branch (`claude/intelligent-hamilton-lb1rb2`).
**ADR:** ADR-220.

## Setup

- `uv sync --all-extras` — clean (one new dependency resolved,
  `statsmodels`'s own transitive extras; no version conflicts).
- Installed the tier-1 scratch oracle: `apt-get update -qq && apt-get
  install -y -qq r-base-core r-cran-mgcv r-cran-jsonlite` (the first attempt,
  without `apt-get update`, hit stale-mirror 404s on unrelated desktop
  packages the default install pulls in — `apt-get update` first fixed it,
  no `--no-install-recommends` needed this session). **R 4.3.3 (2024-02-29) /
  mgcv 1.9.1** — matches the routine's expected apt versions, no drift.
- Read `ROUTINE_MGCV_PARITY.md`, `VERIFICATION_STANDARD.md` in full;
  `PLAN_mgcv_parity_engine.md` slices 7b/7c/7d in full; `CONTINUATION_
  mgcv_parity_engine.md`'s status block and open questions; `CLAUDE.md`;
  `docs/DECISIONS.md` ADR-189/190/193/196/201/202/207/208/210/211/212/217/
  218/219 (+ amendments); `gam_derivatives.py`, `gam_reml.py`,
  `gam_reml_appendix_b.py`, `gam_reml_optimize.py`, `gam_family.py`,
  `gam_fit.py` source.

## Baseline

`OPENBLAS_NUM_THREADS` unset (this container's default thread count),
before any change:

```
uv run pytest tests/ -q -m "not slow"
8 failed, 3586 passed, 22 skipped, 126 deselected
```

Re-run with `OPENBLAS_NUM_THREADS=1` pinned (this epic's own standing
convention for the free-`sp` search, ADR-211/213):

```
6 failed, 3588 passed, 22 skipped, 126 deselected
```

**All 6 remaining failures are pre-existing, verified by reproducing them on
`git stash` (this session's changes absent), not assumed:**

- `test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface` and
  4 cases in `test_synthetic_block.py::TestCalibratedPremiums` — missing
  `data/mortality_tables/*.csv` (CLAUDE.md §11: generated per-environment,
  never committed; this session did not run
  `scripts/convert_soa_tables.py`, since nothing in slice 7d's own scope
  touches mortality tables). Reproduces identically on the unmodified base.
- `test_gam_model_conformance.py::test_the_r_probe_runs_end_to_end` — the
  **already-filed** `OPENBLAS_NUM_THREADS` sensitivity
  (`docs/PRODUCT_DIRECTION_2026-07-24.md`'s own harvested follow-up, from
  slice 7c's baseline session): fails with threads unset, passes pinned, on
  both the unmodified base and this branch, to the same printed digits.

**One failure this session's own change caused, and it was fixed in this
session rather than left standing:**
`test_measurement_provenance.py::test_check_passes_on_the_current_repository`
— `docs/MEASUREMENT_unconditional_coverage.md`'s stamp drifted because
`gam_derivatives.py`/`gam_reml_appendix_b.py` sit in
`scripts/unconditional_coverage_study.py`'s transitive import closure
(through `gam_uncertainty_mi` → `gam_uncertainty`), and this session added
functions to both — an **inert edit** in the sense
`CONTINUATION_mgcv_parity_engine.md`'s own open question describes (nothing
this session touched is on the path `unconditional_coverage_study.py`
actually executes), but the stamp schema has no way to say that, so the
honest fix is to actually re-run the measurement rather than assert
inertness. Re-ran `scripts/measurement_stamp.py stamp
docs/MEASUREMENT_unconditional_coverage.md --run` for real (~5 minutes) —
`age-flat: conditional 0.7435, unconditional 0.7815`; `age-varying:
conditional 0.7781, unconditional 0.8090` — **unchanged to the printed
digit** against the previously-committed figures, confirming the edit
really was inert. `scripts/measurement_stamp.py check` now reports `0
drifted`. Full suite re-run clean afterward:

```
uv run pytest tests/ -q -m "not slow"   (OPENBLAS_NUM_THREADS=1)
5 failed, 3589 passed, 22 skipped, 126 deselected
```

The 5 remaining failures are exactly the pre-existing mortality-table-CSV
gap above — nothing else.

**One test this session's own change required updating, mechanically, not a
regression:** `test_gam_select_free_sp_conformance.py::test_fit_select_free_
sp_case_signature_takes_no_r_fit_output` asserted the exact parameter set of
`fit_select_free_sp_case`; adding `analytic_gradient` (see below) is exactly
the kind of signature change that test exists to catch, and the fix is
widening the asserted set, not loosening the check.

With those accounted for, no new failure and no regression against the last
parity session's own baseline.

## Gap Before

Slice 7c (ADR-219, tier 1 AND tier 3 confirmed) established, before any code
in this session ran: on the `select=TRUE` 7-block structure, 2 of 7 `rho`
directions carry curvature indistinguishable from zero at `mgcv`'s own
point, so the committed `max_abs_log10_sp_diff < 1e-2` gate is unreachable in
principle on those two directions. What remains real and closable, carried
into slice 7d as its own registered scope:

- the **`0.0141` score gap** on the 5 identified directions (warm-starting
  our own search at `mgcv`'s point reaches a score `0.0141` BETTER, under
  our own criterion, than best-of-9 blind multistart reaches) — tier 3, CI
  run 33458654272;
- the **`converged=False`-at-a-near-zero-gradient contradiction** ADR-218
  recorded, traced (ADR-212's own mechanism, one level up) to SciPy's
  forward-difference gradient sitting inside this objective's own noise
  floor when no `jac=` is supplied.

Neither of those numbers is `max_abs_log10_sp_diff` — slice 7c's own DoD
states explicitly that this metric is not this slice's success criterion.

## Registered prediction (written before any measurement, PLAN slice 7c
Part 1, carried verbatim into slice 7d)

> The analytic gradient closes the score gap on the identified directions to
> at or below the objective's own noise floor (blind multistart reaches what
> the warm start reaches, and `converged` stops disagreeing with a
> near-zero gradient), but `max_abs_log10_sp_diff` stays O(1) because the
> direction is not identified.

## The cheap check (PLAN slice 7c/7d's own precondition, run FIRST)

Before deriving `d(alpha)/d(eta)`: is the `dW/drho` term negligible at all,
on a well-conditioned point? Measured on
`tests/fixtures/gam_reml_optimize_near_flat_direction.json` (the N=4,
`n=900` fixture, committed synthetic data, no `mgcv` involved in this
check — pure Python self-consistency) at `select_lambdas_continuous`'s own
production-converged point (default finite-difference search,
`OPENBLAS_NUM_THREADS=1`):

- Analytic gradient with terms 1/2/4 only (`dW/drho` OMITTED entirely) vs a
  trustworthy `h=1e-3` central difference of the profile score (refitting at
  every perturbed point, the same central-difference discipline
  `TestFiniteDiffStep` already established as reliable there,
  `norm(grad) < 0.05`): **max abs diff ≈ 0.0199** (block 1) — an order of
  magnitude above that established noise floor.
- **Verdict: the cheap check FAILS. The term is not negligible.**
  `d(alpha)/d(eta)` needed deriving — not skippable.

## Hypotheses tried

1. **Hypothesis: `d(alpha)/d(eta)` (Wood Appendix D in full, not the
   `alpha ≡ 1` Fisher special case `dw_deta` already implements) closes the
   gap the cheap check found.**

   **The one change:** derived and verified, analytically, each checked
   against a central difference of the function one order below it
   (`atol` `1e-6`–`1e-10`, all three link/family combinations this codebase
   defines) BEFORE composing any of them into the next:
   - `third_deriv_mu_eta` (`d³μ/dη³`, one link — `log`/`logit`/`cloglog` —
     each a two-line closed form derived from `second_deriv_mu_eta`'s own,
     not guessed);
   - `variance_second_deriv` (`d²V/dμ²`; `0` for Poisson, `-2` for
     binomial);
   - `dalpha_deta` (the product-rule combination, `-m·B + (y-μ)·dB/dη`);
   - `dw_deta_observed`/`dw_drho_observed` (the full Appendix D chain,
     `alpha` included, vs `dw_deta`/`dw_drho`'s own `alpha ≡ 1` case).

   `gam_reml_gradient.reml_score_gradient` assembles all four terms of
   Wood (2011) §2 eq. (4) differentiated w.r.t. natural-log `rho`:
   envelope-theorem term (`λⱼβ̂ᵀSⱼβ̂/2γ`), `0.5·tr(H⁻¹λⱼSⱼ)`,
   `0.5·tr(H⁻¹Xᵀ(dW/drhoⱼ)X)` (now exact, via `dw_drho_observed`), and
   `-0.5·λⱼ·tr(S⁺Sⱼ)` — the last via a NEW
   `gam_reml_appendix_b.dlogdet_s_plus_drho`, which reads the pseudoinverse
   `S⁺` off Appendix B's own already-robust `E` (`EᵀE = S`, economy SVD)
   rather than eigendecomposing the raw badly-scaled sum (the exact failure
   mode Appendix B exists to avoid, Defect A) — verified against a central
   difference of `logdet_s_plus` on both a well-scaled and a 10-decade
   badly-scaled/rank-deficient case (`atol` `1e-6`/`1e-5`).

   **Re-measure, same fixture and point:** the SAME cheap check, now with
   the exact `dW/drho` term included: **max abs diff ≈ 1.3e-5–1.9e-5** —
   below the central-difference noise floor by three orders of magnitude,
   at the SAME point that showed `0.02` before. A second, well-conditioned
   interior point (`log10(lambda) = [2, 1.5, 3, 4]`, no near-flat block)
   agrees to `~1e-6`.

   **Verdict: HOLDS, decisively.** Every function verified individually
   before composition; `reml_score_gradient` itself is checked against a
   central difference of the profile score (refitting at each perturbed
   point — NOT differencing the score at fixed `coef`, which was tried
   first in the test suite and found to compute a different, partial
   quantity that omits `dW/drho` by construction, since holding `coef`
   fixed makes `W` independent of `rho`; see
   `tests/test_analytics/test_gam_reml_gradient.py`'s own
   `_central_difference_gradient` docstring) on three further fixtures
   (two-block disjoint support × 3 families, a badly-scaled three-block
   case, one with an offset and `gamma ≠ 1`) — all pass at `atol`
   `1e-4`–`2e-3`.

2. **Wired the exact gradient into the production search.**
   `select_lambdas_continuous(analytic_gradient=True)` passes
   `reml_score_gradient` to `scipy.optimize.minimize` via its `jac=True`
   combined-objective protocol (one fit produces both the score and the
   gradient — `penalized_fit_score_and_gradient`, new) instead of SciPy's
   own forward-difference estimate. Opt-in, default `False`: every existing
   caller (`select_lambdas_continuous_multistart`, `fit_polaris_gam`,
   `fit_select_free_sp_case`) gained the SAME opt-in parameter, threaded
   through unchanged, and a wiring test
   (`test_the_eps_option_reaches_scipy_minimize`'s own pattern) pins that a
   future refactor cannot silently drop it.

   **Measured on the N=4 fixture (own-criterion, no `mgcv` anywhere):**
   single-start `analytic_gradient=True` reaches REML score `612.610032` in
   20 function evaluations, against the finite-difference default's
   `612.610092` in 120 — a BETTER score at 6x fewer evaluations, on the
   exact fixture ADR-211/212 built the finite-difference-step fix for.

   **Measured on the `select=TRUE` N=7 fixture — tier 1 (R 4.3.3/mgcv
   1.9-1), a fresh draw via `scripts/gam_select_multiterm_free_sp_probe.R`
   (its own seed, `n=900`; `mgcv`'s own selection: `sp = [1.979e10,
   0.06994, 5.065e11, 53870, 2349, 491.1, 0.7706]`):**

   | search | total nfev | REML score | score gap vs `mgcv` | `max abs eta diff` | `edf_total diff` | `max abs log10(sp) diff` | converged | true `\|grad\|` |
   |---|---:|---:|---:|---:|---:|---:|---|---:|
   | single-start, finite-difference (default) | 312 | 529.604861 | +5.9595 | 0.4456 | +2.4216 | 5.1320 | True | 0.0625 |
   | single-start, analytic gradient | 42 | 524.788031 | +1.1427 | 0.0529 | +0.1904 | 1.7036 | True | 3.0672 |
   | multistart(9), finite-difference | 4600 | 523.659400 | +0.0141 | 0.0027 | -0.1106 | 1.4754 | True | 0.0405 |
   | multistart(9), analytic gradient | 549 | 523.663316 | +0.0180 | 0.0055 | -0.2583 | 5.1929 | True | 0.0150 |
   | warm-start at `mgcv`'s point, analytic gradient (TRANSPORT) | 7 | 523.645314 | -0.0002 | — | — | 0.0010 | True | 0.0014 |

   (`mgcv`'s own REML score at its selection: `523.645336`.)

   **Verdict, both clauses of the registered prediction:**
   - *"Closes the score gap on the identified directions to at or below the
     objective's own noise floor":* **HOLDS**, via the warm start
     (`523.645314` vs `mgcv`'s `523.645336` — the tightest reading this
     epic has produced on this structure, `max abs log10(sp) diff = 0.0010`)
     and via `multistart(9), analytic gradient` reaching essentially the
     same score gap as the finite-difference default (`0.0180` vs `0.0141`)
     at **8.4x fewer function evaluations** (549 vs 4600) — the "gradient
     cost drops from ~8 solves to ~1" consequence the slice named in
     advance, now measured rather than assumed.
   - *"`converged` stops disagreeing with a near-zero gradient":*
     **REFUTED, by a NEW mechanism, not the one hypothesised.** The blind
     single-start analytic-gradient run reports `converged=True` at a point
     whose TRUE gradient (the exact one, not a finite-difference estimate —
     the SAME function SciPy received as `jac=`) has norm `3.067` on
     directions that are NOT at a search bound. SciPy's own `message`:
     `CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH` — an
     **`ftol`-style stopping rule**, not the `gtol` this caller set.
     Two of the seven blocks (`s(AttdAge)`, `ti(...)`'s own existing block)
     are pinned at the search's upper bound (`12.0`,
     `PRODUCTION_LOG10_BOUNDS`) at this point; L-BFGS-B's line search
     appears to stall near that bound-active corner and exits on function
     tolerance while three of the free directions still carry a large
     residual gradient. This is a DIFFERENT defect from ADR-212's
     finite-difference-noise mechanism (that one supplied a noisy gradient
     estimate near a genuine optimum; this one supplies the EXACT gradient
     and the optimiser still exits early, for a reason internal to its own
     bound handling) — filed below, not chased further this session (its
     own three-pass discipline: this is pass one, and it already
     demonstrates BOTH that the exact gradient is correct — verified
     independently at that exact point, central difference on the free
     blocks agrees to `~0.01`, see "Provenance" — and that a NEW,
     precisely-located defect remains).

## Provenance

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| N=4 cheap-check gradient (with/without `dW/drho`) | `gam_reml_gradient.reml_score_gradient` | a central difference of `gam_reml.reml_score_general`, refitting at each perturbed point (this engine's own function, differenced) | `MEASUREMENT (own criterion)` — no `mgcv` value anywhere in this check; `docs/VERIFICATION_STANDARD.md` §2.1 |
| `third_deriv_mu_eta`/`variance_second_deriv`/`dalpha_deta`/`dw_deta_observed` (unit tests) | each analytic closed form | a central difference of the function one order below it (this engine's own) | `MEASUREMENT (own criterion)` |
| `dlogdet_s_plus_drho` | `gam_reml_appendix_b.dlogdet_s_plus_drho` | a central difference of `gam_reml_appendix_b.logdet_s_plus` (this engine's own) | `MEASUREMENT (own criterion)` |
| `eta`/`log10(sp)`/`edf_total`/per-term `edf` (single/multistart, FD and analytic rows) | `gam_select_free_sp_conformance.fit_select_free_sp_case` (with/without `analytic_gradient=True` — same producer, new parameter) | `mgcv gam(select=TRUE, method='REML')`, `scripts/gam_select_multiterm_free_sp_probe.R` | **INDEPENDENT** — unchanged from `SELECT_FREE_SP_MODEL_CLAIM` (ADR-218/219); `analytic_gradient` does not change which side computes what, so no new `VerificationClaim` was needed (the ADR-193 mechanical test is on the function SIGNATURE, unaffected by this parameter) |
| warm-start row (`log10(sp)`, score) | `select_lambdas_continuous(x0=mgcv's own log10(sp), analytic_gradient=True)` | `mgcv`'s own selection (the SAME values supplied as `x0`) | **TRANSPORT** — the mechanical test fails on sight (the input includes the other side's own output); same status as `gam_select_free_sp_warmstart_diagnostic.py`'s own `WARM_START_CLAIM`; never a parity claim |
| blind single-start's true-gradient-norm-vs-`converged` finding | `reml_score_gradient` evaluated at SciPy's own reported minimum | nothing — a property of our own optimiser's behaviour | `MEASUREMENT (own criterion)`; `mgcv` does not appear in this reading at all |
| `docs/MEASUREMENT_unconditional_coverage.md` re-stamp | `scripts/unconditional_coverage_study.py`, re-run for real this session | its own prior committed figures | regression check on THIS engine's own numbers (goldens detect change, not correctness — `ROUTINE_MGCV_PARITY.md`'s own never-list) — unchanged to the printed digit, see below |

**Everything against `mgcv` in this session (the `SELECT_FREE_SP_MODEL_CLAIM`
table) is TIER 1 ONLY (R 4.3.3 / mgcv 1.9-1, local apt) — not citable outside
this session log until a tier-3 dispatch confirms it, per
`ROUTINE_MGCV_PARITY.md` step 2.** The N=4 fixture's own numbers and every
unit-level derivative check involve no `mgcv` comparison and carry no tier
label at all (`MEASUREMENT (own criterion)`, self-contained Python).

## Oracle version

Tier 1: R 4.3.3 (2024-02-29) / mgcv 1.9.1, local apt install, this
container. Tier 3: see the PR/ADR once dispatched (this session's own
`workflow_dispatch` — recorded there, not duplicated here to avoid a stale
copy).

## Quality gate

- `uv run ruff format src/ tests/ scripts/` — 3 files reformatted (my own
  new/edited files; nothing pre-existing touched).
- `uv run ruff check src/ tests/ scripts/ --fix` — clean on every file this
  session touched (one `RUF002` ambiguous-apostrophe fix in a new
  docstring); the 13 remaining findings are pre-existing, in files this
  session did not touch (`scripts/train_ml_assumptions.py`,
  `scripts/validate_tables.py`).
- `uv run pytest tests/ -q -m "not slow"` (`OPENBLAS_NUM_THREADS=1`) — final
  clean run: **5 failed (all pre-existing, missing mortality-table CSVs),
  3589 passed, 22 skipped, 126 deselected.** 0 new failures; the
  `test_measurement_provenance`/`OPENBLAS_NUM_THREADS`-sensitivity/signature
  items above are all accounted for and resolved or explained.
- `uv run pytest tests/qa/ -q --tb=short` — **85 passed, 9 skipped.**
  Byte-identical goldens (`git diff` on `tests/qa/golden_outputs/` empty):
  nothing in `products/`, `reinsurance/` or the CLI moved.
- Conformance run — **attempted three times, did not complete.** Two
  `workflow_dispatch` runs (144, 146) and the automatic `pull_request` run
  (145, triggered by opening PR #225 — several touched paths are in the
  workflow's own trigger list) all reached the R job successfully every
  time (green, unaffected). The Python "Compare against the Python
  reference" job stalled: run 144 hung on the generic "Install
  dependencies" step for 15+ minutes without ever reaching this session's
  own code; after cancelling it, run 145 progressed through most steps at
  a normal pace (including this session's own extended slice 7b table) but
  then stalled 20+ minutes inside the PRE-EXISTING, UNMODIFIED slice 7c
  identifiability diagnostic step — a step ADR-219's own session completed
  in well under a minute. All three runs cancelled after generous waits
  rather than left running. Reads as CI/runner resource contention in this
  environment on this day, not a defect introduced this session: the stall
  occurred inside code this session does not touch. **The
  `SELECT_FREE_SP_MODEL_CLAIM` table above is TIER 1 ONLY** and not yet
  citable as settled parity evidence outside this session log/PR #225
  until a future check-in successfully re-dispatches
  `mgcv-conformance.yml` on this branch.

## Perf history

`uv run python scripts/perf_history.py -o /tmp/perf_history_out.json` — one
row appended for this branch's HEAD commit (ADR-177 step 14b, initial PR
open), append-only, no prior row touched. Verdict: `has_structural_creep=
False`, `has_wall_time_creep=False`, `has_config_drift=False` — `peak MiB
33 -> 33 (Δ+0)`, wall-time recent/baseline `1.064x`. Clean, on a probe
entirely unrelated to this session's GAM-only, no-production-`TermLife`-
path-changed work.

## Follow-ups filed

- **NEW, this session: SciPy L-BFGS-B can report `converged=True` via an
  `ftol`-style stopping rule while a large TRUE gradient remains on
  directions not pinned at a search bound**, independent of ADR-212's
  finite-difference-noise mechanism (that one supplied a noisy gradient
  near a genuine optimum; this is the EXACT gradient, and the optimiser
  still exits early near a bound-active corner). Localised to one
  reproducible case (blind single-start, `select=TRUE` N=7 structure) but
  not yet chased to a general fix (a tighter `factr`, a restart after a
  bound-active exit, or accepting it as a property of L-BFGS-B on this
  shape of problem are three candidate directions, none evaluated).
  1st-order — a defect in the search this slice's own scope touches
  directly, not a tangential finding.
- **The dW/drho defect-in-waiting ADR-219 flagged is now CLOSED**, not
  merely avoided: `dw_deta_observed`/`dw_drho_observed` supply the exact,
  alpha-aware chain, verified against central differences on all three
  link/family combinations this codebase defines, and
  `reml_score_gradient` uses them rather than the Fisher-only
  `dw_deta`/`dw_drho` ADR-219 warned against wiring in "straight".
- **Carried, not re-opened:** the `OPENBLAS_NUM_THREADS`-sensitivity of
  `test_the_r_probe_runs_end_to_end` (filed at slice 7c's own baseline,
  reproduced identically again this session, still 2nd-order/needs-its-own-
  slice) and the CONTINUATION doc's own open question about the stamp
  schema understating evidence after an inert edit (this session's own
  `MEASUREMENT_unconditional_coverage.md` re-stamp is a second, independent
  instance of exactly that gap — filed there already, not re-filed here).
