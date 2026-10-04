# Dev session log — 2026-10-04 — outer-solver slice 3 (rounding noise at an 11-decade spread)

**Branch:** `claude/intelligent-hamilton-c64y8s`. **Routine:** `docs/ROUTINE_MGCV_PARITY.md` (active epic `PLAN_wood_outer_solver.md`). **PR title class:** `harness(mgcv-parity)` — NO INDEPENDENT comparison is landed; every reading is Polaris against itself.
**Perf verdict (ADR-177):** row appended (touches non-conformance `src/` modules `gam_reml_gradient.py`, `gam_reml_hessian.py`).
**Registered-prompt vs ROUTINE file:** the prompt box's CURRENT STATE says "the epic is at ADR-207" and "next unchecked slice of PLAN_mgcv_parity_engine"; the ROUTINE file's ACTIVE EPIC POINTER (ADR-241) makes `PLAN_wood_outer_solver.md` the plan and the epic is at ADR-243. The ROUTINE file wins as instructed; the box is stale (a maintainer edit).

## Baseline
`make test` with R installed (before any edit): 3882 passed, 22 skipped, 5 failed — the same 5 standing failures as the Slice 2 log (generated mortality tables absent). After: 3885 passed (+3 new), same 5 deselected. `tests/qa/`: 85 passed, 9 skipped, goldens untouched. Ten-cell conformance suite (tier 1, scratch output): levels 1-3 AGREE, 5 AGREES, 4 DISAGREES (standing, ADR-207 decision 3).

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt, after `apt-get update`), `OPENBLAS_NUM_THREADS=1`; same as last session. Tier 2 unavailable (no daemon). Tier 3: run 37167311644 on `6851cab`, R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. ADR-244's numbers are tier 3 except the Hessian BEFORE column (tier 1, labelled).

## Gap Before
Cross-thread: ADR-222 amendment 1 (multistart + L-BFGS-B) d eta 0.356 / d edf 10.0 — never re-measured on the Newton search. Precision: a random orthogonal rotation of the coordinates moved the analytic gradient 1.6e-4 (≈ the Newton tolerance 1.66e-4), the scaled Hessian 0.77, and made the inner IRLS fail in 4 of 6 rotations at `mgcv`'s point; `eps*cond(H) = 7.7e-5` was assumed to be the gradient's floor. `beta'S beta` vs `float128`: 6.8e-05 (formed), 1.99e-4 (sum of squares), read as inaccuracy.

## Hypotheses Tried (including failures)
1. Thread axis passes on exact-Hessian Newton with no reparameterisation. **HELD** (tier 3: d eta 2.8e-07).
2. The rotation noise is the missing Appendix B transform; carrying `T` with structural zeroing fixes it. **PARTLY** — inner failures 4/6 -> 0/6, gradient noise only halved. Then discovered the rotation test also perturbs `S`'s representation, so it is not a valid gate.
3. Jacobi equilibration of `H`. **REFUTED** (no effect).
4. Decompose the gradient under one ulp on `X`: it is term 1 (formed `beta'S_j beta`), 3e-5 from a 5e-15 change in `beta`. Substitute block roots. **HELD** — 6.5e-05 -> 4.7e-08 (tier 3).
5. Same for the Hessian's `A_j beta` / `beta'A_j beta`. **HELD** — scaled 0.39 -> 4.8e-04 at the wide point.
6. Canonical `L L'` penalty; and transform+zeroing in the canonical basis, against an ulp on `S`. **REFUTED** — the remaining sensitivity is the problem's own.
7. `float128`: the sum-of-squares error against its own `float128` value is 7e-15; the "1.8e-4" is the gap between two definitions of truth. **CORRECTION** to ADR-222 amendment 2's reading.

## Gap After
Cross-thread (Newton, tier 3): d eta 2.8e-07, d edf 1.7e-05, 20 fits all converged. Gradient evaluation noise under one ulp on `X` (tier 3): 4.7e-08 / 4.0e-09 / 3.5e-09 at the wide point / `mgcv`'s point / Newton stop; remaining one-ulp-on-`S` sensitivity 4.6e-06..2.6e-05 is below the Newton tolerance by 6-100x and is not removable by evaluation. Newton verdicts unchanged (L1/3b/3c agree, same fit counts). This is a characterisation, not a parity gap.

## Provenance
- Thread axis, ulp-perturbation floor, `float128` readings — **none of these has a second producer.** Left and right are Polaris on perturbed inputs / another thread count / another precision. Class: `MEASUREMENT (own criterion)`; no `VerificationClaim`; nothing gated; not parity evidence.
- `mgcv`'s `sp` appears only as a point of evaluation (VERIFICATION_STANDARD §2.1) and, in the thread table, as a printed reference.
- Newton L1/3b/3c rows (tier 3): INDEPENDENT eta/edf by the existing claims (headline from `evidence_markdown`), unchanged and not the subject of this slice.
- The N=7 pre-reading (eta 5.7e-05 vs `mgcv`): tier 1, INDEPENDENT in construction (Newton sees only data and `initial.spg`), but unverified and not committed as settled.
- No ECHO or TRANSPORT column is reported as evidence.

## DoD (PLAN Slice 3, verbatim, with evidence)
- [x] both reproducibility axes (seed, BLAS threads) re-measured on ADR-222 amendment 1's protocol, beside its readings — thread: ADR-244 finding 1. **Seed: NOT MET because no operand** (Newton has no random component).
- [x] `beta'S beta` against `float128` at the 11-decade spread, beside `6.8e-05` — ADR-244 finding 4.

## Open / follow-ups
Slice 4 NEXT. Slice 3b registered (release condition in the PLAN). A mutation of the old arithmetic fails `test_gam_penalty_quadratic_forms.py`. Not audited: `experience_gam_penalized` for the same pattern (Anchor 7). Level 4 DISAGREES (standing). Mechanism class (iv); no start strategy added.
