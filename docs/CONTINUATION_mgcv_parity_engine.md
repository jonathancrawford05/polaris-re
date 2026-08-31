# Continuation: a Python GAM engine at parity with `mgcv`

**Source:** maintainer direction 2026-08-10 (the target model form, supplied as R).
**Plan:** `docs/PLAN_mgcv_parity_engine.md`
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` — a convergence loop, not a backlog walk.
**Predecessors:** ADR-189 + amendment 1 (the conformance suite and its first run),
ADR-185 through ADR-188 (the penalized fitter this epic reuses).
**Status:** **IN PROGRESS** — slice 1 is **DONE (raw path only)** (2026-08-15b); slice
1b (mgcv-native extraction) is **DONE** (2026-08-16, tier 1 and tier 3 both confirmed);
slice 2 (`bs = "cr"`) is **DONE** (2026-08-17, tier 1 and tier 3 both confirmed — ADR-194)
— the epic's first INDEPENDENT Stage-A parity result. Slice 3 (families/links/weights)
is **DONE** (2026-08-17, tier 1 and tier 3 both confirmed — ADR-195) — the epic's first
INDEPENDENT Stage-B parity result outside the already-verified Poisson case. Slice 4
(the outer optimiser) is **IN PROGRESS** — part A (the REML score itself, generalized to
known-scale families and multiple penalty blocks) is **DONE AND RESOLVED, 2026-08-18**
(ADR-196): it first DISAGREED with `mgcv` (an INDEPENDENT, tier-1/tier-3-identical
result), then the maintainer supplied Wood (2011) directly and the fix — a missing
penalized-deviance term, §2 eq. (4) — closed the gap to float round-trip precision, tier
1 and tier 3 identical (CI run 32142352655). **`docs/WORK_ORDER_reml_penalized_deviance_production_check.md`
has now RUN, 2026-08-18** (ADR-197, tier 1 and tier 3 identical, CI run 32181109927): the
shipped, production `experience_gam_penalized.reml_score` DOES carry the identical
omission, and the registered §3.2 prediction HELD on all three free-sp cells (the
corrected grid search selects measurably closer to `mgcv`'s own free-sp selection
everywhere tested). **RESOLVED, 2026-08-19 (ADR-197 amendment, maintainer-authorized):**
the maintainer explicitly authorized "fix `experience_gam_penalized.reml_score` the same
way ADR-196 fixed `gam_reml.reml_score_general` (add the missing term)". The fix is
applied — `experience_gam_penalized.reml_score` and `gam_reml.reml_score_general` now
compute the identical criterion, bit-for-bit — and `data/mgcv_exchange/synthetic/
python_reference.json` is re-baselined via its own regeneration path, moving exactly as
§3.2 predicted on all three named free-sp cells (`l2-free-sp` λ_age 3162.28→5623.41,
λ_year unchanged) plus `l5-gamma` (not one of the three §3.2 named, same mechanism). The
full ten-cell conformance suite re-run against the fixed module (tier 1 confirmed, tier 3
pending/confirmed — see ADR-197) shows required levels 1-3 still AGREE (no regression) and
level 5 (Wood's `gamma`) moves from DISAGREES to AGREES — an improvement beyond what §3.2
alone measured. Level 4 (Kass-Steffey covariance) is unchanged in kind, ADR-190's separate,
already-tracked `dw/drho` gap. **Slice 4 part B remains unblocked to proceed** — the outer
search builds on `gam_reml.reml_score_general`, already correct before ADR-197's session
ran, and now the production 2-D grid selector agrees with it too rather than being two
steps removed. This remains the epic's largest remaining piece of work, and slices 5-7 all
depend on it. **Part B's first slice is DONE, 2026-08-22** (ADR-199, tier 1 AND tier 3 both
confirmed, CI run 32544930172): `gam_reml_optimize.py`'s `select_lambdas_continuous`, a
Newton/quasi-Newton search over `log10(lambda)` built on the already-verified
`gam_fit`/`gam_reml` functions, and it **decisively confirms ADR-198's registered
prediction** — the free-sp residual left after ADR-197's fix collapses from the grid's
0.0645/0.0791/0.1048/0.0776 to (tier 3) 6.9e-04/5.1e-05/1.7e-04/9.8e-04 (2-3 orders of
magnitude, identical in verdict to tier 1) once the grid is replaced by a continuous search
on the identical criterion. Tested only at the existing 2-block designs; extending to the
target's 13-21 blocks needs a multi-term mgcv-native model (slice 5 onward). **Slice 5
(`ti()` and the MI term) is IN PROGRESS, 2026-08-22:** the MI term's own basis,
`s(AttdAge, by=StudyYear_C)`, is **DONE (Stage A only)** (ADR-200, tier 1 and tier 3
identical) — the epic's first INDEPENDENT Stage-A result for a numeric-`by` `cr` smooth;
`mgcv` absorbs no identifiability constraint on it at all. **`ti(AttdAge, PolYear)` is now
also DONE (Stage A only), 2026-08-24** (ADR-205, tier 1 and tier 3 identical, CI run
32677470292) — the epic's second INDEPENDENT Stage-A result, built by instrumenting
`mgcv:::smooth.construct.tensor.smooth.spec` directly (Anchor 8) rather than reading its
own source cold: each margin's own constrained `cr` basis, no further reparameterization
(`cr` sets `noterp`, so `ti()`'s `np=TRUE` SVD reparam never fires for an all-`cr`
tensor — found the hard way, after an earlier hand-replica that DID apply it disagreed by
up to 182 in `X`), row-wise Kronecker design and penalties, then a SECOND tensor-level
`scale.penalty` rescaling on top of each margin's own (found after step-4-only output
agreed on `X` but disagreed on `S` by a constant ratio per block). Agrees with
`smoothCon(ti(...), absorb.cons=TRUE)` to float round-trip precision (~1e-14) on a
synthetic case and the target's own `ti(AttdAge, PolYear, k=c(13,6))` knots.
**The multi-term mgcv-native model Stage B needed is now DONE, 2026-08-24** (ADR-206,
tier 1 and tier 3 identical, CI run 32722872476): a three-term model (reference age,
the `by` term, `ti()`) fit together at fixed sp agrees with mgcv on `eta` on the first
measurement, `max_abs_eta_diff=1.242e-10`. **Slice 5 is DONE.**

> **ANCHOR 7 IS AMENDED** (2026-08-24, maintainer-authorized, **ADR-207**). The old
> engine stays until a new one demonstrably matches it and nothing is re-pointed
> silently, but **building a new production path from the tier-3-verified components is
> now explicitly permitted and is the epic's intended route.**
>
> **ADR-206 confirmed ADR-207's diagnosis within hours, and sharpened it.** ADR-207 was
> written against a repository holding nine verified modules and nothing permitted to
> compose them, arguing that Anchor 7 forced every component to justify itself as a
> conformance artifact. ADR-206 then built the assembler — and built it as
> `gam_multiterm_conformance.assemble_multiterm_design(r_case: RMultiTermRecipe)`: a
> harness that takes its model definition from **an R script's JSON payload** and fits
> at a **fixed, externally-supplied `sp`**. It is excellent work and its Stage-B `eta`
> parity is real, but it cannot fit a model `mgcv` has not already defined, and it does
> not select its own smoothing parameters.
>
> That is the pattern, not a criticism: with Anchor 7 in force, a harness was the only
> available framing. **The remaining gap is now precise and much smaller than ADR-207
> estimated** — drive the same, already-verified assembly from `ModelSpec` instead of
> `RMultiTermRecipe`, and select lambda with `select_lambdas_continuous` instead of
> receiving it. `docs/WORK_ORDER_multi_term_assembly.md` is rewritten to that scope and
> is **READY, not designated** — designating a slice is a routine call.
>
> **Withdrawn, not granted:** the long-open "re-point `smoothing_uncertainty` at
> `gam_uncertainty`" item (ADR-207 decision 3). ADR-203 removed its justification, and
> the new path uses `gam_uncertainty` natively. The ten-cell suite's level 4 will read
> DISAGREES about the legacy engine permanently and correctly.

**Slice 5b (`PolarisGAM` from a `ModelSpec`) is DONE, 2026-08-25** (ADR-208, tier 1
and tier 3 both confirmed, CI run 32855338611).
`src/polaris_re/analytics/gam_model.py` generalises ADR-206's
`assemble_multiterm_design` into `assemble_model_design(model: ModelSpec, data)`
(any mix of `"cr"`/`"ti"` terms, not just the fixed three) and adds
`fit_polaris_gam`, which selects its own `log10(lambda)` via
`select_lambdas_continuous` (ADR-199) and fits with `penalized_irls_general`
(ADR-195) — nothing re-derived, exactly the work order's own scope.
`assemble_multiterm_design` is now a thin adapter onto the shared function;
ADR-206's own tests pass unchanged, proving the extraction preserved behaviour.

**The work order's own §4 registered prediction — that N=4 free-`sp` selection
lands in ADR-199's 2-block range (6.9e-04 to 9.8e-04) — is REFUTED at both tiers**:
`max_abs_log10_sp_diff=0.7766` (tier 1) / `0.6398` (tier 3), three orders of
magnitude larger, concentrated in the by-term's block. PLAN §6's *separate*
registered prediction — "edf agrees far better than sp does" — holds again:
`edf_total_diff` is ≈4% against `sp`'s near-full-decade disagreement.

**The refutation's original diagnosis was corrected same-day (PR #212 review
[P1]).** The first pass (two checks, both reading only OUR OWN already-verified
criterion at mgcv's point and Python's point) concluded "a flat REML surface,
optimiser-path-sensitive, no criterion gap" — but that inference could not
distinguish that from an `sp`-dependent criterion discrepancy the review named
explicitly. The discriminating measurement (`scripts/gam_multiterm_sp_delta_probe.R`,
new, diagnostic-only): read `mgcv`'s OWN score at both points too.
**`mgcv`'s own criterion and ours rank the two points in OPPOSITE order** —
`mgcv`'s point scores *better* under its own criterion (`delta_mgcv=-0.1214`)
but *worse* under ours (`delta_ours=+0.7252`). That is real evidence of an
`sp`-dependent criterion discrepancy specific to this N=4-block, `ti()`
-sharing-a-column-span structure — ADR-196/197's own 2-block, disjoint-support
verification never had the structure to catch it. **CONFIRMED at tier 3, same
day**: `scripts/gam_multiterm_sp_delta_probe.R` re-run on the pinned oracle
(mgcv 1.9.4, CI run 32874213883) reproduced `delta_mgcv=-0.121389` identical
to tier 1 at every printed digit — the sign flip is a real, reproducible
finding on the production oracle, not a tier-1 or BLAS artefact. See ADR-208's
amendment for the full measurement and the named next hypothesis (Wood 2011
§3.1's log-determinant machinery, previously ruled out for ADR-196's
disjoint-support fixture for a reason that does not hold for `ti()`'s
overlapping penalty blocks). **Still do not designate slice 6** — confirming
the discrepancy is real is not the same as localising or closing it, and the
next hypothesis has not been tested. Building a fourth basis's own `sp`
selection on top of a CONFIRMED, still-unlocalised `sp`-dependent discrepancy
would compound rather than isolate the next disagreement.

An INDEPENDENT comparison that disagreed is still the routine's own definition
of a successful session — the correction is about WHY, not about whether this
was worth reporting.

**LOCALISED, 2026-08-25 — at TIER 1 ONLY, so no figure from it appears in this
file.** The named next hypothesis has been tested and it holds, qualitatively:
evaluating **both criteria at the same fixed `sp`** removes the optimiser from the
comparison entirely, and the difference `ours − mgcv` is **not constant** — so the
discrepancy is in the criterion, not the search. It departs only where the λ's span
many decades, which is the signature of a rank decision flipping rather than a wrong
formula term, and `gam_reml.reml_score_general` cuts `log|S|₊`'s null space at a
fixed relative tolerance. Correcting only that cut collapses the difference to a
constant and removes the ranking flip. This is Wood (2011) §3.1's **"numerical zero
leakage"**, whose own trigger condition — the ratio of the largest positive
eigenvalue of the dominant `λᵢSᵢ` to the smallest positive eigenvalue of a
subordinate one being too great — is what the spread-λ configurations hit.

**Every number from that measurement lives in
`docs/RECALIBRATION_mgcv_parity_2026-08-25.md` §1, which is a tier-1 session
record.** They are deliberately not repeated here: this file is TIER 3 ONLY
(`ROUTINE_MGCV_PARITY.md` — *"a CONTINUATION is the first thing the next session
believes"*). Slice 5c's sequencing step 1 is the tier-3 re-measurement that would
make them citable.

**The work is registered as PLAN slice 5c**, which carries Wood's Appendix B
algorithm in implementable detail, the scope boundary (fix the determinant only;
do not adopt the reparameterisation through the fitter), and a registered
prediction. `1e-12` is *not* the fix — that is the tuned constant Anchor 8
forbids, and Wood rules the tolerance approach out explicitly:
*"re-parameterization is preferable to simply limiting the working λ range."*

> **Slice 5c is DONE, 2026-08-29 (ADR-210, tier 1 AND tier 3 confirmed identical,
> CI runs 33267701996/33267879635).** Both defects — `log|S|₊`'s null-space cut
> (Appendix B, built whole: the similarity transform, the pivoted-QR determinant,
> the stable square root `E`) and the score's use of the expected/Fisher Hessian
> where Wood eq. (4) needs the observed one (`Family.observed_information_weight`,
> analytically exact `alpha_i=1` for both canonical links this module defines) —
> are fixed in the ACTUAL production `reml_score_general`, not a diagnostic
> replica. The eight-point fixed-`sp` spread against `mgcv` collapses from
> **3.910776** (raw, shipped defect) to **4.271e-07** (tier 1) / **0.000000 at
> tier 3's print precision** — float round-trip precision, identical at both
> tiers, ~9.2 million times smaller than the standing defect. Mutation-tested:
> 2 of 6 mutations caught by dedicated tests (skip the pre-step; transpose the
> accumulated `Q_s`), 4 NOT caught by any fixture tried including the target
> model's own real four-block structure — recorded as an honest test-coverage
> gap in ADR-210 rather than papered over.
>
> **The work order's §4 registered prediction lands on its THIRD branch, and
> this is the session's most important finding.** Fixed-`sp` closes exactly as
> predicted. Free-`sp` selection on ADR-208's own N=4 structure does NOT follow
> it there: `max_abs_log10_sp_diff` reads 0.7560 (tier 1) / **1.0996 (tier 3 —
> WORSE than the 0.6398 pre-fix reading)**. But the discriminating measurement
> (score both sides' points under our OWN now-correct criterion) shows `mgcv`'s
> own selected point scoring measurably BETTER than our optimiser's own
> converged point (612.611 vs 612.663, tier 1) — **this is an OPTIMISER
> CONVERGENCE finding, not a criterion-formula one.** ADR-208's amendment had
> attributed the N=4 free-`sp` disagreement to the criterion; that diagnosis is
> now superseded for the *residual that remains after the criterion is fixed* —
> the criterion itself is settled (float precision, both tiers), and what is
> left is `select_lambdas_continuous`'s own convergence on this specific
> `by`-term-dominated landscape.
>
> **Registered as PLAN slice 5d**, which is what unblocks slice 6 now — not 5c
> a second time. Two live hypotheses (optimiser precision on a weakly-identified
> `lambda`, versus a genuinely multi-modal surface `mgcv`'s own Newton-based
> optimiser navigates differently than SciPy L-BFGS-B does), a cheap tier-3
> discriminator named before either needs new code, and an explicit escalation
> note per slice 5c's own DoD (a third-branch outcome reopens the epic's cost
> estimate — this is a fact for the maintainer, not a session's call to absorb
> silently). **Slice 6 stays blocked** — see slice 5d's own entry for why the
> blocking reason changed rather than lifted.

> **Slice 5d done the SAME DAY as 5c (ADR-212).** Both hypotheses were
> distinguished with evidence, at both tiers, without building the analytic
> gradient hypothesis 1 had named as available. The cheap tier-3 step
> confirmed the tier-1 reading exactly and, since the fixed-`sp` spread is 0
> everywhere, mechanically ruled out "the two criteria disagree" — leaving
> purely an optimiser question. An interpolation sweep between the optimiser's
> converged point and `mgcv`'s point found a single smooth, monotonic surface
> (no barrier), refuting genuine multi-modality for this pair of points. A
> forward-difference step scan at the "converged" point localised hypothesis
> 1's exact mechanism: SciPy's L-BFGS-B default step (`1.49e-8`) sits inside
> the noise floor the nested penalized-IRLS solve creates, so the reported
> "convergence" had a true residual gradient of `~0.55`, not the near-zero
> SciPy's own noisy estimate implied. **Fixed** by deriving
> `gam_reml_optimize._FINITE_DIFF_STEP = 1e-5` from this module's OWN measured
> noise floor — never from a comparison against `mgcv` — and wiring it into
> the one `scipy.optimize.minimize` call. Confirmed at both tiers: `mgcv`'s
> own criterion now ranks Python's default-start point within `0.0007` of its
> own optimum (was `0.0523`, ~78x tighter), `eta` agreement improves to
> `~8e-4` (from `3.7e-2`), `edf_total` to `~0.015-0.018`. **But the raw
> `max_abs_log10_sp_diff` metric swings 3.4x between tiers** (`0.8777` tier 1,
> `0.2606` tier 3) **while `eta` barely moves** — the decisive evidence for a
> third finding: the by-term's own smoothing parameter is weakly identified
> by this criterion on this fixture, so different converged runs (and
> different R builds' own selections) land at different values along a
> near-flat direction without disagreeing about the fitted model.
> **Slice 6 is now UNBLOCKED** (PLAN's own entry restated accordingly) on the
> finding that the remaining gap is understood, not merely observed. One open
> question carried to the maintainer: whether `FREE_SP_MODEL_CLAIM`'s primary
> metric should be revisited to weight `eta`/`edf` over raw `log10(sp)` given
> this finding (ADR-212 Consequences) — see "Open questions" below.

> **Slice 5d is DONE, 2026-08-29 (ADR-211), and both hypotheses resolved —
> Slice 6 is UNBLOCKED.** Slice 5d's own cheap first step (re-measure the
> discriminator at tier 3) surfaced something the slice did not anticipate:
> a single unpinned degree of freedom in the Python side's own environment
> — OpenBLAS thread count — moves the free-`sp` residual (by-term
> `log10(sp)`: 9.116 / 8.519 / 8.773 at 1/2/4 threads) by more than the
> entire gap under investigation, while a FIXED-sp evaluation of the
> identical criterion moves by `~4e-10` across the same thread counts. This
> fully explains why ADR-210's own tier-1 (0.7560) and tier-3 (1.0996)
> readings of "the same" measurement disagreed — the criterion is
> thread-independent, the SEARCH is not. **The decisive discriminator:**
> warm-starting `select_lambdas_continuous` at `mgcv`'s own free-`sp`
> selection converges back to it (within `1e-6`) at a score **0.052286
> BETTER** than the blind, bounds-centre default start's own result.
> Hypothesis 2 (`mgcv` reaching somewhere ours structurally cannot) is
> REFUTED — the identical starting point reaches the identical, better
> point. Hypothesis 1 (optimiser convergence precision on a
> weakly-identified `lambda`) is CONFIRMED, with the thread-count table as
> the precise mechanism rather than a vague "the surface is flat." A blind,
> non-cheating multi-start check (9 starts, no information from `mgcv`)
> reaches 612.6149 at best — closer than the single default start's
> 612.6630 but short of `mgcv`'s reachable 612.6108, and 2 of 9 far-corner
> starts fail to converge outright. **Confirmed at tier 3, same day** (CI
> run 33279913273, oracle `sha256:0d54c192…` build 8): warm start lands
> within `1.09e-4` of `mgcv`'s point at score `612.610760` — identical to
> the tier-1 reading's last printed digit — `0.030862` better than a blind
> start that this run reports `converged=False` outright. A second,
> independent host (a GitHub Actions runner vs. this session's own
> container) landing on a DIFFERENT, non-converging blind result at the
> identical pinned thread count is a second, independent confirmation of
> hypothesis 1, not a weaker reading of it. **This does not by itself fix
> the production search** — it is registered as PLAN slice 5e, a real,
> unfixed, and now precisely characterized engineering gap that will only
> get harder at the target's 13-21 blocks, and is flagged below as an open
> question for the maintainer per the same escalation practice slice 5c
> used.

> **Slice 5e is DONE, 2026-08-30 (ADR-213).** `select_lambdas_continuous_multistart`
> — best-of-9, deterministic starts (`numpy.random.default_rng`, pinned
> seed, ADR-074), the same "adds no new formula" discipline every function
> in this search's own family follows — turns ADR-211's own one-off blind
> multi-start check into a reusable production-available building block.
> Measured, thread-pinned, at two points (the N=4 and N=8 structures —
> three `OPENBLAS_NUM_THREADS` settings each), **making no mgcv comparison
> anywhere** (there is no second producer for ADR-193's mechanical test to
> apply to — an internal robustness measurement, the same class ADR-211's
> own BLAS-thread table already was). **At N=4 (the actual ADR-211/212
> fixture): single-start's own score spread across all three thread counts
> is `0.001483`, best-of-9's is `0.000006` — a ~247x tighter reproducibility
> band.** At 4 threads the single bounds-centre start does NOT converge
> (`success=False`, score `612.6115`); at 2 threads it reports
> `converged=True` but still lands on its own worst reading of the three —
> a "successful" termination is not itself evidence of a good point on this
> surface. Best-of-9 finds the same converged, better point at every thread
> count — a real, reproducible improvement on the exact structure the
> slice's acceptance criterion was registered against. **At a synthetic
> N=8 stress case** (PART 1's own three-term shape duplicated onto a
> second, covariate-DECOUPLED draw — chosen after reusing
> `AttdAge`/`PolYear` under more `by`-scalings produced an exactly singular
> design first): **single-start already sufficed at every thread count
> tested** (three) — the opposite of what motivated the slice, and a
> genuine answer rather than a null result; its own spread (`0.001180`) is
> essentially equal to best-of-9's (`0.001165`), unlike N=4's 247x gap.
> Cost: best-of-9 runs ~8-21x a single search's own function evaluations, across all three thread counts.
> **Registered as PLAN slice 5f, not blocking**: ADR-213's own N=8 case was
> deliberately covariate-decoupled (to rule out the rank-deficiency its
> first attempt hit), so it says nothing about a structure where the extra
> blocks SHARE covariates the way the target formula's own 13-21 blocks
> mostly do — that measurement remains open. See ADR-213 for every number.

> **Slice 5f is DONE, 2026-08-31 (ADR-214).** Built the covariate-SHARING
> N=8 structure ADR-213 flagged as untested: the N=4 fixture's own
> `ref`+`by`+`ti` plus four `s(x, by=Group)` terms (two on `AttdAge`, two
> on `PolYear`, standing in for the target's own four `sz(factor,
> AttdAge/PolYear)` terms without building `sz`'s own constrained
> construction). A first two-indicator draft (reusing one indicator across
> an `AttdAge` term and a `PolYear` term, mirroring `FaceSize`/`Smoke`
> literally) was exactly rank-deficient by 2, SVD-confirmed — an
> unconstrained `by`-scaled `cr` basis always contains the constant
> function in its span (ADR-200), so two terms sharing one indicator each
> contain that indicator's own direction. Fixed with four independent
> indicators; measured full rank and well-conditioned before use.
> **At all three thread counts (1/2/4), single-start converged and
> matched best-of-9 EXACTLY — gap `0.000000` throughout — and the
> thread-to-thread spread (`0.000656` for both) is the SMALLEST of any
> structure measured across slices 5e/5f**, tighter than both of ADR-213's
> own readings (N=4: 0.001483/0.000006; decoupled N=8: 0.001180/0.001165),
> not between them. **ADR-213's own registered reading question —
> "does this structure's spread sit closer to N=4 than to decoupled N=8,
> evidence covariate-sharing drives the pathology" — is answered in the
> negative**: this specific covariate-sharing construction is MORE stable
> than either prior reading, the opposite of what that hypothesis
> predicted. One feature partially persists regardless of structure: the
> MI by-term sits exactly on the search's own upper bound at 2 of the 3
> thread counts on this structure (at 1 thread it lands at `10.859`,
> `at_bound=False` — PR #219 review [P1-1], corrected from an earlier
> "at every thread count" overstatement) — present, but on this structure
> it does not propagate into whole-search score instability. Cost:
> best-of-9 ~9x-15x a
> single search's own evaluations, inside ADR-213's stated range. Caveat
> named: this is one covariate-sharing construction (independent
> `by`-indicators, not `sz`'s own constrained parameterisation) — evidence
> about the outer search's robustness, not a preview of `sz`'s own basis
> behaviour (slice 6). No mgcv comparison anywhere in this ADR, the same
> status ADR-213 declared for its own measurements. See ADR-214 for every
> number.


**Total slices:** **7** autonomous, plus slice 1b (inserted 2026-08-16), slice 5b
(inserted 2026-08-24/25, ADR-207/ADR-208), slice 5c (inserted 2026-08-25, DONE
2026-08-29, ADR-210), slice 5d (inserted 2026-08-29, DONE 2026-08-29 — resolved
concurrently by ADR-212 (PR #216) and ADR-211 (PR #217), which unblock slice 6),
slice 5e (inserted 2026-08-29, DONE 2026-08-30, ADR-213 — best-of-9 multi-start
built, recovers a real N=4 convergence failure, no mgcv comparison anywhere in
the slice), slice 5f (inserted 2026-08-30, DONE 2026-08-31, ADR-214 — the
same N>4 question on a covariate-SHARING structure; single-start already
sufficient there too, and the most stable structure measured across either
slice), slice 6b (inserted 2026-08-31, DONE the same day, ADR-216 — the
Stage-B multi-term fit including an `sz` term) plus one deferred to a later
epic.
**Estimated scope:** the largest numerical undertaking in the project.

**Slice 6 (`bs = "sz"`) is DONE FOR STAGE A, 2026-08-31** (ADR-215, tier 1
AND tier 3 confirmed identical, CI run 33353326193 — `docs/CONFORMANCE_LEDGER.md`
carries the reading). `gam_basis_cr.sz_basis` — a single-factor construction
independently re-derived from `mgcv`'s own measured behaviour (the raw,
un-rescaled per-level `cr` block tensored against a factor-level indicator,
one shared `scale.penalty` factor, then a contrast-against-the-last-level
constraint, `M = D ⊗ I_k` — NOT a transcription of `mgcv:::XZKr`, which has no
closed-form statement anywhere `mgcv` documents) — agrees with
`smoothCon(bs="sz", absorb.cons=TRUE)` to float round-trip precision (~1e-14)
on `design_X`, every `penalty_S` block and `rank`, on a synthetic three-level
case and the target formula's own `AttdAge` (k=13) / `PolYear` (k=6) knots at
two levels (matching `FaceSize`/`Smoke`). `SZ_BASIS_CLAIM` declares all three
`INDEPENDENT`. **PLAN §6's own "hardest basis" prediction did not bite Stage
A** — the cost was entirely in *understanding* `mgcv`'s constraint machinery
(the `object$C <- c(0, nf)` sentinel routing `smoothCon()`'s `absorb.cons`
step into a branch no other basis in this repo uses), not in getting the
numbers to agree once that understanding existed; no iteration was needed.
**Scope: single factor, no `id`** — every one of the target's four `sz` terms
fits this exactly.

**Slice 6b (`sz` Stage B) is DONE, 2026-08-31, the same day** (ADR-216, tier 1
AND tier 3 confirmed, CI run 33393744694). `gam_model.assemble_model_design`
now dispatches `basis="sz"` (via `TermSpec.n_levels`, an explicit input never
derived from a sample's own observed factor codes, Anchor 4), alongside the
`cr`/`ti` dispatch slice 5b already built — the third and, for the target
formula's own vocabulary, final basis this function needed. `gam_multiterm_sz_conformance.py`
assembles and fits `s(AttdAge,k=13,bs="cr") + s(FaceSize,AttdAge,k=13,
bs="sz",xt=list(bs="cr"))` — the target formula's own first `sz` term
verbatim, at its own `AttdAge` k=13 knots (ADR-215's own
"sz-target-attdage-k13" case) — at a fixed `sp`, agreeing with `mgcv`'s
native fit on `eta` to `3.921e-12` (tier 1) / `3.912e-12` (tier 3), first
measurement, no iteration needed — the same shape ADR-206's own first
multi-term result had (`1.242e-10`). `SZ_MULTITERM_CLAIM` declares `eta`
INDEPENDENT. **Not built, named rather than silently skipped:** extending
`select_lambdas_continuous` to an `sz`-shaped block structure (one smoothing
parameter per factor level); a model combining `sz` with `ti`/`by`; a model
with more than one `sz` term. See ADR-216.

**Every basis PLAN §1 named as required (`cr`, `ti`, `sz`, plus a
numeric-`by`-scaled `cr`) now has both an INDEPENDENT Stage-A AND an
INDEPENDENT Stage-B result.** What remains before the target formula's full
eight-term structure can be assembled, fit and have its own smoothing
parameters selected: extending the outer search to an `sz`-shaped block
structure, combining `sz` with `ti`/`by` in one model, and slice 7
(`select = TRUE`).

> **This is the ACTIVE epic.** `CONTINUATION_penalized_mi_surface.md` is superseded from
> its slice 6 onward and all of its remaining slices are PARKED. A routine run selecting
> work should land here.

## Overall goal

Fit the maintainer's selected model form — 110 coefficients, 8 smooth terms, 13-21
smoothing parameters, binomial/`cloglog` on a proportion response with prior weights and
hand-chosen non-uniform knots — in Python, verified term by term against `mgcv`. The
existing penalized IRLS core carries over and is already verified to 5e-13; **the basis
layer is a rebuild.** PLAN §1 has the target verbatim and the measurements that size it.

## Slices

1. **The Stage-A harness, and a term spec to hang it on** — **DONE (raw path only),
   2026-08-15b.** The mgcv-native half is slice 1b, not slice 2 — PR #197 review found
   that deferring it to slice 2 rested on a premise that doesn't hold (the referent it
   needs already exists and is already tier-3-green, ADR-191). See
   `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`.

   **Done:** `src/polaris_re/analytics/gam_term_spec.py` — `TermSpec` / `ModelSpec`
   (Anchor 3), matching the target formula's own basis vocabulary (`cr`, `ti`, `sz`,
   plus `raw` for the existing paraPen-supplied tensor). 22 tests.

   **Done, and settled rather than deferred:** the one risk PLAN §5.1 named —
   `predict(type="lpmatrix")` is post-reparameterisation, `smoothCon()` is pre- unless
   called with `absorb.cons=TRUE`, and which one Stage A compares against changes what
   "our `X` equals `mgcv`'s `X`" means. **They are the same object, not two competing
   referents.** `predict.gam` dispatches to `PredictMat` on the smooth `gam.setup`
   built with `absorb.cons=TRUE`, so `smoothCon(..., absorb.cons=TRUE)$X` reproduces
   `lpmatrix`'s corresponding block **bit-exactly** — measured at tier 1 (R 4.3.3 /
   mgcv 1.9.1) and re-measured identical to the last printed digit at **tier 3** (R
   4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192…`, run 31907362222) via
   `scripts/smoothcon_lpmatrix_probe.R`, wired into `mgcv-conformance.yml` as a
   diagnostic step alongside ADR-190's `ks_formula_probe.R`. `docs/CONFORMANCE_LEDGER.md`
   carries both readings. **Decision: Stage A's referent is
   `smoothCon(..., absorb.cons=TRUE)`** — it needs no fitted model, which is what makes
   an isolated-term harness possible, and PLAN §5.1's weaker column-space fallback is
   not needed. Recorded in ADR-191.

   **Done (2026-08-15b):** the R-side per-term extractor (`scripts/gam_term_extract.R`)
   and its Python comparator (`src/polaris_re/analytics/gam_stage_a.py` —
   `TermExtract`, `extract_raw_terms`, `compare_term_extract`), proven on the existing
   verified `raw`/`paraPen` basis first (Anchor 1's "known-good basis before a new
   one"). That basis has no `smoothCon()` equivalent (`paraPen`-only fits have an empty
   smooth list), so both sides read what the fit actually used rather than a basis
   recipe: the R side reads `m$paraPen$S` / `m$paraPen$rank` off the fitted object
   (not the exchange's own TSVs, which would prove nothing about mgcv's bookkeeping),
   and the Python side reads the already-fitted `DesignExport`. Agrees exactly (design
   diff at float round-trip noise ~5e-16, `S` diff `0.0`, rank diff `0`, index ranges
   agree) across both `d1` (tensor only) and `d2` (tensor + factor block), at tier 1 and
   confirmed at **tier 3** (CI run 31915145674, both jobs green in 55s;
   `docs/CONFORMANCE_LEDGER.md` carries both readings). Caught one real bug in the R
   script's own harness proof — the factor term's JSON key didn't match its label —
   which is exactly what "prove the harness on a known-good basis first" is for.

   **Explicitly deferred, not attempted here — and re-scoped to slice 1b, not slice 2
   (2026-08-16 correction):** mgcv-native extraction (`cr`/`ti`/`sz` via
   `smoothCon(..., absorb.cons=TRUE)`, per ADR-191's referent decision).
   `extract_raw_terms` only handles `basis="raw"` and raises if handed anything else.
   The original reasoning — building the mgcv-native path now would be speculative work
   "with nothing yet to verify it against" (Anchor 8) — **does not hold**: the referent
   is `scripts/smoothcon_lpmatrix_probe.R`, already committed and already tier-3-green
   (ADR-191, run 31907362222). What's missing is packaging the existing per-term JSON
   schema through that referent, not new verification, so Anchor 8 doesn't block it and
   it doesn't need to wait for a Python `cr` basis. Slice 1b's own scope is that
   packaging; slice 2 narrows to the actual math question (does Python's `cr` basis
   match mgcv's).

1b. **mgcv-native per-term extraction** — **DONE, 2026-08-16** (harness: every
    compared quantity is TRANSPORT, ADR-193 — see the note under slice 2).

    Spec: `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`. Shipped: a `smoothCon`
    branch (`extract_smooth_one`) in `scripts/gam_term_extract.R` emitting the
    existing per-term schema (`label`/`index_start`/`index_end`/`X`/`S`/`rank`/`knots`)
    for three isolated `bs="cr"` cases (default knots `k=8`/`k=13`, supplied knots
    `k=8`), with the probe's own cross-check (against `predict(type="lpmatrix")` and
    `m$smooth[[j]]`) promoted from a one-off diagnostic into the extractor's standing
    internal guard — it now `stop()`s the script if it ever stops agreeing. Python
    side: `extract_smooth_terms()` (`gam_stage_a.py`) packages the R payload directly
    into `TermExtract` — there is no independent Python `cr`/`ti`/`sz` basis yet, so
    this is packaging, not re-verification — and `compare_term_extract` now compares
    `knots`, which slice 1 accepted but never compared. **The index-range design
    question is settled as ADR-192**: assigned by the harness assembling a term into a
    model, not read off a fit — the model an isolated Stage-A case assembles *is* the
    one term, so its range is `[0, width)`, mirroring how `extract_raw_terms` already
    treats index ranges as inputs from the assembled `DesignExport` rather than
    something read off `mgcv`.

    **Caught one real bug**, exactly what Anchor 1's "prove the harness first"
    discipline exists to catch: jsonlite's `auto_unbox` silently collapsed the
    single-penalty `rank = sm$rank` (a length-1 vector) to a bare JSON scalar, and the
    Python side's `for v in r_term["rank"]` raised `TypeError`. The `raw` path never
    hit this because it always carries two penalties. Fixed with `rank = I(sm$rank)`.
    Tier 1 and tier 3 both confirmed (`docs/CONFORMANCE_LEDGER.md`) — tier 3 read the
    R script's `stop()`-gated guard and the Python packaging's exception-freedom on
    the pinned image, not the per-metric diff table (blocked by this environment's
    egress policy on the artifact host); the ledger states that boundary explicitly.
2. **`bs = "cr"`**, with supplied and default knots. Depends on slice 1b (done), not
   slice 1 — Stage A needs the mgcv-native extractor to check this basis against.
   **DONE, 2026-08-17** (ADR-194).

   **The epic's first genuine Stage-A PARITY slice (ADR-193).** Slices 1 and 1b were
   harness: slice 1's `X`/`S` are ECHO, slice 1b's columns are all TRANSPORT. Slice 2
   built the missing Python producer — `src/polaris_re/analytics/gam_basis_cr.py`,
   Wood's natural-cubic-spline construction, with every non-textbook detail (default
   knot placement, the `colMeans`-QR identifiability constraint, `smoothCon`'s own
   penalty rescaling) read directly out of `mgcv`'s R source rather than guessed. It
   agrees with `smoothCon(bs="cr", absorb.cons=TRUE)` to float round-trip precision
   (~1e-14) on 5 cases, including PLAN §1's own `AttdAge`(k=13)/`PolYear`(k=6) knot
   vectors, not just the harness's original synthetic ones. `CR_BASIS_CLAIM`
   (`gam_stage_a.py`) declares `design_X`/`penalty_S`/`rank` `INDEPENDENT`, and
   `require_parity_evidence` gates the claim — `knots` is checked separately
   (`compare_term_extract`) rather than folded into the claim, because it is ECHO,
   not INDEPENDENT, in the 3 supplied-knot cases (PR #201 review [P1], ADR-194
   amendment). Extrapolation beyond the knot range is explicitly unverified (module
   docstring) — needed before real-data knots that don't span the data range. See
   ADR-194 and `docs/CONFORMANCE_LEDGER.md`.
