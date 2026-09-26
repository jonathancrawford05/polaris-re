# CONTINUATION: mgcv capability ladder (L1–L5)

**Plan:** `docs/PLAN_mgcv_capability_ladder.md`
**Created:** 2026-09-19, by the session that started slice 1 — as the plan's §3
requires, and not before (the one-active-epic rule).
**Status:** **ACTIVE.** Slices 1, 2 and 3 complete; slice 4 (L3, factor-`by`)
next.

---

## Slice status

| slice | rung | status |
|---|---|---|
| **1** | **L1** `gaussian(identity)` | **DONE** (2026-09-19, ADR-229) — family built, closed-form verified, and measured against `mgcv` at **tier 3**. **Fixed `sp` only until slice 3; free `sp` landed 2026-09-26 (ADR-231)** |
| **2** | **L2** `bs="re"` | **DONE** (2026-09-21, ADR-230) — basis built, measured against `mgcv` at **tier 3**, Stage A AND Stage B, **fixed AND free `sp` both landed in this slice** |
| **3** | **L5** scale-estimated REML | **DONE** (2026-09-26, ADR-231) — the free-scale REML criterion derived from Wood (2011) §2 eq. (4) (paper supplied directly by the maintainer after web access was blocked), measured against `mgcv`'s own `gcv.ubre` at **tier 3** (score, both free-scale families) and the fit-level free-sp re-run (Gaussian). **Removed ladder slice 1's own "fixed `sp` only" qualifier in this slice's PR**, its own acceptance criterion. A real, pre-existing factor-of-2 defect in `_gaussian_deviance_terms` (shipped harmlessly at slice 1, since Gaussian's deviance had only one, scale-invariant consumer until this slice) was found in MEASURE FIRST and fixed |
| 4 | L3 factor-`by` | not started |
| 5 | L4 unpenalized parametric block | not started |

---

## Slice 1 — what landed

### Built

- **`gam_family.gaussian_identity()`** — identity link, `V(mu) = 1`,
  `V'(mu) = 0`, `dispersion_fixed=False`.
- **Registered** in `gam_model._FAMILY_LINKS` as `("gaussian", "identity")`, so
  `ModelSpec(family="gaussian", link="identity")` now resolves where it
  previously raised.
- **The four `gam_derivatives` registries extended** — `second_deriv_mu_eta`
  and `third_deriv_mu_eta` for the `identity` link, `variance_deriv` and
  `variance_second_deriv` for `gaussian` (all four vanish identically). PR #237
  review [P1-3] caught two of these; sweeping found the other two. A new test
  **walks `_FAMILY_LINKS`** and demands all four entries, so the next family
  cannot be registered without them.
