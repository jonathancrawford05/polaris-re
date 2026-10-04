# Plan: the Wood-shaped outer solver — mgcv's smoothing-parameter search, not a better start

> **STATUS: IN PROGRESS — ACTIVE EPIC (maintainer, 2026-10-03; ADR-241).**
> Slice 0 (diagnosis) DONE (ADR-241). Slice 1 DONE (ADR-242, tier 3, run 37130685404). Slice 2 DONE (ADR-243, tier 3, run 37153229821). Slice 3 DONE as a CHARACTERISATION (ADR-244, tier 3, run 37167311644): the thread axis already passes on the exact-Hessian Newton search without a reparameterisation, and the rounding noise was the gradient/Hessian penalty quadratic forms (fixed, two substitutions), not a missing transform. **Slice 4a DONE (ADR-245, tier 3, run 37204039328): gauntlet cases 1-3 — one Newton start agrees on all nine rows. NEXT: Slice 4b** (cases 4-5, blocking fixed-scale step, the default flip). Slice 3b (QR-augmented solve) is registered with a release condition.
> This epic takes the active slot from `PLAN_mgcv_capability_ladder.md`, which
> yields; its remaining start-strategy slice (7c) is SUPERSEDED here (3e/3f
> were closed by maintainer decision, ADR-240 amendment 1).
> It is `PLAN_mgcv_parity_engine.md` slice 8, promoted to its own epic so the
> work-selection rule can reach it (§2).

**Source:** maintainer direction 2026-10-03, after reviewing PR #249 (ladder
slice 3e): *"clearly we are spiralling … we need to take the time to plan the
necessary overhaul to our approach to starting, to even get close to mgcv
parity … we have described the exact components, but failed to prioritize the
effort."* And earlier, 2026-09-05, recorded as slice 8's origin: *"we need a
reliable solver (mgcv achieves this so a real and implementable mechanism
exists)."*
**Supersedes:** `PLAN_mgcv_parity_engine.md` slice 8 (its scope and DoD are
carried in full below); ladder slice 7c. (Ladder 3e/3f were closed by
maintainer decision, ADR-240 amendment 1, before this epic started.)
**Total slices:** 0 (done) + 4.
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` — a convergence loop with a live
oracle. Same tiers, same provenance gate, same nevers.

---

## 1. What is wrong, measured (slice 0, ADR-241)

The engine's REML **criterion** is right: ADR-196/231 confirm it against
`mgcv` to float round-trip on known- and free-scale families, and every Stage-A
basis on the target form is INDEPENDENT-exact. What the engine cannot do is
**reliably find the criterion's minimum**. In every recorded free-`sp`
disagreement with `mgcv` that this plan's author found (ADR-218, ADR-226,
ADR-236, ADR-238/239, ADR-240), `mgcv`'s point scores at least as well as
ours **under our own criterion**. None was found running the other way.

Slice 0 asked the one question that decides the architecture: on the two cells
where ADR-240 found a start that disagrees, is there a **barrier** between our
stopping point and `mgcv`'s, or did the **search stop early**?
`scripts/gam_outer_solver_landscape_probe.py`, `MEASUREMENT (own criterion)` —
`mgcv`'s `sp` is only the point of evaluation (`VERIFICATION_STANDARD.md` §2.1).
Tier 3 (R 4.6.1 / mgcv 1.9.4, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`): run
37091438628, plus the accepted-iterate and exit-message readings added after
PR #250's review (run recorded in ADR-241); tier 1 identical at every printed
digit.

| cell, start | first trial point | first ACCEPTED step | how the search ended | stop vs `mgcv` point (own score) | segment barrier | gradient at stop |
|---|---|---|---|---|---|---|
| gaussian L1, `initial.spg` seed | 11.81 decades | **11.81 decades — accepted**, two blocks onto the UPPER bound | `factr` relative-reduction test | 180.84 vs 165.30 | 0.158, on a 15.5 descent | ~0 on three plateau blocks, -0.073 on the fourth |
| quasipoisson 3c draw, bounds-centre | 7.00 decades (one block to the lower bound) | 1.47 decades — the 7.00 trial was **rejected** by the line search | `factr` relative-reduction test, `converged=True` | 1642.33 vs 1638.95 | **none** — monotone descent | **up to ~2 per decade** |