3. **Families, links and weights** — binomial `cloglog`/`logit` on a proportion with prior
   weights, quasi-Poisson with `φ` estimated, Poisson with a log offset. Independent of 2.
   **DONE, 2026-08-17** (ADR-195).

   **The epic's first Stage-B PARITY slice outside Poisson (ADR-193).** `gam_family.py`
   declares the `Family`/`Link` abstraction — standard GLM IRLS theory (Wood §3.1.2), not
   `mgcv`-internal machinery, so no R-source archaeology was needed the way the `cr` basis
   required. `gam_fit.py`'s `penalized_irls_general` generalizes the penalized IRLS
   recursion from `experience_gam_penalized._penalized_irls` (Poisson-log-offset only, left
   untouched per Anchor 7) to an arbitrary family/link with prior weights, proven to reduce
   to that already-verified function bit-for-bit at `S = 0` and under a real penalty before
   any R round trip was spent, and cross-checked against an independent `statsmodels` GLM
   for both binomial links. `gam_family_conformance.py`'s `FAMILY_CLAIM` declares `eta` and
   `dispersion` `INDEPENDENT` — `fit_family_case` reads only the shared recipe off
   `scripts/gam_family_probe.R`'s payload (a deterministic shared design it builds itself,
   `set.seed`, ADR-074), never the R side's own `eta`/`coef`/`dispersion`. Confirmed at
   tier 3 (CI run 32057694949): all four combinations (`binomial-logit`, `binomial-cloglog`,
   `quasipoisson-log`, `poisson-log-offset`) agree to float round-trip precision (~1e-14 on
   `eta`) on the first measurement — no iteration needed, same shape of result as ADR-194's
   `cr` basis. Coefficients are never compared (Anchor 2, restated for Stage B). `cloglog`'s
   non-canonical-link concavity gap is recorded rather than assumed (ADR-195 decision 3) —
   it did not bite this slice's measurement, but a harder-conditioned future case could
   still disagree, and that would be a real result, not a bug in this slice. See ADR-195
   and `docs/CONFORMANCE_LEDGER.md`.