- **13 collected closed-form tests** (10 functions, one parametrised ×4) in
  `tests/test_analytics/test_gam_family.py`. These
  compare against **the algebra, not against a reference**:
  - unpenalized IRLS ≡ OLS (`lstsq`), to `1e-12`;
  - penalized IRLS ≡ the closed-form ridge `(X'X + S)^-1 X'y`, to `1e-12`, and
    again across `log10(lambda) ∈ {-4, 0, 4, 8}` so a penalty-scaling error
    cannot hide at `lambda = 1`;
  - observed ≡ expected Hessian weight (canonical link ⇒ Wood's `alpha_i ≡ 1`);
  - `d2mu_deta2` exactly zero, `V(mu)` exactly one;
  - the deviance's factor-of-2 convention, pinned so nobody "fixes" it;
  - `n_iter <= 2`, the property that makes L1 the diagnostic floor.

### Measured

- **`scripts/gam_gaussian_probe.R`** — `gam_multiterm_probe.R`'s own three-term
  design with `family = gaussian(link = "identity")` and nothing else changed,
  so the family is the only unverified thing in the comparison.
- **`src/polaris_re/analytics/gam_gaussian_conformance.py`** — a declared
  `VerificationClaim`, both quantities `INDEPENDENT`, tolerances **imported**
  from `gam_select_free_sp_conformance` and never redeclared.
- **A `mgcv-conformance.yml` probe step + compare step + path filters**, so the
  measurement re-runs on the pinned digest whenever either side changes.
- **Tier 3 result:** `eta` `2.442e-14`, `edf_total` diff `-7.105e-15`, inside
  ADR-221's `2e-2` / `1.0`. See ADR-229 and the ledger row.
- **10 tests over the conformance module**, including the two that make the
  independence claim checkable rather than asserted: stripping every
  `mgcv`-produced key leaves the fit bit-identical, and `edf_total` moves with
  the penalty.
- **`MGCV_FEATURE_COVERAGE.md` §2.2 Stage B** now reads ✅ tier 3, **fixed `sp`
  only** — the two claims in that row moved at different times on purpose:
  `expressible?` when the registration landed, Stage B when this measurement
  did. (PR #237 review [P1-2]: holding the whole row was under-claiming, the
  opposite drift from over-claiming Stage B. Both are drift.)

---

## Slice 2 — what landed

### Built

- **`gam_basis_re.re_basis(group, n_levels)`** — the entire construction is a
  0/1 level-indicator design plus `numpy.eye(n_levels)`. No knot recipe, no
  rescaling, no constraint step: every one of `gam_basis_cr`'s four
  construction stages collapses to nothing for this basis.
- **`TermSpec` gains `basis="re"`** — one factor variable, no `k`, `n_levels`
  **required** (the mgcv asymmetry the OTHER way from `sz`, where `n_levels`
  is optional).
- **`gam_model.assemble_model_design`'s dispatch extended** for `"re"`,
  alongside `cr`/`ti`/`sz`.
- **`gam_stage_a.build_python_re_term` + `RE_BASIS_CLAIM`** — the Stage-A
  independent producer, plus two new `gam_term_extract.R` cases
  (`re-4level`, `re-7level`).
- **`gam_re_conformance.py`** — Stage B, TWO claims: `RE_FIXED_SP_CLAIM`
  (`gaussian(identity)`, fixed `sp`, same reasoning as ladder slice 1) and
  `RE_FREE_SP_CLAIM` (`poisson(log)`, free `sp` — chosen specifically so this
  half does not wait on rung L5, per the plan's own instruction for this
  slice).
- **Verified first, before any code**: `smoothCon(s(fac, bs="re"),
  absorb.cons=TRUE)` and `absorb.cons=FALSE` return bit-identical `$X`, and
  `nrow($C) == 0` regardless — `mgcv` absorbs NO constraint on a `"re"` term
  at all. So the Stage-A claim names one `mgcv` producer, not two.
- Closed-form unit tests (`test_gam_basis_re.py`) against the algebra
  (indicator matrix structure, identity penalty, full rank, width = `n_levels`
  regardless of the observed level count).

### Measured

- **Stage A** (`re-4level`, `re-7level`): `max_abs_design_diff` /
  `max_abs_S_diff` / `rank_diff` all **exactly** `0.000e+00` / `0.000e+00` /
  `0`, tier 3. No continuous construction step exists for either side to
  differ about.
- **Stage B fixed `sp`** (`gaussian(identity)`, `n=900`, `n_levels=6`):
  `max_abs_eta_diff = 2.176e-14`, `edf_total_diff = 1.066e-14`, tier 3.
- **Stage B free `sp`** (`poisson(log)`, `n=900`, `n_levels=6`, `p=19`,
  single-start — no `multistart` needed): `max_abs_eta_diff = 3.226e-05`,
  `max_abs_log10_sp_diff = 0.0010`, `edf_total_diff = -0.0010`,
  `at_bound=False`, `converged=True` on both sides, tier 3.
- **Both regimes `agrees=True`** under ADR-221's imported `2e-2`/`1.0` gate.
  Run [35553707543](https://github.com/jonathancrawford05/polaris-re/actions/runs/35553707543),
  oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`,
  R 4.6.1 / mgcv 1.9.4.
- **The same suspicion-not-just-a-check pair slice 1 used**, now run on both
  Stage-B regimes: every `mgcv`-produced key stripped from the payload leaves
  the Polaris fit bit-identical, and `edf_total` strictly falls when the
  `"re"` block's own fixed `sp` is raised.
- **`MGCV_FEATURE_COVERAGE.md` §2.1's `re` row** moves from **NO** to
  **yes**, Stage A ✅ tier 3 (exact), Stage B ✅ tier 3 **fixed AND free
  `sp`** — the first basis in this epic to land both regimes in the slice
  that introduced it.

**What was NOT deferred, contrary to the usual pattern.** `sz` (slice 6 of the
predecessor epic) shipped Stage A only, then fixed-`sp` Stage B, then never
reached free `sp` — three separate landings, and the last one never happened
(deprioritised to L11). `bs="re"`'s free-`sp` half was reachable in the SAME
session because `poisson(log)`'s free-`sp` search was already verified
elsewhere in this epic and does not share Gaussian's free-scale blocker, so
this slice measured all three (Stage A, Stage B fixed, Stage B free) rather
than registering a follow-up letter-suffix slice.

---

## Slice 3 — what landed

### Built

- **`gam_reml.reml_score_general`'s free-scale branch** — replaces the
  unconditional raise at `dispersion_fixed=False`. Derived from Wood (2011)
  §2 eq. (4), differentiated w.r.t. the unknown scale `φ` and substituted
  back: `φ̂ = Dp/(n-Mp)` (`Mp` = the paper's own null-space dimension of
  `S`), then `V = 0.5(n-Mp)(1+log(φ̂)) + K + 0.5(n-Mp)log(2π)` with `K`
  computed identically to the known-scale branch (same `logdet_h`/
  `logdet_s`/`rank_s`/observed-Hessian weight). The paper's PDF was supplied
  directly by the maintainer after every web host this session tried
  (journal publishers, ResearchGate, Semantic Scholar, arXiv, university
  course notes) was blocked by egress policy — see ADR-231 for the exact
  citation and the full derivation.
- **`gam_family._gaussian_deviance_terms` corrected** — a real,
  pre-existing factor-of-2 defect (shipped at ladder slice 1, ADR-229,
  where it was harmless: Gaussian's deviance had exactly one consumer, the
  scale-invariant IRLS convergence test). Found in MEASURE FIRST, before any
  new formula was written: `mgcv`'s own `gaussian()$deviance` is the plain
  RSS, not `2*RSS`. Fixed, and the ADR-229 test that had pinned the wrong
  value is corrected.
- **`gam_free_scale_reml_conformance.py`** — the score-level Stage-C claim,
  `FREE_SCALE_REML_SCORE_CLAIM`, for BOTH free-scale families. Gaussian is
  compared on the ABSOLUTE score (confirmed exact against `mgcv`'s
  `gcv.ubre`, including every additive constant); quasi-Poisson on PAIRWISE
  DIFFERENCES only (same convention ADR-196 already established for the
  known-scale Poisson criterion's own convention offset — quasi-likelihood
  has no proper saturated log-likelihood).
- **`gam_gaussian_conformance.py` gains `GAUSSIAN_FREE_SP_CLAIM`** — the
  fit-level re-run of ladder slice 1's OWN three-term recipe (identical
  seed), now at free `sp` via `gam_model.fit_polaris_gam`, single-start,
  no `multistart` needed.
- **Two new R probes**: `scripts/gam_free_scale_reml_score_probe.R` (shared
  two-block design, three fixed `(sp1,sp2)` points, BOTH families,
  `method="REML"`) and `scripts/gam_gaussian_free_sp_probe.R` (slice 1's own
  recipe, free `sp`).
- **`gamma` explicitly NOT extended** to the free-scale branch — raises on
  `gamma != 1.0` for a `dispersion_fixed=False` family, a marked scope
  boundary rather than a guess (module docstring, ADR-231).

### Measured

- **Gaussian score, ABSOLUTE, 3 fixed `(sp1,sp2)` points, TIER 3**: diffs
  `0.000e+00`/`4.263e-14`/`-7.105e-14` against scores of order `~70` — float
  round-trip precision, first measurement, no iteration needed. Tier 1 read
  `-8.5e-14`/`-7.1e-14`/`-1.6e-13` on the same recipe — same verdict, same
  order of magnitude.
- **Quasi-Poisson score, PAIRWISE, 3 pairs, TIER 3**: residuals
  `4.263e-14`/`2.842e-14`/`-1.421e-14`, same order, first measurement. Tier 1
  read `-1.4e-14`/`-2.8e-14`/`-1.4e-14` on the same recipe.
- **Gaussian free-sp FIT** (ladder slice 1's own recipe, now free `sp`),
  TIER 3, `n=900`, `p=86`: `max_abs_eta_diff=2.933e-04`,
  `edf_total_diff=-0.0206`, `max_abs_term_edf_diff=0.0207`,
  `at_bound=False`, `converged=True` both sides, `agrees=True` — first
  measurement, no iteration needed. `max_abs_log10_sp_diff=0.6301` (reported,
  not gated), offset tripwire `3.553e-15` — two blocks land at very large
  `sp` on both sides, consistent with `mgcv` shrinking a low-signal term
  toward its null space. Tier 1 read `max_abs_eta_diff=1.874e-05`,
  `edf_total_diff=-0.000999`, `max_abs_log10_sp_diff=0.8245` on the same
  recipe — same verdict, same order of magnitude.
- **Both tiers agree in verdict and order of magnitude** — run
  [36242943352](https://github.com/jonathancrawford05/polaris-re/actions/runs/36242943352),
  oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), R 4.6.1 / mgcv 1.9.4. Full figures in ADR-231.
- **`MGCV_FEATURE_COVERAGE.md`**: §2.2 Gaussian row moves to fixed AND free
  `sp` tier 3; §2.3 quasi-Poisson row moves to score-level tier 3; §2.3's
  "Scale-estimated REML" row moves from NO to tier 3; the L5 ladder row
  marked climbed.
- **Ladder slice 1's own "fixed `sp` only" qualifier removed in this PR** —
  the plan's own acceptance criterion for this slice, not a follow-up.

**What was NOT attempted.** Quasi-Poisson's own FIT-level free-sp re-run (a
`PolarisGAM` measurement analogous to Gaussian's) — the plan's acceptance
criterion named only the score measurement and Gaussian's fit re-run.
Registering the `Gamma`/Tweedie families in `_FAMILY_LINKS` — this slice
unblocks them in principle (the free-scale branch works for any family), but
neither is registered, and registering one is separate work.

---

## Carried constraints — read before touching slice 4

Constraints 2-5 below were written for slice 1 and **all still hold**.
Constraint 1 is **superseded** (L5 closed it, ADR-231) and kept here, struck
through in substance, so a later reader does not have to reconstruct why
"fixed `sp` only" no longer applies to Gaussian. Constraint 6 is corrected in
place (slice 1 itself, not slice 3, was where the "only one family" wording
was falsified — already fixed, kept here as history).

1. ~~**Fixed `sp` only.**~~ **CLOSED by slice 3 (ADR-231).**
   `gam_reml.reml_score_general` now has a free-scale branch; Gaussian's own
   free-`sp` selection is measured (tier 3) and `agrees=True`.
   `test_gaussian_estimates_its_scale` still asserts the *premise*
   (Gaussian's scale is genuinely estimated) — that has not changed, only
   the criterion's inability to handle it, which is what this slice fixed.
2. **No new tolerance.** ADR-221's `eta`/`edf_total` bounds are **imported**,
   never redeclared — Anchor W5 forbids re-gating. Follow
   `gam_production_mi_conformance.py`'s import of
   `_AGREEMENT_TOLERANCE_ETA`/`_EDF`. Slice 3 followed this too — no new
   tolerance anywhere in its own claims.
3. **Tier 3 or it did not happen.** A local apt-R reading is a hypothesis
   (`ROUTINE_MGCV_PARITY.md`); only the pinned digest settles it.
4. **The `eta` offset trap.** Read `m$linear.predictors`, **never**
   `predict(type="link")` — the latter drops an argument-supplied offset and has
   already produced one `1.9751`-against-`2e-2` false reading in this epic. The
   existing probes carry a tripwire; copy it. Slice 3's own free-sp probe found
   this tripwire is NOT exactly `0.0` for a free-sp REML fit the way it is for
   a fixed-sp linear solve (`7.1e-15`, still ~1e12x inside tolerance) — a
   `< 1e-9` bound, not exact equality, is the right assertion for any FUTURE
   free-sp probe's own offset tripwire test.
5. **`REFERENCE_INTERNAL` exists now** (ADR-228, PR #236). A Polaris-vs-`mgcv`
   comparison is `INDEPENDENT` — but any `mgcv`-vs-`mgcv` column takes the new
   member, not `INDEPENDENT`.
6. **The reach split across the registry is the free scale, not the
   count/binary divide.** `quasipoisson(log)` and `gaussian(identity)` both
   carried `dispersion_fixed=False`; slice 3 closed BOTH at the score level
   and Gaussian at the fit level. Quasi-Poisson's own fit-level free-sp
   re-run is NOT done (see slice 3's "what was NOT attempted") — a future
   session wanting it can copy `GAUSSIAN_FREE_SP_CLAIM`'s shape directly.

---

## Open questions for the maintainer

None blocking. Slice 3's derivation source (Wood 2011 §2 eq. 4, PDF supplied
directly by the maintainer after web access was blocked) and its scope
boundary on `gamma` (not extended to the free-scale branch — raises rather
than guesses) are both recorded in ADR-231 for review.

---

## Where to pick up

`docs/PLAN_mgcv_capability_ladder.md` §3, **slice 4 — L3 factor-`by`**.
Slices 1, 2 and 3 are closed (ADR-229, ADR-230, ADR-231).

**Read the plan's own sizing correction first**: `s(x, by = fac)` on a
3-level factor produces **three separate smooths**, each with its own `sp`
— a term *multiplier*, not a term *parameter*. `TermSpec.by` is documented as
*numeric* and `TermSpec.factor` is **not** a factor-`by` flag (it marks the
`sz`/`fs` construction and is mutually exclusive with `by`,
`gam_term_spec.py:74-79`). So this slice owns a contract decision — widen
`by` to accept a factor, or add a field — before it owns any basis work.

Nearest template for the whole basis-plus-conformance shape — R probe,
conformance module with a declared claim, workflow probe step + compare step
+ path filters, tier-3 dispatch — remains **slices 1, 2 and 3**:
`scripts/gam_gaussian_probe.R` / `gam_re_probe.R` / `gam_re_free_sp_probe.R` /
`gam_free_scale_reml_score_probe.R` / `gam_gaussian_free_sp_probe.R` +
`src/polaris_re/analytics/gam_gaussian_conformance.py` /
`gam_re_conformance.py` / `gam_free_scale_reml_conformance.py`.

**A near-exact or exact agreement is a suspicion before it is a result** —
slices 1 and 2 needed a pair of independence tests (strip every
`mgcv`-produced key; check the compared quantity moves with the thing under
test) to make their agreements reportable rather than merely green. Slice 3's
Gaussian score comparison found something stronger — an EXACT match
(absolute, not shape-only) against `mgcv`'s own `gcv.ubre`, confirmed by
deriving the formula from the paper FIRST and only then measuring, which is
the strongest form this pattern can take. Any new slice landing a near-exact
or exact reading should still carry the strip/perturb pair.
