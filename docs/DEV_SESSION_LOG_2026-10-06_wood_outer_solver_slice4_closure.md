# Dev session log — 2026-10-06 — outer-solver Slice 4 closure (`eps_rel`, default flip)

**Branch:** `claude/zen-einstein-cqzueg`. **PR title class:** `feat(mgcv-parity)` (the `select=TRUE` `log10(sp)` reading is INDEPENDENT; the plateau measurement is own-criterion). **Trigger:** maintainer instruction, 2026-10-06 — *"Let's get e_rel measured and closed and make Newton the default"*, plus the two preview decisions (`polaris_re.gam`; bare `s()` refused until `tp`). Executes `ROUTINE_MGCV_PARITY.md`'s SLICE 4 CLOSURE RULE (drafted 2026-10-05 on this branch, same PR) in one PR.
**Perf:** one row appended (ADR-177): this PR modifies `gam_model.py`, which is not a `*_conformance.py` module, so amendment 2's exemption does not apply (the probe's import closure does not load it either; the row is the rule, not a judgement).

## Baseline
`origin/main` at `9d4ee8c` (PR #256 merged), mortality tables present: **4044 passed, 38 skipped, 0 failed** (PR #256 review run, same tree plus #256's fix commit). After this change: **4050 passed, 38 skipped, 0 failed** (+6 new tests; `tests/qa/` goldens unchanged).

## Oracle Version
No R locally (tier 1 unavailable). The plateau measurement needs none (committed R draws, `mgcv` outputs stripped). The `log10(sp)` reading is tier 3: run 37402772623 on `da63a06`, R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192…`.

## Gap Before
PLAN Slice 4's last items, carried "not run this session" through 4a/4b/4c part 1:
- the restricted-plateau measurement and the `eps_rel` / curvature-to-noise question;
- the INDEPENDENT `log10(sp)` reading on `select=TRUE`;
- the default flip.

## Hypotheses Tried
1. **At the Newton stop, the restricted projected gradient sits near `mgcv`'s `conv.tol`, not near the provisional 1e-8.** HELD. N=4: 6.95e-07; N=7: 7.60e-07 (relative, natural-log `rho`). 1e-8 would certify none of them.
2. **The flat directions slice 7c found are still flat on the post-7h criterion.** REFUTED. The step-stability scan resolves 4 of 4 and 7 of 7 directions, smallest curvature ~4e-4 vs `eps_f` ~1e-12. The pre-7h noise (`eps_f/h^2` ~0.08 at `h = 0.025`) is what made them read flat.
3. **The `select=TRUE` `log10(sp)` slack is shallow real curvature, not a solver defect.** HELD (own criterion). The remaining Newton step on blocks 1/3 is 0.43-0.46 decades, worth 4e-4 of score and 5.7e-05 of `eta`. Tier-3 per-block reading against `mgcv`: b0 -0.255, b2 -0.289, every other block within 0.006 — b0/b2 are exactly the two low-curvature directions (a) located; Polaris stops ~0.27 decades below `mgcv`, the stationary point lies ~0.15-0.21 above `mgcv`, so the two engines stop on opposite sides of a shallow valley under the same 1e-6 test. Known limitation, recorded (ADR-248).

## Gap After
Slice 4 DONE; the outer-solver epic is DONE (ADR-248).
- `fit_polaris_gam` defaults to `outer="newton"`.
- `eps_rel = 1e-6` ratified; curvature-to-noise = the step-stability scan.

## Provenance
- **Plateau:** MEASUREMENT (own criterion). Polaris's criterion at Polaris's selected point; fixtures are R draws with `mgcv` outputs stripped. No `VerificationClaim`; the CI step's headline says "NOT parity evidence".
- **`log10(sp)` per block:** INDEPENDENT. The fit takes the recipe only; `mgcv`'s `sp` is the other operand. Already declared on `SELECT_FREE_SP_MODEL_CLAIM` (ADR-221 amendment 3). Reported, not gated; no tolerance added.
- **Default flip:** no comparison. The evidence is ADR-245..247's gauntlet.

## DoD (PLAN Slice 4, with evidence)
- [x] cases 1-4 — ADR-245/246.
- [x] case 2 blocking CI step — ADR-246.
- [x] case 5 — thread axis ADR-247; seed axis has no operand for Newton.
- [x] `epsilon_rel` / curvature-to-noise — measured and CLOSED (ADR-248; `PROPOSAL_convergence_certificate.md` §6).
- [x] default flip — `gam_model.py`; `test_fit_polaris_gam_defaults_to_the_newton_search`, `test_the_default_fit_is_the_newton_fit`.
- [x] `[machine]` gauntlet table by one script, headline from `evidence_markdown()` — `scripts/gam_newton_gauntlet.py`, now with the `log10(sp)` column.
- [x] goldens byte-identical — `pytest tests/qa/` within the full run; no file under `tests/qa/golden_outputs/` changed.
- [x] `[judgement]` reliability wording — ADR-248 "Not claimed" names cases, axes, tolerance and the `log10(sp)` limitation.

## Test changes
- **Three existing tests gained `outer="lbfgsb"`:** `test_fit_polaris_gam_multistart_matches_default_shape`, `..._analytic_gradient_matches_default_shape` and `..._rejects_x0_together_with_multistart`. This is the kwarg addition the closure rule pre-approved; no assertion, tolerance or expected value changed.
- **New tests:** three default-pinning tests in `test_gam_model.py` and three `log10(sp)`-reporting tests in `test_gam_newton_gauntlet_conformance.py`.

## PR #257 CI
All checks green on `da63a06`. The plateau CI step (non-gating) raised inside the step-stability scan: an inner-IRLS non-convergence at a probe point, environment-dependent (ADR-224 amendment 1). Fixed by reporting a failing case as an error row (the gauntlet's own rule); the local readings are complete.

## Open / follow-ups
None in this epic. Next work is `PLAN_gam_parity_preview.md`'s epic start (ROUTINE pointer). Slice 3b stays registered with its release condition. The maintainer's routine-prompt edit (the stale "ADR-207 / parity PLAN" box) is outside this PR.