**Diagnosis: two outer-search defects, neither of them the start.**

1. **An uncapped accepted step (L1).** L-BFGS-B's first quasi-Newton step,
   taken with an identity Hessian approximation and no step-length limit,
   moved 11.8 decades and was ACCEPTED, landing on the `lambda -> infinity`
   plateau where a fully-penalised term's REML derivative vanishes. The
   `initial.spg` seed was good and was discarded by that step.
2. **A termination test that is not a stationarity test (3c, and L1's exit).**
   Both searches end on L-BFGS-B's relative-function-reduction test (`factr`),
   not its gradient test. On 3c that declares `converged=True` with the
   gradient still ~2 per decade and a monotone descent of 3.38 still
   available. ADR-239's "worse stationary point" is wrong: it is not
   stationary.

`mgcv`'s Newton addresses both: it caps every step
(`gam.control()$newton$maxNstep = 5` natural-log units, about 2.17 decades),
halves steps that do not improve (`maxHalf = 30`), forces the Hessian positive
definite by eigendecomposition, drops already-converged directions from the
step, and tests convergence on the GRADIENT relative to the score's scale
(read from `mgcv:::newton`, 1.9.1, tier 1 — behaviour and constants, not
transcribed code).

**What this says about the last eleven slices.** Multistart (ADR-213), the
two-start rule (ADR-237), the seeded start (ADR-239) and best-of-both (ADR-240)
each sampled more starts for a search whose defect is what it does *after* the
start. That is why each fixed the cell it was built on and broke or missed
another, and why ADR-226 measured best-of-9 settling in the worse basin on
8 of 10 seeds. `mgcv` has no multistart anywhere.

## 2. Why this epic exists as an epic, and the rule that keeps it from being skipped again

Everything in §3 has been written down since ADR-222 amendment 1 (2026-09-05)
as `PLAN_mgcv_parity_engine.md` slice 8. It was never built because:

1. The parity epic yielded the active slot (2026-09-14) to wiring, then to the
   ladder; slice 8 stayed `NEXT` in a CONTINUATION nobody was reading.
2. The routine selects "the PLAN's next unchecked slice", and ADR-209 decision
   1 registers every newly opened gap as a letter-suffix slice **in the active
   PLAN**. Each ladder slice met a solver symptom, registered a narrow
   start-strategy follow-up, and that follow-up became next — ahead of the
   older, structural slice in another file.

The routine change in ADR-241 (`ROUTINE_MGCV_PARITY.md`, "MECHANISM BEFORE
SLICE") closes that: a gap whose diagnosed mechanism is the outer search is an
**acceptance case for this epic**, not a new slice anywhere.

## 3. The slices

Each slice ships opt-in and additive (`fit_polaris_gam(outer="newton")` or
equivalent) until Slice 4 surfaces it. `tests/qa/golden_outputs/` must stay
byte-identical throughout — no pricing path uses `fit_polaris_gam` (Anchor 7).

### Slice 0 — diagnose: barrier or early stop? — ✅ DONE 2026-10-03 (ADR-241)

Probe, tests, non-gating CI step, ledger rows. See §1.

### Slice 1 — a safeguarded Newton outer loop, with the gradient we have — ✅ DONE 2026-10-03 (ADR-242)

**Hypothesis (registered before the code):** the two §1 defects — an
uncapped accepted step and a function-reduction stop at a non-stationary point
— are the outer search, not the start or the criterion. A Newton step with
`mgcv`'s safeguards and a gradient-based convergence test, from the
`initial.spg` start, reaches `mgcv`'s point on BOTH cells without any
multistart.

**Scope.**
- **Free-scale analytic gradient.** `reml_score_gradient` raises for
  `dispersion_fixed=False` today, so every gaussian/quasipoisson fit runs on
  finite differences. Derive it for the profiled criterion
  (`gam_reml.py`'s L5 derivation). Expected route: because `phi_hat` is the
  criterion's own stationary point in `phi`, the envelope theorem gives the
  profiled gradient as the fixed-`phi` gradient evaluated at `phi_hat` — a
  hypothesis to verify against a central difference, not an assumption.
- **The Newton loop**, new code in its own module beside
  `gam_reml_optimize`: Hessian as a central difference of the ANALYTIC
  gradient (N extra gradient evaluations — exact Hessian is Slice 2);
  eigen-perturbation to positive definite; a step-length cap of 5 in
  natural-log `lambda`; step halving (up to 30) on a non-decreasing score; a
  steepest-descent fallback; converged directions dropped from the step; a
  convergence test relative to the score's own scale. Each constant is
  `mgcv`'s documented `gam.control()` default, named as such — derived from
  the method, not tuned to a cell.
- `initial.spg` start (ADR-239) as this loop's only start.

**Definition of Done (ADR-209 decision 3) — status:** all four items met at tier 3 (see ADR-242); L1's margin is thin and its tier-1 run stalled on the gradient's precision floor (Slice 3).
- `[machine]` Free-scale analytic gradient equals a central difference of the
  score on gaussian and quasipoisson, at three `rho` points each including one
  with a block at `lambda >= 1e10`.
- `[machine]` INDEPENDENT, tier 3: the Newton fit agrees with `mgcv` under
  ADR-221 on gaussian L1 AND the 3c draw, single start, no multistart.
- `[machine]` Slice 0's probe re-run on the Newton fit: every ACCEPTED step
  `<= 2.17` decades on both cells, and the search ends on its gradient test
  (max |gradient| below the score-scaled tolerance at the stop), never on a
  function-reduction test alone.
- `[judgement]` If either cell still disagrees: characterised with the probe,
  not patched with a start.

### Slice 2 — the exact Hessian (Wood 2011 §3.4-3.5, Appendix D) — ✅ DONE 2026-10-03 (ADR-243)

`gam_derivatives` already computes `d beta/d rho` and `dw/drho`; the Hessian
needs the second-order terms. Derived from the paper, never transcribed from
`mgcv`. Replaces Slice 1's differenced Hessian.

**DoD (status).**
- [x] `[machine]` analytic Hessian equals a central difference of the analytic gradient on all three family/link combinations (five were run), before composition — `tests/test_analytics/test_gam_reml_hessian.py::test_hessian_matches_a_central_difference_of_the_analytic_gradient`.
- [x] `[machine]` Slice 1's cells re-run at tier 3, readings unchanged in verdict — ADR-243, run 37153229821.
- [x] `[machine]` function evaluations per fit reported beside L-BFGS-B's — ADR-243 table (exact 11/5/8, differenced 92/37/52, L-BFGS-B 790/65/75).
- Beyond the DoD: an INDEPENDENT comparison against `mgcv`'s own `outer.info$hess`, five cases, tier 3 (ADR-243 finding 1).

### Slice 3 — Wood §3.1 reparameterisation through the fit and the derivatives — ✅ DONE 2026-10-04 as a characterisation (ADR-244)

`gam_reml_appendix_b` builds the transform and the stable root `E`, wired today
to `log|S|+` only. Carry it through `beta_hat`, `log|X'WX+S|` and every
derivative — the precision Wood says is lost without it at 10+ decade `lambda`
spreads, which is exactly where §1's plateau sits.

**First task (carried from slice 8's sequencing note):** re-run ADR-222
amendment 1's thread-axis study with the transform applied, BEFORE wiring it
everywhere. It either confirms this slice or redirects it.

**DoD (status).**
- [~] `[machine]` both reproducibility axes re-measured (THREAD AXIS ONLY — seed axis has no operand) on ADR-222 amendment 1's protocol, beside its readings — thread axis: ADR-244 finding 1 (tier 3, d eta 2.8e-07 vs 0.356). **Seed axis: NOT MET because it has no operand** — Newton from `initial.spg` has no random component.
- [x] `[machine]` `beta' S beta` against `float128` at the 11-decade spread, beside slice 7h's `6.8e-05` — ADR-244 finding 4 (tier 3): evaluation error 7.1e-15; the 1.8e-4 is a representation gap between two definitions of truth.
- Outcome: the transform was **not wired**. Four hypotheses refuted (ADR-244, ledger); the real defect (derivative path's formed quadratic forms) was fixed instead.

### Slice 3b — QR-augmented stable solve (Wood 2011 §3.2) — REGISTERED, not started
Factor `[sqrt(W) X; E]` instead of forming `X'WX + S`, so the factor's condition number is `sqrt(cond H)` (~6e5, not 3.5e11) for the fit, `log|H|` and the `tr(H^-1 S_j)` terms. Needs a non-negative `W` (the observed weight can be negative for a non-canonical link), so the cloglog case needs a design decision first. **Release condition:** a Slice 4 gauntlet case fails on gradient precision with `max |g|` within 2x of its tolerance, or ADR-244's `S`-representation floor (gradient 2.6e-05 at `mgcv`'s point) comes within 10x of a tolerance. Until then it is not needed: the measured floor is 6-100x below the search's tolerance. Mechanism class (iv).

### Slice 4 — surface: one deterministic solver for every free-`sp` fit

> **4a DONE 2026-10-04 (ADR-245)** — cases 1, 2 (comparison only), 3. **4b REGISTERED, NEXT:** case 2's CI step made blocking; case 4 (4-term HGAM); case 5 (reproducibility axes, thread only for Newton); the `epsilon_rel` / curvature-to-noise measurement put to the maintainer; THEN the default flip and `evidence_markdown` DoD table. Release condition: none external.

Make the Newton solver (with `initial.spg`) `fit_polaris_gam`'s default;
`multistart`, the two-start rule and the seeded-start flag stay only as
diagnostics.

**The gauntlet — every case below, ONE start, NO multistart, tier 3, ADR-221's
`eta`/`edf_total` gate, INDEPENDENT:**
1. all six free-scale cells (gaussian L1, L3, L4, L6; quasipoisson 3b, 3c);
2. quasipoisson fixed `scale=6` (ADR-236) — **and** that CI step made
   blocking, per the 2026-10-01 maintainer decision carried from slice 8;
3. the `select=TRUE` N=7 fixture: reach the `523.645` basin (ADR-226), not on
   3 of 10 seeds but by construction. (Slice 3 left a tier-1-only pre-reading: one start, eta diff 5.7e-05, edf diff 0.004 vs `mgcv`, 20 fits — to be re-read at tier 3 here.);
4. wiring slice 1's 4-term HGAM (ADR-227);
5. both reproducibility axes pass (ADR-222 amendment 1's protocol).

**Also carried from slice 8:** its "first task" — re-measure the restricted
projected-gradient plateau on the post-7h criterion and put `ε_rel` and the
curvature-to-noise ratio to the maintainer (`PROPOSAL_convergence_certificate.md`
§6). The exact Hessian makes the restriction nearly free.

**DoD.** `[machine]` the gauntlet table, produced by one script whose headline
comes from `evidence_markdown()`. `[machine]` goldens byte-identical.
`[judgement]` the reliability claim names its axes, cases and tolerance — never
an unqualified "reliable".

## 4. Out of scope

- Re-pointing production pricing or the dashboard at this solver (Anchor 7; a
  separate maintainer decision).
- `bam`/`discrete=TRUE`/fREML.
- New bases or rungs (ladder L6-L11, slice 6b `select=TRUE` on `cr+re+ti`) —
  they resume after Slice 4, on a solver that no longer needs a per-cell start
  strategy.
- Any tolerance change. ADR-221's gate is the gate.

## 5. Risks

1. **A real barrier exists on some cell.** L1's segment shows a 0.158 rise on
   a straight line; a curved path may avoid it, but if a Newton search from
   `initial.spg` still lands on the plateau, the start matters after all.
   Slice 1's `[judgement]` line covers it: characterise, do not patch.
2. **The plateau itself.** A term at `lambda -> infinity` has a vanishing
   derivative; dropping converged directions (as `mgcv` does) is what stops it
   from stalling the whole step. If that is insufficient, `mgcv`'s handling of
   indefinite/flat Hessians is the next place to read.
3. **Profiled vs joint `phi`.** `mgcv` treats log-scale as a search parameter;
   we profile it out (ADR-239 lists this as unexamined). Same optimum, different
   geometry. Slice 1 measures before anyone changes it.
