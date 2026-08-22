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
`mgcv` absorbs no identifiability constraint on it at all. `ti(AttdAge, PolYear)` and a
multi-term mgcv-native model (needed for Stage B) are not yet started.
**Total slices:** **7** autonomous, plus slice 1b (inserted 2026-08-16) and one deferred
to a later epic.
**Estimated scope:** the largest numerical undertaking in the project.

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
   **IN PROGRESS.**

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

   **Not started:** `ti(AttdAge, PolYear)` — a materially different construction (its own
   tensor-product machinery and identifiability treatment). And no multi-term mgcv-native
   model exists yet, so nothing has run Stage B / Anchor 2's own criteria (the MI contrast,
   `η`) on this term — that is what unblocks both slice 4 part B's N>2 extension and
   Anchor 5's absolute/relative demonstration.
6. **`bs = "sz"`** — orthogonal factor-smooth interactions. Expect the hardest basis.
   PLANNED.
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
| `ti()` — tensor interaction | Tensor product with marginal main effects excluded | **Not started** | The outer search (slice 5) |
| `s(..., by=...)` with a `cr` basis | The MI term itself — a `cr` basis scaled by a numeric `by` variable | **Stage A DONE, 2026-08-22** (ADR-200, tier 1 AND tier 3 confirmed) — `mgcv` absorbs no identifiability constraint on a numeric-`by` smooth; agrees to ~2e-14. Stage B unmeasured (needs a multi-term model) | A multi-term mgcv-native model for the Stage-B half (slice 5's remaining scope) |
| `bs = "sz"` | Sum-to-zero factor-smooth interactions (4 terms in the target formula) | **Not started**, expected hardest basis (PLAN §6 registered prediction) | The outer search (slice 6) |
| `select = TRUE` | The double penalty / null-space shrinkage that takes 13 sp → 21 | **Not started** | Slices 4-6 |
| `cr` basis extrapolation | Behaviour for `x` outside `[knots[0], knots[-1]]` | **Unverified**, not assumed — `gam_basis_cr.py` marks it explicitly | A future session measuring it; blocks fitting the target's own knots against real experience data, whose range need not match the hand-chosen knots |
| Kass-Steffey / `vcov(unconditional=TRUE)` | The full Wood, Pya & Säfken (2016) correction (`dw/drho`) | **Known wrong, re-scoped as a formula gap** (ADR-190) — a SEPARATE standing blocker, not fixed by slice 4's REML work; different paper, different derivation. **Its named prerequisite `dw/drho` is now BUILT and tier-3 verified (ADR-201, 2026-08-22)** from Wood (2011) §3.4 + Appendix D — the blocker itself is unchanged | the **Vc ASSEMBLY** from Wood, Pya & Säfken (2016), re-derived from that paper, never from GPL source. Wood (2011) does not contain it (zero occurrences of "unconditional") |
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
   extending the search to more than 2 penalty blocks, which needs a multi-term
   mgcv-native model (slice 5's own scope) — the search itself is already written
   generally, nothing here
   needs revisiting once that model exists.
4. **Slice 5 — `ti()` and the MI term.** Ship the MI term first if they split (PLAN
   §3: it's the cheap, well-conditioned one and the actual point of the target
   formula). **The MI term's basis is DONE (Stage A only), 2026-08-22** (ADR-200, tier 1
   AND tier 3 confirmed). **What remains:** (a) `ti(AttdAge, PolYear)` — not started;
   (b) a multi-term mgcv-native model, which is the shared prerequisite for this slice's
   own Stage-B half, for extending slice 4 part B's search above N=2, and for item (8)
   below.
5. **Slice 6 — `bs = "sz"`.** Expected hardest basis; Stage A is where a mistake here
   is cheap (PLAN §6 registered prediction).
6. **Slice 7 — `select = TRUE`.** 13 → 21 smoothing parameters.
7. **Kass-Steffey / `vcov(unconditional=TRUE)` — the level-4 BLOCKER.** Separate from
   the REML score work above: a different paper (Wood, Pya & Säfken 2016), needs
   `dw/drho`, re-derived from the paper per the same GPL/MIT discipline. Standing
   since ADR-188/190; see "Carried in from the superseded epic" below for the full
   context. **Its prerequisite is DONE, 2026-08-22 (ADR-201, tier 1 AND tier 3):**
   `gam_derivatives` computes `dbeta/drho`, `d(eta)/drho` and `dw/drho` from Wood
   (2011) §3.4 + Appendix D, agreeing with `mgcv`'s own differenced refits to
   ~5e-11 with a Richardson ratio of 4.00. **What is still missing is only the
   assembly** — how `dw/drho` enters `Vc` — which is the 2016 paper's own
   contribution and is not in Wood (2011) at all. A future session starts from a
   measured ingredient rather than an absent one. Note the derivative required the
   OBSERVED (Newton) Hessian, not the fitter's Fisher weights; that distinction is
   worth ~5 orders of magnitude on a non-canonical link and any `Vc` work inherits
   it.
8. **Demonstrate Anchor 5's absolute/relative idiom end to end** on the target's own
   multi-term structure, once a multi-term model exists (needs (3)).
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
  it would need to claim, and level 4 (ADR-190's `dw/drho` gap) is the substantive blocker.
  **Movable when:** level 4 closes, or coverage reaches the gate — then re-open the question
  rather than citing this note. Labelling an interval a 95% band remains maintainer-reserved
  either way; measuring and recommending toward it does not.

## Open questions (for human)

- **The duration treatment on real data** — band as factor, or band as ordered numeric via
  a representative value. The maintainer has reserved this as a modelling judgement; the
  engine will support both and the routine is forbidden from deciding it.
- **Scheduling.** This epic advances only when `ROUTINE_MGCV_PARITY.md` is registered as a
  scheduled task; the cron config lives outside the repo. Until then nothing here moves.
- **Ledger framing.** This epic is sourced from maintainer direction rather than the Tier-A
  table of a `COMMERCIAL_VIABILITY_REVIEW`. It is registered in
  `PRODUCT_DIRECTION_2026-07-24.md` so it is visible to a selecting routine, but the next
  commercial-viability review should re-rank it properly.