4. **The outer optimisation — N-dimensional (f)REML.** The prerequisite for everything
   multi-term, and the largest single piece of work. **IN PROGRESS.**

   **Part A DONE AND RESOLVED, 2026-08-18** (ADR-196): `gam_reml.reml_score_general`
   generalizes the already-verified Poisson-only, two-hardcoded-block `reml_score` onto
   `gam_fit`'s general IRLS core — known-scale families (binomial included;
   quasi-Poisson's estimated-dispersion criterion is a different formula the target
   formula never needs), any number of independently-scaled penalty blocks (via their
   caller-summed `S_lambda`). **Measured against `mgcv` on a shared two-block
   binomial/logit design at three fixed `(sp1,sp2)` points, compared on PAIRWISE SCORE
   DIFFERENCES** (not the absolute value — ADR-189 amendment 1 already found an
   unresolved offset there for the single-block Poisson case; differencing cancels any
   purely additive offset and is what an optimiser needs anyway).

   **First measurement: DISAGREED.** The fit itself was correct (a committed,
   INDEPENDENT `deviance` comparison matched `mgcv` to ~1e-11 at every point) but the
   score's dependence on `(sp1,sp2)` did not match `mgcv`'s — all three pairwise
   differences missed the declared 1e-6 tolerance, identical at tier 1 and tier 3. The
   original next-hypothesis (a multi-penalty log-determinant numerical-stability issue,
   Wood 2011 §3.1) was corrected same-day by PR #203 review [P1-3] after being found
   circular.

   **Resolution, same day: the maintainer supplied Wood (2011) directly.** §2 eq. (4)
   names the actual missing piece — the criterion needs the PENALIZED deviance
   `Dp = D(beta_hat) + beta_hat^T S beta_hat`, not the plain deviance the first
   generalization used (verbatim from the old module, which appears to have the
   identical omission — see below). Adding the missing term closed the gap to float
   round-trip precision (~1e-12) on all three pairs, tier 1 and tier 3 identical (CI run
   32142352655). `REML_SCORE_CLAIM`'s two declared quantities (`reml_score_pairwise_diff`,
   `deviance`) are both INDEPENDENT and both now agree — the epic's first Stage-C
   parity result of this kind. §3.1's numerical-stability machinery turned out to be
   inapplicable to this fixture for a well-grounded reason (its two blocks have
   disjoint column supports, so no cross-block "zero leakage" is possible), not merely
   coincidentally matching at two points. See ADR-196's resolution section and
   `docs/CONFORMANCE_LEDGER.md`.

   **Part B's gate — `docs/WORK_ORDER_reml_penalized_deviance_production_check.md` —
   HAS RUN, 2026-08-18** (ADR-197, tier 1 and tier 3 identical, CI run 32181109927).
   `experience_gam_penalized.reml_score` — the ALREADY-SHIPPED, production
   tensor-MI-surface REML score `select_lambdas_reml`'s 2-D grid actually uses — DOES
   carry the identical omission (confirmed, not merely suspected by inspection). §3.1
   (the raw/offset-adjusted score gap at each side's own mismatched free-sp point) does
   NOT collapse — it roughly doubles, a named limitation of comparing at mismatched
   points, not a refutation. **§3.2 — the decisive, registered-in-advance measurement —
   HELD on all three free-sp cells**: a diagnostic replica of `select_lambdas_reml`'s
   own grid search, re-scored with the corrected criterion, selects a point measurably
   CLOSER to `mgcv`'s own free-sp selection everywhere tested (log10 distance
   0.31→0.07, 0.19→0.11, 0.46→0.12), and independently reproduces the exact grid-step
   move (`l2-free-sp`: λ_age 3162.28→5623.41) a maintainer-run local patch-and-refit
   experiment already found — a second, structurally different confirmation. §3.3: the
   correction shifts `smoothing_uncertainty`'s finite-difference Hessian materially
   (~25-40% on eigenvalues) but the resulting inflation-ratio move is small relative to
   ADR-190's separately-characterized 3.2-4.1x gap — **this bug is not a material
   contributor to the standing level-4 BLOCKER.**

   **RESOLVED, 2026-08-19 (ADR-197 amendment, maintainer-authorized):** the maintainer
   explicitly authorized the fix ("Proceed to fix `experience_gam_penalized.reml_score`
   the same way ADR-196 fixed `gam_reml.reml_score_general` (add the missing term)").
   Applied — same pattern, same Wood (2011) §2 eq. (4) citation — and
   `data/mgcv_exchange/synthetic/python_reference.json` re-baselined via its own
   regeneration path (`export_mgcv_case.py`, not hand-edited), moving exactly as §3.2
   predicted. `tests/qa/golden_outputs/` reconfirmed byte-identical after the ACTUAL fix
   (`git diff` empty), not merely the prior diagnostic-patch measurement. Full details,
   the exact delta, and the re-run ten-cell conformance measurement are in ADR-197's
   2026-08-19 resolution amendment.

   **Slice 4 part B is now unblocked to proceed, regardless of that decision** — the
   outer search builds on `gam_reml.reml_score_general`, which was already correct
   before ADR-197's session ran; the production 2-D grid selector's own status was the
   thing being gated on, and it is now measured rather than merely suspected.

   **Part B's first slice DONE, 2026-08-22** (ADR-199, tier 1 AND tier 3 confirmed):
   `gam_reml_optimize.py`'s `select_lambdas_continuous` — a Newton/quasi-Newton search
   (SciPy L-BFGS-B) over `log10(lambda)` for any number of independently-scaled penalty
   blocks and any known-scale family, built on `gam_fit.penalized_irls_general` and
   `gam_reml.reml_score_general` alone (no new fitting or scoring formula). This is
   ADR-198's own decisive test, and it **HOLDS, decisively**: on the same four
   free-sp cells ADR-198 measured post-fix, `max_abs_log10_sp_diff` against `mgcv`'s
   own free-sp selection collapses from the grid's 0.0645/0.0791/0.1048/0.0776 to
   (tier 3) 6.9e-04/5.1e-05/1.7e-04/9.8e-04 (SciPy `converged=True` on all four,
   identical in verdict at tier 1) — the residual ADR-197's fix left behind was grid
   quantisation, not a remaining criterion difference. `CONTINUOUS_LAMBDA_CLAIM`
   (`gam_reml_optimize_conformance.py`) declares both `max_abs_log10_sp_diff`/`edf_total`
   INDEPENDENT. `select_lambdas_reml` and every other production entry point are
   untouched (PLAN Anchor 7) — this is a genuinely separate search, per ADR-198's own
   "Two searches, not one". Confirmed at tier 3, CI run 32544930172, oracle
   `sha256:0d54c192…` build 8 — required levels 1-3 of the ten-cell suite also still
   agree on this run, no regression from the workflow edit. **Tested only at N=2**
   (the existing ten-cell suite's own `d1`/`d2`/`d3` designs) — the search is written
   to accept any block count, but nothing has
   exercised it beyond 2 yet; extending to a real multi-term model (13-21 blocks)
   needs a multi-term mgcv-native model, which is slice 5 onward's own work.
5. **`ti()` and the varying-coefficient MI term.** Ship the MI term first if they split.
   **DONE, 2026-08-24** (ADR-206 closes the remaining multi-term Stage-B scope below).

   **The MI term's own basis is DONE (Stage A only), 2026-08-22** (ADR-200, tier 1 and
   tier 3 both confirmed, CI run 32571764900, identical to the printed digit). `mgcv`
   absorbs **no identifiability constraint at all** on a numeric-`by` smooth — measured
   before writing any code (`smoothCon(s(x, by=z, bs="cr", k), absorb.cons=TRUE)$C` has
   zero rows), not guessed — so the by-term's design is the *unconstrained* `k`-column
   `cr` basis with each row scaled by the by-variable, and its penalty is that same
   unconstrained `S`, untouched by the scaling. `gam_basis_cr.by_scale_design` (new) plus
   a branch in `build_python_cr_term`; `gam_term_extract.R` gained a `with_by` branch and
   one case (`mi-term-attdage-by-k13`, the target's own `AttdAge` k=13 knots). Agrees at
   `max_X_diff=2.176e-14`, `max_S_diff=3.775e-15`, `rank_diff=(0,)` — same order as slice
   2's other five cases. Carries its own `CR_BY_BASIS_CLAIM` (same three
   INDEPENDENT quantities as `CR_BASIS_CLAIM`, but every producer string differs —
   the by-branch skips the constraint absorption and mgcv is called with `by=z`;
   split out same-day after PR #206 review [P1], no measured value affected). ADR-191's `smoothCon`-vs-`lpmatrix` internal guard
   re-passed on the by-construction with no changes (the `s(x):z.N` column names still
   match its existing grep).

   **`ti(AttdAge, PolYear)` is now also DONE (Stage A only), 2026-08-24** (ADR-205, tier 1
   and tier 3 both confirmed, CI run 32677470292, identical in order of magnitude and
   identical to the printed digit on the target-knots case). `gam_basis_cr.ti_basis`
   builds it from two per-margin `cr` constructions (unchanged from ADR-194) reused as-is:
   each margin's own `smoothCon(absorb.cons=TRUE)`-equivalent basis/penalty, NO further
   reparameterization (measured, not assumed — `mgcv::ti`'s `np=TRUE` default SVD
   reparameterization is real, but every `cr` margin sets `noterp`, which the tensor
   constructor's own gate skips; found by instrumenting
   `mgcv:::smooth.construct.tensor.smooth.spec` directly after a naive hand-replica that
   DID apply the reparameterization disagreed by up to 182 in `X`), a per-margin
   eigenvalue-normalized penalty, a row-wise Kronecker design (`np.einsum` reproduces
   `mgcv::tensor.prod.model.matrix`'s exact column order, confirmed on a hand-built
   example), Kronecker penalties (`numpy.kron`, matching `mgcv::tensor.prod.penalties`),
   and a SECOND, tensor-level `scale.penalty` rescaling on top of each margin's own
   (found after step-4-only output agreed with `smoothCon()` on `X` exactly but disagreed
   on `S` by a constant ratio per block — 8.06x on one test case). Agrees at
   `max_X_diff≈1.5e-14`, `max_S_diff≈3-5e-14` on both blocks, `rank_diff=(0,0)`, on a
   synthetic case and the target's own `ti(AttdAge, PolYear, k=c(13,6))` knots.
   `gam_term_extract.R` gained `extract_smooth_ti` (its own `smoothCon`-vs-`lpmatrix`
   internal guard, ADR-191's discipline, re-run on the tensor term). Carries its own
   `TI_BASIS_CLAIM` (`design_X`/`penalty_S`/`rank`, both penalty blocks, all INDEPENDENT).

   **The multi-term mgcv-native model is now DONE (Stage B on `eta`), 2026-08-24**
   (ADR-206, tier 1 AND tier 3 identical to the printed digit, CI run 32722872476):
   `gam_multiterm_conformance.py` assembles `s(AttdAge,k=13,bs="cr")` +
   `s(AttdAge,by=StudyYear_C,k=13,bs="cr")` + `ti(AttdAge,PolYear,k=c(13,6),bs="cr")`
   from the three already-independently-verified basis producers above and fits it
   with `gam_fit.penalized_irls_general` at a fixed sp per block (binomial/cloglog,
   `ExposCnt` weights — Anchor 5's absolute idiom), reading only the shared recipe
   (never mgcv's own `eta`/`coef`). Agreed on the first measurement,
   `max_abs_eta_diff=1.242e-10` (`n=900`, `p=86`), identical at tier 1 and tier 3 —
   looser than single-term Stage-A cases (~1e-14) but diagnosed as the shared IRLS
   convergence floor on a larger design, not a basis or assembly defect (`cond(XᵀWX+S)
   ≈5000`, converges in 9 iterations). `MULTITERM_CLAIM` declares `eta` INDEPENDENT.
   **This closes slice 5's own remaining-scope line.** What it does NOT do: reach
   Anchor 2's *primary* MI-contrast-on-a-grid metric (needs basis evaluation at
   unseen covariate values, a distinct question from this training-design `eta`
   check), extend slice 4 part B's search to N>2 blocks (the assembled design is the
   right shape for `select_lambdas_continuous` but nothing calls it yet), or add the
   `sz` terms (slice 6). All three are named, separate follow-on work — see ADR-206.
6. **`bs = "sz"`** — orthogonal factor-smooth interactions. Expect the hardest basis.
   **BLOCKED, 2026-08-25** (PR #212 review [P1], tier-3 CONFIRMED same day):
   do not designate until ADR-208's amendment (the `sp`-dependent REML
   criterion discrepancy on slice 5b's N=4 structure, now confirmed real at
   tier 3, CI run 32874213883) is localised or closed — see
   `docs/PLAN_mgcv_parity_engine.md` slice 6. **Round-2 review (same day)
   named a cheaper measurement to run FIRST, before any Wood (2011) §3.1
   log-determinant derivation:** ADR-206 only ever compared `eta` at fixed
   `sp` — the REML score itself has never been compared against `mgcv` on
   this N=4 span-sharing structure, at any `sp`. Evaluate
   `reml_score_general` against `mgcv`'s own score at the same fixed `sp`,
   at 2-3 well-separated `sp` vectors, reusing ADR-206's fixed-`sp` path and
   `gam_multiterm_sp_delta_probe.R`'s `gcv.ubre` read — no optimiser, no new
   numerics. Disagreement there points at `log|S|₊`; agreement there with
   divergence only under free selection means §3.1 is the wrong place to
   look. See `docs/DEV_SESSION_LOG_2026-08-25_mgcv_parity_slice5b_polarisgam.md`'s
   "PR #212 review response, round 2" section for the full argument.

   **UNBLOCKED and DONE FOR STAGE A, 2026-08-31** (ADR-215) — the blocking
   `sp`-dependent REML criterion discrepancy above was localised and closed
   by slices 5c/5d (ADR-210/ADR-211/ADR-212), same day. See the status block
   above for the full measurement.
6b. **`sz` Stage B — a multi-term fit including an `sz` term.** **DONE,
   2026-08-31, the same day as slice 6** (ADR-216). See the status block
   above for the full measurement. Not built, named rather than silently
   skipped: extending `select_lambdas_continuous` to an `sz`-shaped block
   structure; a model combining `sz` with `ti`/`by`; a model with more than
   one `sz` term.
7. **`select = TRUE`** — the double penalty; 13 → 21 smoothing parameters. PLANNED.

Deferred to a later epic: `bam` + `discrete = TRUE` + fREML. Safe to defer because at
fixed `sp` on a `paraPen`-only model `bam` agrees with `gam` to **2.1e-12**, and because
`bam` at 125,000 rows takes **1.69 s** — performance is not the reason to want it.

## Gap audit — what's not yet implemented against `mgcv` (2026-08-18)

A single place to see the whole shape of what's left, rather than reconstructing it
from seven slices' worth of status prose above. Organized by what's missing, not by
slice number, since some gaps (the REML formula, the Kass-Steffey correction) cut
across the slice structure.

| Gap | mgcv feature | Status | Blocked on |
|---|---|---|---|
| Multi-penalty REML criterion (Python-side) | The penalized-deviance criterion, Wood (2011) §2 eq. (4), for any number of independently-scaled penalty blocks | **FIXED, 2026-08-18** (ADR-196) — the score was missing `β̂ᵀSβ̂`; adding it closed the gap to float precision, tier 1 and tier 3 identical | Nothing — DONE |
| Same criterion, production module | `experience_gam_penalized.reml_score` — the SHIPPED tensor-MI 2-D grid selector's own score, same formula shape, same omission | **FIXED, 2026-08-19** (ADR-197 amendment, maintainer-authorized) — identical fix to ADR-196's, `python_reference.json` re-baselined moving exactly as §3.2 predicted, required conformance levels 1-3 still agree, level 5 moved from DISAGREES to AGREES | Nothing — DONE |
| N-dimensional outer search | Newton/quasi-Newton (f)REML optimisation over 13-21 `log λ` | **First slice DONE, 2026-08-22** (ADR-199, tier 1 AND tier 3 confirmed) — `select_lambdas_continuous` built and confirms ADR-198's prediction decisively; tested only at N=2, not yet at the target's 13-21 blocks | A multi-term mgcv-native model to build N>2 blocks from (slice 5 onward) |
| `ti()` — tensor interaction | Tensor product with marginal main effects excluded | **Stage A+B DONE, 2026-08-24** (ADR-205 Stage A, ADR-206 Stage B, tier 1 AND tier 3 confirmed) — agrees with `smoothCon(ti(...))` to ~1e-14 (Stage A) and with a native multi-term `gam()` fit's `eta` to 1.242e-10 (Stage B), including the target's own `ti(AttdAge, PolYear, k=c(13,6))` knots | Nothing for this term's own basis+fit; the MI-contrast-on-a-grid metric and N>2 slice-4-part-B extension remain (ADR-206) |
| `s(..., by=...)` with a `cr` basis | The MI term itself — a `cr` basis scaled by a numeric `by` variable | **Stage A+B DONE, 2026-08-24** (ADR-200 Stage A, ADR-206 Stage B, tier 1 AND tier 3 confirmed) — `mgcv` absorbs no identifiability constraint on a numeric-`by` smooth; agrees to ~2e-14 (Stage A) and to 1.242e-10 on `eta` in the multi-term fit (Stage B) | Nothing for this term's own basis+fit; same remaining items as the `ti()` row above |
| `bs = "sz"` | Sum-to-zero factor-smooth interactions (4 terms in the target formula) | **Stage A+B DONE, 2026-08-31** (ADR-215 Stage A, ADR-216 Stage B, both tier 1 AND tier 3 confirmed — single factor, no `id`) — agrees with `smoothCon(bs="sz")` to ~1e-14 (Stage A) and with a native multi-term `gam()` fit's `eta` to ~4e-12 (Stage B) | Extending `select_lambdas_continuous` to an `sz`-shaped block structure; combining `sz` with `ti`/`by` in one model; more than one `sz` term |
| `select = TRUE` | The double penalty / null-space shrinkage that takes 13 sp → 21 | **Not started** | Slices 4-6 |
| `cr` basis extrapolation | Behaviour for `x` outside `[knots[0], knots[-1]]` | **Unverified**, not assumed — `gam_basis_cr.py` marks it explicitly | A future session measuring it; blocks fitting the target's own knots against real experience data, whose range need not match the hand-chosen knots |
| Kass-Steffey / `vcov(unconditional=TRUE)` | The full Wood, Pya & Säfken (2016) correction (`dw/drho`) | **CLOSED, 2026-08-22** (ADR-202, tier 1 AND tier 3 identical, CI run 32589501512) — `gam_uncertainty` reproduces `mgcv`'s `Vc` to <1% element-wise and <0.1% on the inflation ratio, where the first-order-only correction inflated 1.11-1.21x against `mgcv`'s 1.49-1.87x. Built on ADR-201's `dw/drho` | Nothing for the FORMULA. What remains is a **separate, Anchor-7-gated decision**: re-pointing `experience_gam_penalized.smoothing_uncertainty` at it (with its own determinism answer, ADR-186), and then re-running ADR-188's coverage gate — until that happens the ten-cell suite's level 4 correctly still reads DISAGREES |
| Anchor 5 absolute/relative idiom, demonstrated end to end | Weights and an offset used simultaneously on the target's own multi-term structure | Each control verified in isolation only (PLAN slice 3's own deferred criterion) | A multi-term model, which needs the outer search |
| `bam(discrete=TRUE)` + fREML | The discretised-covariate fast fitting algorithm | **Deferred to a later epic**, deliberately (maintainer decision 2026-08-10) — not a gap in the current epic's scope | N/A |
| `bs = "fs"` | Factor-smooth via difference penalties (an earlier maintainer formula) | **Superseded by `sz`** in the selected target form — recorded, not pursued | N/A |
| `gamboost` / componentwise boosting | A different regularisation algorithm entirely | **Explicitly out of scope** (PLAN §1) — `select=TRUE` covers the term-selection role this epic needs | N/A |

**Read this table as "what mgcv can do that this engine cannot yet reproduce,"** not
as a claim that mgcv itself is incomplete — the framing the maintainer's question used
("what is not implemented in mgcv") is inverted from what actually matters here: mgcv
is the fully-featured reference, and every row above is this engine catching up to it.

## Backlog

Order-classification convention matches `docs/PRODUCT_DIRECTION_2026-07-24.md`'s own
cap (1st-order promote, 2nd-order NICE-TO-HAVE, 3rd-order PARKED). This section is the
epic-scoped consolidation of everything still open across that file's chronological
harvest log — kept here because a reader working this epic shouldn't have to reread
eleven "Harvested" entries to find out what's still outstanding. `PRODUCT_DIRECTION`
remains the cross-epic source of record; if the two drift, that file wins and this one
should be re-synced.

### 1st-order (on the epic's critical path)

1. ~~**Close the multi-penalty REML formula gap (ADR-196).**~~ **DONE, 2026-08-18.**
   The maintainer supplied Wood (2011) directly; §2 eq. (4) named the missing
   penalized-deviance term. Fixed, tier 1 and tier 3 confirmed to float round-trip
   precision. See ADR-196's resolution section.
2. ~~**Run `docs/WORK_ORDER_reml_penalized_deviance_production_check.md`.**~~
   **DONE, 2026-08-18** (ADR-197, tier 1 and tier 3 identical, CI run 32181109927).
   The SAME missing term DOES affect `experience_gam_penalized.reml_score`, and §3.2's
   registered prediction held on all 3 free-sp cells — the corrected criterion selects
   measurably closer to `mgcv`'s own free-sp selection everywhere tested.
   ~~Recommendation: fix it~~ **— and the fix is DONE, 2026-08-21.** The maintainer gave
   the PLAN Anchor 7 sign-off for that one line;
   `data/mgcv_exchange/synthetic/python_reference.json` was re-baselined through its own
   regeneration script (`scripts/export_mgcv_case.py`, not hand-edited); the delta matched
   §3.2's registered prediction to every printed digit. Conformance moved **level 5
   DISAGREES → AGREES**, levels 1-3 AGREE throughout, level 4 unchanged. See ADR-197's
   resolution amendment.
3. ~~**Slice 4 part B — the N-dimensional outer search.** Newton/quasi-Newton on the
   (f)REML score.~~ **First slice DONE, 2026-08-22** (ADR-199, tier 1 AND tier 3
   confirmed, CI run 32544930172). `gam_reml_optimize.select_lambdas_continuous` (SciPy
   L-BFGS-B on `gam_fit`/`gam_reml`) tested ADR-198's registered prediction directly: on
   the same four free-sp cells, `max_abs_log10_sp_diff` against `mgcv`'s own selection
   collapsed from the grid's 0.0645/0.0791/0.1048/0.0776 to (tier 3)
   6.9e-04/5.1e-05/1.7e-04/9.8e-04 — **ADR-198's prediction HOLDS, decisively**, not
   merely "inside tolerance": the residual left after ADR-197's fix was grid
   quantisation, not a remaining criterion difference. **What remains of this item:**
   a real multi-term mgcv-native model now exists (ADR-206, item 4 below) and
   `assemble_multiterm_design` produces exactly the `(x, penalty_blocks)` shape
   `select_lambdas_continuous` consumes — extending the search to N=4 blocks on it is
   direct follow-on work, not yet attempted (ADR-206 names it explicitly rather than
   claiming it).
4. ~~**Slice 5 — `ti()` and the MI term.**~~ **DONE, 2026-08-24** (ADR-206). Ship the
   MI term first if they split (PLAN §3: it's the cheap, well-conditioned one and the
   actual point of the target formula). The MI term's basis: **DONE (Stage A), 2026-08-22**
   (ADR-200, tier 1 AND tier 3 confirmed). `ti(AttdAge, PolYear)`'s basis: **DONE (Stage A),
   2026-08-24** (ADR-205, tier 1 AND tier 3 confirmed). **The multi-term mgcv-native model
   (Stage B on both terms) is now DONE, 2026-08-24** (ADR-206, tier 1 AND tier 3 identical):
   a three-term model — reference age smooth, the `by` term, `ti()` — fit together at a
   fixed sp agrees with `mgcv`'s native fit on `eta`, `max_abs_eta_diff=1.242e-10`, first
   measurement. **What remains, named but not attempted by ADR-206:** Anchor 2's primary
   MI-contrast-on-a-grid metric (needs basis evaluation at unseen covariate values),
   extending slice 4 part B's search to N>2 blocks on this design (item 3 above), and
   item (8) below.
5. ~~**Slice 6 — `bs = "sz"`.** Expected hardest basis; Stage A is where a mistake here
   is cheap (PLAN §6 registered prediction).~~ **Stage A DONE, 2026-08-31** (ADR-215).
   ~~Stage B (a multi-term fit including an `sz` term) remains, registered as slice 6b.~~
   **Slice 6b DONE, 2026-08-31, the same day** (ADR-216, tier 1 AND tier 3
   confirmed): a two-term `cr`+`sz` model agrees with `mgcv`'s native fit on
   `eta` at `3.912e-12` (tier 3), first measurement. What remains: extending
   the outer search to an `sz`-shaped block structure, combining `sz` with
   `ti`/`by`, and more than one `sz` term — named, not yet registered as a
   slice.
6. **Slice 7 — `select = TRUE`.** 13 → 21 smoothing parameters.
7. ~~**Kass-Steffey / `vcov(unconditional=TRUE)` — the level-4 BLOCKER.**~~
   **CLOSED, 2026-08-22** (ADR-202, tier 1 AND tier 3 identical, CI run 32589501512).
   The maintainer supplied Wood, Pya & Säfken (2016); eq. (7)'s `V''` term is exactly
   what ADR-190 measured as missing, and `gam_uncertainty` now reproduces `mgcv`'s
   `Vc` to <1% element-wise (0.023%-0.904%) and <0.1% on the inflation ratio, across
   three committed cases plus five held-out ones including a non-canonical link.
   Three things had to be identified and all three were MEASURED, not chosen: the
   `Vrho` ridge is exactly 0.1 (against `mgcv`'s own `m$V.sp`, 1.78e-15); the factor
   is Wood (2011) §3.3's lower-triangular `L^-1`, and `V''` is *not* invariant to
   that choice; and the two terms use **different** inverses of the rho Hessian.
   **What remains is NOT the formula.** Re-pointing production at it is a separate
   Anchor-7 decision carrying its own determinism question (ADR-186). Labelling
   any interval a 95% band stays maintainer-reserved.

   **ADR-188's coverage gate has now been RUN** (2026-08-23, ADR-203 — this line
   said "a further, still-unrun measurement" until then, the one document ADR-203's
   seven-document sweep missed). ADR-190 decision 4's prediction is **confirmed in
   direction and refuted in sufficiency**: eq. (7) moves coverage up on both truths
   but the gate still fails by up to 0.1025, so the formula was *a* gap and not
   *the* gap. A second cause remains that no covariance eq. (7) can form will
   reach. **Coverage therefore does not supply the argument for re-pointing
   production** — ADR-202's parity is that case, and it is a different one.

8. **Demonstrate Anchor 5's absolute/relative idiom end to end** on the target's own
   multi-term structure. **Partially demonstrated by ADR-206** (2026-08-24): the
   multi-term model uses the absolute idiom (`ExposCnt` weights, no offset) and fits
   correctly under it — but at a fixed, externally-supplied `sp`, not through the
   outer smoothing-parameter search, and the relative idiom (an offset, no weights)
   is not exercised at all on this structure. Both remain open for a session wiring
   `select_lambdas_continuous` through this design (item 3 above).
9. **`cr` basis extrapolation beyond the knot range.** Needed before fitting the
   target's own `AttdAge`/`PolYear` knots against real experience data.

### 2nd-order (nice-to-have, not blocking)

1. **`binomial`/`cloglog`'s non-canonical-link concavity gap** — documented caveat
   (ADR-195 decision 3), not a work item unless a future measurement actually hits it.
2. **The `continue-on-error` job-summary-artifact limitation** likely still affects the
   ADR-190 (`ks_formula_probe.R`) and ADR-191 (`smoothcon_lpmatrix_probe.R`) diagnostic
   steps — their tier-3 confirmations rest on "the step didn't except" rather than a
   read of the actual numbers, the same limitation slice 1b's row had before the
   print-to-stdout fix (ADR-194) was adopted for every later probe. A few lines per
   step if a future session needs to re-read one of those probes' real numbers.
3. **Retro-classify the historical conformance-ledger rows** with a per-row
   `CONFIRMED (harness)` marker — needs an append-only-safe convention first (PR #200
   review).
4. **The `auto_unbox`/length-1-field gotcha** — any R-side field that can be length-1
   needs `I()` to survive jsonlite's `auto_unbox`, documented for whoever writes the
   next R-side branch (slice 1b's bug).

### 3rd-order (parked)

1. **Quasi-Poisson's estimated-dispersion REML criterion.** `reml_score_general`
   raises rather than silently reusing a formula not derived for it; the target
   formula's own family (binomial) never needs it. Revive only on an explicit future
   need.

## Context for the next session

- **Read PLAN Anchors 1 and 2 before writing code.** They change what you build, not just
  how you check it: construction is verified before fit, and the fitted surface is the
  acceptance criterion while coefficients are not.
- **Local R is a SCRATCH oracle, not a cheap version of the real one.** `apt-get install -y
  r-base-core r-cran-mgcv r-cran-jsonlite`, ~3.5 min, then 2.2 s per run — but it is **mgcv
  1.9.1 against reference `libblas`**, where the image is **mgcv 1.9.4 against OpenBLAS**.
  Different release, different BLAS: local output *cannot* match the image at Stage-A
  precision (~1e-15) however correct the code is, so a local-vs-image difference at that
  scale is evidence of nothing. **Iterate locally, verify on CI** — a `workflow_dispatch`
  round trip on the pinned digest costs about a minute (measured: run 31892118379, 59 s).
  `ROUTINE_MGCV_PARITY.md` step 2 has the three tiers and which one a number may be
  committed from. Running the image locally is *not* an option here: `docker` is installed
  but there is no daemon.
- **The oracle image is `sha256:0d54c192…`** — upstream **build 8**, the first with
  host-independent numerics. Builds 1-7 let OpenBLAS size its thread pool from the host, so
  the last bits depended on which runner drew the job. We adopted build 8 for **slice 1**,
  not for `mboost`: Anchor 1 compares design matrices at ~3.5e-15, the same order as that
  nondeterminism, so on an older build a Stage-A disagreement could have been the runner.
  Re-measured, not assumed — run 31892118379: levels 1-3 agree, 4-5 unchanged findings.
  ADR-189 amendment 2.
- **ADR-189 amendment 1's numbers belong to build 1 (`sha256:a77a61cf…`)**, and amendment 2
  deliberately does not restate them as build-8 numbers — the verdicts were reproduced, the
  per-metric digits were not read. **Never quote a conformance number without the digest
  that produced it.** This file has pinned three builds; `mgcv_version` does not distinguish
  them, because all three carry mgcv 1.9.4.
- **Upstream tagging is fixed (R-Gam-base PR #3):** immutable never-reused tags
  `r<R>-cran<snapshot>-b<NN>`, a digest-keyed `BUILDS.md` catalog, CI refusal to push an
  existing tag, and `/opt/oracle-manifest.json` from build 3 forward (builds 1-2 carry
  `/opt/versions.json`, and record no `MASS` version). `r4.6.1-2026-08-01` is **deprecated,
  not deleted** — GHCR deletes versions rather than tags, and that tag sits on the digest we
  pin. The `-b1`/`-b2` tags are staged in an upstream retag workflow and **were not yet
  applied** when this was written; the digests are the durable references either way.
- **`mboost` is not a parity target.** It is there for the maintainer's exploratory
  `gamboost` work. Componentwise boosting is a different algorithm with no likelihood
  covariance; `select = TRUE` covers the term-selection role inside penalized likelihood.
- **`weights` are not an `offset`** (PLAN Anchor 5). The target uses weights and no offset;
  the existing polaris engine uses an offset. Both are wanted, and A/E is what `η`
  estimates rather than an input.
- **The MI term is a varying-coefficient term, not a tensor**, and it is better conditioned
  than what the old epic built — 13 coefficients against 38-60. Do not "improve" it.
- **Do not compare coefficients outside Stage A.** It is the mistake that looks most like
  rigour and is least informative.
- **The conformance CI gate blocks on levels 1-3 and annotates 4-5.** Do not narrow
  `REQUIRED_LEVELS` to go green.
- **There are TWO searches over λ and only one of them is scheduled to become continuous**
  (ADR-198). Slice 4 part B builds a continuous Newton/quasi-Newton optimiser **for this
  epic's engine**, because the target has 13 smoothing parameters (21 with
  `select = TRUE`) and a three-point grid in 14 dimensions is 4.8 million fits — the grid
  is not slow there, it is impossible. The **shipped production selector**
  (`experience_gam_penalized.select_lambdas_reml`) keeps its grid: two dimensions where
  the grid is affordable, and ADR-186 chose it *deliberately* over a continuous optimiser
  to get reproducibility by construction (three fresh interpreters, exact repr equality).
  Re-pointing production at part B's optimiser later is a separate decision needing its own
  Anchor 7 sign-off and its own answer on determinism. Do not conflate the two when
  reporting what "parity" will mean.

## Carried in from the superseded epic

- **The level-4 Kass-Steffey under-inflation is a live BLOCKER** — ours inflates
  1.11-1.21x where `mgcv` inflates 1.49-1.87x, same direction every cell. It is
  engine-agnostic, and it is the standing bar on labelling any interval a 95% band.
  Whatever this engine reports as a band inherits it. Tracked in
  `PRODUCT_DIRECTION_2026-07-24.md`.
  **ADR-190 (2026-08-15) re-scoped it: this is a FORMULA gap, not our arithmetic.**
  `vcov(unconditional = TRUE)` is not `Vb + J V_rho Jᵀ` — built from `mgcv`'s own
  coefficients, `V_rho` and λ, that expression reproduces *our* number, not `mgcv`'s.
  `mgcv` implements Wood, Pya & Säfken (2016), which uses `dw/drho`; plain Kass-Steffey is
  its first-order part. **Closing it is a slice needing `dw/drho`, and it must be re-derived
  from the paper — `mgcv` is GPL (>= 2), this project is MIT.** Do not go looking for a bug
  in `smoothing_uncertainty`; two tests now pin that arithmetic as correct.
- **The old CONTINUATION's refinement-backlog harvest is owed** before its status may
  change from IN PROGRESS. Not this epic's work, but it is the reason that file is still
  open, and a reader should not mistake it for an active epic.

## Standing positions — open, and movable on new evidence (2026-08-21)

**Source, quoted in full — added after PR #204's round-3 review flagged this section's
original wording as a [P0]: no quote or channel was recorded here, unlike ADR-196/197's
authorization pattern.** Live Claude Code session on `claude/zealous-mendel-j0huik`: the
maintainer wrote *"Okay, I am ready to merge, do you want to recommend a way forward on the
open review questions so I can authorize you to confirm this for future iterations to have
the decision on hand?"*; Claude restated the recommendation `00ebd27` had already presented
with a case for and against; the maintainer replied *"They look right."* Full record and the
same caveat about what a conversational source can and can't prove: `docs/DECISIONS.md`,
ADR-198, "Two standing positions, held until parity work supersedes them".

**Scope of that endorsement — clarified 2026-08-22 (PR #204 round-3, maintainer
direction).** *"They look right"* endorsed the **substance** of both positions on that
day's evidence; it was not a bar on revisiting them. Recording them as settled, and as
items that "should not be reopened without new evidence", was preemptive — neither has
reached parity nor definitive obsolescence.

**Both stay open, and a later session may move either on its own evidence, without asking
first.** Each names below what would count. Do not cite this section as a reason to leave
an item alone once the parity work has produced what it asks for — the objective is `mgcv`
parity for MI estimation, and these are working defaults, not gates. Still maintainer-gated,
unchanged: PLAN Anchor 7's protected artifacts, and labelling any interval a 95% band.

Both raised by PR #204's round-2 review (ADR-198); both hold as the working default
*because nothing measured yet argues for changing them*:

- **The level-5 `gamma` tolerances are not promoted from PROVISIONAL — for now.** They pass
  with room (`max_abs_log10_sp_diff_gamma` 0.0776 vs tol 0.5, `abs_edf_total_diff_gamma`
  -0.0024 vs tol 1.0), but one exchange is a measurement, not a derivation, and Anchor 8
  forbids tightening a bound *because a check went green*. What did change: `gamma`'s Anchor
  9 status moves from "adopted, unmeasured" to "adopted, measured, AGREES" — a factual
  update, not a new tolerance. **Movable when:** slice 5/6's cells make a derived bound
  possible. Tightening them then is ordinary parity work — do it and record the derivation.
- **The coverage move (0.7598 → 0.8282, old age) does not by itself change anything
  downstream.** Slice 4's gate still fails (0.9192 floor untouched), so the default of not
  showing the penalized band holds on today's evidence: 82.8% is 12 points short of the 95%
  it would need to claim.
  **Movable when:** level 4 closes, or coverage reaches the gate — then re-open the question
  rather than citing this note.

  > **The trigger has FIRED, and the answer did not change** (2026-08-24). This bullet
  > named "level 4 (ADR-190's `dw/drho` gap)" as the substantive blocker. **That gap is
  > closed** — ADR-202, eq. (7) reproduces `mgcv`'s `Vc` to 0.023-0.904% at tier 3. ADR-203
  > then ran the gate and measured that closing it moved coverage only to 0.8167 / 0.8354
  > against the 0.9192 floor. So the default of not showing the penalized band still holds,
  > **but for a different reason**: a second cause, still unidentified, that no covariance
  > correction reaches. A reader arriving at the original wording would have thought the
  > blocker was still ahead of them. Labelling an interval a 95% band remains maintainer-reserved
  either way; measuring and recommending toward it does not.

## Open questions (for human)

- **RESOLVED, same day (2026-08-29, ADR-212).** Slice 5c's third-branch escalation
  (below, filed the same day) was resolved by slice 5d before this file was next
  read: the optimiser defect was a specific, measured finite-difference-step bug
  (SciPy's default step sitting inside the nested-IRLS noise floor), now fixed
  from the module's own measured noise floor rather than tuned against `mgcv`.
  The remaining `max_abs_log10_sp_diff` residual is now understood as weak
  identifiability on the by-term's own smoothing parameter (the metric swings
  3.4x between tiers while `eta`/`edf` agree tightly and consistently at both) —
  not an unresolved defect. Slice 6 is unblocked. **What is still an open
  question for the maintainer, narrower than before:** whether
  `FREE_SP_MODEL_CLAIM`'s own primary metric should be revisited to weight
  `eta`/`edf` over raw `log10(sp)` on structures where one block is weakly
  identified, since the raw metric is now demonstrated to be unstable across R
  builds in a way that does not track model agreement (ADR-212 Consequences).
  The original escalation is kept below, struck through, for the record of what
  was asked and how quickly it resolved.
- ~~**Slice 5c's registered prediction landed on its third branch — escalated per the
  slice's own DoD** *(filed 2026-08-29, ADR-210)*. Both defects (Appendix B's
  `log|S|+`, the observed-Hessian weight) are fixed and the fixed-`sp` criterion
  now agrees with `mgcv` to float precision at both tiers — real, closed progress.
  But free-`sp` selection on the N=4 structure ADR-208 already found disagreeing
  is now WORSE at tier 3 (1.0996 vs the pre-fix 0.6398), and the cause has moved
  from "the criterion is wrong" to "our optimiser (SciPy L-BFGS-B, finite-difference
  gradient) is not converging to this now-correct criterion's true optimum, on this
  specific `by`-term-dominated landscape" — a different, and possibly larger, kind
  of gap than the epic's cost estimate assumed. Registered as PLAN slice 5d with
  two named hypotheses and a cheap tier-3 discriminator; not chased further this
  session per its own DoD ("escalated to the maintainer if the third branch is the
  outcome, because that reopens the epic's cost estimate"). **Not this routine's
  call to size**: whether an analytic-gradient optimiser rewrite belongs in this
  epic's scope, or whether the free-`sp` acceptance bar for a 13-21-parameter
  target needs to be restated given a 2-block optimiser (ADR-199) already needed
  1e-4-level precision to demonstrate parity and a 4-block one does not reach it.~~

  > **Addendum, ADR-211 (PR #217, written concurrently with ADR-212).** A
  > second session resolved the same slice the same day, from the environment
  > rather than the objective, and two of its results are not covered by the
  > bullet above. (1) The blind search's own converged point moves with
  > `OPENBLAS_NUM_THREADS` alone — by-term `log10(sp)` at `9.116` / `8.519` /
  > `8.773` on 1 / 2 / 4 threads, against `~4e-10` of movement for a fixed-`sp`
  > evaluation of the same criterion — which is what made ADR-210's own
  > tier-1/tier-3 readings of "the same" measurement disagree. That confound is
  > now pinned in the CI compare job. (2) Hypothesis 2 was refuted directly:
  > warm-starting our own search at `mgcv`'s point converges back to it at a
  > better score than the blind start reaches, so that point is REACHABLE under
  > our criterion (a DIAGNOSTIC check by ADR-193's mechanical test — `mgcv`'s
  > own output is its input — never folded into `FREE_SP_MODEL_CLAIM`). The
  > sizing question ADR-211 registered as PLAN slice 5e survives ADR-212's fix,
  > but with a narrower premise: the score gap it was registered against has
  > largely closed, and what remains open is whether a single start still
  > suffices at the target's 13-21 blocks. See PLAN slice 5e, premise restated
  > 2026-08-30.
- **The duration treatment on real data** — band as factor, or band as ordered numeric via
  a representative value. The maintainer has reserved this as a modelling judgement; the
  engine will support both and the routine is forbidden from deciding it.
- ~~**Scheduling.** This epic advances only when `ROUTINE_MGCV_PARITY.md` is registered as
  a scheduled task; the cron config lives outside the repo. Until then nothing here
  moves.~~ **RESOLVED — and it was resolved almost immediately, then said otherwise for two
  weeks.** Written 2026-08-11 (`57ad0f0`), when it was true. The routine has in fact been
  running since about that date: `DEV_SESSION_LOG_2026-08-11_mgcv_parity_epic.md` onward
  name it as their routine, and every slice from 1b to 5 was produced by one — most
  recently `DEV_SESSION_LOG_2026-08-24_mgcv_parity_slice5_multiterm.md`, which installed
  the tier-1 oracle, dispatched tier 3 and produced ADR-206. **Nothing outside the repo is
  needed to advance this epic; the next unchecked slice is 5b and a routine run will
  select it.**

  **This is the third instance of the prose-drift failure two bullets up, and the most
  expensive.** The other two were a bullet and an example output. This one was load-bearing
  false: it says the epic cannot move, in the file the routine reads first, while the
  routine was moving it. On 2026-08-25 it caused a session to tell the maintainer that
  registering the routine was the blocker and to hand them a task list for work that was
  already done — corrected only because the maintainer asked why the routine could not
  handle it. That is the mechanism gap costing something real rather than theoretically:
  a trigger condition fired, nobody noticed, and the stale claim was believed and acted on.
- **Ledger framing.** This epic is sourced from maintainer direction rather than the Tier-A
  table of a `COMMERCIAL_VIABILITY_REVIEW`. It is registered in
  `PRODUCT_DIRECTION_2026-07-24.md` so it is visible to a selecting routine, but the next
  commercial-viability review should re-rank it properly.
- **A forward-looking prose claim has no drift detection** *(1st-order — follow-up of
  ADR-204's stamp system; raised by ADR-207, filed here 2026-08-24)*. ADR-204 gives
  *measurements* a machine-checked closure fingerprint, so a stamped number cannot go stale
  unnoticed. **Prose has no equivalent**, and the failure mode is not hypothetical: a
  *"Movable when: level 4 closes"* bullet in this file, and a `level 5: DISAGREES` example in
  `RUNBOOK_mgcv_conformance.md`, both had their trigger conditions fire (ADR-202 and ADR-197
  respectively) and stayed wrong until a human happened to read them. Both said the blocker
  was still ahead of a reader who had in fact already passed it. This is ADR-203's failure
  mode expressed in sentences rather than in figures. Whether it is worth a mechanism — a
  claim register with trigger conditions, say — or whether it stays a review-time
  responsibility, is a maintainer call, not a routine's.
- **The stamp schema understates evidence after an inert edit** *(1st-order — defect in
  ADR-204's schema; raised by the maintainer 2026-08-24, filed here same day)*. A stamp
  fingerprints the producer's transitive import closure, so **any** edit inside that closure
  drifts every document downstream of it — including documents regenerated on real inputs
  the day before. Re-stamping under RUNBOOK §2 case (c) then writes `method: asserted` and
  `generated: <today>`, and the schema has no way to say what actually happened. **Two
  distinct defects, and they show up in different documents:**
  - **`generated` is the stamp date, not the run date** (`measurement_provenance.py:273`
    defines it as *"ISO date the stamp was written"*). `MEASUREMENT_experience_gam_ilec`,
    `_hmd` and `_portfolio_parallel_macbook_air` were regenerated 2026-08-23 and now read
    `2026-08-24` because a `table_io` error-message edit landed after them. Their `method`
    is fine — all three were already `asserted`, and an operator really did regenerate them
    elsewhere. Only the date misleads.
  - **`asserted` is positively false for a case-(c) document.** `StampMethod.ASSERTED`'s
    docstring reads *"An operator regenerated it elsewhere ... and recorded a note saying
    so."* `MEASUREMENT_unconditional_coverage.md` is the one document this PR actually moved
    (`regenerated` → `asserted`), and nobody re-ran it anywhere — the warrant is inertness,
    not an elsewhere-run. So case (c) fits **neither** existing value, and the enum now
    asserts something untrue about it.
  The prose notes rescue both; the machine-readable fields do not, and future tooling reads
  the fields. **Proposed fix, and note the two axes are orthogonal:** *how the numbers were
  produced* (`regenerated` / `asserted`) and *whether the stamp is reconciled to current
  code* are independent — ilec is both `asserted` and inert-drifted at once. So a third
  peer value is probably the wrong shape; better is to keep `method` describing production
  and add a separate field for a closure that has moved under an inertness argument, plus
  splitting `generated` into run date and stamp date. Conflating those two axes is what
  produced both defects. This amends ADR-204's schema and re-touches every stamped
  document — including a migration decision (accept both forms during a transition, or
  re-stamp all six at once) — so it is a maintainer call.
- **Whether Anchor 7's gating pattern should bind future work**
  *(2nd-order — process, not engine; raised by the maintainer 2026-08-24)*. ADR-207 amended
  Anchor 7 by recording what it *cost*. The maintainer's reading supplies the other half:
  the anchor is also what *produced* the nine tier-3-verified components, by forbidding
  assembly until each part was understood in isolation. `PATTERN_gated_decomposition.md`
  is the retrospective — it argues the defect was the missing release condition rather than
  the constraint, and proposes four requirements a gate should carry. **It is PROPOSED and
  binds nothing.** Adopting it means an ADR (the `VERIFICATION_STANDARD.md` / ADR-193
  precedent) and, if adopted, re-reading the PLAN's other anchors against requirement 2.
